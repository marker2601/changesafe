# ChangeSafe Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a production-oriented, credential-free-by-default ChangeSafe web application that analyzes DataHub-aware schema changes, generates and verifies safe migration artifacts, and supports owner-gated GitHub/DataHub publication.

**Architecture:** A React/TypeScript single-run workspace talks to a FastAPI service over JSON and server-sent events. The service runs an explicit state machine backed by SQLite, with typed ports for DataHub context, bounded generation, artifact verification, GitHub publication, and DataHub writeback; replay implementations make the complete golden workflow deterministic and credential-free.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, aiosqlite, sqlglot, PyYAML, OpenAI Responses API, datahub-agent-context 1.7.0, React 19, TypeScript, Vite, Vitest, Playwright, pnpm 11, Docker, GitHub Actions.

## Global Constraints

- Support exactly one rename, removal, or type-change operation per run.
- The golden rename must find exactly four downstream assets and score 90/Critical.
- Replay mode is credential-free, truthful about snapshot provenance, and incapable of external mutation.
- External mutations require verified artifacts, explicit approval, feature flags, allowlists, and `CHANGESAFE_ADMIN_TOKEN`.
- The LLM cannot alter the deterministic score or omit mandatory files; tests and replay cannot require paid calls.
- Generate exactly seven golden artifacts and block publication on any mandatory verification failure.
- Keep generated paths confined to the approved artifact allowlist and never execute generated shell code.
- Use Python 3.12, Node.js 24, `datahub-agent-context==1.7.0`, and `gpt-5.6-luna` as the configurable default model.
- Serve frontend, API, SSE, and health checks from one origin in the production container.
- Keep all secrets server-side and redact tokens and authorization headers from logs, errors, evidence, fixtures, and built assets.

---

## File map

- `pyproject.toml`: Python package metadata, runtime dependencies, lint/type/test configuration.
- `apps/api/src/changesafe/`: backend package containing configuration, domain contracts, adapters, orchestration, persistence, and HTTP routes.
- `apps/api/tests/`: unit, contract, integration, security, and API tests.
- `apps/web/src/`: React application, API client, state hook, accessible product components, and styling.
- `apps/web/tests/`: Vitest component tests.
- `tests/e2e/`: Playwright golden-flow and accessibility smoke tests.
- `fixtures/datahub/`: canonical replay context, evidence envelopes, and checksum.
- `examples/unsafe-change/`: golden input request.
- `examples/generated-safe-change/`: verified expected artifact set.
- `scripts/`: Windows and portable development launchers, fixture capture, checksum, and DataHub seed entry points.
- `.github/workflows/ci.yml`: full quality gate.
- `Dockerfile`, `docker-compose.yml`: reproducible single-container build and replay startup.
- `README.md`, `LICENSE`, `CONTRIBUTING.md`, `SECURITY.md`, `docs/`: public setup, architecture, limitations, submission copy, and demo script.

---

### Task 1: Reproducible monorepo and safe configuration

**Files:**
- Create: `pyproject.toml`
- Create: `apps/api/src/changesafe/__init__.py`
- Create: `apps/api/src/changesafe/config.py`
- Create: `apps/api/tests/test_config.py`
- Create: `apps/web/package.json`
- Create: `apps/web/tsconfig.json`
- Create: `apps/web/vite.config.ts`
- Create: `apps/web/index.html`
- Create: `package.json`
- Create: `pnpm-workspace.yaml`
- Create: `.env.example`
- Create: `scripts/dev.ps1`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: `C:/Users/harik/ChangeSafe/private/changesafe.env` when it exists or the path supplied by `CHANGESAFE_ENV_FILE`.
- Produces: `Settings` with `mode`, credential-presence properties, mutation gates, paths, retry policy, and public-safe configuration.

- [ ] **Step 1: Write failing configuration tests**

