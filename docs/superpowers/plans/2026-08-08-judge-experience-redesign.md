# ChangeSafe Judge Experience Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn ChangeSafe into the approved event-driven judge command center using DataHub's official `showcase-ecommerce` Order Entry Analytics scenario, evidence-led impact classifications, a secure shared judge sandbox, and truthful publication receipts.

**Architecture:** Preserve the existing FastAPI, SQLite, React, SSE, deterministic generation, verification, and publication boundaries. Extend the normalized analysis contract with deterministic impact assessments, move the golden replay and live seed to the organizer's official `order_details.cust_email` graph, add privacy-limited session activity behind the existing owner token, and rebuild the React composition around the approved command-center image while reusing existing functional components.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, SQLite/aiosqlite, DataHub Agent Context Kit 1.7, React 19, TypeScript 6, Vite 8, Vitest, Testing Library, Playwright, dbt, CSS.

## Global Constraints

- Canonical headline: `Change data safely, with every dependency in view.`
- Canonical scenario: DataHub `showcase-ecommerce`, data product `Order Entry Analytics`, target `urn:li:dataset:(urn:li:dataPlatform:dbt,b2fd91.ORDER_ENTRY_DB.analytics.order_details,PROD)`, rename `cust_email` to `primary_email`.
- Canonical graph heading: `Tracing what depends on cust_email`.
- Generate exactly seven deterministic artifacts and require all twelve blocking checks.
- Progress is derived from persisted server events, never presentation timers.
- Impact inferences always carry confidence and evidence; financial exposure is never given a fabricated amount.
- Judges never provide DataHub, GitHub, or OpenAI credentials; service secrets remain server-side.
- Replay, live, fallback, preview, and published provenance must remain visibly distinct.
- No warehouse SQL execution, automatic PR merge, or unallowlisted external write.
- Preserve current publication crash recovery, destination binding, artifact integrity, policy re-verification, rate limiting, strict request schemas, and secret scanning.
- Desktop and mobile must remain keyboard-accessible, WCAG AA, screen-reader understandable, and reduced-motion safe.
- Use the existing Lucide dependency for UI icons; do not create handmade interface SVG or CSS art.
- Implement on `master` only because the user explicitly authorized direct completion and merge to `master`.

---

### Task 1: Establish the official ecommerce golden scenario

**Files:**
- Create: `apps/api/src/changesafe/demo.py`
- Modify: `apps/api/src/changesafe/config.py`
- Modify: `apps/api/src/changesafe/context/live.py`
- Modify: `fixtures/datahub/golden-context.json`
- Modify: `fixtures/datahub/golden-context.sha256`
- Modify: `examples/unsafe-change/change.json`
- Modify: `scripts/seed_datahub.py`
- Modify: `scripts/regenerate_examples.py`
- Modify: `apps/api/tests/context/test_contract.py`
- Modify: `apps/api/tests/context/test_live_mapping.py`
- Modify: `apps/api/tests/context/test_scripts.py`
- Modify: `apps/api/tests/test_config.py`
- Modify: `apps/api/tests/test_domain.py`
- Modify: `apps/api/tests/test_generation.py`
- Modify: `apps/api/tests/test_openai_generation.py`
- Modify: `apps/api/tests/test_orchestrator.py`
- Modify: `apps/api/tests/test_risk.py`
- Modify: `apps/api/tests/test_store.py`
- Modify: `apps/api/tests/test_verification.py`
- Modify: `apps/api/tests/publication/helpers.py`

**Interfaces:**
- Produces: `DEMO_TARGET_URN`, `DEMO_FIELD`, `DEMO_NEW_FIELD`, `DEMO_DATA_PRODUCT`, and `golden_change()` constants/helpers in `changesafe.demo`.
- Consumes: existing `ContextBundle`, replay checksum validation, Agent Context Kit 1.7 envelopes, and deterministic generator path derivation.

