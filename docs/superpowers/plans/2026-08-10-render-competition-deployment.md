# Render Competition Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish ChangeSafe as a truthful competition-ready pilot at a stable Render HTTPS URL.

**Architecture:** Keep the existing Dockerized, single-origin FastAPI and React application intact. A Render Blueprint deploys one free web service in recorded DataHub mode with all mutation and warehouse switches disabled; after the hosted workflow passes, the exact service URL is added to the public documentation.

**Tech Stack:** Render Blueprint YAML, Docker, FastAPI, React, SQLite, pytest, PyYAML, Playwright, PowerShell.

## Global Constraints

- Describe ChangeSafe as a **competition-ready pilot**, not a production service.
- The initial hosted service must use `CHANGESAFE_MODE=replay` and the repository's checksum-pinned 55-field recording.
- Do not add DataHub, GitHub, Snowflake, Render, or owner credentials to Git, browser configuration, build arguments, logs, or artifacts.
- Keep `PUBLIC_PR_ENABLED=false`, `PUBLIC_WRITEBACK_ENABLED=false`, `CHANGESAFE_LIVE_EVIDENCE_REQUIRED=false`, `CHANGESAFE_WAREHOUSE_VALIDATION_ENABLED=false`, and `CHANGESAFE_WAREHOUSE_VALIDATION_REQUIRED=false`.
- The free tier is intentionally ephemeral; do not claim durable hosted run history until a paid disk is mounted at `/data`.
- Do not publish a hosted URL until root, health, schema discovery, all three operations, preview approval, patch download, and provenance copy pass.
- Preserve the current Apache-2.0 license, public repository, deterministic artifacts, and single-origin API/SSE design.

---

### Task 1: Add a fail-closed Render Blueprint

**Files:**
- Create: `apps/api/tests/test_render_deployment.py`
- Create: `render.yaml`

**Interfaces:**
- Consumes: the root `Dockerfile`, `/healthz`, and existing environment names from `changesafe.config.Settings`.
- Produces: one Render web service named `changesafe-competition` with a safe, credential-free replay configuration.

- [ ] **Step 1: Write the failing Blueprint contract test**

```python
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[3]
BLUEPRINT = ROOT / "render.yaml"

EXPECTED_ENV = {
    "CHANGESAFE_DATA_PATH": "/data/changesafe.db",
    "CHANGESAFE_LIVE_EVIDENCE_REQUIRED": "false",
    "CHANGESAFE_MODE": "replay",
    "CHANGESAFE_RUNS_PER_MINUTE": "30",
    "CHANGESAFE_WAREHOUSE_VALIDATION_ENABLED": "false",
    "CHANGESAFE_WAREHOUSE_VALIDATION_REQUIRED": "false",
    "CHANGESAFE_WEB_DIST": "/app/web",
    "PORT": "8000",
    "PUBLIC_PR_ENABLED": "false",
    "PUBLIC_WRITEBACK_ENABLED": "false",
}


def load_service() -> dict[str, Any]:
    document = yaml.safe_load(BLUEPRINT.read_text(encoding="utf-8"))
    assert list(document) == ["services"]
    assert len(document["services"]) == 1
    return document["services"][0]


def test_render_blueprint_deploys_the_existing_container_safely() -> None:
    service = load_service()
    assert service["type"] == "web"
    assert service["name"] == "changesafe-competition"
    assert service["runtime"] == "docker"
    assert service["plan"] == "free"
    assert service["region"] == "ohio"
    assert service["branch"] == "master"
    assert service["autoDeployTrigger"] == "checksPass"
    assert service["dockerfilePath"] == "./Dockerfile"
    assert service["dockerContext"] == "."
    assert service["healthCheckPath"] == "/healthz"
    assert service["renderSubdomainPolicy"] == "enabled"
    assert service["maxShutdownDelaySeconds"] == 30
    assert "disk" not in service


def test_render_blueprint_contains_only_public_safe_environment() -> None:
    service = load_service()
    environment = {item["key"]: item["value"] for item in service["envVars"]}
    assert environment == EXPECTED_ENV
    forbidden_fragments = ("TOKEN", "PASSWORD", "PRIVATE_KEY", "SECRET")
    assert not any(
        fragment in key
        for key in environment
        for fragment in forbidden_fragments
    )
```

- [ ] **Step 2: Run the test and verify the missing Blueprint fails**

Run:

```powershell
& '.\.venv\Scripts\python.exe' -m pytest -q apps/api/tests/test_render_deployment.py
```

Expected: FAIL with `FileNotFoundError` for `render.yaml`.

- [ ] **Step 3: Add the minimal Blueprint**

```yaml
services:
  - type: web
    name: changesafe-competition
    runtime: docker
    plan: free
    region: ohio
    branch: master
    autoDeployTrigger: checksPass
    dockerfilePath: ./Dockerfile
    dockerContext: .
    healthCheckPath: /healthz
    renderSubdomainPolicy: enabled
    maxShutdownDelaySeconds: 30
    envVars:
      - key: PORT
        value: "8000"
      - key: CHANGESAFE_MODE
        value: replay
      - key: CHANGESAFE_DATA_PATH
        value: /data/changesafe.db
      - key: CHANGESAFE_WEB_DIST
        value: /app/web
      - key: CHANGESAFE_RUNS_PER_MINUTE
        value: "30"
      - key: CHANGESAFE_LIVE_EVIDENCE_REQUIRED
        value: "false"
      - key: CHANGESAFE_WAREHOUSE_VALIDATION_ENABLED
        value: "false"
      - key: CHANGESAFE_WAREHOUSE_VALIDATION_REQUIRED
        value: "false"
      - key: PUBLIC_PR_ENABLED
        value: "false"
      - key: PUBLIC_WRITEBACK_ENABLED
        value: "false"
```

- [ ] **Step 4: Run focused and static verification**

Run:

```powershell
& '.\.venv\Scripts\python.exe' -m pytest -q apps/api/tests/test_render_deployment.py
& '.\.venv\Scripts\ruff.exe' check apps/api/tests/test_render_deployment.py
& '.\.venv\Scripts\python.exe' scripts/check_secrets.py
git diff --check
```

Expected: two tests pass; Ruff, the credential scan, and the diff check exit 0.

- [ ] **Step 5: Commit the Blueprint contract**

```powershell
git add -- render.yaml apps/api/tests/test_render_deployment.py
git commit -m "build: add safe Render competition deployment"
```

---

### Task 2: Publish the one-click deployment and judge runbook

**Files:**
- Modify: `apps/api/tests/test_render_deployment.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: the `render.yaml` Blueprint from Task 1 and public repository `https://github.com/marker2601/changesafe`.
- Produces: a one-click Render deployment link, a truthful hosted-demo explanation, and explicit cold-start/live-upgrade boundaries.

- [ ] **Step 1: Add failing README contract assertions**

Append to `apps/api/tests/test_render_deployment.py`:

```python
README = ROOT / "README.md"
DEPLOY_URL = (
    "https://render.com/deploy?repo="
    "https://github.com/marker2601/changesafe"
)


def test_readme_exposes_truthful_render_deployment() -> None:
    readme = README.read_text(encoding="utf-8")
    assert DEPLOY_URL in readme
    assert "competition-ready pilot" in readme
    assert "Recorded DataHub evidence" in readme
    assert "free service can sleep" in readme
    assert "may clear earlier run history" in readme
    assert "publicly reachable DataHub GMS URL" in readme
```

- [ ] **Step 2: Run the focused test and verify the missing documentation fails**

Run:

```powershell
& '.\.venv\Scripts\python.exe' -m pytest -q apps/api/tests/test_render_deployment.py
```

Expected: the two Blueprint tests pass and `test_readme_exposes_truthful_render_deployment` fails on the missing deploy URL.

- [ ] **Step 3: Add the hosted-demo section and Deploy to Render button**

Place this section immediately before `## Fastest start: Docker replay`:

```markdown
## Hosted competition pilot

ChangeSafe can be deployed as a credential-free, competition-ready pilot on
Render. The hosted default executes the real analysis, generation, verification,
event, preview-approval, and patch paths against checksum-pinned Recorded DataHub
evidence. It does not query production rows or enable external mutations.

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/marker2601/changesafe)

The free service can sleep after inactivity and may take extra time on its first
request. Its ephemeral filesystem may clear earlier run history after a restart;
start a new analysis if that happens. Upgrade the same service with a persistent
disk mounted at `/data` before claiming durable hosted history.

Live hosted metadata requires a publicly reachable DataHub GMS URL and a
server-side token. Keep replay mode enabled until that endpoint exists and the
live smoke test passes from the hosted environment.
```