```python
def test_replay_defaults_need_no_credentials(monkeypatch, tmp_path):
    monkeypatch.setenv("CHANGESAFE_ENV_FILE", str(tmp_path / "missing.env"))
    settings = Settings(_env_file=None)
    assert settings.mode == Mode.REPLAY
    assert settings.live_context_enabled is False
    assert settings.public_pr_enabled is False


def test_live_mutation_requires_admin_token():
    with pytest.raises(ValidationError):
        Settings(mode="live", public_pr_enabled=True, github_token="token")
```

- [ ] **Step 2: Run the focused tests and confirm they fail because `Settings` does not exist**

Run: `python -m pytest apps/api/tests/test_config.py -q`

- [ ] **Step 3: Implement strict settings and private env-file resolution**

```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_default_env_file(), extra="ignore")
    mode: Mode = Mode.REPLAY
    changesafe_data_path: Path = Path("data/changesafe.db")
    datahub_gms_url: AnyHttpUrl | None = None
    datahub_gms_token: SecretStr | None = None
    openai_api_key: SecretStr | None = None
    openai_model: str = "gpt-5.6-luna"
    github_token: SecretStr | None = None
    github_repository: str | None = None
    github_base_branch: str = "main"
    public_writeback_enabled: bool = False
    public_pr_enabled: bool = False
    changesafe_admin_token: SecretStr | None = None
```

- [ ] **Step 4: Add locked workspace manifests, `.env.example`, and the PowerShell launcher**

`scripts/dev.ps1` sets `CHANGESAFE_ENV_FILE` to the private file when present, starts FastAPI on port 8000, and starts Vite on port 5173 with API proxying.

- [ ] **Step 5: Install dependencies and run configuration tests**

Run: `python -m pip install -e ".[dev,live]"`
Run: `pnpm install --frozen-lockfile=false`
Run: `python -m pytest apps/api/tests/test_config.py -q`

- [ ] **Step 6: Commit the foundation**

```bash
git add .gitignore .env.example pyproject.toml package.json pnpm-workspace.yaml apps scripts/dev.ps1
git commit -m "build: establish ChangeSafe monorepo"
```

### Task 2: Domain contracts and deterministic risk engine

**Files:**
- Create: `apps/api/src/changesafe/domain.py`
- Create: `apps/api/src/changesafe/risk.py`
- Create: `apps/api/tests/test_domain.py`
- Create: `apps/api/tests/test_risk.py`
- Create: `examples/unsafe-change/change.json`

**Interfaces:**
- Produces: `ChangeRequest`, `ContextBundle`, `EvidenceRef`, `AffectedAsset`, `RiskFactor`, `RiskResult`, `ArtifactFile`, `ArtifactBundle`, `ValidationCheck`, `ValidationReport`, `AnalysisResult`, `RunState`, `RunView`.
- Produces: `score_change(change: ChangeRequest, context: ContextBundle) -> RiskResult`.

- [ ] **Step 1: Write validation and score tests**

```python
def test_rename_requires_new_field():
    with pytest.raises(ValidationError):
        ChangeRequest(asset_urn=TARGET, operation="rename", field="customer_email")


def test_golden_rename_scores_ninety(golden_context):
    result = score_change(golden_change(), golden_context)
    assert (result.score, result.band) == (90, RiskBand.CRITICAL)
    assert [factor.points for factor in result.factors] == [25, 20, 15, 10, 10, 10]
```

- [ ] **Step 2: Confirm boundary tests fail before implementation**

Run: `python -m pytest apps/api/tests/test_domain.py apps/api/tests/test_risk.py -q`

- [ ] **Step 3: Implement strict Pydantic contracts and the explicit lifecycle enum**

```python
class RunState(StrEnum):
    CREATED = "created"
    LOADING_CONTEXT = "loading_context"
    SCORING_RISK = "scoring_risk"
    GENERATING = "generating"
    VALIDATING = "validating"
    AWAITING_APPROVAL = "awaiting_approval"
    PREPARING_PREVIEW = "preparing_preview"
    PUBLISHING = "publishing"
    COMPLETED = "completed"
    FAILED = "failed"
    PUBLICATION_FAILED = "publication_failed"
```

