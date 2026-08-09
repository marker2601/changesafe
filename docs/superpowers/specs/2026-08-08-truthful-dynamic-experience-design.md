# ChangeSafe Truthful Dynamic Experience

**Date:** 2026-08-08

**Status:** Product direction approved; written specification awaiting review

## 1. Decision

ChangeSafe will present analysis as a truthful data-contract safety workflow, not as a competition-specific demonstration or a simulated long-running process. The redesign keeps the existing high-contrast command-center identity while correcting misleading controls, hardcoded scenario copy, static-looking impact cards, the shrinking hero, and the inventory-like dependency map.

The product must remain honest about speed and provenance:

- a replay run may complete in a fraction of a second;
- identical requests against the same checksummed evidence must produce identical results;
- motion explains lineage direction and current state, but never pretends that backend work is still running;
- recorded evidence, preview-only behavior, and live publication are named in plain language; and
- all public copy is product language, not "judge," "competition," or "prepared demo" language.

This specification refines and supersedes the public-copy, runtime-status, hero, graph-motion, impact-interaction, and artifact-explanation requirements in `2026-08-08-judge-experience-redesign-design.md`. The earlier security, publication, recovery, accessibility, and deterministic-verification requirements remain in force.

## 2. User-visible promise

The stable product message is:

> Change data safely, with every dependency in view.

> ChangeSafe uses DataHub evidence to find affected systems and teams, prepare a compatible migration, verify every generated file, and pause before anything is published.

The message does not shrink, disappear, or change wording after analysis begins. A compact run summary may appear below it, but the hero keeps a stable footprint across empty, running, approval, failure, and completed states.

The interface must answer four questions without requiring data-engineering knowledge:

1. What change is being proposed?
2. Which systems, reports, and teams depend on it?
3. What could go wrong, and what evidence supports that conclusion?
4. What did ChangeSafe generate and verify before asking for approval?

## 3. Provenance and deterministic replay

### Recorded DataHub evidence

The term `REPLAY` is replaced in prominent user-facing copy by **Recorded DataHub evidence**. Supporting text explains:

> This run uses a checksum-verified recording of DataHub metadata. It makes the demo reproducible and performs no live DataHub reads or writes.

The footer and run summary expose:

- evidence source: `Recorded snapshot` or `Live DataHub`;
- snapshot retrieval time when recorded evidence is used;
- an abbreviated checksum with a copy affordance for the full value;
- publication behavior: `Preview only` or the configured live destinations; and
- actual elapsed analysis time.

`Snapshot replay` and `Preview only / snapshot mode` are not rendered as bordered cards or button-like pills. They are status rows or badges with non-interactive semantics. A separately labeled **About this run** control opens the full explanation when more detail is useful.

### Reproducibility explanation

After a replay run, the result summary states:

> Same request + same evidence = same verified result.

This is a positive reproducibility property, not hidden behavior. The request operation, normalized fields or types, source commit, snapshot checksum, and run ID remain visible so users can see what would make a result different.

Changing Rename, Remove, or Type change must update the request summary immediately and generate operation-specific risk, copy, artifacts, and tests. The six impact dimensions remain stable categories because they are the product's assessment framework; their evidence and severity are computed results, not user selections.

## 4. Stable layout and responsive behavior

### Header and hero

- Remove the `is-compact` hero behavior.
- Keep the brand mark, eyebrow, headline, and supporting copy at the same typography and spacing before and after a run.
- Replace fixed left padding that causes medium-desktop clipping with a responsive grid that reserves space for the mark only when the viewport can support it.
- At widths below the desktop threshold, stack the brand mark above or beside the copy without horizontal overflow.
- Runtime provenance appears in a compact facts row below the supporting copy, not as oversized pseudo-buttons in the primary header.
- The activity control is labeled **Review activity** and its panel uses neutral terms such as `session`, `run`, `review`, and `owner`.

### Workspace

The desktop workspace retains three clear regions:

1. proposed change and computed impact;
2. directional dependency journey and artifacts; and
3. real run activity and approval.

The layout must remain usable at 1280 px without clipped headlines or off-screen runtime facts. Below the existing responsive breakpoint, regions stack in task order and the dependency journey has a full accessible list alternative.

## 5. Scenario-aware change summary

The change form owns a draft object that is lifted to the application shell. Both the form and the central empty state consume the same draft, preventing stale rename copy after the user selects another operation.

Required pre-analysis summaries:

- Rename: `Keep cust_email available while consumers move to primary_email.`
- Remove: `Delay removal of cust_email until every recorded consumer has migrated.`
- Type change: `Keep cust_email and add a safely cast compatibility field during phase one.`

The heading above the map derives its field and operation from the current draft before submission and from the immutable run request afterward. The submitted request, not later form edits, controls all analyzed-result copy.

