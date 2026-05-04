# FULL BUILD DOC — Autonomous Jira Bug Fixing Platform
## Production Engineering Implementation Blueprint

---

# 1. SYSTEM PURPOSE

Build a production-grade autonomous engineering agent that:

1. polls Jira daily,
2. selects AI-safe bug tickets,
3. clones the affected Bitbucket repository,
4. constructs technical context,
5. invokes Claude Code as autonomous coding worker,
6. validates generated fix,
7. creates branch + push + PR,
8. comments Jira,
9. emits complete audit report.

System mode: **semi-autonomous with human PR approval**.

---

# 2. GLOBAL EXECUTION STATE MACHINE

```text
IDLE
 ↓
FETCH_JIRA_ISSUES
 ↓
CLASSIFY_ISSUE
 ↓
PREPARE_WORKSPACE
 ↓
BUILD_CONTEXT
 ↓
RUN_CLAUDE_FIX
 ↓
VALIDATE_PATCH
 ↓
RETRY_FIX (optional one time)
 ↓
CONFIDENCE_CHECK
 ↓
CREATE_BRANCH_AND_PR
 ↓
COMMENT_JIRA
 ↓
REPORT_RESULTS
 ↓
END
```

Each state must persist logs and return structured result objects.

---

# 3. PROJECT TREE (FINAL)

```text
ai-jira-fixer/
│
├── main.py
├── config.py
├── requirements.txt
├── .env
│
├── orchestrator/
│   ├── daily_cycle.py
│   ├── issue_pipeline.py
│   └── state_machine.py
│
├── integrations/
│   ├── jira_client.py
│   ├── bitbucket_client.py
│   ├── claude_runner.py
│   └── slack_client.py
│
├── analysis/
│   ├── issue_classifier.py
│   ├── context_builder.py
│   ├── repo_scanner.py
│   └── confidence_engine.py
│
├── workspace/
│   ├── repo_manager.py
│   ├── git_manager.py
│   └── filesystem_manager.py
│
├── execution/
│   ├── patch_validator.py
│   ├── test_runner.py
│   ├── docker_runner.py
│   └── retry_engine.py
│
├── reporting/
│   ├── jira_commenter.py
│   ├── audit_logger.py
│   └── daily_reporter.py
│
├── prompts/
│   ├── master_fix_prompt.md
│   └── retry_fix_prompt.md
│
└── logs/
```

---

# 4. CORE DATA CONTRACTS (MANDATORY PYDANTIC MODELS)

## models/issue_models.py

```python
class JiraIssue(BaseModel):
    key: str
    summary: str
    description: str
    comments: list[str]
    labels: list[str]
    priority: str
    components: list[str]
    attachments: list[str]

class ClassificationResult(BaseModel):
    eligible: bool
    score: int
    reasons: list[str]

class WorkspaceContext(BaseModel):
    repo_url: str
    local_path: str
    default_branch: str

class ClaudeExecutionResult(BaseModel):
    success: bool
    stdout: str
    stderr: str
    confidence: int
    files_changed: int
    lines_changed: int

class ValidationResult(BaseModel):
    lint_passed: bool
    tests_passed: bool
    build_passed: bool
    logs: str

class PullRequestResult(BaseModel):
    pr_url: str
    branch_name: str
    commit_hash: str
```

---

# 5. main.py ENTRYPOINT

```python
from orchestrator.daily_cycle import run_daily_cycle

if __name__ == "__main__":
    run_daily_cycle()
```

---

# 6. ORCHESTRATOR — daily_cycle.py

### RESPONSIBILITY
Top level daily execution controller.

### PSEUDOCODE

```python
def run_daily_cycle():
    logger.start_session()

    issues = jira_client.fetch_candidate_issues()

    for issue in issues[:MAX_DAILY_ISSUES]:
        try:
            process_single_issue(issue)
        except Exception as e:
            logger.log_fatal(issue.key, str(e))

    daily_reporter.send_summary()
```

---

# 7. ORCHESTRATOR — issue_pipeline.py

```python
def process_single_issue(issue: JiraIssue):

    classification = issue_classifier.classify(issue)
    if not classification.eligible:
        audit_logger.log_skip(issue, classification)
        return

    workspace = repo_manager.prepare_workspace(issue)

    context_file = context_builder.build(issue, workspace)

    claude_result = claude_runner.run_fix(context_file, workspace)

    validation = patch_validator.validate(workspace)

    if not validation.tests_passed:
        claude_result, validation = retry_engine.retry(issue, workspace, validation)

    if not confidence_engine.approve(claude_result, validation):
        jira_commenter.comment_failed(issue)
        return

    pr_result = bitbucket_client.publish_pr(issue, workspace, claude_result, validation)

    jira_commenter.comment_success(issue, pr_result)
```