- [ ] **Step 4: Implement risk rules with ordered evidence factors and a 100-point cap**

```python
def score_change(change: ChangeRequest, context: ContextBundle) -> RiskResult:
    factors = [base_factor(change)]
    factors.extend(context_factors(context))
    score = min(sum(item.points for item in factors), 100)
    return RiskResult(score=score, band=band_for(score), factors=factors)
```

- [ ] **Step 5: Run unit tests and commit**

Run: `python -m pytest apps/api/tests/test_domain.py apps/api/tests/test_risk.py -q`

```bash
git add apps/api/src/changesafe/domain.py apps/api/src/changesafe/risk.py apps/api/tests examples/unsafe-change
git commit -m "feat: add deterministic change risk model"
```

### Task 3: Replay fixture and live DataHub context port

**Files:**
- Create: `apps/api/src/changesafe/context/base.py`
- Create: `apps/api/src/changesafe/context/replay.py`
- Create: `apps/api/src/changesafe/context/live.py`
- Create: `apps/api/src/changesafe/context/factory.py`
- Create: `apps/api/src/changesafe/redaction.py`
- Create: `fixtures/datahub/golden-context.json`
- Create: `fixtures/datahub/golden-context.sha256`
- Create: `apps/api/tests/context/test_contract.py`
- Create: `apps/api/tests/context/test_live_mapping.py`
- Create: `apps/api/tests/test_redaction.py`
- Create: `scripts/capture_snapshot.py`
- Create: `scripts/seed_datahub.py`

**Interfaces:**
- Produces: `DataHubContextPort.load(change) -> ContextBundle` and `DataHubContextPort.writeback(run, approval) -> DataHubReceipt`.
- Live calls execute inside `DataHubContext(DataHubClient(server=url, token=token))` and are wrapped by `asyncio.to_thread`.

- [ ] **Step 1: Add a canonical synthetic snapshot and contract tests**

```python
@pytest.mark.parametrize("factory", [replay_port, fake_live_port])
async def test_context_contract_finds_four_downstream_assets(factory, golden_change):
    context = await factory().load(golden_change)
    assert len(context.downstream_assets) == 4
    assert context.usage_tier == "high"
    assert "urn:li:tag:PII" in context.field_tags
```

- [ ] **Step 2: Run context tests and confirm missing adapter failures**

Run: `python -m pytest apps/api/tests/context apps/api/tests/test_redaction.py -q`

- [ ] **Step 3: Implement replay checksum verification and sanitized evidence envelopes**

The replay adapter rejects checksum drift, sets `mode="snapshot"`, and records timestamp, adapter version, SHA-256, bounded parameters, duration, result count, and referenced URNs.

- [ ] **Step 4: Implement real Agent Context Kit calls**

```python
with DataHubContext(client):
    entity = get_entities([change.asset_urn])
    schema = list_schema_fields(change.asset_urn, keywords=[change.field])
    downstream = get_lineage(change.asset_urn, column=change.field, upstream=False, max_hops=3)
    queries = get_dataset_queries(change.asset_urn, column=change.field, count=10)
```

- [ ] **Step 5: Implement allowlisted writeback using `save_document`, `add_structured_properties`, and `add_tags`**

The writeback method validates the exact target URN, artifact hash, admin authorization, and idempotency ledger before executing mutations.

- [ ] **Step 6: Implement redaction and snapshot capture/seed commands**

Redaction recursively replaces values for keys matching `authorization`, `token`, `secret`, `password`, or `api_key`; capture writes canonical sorted JSON plus checksum.

- [ ] **Step 7: Run contract tests and commit**

Run: `python -m pytest apps/api/tests/context apps/api/tests/test_redaction.py -q`

```bash
git add apps/api/src/changesafe/context apps/api/src/changesafe/redaction.py fixtures scripts apps/api/tests/context apps/api/tests/test_redaction.py
git commit -m "feat: add DataHub live and replay context adapters"
```

### Task 4: Safe artifact generation and mandatory verifier

