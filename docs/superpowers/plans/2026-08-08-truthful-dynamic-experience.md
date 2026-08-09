# ChangeSafe Truthful Dynamic Experience Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make ChangeSafe's replay, impact findings, dependency flow, generated artifacts, and run timing feel dynamic and professional while remaining technically truthful and reproducible.

**Architecture:** Keep the existing FastAPI orchestration, persisted SSE events, deterministic classifier/generator/verifier, and React command-center shell. Add focused presentation helpers for change drafts, provenance, elapsed timing, and artifact explanations; make the current components consume the immutable run request after submission and real event order throughout the workflow.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, pytest, React 19, TypeScript 6, Vitest, Testing Library, Lucide React, CSS, Vite, dbt Core with DuckDB, and the existing in-app Browser workflow.

## Global Constraints

- No artificial processing delay, random score, or fabricated live DataHub activity.
- The hero's structure and size remain stable before and after analysis.
- Public UI copy contains no `judge`, `judge-ready`, or competition-preparation language.
- Recorded evidence is named **Recorded DataHub evidence** and explains its checksum-backed, read-only behavior.
- Identical request plus identical evidence is explicitly described as a reproducible result.
- Motion illustrates lineage direction; persisted server events remain the only source of run progress.
- Directional motion has a `prefers-reduced-motion` equivalent.
- Impact categories are computed findings; only the supporting-evidence action is interactive.
- Rename, Remove, and Type change render operation-specific copy and deterministic artifacts.
- The removal guard keeps `where false` and explains its dbt zero-row/compile-failure semantics.
- No new graph framework, animation package, route, data store, or source dataset is introduced.
- Owner gating, mutation allowlists, durable publication recovery, and server-side secrets remain unchanged.
- Final visual verification uses the user's selected in-app Browser; Playwright CLI is run only after explicit user permission.

---

### Task 1: Neutralize public session and request identity

**Files:**
- Modify: `apps/api/src/changesafe/domain.py`
- Modify: `apps/api/src/changesafe/store.py`
- Modify: `apps/api/src/changesafe/api.py`
- Modify: `apps/api/src/changesafe/demo.py`
- Modify: `apps/api/tests/test_store.py`
- Modify: `apps/api/tests/test_api.py`
- Modify: `examples/generated-safe-change/changesafe-manifest.json`
- Modify: `apps/web/src/api.ts`
- Modify: `apps/web/src/types.ts`
- Modify: `apps/web/src/components/OwnerActivity.tsx`
- Modify: `apps/web/tests/api.test.ts`
- Modify: `apps/web/tests/OwnerActivity.test.tsx`

**Interfaces:**
- Produces: `ReviewActivity`, neutral `session-<8 hex>` labels, and public **Review activity** copy.
- Preserves: `GET /api/owner/activity`, `X-ChangeSafe-Session-ID`, privacy limits, and the JSON response field names.

- [ ] **Step 1: Write failing backend neutral-label tests**

Update the recent-activity assertion and add a response-copy assertion:

```python
activity = await store.recent_activity()
assert activity[0].session_label.startswith("session-")
assert "judge" not in activity[0].model_dump_json().casefold()
```

Add an API validation assertion that malformed session IDs produce `Session ID must be a 16-128 character opaque value.`

- [ ] **Step 2: Run the focused backend tests and confirm failure**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest apps/api/tests/test_store.py apps/api/tests/test_api.py -q
```

Expected: failures reference the existing `judge-` session label and `Judge session ID` detail.

- [ ] **Step 3: Implement neutral backend terminology**

Rename the internal response model to `ReviewActivity` and use this field contract:

```python
class ReviewActivity(StrictModel):
    run_id: str
    session_label: str = Field(pattern=r"^session-(?:[0-9a-f]{8}|unassigned)$")
    scenario: str = Field(min_length=1)
    state: RunState
    context_mode: ContextMode | None = None
    publication_mode: Literal["live", "preview"] | None = None
    created_at: datetime
    updated_at: datetime