---

# 8. integrations/jira_client.py

### FUNCTIONS TO IMPLEMENT

```python
def fetch_candidate_issues() -> list[JiraIssue]
def add_comment(issue_key: str, body: str) -> None
def transition_issue(issue_key: str, status: str) -> None
```

### JQL

```jql
project = APP
AND issuetype = Bug
AND status = "To Do"
AND labels = ai-fixable
AND priority in (Low, Medium)
ORDER BY created ASC
```

### RAW REST ENDPOINTS

GET:
`/rest/api/3/search`

POST comment:
`/rest/api/3/issue/{issueKey}/comment`

Use token auth.

---

# 9. integrations/bitbucket_client.py

### FUNCTIONS

```python
def create_branch(local_repo, branch_name)
def push_branch(local_repo, branch_name)
def create_pull_request(issue, branch_name, claude_result, validation) -> PullRequestResult
def publish_pr(issue, workspace, claude_result, validation) -> PullRequestResult
```

### REQUIRED PR BODY TEMPLATE

```text
Automated conservative fix generated by Claude Code.

Issue: {issue.key}
Files changed: {files_changed}
Lines changed: {lines_changed}
Tests: PASS
Lint: PASS
Build: PASS
Confidence: {confidence}

Human review required before merge.
```

---

# 10. workspace/repo_manager.py

### RESPONSIBILITY
Clone and prepare repo.

### FUNCTIONS

```python
def resolve_repo(issue) -> str
def clone_repo(repo_url, issue_key) -> str
def checkout_default_branch(path)
def prepare_workspace(issue) -> WorkspaceContext
```

### IMPLEMENTATION RULES

Workspace path:

```text
/tmp/ai_agent_runs/{ISSUE_KEY}/repo
```

Always hard reset:

```bash
git reset --hard
git clean -fd
```

---

# 11. analysis/issue_classifier.py

### RULE ENGINE

```python
score = 0

if stacktrace_present: score += 20
if reproducible_steps_present: score += 15
if one_repo_match: score += 20
if no_db_migration_keywords: score += 20
if no_security_keywords: score += 20
if estimated_scope_small: score += 15
```

eligible if score >= 70

### KEYWORD BLACKLIST

Abort if description contains:

- migration
- auth
- login security
- permissions
- billing critical
- production outage

---

# 12. analysis/context_builder.py

Must generate `/tmp/.../issue_context.md`

Contains:

1. Jira full content
2. grep results
3. related files
4. recent git commits
5. existing tests
6. repository tree summary

### FUNCTIONS

```python
def scan_repo_tree(path)
def grep_keywords(path, issue)
def collect_recent_commits(path)
def locate_tests(path)
def build(issue, workspace) -> str
```

---

# 13. integrations/claude_runner.py

### MOST CRITICAL MODULE

Must invoke subprocess:

```bash
claude-code run --dangerously-skip-permissions < prompt_file
```

### FUNCTION

```python
def run_fix(context_file: str, workspace: WorkspaceContext) -> ClaudeExecutionResult
```

### STEPS

1. Load `prompts/master_fix_prompt.md`
2. Append issue_context.md
3. Save temp prompt
4. Execute Claude in repo working dir
5. Capture stdout/stderr
6. Parse confidence from output
7. Count git diff stats

---

# 14. prompts/master_fix_prompt.md

```text
You are a senior production software engineer.

TASK:
Implement a conservative minimal fix for the attached Jira issue.

STRICT RULES:
- do not refactor unrelated code
- do not modify more than necessary
- preserve conventions
- add/update tests when possible
- after coding output:

CONFIDENCE: <0-100>

and explain files modified.
```

---

# 15. execution/patch_validator.py

### FUNCTION

```python
def validate(workspace) -> ValidationResult
```

### MUST CHECK

```bash
git diff --stat
```

Abort if:

- files changed > 5
- lines changed > 400

Then execute:

```bash
npm install || pip install -r requirements.txt || mvn test dependency preload
npm run lint
npm run test
npm run build
```

Language detection based on repo files.

---

# 16. execution/docker_runner.py

Every validation command must run isolated.

### FUNCTION

```python
def run_in_docker(path, command) -> tuple[bool, str]
```

Mount repo into ephemeral container.

Reason: avoid host pollution.

---

# 17. execution/retry_engine.py

One retry only.

```python
def retry(issue, workspace, validation_logs):
```

Retry prompt:

```text
Previous generated patch failed validation.
Apply one conservative correction only.
Validation logs:
{logs}
```

Run Claude again.
Run validation again.
Return final.

---

# 18. analysis/confidence_engine.py

```python
def approve(claude_result, validation):
```

score = 0