**Files:**
- Create: `apps/api/src/changesafe/generation/templates.py`
- Create: `apps/api/src/changesafe/generation/openai_generator.py`
- Create: `apps/api/src/changesafe/generation/service.py`
- Create: `apps/api/src/changesafe/verification.py`
- Create: `apps/api/tests/test_generation.py`
- Create: `apps/api/tests/test_verification.py`
- Create: `examples/generated-safe-change/models/marts/dim_customers.sql`
- Create: `examples/generated-safe-change/models/marts/dim_customers.yml`
- Create: `examples/generated-safe-change/tests/assert_customer_email_compatibility.sql`
- Create: `examples/generated-safe-change/migrations/2026-08-06-customer-email-rename.md`
- Create: `examples/generated-safe-change/ROLLBACK.md`
- Create: `examples/generated-safe-change/PR_BODY.md`
- Create: `examples/generated-safe-change/changesafe-manifest.json`

**Interfaces:**
- Produces: `generate_artifacts(change, context, risk, llm=None) -> ArtifactBundle`.
- Produces: `verify_artifacts(bundle, change, context) -> ValidationReport`.

- [ ] **Step 1: Write golden generation and adversarial verification tests**

```python
def test_golden_rename_generates_exact_manifest(golden_change, golden_context, golden_risk):
    bundle = generate_artifacts(golden_change, golden_context, golden_risk)
    assert sorted(bundle.files) == sorted(EXPECTED_SEVEN_PATHS)
    assert "customer_email" in bundle.files[MODEL_SQL].content
    assert "primary_email" in bundle.files[MODEL_SQL].content


def test_select_star_blocks_publication(valid_bundle, golden_change, golden_context):
    invalid = replace_file(valid_bundle, MODEL_SQL, "select * from analytics.stg_customers")
    report = verify_artifacts(invalid, golden_change, golden_context)
    assert report.passed is False
    assert report.check("no_select_star").passed is False
```

- [ ] **Step 2: Confirm tests fail before generator and verifier exist**

Run: `python -m pytest apps/api/tests/test_generation.py apps/api/tests/test_verification.py -q`

- [ ] **Step 3: Implement deterministic rename, removal, and type-change templates**

Every template produces the same seven allowed paths; phase-one rename aliases the source expression twice so old and new names coexist.

- [ ] **Step 4: Implement optional one-call OpenAI structured planning**

The Responses API schema permits only transformation expression, explanation, deprecation language, migration summary, rollback summary, and PR prose. The deterministic template remains authoritative.

- [ ] **Step 5: Implement SQL, YAML, compatibility, path, rollback, and manifest verification**

Use `sqlglot.parse` with the configured dialect, `yaml.safe_load`, normalized `PurePosixPath`, and SHA-256 over exact UTF-8 bytes.

- [ ] **Step 6: Materialize golden examples, run tests, and commit**

Run: `python -m pytest apps/api/tests/test_generation.py apps/api/tests/test_verification.py -q`

```bash
git add apps/api/src/changesafe/generation apps/api/src/changesafe/verification.py apps/api/tests examples/generated-safe-change
git commit -m "feat: generate and verify safe migration artifacts"
```

### Task 5: Durable run store, orchestrator, API, and SSE

**Files:**
- Create: `apps/api/src/changesafe/store.py`
- Create: `apps/api/src/changesafe/orchestrator.py`
- Create: `apps/api/src/changesafe/api.py`
- Create: `apps/api/src/changesafe/main.py`
- Create: `apps/api/tests/test_store.py`
- Create: `apps/api/tests/test_orchestrator.py`
- Create: `apps/api/tests/test_api.py`

**Interfaces:**
- Produces: `RunStore.create`, `RunStore.transition`, `RunStore.get`, `RunStore.events`, and publication-ledger methods.
- Produces: `POST /api/runs`, `GET /api/runs/{run_id}`, `GET /api/runs/{run_id}/events`, `POST /api/runs/{run_id}/approve`, `GET /api/runs/{run_id}/artifacts/{path}`, `GET /api/public-config`, and `GET /healthz`.