- [ ] **Step 1: Write failing official-scenario contract tests**

Add literal expectations to `test_contract.py`:

```python
@pytest.mark.asyncio
async def test_replay_uses_the_official_order_entry_scenario() -> None:
    context = await ReplayDataHubContext.from_default().load(golden_change())

    assert context.target_urn == DEMO_TARGET_URN
    assert context.target_name == "order_details"
    assert context.field == "cust_email"
    assert context.field_type in {"TEXT", "VARCHAR"}
    assert "urn:li:tag:b2fd91.PII_Data" in context.field_tags
    assert any("powerbi" in asset.urn.lower() for asset in context.downstream_assets)
    assert any("looker" in asset.urn.lower() for asset in context.downstream_assets)
```

Add a live normalization regression proving the golden target accepts a variable, non-empty downstream set rather than exactly four assets.

- [ ] **Step 2: Run the new tests and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest apps/api/tests/context/test_contract.py apps/api/tests/context/test_live_mapping.py -q
```

Expected: failures show the replay still targets `dim_customers`, config still allowlists it, and live normalization still contains the exact-four assertion.

- [ ] **Step 3: Add the official scenario module and remove synthetic golden coupling**

Implement `demo.py` with typed constants and a helper:

```python
DEMO_TARGET_URN = (
    "urn:li:dataset:(urn:li:dataPlatform:dbt,"
    "b2fd91.ORDER_ENTRY_DB.analytics.order_details,PROD)"
)
DEMO_FIELD = "cust_email"
DEMO_NEW_FIELD = "primary_email"
DEMO_DATA_PRODUCT = "Order Entry Analytics"

def golden_change() -> ChangeRequest:
    return ChangeRequest(
        asset_urn=DEMO_TARGET_URN,
        operation=ChangeOperation.RENAME,
        field=DEMO_FIELD,
        new_field=DEMO_NEW_FIELD,
        old_type=None,
        new_type=None,
        source_commit="showcase-ecommerce-safe-rename",
        requested_by="judge-demo",
    )
```

Import these constants in tests, config defaults, and seed scripts. Delete `GOLDEN_DOWNSTREAM_URNS` and the exact-set rejection from `live.py`; retain pagination, schema, type, and malformed-envelope fail-closed checks.

- [ ] **Step 4: Replace the replay fixture with official-source evidence**

Build the checksum-pinned snapshot around the official target and its actual 55-field schema subset required by generation. Include the direct dbt customer source upstream, the Snowflake sibling, Power BI semantic models, Looker view/explore, and a related report/dashboard only when the recorded relation is identified as direct or associated. Use the real DataHub URNs and label the official source in evidence. Do not include fabricated personal field values.

Regenerate the checksum with:

```powershell
.\.venv\Scripts\python.exe scripts/capture_snapshot.py fixtures/datahub/golden-context.json fixtures/datahub/golden-context.json fixtures/datahub/golden-context.sha256
```

Use a temporary source path if the script cannot safely read and replace the same file; never hand-edit the checksum.

- [ ] **Step 5: Align live seeding and verification with the datapack**

Update `seed_datahub.py` so it assumes `datahub datapack load showcase-ecommerce` supplies the base graph and only emits a namespaced ChangeSafe overlay when needed for reproducible query usage, decision structured properties, or field-level demo linkage. `verify_seed()` must assert the exact target, `cust_email`, PII/governance metadata, at least one accountable owner, and evidence-backed downstreams without asserting a fixed count.

- [ ] **Step 6: Run context and seed tests and verify GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest apps/api/tests/context apps/api/tests/test_config.py -q
```

Expected: all tests pass with the official URN and no synthetic exact-four dependency.

- [ ] **Step 7: Commit the scenario migration**

```powershell
git add apps/api/src/changesafe/demo.py apps/api/src/changesafe/config.py apps/api/src/changesafe/context/live.py apps/api/tests/context apps/api/tests/test_config.py fixtures/datahub examples/unsafe-change scripts/seed_datahub.py scripts/regenerate_examples.py
git commit -m "feat: adopt official ecommerce demo graph"
```

