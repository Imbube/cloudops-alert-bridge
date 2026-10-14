"""Monta o conteúdo da issue (título + descrição) a partir de um alerta classificado.

Separado do cliente Jira para que a formatação possa ser testada sem HTTP
e para que o cliente não precise conhecer o formato dos alertas.
A descrição usa Atlassian Document Format (ADF), exigido pela REST API v3.
"""
from app.schemas import AlertIn, AlertType, Severity

SEVERITY_LABELS = {
    Severity.P1: "Crítica",
    Severity.P2: "Alta",
    Severity.P3: "Média",
    Severity.P4: "Baixa",
}

# Nome legível da métrica e unidade do valor.
ALERT_INFO = {
    AlertType.CPU_HIGH: ("Uso de CPU elevado", "CPU", "%"),
    AlertType.MEMORY_HIGH: ("Uso de memória elevado", "Memória", "%"),
    AlertType.DISK_HIGH: ("Uso de disco elevado", "Disco", "%"),
    AlertType.LATENCY_HIGH: ("Latência elevada", "Latência", " ms"),
    AlertType.SERVICE_DOWN: ("Serviço indisponível", None, None),
}


def build_summary(alert: AlertIn, severity: Severity) -> str:
    """Ex.: '[P1] Uso de CPU elevado em web-01 (production)'"""
    title = ALERT_INFO[alert.alert_type][0]
    return f"[{severity.value}] {title} em {alert.host} ({alert.environment.value})"[:255]


def _text(value: str) -> dict:
    return {"type": "text", "text": value}


def _bold(value: str) -> dict:
    return {"type": "text", "text": value, "marks": [{"type": "strong"}]}


def _item(label: str, value: str) -> dict:
    return {"type": "listItem", "content": [
        {"type": "paragraph", "content": [_bold(f"{label}: "), _text(value)]}
    ]}


def build_description(alert: AlertIn, severity: Severity, reason: str, alert_id: str) -> dict:
    """Descrição técnica em ADF. Só inclui campos que existem no alerta."""
    title, metric, unit = ALERT_INFO[alert.alert_type]

    # Se o alerta não trouxe timestamp, o schema gerou um no recebimento — deixamos isso explícito.
    ts = alert.timestamp.isoformat()
    if "timestamp" not in alert.model_fields_set:
        ts += " (gerado no recebimento; o alerta não informou horário)"

    items = [
        _item("Origem", f"{alert.source} (via CloudOps Alert Bridge)"),
        _item("Severidade", f"{severity.value} — {SEVERITY_LABELS[severity]}"),
        _item("Ambiente", alert.environment.value),
        _item("Host", alert.host),
        _item("Tipo de alerta", f"{title} ({alert.alert_type.value})"),
    ]
    if metric and alert.value is not None:
        items.append(_item("Métrica", metric))
        items.append(_item("Valor observado", f"{alert.value:g}{unit}"))
    items += [
        _item("Data e hora do evento", ts),
        _item("ID do alerta", alert_id),
        _item("Critério de classificação", reason),
    ]
    if alert.message:
        items.append(_item("Mensagem do alerta", alert.message))

    return {
        "type": "doc",
        "version": 1,
        "content": [
            {"type": "paragraph", "content": [
                _text(f"{title} detectado em {alert.host}. Issue aberta automaticamente.")
            ]},
            {"type": "bulletList", "content": items},
            {"type": "paragraph", "content": [
                _text("Gerado pelo CloudOps Alert Bridge (projeto demonstrativo; alertas simulados).")
            ]},
        ],
    }