- [ ] **Step 1: Write state-machine, persistence, and API tests**

```python
async def test_golden_run_reaches_awaiting_approval(client):
    created = (await client.post("/api/runs", json=GOLDEN_CHANGE)).json()
    run = await wait_for_state(client, created["run_id"], "awaiting_approval")
    assert run["analysis"]["risk"]["score"] == 90
    assert len(run["analysis"]["artifacts"]["files"]) == 7


async def test_invalid_transition_is_rejected(store, run_id):
    with pytest.raises(InvalidTransition):
        await store.transition(run_id, RunState.COMPLETED)
```

- [ ] **Step 2: Run tests and confirm failures**

Run: `python -m pytest apps/api/tests/test_store.py apps/api/tests/test_orchestrator.py apps/api/tests/test_api.py -q`

- [ ] **Step 3: Implement SQLite tables and atomic transition validation**

Tables: `runs(run_id, state, request_json, analysis_json, error_json, artifact_hash, created_at, updated_at)`, `run_events(sequence, run_id, state, public_message, evidence_json, created_at)`, and `publication_ledger(idempotency_key, artifact_hash, receipt_json, created_at)`.

- [ ] **Step 4: Implement the orchestration pipeline**

```python
await transition(LOADING_CONTEXT)
context = await context_port.load(change)
await transition(SCORING_RISK)
risk = score_change(change, context)
await transition(GENERATING)
artifacts = await generator.generate(change, context, risk)
await transition(VALIDATING)
validation = verify_artifacts(artifacts, change, context)
await transition(AWAITING_APPROVAL if validation.passed else FAILED)
```

- [ ] **Step 5: Implement HTTP routes, safe errors, SSE resume via `Last-Event-ID`, and static frontend fallback**

The SSE endpoint emits `id`, `event: run_state`, and JSON `data`; it sends a 15-second comment heartbeat and closes on terminal state.

- [ ] **Step 6: Run integration tests and commit**

Run: `python -m pytest apps/api/tests/test_store.py apps/api/tests/test_orchestrator.py apps/api/tests/test_api.py -q`

```bash
git add apps/api/src/changesafe/store.py apps/api/src/changesafe/orchestrator.py apps/api/src/changesafe/api.py apps/api/src/changesafe/main.py apps/api/tests
git commit -m "feat: orchestrate durable ChangeSafe analysis runs"
```

### Task 6: GitHub publisher, preview patch, and idempotent approval

**Files:**
- Create: `apps/api/src/changesafe/publication/base.py`
- Create: `apps/api/src/changesafe/publication/preview.py`
- Create: `apps/api/src/changesafe/publication/github.py`
- Create: `apps/api/src/changesafe/publication/service.py`
- Create: `apps/api/tests/publication/test_preview.py`
- Create: `apps/api/tests/publication/test_github.py`
- Create: `apps/api/tests/publication/test_idempotency.py`

**Interfaces:**
- Produces: `publication_key(change, source_commit, artifact_manifest) -> str`.
- Produces: `PublicationService.approve(run_id, supplied_admin_token) -> PublicationReceipt`.

- [ ] **Step 1: Write preview, API-mapping, gate, and retry tests**

```python
async def test_replay_approval_creates_preview_without_network(service, replay_run):
    receipt = await service.approve(replay_run.run_id, supplied_admin_token=None)
    assert receipt.mode == "preview"
    assert receipt.writeback.label == "NOT WRITTEN — SNAPSHOT MODE"


async def test_duplicate_approval_returns_existing_receipt(service, live_run):
    first = await service.approve(live_run.run_id, ADMIN_TOKEN)
    second = await service.approve(live_run.run_id, ADMIN_TOKEN)
    assert second == first
```

- [ ] **Step 2: Confirm tests fail before publishers exist**

Run: `python -m pytest apps/api/tests/publication -q`

- [ ] **Step 3: Implement downloadable unified patch and PR preview**

