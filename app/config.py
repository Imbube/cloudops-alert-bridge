"""Configuração da integração com o Jira, lida de variáveis de ambiente.

A validação acontece ANTES de qualquer chamada externa: se faltar algo,
a aplicação responde com um erro claro, sem nunca exibir o valor do token.
"""
import os
import re
from dataclasses import dataclass, field
from typing import Mapping, Optional
from urllib.parse import urlparse

DEFAULT_PROJECT_KEY = "KAN"
DEFAULT_ISSUE_TYPE = "Task"
DEFAULT_TIMEOUT_SECONDS = 10.0
SEVERITIES = ("P1", "P2", "P3", "P4")

PROJECT_KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]{1,9}$")


class JiraConfigError(Exception):
    """Configuração ausente ou inválida. A mensagem nunca contém segredos."""


@dataclass(frozen=True)
class JiraSettings:
    base_url: str
    email: str
    # repr=False: se o objeto for impresso/logado por engano, o token não aparece.
    api_token: str = field(repr=False)
    project_key: str = DEFAULT_PROJECT_KEY
    issue_type: str = DEFAULT_ISSUE_TYPE
    # Ex.: {"P1": "Highest", ...}. Vazio = não enviar prioridade (usa o padrão do Jira).
    priority_map: Mapping[str, str] = field(default_factory=dict)
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS


def _parse_priority_map(raw: str) -> dict[str, str]:
    """Converte 'P1=Highest,P2=High,P3=Medium,P4=Low' em dicionário."""
    result: dict[str, str] = {}
    for part in raw.split(","):
        if not part.strip():
            continue
        if "=" not in part:
            raise JiraConfigError(
                "JIRA_PRIORITY_MAP inválido. Formato esperado: P1=Nome,P2=Nome,P3=Nome,P4=Nome"
            )
        sev, name = (s.strip() for s in part.split("=", 1))
        if sev not in SEVERITIES or not name:
            raise JiraConfigError(f"JIRA_PRIORITY_MAP: entrada inválida '{sev}'. Use P1 a P4.")
        result[sev] = name
    if result and set(result) != set(SEVERITIES):
        faltando = sorted(set(SEVERITIES) - set(result))
        raise JiraConfigError(f"JIRA_PRIORITY_MAP incompleto; faltando: {', '.join(faltando)}")
    return result


def load_jira_settings(env: Optional[Mapping[str, str]] = None) -> JiraSettings:
    """Lê e valida as variáveis. `env` pode ser injetado nos testes."""
    env = os.environ if env is None else env

    def get(name: str) -> str:
        return (env.get(name) or "").strip()

    required = ["JIRA_BASE_URL", "JIRA_EMAIL", "JIRA_API_TOKEN"]
    missing = [name for name in required if not get(name)]
    if missing:
        # Só os NOMES das variáveis aparecem na mensagem, nunca valores.
        raise JiraConfigError(
            "Integração com Jira não configurada. Variáveis ausentes: "
            + ", ".join(missing)
            + ". Copie .env.example para .env e preencha os valores."
        )

    base_url = get("JIRA_BASE_URL").rstrip("/")
    parsed = urlparse(base_url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise JiraConfigError("JIRA_BASE_URL deve ser uma URL HTTPS, ex.: https://sua-empresa.atlassian.net")
    if parsed.username or parsed.password:
        raise JiraConfigError("JIRA_BASE_URL não deve conter usuário/senha. Use JIRA_EMAIL e JIRA_API_TOKEN.")
    if parsed.path not in ("", "/") or parsed.query:
        raise JiraConfigError("JIRA_BASE_URL deve conter apenas o domínio, ex.: https://sua-empresa.atlassian.net")

    email = get("JIRA_EMAIL")
    if "@" not in email:
        raise JiraConfigError("JIRA_EMAIL inválido: informe o e-mail da conta Atlassian.")

    project_key = get("JIRA_PROJECT_KEY") or DEFAULT_PROJECT_KEY
    if not PROJECT_KEY_RE.match(project_key):
        raise JiraConfigError("JIRA_PROJECT_KEY inválido: use a chave do projeto em maiúsculas, ex.: KAN")

    timeout_raw = get("JIRA_TIMEOUT_SECONDS")
    try:
        timeout = float(timeout_raw) if timeout_raw else DEFAULT_TIMEOUT_SECONDS
    except ValueError:
        raise JiraConfigError("JIRA_TIMEOUT_SECONDS deve ser um número (segundos).") from None
    if not 0 < timeout <= 60:
        raise JiraConfigError("JIRA_TIMEOUT_SECONDS deve estar entre 0 e 60.")

    return JiraSettings(
        base_url=base_url,
        email=email,
        api_token=get("JIRA_API_TOKEN"),
        project_key=project_key,
        issue_type=get("JIRA_ISSUE_TYPE") or DEFAULT_ISSUE_TYPE,
        priority_map=_parse_priority_map(get("JIRA_PRIORITY_MAP")),
        timeout_seconds=timeout,
    )
