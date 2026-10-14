import pytest

from app.classifier import classify
from app.schemas import AlertIn


def make(alert_type, value=None, env="production"):
    return AlertIn(source="t", host="h", alert_type=alert_type, value=value, environment=env)


@pytest.mark.parametrize("alert_type,value,env,expected", [
    ("cpu_high", 97, "production", "P1"),
    ("cpu_high", 95, "production", "P1"),   # limite exato
    ("cpu_high", 90, "production", "P2"),
    ("cpu_high", 75, "production", "P3"),
    ("cpu_high", 50, "production", "P4"),
    ("memory_high", 96, "production", "P1"),
    ("disk_high", 92, "production", "P2"),
    ("latency_high", 6000, "production", "P1"),
    ("latency_high", 2300, "production", "P2"),
    ("latency_high", 1200, "production", "P3"),
    ("latency_high", 300, "production", "P4"),
    ("service_down", None, "production", "P1"),
    # Ajuste por ambiente
    ("service_down", None, "staging", "P2"),
    ("service_down", None, "development", "P3"),
    ("cpu_high", 50, "development", "P4"),   # nunca abaixo de P4
])
def test_classification_rules(alert_type, value, env, expected):
    severity, reason = classify(make(alert_type, value, env))
    assert severity.value == expected
    assert reason
