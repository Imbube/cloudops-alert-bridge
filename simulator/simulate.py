"""Simulador: envia alertas fictícios para a API local.

Uso:  python -m simulator.simulate [--url http://127.0.0.1:8000] [--delay 0.5]
"""
import argparse
import time

import httpx

SAMPLE_ALERTS = [
    {"source": "simulator", "host": "web-01", "alert_type": "cpu_high",
     "environment": "production", "value": 97.5, "message": "CPU acima de 95%"},
    {"source": "simulator", "host": "api-02", "alert_type": "service_down",
     "environment": "production", "message": "Serviço de pagamentos indisponível"},
    {"source": "simulator", "host": "api-03", "alert_type": "latency_high",
     "environment": "production", "value": 2300, "message": "Latência elevada"},
    {"source": "simulator", "host": "db-01", "alert_type": "disk_high",
     "environment": "staging", "value": 82, "message": "Disco quase cheio"},
    {"source": "simulator", "host": "dev-01", "alert_type": "memory_high",
     "environment": "development", "value": 90, "message": "Memória alta em dev"},
    # Alerta inválido de propósito, para demonstrar a validação (espera 422).
    {"source": "simulator", "host": "web-09", "alert_type": "cpu_high",
     "environment": "production", "message": "sem valor"},
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Simulador de alertas")
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--delay", type=float, default=0.5, help="segundos entre envios")
    parser.add_argument("--limit", type=int, default=None,
                        help="envia só os N primeiros alertas (cada alerta válido cria 1 issue no Jira)")
    args = parser.parse_args()

    alerts = SAMPLE_ALERTS[: args.limit] if args.limit else SAMPLE_ALERTS
    # Timeout maior que o do Jira (10 s por padrão), pois a API espera a resposta do Jira.
    with httpx.Client(base_url=args.url, timeout=30) as client:
        for alert in alerts:
            try:
                resp = client.post("/alerts", json=alert)
            except httpx.ConnectError:
                print(f"Não foi possível conectar em {args.url}. A API está rodando?")
                return
            body = resp.json()
            prefix = f"[{resp.status_code}] {alert['host']:8} {alert['alert_type']:13}"
            if resp.status_code == 201:
                issue = body["jira_issue"]
                print(f"{prefix} -> {body['severity']}  issue {issue['key']}  {issue['url']}")
            elif resp.status_code == 422:
                print(f"{prefix} -> rejeitado (alerta inválido)")
            else:
                err = body.get("error", {})
                print(f"{prefix} -> {body.get('severity')}  FALHA {err.get('code')} "
                      f"(issue: {err.get('jira_result')}): {err.get('message')}")
            time.sleep(args.delay)


if __name__ == "__main__":
    main()