---

### Task 2: Add deterministic evidence-led impact classifications

**Files:**
- Modify: `apps/api/src/changesafe/domain.py`
- Create: `apps/api/src/changesafe/impact.py`
- Modify: `apps/api/src/changesafe/orchestrator.py`
- Modify: `apps/api/src/changesafe/publication/service.py`
- Create: `apps/api/tests/test_impact.py`
- Modify: `apps/api/tests/test_orchestrator.py`
- Modify: `apps/api/tests/publication/test_idempotency.py`

**Interfaces:**
- Produces: `ImpactCategory`, `ImpactSeverity`, `EvidenceConfidence`, `ImpactAssessment`, and `classify_impacts(change, context) -> list[ImpactAssessment]`.
- Changes: `AnalysisResult.impacts: list[ImpactAssessment]`.
- Consumes: normalized context, deterministic risk evidence, current approval-time policy validation.

- [ ] **Step 1: Write failing classifier tests**

Define six literal expected IDs and prove evidence behavior:

```python
def test_official_rename_classifies_six_evidence_led_impacts() -> None:
    impacts = classify_impacts(golden_change(), golden_context())

    assert [(item.category, item.severity) for item in impacts] == [
        (ImpactCategory.DATA_INTEGRITY, ImpactSeverity.CRITICAL),
        (ImpactCategory.PRIVACY_COMPLIANCE, ImpactSeverity.CRITICAL),
        (ImpactCategory.OPERATIONAL_CONTINUITY, ImpactSeverity.HIGH),
        (ImpactCategory.TRUST_DECISION_QUALITY, ImpactSeverity.HIGH),
        (ImpactCategory.FINANCIAL_EXPOSURE, ImpactSeverity.HIGH),
        (ImpactCategory.ORGANIZATIONAL_IMPACT, ImpactSeverity.HIGH),
    ]
    assert all(item.evidence_urns for item in impacts)
    financial = impacts[4]
    assert financial.confidence is EvidenceConfidence.INFERRED
    assert financial.qualifier == "Potentially high, not quantified"
    assert "$" not in financial.summary
```

Add boundary tests showing privacy drops to informational/unavailable without governance evidence and trust does not claim a report when only operational datasets are present.