`requested_by` must use a neutral anonymous-session identifier instead of `judge-demo`. No visible string contains `judge`, `judge-ready`, `official judge scenario`, or `prepared for judging`.

## 6. Truthful event flow

ChangeSafe continues to consume persisted Server-Sent Events and never advances backend state with presentation timers.

### During a genuinely active run

- highlight only the phase represented by the latest persisted event;
- progressively reveal evidence and artifacts when the corresponding server data exists;
- announce phase changes through the existing accessible live region;
- show a live elapsed timer derived from the request start time; and
- stop motion and expose recovery actions on fallback or failure.

### When replay finishes immediately

If the browser receives several events before it can paint intermediate states, it renders the completed history without artificial waiting and reports the measured result, for example:

> Analysis completed in 0.28 seconds from recorded evidence.

Timeline entries use sequence numbers and millisecond-capable relative timing where timestamps are otherwise identical. The interface may animate their entrance over a short 160–260 ms visual transition, but does not delay availability, approval, or navigation.

The timeline distinguishes `attempted`, `completed`, `active`, `failed`, and `pending`. A failed live context read is never labeled `Context loaded` merely because the loading state was observed.

## 7. Directional dependency journey

The map communicates movement from upstream inputs through the governed dbt model to downstream consumers.

### Visual behavior

- connect the three regions with visible left-to-right rails rather than isolated arrow icons;
- animate a restrained teal light travelling along each rail to communicate data direction;
- use the animation as relationship affordance, not as a claim that analysis is still running;
- emphasize the active discovery rail while context is loading;
- keep a slower ambient direction indicator after completion, as requested, without pulsing completed status nodes;
- disable travel animation under `prefers-reduced-motion` and retain arrowheads plus `Upstream`, `Governed model`, and `Depends on this field` labels;
- show direct and multi-hop relationships as explicit text on every dependency card; and
- when an impact evidence filter is active, dim unrelated nodes and display `Showing evidence for <category>` above the map.

### Interaction

Dependency cards remain real buttons because they open evidence details. Their labels and focus states must make that action clear. The map also provides the existing accessible dependency list with the same evidence, relationship direction, path degree, domain, and DataHub link.

No connector fabricates a direct edge. Multi-hop evidence is labelled as multi-hop even when only endpoints and degree are available.

## 8. Computed impact findings

Impact classifications are results, not choices. Each category is rendered as a non-interactive finding card containing:

- category and severity;
- confidence: `Direct evidence`, `Inferred`, or `Evidence unavailable`;
- one operation-specific consequence sentence;
- a concise basis sentence; and
- a **Trace supporting evidence** button.

Only that evidence button is interactive. Finding cards do not use `aria-pressed` and do not receive a selected-input treatment. When evidence is traced, the graph and evidence drawer show which URNs produced the finding.

The classifier's operational-continuity summary must name the actual operation rather than always saying `during the rename`. Stable categories may keep the same severity when the evidence justifies it; the UI explains that the underlying dataset, governance tags, owners, and consumers are unchanged even when the requested operation changes.

Financial exposure remains explicitly qualitative. No dollar amount, customer count, penalty, or certainty is invented from metadata.

## 9. Artifact truth and explanations

The seven generated files remain deterministic and byte-for-byte verifiable. The artifact explorer adds a plain-language panel for each file type:

| Artifact | What it does | Failure it prevents |
|---|---|---|
| dbt model SQL | Preserves the current field and adds the compatible alias or cast when required. | Breaking existing consumers during phase one. |
| dbt model YAML | Enforces the output contract using DataHub-backed names, types, and nullability. | SQL/YAML drift and invented constraints. |
| compatibility test | Proves the old and new outputs agree, or proves the old field is still present for deferred removal. | Silent divergence or premature removal. |
| migration notes | Records owner, evidence, migration window, consumers, and exit criteria. | An uncoordinated phase-two change. |
| rollback guide | Identifies the exact generated files and recovery order. | Incomplete or unsafe reversal. |
| pull-request body | Summarizes deterministic risk, impact, and verification gates. | Publishing without reviewer context. |
| manifest | Binds the request, evidence checksum, risk, paths, and exact UTF-8 hashes. | Artifact substitution or drift after verification. |

The removal test remains a dbt singular compile-time guard. Its generated comment becomes:

```sql
-- Phase-one safety guard: dbt passes because this query returns zero rows.
-- If cust_email is removed too early, compilation fails before publication.
select cust_email
from {{ ref('order_details') }}
where false
```

This is valid because a dbt singular test passes when its query returns zero rows, while resolving the selected column still requires the field to exist. The validation label for removal must say `Phase-one field remains available`, not `compares old and new values`.