```

Change `RunStore.recent_activity()` to compute `session-<hash>` or `session-unassigned`, change the API validation detail to neutral copy, and change `golden_change().requested_by` from `judge-demo` to `changesafe-demo`.

- [ ] **Step 4: Write failing frontend review-activity tests**

Rename the TypeScript shape to `ReviewActivity`, set the API fixture label to
`session-7a31f0`, and assert the component's human-readable rendering:

```tsx
expect(screen.getByRole("heading", { name: "Review activity" })).toBeVisible();
expect(await screen.findByText("Session 7A31F0")).toBeVisible();
expect(screen.queryByText(/judge/i)).not.toBeInTheDocument();
```

Keep the session-storage value opaque; rename the exported constant to `REVIEW_SESSION_KEY` while retaining the existing stored key string for browser-session continuity.

- [ ] **Step 5: Run the focused frontend tests and confirm failure**

Run:

```powershell
pnpm --filter @changesafe/web test --run tests/api.test.ts tests/OwnerActivity.test.tsx
```

Expected: failures identify `Judge activity`, `No judge sessions`, and the old TypeScript name.

- [ ] **Step 6: Implement the neutral frontend copy and types**

Use `ReviewActivity` through `types.ts`, `api.ts`, and `OwnerActivity.tsx`.
Format `session-7a31f0` as `Session 7A31F0` only at the presentation boundary.
Render `Review activity`, `Private review view`, and `No review sessions have
been recorded yet.` Keep the owner-token authorization and privacy explanation
unchanged in meaning.

- [ ] **Step 7: Re-run focused tests**

Regenerate the deterministic example after changing the canonical requester, then
run both commands from Steps 2 and 5 plus the checked-in generation proof:

```powershell
.\.venv\Scripts\python.exe scripts/regenerate_examples.py
.\.venv\Scripts\python.exe scripts/regenerate_examples.py --check
.\.venv\Scripts\python.exe -m pytest apps/api/tests/test_generation.py -q
```

Expected: all focused tests and deterministic byte checks pass.

- [ ] **Step 8: Commit the neutral terminology**

```powershell
git add apps/api/src/changesafe/domain.py apps/api/src/changesafe/store.py apps/api/src/changesafe/api.py apps/api/src/changesafe/demo.py apps/api/tests/test_store.py apps/api/tests/test_api.py apps/web/src/api.ts apps/web/src/types.ts apps/web/src/components/OwnerActivity.tsx apps/web/tests/api.test.ts apps/web/tests/OwnerActivity.test.tsx examples/generated-safe-change/changesafe-manifest.json
git commit -m "fix: use neutral review terminology"
```

---

### Task 2: Make impact summaries operation-specific

**Files:**
- Modify: `apps/api/src/changesafe/impact.py`
- Modify: `apps/api/tests/test_impact.py`
- Modify: `apps/web/tests/fixtures.ts`

**Interfaces:**
- Consumes: `ChangeRequest`, `ContextBundle`.
- Produces: the existing six `ImpactAssessment` objects with operation-correct `summary` strings and unchanged evidence/confidence semantics.

- [ ] **Step 1: Add failing tests for all supported operations**

Add a parametrized asynchronous test using these complete requests and expected
action phrases:

```python
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("change", "phrase"),
    [
        (golden_change(), "Renaming cust_email to primary_email"),
        (
            ChangeRequest(
                asset_urn=golden_change().asset_urn,
                operation=ChangeOperation.REMOVE,
                field="cust_email",
                source_commit="showcase-ecommerce-safe-remove",
                requested_by="changesafe-demo",
            ),
            "Removing cust_email",
        ),
        (
            ChangeRequest(
                asset_urn=golden_change().asset_urn,
                operation=ChangeOperation.TYPE_CHANGE,
                field="cust_email",
                old_type="TEXT",
                new_type="VARCHAR(320)",
                source_commit="showcase-ecommerce-safe-type-change",
                requested_by="changesafe-demo",
            ),
            "Changing cust_email from TEXT to VARCHAR(320)",
        ),
    ],
)
async def test_impact_summaries_name_the_requested_operation(change, phrase):
    context = await ReplayDataHubContext.from_default().load(change)
    impacts = classify_impacts(change, context)
    assert all(phrase in impact.summary for impact in impacts)
    if change.operation is not ChangeOperation.RENAME:
        assert all("during the rename" not in impact.summary for impact in impacts)
```

- [ ] **Step 2: Run the impact tests and confirm failure**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest apps/api/tests/test_impact.py -q
```

Expected: current generic summaries and the hardcoded operational `rename` sentence fail.

- [ ] **Step 3: Add one shared action formatter**

Implement:

```python
def _change_action(change: ChangeRequest, context: ContextBundle) -> str:
    if change.operation is ChangeOperation.RENAME:
        return f"Renaming {change.field} to {change.new_field}"
    if change.operation is ChangeOperation.TYPE_CHANGE:
        old_type = change.old_type or context.field_type
        return f"Changing {change.field} from {old_type} to {change.new_type}"
    return f"Removing {change.field}"
```

Start each category summary with `_change_action(change, context)` and retain the
current direct/inferred/unavailable distinctions. The financial summary must still
say metadata cannot establish a monetary amount.

- [ ] **Step 4: Align the frontend fixture copy**

Update all six fixture summaries so component tests exercise the new operation-specific response shape. Do not change fixture severities or evidence URNs.

