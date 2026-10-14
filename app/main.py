"""API FastAPI do CloudOps Alert Bridge.

Fluxo de POST /alerts:
  validação (Pydantic) -> classificação P1-P4 -> montagem da issue -> Jira Cloud
"""
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, status
from fastapi.responses import FileResponse, JSONResponse

from app.classifier import classify
from app.config import JiraConfigError, load_jira_settings
from app.incident import build_description, build_summary
from app.jira_client import JiraClient, JiraError
from app.logging_config import setup_logging
from app.schemas import AlertIn, AlertOut, ErrorOut, JiraIssueOut, Severity

# Carrega o arquivo .env (se existir) da pasta do projeto para as variáveis de ambiente.
# Caminho explícito: sem ele, o python-dotenv sobe pelas pastas e poderia ler o .env
# de outro projeto. Variáveis já definidas no sistema têm prioridade sobre o .env.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

logger = setup_logging()
app = FastAPI(title="CloudOps Alert Bridge", version="0.2.0")


def build_jira_client() -> JiraClient:
    """Lê a configuração e cria o cliente. Lança JiraConfigError se incompleta."""
    return JiraClient(load_jira_settings())


def get_jira_client_factory() -> Callable[[], JiraClient]:
    """Dependência do FastAPI: entrega a *fábrica* do cliente, não o cliente.

    Assim a configuração só é lida depois que o alerta passou na validação
    (um alerta inválido continua recebendo 422 mesmo sem .env), e os testes
    podem substituir a fábrica por um Jira simulado.
    """
    return build_jira_client


def _error_response(http_status: int, err_type: str, code: str, message: str,
                    issue_created: Optional[bool], alert_id: str, severity: Severity) -> JSONResponse:
    body = ErrorOut(
        error={
            "type": err_type,
            "code": code,
            "message": message,
            "jira_result": "not_created" if issue_created is False else "unknown",
        },
        alert_id=alert_id,
        severity=severity,
    )
    return JSONResponse(status_code=http_status, content=body.model_dump(mode="json"))


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    """Interface web do simulador (HTML estático que chama POST /alerts)."""
    return FileResponse(PROJECT_ROOT / "static" / "index.html", media_type="text/html")


@app.get("/health")
def health() -> dict:
    """Verificação simples de que a API está de pé (não consulta o Jira)."""
    return {"status": "ok"}


@app.post(
    "/alerts",
    response_model=AlertOut,
    status_code=status.HTTP_201_CREATED,
    responses={
        500: {"model": ErrorOut, "description": "Integração com Jira não configurada"},
        502: {"model": ErrorOut, "description": "Jira recusou ou falhou ao criar a issue"},
        504: {"model": ErrorOut, "description": "Tempo esgotado na comunicação com o Jira"},
    },
)
def receive_alert(
    alert: AlertIn,
    jira_factory: Callable[[], JiraClient] = Depends(get_jira_client_factory),
):
    """Recebe um alerta, classifica a severidade e cria uma issue no Jira.

    - 201: issue criada (resposta inclui a chave, ex.: KAN-42)
    - 422: alerta inválido (validação do Pydantic)
    - 500: configuração do Jira ausente/inválida
    - 502/504: falha na comunicação com o Jira (ver `jira_result`)
    """
    severity, reason = classify(alert)
    alert_id = str(uuid.uuid4())
    log_fields = {
        "alert_id": alert_id,
        "source": alert.source,
        "host": alert.host,
        "alert_type": alert.alert_type.value,
        "environment": alert.environment.value,
        "value": alert.value,
        "severity": severity.value,
    }
    # O campo livre `message` não é logado: pode conter dados sensíveis.
    logger.info("alert_classified", extra={"fields": {**log_fields, "reason": reason}})

    # 1) Configuração
    try:
        jira = jira_factory()
    except JiraConfigError as exc:
        logger.error("jira_config_error", extra={"fields": {**log_fields, "error": str(exc)}})
        return _error_response(500, "configuration_error", "jira_not_configured", str(exc),
                               False, alert_id, severity)

    # 2) Criação da issue
    try:
        issue = jira.create_issue(
            summary=build_summary(alert, severity),
            description=build_description(alert, severity, reason, alert_id),
            priority=jira.settings.priority_map.get(severity.value),
        )
    except JiraError as exc:
        logger.error("jira_issue_failed", extra={"fields": {
            **log_fields,
            "error_code": exc.code,
            "jira_status": exc.jira_status,
            "issue_created": "no" if exc.issue_created is False else "unknown",
            "error": exc.message,
        }})
        return _error_response(exc.http_status, "integration_error", exc.code, exc.message,
                               exc.issue_created, alert_id, severity)

    logger.info("jira_issue_created", extra={"fields": {
        **log_fields, "jira_issue_key": issue.key, "jira_issue_id": issue.id,
    }})

    return AlertOut(
        alert_id=alert_id,
        severity=severity,
        reason=reason,
        host=alert.host,
        alert_type=alert.alert_type,
        environment=alert.environment,
        received_at=datetime.now(timezone.utc),
        jira_issue=JiraIssueOut(id=issue.id, key=issue.key, url=issue.url),
    )
