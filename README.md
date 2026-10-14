# CloudOps Alert Bridge

Recebe alertas de infraestrutura (simulados), classifica a severidade de P1 a P4 e abre uma issue no Jira Cloud pela REST API v3. É um fluxo de incidentes em pequena escala: detecção → triagem → registro do chamado.

Os alertas são simulados: não há monitoramento real nem SLAs.

## Como funciona

```
Interface web / simulador ─POST /alerts─▶ FastAPI ─▶ validação (Pydantic) ─▶ classificador P1–P4
                                                                                   │
                       issue no projeto KAN ◀─HTTPS─ cliente Jira ◀─ título + descrição (ADF)
```

| Módulo | Função |
|---|---|
| `app/schemas.py` | Contrato da API e validação dos alertas |
| `app/classifier.py` | Regras de severidade (não sabe que o Jira existe) |
| `app/incident.py` | Monta título e descrição da issue em ADF |
| `app/config.py` | Lê e valida as variáveis `JIRA_*` |
| `app/jira_client.py` | Única parte que conversa com o Jira |
| `app/main.py` | Rotas e tradução de erros em respostas HTTP |
| `static/index.html` | Interface web (HTML/CSS/JS puro) |
| `simulator/simulate.py` | Envia alertas de exemplo pela linha de comando |
| `scripts/jira_check.py` | Diagnóstico da configuração do Jira (só leitura) |

## Rodando

Requisitos: Python 3.10+ e, para criar issues de verdade, um site Jira Cloud com um [API token](https://id.atlassian.com/manage-profile/security/api-tokens).

No Windows, basta dar dois cliques em `iniciar.bat`: ele cria a `.venv` na primeira vez, sobe a API e abre http://127.0.0.1:8000/.

Manualmente:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env   # preencha com os dados do seu Jira
uvicorn app.main:app --reload
```

- Interface: http://127.0.0.1:8000/ (tem um botão que gera um chamado aleatório a cada clique)
- Swagger: http://127.0.0.1:8000/docs

Sem o `.env` a interface abre normalmente, mas o envio responde `500` (Jira não configurado).

### Configuração (`.env`)

| Variável | Obrigatória | Descrição |
|---|---|---|
| `JIRA_BASE_URL` | sim | `https://sua-empresa.atlassian.net` |
| `JIRA_EMAIL` | sim | E-mail da conta dona do token |
| `JIRA_API_TOKEN` | sim | API token |
| `JIRA_PROJECT_KEY` | não | Padrão `KAN` |
| `JIRA_ISSUE_TYPE` | não | Nome ou id do tipo de issue (padrão `Task`; em sites em português costuma ser `Tarefa`) |
| `JIRA_PRIORITY_MAP` | não | Ex.: `P1=Highest,P2=High,P3=Medium,P4=Low`. Vazio = não envia prioridade |
| `JIRA_TIMEOUT_SECONDS` | não | Padrão `10` |

Para descobrir o tipo de issue e as prioridades aceitas pelo seu projeto, sem criar nada:

```powershell
python -m scripts.jira_check
```

## Testes

```powershell
python -m pytest
```

Os testes não acessam a rede: o `conftest.py` remove as variáveis `JIRA_*` e troca o cliente por um Jira simulado (`httpx.MockTransport`). Eles cobrem classificação, validação, montagem da issue, erros 400/401/403/404/429/5xx, timeouts e garantem que o token não aparece em respostas nem em logs.

O mock prova que as requisições são montadas e interpretadas corretamente, não que a integração real funciona. Ela foi validada criando issues no projeto KAN.

## Regras de classificação

1. Severidade base (valor `>=` limite):

| Tipo | P1 | P2 | P3 | P4 |
|---|---|---|---|---|
| `cpu_high`, `memory_high` (%) | ≥ 95 | ≥ 85 | ≥ 70 | abaixo |
| `disk_high` (%) | ≥ 95 | ≥ 90 | ≥ 80 | abaixo |
| `latency_high` (ms) | ≥ 5000 | ≥ 2000 | ≥ 1000 | abaixo |
| `service_down` | P1 | | | |

2. Ajuste por ambiente, para todos os tipos: `production` mantém, `staging` desce 1 nível, `development` desce 2 (mínimo P4). Ex.: `service_down` em staging vira P2.

## Respostas da API

| Código | Quando |
|---|---|
| `201` | Issue criada; a resposta traz `jira_issue.key` e `url` |
| `422` | Alerta inválido (o Jira não é chamado) |
| `500` | Configuração do Jira ausente ou inválida |
| `502` | O Jira recusou ou falhou (401, 403, 404, 400, 429, 5xx, resposta inválida) |
| `504` | Timeout falando com o Jira |

Nos erros, `error.jira_result` diz se a issue com certeza não foi criada (`not_created`) ou se não dá para saber (`unknown`, por exemplo um timeout depois do envio). Nesse caso é melhor conferir no Jira antes de reenviar.

## Decisões

- **Basic auth (e-mail + API token) sobre HTTPS**, como a Atlassian documenta para scripts. Para um app distribuído o caminho seria OAuth 2.0.
- **Sucesso só com prova:** só responde 201 se o Jira devolver 201 com `id` e `key` válidos do projeto.
- **Sem retry automático:** sem idempotência, repetir pode duplicar incidentes.
- **Token só em variável de ambiente**, fora dos logs e do `repr` da configuração. O campo livre `message` também não vai para os logs.
- **Configuração lida depois da validação:** alerta inválido recebe 422 mesmo sem `.env`.

## Limitações e próximos passos

Hoje não há banco de dados, então não há histórico nem deduplicação: o mesmo alerta enviado duas vezes vira duas issues. A chamada ao Jira é síncrona.

Próximos passos: idempotência (guardar o `alert_id` na issue e consultar via JQL antes de criar), fila com reprocessamento seguro, comentar na issue existente quando o alerta se repetir e um runbook no Confluence ligado à issue.
