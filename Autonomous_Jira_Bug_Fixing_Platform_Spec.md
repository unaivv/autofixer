# Autonomous Jira Bug Fixing Platform (Claude Code / Cursor + Jira + Bitbucket)

## 1. Objetivo del sistema

Construir una plataforma autónoma/semi-autónoma capaz de:

- Consultar diariamente Jira en busca de bugs/issues elegibles.
- Analizar automáticamente cada incidencia.
- Clonar el repositorio afectado.
- Invocar un agente de código (Claude Code preferiblemente, Cursor opcional) para implementar un fix conservador.
- Ejecutar lint, tests y build.
- Si todo pasa, crear branch, commit, push y Pull Request en Bitbucket.
- Comentar el issue de Jira con el resultado.
- Generar un informe diario de actividad.

El sistema debe operar con **human review obligatorio en PR**, pero con **mínima intervención manual durante el proceso**.

---

## 2. Filosofía de diseño

Este no es un script simple.

Es un **AI Engineering Orchestrator** compuesto por:

- Scheduler
- Jira Connector
- Repo Workspace Manager
- AI Coding Agent Runner
- Test Validation Runner
- Pull Request Publisher
- Jira Feedback Module
- Reporting/Logging Layer
- Confidence Guardrails

Principios:

1. Nunca tocar tickets no etiquetados como seguros.
2. Nunca mergear automáticamente.
3. Nunca hacer cambios grandes.
4. Abort inmediato si tests no estabilizan.
5. Todo cambio debe quedar trazado.

---

## 3. Stack tecnológico recomendado

## Core Runtime
- Python 3.12+

## Librerías Python
- requests
- atlassian-python-api
- gitpython
- subprocess
- docker SDK
- pydantic
- schedule o APScheduler
- loguru
- slack_sdk (opcional)

## Integraciones externas
- Jira Cloud / Jira Server API
- Bitbucket API
- Claude Code CLI (preferido)
- Cursor Agent wrapper (opcional)

## Infra local
- Docker para sandbox de ejecución
- Workspace temporal de repositorios

---

## 4. Arquitectura general

```text
cron_scheduler/
    triggers daily run

orchestrator/
    main workflow controller

integrations/
    jira_client.py
    bitbucket_client.py
    claude_runner.py

workspace/
    repo_manager.py
    branch_manager.py

analysis/
    issue_classifier.py
    context_builder.py
    confidence_engine.py

execution/
    patch_runner.py
    test_runner.py
    retry_runner.py

reporting/
    jira_commenter.py
    slack_reporter.py
    audit_logger.py
```

---

## 5. Flujo funcional completo

### STEP 1 — Lanzamiento diario

Hora recomendada: 07:00 AM servidor.

Cron:

```bash
0 7 * * * python main.py
```

El scheduler invoca:

```python
run_daily_ai_bugfix_cycle()
```

---

### STEP 2 — Consulta de issues en Jira

Usar JQL estricto:

```jql
project = APP
AND issuetype = Bug
AND status = "To Do"
AND labels = ai-fixable
AND priority in (Low, Medium)
ORDER BY created ASC
```

Campos a traer:

- key
- summary
- description
- comments
- labels
- priority
- attachments
- components

Guardar issue payload bruto en `/logs/issues/YYYY-MM-DD/`

---

### STEP 3 — Clasificador de elegibilidad

Antes de tocar código, pasar issue por `IssueClassifier`.

Debe puntuar:

| Regla | Score |
|-------|-------|
| Tiene stacktrace | +20 |
| Tiene pasos reproducibles | +15 |
| Un solo repo afectado | +20 |
| Sin DB migration | +20 |
| Sin auth/security | +20 |
| Menos de 5 archivos estimados | +15 |

Abort si score < 70.

---

### STEP 4 — Resolver repositorio correspondiente

Mapear Jira component → repo URL.

Ejemplo:

```python
REPO_MAP = {
    "payments-api": "git@bitbucket.org:company/payments-api.git",
    "frontend-web": "git@bitbucket.org:company/frontend-web.git"
}
```

Clonar en:

```text
/tmp/ai_agent_runs/{ISSUE_KEY}/repo
```

Siempre desde rama principal actualizada:

```bash
git checkout develop
git pull
```

---

### STEP 5 — Construcción de dossier técnico

Crear archivo `issue_context.md` con:

