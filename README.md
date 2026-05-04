# Autofixer (AI Jira → Bitbucket)

Semi-autonomous pipeline: **Jira Cloud** (bugs elegibles) → clone **Bitbucket** → agente de código → **Docker** (npm lint/test/build) → branch + **PR** → comentario y transición en Jira.

El código ejecutable vive en **`ai-jira-fixer/`**. En la raíz están las especificaciones en Markdown.

## Requisitos

- **Python 3.9+** (recomendado 3.11+ en máquinas nuevas)
- **Docker** (validación Node en contenedor)
- CLI del agente (p. ej. **Claude Code** / `claude`) en `PATH`, o ruta absoluta en `AGENT_COMMAND`
- Cuenta **Atlassian** (Jira + Bitbucket Cloud) y credenciales según [`.env.example`](ai-jira-fixer/.env.example)

## Uso rápido (otro PC / trabajo)

```bash
git clone https://github.com/TU_USUARIO/TU_REPO.git
cd TU_REPO/ai-jira-fixer

python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -U pip
pip install -r requirements.txt

cp .env.example .env
# Edita .env: Jira, Bitbucket, BITBUCKET_GIT_ACCESS_TOKEN (recomendado para Git), AGENT_COMMAND, etc.

python3 main.py
```

Más detalle de variables: **`ai-jira-fixer/.env.example`**.

## Documentación

| Archivo | Contenido |
|---------|-----------|
| [`Autonomous_Jira_Bug_Fixing_Platform_Spec.md`](Autonomous_Jira_Bug_Fixing_Platform_Spec.md) | Visión y flujo |
| [`FULL_BUILD_DOC_Autonomous_Jira_Fixer.md`](FULL_BUILD_DOC_Autonomous_Jira_Fixer.md) | Blueprint técnico y orden de módulos |

## Estructura

```text
autofixer/
├── README.md
├── ai-jira-fixer/          # aplicación Python
│   ├── main.py
│   ├── config.py
│   ├── requirements.txt
│   ├── .env.example
│   └── ...
└── *.md                    # specs
```

## Subir a GitHub (desde tu máquina)

1. Crea un repo vacío en GitHub (sin README si ya tienes uno aquí).
2. En la carpeta `autofixer`:

   ```bash
   git remote add origin https://github.com/TU_USUARIO/TU_REPO.git
   git branch -M main
   git push -u origin main
   ```

3. En el PC del trabajo: `git clone` y sigue la sección **Uso rápido**. Copia solo **`.env`** (o créalo de nuevo; no lo subas al repo).

## Seguridad

- **No** subas `.env` ni tokens.
- Si alguna vez filtraste un token en un log, **revócalo** en Atlassian/Bitbucket y genera otro.
