"""Verifica a configuração do Jira SEM criar nada (apenas requisições GET).

Uso:  python -m scripts.jira_check

Mostra:
  1. se a autenticação funciona (nome de exibição da conta);
  2. os tipos de issue disponíveis no projeto (para JIRA_ISSUE_TYPE);
  3. os campos obrigatórios do tipo escolhido;
  4. se o campo Prioridade pode ser preenchido na criação e quais valores são aceitos
     (para JIRA_PRIORITY_MAP).
O token nunca é exibido.
"""
import sys
from pathlib import Path

from dotenv import load_dotenv

from app.config import JiraConfigError, load_jira_settings
from app.jira_client import JiraClient, JiraError

# Campos que a aplicação já preenche ao criar a issue.
FIELDS_WE_SEND = {"project", "issuetype", "summary", "description", "priority"}


def main() -> int:
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    try:
        settings = load_jira_settings()
    except JiraConfigError as exc:
        print(f"[ERRO de configuração] {exc}")
        return 1

    client = JiraClient(settings)
    key = settings.project_key
    print(f"Site: {settings.base_url} | Projeto: {key} | Tipo configurado: {settings.issue_type}\n")

    try:
        me = client.get_json("/rest/api/3/myself")
        print(f"[OK] Autenticado como: {me.get('displayName', '(sem nome)')}")

        data = client.get_json(f"/rest/api/3/issue/createmeta/{key}/issuetypes")
        types = data.get("issueTypes") or data.get("values") or []
        print(f"\nTipos de issue disponíveis em {key}:")
        for t in types:
            sub = " (subtarefa - não usar)" if t.get("subtask") else ""
            print(f"  - nome: {t.get('name')!r:<20} id: {t.get('id')}{sub}")

        wanted = settings.issue_type.lower()
        chosen = next((t for t in types if str(t.get("id")) == settings.issue_type
                       or str(t.get("name", "")).lower() == wanted), None)
        if not chosen:
            print(f"\n[ATENÇÃO] JIRA_ISSUE_TYPE={settings.issue_type!r} não existe neste projeto. "
                  "Use um dos nomes ou ids acima.")
            return 1
        print(f"\n[OK] Tipo de issue {chosen['name']!r} (id {chosen['id']}) encontrado.")

        meta = client.get_json(f"/rest/api/3/issue/createmeta/{key}/issuetypes/{chosen['id']}",
                               params={"maxResults": 200})
        fields = {f.get("fieldId"): f for f in (meta.get("fields") or meta.get("values") or [])}

        extra_required = [f.get("name") for fid, f in fields.items()
                          if f.get("required") and not f.get("hasDefaultValue")
                          and fid not in FIELDS_WE_SEND]
        if extra_required:
            print(f"[ATENÇÃO] Campos obrigatórios que a aplicação NÃO preenche: {extra_required}")
        else:
            print("[OK] Nenhum campo obrigatório adicional.")

        prio = fields.get("priority")
        if not prio:
            print("\nCampo Prioridade NÃO está disponível na criação deste tipo de issue.")
            print("  -> Deixe JIRA_PRIORITY_MAP vazio. A severidade continuará no título e na descrição.")
        else:
            names = [v.get("name") for v in prio.get("allowedValues") or []]
            print(f"\nPrioridades aceitas: {names}")
            if settings.priority_map:
                invalid = [v for v in settings.priority_map.values() if v not in names and not v.isdigit()]
                if invalid:
                    print(f"[ATENÇÃO] JIRA_PRIORITY_MAP usa valores inexistentes: {invalid}")
                else:
                    print(f"[OK] JIRA_PRIORITY_MAP válido: {dict(settings.priority_map)}")
            elif len(names) >= 4:
                print("  Sugestão (confira a ordem na interface do Jira antes de usar):")
                print("  JIRA_PRIORITY_MAP=" + ",".join(f"P{i + 1}={n}" for i, n in enumerate(names[:4])))
    except JiraError as exc:
        print(f"[ERRO {exc.code}] {exc.message}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