The patch uses `/dev/null` for added files, stable LF endings, relative allowlisted paths, and includes the generated `PR_BODY.md` as preview content.

- [ ] **Step 4: Implement GitHub branch, blob/tree/commit/ref, and pull-request calls with `httpx`**

Branch name is `changesafe/{run_id[:8]}`. Requests use the repository-scoped token only on `api.github.com`, a stable API version header, ten-second timeouts, and typed error mapping.

- [ ] **Step 5: Implement idempotency and partial-publication behavior**

The service records GitHub success before DataHub writeback, returns `publication_failed` on partial failure, and retries only the missing side effect with the original key and artifact hash.

- [ ] **Step 6: Run publication tests and commit**

Run: `python -m pytest apps/api/tests/publication -q`

```bash
git add apps/api/src/changesafe/publication apps/api/tests/publication
git commit -m "feat: add gated GitHub and DataHub publication"
```

### Task 7: Polished accessible React single-run workspace

**Files:**
- Create: `apps/web/src/main.tsx`
- Create: `apps/web/src/App.tsx`
- Create: `apps/web/src/api.ts`
- Create: `apps/web/src/types.ts`
- Create: `apps/web/src/hooks/useRun.ts`
- Create: `apps/web/src/components/Header.tsx`
- Create: `apps/web/src/components/ChangeForm.tsx`
- Create: `apps/web/src/components/RunTimeline.tsx`
- Create: `apps/web/src/components/RiskCard.tsx`
- Create: `apps/web/src/components/ImpactGraph.tsx`
- Create: `apps/web/src/components/AffectedAssets.tsx`
- Create: `apps/web/src/components/ArtifactExplorer.tsx`
- Create: `apps/web/src/components/ValidationPanel.tsx`
- Create: `apps/web/src/components/ApprovalPanel.tsx`
- Create: `apps/web/src/styles.css`
- Create: `apps/web/tests/App.test.tsx`
- Create: `apps/web/tests/ChangeForm.test.tsx`
- Create: `apps/web/tests/RiskCard.test.tsx`

**Interfaces:**
- Consumes: API routes and JSON contracts from Task 5.
- Produces: keyboard-accessible golden workflow at `/` with truthful live/snapshot badges, evidence, score, impact, files, validation, preview approval, and receipts.

- [ ] **Step 1: Write component tests for the seeded form, 90/Critical result, and approval labels**

```tsx
it("shows the deterministic score and every factor", async () => {
  render(<App api={goldenApi} />);
  await userEvent.click(screen.getByRole("button", { name: /analyze change/i }));
  expect(await screen.findByText("90")).toBeVisible();
  expect(screen.getByText("Critical risk")).toBeVisible();
  expect(screen.getAllByTestId("risk-factor")).toHaveLength(6);
});
```

- [ ] **Step 2: Run Vitest and confirm missing UI failures**

Run: `pnpm --filter @changesafe/web test --run`

- [ ] **Step 3: Implement typed API client and resilient EventSource run hook**

The hook reconnects once with the last sequence, fetches the final run on terminal state, exposes `analyze`, `approve`, `retry`, and never invents progress events.

- [ ] **Step 4: Implement the responsive operations-console layout**

Use a warm off-white canvas, navy text, teal success, amber risk, restrained red failure, 44-pixel minimum controls, visible focus rings, tabbed artifact viewer, and a compact SVG lineage graph with text labels.

- [ ] **Step 5: Implement loading, empty, failure, partial-publication, and preview states**

Every state has visible text and icon cues; generated Markdown and code render as escaped text rather than injected HTML.

- [ ] **Step 6: Run lint, type checking, component tests, and commit**

Run: `pnpm --filter @changesafe/web lint`
Run: `pnpm --filter @changesafe/web typecheck`
Run: `pnpm --filter @changesafe/web test --run`

```bash
git add apps/web
git commit -m "feat: build ChangeSafe analysis workspace"
```

### Task 8: End-to-end proof, container, CI, documentation, and submission assets

