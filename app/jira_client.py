"""Cliente da API REST do Jira Cloud (v3).

Responsabilidade única: falar HTTP com o Jira. Não conhece regras de
severidade nem o formato dos alertas — recebe título, descrição e prioridade
já prontos.

Autenticação: HTTP Basic com "e-mail:API token" sobre HTTPS, conforme
https://developer.atlassian.com/cloud/jira/platform/basic-auth-for-rest-apis/
"""
import re
from dataclasses import dataclass
from typing import Any, Optional

import httpx

from app.config import JiraSettings

USER_AGENT = "cloudops-alert-bridge/0.2"
ISSUE_KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]+-\d+$")


# --------------------------------------------------------------------------- #
# Erros
# --------------------------------------------------------------------------- #
class JiraError(Exception):
    """Falha de integração. As mensagens são escritas por nós e nunca incluem
    credenciais, cabeçalhos ou o texto bruto de exceções de rede."""

    code = "jira_error"
    http_status = 502  # Bad Gateway: o serviço externo (Jira) falhou

    def __init__(self, message: str, *, issue_created: Optional[bool] = False,
                 jira_status: Optional[int] = None):
        super().__init__(message)
        self.message = message
        # False = com certeza NÃO foi criada; None = desconhecido (não repetir às cegas)
        self.issue_created = issue_created
        self.jira_status = jira_status


class JiraAuthError(JiraError):
    code = "jira_auth_failed"


class JiraPermissionError(JiraError):
    code = "jira_permission_denied"


class JiraNotFoundError(JiraError):
    code = "jira_not_found"


class JiraRejectedError(JiraError):
    code = "jira_rejected"


class JiraUnavailableError(JiraError):
    code = "jira_unavailable"


class JiraTimeoutError(JiraError):
    code = "jira_timeout"
    http_status = 504  # Gateway Timeout


class JiraUnexpectedResponseError(JiraError):
    code = "jira_unexpected_response"


# --------------------------------------------------------------------------- #
# Resultado
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class CreatedIssue:
    id: str
    key: str
    url: str  # link navegável: https://<site>/browse/KAN-123


# --------------------------------------------------------------------------- #
# Cliente
# --------------------------------------------------------------------------- #
def _ref(value: str) -> dict:
    """Jira aceita referência por id (numérico) ou por nome."""
    return {"id": value} if value.isdigit() else {"name": value}


def _jira_error_details(response: httpx.Response) -> str:
    """Extrai as mensagens de erro do corpo padrão do Jira
    ({"errorMessages": [...], "errors": {campo: msg}}), limitadas em tamanho."""
    try:
        body = response.json()
    except ValueError:
        return ""
    if not isinstance(body, dict):
        return ""
    parts = [str(m) for m in body.get("errorMessages") or []]
    errors = body.get("errors") or {}
    if isinstance(errors, dict):
        parts += [f"{k}: {v}" for k, v in errors.items()]
    return "; ".join(parts)[:500]


