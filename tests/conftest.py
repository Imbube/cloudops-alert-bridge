"""Fixtures compartilhadas.

Garantia de segurança: NENHUM teste fala com o Jira real.
- As variáveis JIRA_* são removidas do ambiente em cada teste (mesmo que exista um .env local).
- A dependência do FastAPI é substituída por um cliente com httpx.MockTransport,
  que responde em memória, sem rede.
"""
import httpx
import pytest

from app.config import JiraSettings
from app.jira_client import JiraClient
from app.main import app, get_jira_client_factory

FAKE_BASE_URL = "https://exemplo-teste.atlassian.net"
FAKE_EMAIL = "bot@example.com"
FAKE_TOKEN = "TOKEN-FICTICIO-NAO-REAL-123456"

JIRA_VARS = ["JIRA_BASE_URL", "JIRA_EMAIL", "JIRA_API_TOKEN", "JIRA_PROJECT_KEY",
             "JIRA_ISSUE_TYPE", "JIRA_PRIORITY_MAP", "JIRA_TIMEOUT_SECONDS"]


def make_settings(**overrides) -> JiraSettings:
    data = dict(base_url=FAKE_BASE_URL, email=FAKE_EMAIL, api_token=FAKE_TOKEN,
                project_key="KAN", issue_type="Task", priority_map={}, timeout_seconds=5)
    data.update(overrides)
    return JiraSettings(**data)


def created_response(request: httpx.Request) -> httpx.Response:
    """Resposta de sucesso no formato documentado do POST /rest/api/3/issue."""
    return httpx.Response(201, json={
        "id": "10042", "key": "KAN-42", "self": f"{FAKE_BASE_URL}/rest/api/3/issue/10042",
    })


class JiraStub:
    """Jira falso: registra as requisições recebidas e responde com `handler`."""

    def __init__(self):
        self.requests: list[httpx.Request] = []
        self.handler = created_response
        self.settings = make_settings()

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.handler(request)

    def client(self) -> JiraClient:
        return JiraClient(self.settings, transport=httpx.MockTransport(self))


@pytest.fixture
def jira_stub() -> JiraStub:
    return JiraStub()


@pytest.fixture(autouse=True)
def isolate_from_real_jira(monkeypatch, jira_stub):
    for name in JIRA_VARS:
        monkeypatch.delenv(name, raising=False)
    app.dependency_overrides[get_jira_client_factory] = lambda: jira_stub.client
    yield
    app.dependency_overrides.clear()
