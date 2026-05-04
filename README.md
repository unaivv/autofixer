# Autofixer (AI Jira → Bitbucket)

Semi-autonomous pipeline: **Jira Cloud** (bugs elegibles) → clone **Bitbucket** → agente de código → **Docker** (npm lint/test/build) → branch + **PR** → comentario y transición en Jira.

La aplicación Python está en la **raíz** de este repo (`main.py`, `config.py`, `orchestrator/`, etc.). Las especificaciones están en los Markdown de la raíz.

## Requisitos

- **Python 3.9+** (recomendado 3.11+)
- **Docker**
- CLI del agente (p. ej. **Claude Code** / `claude`) en `PATH`, o ruta absoluta en `AGENT_COMMAND`
- Cuenta **Atlassian** + credenciales según [`.env.example`](.env.example)

## Uso rápido (clonar en otro PC)

```bash
git clone https://github.com/unaivv/autofixer.git
cd autofixer

python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -U pip
pip install -r requirements.txt

cp .env.example .env
# Edita .env: Jira, Bitbucket, BITBUCKET_GIT_ACCESS_TOKEN, AGENT_COMMAND, etc.

python3 main.py
```

Detalle de variables: **`.env.example`**.

## Documentación

| Archivo | Contenido |
|---------|-----------|
| [`Autonomous_Jira_Bug_Fixing_Platform_Spec.md`](Autonomous_Jira_Bug_Fixing_Platform_Spec.md) | Visión y flujo |
| [`FULL_BUILD_DOC_Autonomous_Jira_Fixer.md`](FULL_BUILD_DOC_Autonomous_Jira_Fixer.md) | Blueprint técnico |

## Estructura

```text
autofixer/
├── README.md
├── main.py
├── config.py
├── requirements.txt
├── .env.example
├── orchestrator/
├── integrations/
├── Autonomous_Jira_Bug_Fixing_Platform_Spec.md
└── FULL_BUILD_DOC_Autonomous_Jira_Fixer.md
```

## Seguridad

No subas **`.env`** ni tokens. Rota cualquier token que haya aparecido en logs o chats.
