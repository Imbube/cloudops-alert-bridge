"""Testes da interface web servida em GET /."""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_index_serves_html():
    r = client.get("/")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    html = r.text
    assert "CloudOps Simulator" in html
    assert 'fetch("/alerts"' in html


def test_index_options_match_api_enums():
    """Os valores enviados pelos dropdowns precisam existir nos enums da API."""
    html = client.get("/").text
    for value in ["cpu_high", "memory_high", "disk_high", "latency_high", "service_down",
                  "production", "staging", "development"]:
        assert f'value="{value}"' in html


def test_index_has_random_alert_button():
    html = client.get("/").text
    assert 'id="random"' in html
    # O sorteio só usa tipos que existem na API.
    for value in ["cpu_high", "memory_high", "disk_high", "latency_high", "service_down"]:
        assert f"{value}:" in html


def test_index_not_in_openapi():
    assert "/" not in client.get("/openapi.json").json()["paths"]
