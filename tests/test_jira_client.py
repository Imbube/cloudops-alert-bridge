"""Testes do cliente Jira com httpx.MockTransport (sem rede, sem Jira real).

Importante: estes testes provam que o cliente monta e interpreta as
requisições corretamente; eles NÃO provam que a integração real funciona.
"""
import base64
import json

import httpx
import pytest

from app.jira_client import (
    JiraAuthError, JiraClient, JiraNotFoundError, JiraPermissionError, JiraRejectedError,
    JiraTimeoutError, JiraUnavailableError, JiraUnexpectedResponseError,
)
from tests.conftest import FAKE_EMAIL, FAKE_TOKEN, make_settings

ADF = {"type": "doc", "version": 1, "content": []}


def client_with(handler, **settings):
    calls = []

    def recorder(request):
        calls.append(request)
        return handler(request)

    return JiraClient(make_settings(**settings), transport=httpx.MockTransport(recorder)), calls


def ok(request):
    return httpx.Response(201, json={"id": "10042", "key": "KAN-42", "self": "x"})


# --------------------------------------------------------------------------- sucesso
def test_create_issue_success_returns_key_id_url():
    client, _ = client_with(ok)
    issue = client.create_issue("titulo", ADF)
    assert issue.key == "KAN-42"
    assert issue.id == "10042"
    assert issue.url == "https://exemplo-teste.atlassian.net/browse/KAN-42"


def test_request_uses_https_basic_auth_and_project_kan():
    client, calls = client_with(ok)
    client.create_issue("titulo", ADF)
    req = calls[0]
    assert req.method == "POST"
    assert req.url.scheme == "https"
    assert str(req.url) == "https://exemplo-teste.atlassian.net/rest/api/3/issue"
    expected = base64.b64encode(f"{FAKE_EMAIL}:{FAKE_TOKEN}".encode()).decode()
    assert req.headers["Authorization"] == f"Basic {expected}"
    assert req.headers["Accept"] == "application/json"
    fields = json.loads(req.content)["fields"]
    assert fields["project"] == {"key": "KAN"}
    assert fields["issuetype"] == {"name": "Task"}
    assert fields["summary"] == "titulo"
    assert fields["description"] == ADF
    assert "priority" not in fields  # sem mapeamento configurado, não envia prioridade


def test_issue_type_and_priority_by_id_or_name():
    client, calls = client_with(ok, issue_type="10001")
    client.create_issue("t", ADF, priority="Highest")
    fields = json.loads(calls[0].content)["fields"]
    assert fields["issuetype"] == {"id": "10001"}
    assert fields["priority"] == {"name": "Highest"}


def test_timeout_is_configured():
    client, _ = client_with(ok, timeout_seconds=7)
    with client._http() as http:
        assert http.timeout.read == 7
        assert http.timeout.connect == 7


# --------------------------------------------------------------------------- erros HTTP
@pytest.mark.parametrize("status,exc_type,created", [
    (401, JiraAuthError, False),
    (403, JiraPermissionError, False),
    (404, JiraNotFoundError, False),
    (400, JiraRejectedError, False),
    (429, JiraUnavailableError, False),
    (500, JiraUnavailableError, None),   # servidor falhou: resultado incerto
    (503, JiraUnavailableError, None),
])
def test_http_errors_are_mapped(status, exc_type, created):
    client, _ = client_with(lambda r: httpx.Response(status, json={"errorMessages": ["x"]}))
    with pytest.raises(exc_type) as exc:
        client.create_issue("t", ADF)
    assert exc.value.jira_status == status
    assert exc.value.issue_created is created


def test_400_includes_jira_error_details():
    body = {"errorMessages": [], "errors": {"issuetype": "Specify a valid issue type"}}
    client, _ = client_with(lambda r: httpx.Response(400, json=body))
    with pytest.raises(JiraRejectedError) as exc:
        client.create_issue("t", ADF)
    assert "issuetype: Specify a valid issue type" in exc.value.message


# --------------------------------------------------------------------------- rede
def raise_(exc_cls):
    def handler(request):
        raise exc_cls("simulado", request=request)
    return handler


def test_read_timeout_result_unknown():
    client, _ = client_with(raise_(httpx.ReadTimeout))
    with pytest.raises(JiraTimeoutError) as exc:
        client.create_issue("t", ADF)
    assert exc.value.issue_created is None
    assert exc.value.http_status == 504


def test_connect_timeout_not_created():
    client, _ = client_with(raise_(httpx.ConnectTimeout))
    with pytest.raises(JiraTimeoutError) as exc:
        client.create_issue("t", ADF)
    assert exc.value.issue_created is False


def test_connect_error_not_created():
    client, _ = client_with(raise_(httpx.ConnectError))
    with pytest.raises(JiraUnavailableError) as exc:
        client.create_issue("t", ADF)
    assert exc.value.issue_created is False


def test_connection_dropped_result_unknown():
    client, _ = client_with(raise_(httpx.RemoteProtocolError))
    with pytest.raises(JiraUnavailableError) as exc:
        client.create_issue("t", ADF)
    assert exc.value.issue_created is None


def test_no_automatic_retry():
    client, calls = client_with(raise_(httpx.ReadTimeout))
    with pytest.raises(JiraTimeoutError):
        client.create_issue("t", ADF)
    assert len(calls) == 1  # uma única tentativa: evita issues duplicadas


# --------------------------------------------------------------------------- respostas inválidas
@pytest.mark.parametrize("response", [
    httpx.Response(201, text="não é json"),
    httpx.Response(201, json=[]),
    httpx.Response(201, json={"id": "1"}),                      # sem key
    httpx.Response(201, json={"id": "1", "key": "OUTRO-1"}),    # projeto diferente
    httpx.Response(201, json={"id": 1, "key": "KAN-1"}),        # id com tipo errado
    httpx.Response(200, json={"id": "1", "key": "KAN-1"}),      # status diferente de 201
])
def test_unexpected_success_body(response):
    client, _ = client_with(lambda r: response)
    with pytest.raises(JiraUnexpectedResponseError) as exc:
        client.create_issue("t", ADF)
    assert exc.value.issue_created is None


def test_redirect_is_not_success():
    client, _ = client_with(lambda r: httpx.Response(302, headers={"Location": "https://x"}))
    with pytest.raises(JiraUnexpectedResponseError):
        client.create_issue("t", ADF)


# --------------------------------------------------------------------------- segurança
@pytest.mark.parametrize("handler", [
    lambda r: httpx.Response(401, text="Unauthorized"),
    lambda r: httpx.Response(400, json={"errorMessages": ["bad"]}),
    raise_(httpx.ReadTimeout),
    raise_(httpx.ConnectError),
])
def test_errors_never_expose_token(handler):
    client, _ = client_with(handler)
    with pytest.raises(Exception) as exc:
        client.create_issue("t", ADF)
    encoded = base64.b64encode(f"{FAKE_EMAIL}:{FAKE_TOKEN}".encode()).decode()
    for text in (str(exc.value), repr(exc.value)):
        assert FAKE_TOKEN not in text
        assert encoded not in text
    assert exc.value.__cause__ is None  # exceção original de rede descartada