- [ ] **Step 5: Re-run impact and orchestrator tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest apps/api/tests/test_impact.py apps/api/tests/test_orchestrator.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit the impact correction**

```powershell
git add apps/api/src/changesafe/impact.py apps/api/tests/test_impact.py apps/web/tests/fixtures.ts
git commit -m "fix: align impact copy with each operation"
```

---

### Task 3: Clarify the removal guard and verifier result

**Files:**
- Modify: `apps/api/src/changesafe/generation/templates.py`
- Modify: `apps/api/src/changesafe/verification.py`
- Modify: `apps/api/tests/test_generation.py`
- Modify: `apps/api/tests/test_verification.py`
- Modify: `examples/generated-safe-change/changesafe-manifest.json`
- Modify: generated example files changed by `scripts/regenerate_examples.py`

**Interfaces:**
- Produces: exact two-line removal-guard explanation and operation-specific `compatibility_test` validation label/detail.
- Preserves: `where false`, the seven-file allowlist, SQL parsing, hashes, and publication eligibility.

- [ ] **Step 1: Add an exact failing removal-guard test**

Assert the generated test is exactly:

```python
assert bundle.files["tests/assert_cust_email_retained.sql"].content == (
    "-- Phase-one safety guard: dbt passes because this query returns zero rows.\n"
    "-- If cust_email is removed too early, compilation fails before publication.\n"
    "select cust_email\n"
    "from {{ ref('order_details') }}\n"
    "where false\n"
)
```

- [ ] **Step 2: Add a failing verifier-label test**

For a Remove request, assert:

```python
check = verify_artifacts(bundle, change, context).check("compatibility_test")
assert check.label == "Phase-one field remains available"
assert "compiles only while cust_email exists" in check.detail
```

For Rename and Type change, retain `Compatibility test compares old and new values`.

