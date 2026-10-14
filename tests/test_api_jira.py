"""Testes do endpoint POST /alerts integrado ao Jira (simulado)."""
import base64
import json
import logging

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app, build_jira_client, get_jira_client_factory
from tests.conftest import FAKE_EMAIL, FAKE_TOKEN, make_settings
from tests.test_incident import adf_text

client = TestClient(app)
ENCODED_AUTH = base64.b64encode(f"{FAKE_EMAIL}:{FAKE_TOKEN}".encode()).decode()


def payload(**overrides):
    base = {"source": "test", "host": "web-01", "alert_type": "cpu_high",
            "environment": "production", "value": 97}
    base.update(overrides)
    return base


def assert_no_secrets(*texts):
    for text in texts:
        assert FAKE_TOKEN not in text
        assert ENCODED_AUTH not in text


def test_success_returns_issue_and_sends_alert_data(jira_stub):
    r = client.post("/alerts", json=payload())
    assert r.status_code == 201
    body = r.json()
    assert body["jira_issue"] == {"id": "10042", "key": "KAN-42",
                                  "url": "https://exemplo-teste.atlassian.net/browse/KAN-42"}
    assert len(jira_stub.requests) == 1
    fields = json.loads(jira_stub.requests[0].content)["fields"]
    assert fields["project"] == {"key": "KAN"}
    assert fields["summary"] == "[P1] Uso de CPU elevado em web-01 (production)"
    text = adf_text(fields["description"])
    assert body["alert_id"] in text
    assert "P1 — Crítica" in text and "97%" in text


@pytest.mark.parametrize("alert,expected_priority", [
    (payload(value=97), "Highest"),       # P1
    (payload(value=90), "High"),          # P2
    (payload(value=75), "Medium"),        # P3
    (payload(value=50), "Low"),           # P4
])
def test_severity_mapped_to_configured_priority(jira_stub, alert, expected_priority):
    jira_stub.settings = make_settings(priority_map={
        "P1": "Highest", "P2": "High", "P3": "Medium", "P4": "Low"})
    assert client.post("/alerts", json=alert).status_code == 201
    fields = json.loads(jira_stub.requests[0].content)["fields"]
    assert fields["priority"] == {"name": expected_priority}


def test_invalid_alert_is_422_and_jira_not_called(jira_stub):
    r = client.post("/alerts", json=payload(value=None))
    assert r.status_code == 422
    assert jira_stub.requests == []


def test_invalid_alert_is_422_even_without_config():
    # Usa a fábrica real com o ambiente vazio: a validação vem antes da configuração.
    app.dependency_overrides[get_jira_client_factory] = lambda: build_jira_client
    assert client.post("/alerts", json=payload(alert_type="banana")).status_code == 422


def test_missing_config_returns_500_configuration_error():
    app.dependency_overrides[get_jira_client_factory] = lambda: build_jira_client
    r = client.post("/alerts", json=payload())
    assert r.status_code == 500
    err = r.json()["error"]
    assert err["type"] == "configuration_error"
    assert err["code"] == "jira_not_configured"
    assert err["jira_result"] == "not_created"
    assert "JIRA_API_TOKEN" in err["message"]
    assert r.json()["severity"] == "P1"


def raise_(exc_cls):
    def handler(request):
        raise exc_cls("simulado", request=request)
    return handler


@pytest.mark.parametrize("handler,status,code,result", [
    (lambda r: httpx.Response(401), 502, "jira_auth_failed", "not_created"),
    (lambda r: httpx.Response(403), 502, "jira_permission_denied", "not_created"),
    (lambda r: httpx.Response(404, json={"errorMessages": ["No project could be found with key 'KAN'."]}),
     502, "jira_not_found", "not_created"),
    (lambda r: httpx.Response(400, json={"errors": {"issuetype": "Specify a valid issue type"}}),
     502, "jira_rejected", "not_created"),
    (lambda r: httpx.Response(503), 502, "jira_unavailable", "unknown"),
    (raise_(httpx.ConnectError), 502, "jira_unavailable", "not_created"),
    (raise_(httpx.ReadTimeout), 504, "jira_timeout", "unknown"),
    (lambda r: httpx.Response(201, text="<html>"), 502, "jira_unexpected_response", "unknown"),
])
def test_integration_failures_never_report_success(jira_stub, caplog, handler, status, code, result):
    jira_stub.handler = handler
    with caplog.at_level(logging.INFO, logger="alert_bridge"):
        r = client.post("/alerts", json=payload())
    assert r.status_code == status
    body = r.json()
    assert "jira_issue" not in body
    assert body["error"]["type"] == "integration_error"
    assert body["error"]["code"] == code
    assert body["error"]["jira_result"] == result
    assert body["alert_id"] and body["severity"] == "P1"
    # Nem a resposta nem os logs podem conter o token ou o cabeçalho de autorização.
    assert_no_secrets(r.text, caplog.text, *(str(rec.__dict__) for rec in caplog.records))
    assert any(rec.getMessage() == "jira_issue_failed" for rec in caplog.records)


def test_success_log_has_issue_key_and_no_secrets_or_message(caplog):
    with caplog.at_level(logging.INFO, logger="alert_bridge"):
        r = client.post("/alerts", json=payload(message="senha=supersecreta"))
    assert r.status_code == 201
    rec = next(x for x in caplog.records if x.getMessage() == "jira_issue_created")
    assert rec.fields["jira_issue_key"] == "KAN-42"
    all_logs = " ".join(str(x.__dict__) for x in caplog.records)
    assert_no_secrets(all_logs)
    assert "supersecreta" not in all_logs  # campo livre `message` não é logado