All Rename, Remove, and Type change bundles must pass the shared twelve-check verifier. The executable dbt sample must continue to parse and build, and operation-specific generated SQL must parse with the Snowflake dialect.

## 10. Component boundaries

Implementation stays within the existing React and FastAPI architecture.

- `App.tsx` coordinates the immutable analyzed run, current form draft, stable hero, selected evidence category, and elapsed summary.
- `ChangeForm.tsx` exposes a typed draft-change callback and renders operation-specific guidance.
- `Header.tsx` renders stable branding, neutral activity access, and non-button runtime facts.
- a focused run-provenance component explains recorded versus live evidence and preview versus publication without overloading the header.
- `ImpactClassification.tsx` renders findings and dedicated evidence actions.
- `ImpactGraph.tsx` renders directional rails, relationship labels, evidence filtering, and accessible equivalents.
- `RunTimeline.tsx` derives truthfully completed stages and relative durations from persisted events.
- `ArtifactExplorer.tsx` maps each known path to its purpose and protected failure mode.
- the backend impact classifier supplies operation-correct summaries.
- the deterministic artifact templates supply the clarified removal guard comment.

No new frontend framework, graph library, route, data store, or animation dependency is required. Existing Lucide icons, CSS tokens, event models, evidence drawer, and API contracts are reused.

## 11. Failure and recovery behavior

- A live-context failure freezes the failed stage and offers explicit recorded-evidence fallback.
- Snapshot fallback clears stale errors and updates provenance everywhere.
- A publication or preview failure preserves successful checkpoints and shows retry only when `retryable` is true.
- Restored `publishing` and `preparing_preview` runs retain their persisted intent and expose the correct resume action.
- Unknown artifact paths still render safely as text and receive a generic `Generated file` explanation.
- Missing or malformed timing information falls back to event order without inventing durations.
- Motion never hides or delays an error, approval control, or completed result.

## 12. Testing and visual verification

Implementation is test-driven.

### Backend

- operation-specific impact-summary tests for rename, remove, and type change;
- exact removal-guard content and verifier-label tests;
- all three operation bundles pass deterministic generation and verification;
- dbt parse/build remains green for the checked-in executable example; and
- existing risk, schema-type, manifest, publication, replay, and live-context tests remain green.

### Frontend

- the hero has identical structural size/class before and after analysis;
- switching operations updates both form guidance and empty-state scenario copy;
- no public `judge` copy remains;
- runtime facts are not exposed as buttons;
- impact findings are articles with a dedicated evidence action, not pressed choices;
- graph rails, direct/multi-hop labels, active evidence filtering, and reduced-motion behavior render correctly;
- an immediate replay displays actual elapsed time and completed event order without artificial delay;
- artifact explanations and operation-specific compatibility labels are present; and
- stored-run restoration, fallback, approval, retryability, and publication truthfulness remain covered.

### Browser and repository gates

- inspect empty, running if observable, awaiting-approval, failure/fallback, and completed states in the user-selected in-app Browser;
- verify desktop at 1440 px and medium desktop at 1280 px, plus the existing mobile target;
- confirm no clipping, horizontal overflow, false buttons, console errors, or broken core interactions;
- compare refreshed desktop and mobile screenshots to the approved direction;
- update `design-qa.md` with evidence and `final result: passed`;
- run Ruff, strict mypy, Python tests, example regeneration, secret scan, frontend lint, TypeScript, Vitest, production build, Playwright, dbt, and `git diff --check` before completion.

## 13. Acceptance criteria

The redesign is complete only when:

- the hero no longer changes size after Analyze;
- medium-desktop and mobile layouts do not clip or overflow;
- no competition-targeted `judge` wording appears in the public interface;
- every pre-analysis scenario sentence follows the selected operation;
- recorded evidence and preview-only behavior are understandable and do not look clickable;
- repeated replay results are explained as deterministic and show their request/evidence identity;
- real events drive state, while actual sub-second completion is reported honestly;
- directional light visibly travels from upstream inputs through the governed model to downstream consumers, with reduced-motion equivalence;
- impact cards read as computed findings and expose a clear supporting-evidence action;
- operation-specific impact copy is correct;
- each artifact explains its purpose and protected failure;
- the removal compile guard is technically unchanged but clearly explained;
- all three operations produce different operation-appropriate risk/artifacts and pass the verifier; and
- the complete repository and browser quality gates pass.

## 14. Non-goals

- No artificial four-to-six-second processing delay.
- No random risk scores or nondeterministic impact classifications.
- No fabricated live DataHub activity when recorded evidence is active.
- No additional recorded dataset in this implementation; a separately captured second DataHub scenario is a future enhancement because genuine variability requires genuine source evidence.
- No automatic PR merge, warehouse execution, or phase-two field removal.
- No change to owner-gated publication safety, destination allowlists, or server-side credential handling.