- [ ] **Step 3: Run focused generation and verification tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest apps/api/tests/test_generation.py apps/api/tests/test_verification.py -q
```

Expected: both new assertions fail against the cryptic comment and generic label.

- [ ] **Step 4: Implement the template and verifier branches**

Return the exact SQL from Step 1 for Remove. In `verify_artifacts`, branch label, pass detail, and fail detail on `ChangeOperation.REMOVE`; keep the existing comparison logic for Rename and Type change.

- [ ] **Step 5: Regenerate deterministic examples**

Run:

```powershell
.\.venv\Scripts\python.exe scripts/regenerate_examples.py
.\.venv\Scripts\python.exe scripts/regenerate_examples.py --check
```

Expected: regeneration updates the neutral `requested_by` manifest value and the check command succeeds.

- [ ] **Step 6: Run dbt and focused Python validation**

Run:

```powershell
.\.venv-dbt\Scripts\dbt.exe parse --project-dir fixtures/dbt_project --profiles-dir fixtures/dbt_project
.\.venv-dbt\Scripts\dbt.exe build --project-dir fixtures/dbt_project --profiles-dir fixtures/dbt_project
.\.venv\Scripts\python.exe -m pytest apps/api/tests/test_generation.py apps/api/tests/test_verification.py -q
```

Expected: dbt parse/build and all focused tests pass.

- [ ] **Step 7: Commit artifact truth improvements**

```powershell
git add apps/api/src/changesafe/generation/templates.py apps/api/src/changesafe/verification.py apps/api/tests/test_generation.py apps/api/tests/test_verification.py examples/generated-safe-change
git commit -m "fix: explain phase-one removal safety guard"
```

---

### Task 4: Centralize the change draft and scenario copy

**Files:**
- Create: `apps/web/src/changeDraft.ts`
- Create: `apps/web/tests/changeDraft.test.ts`
- Modify: `apps/web/src/components/ChangeForm.tsx`
- Modify: `apps/web/src/App.tsx`
- Modify: `apps/web/tests/ChangeForm.test.tsx`
- Modify: `apps/web/tests/App.test.tsx`

**Interfaces:**
- Produces: `ChangeDraft`, `DEFAULT_CHANGE_DRAFT`, `sourceCommitForOperation(operation)`, `draftToRequest(draft)`, and `changeSummary(change)`.
- Produces: controlled `ChangeForm` props `draft`, `onDraftChange`, `onSubmit`, and `submittedRequest`.
- Consumes: the immutable `run.request` after submission or restoration.

- [ ] **Step 1: Write failing draft-helper tests**

Cover all operations:

```ts
expect(changeSummary({ ...DEFAULT_CHANGE_DRAFT, operation: "rename" })).toBe(
  "Keep cust_email available while consumers move to primary_email.",
);
expect(changeSummary({ ...DEFAULT_CHANGE_DRAFT, operation: "remove" })).toBe(
  "Delay removal of cust_email until every recorded consumer has migrated.",
);
expect(
  changeSummary({ ...DEFAULT_CHANGE_DRAFT, operation: "type_change" }),
).toBe(
  "Keep cust_email and add a safely cast VARCHAR(320) compatibility field during phase one.",
);
```

Assert `draftToRequest` nulls irrelevant fields and uses `requested_by: "changesafe-web"`.

- [ ] **Step 2: Run the helper test and confirm failure**

Run:

```powershell
pnpm --filter @changesafe/web test --run tests/changeDraft.test.ts
```

Expected: the module does not exist.

- [ ] **Step 3: Implement the typed draft helpers**

Use this shape:

```ts
export interface ChangeDraft {
  asset_urn: string;
  operation: ChangeOperation;
  field: string;
  new_field: string;
  old_type: string;
  new_type: string;
  source_commit: string;
}
```

Use operation-specific default commits:

```ts
const OPERATION_COMMITS = {
  rename: "showcase-ecommerce-safe-rename",
  remove: "showcase-ecommerce-safe-remove",
  type_change: "showcase-ecommerce-safe-type-change",
} satisfies Record<ChangeOperation, string>;
```

- [ ] **Step 4: Write failing controlled-form tests**

Render `ChangeForm` with a controlled draft, select Remove, and assert `onDraftChange` receives `operation: "remove"` plus `showcase-ecommerce-safe-remove`. Add a Type change assertion for the operation-specific intro. Assert the submitted request summary comes from `submittedRequest`, not the current editable draft.

- [ ] **Step 5: Convert ChangeForm to controlled state**

Remove its seven local request-field states. All input handlers call `onDraftChange`. Submit calls `onSubmit(draftToRequest(draft))`. Render dynamic guidance from `changeSummary`, and display the immutable `submittedRequest` when present.

- [ ] **Step 6: Write a failing application integration test**

Before analysis, select Remove and assert the central state contains:

```tsx
expect(
  screen.getByText(
    "Delay removal of cust_email until every recorded consumer has migrated.",
  ),
).toBeVisible();
expect(screen.queryByText("Official judge scenario ready")).not.toBeInTheDocument();
```

- [ ] **Step 7: Lift the draft into App**

Store `DEFAULT_CHANGE_DRAFT` in `App`, pass it to `ChangeForm`, and render
`changeSummary(run?.request ?? draft)` in the central ready state. Define
`changeSummary` against the shared snake-case subset `operation`, `field`,
`new_field`, and `new_type`, allowing the editable draft and immutable request to
use the same formatter. Replace the eyebrow with `Ready to trace this change`.
Pass `run.request.field` to analyzed components so later form edits cannot change
a submitted run.

- [ ] **Step 8: Run the focused frontend tests**

Run:

```powershell
pnpm --filter @changesafe/web test --run tests/changeDraft.test.ts tests/ChangeForm.test.tsx tests/App.test.tsx
```

Expected: all focused tests pass.

- [ ] **Step 9: Commit shared scenario state**

```powershell
git add apps/web/src/changeDraft.ts apps/web/src/components/ChangeForm.tsx apps/web/src/App.tsx apps/web/tests/changeDraft.test.ts apps/web/tests/ChangeForm.test.tsx apps/web/tests/App.test.tsx
git commit -m "fix: make scenario copy follow the request"
```

---

### Task 5: Add stable, explanatory run provenance

**Files:**
- Create: `apps/web/src/components/RunProvenance.tsx`
- Create: `apps/web/tests/RunProvenance.test.tsx`
- Modify: `apps/web/src/components/Header.tsx`
- Modify: `apps/web/src/App.tsx`
- Modify: `apps/web/tests/Header.test.tsx`
- Modify: `apps/web/tests/App.test.tsx`
- Modify: `apps/web/src/styles.css`

**Interfaces:**
- Produces: `RunProvenance({ config, run, busy })` and `formatElapsed(milliseconds)`.
- Preserves: restored live-publication truth in approval controls; the header no longer owns provenance labels.

- [ ] **Step 1: Write failing provenance tests**

For a snapshot run created at `20:00:00.000Z` and updated at `20:00:00.280Z`, assert:

```tsx
expect(screen.getByText("Recorded DataHub evidence")).toBeVisible();
expect(screen.getByText("Preview only")).toBeVisible();
expect(screen.getByText("Completed in 0.28 seconds")).toBeVisible();
expect(screen.getByText("Same request + same evidence = same verified result.")).toBeVisible();
expect(screen.getByText(/^bbbbbbbb/)).toBeVisible();
```

Assert the status values are not buttons. Expand **About this run** and assert the checksum/read-only explanation is visible.

- [ ] **Step 2: Run the provenance test and confirm failure**

Run:

```powershell
pnpm --filter @changesafe/web test --run tests/RunProvenance.test.tsx
```

Expected: the component does not exist.

- [ ] **Step 3: Implement truthful provenance and elapsed formatting**

Use `run.created_at` and `run.updated_at` for completed analysis. While a nonterminal run is busy, update elapsed display from `Date.now()` at 100 ms intervals and clear the interval on completion/unmount. Format below one second to two decimals, one to ten seconds to one decimal, and longer durations as whole seconds.

Render provenance as a `<dl>` with `Evidence`, `Publication`, `Elapsed`, and `Evidence ID`. The only controls are a checksum copy button and the **About this run** disclosure.

- [ ] **Step 4: Simplify the Header**

Remove the pseudo-button `.environment-status` group. Keep the brand and a real **Review activity** button only when enabled. Update `Header` props to:

```ts
interface HeaderProps {
  reviewActivityAvailable: boolean;
  onOpenReviewActivity?: () => void;
}
```

- [ ] **Step 5: Keep the hero stable in App**

Remove `is-compact` from the hero class, place `RunProvenance` below the hero
message, and update supporting copy to `prepare a compatible migration` and
`pause before anything is published`. Remove the environment aside that
duplicates the provenance facts. Replace footer `Environment: REPLAY` with the
neutral `Evidence source: Recorded snapshot` or `Evidence source: Live DataHub`,
derived from the immutable analysis provenance.

- [ ] **Step 6: Update header and app tests**

Assert no element contains `Snapshot replay` or `Preview only / snapshot mode`. Assert `.product-hero` has the same class before and after Analyze and never has `is-compact`.

- [ ] **Step 7: Implement stable responsive hero CSS**

Delete `.product-hero.is-compact` rules and the fixed `padding-left: 260px`. Use an explicit responsive grid for the existing brand mark/copy and provenance facts. At 1260 px and below, switch to a single copy column without horizontal overflow.

- [ ] **Step 8: Run focused frontend tests**

Run:

```powershell
pnpm --filter @changesafe/web test --run tests/RunProvenance.test.tsx tests/Header.test.tsx tests/App.test.tsx
```

Expected: all focused tests pass without fake timers leaking.

- [ ] **Step 9: Commit stable provenance and hero**

```powershell
git add apps/web/src/components/RunProvenance.tsx apps/web/src/components/Header.tsx apps/web/src/App.tsx apps/web/src/styles.css apps/web/tests/RunProvenance.test.tsx apps/web/tests/Header.test.tsx apps/web/tests/App.test.tsx
git commit -m "feat: explain recorded evidence truthfully"
```

---

### Task 6: Turn impact choices into evidence-backed findings

**Files:**
- Modify: `apps/web/src/components/ImpactClassification.tsx`
- Modify: `apps/web/src/App.tsx`
- Modify: `apps/web/tests/ImpactClassification.test.tsx`
- Modify: `apps/web/tests/App.test.tsx`
- Modify: `apps/web/src/styles.css`

**Interfaces:**
- Produces: `ImpactClassification({ impacts, active, onTrace })`.
- Produces: non-interactive finding articles and one dedicated trace/hide evidence button per category.

- [ ] **Step 1: Replace the old selection test with failing finding semantics**

Assert:

```tsx
expect(screen.getAllByRole("article")).toHaveLength(6);
expect(screen.queryByRole("button", { name: "Financial exposure" })).not.toBeInTheDocument();
expect(
  screen.getByRole("button", {
    name: "Trace supporting evidence for Financial exposure",
  }),
).toBeVisible();
expect(screen.getByText(impacts[4].summary)).toBeVisible();
expect(screen.getByText(impacts[4].basis)).toBeVisible();
```

Click the trace button and assert `onTrace(impacts[4])`.

- [ ] **Step 2: Run the focused test and confirm failure**

Run:

```powershell
pnpm --filter @changesafe/web test --run tests/ImpactClassification.test.tsx
```

Expected: the whole card is still a pressed button and summary/basis are absent.

- [ ] **Step 3: Implement finding-card markup**

Render each item as `<article data-testid="impact-category">`. Show label,
severity, confidence, summary, basis, and qualifier. Add the footnote `The six
categories are fixed; severity, confidence, and evidence are computed for this
request.` The trace button uses `aria-expanded={active}` and changes its text to
**Hide supporting evidence for …** when active; it never uses `aria-pressed`.

- [ ] **Step 4: Implement evidence toggle ownership in App**

Replace direct `setSelectedImpact` with:

```ts
const traceImpact = (impact: ImpactAssessment) => {
  setSelectedImpact((current) =>
    current?.category === impact.category ? null : impact,
  );
};
```

Clear a selected category when a new run starts or its category is absent from the immutable analysis.

- [ ] **Step 5: Restyle findings**

Remove selected-input styling. Give the article a stable severity edge, readable summary/basis hierarchy, and a visibly secondary evidence button. Preserve WCAG AA contrast and 44 px touch targets.

- [ ] **Step 6: Run focused tests**

Run:

```powershell
pnpm --filter @changesafe/web test --run tests/ImpactClassification.test.tsx tests/App.test.tsx
```

Expected: all focused tests pass.

- [ ] **Step 7: Commit impact interaction improvements**

```powershell
git add apps/web/src/components/ImpactClassification.tsx apps/web/src/App.tsx apps/web/src/styles.css apps/web/tests/ImpactClassification.test.tsx apps/web/tests/App.test.tsx
git commit -m "feat: present impacts as computed findings"
```

---

### Task 7: Build directional evidence flow without fake progress

**Files:**
- Modify: `apps/web/src/components/ImpactGraph.tsx`
- Modify: `apps/web/src/App.tsx`
- Modify: `apps/web/tests/ImpactGraph.test.tsx`
- Modify: `apps/web/src/styles.css`

**Interfaces:**
- Produces: `ImpactGraph({ context, request, activeImpact, dataHubOrigin })`.
- Produces: two `data-testid="lineage-flow"` rails, direct/multi-hop labels, active evidence filtering, and unchanged evidence drawer behavior.

- [ ] **Step 1: Add failing directional-flow tests**

Assert:

```tsx
expect(screen.getAllByTestId("lineage-flow")).toHaveLength(2);
expect(screen.getByRole("heading", { name: "Tracing what depends on cust_email" })).toBeVisible();
expect(screen.getByText("Showing evidence for Data integrity")).toBeVisible();
expect(screen.getByRole("button", { name: /ORDER_DETAILS, dataset, direct evidence/ })).toBeVisible();
expect(screen.getByRole("button", { name: /Customer Analytics Measures.*multi-hop evidence/ })).toBeVisible();
```

Assert an unrelated node receives `is-dimmed` only while an impact filter is active.

- [ ] **Step 2: Run the graph test and confirm failure**

Run:

```powershell
pnpm --filter @changesafe/web test --run tests/ImpactGraph.test.tsx
```

Expected: static arrow containers do not satisfy the flow/filter assertions.

- [ ] **Step 3: Implement semantic flow rails**

Replace each `map-direction` with:

```tsx
<div className="lineage-flow" data-testid="lineage-flow" aria-hidden="true">
  <span className="lineage-flow-light" />
  <ArrowRight />