class JiraClient:
    def __init__(self, settings: JiraSettings, transport: Optional[httpx.BaseTransport] = None):
        self.settings = settings
        # `transport` permite que os testes simulem o Jira sem rede (httpx.MockTransport).
        self._transport = transport

    def _http(self) -> httpx.Client:
        return httpx.Client(
            base_url=self.settings.base_url,
            auth=httpx.BasicAuth(self.settings.email, self.settings.api_token),
            timeout=httpx.Timeout(self.settings.timeout_seconds),
            headers={"Accept": "application/json", "User-Agent": USER_AGENT},
            transport=self._transport,
            # verify=True é o padrão do httpx: o certificado TLS é sempre verificado.
        )

    def _send(self, method: str, path: str, **kwargs) -> httpx.Response:
        """Envia a requisição e converte falhas de rede em erros seguros.

        Distingue falhas em que a requisição certamente não chegou ao Jira
        (conexão recusada / timeout de conexão) daquelas em que ela pode ter
        sido processada (timeout de leitura, conexão caída no meio).
        """
        try:
            with self._http() as client:
                return client.request(method, path, **kwargs)
        except (httpx.ConnectTimeout, httpx.PoolTimeout):
            raise JiraTimeoutError(
                "Tempo esgotado ao conectar ao Jira. A requisição não foi enviada.",
                issue_created=False) from None
        except httpx.TimeoutException:
            raise JiraTimeoutError(
                "Tempo esgotado aguardando resposta do Jira. Não é possível saber se a "
                "issue foi criada: verifique no Jira antes de reenviar o alerta.",
                issue_created=None) from None
        except httpx.ConnectError:
            raise JiraUnavailableError(
                "Não foi possível conectar ao Jira (DNS, rede ou TLS). A requisição não foi enviada.",
                issue_created=False) from None
        except httpx.TransportError:
            raise JiraUnavailableError(
                "A conexão com o Jira foi interrompida durante a requisição. Não é possível "
                "saber se a issue foi criada: verifique no Jira antes de reenviar o alerta.",
                issue_created=None) from None
        # `from None` descarta a exceção original, evitando vazar detalhes internos.

    def _raise_for_error(self, response: httpx.Response) -> None:
        status = response.status_code
        if 200 <= status < 300:
            return
        details = _jira_error_details(response)
        suffix = f" Detalhes do Jira: {details}" if details else ""

        if status == 401:
            raise JiraAuthError(
                "Jira recusou a autenticação (401). Verifique JIRA_EMAIL e JIRA_API_TOKEN.",
                jira_status=status)
        if status == 403:
            raise JiraPermissionError(
                "Sem permissão no Jira (403). A conta precisa poder criar issues no projeto "
                f"{self.settings.project_key}.{suffix}", jira_status=status)
        if status == 404:
            raise JiraNotFoundError(
                "Recurso não encontrado no Jira (404). Verifique JIRA_BASE_URL e "
                f"JIRA_PROJECT_KEY.{suffix}", jira_status=status)
        if status == 429:
            raise JiraUnavailableError(
                "Limite de requisições do Jira atingido (429). Tente novamente mais tarde.",
                jira_status=status)
        if status >= 500:
            raise JiraUnavailableError(
                f"Jira retornou erro interno ({status}). Não é possível garantir que a issue "
                "não foi criada: verifique no Jira antes de reenviar.",
                issue_created=None, jira_status=status)
        if 400 <= status < 500:
            raise JiraRejectedError(
                f"Jira rejeitou a requisição ({status}). Verifique projeto, tipo de issue e "
                f"prioridade configurados.{suffix}", jira_status=status)
        raise JiraUnexpectedResponseError(
            f"Resposta inesperada do Jira (HTTP {status}).", jira_status=status)

    # ------------------------------------------------------------------ #
    def create_issue(self, summary: str, description: dict,
                     priority: Optional[str] = None) -> CreatedIssue:
        """Cria uma issue no projeto configurado (POST /rest/api/3/issue).

        `description` deve estar em Atlassian Document Format (ADF), exigido pela v3.
        """
        fields: dict[str, Any] = {
            "project": {"key": self.settings.project_key},
            "issuetype": _ref(self.settings.issue_type),
            "summary": summary,
            "description": description,
        }
        if priority:
            fields["priority"] = _ref(priority)

        response = self._send("POST", "/rest/api/3/issue", json={"fields": fields})
        self._raise_for_error(response)

        # Só consideramos sucesso com HTTP 201 e um corpo válido com id e key.
        if response.status_code != 201:
            raise JiraUnexpectedResponseError(
                f"Jira respondeu HTTP {response.status_code} em vez de 201. Verifique no Jira "
                "se a issue foi criada.", issue_created=None, jira_status=response.status_code)
        try:
            body = response.json()
        except ValueError:
            body = None
        issue_id = body.get("id") if isinstance(body, dict) else None
        key = body.get("key") if isinstance(body, dict) else None
        if not (isinstance(issue_id, str) and isinstance(key, str) and ISSUE_KEY_RE.match(key)
                and key.startswith(self.settings.project_key + "-")):
            raise JiraUnexpectedResponseError(
                "Jira respondeu 201, mas sem id/key válidos para o projeto "
                f"{self.settings.project_key}. Verifique no Jira se a issue foi criada.",
                issue_created=None, jira_status=201)

        return CreatedIssue(id=issue_id, key=key, url=f"{self.settings.base_url}/browse/{key}")

    def get_json(self, path: str, params: Optional[dict] = None) -> Any:
        """GET somente leitura (usado pelo script de verificação da configuração)."""
        response = self._send("GET", path, params=params)
        self._raise_for_error(response)
        try:
            return response.json()
        except ValueError:
            raise JiraUnexpectedResponseError("Jira retornou um corpo que não é JSON.") from None