- [ ] **Step 2: Run classifier tests and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest apps/api/tests/test_impact.py -q
```

Expected: import failure for the missing classifier and models.

- [ ] **Step 3: Implement the strict impact models and deterministic rules**

Use enum-backed categories, severity, confidence, a plain-language summary, qualifier, basis code, and non-empty evidence URNs. Reporting evidence is detected from entity type and recognized platform URNs (`looker`, `powerbi`, `tableau`); revenue/business implications remain inferred.

- [ ] **Step 4: Persist impacts and re-check them at approval**

Set `impacts=classify_impacts(run.request, context)` in the orchestrator. Extend `PublicationService._require_current_policy` to recompute impacts and require exact equality with persisted analysis, preventing pre-upgrade or manipulated impact evidence from being approved.

- [ ] **Step 5: Run impact, orchestrator, and publication tests and verify GREEN**

```powershell
.\.venv\Scripts\python.exe -m pytest apps/api/tests/test_impact.py apps/api/tests/test_orchestrator.py apps/api/tests/publication -q
```

- [ ] **Step 6: Commit the impact contract**

```powershell
git add apps/api/src/changesafe/domain.py apps/api/src/changesafe/impact.py apps/api/src/changesafe/orchestrator.py apps/api/src/changesafe/publication/service.py apps/api/tests/test_impact.py apps/api/tests/test_orchestrator.py apps/api/tests/publication
git commit -m "feat: classify evidence-led change impacts"
```

---

### Task 3: Make persisted events tell the plain-language safety story

**Files:**
- Modify: `apps/api/src/changesafe/orchestrator.py`
- Modify: `apps/api/src/changesafe/publication/service.py`
- Modify: `apps/api/tests/test_orchestrator.py`
- Modify: `apps/api/tests/publication/test_api_approval.py`
- Modify: `apps/web/tests/RunTimeline.test.tsx`

**Interfaces:**
- Produces: canonical persisted `RunEvent.public_message` values for analysis and publication.
- Consumes: existing run states and ordered SQLite event sequence.

- [ ] **Step 1: Write failing event-language tests**

Assert the ordered analysis messages are:

```python
assert [event.public_message for event in events[1:]] == [
    "Reading the existing data contract",
    "Classifying business and technical impact",
    "Preparing a compatible migration",
    "Proving the generated change is safe",
    "Waiting for the accountable owner",
]
```

The UI derives the dependency-discovery substep from the context-loaded `SCORING_RISK` event and its evidence, while publication persists `Publishing the approved change and evidence`.

- [ ] **Step 2: Run event tests and verify RED**

```powershell
.\.venv\Scripts\python.exe -m pytest apps/api/tests/test_orchestrator.py apps/api/tests/publication/test_api_approval.py -q
```

- [ ] **Step 3: Replace technical event copy at the source**

Change only public messages, not state-machine semantics. Include context evidence on the scoring transition so the graph can reveal nodes from real evidence. Preserve explicit fallback and failure messages.

- [ ] **Step 4: Run event tests and verify GREEN**

```powershell
.\.venv\Scripts\python.exe -m pytest apps/api/tests/test_orchestrator.py apps/api/tests/publication/test_api_approval.py -q
```

- [ ] **Step 5: Commit event truthfulness**

```powershell
git add apps/api/src/changesafe/orchestrator.py apps/api/src/changesafe/publication/service.py apps/api/tests/test_orchestrator.py apps/api/tests/publication/test_api_approval.py
git commit -m "feat: stream plain-language safety events"
```

---

### Task 4: Add privacy-limited shared judge activity

**Files:**
- Modify: `apps/api/src/changesafe/domain.py`
- Modify: `apps/api/src/changesafe/store.py`
- Modify: `apps/api/src/changesafe/api.py`
- Modify: `apps/api/src/changesafe/config.py`
- Modify: `apps/api/tests/test_store.py`
- Modify: `apps/api/tests/test_api.py`
- Modify: `apps/api/tests/test_config.py`

**Interfaces:**
- Produces: `JudgeActivity`, `RunStore.recent_activity(limit)`, and `GET /api/owner/activity` protected by `X-ChangeSafe-Admin-Token`.
- Changes: `RunStore.create(..., session_id: str | None = None)` and `POST /api/runs` accepts validated `X-ChangeSafe-Session-ID`.
- Consumes: existing admin secret and constant-time token comparison.

- [ ] **Step 1: Write failing persistence and authorization tests**

```python
@pytest.mark.asyncio
async def test_recent_activity_contains_only_operational_demo_fields(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.db")
    run = await store.create(golden_change(), session_id="judge_session_0123456789")
    activity = await store.recent_activity(limit=10)

    assert activity[0].run_id == run.run_id
    assert activity[0].session_label.startswith("judge-")
    assert activity[0].scenario == "Order Entry Analytics"
    assert "cust_email" not in activity[0].model_dump_json()
    assert "requested_by" not in activity[0].model_dump_json()
```

API tests must prove missing/wrong owner tokens return 403, the correct token returns activity, malformed session IDs return 400, and no secret appears in the payload.

- [ ] **Step 2: Run activity tests and verify RED**

```powershell
.\.venv\Scripts\python.exe -m pytest apps/api/tests/test_store.py apps/api/tests/test_api.py apps/api/tests/test_config.py -q
```

- [ ] **Step 3: Add the backward-compatible SQLite migration**

During `initialize()`, inspect `PRAGMA table_info(runs)` and add a nullable `session_id` column only when absent. Persist the validated opaque session ID, but expose only a stable short hash label such as `judge-4f19a0c2` from `recent_activity()`. Join current run state and publication receipt into the activity view without returning request bodies or credentials.

- [ ] **Step 4: Add the owner activity endpoint and public capability**

Add `owner_activity_available` to public config without exposing a token. Protect the endpoint with the same configured owner secret using `secrets.compare_digest`. Return at most 50 recent items and no free-form query or PII fields.

- [ ] **Step 5: Run store, API, config, and redaction tests and verify GREEN**

```powershell
.\.venv\Scripts\python.exe -m pytest apps/api/tests/test_store.py apps/api/tests/test_api.py apps/api/tests/test_config.py apps/api/tests/test_redaction.py -q
```

- [ ] **Step 6: Commit judge activity**

```powershell
git add apps/api/src/changesafe/domain.py apps/api/src/changesafe/store.py apps/api/src/changesafe/api.py apps/api/src/changesafe/config.py apps/api/tests/test_store.py apps/api/tests/test_api.py apps/api/tests/test_config.py
git commit -m "feat: add privacy-limited judge activity"
```

---

### Task 5: Extend the browser contract and recovery model

**Files:**
- Modify: `apps/web/src/types.ts`
- Modify: `apps/web/src/api.ts`
- Modify: `apps/web/src/hooks/useRun.ts`
- Modify: `apps/web/tests/fixtures.ts`
- Modify: `apps/web/tests/App.test.tsx`
- Create: `apps/web/tests/api.test.ts`

**Interfaces:**
- Produces: impact and activity TypeScript contracts, `getOwnerActivity(adminToken)`, browser session header propagation, and event-history reconstruction.
- Consumes: new backend JSON models and existing SSE sequence semantics.

- [ ] **Step 1: Write failing browser-boundary tests**

Use a real `BrowserChangeSafeApi` with a stubbed `fetch` to assert `createRun` sends an opaque session header and `getOwnerActivity` sends only the owner token. Extend the refresh test so a recovered `awaiting_approval` run subscribes from sequence zero, rebuilds the seven visible process messages, deduplicates stored sequence numbers, and then stops.

- [ ] **Step 2: Run frontend tests and verify RED**

```powershell
pnpm --filter @changesafe/web test --run apps/web/tests/api.test.ts apps/web/tests/App.test.tsx
```

- [ ] **Step 3: Implement the typed browser boundary**

Generate and store `changesafe.judge-session.v1` with `crypto.randomUUID()` once per browser session. Send it in `X-ChangeSafe-Session-ID` only on run creation. Add strict TypeScript interfaces for impacts and owner activity. Update recovery to replay history from zero because only storing a cursor cannot reconstruct the transcript; keep deduplication by sequence and the existing new-run race protection.

- [ ] **Step 4: Run browser-boundary tests and verify GREEN**

```powershell
pnpm --filter @changesafe/web test --run apps/web/tests/api.test.ts apps/web/tests/App.test.tsx
```

- [ ] **Step 5: Commit browser contracts**

```powershell
git add apps/web/src/types.ts apps/web/src/api.ts apps/web/src/hooks/useRun.ts apps/web/tests/fixtures.ts apps/web/tests/App.test.tsx apps/web/tests/api.test.ts
git commit -m "feat: extend judge session browser contract"
```

---

### Task 6: Build the approved event-driven command center

**Files:**
- Modify: `apps/web/src/App.tsx`
- Modify: `apps/web/src/components/Header.tsx`
- Modify: `apps/web/src/components/ChangeForm.tsx`
- Modify: `apps/web/src/components/ImpactGraph.tsx`
- Replace: `apps/web/src/components/RiskCard.tsx` with impact-focused rendering while preserving the technical score summary
- Modify: `apps/web/src/components/RunTimeline.tsx`
- Modify: `apps/web/src/components/ArtifactExplorer.tsx`
- Modify: `apps/web/src/components/ValidationPanel.tsx`
- Modify: `apps/web/src/components/ApprovalPanel.tsx`
- Create: `apps/web/src/components/CommandRail.tsx`
- Create: `apps/web/src/components/ImpactClassification.tsx`
- Create: `apps/web/src/components/LiveProcess.tsx`
- Create: `apps/web/src/components/EvidenceDrawer.tsx`
- Modify: `apps/web/src/styles.css`
- Modify: `apps/web/tests/App.test.tsx`
- Modify: `apps/web/tests/ChangeForm.test.tsx`
- Modify: `apps/web/tests/RiskCard.test.tsx`
- Modify: `apps/web/tests/RunTimeline.test.tsx`
- Create: `apps/web/tests/ImpactGraph.test.tsx`
- Create: `apps/web/tests/ImpactClassification.test.tsx`

**Interfaces:**
- Produces: the selected dark command-center shell and accessible progressive graph/list experience.
- Consumes: real `RunView`, ordered events, impacts, context evidence, validation, artifacts, and publication state.

- [ ] **Step 1: Write failing command-center component tests**

Tests must prove:

```typescript
expect(screen.getByRole("heading", {
  name: "Change data safely, with every dependency in view.",
})).toBeVisible();
expect(screen.getByText("Official DataHub showcase-ecommerce")).toBeVisible();
expect(screen.getByText("Order Entry Analytics")).toBeVisible();
expect(screen.getByText("cust_email")).toBeVisible();
expect(screen.getByText("primary_email")).toBeVisible();
expect(screen.getAllByTestId("impact-category")).toHaveLength(6);
expect(screen.getByText("Potentially high, not quantified")).toBeVisible();
expect(screen.getByText("12 / 12")).toBeVisible();
```

Add graph tests for selecting a node, opening evidence details, keyboard activation, direct versus inferred path labels, and the accessible list alternative. Add process tests showing only reached server states are complete and fallback does not mark context as loaded.

- [ ] **Step 2: Run component tests and verify RED**

```powershell
pnpm --filter @changesafe/web test --run
```

Expected: failures identify the old light shell, old scenario copy, old five-step timeline, and missing impact/evidence components.

- [ ] **Step 3: Implement the semantic component structure**

Compose `App` as header, left change/impact rail, central graph, right process transcript, bottom command rail, then the existing artifact and approval workspace. Keep all primary controls functional. Use buttons for graph nodes, dialogs or drawers with focus management for evidence, semantic lists for steps, and visible status text in addition to color.

- [ ] **Step 4: Implement progressive data-driven behavior**

`LiveProcess` maps ordered events and the current state to the seven canonical messages. `ImpactGraph` reveals all normalized nodes when context arrives, emphasizes evidence referenced by the active impact or selected node, and never manufactures a lineage path when `lineage_path` is empty. Under reduced motion, remove path pulses and transitions without changing content.

- [ ] **Step 5: Implement the visual system from the approved concept**

Use CSS custom properties for near-black navy, cream, teal/cyan, lime approval, amber, and critical red. Recreate the three-column desktop proportions and five-stage bottom rail with standard CSS layout, not drawn assets. Icons come from Lucide. Use a freely available local/system condensed fallback stack for the display face and keep operational copy in the existing sans-serif stack. Do not place the generated concept image behind the application.

- [ ] **Step 6: Run component tests and verify GREEN**

```powershell
pnpm --filter @changesafe/web test --run
```

- [ ] **Step 7: Commit the command center**

```powershell
git add apps/web/src apps/web/tests
git commit -m "feat: build event-driven judge command center"
```

---

### Task 7: Add owner activity and safe DataHub evidence links

**Files:**
- Modify: `apps/api/src/changesafe/config.py`
- Modify: `apps/web/src/types.ts`
- Modify: `apps/web/src/api.ts`
- Modify: `apps/web/src/components/Header.tsx`
- Create: `apps/web/src/components/OwnerActivity.tsx`
- Modify: `apps/web/src/components/EvidenceDrawer.tsx`
- Modify: `apps/web/src/styles.css`
- Modify: `.env.example`
- Modify: `apps/api/tests/test_config.py`
- Modify: `apps/web/tests/Header.test.tsx`
- Create: `apps/web/tests/OwnerActivity.test.tsx`

**Interfaces:**
- Produces: optional `datahub_ui_url` public configuration, safe deep links, and an owner-token-protected activity drawer.
- Consumes: activity endpoint from Task 4 and existing publication owner token behavior.

- [ ] **Step 1: Write failing link and owner activity tests**

Assert no DataHub anchor is emitted without a configured catalog origin. With `https://datahub.example.com`, assert evidence anchors remain on that origin, encode the URN, open in a new tab, and use `rel="noreferrer"`. Owner activity tests must require a password input, keep the token only in component state, show operational session rows, and render 403 errors next to the token control.

- [ ] **Step 2: Run tests and verify RED**

```powershell
.\.venv\Scripts\python.exe -m pytest apps/api/tests/test_config.py -q
pnpm --filter @changesafe/web test --run apps/web/tests/Header.test.tsx apps/web/tests/OwnerActivity.test.tsx
```

- [ ] **Step 3: Implement explicit catalog configuration and owner activity**

Add optional `DATAHUB_UI_URL`; expose only its normalized origin. Construct links with `new URL('/dataset/' + encodeURIComponent(urn), origin)`. Add an `Owner activity` header control when the capability is available. The drawer fetches only after token submission and never persists the token in storage, URL, logs, or global state.

- [ ] **Step 4: Run config and component tests and verify GREEN**

```powershell
.\.venv\Scripts\python.exe -m pytest apps/api/tests/test_config.py -q
pnpm --filter @changesafe/web test --run apps/web/tests/Header.test.tsx apps/web/tests/OwnerActivity.test.tsx
```

- [ ] **Step 5: Commit owner controls**

```powershell
git add apps/api/src/changesafe/config.py apps/api/tests/test_config.py apps/web/src apps/web/tests .env.example
git commit -m "feat: add owner activity and evidence links"
```

---

### Task 8: Align generated examples, docs, deployment guidance, and E2E proof

**Files:**
- Modify: `scripts/regenerate_examples.py`
- Modify: `examples/generated-safe-change/**`
- Modify: `fixtures/dbt_project/**`
- Modify: `README.md`
- Modify: `docs/architecture.md`
- Modify: `docs/demo-script.md`
- Modify: `docs/devpost-submission.md`
- Modify: `docs/design/changesafe-design-system.md`
- Modify: `tests/e2e/golden-flow.spec.ts`
- Modify: `tests/e2e/capture-screenshots.spec.ts`
- Replace: `docs/screenshots/changesafe-desktop-replay.png`
- Replace: `docs/screenshots/changesafe-mobile-replay.png`
- Create: `docs/shared-sandbox-runbook.md`

**Interfaces:**
- Produces: current seven-file examples, judge instructions, environment-value source guide, shared deployment runbook, and visual evidence.
- Consumes: official scenario, final UI, preview/live truth labels, current repository commands.

- [ ] **Step 1: Write failing E2E expectations for the approved story**

Update the golden flow to assert the headline, official datapack badge, `order_details`, six impact categories, progressive completion, seven artifacts, twelve checks, approval stop, preview receipt, and no horizontal phone overflow. Keep console-error collection.

- [ ] **Step 2: Run E2E and verify RED against the pre-documentation build**

```powershell
pnpm test:e2e
```

- [ ] **Step 3: Regenerate deterministic outputs for `order_details`**

Make `DBT_FIXTURE_PATHS` derive from `expected_artifact_paths()` rather than hard-coded `dim_customers` paths, then run:

```powershell
.\.venv\Scripts\python.exe scripts/regenerate_examples.py
.\.venv\Scripts\python.exe scripts/regenerate_examples.py --check
```

- [ ] **Step 4: Rewrite judge and operator documentation**

Document the official datapack command, replay-first judge flow, optional live credentials, the exact source of every `changesafe.env` value, owner activity, shared sandbox controls, DataHub token necessity by mode, GitHub sandbox behavior, truthful limitations, and the under-three-minute narrative. Remove old scenario and rejected product copy throughout tracked text.

- [ ] **Step 5: Run E2E and regenerate screenshots**

Run the app with deterministic replay data, execute Playwright, then run the existing screenshot script for the same desktop and mobile states. Inspect both images for readable copy, current twelve-check count, correct provenance, and no clipped panels.

- [ ] **Step 6: Commit examples and public evidence**

```powershell
git add scripts/regenerate_examples.py examples fixtures/dbt_project README.md docs tests/e2e
git commit -m "docs: align judge proof with ecommerce scenario"
```

---

### Task 9: Perform visual QA, create the implementation-matched Figma file, and close all gates

**Files:**
- Create: `design-qa.md`
- Create or update: implementation-matched Figma file through the configured Figma integration
- Modify: source or tests only for issues proven by QA or failing gates

**Interfaces:**
- Produces: passed visual comparison report, desktop/mobile Figma frames, complete test evidence, and a clean release commit.
- Consumes: selected reference `docs/design/changesafe-judge-command-center-v1.png` and final running app.

- [ ] **Step 1: Start the verified local application**

Use the existing full-stack development workflow and keep the preview running. Confirm `/healthz` and the replay workflow before visual comparison.

- [ ] **Step 2: Capture the exact comparison state**

At 1440×1024, capture the run at `awaiting_approval` with five completed safety stages, active owner authorization, six impact categories, and the dependency graph. Capture a 430×932 mobile state as well.

- [ ] **Step 3: Run blocking design QA**

Compare the selected concept and implementation at the same state and viewport. Write `design-qa.md` with severity-ranked differences, fix all P0/P1/P2 issues test-first, recapture, and repeat until the report ends with exactly `final result: passed`. P3 polish may remain only as explicitly documented follow-up.

- [ ] **Step 4: Create implementation-matched Figma frames**

Create desktop awaiting-approval, desktop completion/failure, and mobile active-run frames from the implemented tokens and components. Add component variants for impact, process, node, validation, approval, and receipt states, plus annotations mapping UI states to backend events.

- [ ] **Step 5: Run the complete repository gate**

```powershell
.\.venv\Scripts\python.exe -m ruff check --no-cache .
.\.venv\Scripts\python.exe -m mypy apps/api/src scripts
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts/regenerate_examples.py --check
.\.venv\Scripts\python.exe scripts/check_secrets.py
pnpm --filter @changesafe/web lint
pnpm --filter @changesafe/web typecheck
pnpm --filter @changesafe/web test --run
pnpm --filter @changesafe/web build
pnpm test:e2e
.\.venv-dbt\Scripts\dbt.exe parse --project-dir fixtures/dbt_project --profiles-dir fixtures/dbt_project
.\.venv-dbt\Scripts\dbt.exe build --project-dir fixtures/dbt_project --profiles-dir fixtures/dbt_project
git diff --check
git status --short
```

Expected: every command exits zero, generated examples match, browser console is clean, dbt passes, and only intentional tracked files remain.

- [ ] **Step 6: Commit final QA corrections**

```powershell
git add design-qa.md apps docs examples fixtures scripts tests README.md .env.example
git commit -m "test: verify redesigned judge experience"
```

- [ ] **Step 7: Push `master` and verify GitHub**

```powershell
git push origin master
git status --short
```

Confirm the remote commit, repository visibility, README rendering, Apache 2.0 license, and CI status before handoff.
