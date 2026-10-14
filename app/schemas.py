"""Modelos de dados (contratos) da API, validados pelo Pydantic."""
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, model_validator


class AlertType(str, Enum):
    CPU_HIGH = "cpu_high"            # valor em %
    MEMORY_HIGH = "memory_high"      # valor em %
    DISK_HIGH = "disk_high"          # valor em %
    LATENCY_HIGH = "latency_high"    # valor em milissegundos
    SERVICE_DOWN = "service_down"    # não precisa de valor


class Environment(str, Enum):
    PRODUCTION = "production"
    STAGING = "staging"
    DEVELOPMENT = "development"


class Severity(str, Enum):
    P1 = "P1"  # crítico
    P2 = "P2"  # alto
    P3 = "P3"  # médio
    P4 = "P4"  # baixo


# Tipos que dependem de uma métrica numérica para serem classificados.
METRIC_TYPES = {
    AlertType.CPU_HIGH,
    AlertType.MEMORY_HIGH,
    AlertType.DISK_HIGH,
    AlertType.LATENCY_HIGH,
}


class AlertIn(BaseModel):
    """Alerta recebido de uma ferramenta de monitoramento."""

    source: str = Field(..., min_length=1, max_length=100, examples=["prometheus"])
    host: str = Field(..., min_length=1, max_length=100, examples=["web-01"])
    alert_type: AlertType
    environment: Environment = Environment.PRODUCTION
    value: Optional[float] = Field(None, ge=0, description="Valor medido (% ou ms)")
    message: Optional[str] = Field(None, max_length=500)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @model_validator(mode="after")
    def check_value_required(self):
        # Regra de negócio: alertas de métrica precisam do valor medido.
        if self.alert_type in METRIC_TYPES and self.value is None:
            raise ValueError(f"'value' é obrigatório para alert_type '{self.alert_type.value}'")
        # Percentuais não podem passar de 100.
        if self.alert_type in {AlertType.CPU_HIGH, AlertType.MEMORY_HIGH, AlertType.DISK_HIGH}:
            if self.value is not None and self.value > 100:
                raise ValueError("'value' deve ser <= 100 para métricas em porcentagem")
        return self


class JiraIssueOut(BaseModel):
    """Issue criada no Jira Cloud."""

    id: str
    key: str = Field(..., examples=["KAN-42"])
    url: str


class AlertOut(BaseModel):
    """Resposta devolvida após processar o alerta e criar a issue no Jira."""

    alert_id: str
    severity: Severity
    reason: str
    host: str
    alert_type: AlertType
    environment: Environment
    received_at: datetime
    jira_issue: JiraIssueOut


class ErrorInfo(BaseModel):
    type: str = Field(..., examples=["integration_error"])  # ou "configuration_error"
    code: str = Field(..., examples=["jira_auth_failed"])
    message: str
    # not_created = com certeza não foi criada; unknown = verificar no Jira antes de reenviar
    jira_result: str = Field(..., examples=["not_created"])


class ErrorOut(BaseModel):
    """Resposta quando o alerta é válido, mas a issue não pôde ser criada."""

    error: ErrorInfo
    alert_id: str
    severity: Severity
