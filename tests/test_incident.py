from datetime import datetime, timezone

from app.incident import build_description, build_summary
from app.schemas import AlertIn, Severity


def adf_text(node) -> str:
    """Concatena todo o texto de um documento ADF (para facilitar asserts)."""
    if isinstance(node, dict):
        return node.get("text", "") + "".join(adf_text(c) for c in node.get("content", []))
    return ""


def test_summary_format():
    alert = AlertIn(source="prometheus", host="web-01", alert_type="cpu_high", value=98)
    assert build_summary(alert, Severity.P1) == "[P1] Uso de CPU elevado em web-01 (production)"


def test_description_contains_alert_data():
    ts = datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc)
    alert = AlertIn(source="prometheus", host="web-01", alert_type="cpu_high", value=98,
                    environment="production", message="CPU travada", timestamp=ts)
    doc = build_description(alert, Severity.P1, "cpu_high=98 -> base P1", "abc-123")
    assert doc["type"] == "doc" and doc["version"] == 1
    text = adf_text(doc)
    for expected in ["prometheus", "P1 — Crítica", "production", "web-01", "CPU", "98%",
                     "2026-10-13T12:00:00+00:00", "abc-123", "cpu_high=98 -> base P1",
                     "CPU travada"]:
        assert expected in text


def test_service_down_has_no_metric_and_no_invented_data():
    alert = AlertIn(source="s", host="api-02", alert_type="service_down")
    text = adf_text(build_description(alert, Severity.P1, "r", "id-1"))
    assert "Valor observado" not in text
    assert "Métrica" not in text
    assert "Mensagem do alerta" not in text
    assert "gerado no recebimento" in text  # timestamp não veio no alerta


def test_latency_unit():
    alert = AlertIn(source="s", host="h", alert_type="latency_high", value=2300)
    assert "2300 ms" in adf_text(build_description(alert, Severity.P2, "r", "id"))