</div>
```

Use `request.field` in the heading. Add `is-highlighted` and `is-dimmed` from `activeImpact.evidence_urns`, and render the active-filter sentence above the map.

- [ ] **Step 4: Animate relationship direction in CSS**

Create a horizontal rail with an animated teal highlight travelling left to right. Keep the arrowhead visible without animation. Under the existing `@media (prefers-reduced-motion: reduce)`, set animation to `none` and display a static gradient plus arrowhead.

At the 980 px stacked layout, rotate the rail to a vertical top-to-bottom path and keep labels in logical DOM order.

- [ ] **Step 5: Preserve evidence interaction tests**

Re-run keyboard drawer and safe DataHub-link assertions. Add a test with `activeImpact={null}` proving no cards are dimmed.

- [ ] **Step 6: Run focused tests**

Run:

```powershell
pnpm --filter @changesafe/web test --run tests/ImpactGraph.test.tsx tests/App.test.tsx
```

Expected: all graph and application tests pass.

- [ ] **Step 7: Commit directional evidence flow**

```powershell
git add apps/web/src/components/ImpactGraph.tsx apps/web/src/App.tsx apps/web/src/styles.css apps/web/tests/ImpactGraph.test.tsx
git commit -m "feat: animate the direction of data dependencies"
```

---

### Task 8: Make timing and generated artifacts understandable

**Files:**
- Create: `apps/web/src/artifactCatalog.ts`
- Create: `apps/web/tests/artifactCatalog.test.ts`
- Create: `apps/web/tests/ArtifactExplorer.test.tsx`
- Modify: `apps/web/src/components/ArtifactExplorer.tsx`
- Modify: `apps/web/src/components/RunTimeline.tsx`
- Modify: `apps/web/src/App.tsx`
- Modify: `apps/web/tests/RunTimeline.test.tsx`
- Modify: `apps/web/src/styles.css`

**Interfaces:**
- Produces: `artifactExplanation(path): { label; purpose; prevents }` with seven known categories and a safe generic fallback.
- Produces: `RunTimeline({ events, runState, field })` with sequence-relative timing.

- [ ] **Step 1: Write failing artifact-catalog tests**

Cover all path patterns and unknown files:

```ts
expect(artifactExplanation("models/marts/order_details.sql").label).toBe("dbt model SQL");
expect(artifactExplanation("tests/assert_cust_email_retained.sql").prevents).toContain("premature removal");
expect(artifactExplanation("changesafe-manifest.json").prevents).toContain("substitution");
expect(artifactExplanation("notes/custom.txt").label).toBe("Generated file");
```

- [ ] **Step 2: Implement the artifact catalog**

Use ordered path predicates for model SQL, model YAML, tests, migrations, `ROLLBACK.md`, `PR_BODY.md`, and `changesafe-manifest.json`. Return immutable strings matching the approved specification.

- [ ] **Step 3: Write a failing ArtifactExplorer component test**

Render the golden bundle, assert **What this file does** and **Failure this prevents**, select the removal test fixture, and verify the explanation changes with the selected path while exact source bytes remain in the code panel.

- [ ] **Step 4: Implement artifact explanations**

Add a concise explanation block between the code-inspector header and `<pre>`. Keep code escaped as text, the hash visible, and copy behavior unchanged.

- [ ] **Step 5: Write failing sequence-relative timeline tests**

Use events at `00.000Z`, `00.024Z`, and `00.280Z`. Assert timeline metadata includes `Event 02 · +24 ms` and `Event 03 · +280 ms`. With identical timestamps, assert sequence numbers still distinguish the events. Pass `field="cust_email"` and assert the field-aware step label.

- [ ] **Step 6: Implement truthful timeline timing**

Derive offsets from the first valid event timestamp. Format missing/invalid timestamps as `Event NN` without a duration. Keep interruption logic and never mark a fallback context load complete. Use `field` in dependency-discovery copy.

- [ ] **Step 7: Run focused tests**

Run:

```powershell
pnpm --filter @changesafe/web test --run tests/artifactCatalog.test.ts tests/ArtifactExplorer.test.tsx tests/RunTimeline.test.tsx tests/App.test.tsx
```

Expected: all focused tests pass.

- [ ] **Step 8: Commit timing and artifact explanations**

```powershell
git add apps/web/src/artifactCatalog.ts apps/web/src/components/ArtifactExplorer.tsx apps/web/src/components/RunTimeline.tsx apps/web/src/App.tsx apps/web/src/styles.css apps/web/tests/artifactCatalog.test.ts apps/web/tests/ArtifactExplorer.test.tsx apps/web/tests/RunTimeline.test.tsx apps/web/tests/App.test.tsx
git commit -m "feat: explain run timing and generated files"
```

---

### Task 9: Integrate responsive polish, browser proof, and public documentation

**Files:**
- Modify: `apps/web/src/styles.css`
- Modify: `apps/web/tests/App.test.tsx`
- Modify: `tests/e2e/golden-flow.spec.ts`
- Modify: `tests/e2e/capture-screenshots.spec.ts`
- Modify: `README.md`
- Modify: `docs/demo-script.md`
- Modify: `docs/devpost-submission.md`
- Modify: `docs/design/changesafe-design-system.md`
- Modify: `docs/screenshots/changesafe-desktop-replay.png`
- Modify: `docs/screenshots/changesafe-mobile-replay.png`
- Modify: `design-qa.md`

**Interfaces:**
- Consumes: the completed truthful UI and existing local API at the configured development origin.
- Produces: contained 1440 px, 1280 px, and mobile layouts; current public screenshots; and implementation-matched documentation.

- [ ] **Step 1: Add final integrated UI assertions**

In `App.test.tsx`, assert the analyzed replay contains **Recorded DataHub evidence**, **Completed in**, **Same request + same evidence**, six finding articles, two lineage-flow rails, seven explained artifacts, and no visible `/judge/i` text.

- [ ] **Step 2: Update end-to-end assertions without running the Playwright CLI**

Replace old snapshot/header strings in `golden-flow.spec.ts` with the new provenance, stable hero, `12 / 12`, artifact explanation, and preview-receipt assertions. Update screenshot capture waits to use the new completed provenance text. Running these files locally remains gated by explicit user permission; CI will execute them after push.

- [ ] **Step 3: Finish responsive CSS**

At 1440 px and 1280 px, keep the headline, facts, three workspace regions, and artifact panel within the viewport. At 980 px and below, stack in task order. At 430 px, preserve 44 px touch targets, readable code scrolling inside its own panel, and no page-level horizontal overflow.

- [ ] **Step 4: Search and correct stale public copy**

Run:

```powershell
rg -n "Snapshot replay|Preview only / snapshot mode|Official judge scenario ready|Judge activity|No judge sessions|Environment:.*REPLAY|Propose the rename" apps/web/src README.md docs/demo-script.md docs/devpost-submission.md docs/design/changesafe-design-system.md tests/e2e
```

Expected: no stale public-interface wording remains. Documentation may use `judge` only when discussing the actual Devpost audience, never as an in-product label.

- [ ] **Step 5: Verify the current application in the in-app Browser**

Inspect the empty Rename, Remove, and Type change states; analyze a replay; trace an impact; open direct and multi-hop evidence; inspect multiple artifact explanations; approve preview; and restore the completed run. Repeat layout inspection at 1440 px, 1280 px, and the existing mobile viewport. Confirm no console errors, clipped hero, false buttons, or page-level horizontal overflow.

- [ ] **Step 6: Capture current desktop and mobile screenshots**

Use the in-app Browser's current rendered state to replace both files under `docs/screenshots`. The desktop capture must show the stable hero, recorded-evidence facts, computed findings, animated-direction rails in their static captured frame, 12 checks, and approval gate. The mobile capture must show contained content and the same provenance truth.

- [ ] **Step 7: Update documentation and design QA**

Explain recorded evidence, deterministic repeated results, true sub-second timing, the removal compile guard, artifact explanations, and the neutral Review activity view. In `design-qa.md`, record the tested viewports, interactions, console/overflow results, screenshot paths, remaining limitations, and the exact line:

```text
final result: passed
```

- [ ] **Step 8: Run the complete frontend unit/build gates**

Run:

```powershell
pnpm --filter @changesafe/web lint
pnpm --filter @changesafe/web typecheck
pnpm --filter @changesafe/web test --run
pnpm --filter @changesafe/web build
```

Expected: every command succeeds.

- [ ] **Step 9: Commit integrated UI proof**

```powershell
git add apps/web/src apps/web/tests tests/e2e README.md docs/demo-script.md docs/devpost-submission.md docs/design/changesafe-design-system.md docs/screenshots design-qa.md
git commit -m "feat: finish truthful dynamic ChangeSafe experience"
```

---

### Task 10: Run repository gates, reconcile master, and publish

**Files:**
- Verify: all tracked files
- Modify only if a gate exposes a defect: the smallest file and its focused regression test

**Interfaces:**
- Produces: a clean, verified `master` commit published to the existing GitHub repository.

- [ ] **Step 1: Run Python quality and deterministic checks**

```powershell
.\.venv\Scripts\python.exe -m ruff check --no-cache .
.\.venv\Scripts\python.exe -m mypy apps/api/src scripts
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts/regenerate_examples.py --check
.\.venv\Scripts\python.exe scripts/check_secrets.py
```

Expected: every command succeeds.

- [ ] **Step 2: Run dbt proof**

```powershell
.\.venv-dbt\Scripts\dbt.exe parse --project-dir fixtures/dbt_project --profiles-dir fixtures/dbt_project
.\.venv-dbt\Scripts\dbt.exe build --project-dir fixtures/dbt_project --profiles-dir fixtures/dbt_project
```

Expected: parse succeeds and build reports all selected models/tests passing.

- [ ] **Step 3: Re-run frontend quality gates**

```powershell
pnpm --filter @changesafe/web lint
pnpm --filter @changesafe/web typecheck
pnpm --filter @changesafe/web test --run
pnpm --filter @changesafe/web build
```

Expected: every command succeeds.

- [ ] **Step 4: Request permission before the local Playwright CLI gate**

If permission is granted, run:

```powershell
pnpm test:e2e
```

Expected: credential-free golden flow and mobile containment pass. If permission is not granted, leave the updated tests for GitHub CI and state that local Playwright was not run.

- [ ] **Step 5: Verify repository integrity**

```powershell
git diff --check
git status --short
git log -12 --oneline
```

Expected: no whitespace errors, no unintended files, and only the planned commit series ahead of the remote branch.

- [ ] **Step 6: Perform final in-app Browser acceptance**

Reopen the completed local build in the in-app Browser and repeat the critical flow after all gates. Confirm the screenshots and `design-qa.md` match the final bytes.

- [ ] **Step 7: Fast-forward master and push**

If implementation used `codex/truthful-dynamic-experience`, fast-forward `master` only after all prior steps pass, then push:

```powershell
git switch master
git merge --ff-only codex/truthful-dynamic-experience
git push origin master
```

Expected: the existing public repository accepts the push and GitHub CI starts for the final master commit.

- [ ] **Step 8: Report the handoff**

Provide the local preview, final commit SHA, GitHub repository/CI links, exact test totals, recorded-evidence explanation, artifact-audit conclusion, and any credential requirements that remain limited to optional live DataHub/GitHub publication.