**Files:**
- Create: `playwright.config.ts`
- Create: `tests/e2e/golden-flow.spec.ts`
- Create: `Dockerfile`
- Create: `docker-compose.yml`
- Create: `.dockerignore`
- Create: `.github/workflows/ci.yml`
- Create: `LICENSE`
- Create: `README.md`
- Create: `CONTRIBUTING.md`
- Create: `SECURITY.md`
- Create: `docs/architecture.md`
- Create: `docs/demo-script.md`
- Create: `docs/devpost-submission.md`
- Create: `docs/ai-assistance.md`

**Interfaces:**
- Produces: one-command `docker compose up --build` replay demo on `http://localhost:8000`.
- Produces: CI gates for Python, TypeScript, artifact verification, Playwright, secret scan, license, and Docker health smoke test.

- [ ] **Step 1: Write the browser acceptance test**

```ts
test("judge completes the credential-free golden workflow", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText("DATAHUB SNAPSHOT")).toBeVisible();
  await page.getByRole("button", { name: "Analyze change" }).click();
  await expect(page.getByText("90")).toBeVisible();
  await expect(page.getByText("Critical risk")).toBeVisible();
  await expect(page.getByTestId("affected-asset-row")).toHaveCount(4);
  await expect(page.getByTestId("artifact-file")).toHaveCount(7);
  await page.getByRole("button", { name: "Approve preview" }).click();
  await expect(page.getByText("NOT WRITTEN — SNAPSHOT MODE")).toBeVisible();
});
```

- [ ] **Step 2: Run Playwright and confirm failure before production assembly**

Run: `pnpm exec playwright test tests/e2e/golden-flow.spec.ts`

- [ ] **Step 3: Implement multi-stage Docker build and replay Compose service**

Stage one builds `apps/web/dist` with Node 24; stage two installs the Python application into `python:3.12-slim`, copies the frontend into the backend static directory, runs as an unprivileged user, mounts `/data`, and exposes `/healthz`.

- [ ] **Step 4: Add complete CI gates and credential-conditional live smoke jobs**

The default workflow never requires secrets. Live DataHub, OpenAI, and publication smoke tests run only when their explicit environment variables exist.

- [ ] **Step 5: Write public documentation and the under-three-minute demo script**

README includes architecture, replay quick start, local development, private env-file instructions, live setup, access scopes, security controls, test commands, limitations, screenshots section, and verified claims only.

- [ ] **Step 6: Run the complete verification matrix**

Run: `python -m ruff check .`
Run: `python -m mypy apps/api/src`
Run: `python -m pytest -q`
Run: `pnpm --filter @changesafe/web lint`
Run: `pnpm --filter @changesafe/web typecheck`
Run: `pnpm --filter @changesafe/web test --run`
Run: `pnpm exec playwright test`
Run: `docker build -t changesafe:local .`
Run: `docker run --rm -d --name changesafe-smoke -p 8000:8000 changesafe:local`
Run: `Invoke-WebRequest -UseBasicParsing http://localhost:8000/healthz`

- [ ] **Step 7: Commit the release-ready project**

```bash
git add .dockerignore .github Dockerfile docker-compose.yml playwright.config.ts tests LICENSE README.md CONTRIBUTING.md SECURITY.md docs
git commit -m "docs: complete ChangeSafe release package"
```

---

## Coverage check

- Product workflow, modes, deterministic score, seven artifacts, and three-minute narrative: Tasks 2, 4, 5, 7, 8.
- Live/replay DataHub reads, writes, evidence, checksum, seed, and parity: Task 3.
- Bounded LLM generation and USD 5 ceiling: Tasks 1 and 4.
- SQL/YAML/path/compatibility/manifest verification: Task 4.
- GitHub PR preview/live publication and idempotency: Task 6.
- Durable lifecycle, SSE, failure states, and partial publication: Tasks 5 and 6.
- Accessible responsive judge experience: Task 7.
- Unit, contract, integration, browser, CI, Docker, security, documentation, and submission deliverables: Task 8.
