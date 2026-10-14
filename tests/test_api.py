import json
import logging

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def payload(**overrides):
    base = {"source": "test", "host": "web-01", "alert_type": "cpu_high",
            "environment": "production", "value": 97}
    base.update(overrides)
    return base


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_valid_alert_returns_201_and_p1():
    r = client.post("/alerts", json=payload())
    assert r.status_code == 201
    body = r.json()
    assert body["severity"] == "P1"
    assert body["alert_id"]


def test_service_down_without_value_is_valid():
    r = client.post("/alerts", json=payload(alert_type="service_down", value=None))
    assert r.status_code == 201
    assert r.json()["severity"] == "P1"


def test_metric_alert_without_value_returns_422():
    r = client.post("/alerts", json=payload(value=None))
    assert r.status_code == 422


def test_invalid_alert_type_returns_422():
    assert client.post("/alerts", json=payload(alert_type="banana")).status_code == 422


def test_missing_host_returns_422():
    data = payload()
    del data["host"]
    assert client.post("/alerts", json=data).status_code == 422


def test_percentage_over_100_returns_422():
    assert client.post("/alerts", json=payload(value=150)).status_code == 422


def test_negative_value_returns_422():
    assert client.post("/alerts", json=payload(value=-1)).status_code == 422


def test_malformed_json_returns_422():
    r = client.post("/alerts", content="{nao e json", headers={"Content-Type": "application/json"})
    assert r.status_code == 422


def test_structured_log_is_json(caplog):
    from app.logging_config import JsonFormatter

    with caplog.at_level(logging.INFO, logger="alert_bridge"):
        client.post("/alerts", json=payload())
    record = next(r for r in caplog.records if r.getMessage() == "alert_classified")
    line = json.loads(JsonFormatter().format(record))
    assert line["severity"] == "P1"
    assert line["host"] == "web-01"
