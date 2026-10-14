"""Classificação de severidade (P1-P4).

Funciona em 2 passos, fáceis de explicar:
1. Severidade BASE pelo tipo e valor da métrica (tabela de limites abaixo).
2. AJUSTE pelo ambiente: produção mantém; staging reduz 1 nível;
   development reduz 2 níveis (nunca abaixo de P4).
"""
from app.schemas import AlertIn, AlertType, Environment, Severity

ORDER = [Severity.P1, Severity.P2, Severity.P3, Severity.P4]

# Limites mínimos (valor >= limite) para P1, P2, P3. Abaixo de tudo: P4.
THRESHOLDS = {
    AlertType.CPU_HIGH: (95, 85, 70),          # %
    AlertType.MEMORY_HIGH: (95, 85, 70),       # %
    AlertType.DISK_HIGH: (95, 90, 80),         # %
    AlertType.LATENCY_HIGH: (5000, 2000, 1000),  # ms
}

# Quantos níveis a severidade "desce" fora de produção.
ENV_DOWNGRADE = {
    Environment.PRODUCTION: 0,
    Environment.STAGING: 1,
    Environment.DEVELOPMENT: 2,
}


def _base_severity(alert: AlertIn) -> Severity:
    if alert.alert_type == AlertType.SERVICE_DOWN:
        return Severity.P1
    p1, p2, p3 = THRESHOLDS[alert.alert_type]
    if alert.value >= p1:
        return Severity.P1
    if alert.value >= p2:
        return Severity.P2
    if alert.value >= p3:
        return Severity.P3
    return Severity.P4


def classify(alert: AlertIn) -> tuple[Severity, str]:
    """Devolve (severidade, motivo legível) para um alerta já validado."""
    base = _base_severity(alert)
    steps = ENV_DOWNGRADE[alert.environment]
    final = ORDER[min(ORDER.index(base) + steps, len(ORDER) - 1)]

    reason = f"{alert.alert_type.value}"
    if alert.value is not None:
        reason += f"={alert.value:g}"
    reason += f" -> base {base.value}"
    if final != base:
        reason += f"; ambiente '{alert.environment.value}' reduz para {final.value}"
    return final, reason