- [ ] **Step 4: Run the focused test and documentation checks**

Run:

```powershell
& '.\.venv\Scripts\python.exe' -m pytest -q apps/api/tests/test_render_deployment.py
& '.\.venv\Scripts\ruff.exe' check apps/api/tests/test_render_deployment.py
& '.\.venv\Scripts\python.exe' scripts/check_secrets.py
git diff --check
```

Expected: three tests pass and every static check exits 0.

- [ ] **Step 5: Commit the deployment documentation**

```powershell
git add -- README.md apps/api/tests/test_render_deployment.py
git commit -m "docs: add Render competition launch path"
```

---

### Task 3: Push, authorize Render, and prove the hosted workflow

**Files:**
- Modify after hosted verification: `README.md`

**Interfaces:**
- Consumes: committed Tasks 1–2, GitHub repository authorization in Render, and the generated Render service URL.
- Produces: a verified stable HTTPS demo URL documented in the repository and ready for the Devpost project field.

- [ ] **Step 1: Run the complete pre-push release gate**

Run:

```powershell
& '.\.venv\Scripts\python.exe' -m pytest -q
& '.\.venv\Scripts\ruff.exe' check .
& '.\.venv\Scripts\mypy.exe' apps/api/src
& '.\.venv\Scripts\python.exe' scripts/regenerate_examples.py --check
& '.\.venv\Scripts\python.exe' scripts/check_secrets.py
$nodeBin='C:\Users\harik\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin'
$env:PATH="$nodeBin;$env:PATH"
pnpm --filter @changesafe/web lint
pnpm --filter @changesafe/web typecheck
pnpm --filter @changesafe/web test --run
pnpm --filter @changesafe/web build
git diff --check
```

Expected: every command exits 0 with no failed test.

- [ ] **Step 2: Build and smoke the exact Docker image locally**

Run:

```powershell
docker build --pull -t changesafe:render-candidate .
docker rm -f changesafe-render-candidate 2>$null
docker run -d --name changesafe-render-candidate -p 18141:8000 changesafe:render-candidate
```

Poll `http://127.0.0.1:18141/healthz` until it returns `{"status":"ok"}`, then verify `/`, `/api/config/public`, and one complete preview run. Stop and remove only `changesafe-render-candidate` after the smoke.

- [ ] **Step 3: Push master and open the Blueprint authorization**

Run:

```powershell
git push origin master
```

Open:

```text
https://render.com/deploy?repo=https://github.com/marker2601/changesafe
```

Sign in with GitHub, review the single free web service, and approve the Blueprint. Do not enter any service credential.

- [ ] **Step 4: Verify the actual Render URL**

Copy the generated HTTPS service URL into the process-local variable `CHANGESAFE_HOSTED_URL`, then run:

```powershell
$env:CHANGESAFE_HOSTED_URL='the exact HTTPS URL copied from Render'
Invoke-RestMethod "$env:CHANGESAFE_HOSTED_URL/healthz"
Invoke-RestMethod "$env:CHANGESAFE_HOSTED_URL/api/config/public"
```

Use the browser to prove at 1440 px and 430 px:

1. the page and 55-field schema load after any cold start;
2. rename, remove, and type-change requests reach a truthful terminal state;
3. each successful run exposes seven artifacts and 12/12 static checks;
4. approval creates a preview receipt and downloadable patch;
5. refresh restores the current run and terminal SSE EOF creates no false error;
6. provenance says recorded DataHub evidence and production rows not queried;
7. keyboard field selection, drawer focus return, and mobile overflow remain correct; and
8. browser console and page errors remain empty.

- [ ] **Step 5: Add the verified hosted URL and rerun the documentation test**

Add one sentence under `## Hosted competition pilot` using the exact Render URL:

```markdown
Open the verified judging deployment at **[ChangeSafe competition pilot](the exact Render HTTPS URL)**.
```

Run:

```powershell
& '.\.venv\Scripts\python.exe' -m pytest -q apps/api/tests/test_render_deployment.py
& '.\.venv\Scripts\python.exe' scripts/check_secrets.py
git diff --check
```

Expected: all deployment tests and static checks pass.

- [ ] **Step 6: Commit and push the verified URL**

```powershell
git add -- README.md
git commit -m "docs: publish verified competition demo"
git push origin master
```

Recheck the same Render URL after the auto-deploy completes. Use this URL in the Devpost project field only after the final root and `/healthz` checks return 200.