- tests pass +30
- lint pass +20
- build pass +20
- files changed <=3 +10
- lines changed <=150 +10
- claude confidence >=80 +10

approve if total >= 80

---

# 19. reporting/jira_commenter.py

### SUCCESS COMMENT

```text
AI agent generated candidate automated fix.

PR: {pr_url}

Validation:
- lint passed
- tests passed
- build passed

Awaiting engineering review.
```

### FAILURE COMMENT

```text
AI attempted automated resolution but validation failed. No PR created.
```

---

# 20. reporting/audit_logger.py

Persist ALL:

- jira payload
- context file
- claude prompts
- claude outputs
- git diffs
- test logs
- PR links

Folder per issue:

```text
/logs/YYYY-MM-DD/{ISSUE_KEY}/
```

---

# 21. reporting/daily_reporter.py

Compile:

- processed issues
- skipped
- failed
- PR created

Send Slack webhook.

---

# 22. .env VARIABLES (aligned with locked decisions)

Use **Atlassian API tokens** for Bitbucket Cloud and Jira Cloud where the same account is sufficient.

```env
# Shared Atlassian account (Jira + Bitbucket Cloud REST + git HTTPS)
ATLASSIAN_EMAIL=
ATLASSIAN_API_TOKEN=

JIRA_BASE_URL=https://YOURDOMAIN.atlassian.net
# Simple JQL building blocks (optional full override)
JIRA_PROJECT=APP
JIRA_ISSUE_TYPE=Bug
JIRA_STATUS=To Do
JIRA_LABEL_AI_FIXABLE=ai-fixable
# JIRA_JQL=   # if set, overrides the built-in simple JQL

BITBUCKET_WORKSPACE=
BITBUCKET_REPO_SLUG=
# Optional explicit clone URL (otherwise built from workspace/slug + token)
# BITBUCKET_GIT_CLONE_URL=

WORKSPACE_ROOT=/tmp/ai_agent_runs
MAX_DAILY_ISSUES=5
DEFAULT_BRANCH=develop
PR_TARGET_BRANCH=develop
JIRA_TRANSITION_IN_REVIEW=In Review

# Subprocess agent (example — adjust to your installed CLI)
AGENT_COMMAND=claude-code run --dangerously-skip-permissions

DOCKER_NODE_IMAGE=node:20-bookworm

# Optional: set true to run validation but skip git push / PR / Jira transition
DRY_RUN=false

# Optional notification on failure / summary
SLACK_WEBHOOK=

# Generous guardrails (tune in config.py / env)
MAX_FILES_CHANGED=50
MAX_LINES_CHANGED=5000
CLASSIFIER_MIN_SCORE=70
CONFIDENCE_MIN_APPROVE=80
```

### Locked product decisions (May 2026)

Synced with `Autonomous_Jira_Bug_Fixing_Platform_Spec.md` section 12.

- **Jira Cloud**; simplest configurable JQL; **transition to In Review** after successful PR; **Jira comment only on success** with PR link; on failure **operator notification** (stdout + audit logs; optional Slack) instead of noisy Jira comments.
- **Bitbucket Cloud** + **Atlassian API tokens** (app passwords deprecated).
- **Git**: always branch from **`develop`**, PR **into `develop`**.
- **Single repo** v1: `BITBUCKET_WORKSPACE` + `BITBUCKET_REPO_SLUG` (or explicit `BITBUCKET_GIT_CLONE_URL`).
- **Node/React** validation via `package.json` scripts inside **one Docker Node image**.
- **Agent**: configurable `AGENT_COMMAND` subprocess; **English** for Jira/PR bodies.
- **Throughput**: max **5** issues/day, **sequential**.
- **No long dry-run mandate**: when validation passes, **push + open PR** (unless `DRY_RUN=true`).
- **Triggers**: manual `python main.py` first; cron optional.
- **Secrets**: `.env` only, local machine first.

---

# 23. IMPLEMENTATION ORDER FOR CLAUDE/CURSOR

Tell coding AI to build in this exact order:

1. config.py
2. pydantic models
3. jira_client
4. repo_manager
5. issue_classifier
6. context_builder
7. claude_runner
8. patch_validator
9. retry_engine
10. bitbucket_client
11. jira_commenter
12. daily_reporter
13. orchestrator wiring
14. production hardening

---

# 24. CRITICAL PRODUCTION RULES

- `DRY_RUN` **optional** (default off for real push/PR when validation passes)
- No automatic merge
- Max 5 issues/day
- One retry only
- Full audit mandatory under `logs/`
- Fail closed, never fail open

---

# 25. NEXT BEST DELIVERABLE

Code in `ai-jira-fixer/` (this repo): orchestrator + integrations + prompts, runnable locally with `.env`.