## Datos Jira
- título
- descripción
- comentarios
- stacktrace
- adjuntos parseados

## Datos repositorio
- tree resumido
- grep de keywords del issue
- últimos commits relacionados
- tests existentes cercanos

Comandos útiles:

```bash
grep -R "NullPointerException" .
git log --all -- path/to/suspect/file
find . -name "*test*"
```

---

### STEP 6 — Prompting al agente Claude Code

Claude debe ejecutarse por subprocess.

Comando conceptual:

```bash
claude-code run --dangerously-skip-permissions < prompt.txt
```

### Prompt maestro obligatorio

```text
You are a senior software engineer operating inside a production repository.

TASK:
Fix the Jira issue conservatively.

MANDATORY RULES:
- minimal possible changes
- do not refactor unrelated files
- preserve style conventions
- add or update tests when possible
- explain modified files
- output confidence score 0-100
- if not enough certainty, abort

AFTER CODING:
run lint, impacted tests, and build commands.
```

Adjuntar issue_context completo.

---

### STEP 7 — Capturar patch generado

El runner debe detectar:

```bash
git diff
git status
```

Guardar snapshot del patch en:

```text
/logs/patches/{ISSUE_KEY}.diff
```

Abort si:

- > 5 archivos modificados
- > 400 líneas cambiadas

---

### STEP 8 — Ejecutar validaciones

Orden:

```bash
npm install
npm run lint
npm run test
npm run build
```

o según stack:

```bash
pytest
mvn test
go test ./...
```

Todo dentro de Docker sandbox.

Guardar logs completos.

---

### STEP 9 — Retry único con feedback

Si falla:

- recopilar errores
- reenviar a Claude con:

```text
Tests failed with the following logs. Perform one conservative correction only.
```

Solo un retry permitido.

Si vuelve a fallar:

```text
mark issue as AI_FAILED
```

---

### STEP 10 — Confidence Engine

Claude debe devolver confidence.

Además calcular confidence interna:

- tests pass = +30
- lint pass = +20
- low file count = +20
- low line diff = +15
- issue reproducibility matched = +15

Abort si confidence final < 80.

---

### STEP 11 — Crear branch y commit

Nombre branch:

```bash
aifix/ABC-123-short-description
```

Commit:

```bash
git checkout -b aifix/ABC-123-short-description
git add .
git commit -m "[AI FIX] ABC-123 conservative automated bug fix"
git push origin aifix/ABC-123-short-description
```

---

### STEP 12 — Crear Pull Request Bitbucket

Título:

```text
[AI FIX] ABC-123 Resolve null pointer in payment validation
```

Body:

```text
Automated conservative fix generated by Claude Code.

Issue: ABC-123
Files changed: X
Lines changed: Y
Tests: PASS
Lint: PASS
Confidence: 87

Human review required before merge.
```

---

### STEP 13 — Comentar Jira automáticamente

Comentario:

```text
AI agent generated a candidate fix.

PR: <bitbucket_link>
Validation:
- lint passed
- tests passed
- build passed

Awaiting engineering review.
```

Si falla:

```text
AI attempted automated resolution but validation failed. No PR created.
```

---

### STEP 14 — Reporte diario

Enviar resumen Slack/email:

```text
AI BUGFIX DAILY REPORT

Processed issues: 8
Successful PRs: 3
Failed attempts: 5

PRs:
- ABC-123
- PAY-221
- WEB-88
```

---

## 6. Estructura de carpetas del proyecto

```text
ai-jira-fixer/
│
├── main.py
├── config.py
├── requirements.txt
│
├── orchestrator/
│   └── daily_cycle.py
│
├── integrations/
│   ├── jira_client.py
│   ├── bitbucket_client.py
│   └── claude_runner.py
│
├── workspace/
│   ├── repo_manager.py
│   └── branch_manager.py
│
├── analysis/
│   ├── issue_classifier.py
│   ├── context_builder.py
│   └── confidence_engine.py
│
├── execution/
│   ├── patch_runner.py
│   ├── test_runner.py
│   └── retry_runner.py
│
├── reporting/
│   ├── jira_commenter.py
│   ├── slack_reporter.py
│   └── audit_logger.py
│
└── logs/
```

---

## 7. Variables de entorno necesarias

