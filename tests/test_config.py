import pytest

from app.config import JiraConfigError, load_jira_settings

VALID_ENV = {
    "JIRA_BASE_URL": "https://exemplo-teste.atlassian.net/",
    "JIRA_EMAIL": "bot@example.com",
    "JIRA_API_TOKEN": "TOKEN-FICTICIO-NAO-REAL-123456",
}


def test_valid_env_uses_kan_by_default():
    s = load_jira_settings(VALID_ENV)
    assert s.project_key == "KAN"
    assert s.base_url == "https://exemplo-teste.atlassian.net"  # barra final removida
    assert s.priority_map == {}
    assert s.timeout_seconds == 10


def test_project_key_can_be_overridden():
    assert load_jira_settings({**VALID_ENV, "JIRA_PROJECT_KEY": "OPS"}).project_key == "OPS"


@pytest.mark.parametrize("missing", ["JIRA_BASE_URL", "JIRA_EMAIL", "JIRA_API_TOKEN"])
def test_missing_required_variable(missing):
    env = {k: v for k, v in VALID_ENV.items() if k != missing}
    with pytest.raises(JiraConfigError) as exc:
        load_jira_settings(env)
    assert missing in str(exc.value)


def test_all_missing_lists_all_names():
    with pytest.raises(JiraConfigError) as exc:
        load_jira_settings({})
    for name in VALID_ENV:
        assert name in str(exc.value)


@pytest.mark.parametrize("url", [
    "http://exemplo.atlassian.net",                 # sem HTTPS
    "exemplo.atlassian.net",                        # sem esquema
    "https://user:senha@exemplo.atlassian.net",     # credencial embutida
    "https://exemplo.atlassian.net/jira/software",  # caminho extra
])
def test_invalid_base_url(url):
    with pytest.raises(JiraConfigError):
        load_jira_settings({**VALID_ENV, "JIRA_BASE_URL": url})


@pytest.mark.parametrize("key,value", [
    ("JIRA_EMAIL", "sem-arroba"),
    ("JIRA_PROJECT_KEY", "kan minúsculo"),
    ("JIRA_TIMEOUT_SECONDS", "abc"),
    ("JIRA_TIMEOUT_SECONDS", "0"),
    ("JIRA_PRIORITY_MAP", "P1=Highest,P2=High"),       # incompleto
    ("JIRA_PRIORITY_MAP", "P5=Lowest,P1=a,P2=b,P3=c"),  # severidade inexistente
    ("JIRA_PRIORITY_MAP", "Highest"),                   # sem '='
])
def test_invalid_values(key, value):
    with pytest.raises(JiraConfigError):
        load_jira_settings({**VALID_ENV, key: value})


def test_priority_map_parsed():
    env = {**VALID_ENV, "JIRA_PRIORITY_MAP": "P1=Highest, P2=High, P3=Medium, P4=Low"}
    assert load_jira_settings(env).priority_map == {
        "P1": "Highest", "P2": "High", "P3": "Medium", "P4": "Low"}


def test_token_never_in_repr_or_errors():
    s = load_jira_settings(VALID_ENV)
    assert VALID_ENV["JIRA_API_TOKEN"] not in repr(s)
    with pytest.raises(JiraConfigError) as exc:
        load_jira_settings({**VALID_ENV, "JIRA_BASE_URL": "http://x"})
    assert VALID_ENV["JIRA_API_TOKEN"] not in str(exc.value)