```env
JIRA_BASE_URL=
JIRA_EMAIL=
JIRA_API_TOKEN=

BITBUCKET_BASE_URL=
BITBUCKET_USER=
BITBUCKET_APP_PASSWORD=

CLAUDE_CODE_PATH=
WORKSPACE_ROOT=/tmp/ai_agent_runs

SLACK_WEBHOOK=
```

---

## 8. Reglas de seguridad obligatorias

- No procesar más de N issues por día (recomendado 5)
- No tocar issues sin label `ai-fixable`
- No permitir merges automáticos
- No permitir más de 1 retry
- No permitir cambios masivos
- Loggear absolutamente todo
- Mantener snapshots de diffs y prompts

---

## 9. Roadmap de implementación sugerido

### FASE 1
- Jira client
- Bitbucket client
- Repo clone manager

### FASE 2
- Claude runner
- issue context builder
- patch capture

### FASE 3
- test sandbox
- retry engine
- confidence engine

### FASE 4
- PR publisher
- Jira commenter
- Slack reports

### FASE 5
- hardening y producción

---

## 10. Modo ejecución (decisión actual)

**Por defecto:** si lint/tests/build pasan, el sistema **hace push y abre PR** (integración real en máquina local primero).

`DRY_RUN` sigue existiendo como **opción** en configuración para pruebas sin push, pero **no** es el modo obligatorio inicial.

---

## 11. Siguiente paso recomendado

Implementación en el repo `ai-jira-fixer/` según el FULL BUILD DOC y la sección **12** de decisiones cerradas.

---

## 12. Decisiones de producto acordadas (cerradas)

Estas respuestas sustituyen ambigüedades anteriores en este documento y en el FULL BUILD DOC.

| Área | Decisión |
|------|----------|
| Jira | **Jira Cloud**. Instrucciones de conexión (token, URL, prueba `myself`) se documentan en `ai-jira-fixer/.env.example` y en el código de `jira_client`. |
| JQL / filtros | **Lo más sencillo**: proyecto + criterios mínimos vía `.env` (ver `config.py`). Label típica `ai-fixable`. |
| Transición Jira | Tras **PR creado con éxito**, transición a **In Review**. El nombre visible del status es configurable (`JIRA_TRANSITION_IN_REVIEW`); el id se resuelve vía API en integración. |
| Comentarios Jira | **Solo en éxito** con enlace al PR. Si no hay PR, **no** comentar por defecto: avisar al operador (consola + log de auditoría; Slack opcional). |
| Bitbucket | **Bitbucket Cloud**. Autenticación **API token de Atlassian** (sustituye app passwords en la línea de tiempo actual); mismo patrón que Jira donde aplique. |
| Ramas Git | Siempre **base `develop`** y **PR hacia `develop`**. |
| Repositorio | **Un solo repo** al inicio: URL o `workspace`+`slug` en `.env` (sin mapa Jira→repo hasta que haya varios). |
| Monorepo / contexto | **Sin** limitación especial de subcarpeta en v1. |
| Stack | **Node + React**: comandos desde `package.json` (`lint`, `test`, `build` si existen). |
| Docker | **Imagen única** Node (LTS), configurable (`DOCKER_NODE_IMAGE`). |
| Agente | **CLI invocable** desde Python (`AGENT_COMMAND`). Cursor como flujo **manual en IDE** es complementario; automatización v1 = subprocess. |
| Confianza | El agente debe emitir línea parseable `CONFIDENCE: 0-100` en su salida. |
| Límites de diff | **Solo los necesarios**, umbrales amplios y configurables (no el “>5 archivos” estricto del borrador inicial). |
| Puntuación | Un único bloque de **config** para umbral de clasificador y de aprobación post-validación (evitar duplicar reglas en docs sueltos). |
| Throughput | **Máximo 5 issues/día**, procesamiento **secuencial** (un repo al inicio). |
| Secretos | Solo **`.env` local** (sin GitHub; despliegue Bitbucket). |
| Lanzamiento | Prioridad: **`python main.py`** o script equivalente; **cron** opcional. |
| Logs / PII | Auditoría completa bajo `logs/` con **`.gitignore`** de `logs/` y `.env`; retención y redacción avanzada quedan para hardening. |
| Idioma | Comentarios Jira y textos de PR **siempre en inglés**. |
| Entorno | Primera ejecución **en tu máquina** con APIs reales. |
