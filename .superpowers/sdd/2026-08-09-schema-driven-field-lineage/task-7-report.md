# Task 7 Report: multi-field proof matrix

## Scope

Added repeatable proof for the three recorded replay contexts:

- `cust_email` -> `primary_email` (`TEXT`)
- `order_total` -> `preferred_order_total` (`FLOAT`)
- `order_status` -> `preferred_order_status` (`NUMBER`)

The backend matrix proves request/context binding, generated selected-field
aliases, non-null manifests, publication eligibility, and all blocking
verification checks.  It also confirms risk-factor evidence URNs are present
in the saved context and that the non-email field-scoped metadata contains no
`cust_email` label, query, or endpoint.

The API test creates two independent replay analyses and proves their request
fields, saved context fields, contexts, and manifest hashes differ.  It
intentionally excludes the complete schema from the `cust_email` negative
assertion because it is a valid neighbouring catalog field.

The web unit test proves the combobox selection submits `order_total`, its
schema-derived `FLOAT` old type, and the explicit
`preferred_order_total` destination.  Playwright coverage adds the full
non-email result route/drawer proof and a 430x932 keyboard-selection,
accessible-list, evidence-drawer, console-error, and horizontal-containment
flow.

## Captured evidence retained

No catalog data was modified.  The checked-in, checksummed catalog records:

- `cust_email`: 6 upstream and 25 downstream assets; no field-scoped tags or
  glossary terms.
- `order_total`: 6 upstream and 31 downstream assets, including captured
  endpoint-derived relationships.
- `order_status`: 6 upstream and 27 downstream assets.

The initial task handoff said `order_total` had 25 downstream assets.  The
controller confirmed that was a typo; 25 belongs to `cust_email`.  The tests do
not reintroduce stale fixed count or score expectations.

## RED / GREEN evidence

The existing field-driven implementation was already green when each new
regression was first introduced.  To prove the regressions detect the intended
default-field failure, I temporarily fault-injected `field="cust_email"` in
the replay context before each relevant run, observed the expected RED, then
restored the existing `field=change.field` implementation:

- Orchestrator matrix RED: `order_total` and `order_status` failed with
  `assert 'cust_email' == 'order_total'` / `order_status`.
- Generation proof RED: replacing the selected source projection with
  `cust_email` failed both non-email aliases and the existing seeded-field
  regression.
- Verification matrix RED: the non-email contexts failed the explicit
  request/context field binding assertion.
- API comparison RED: the second saved context failed with
  `assert 'cust_email' == 'order_total'`.

After restoring the production expressions, all focused Python proof tests
passed.

## Commands and results

- `python -m pytest apps/api/tests/test_orchestrator.py apps/api/tests/test_generation.py apps/api/tests/test_verification.py apps/api/tests/test_api.py -q`
  - PASS: `64 passed in 7.56s`.
- `python -m ruff check` for the four changed API test modules
  - PASS: `All checks passed!`.
- `git diff --check`
  - PASS.
- `pnpm --filter @changesafe/web test --run tests/App.test.tsx`
  - Not runnable in this worker environment: the supplied `pnpm` shim cannot
    locate `node` (`'node' is not recognized`).
- `pnpm test:e2e -- --grep "field|golden workflow|phone"`
  - Not runnable for the same unavailable Node runtime; no browser was opened
    interactively.
- `dbt parse` / `dbt build`
  - Not runnable: this worker's Python environment has no `dbt` module or
    `dbt.exe`.  No dbt fixture was changed.

`ruff format --check` still reports pre-existing formatting in the four
touched test files outside this task's hunks; no unrelated bulk formatting was
applied.

## Changed files

- `apps/api/tests/test_api.py`
- `apps/api/tests/test_orchestrator.py`
- `apps/api/tests/test_generation.py`
- `apps/api/tests/test_verification.py`
- `apps/web/tests/App.test.tsx`
- `tests/e2e/golden-flow.spec.ts`

## Concern

Frontend, Playwright, and dbt execution need to be rerun by an environment
that provides Node and dbt.  The controller owns rendered browser QA and has
already supplied the necessary state-transition correction for the Playwright
flow (`Approve preview` before `New analysis`).

## Fixes Made — round 1

Review found that the field-level lineage source selected by generation could
not support the complete 55-column projection.  The generator previously
overwrote the governed `order_details` model and could emit
`ref('customers')` or `ref('orders')` from selected-field lineage alone.

- Added a separate `order_details__changesafe` phase-one compatibility model
  and YAML contract.  It projects the recorded target schema and selected
  alias/cast from the known governed `ref('order_details')` model only.
- Bound the singular compatibility test, artifact paths, verifier, manifest,
  migration/rollback/PR text, deterministic examples, and checked-in dbt
  fixture to the shim.
- Restored fixture `order_details` as the governed base model over
  `ref('stg_order_details')`, with a base-only YAML descriptor.  Removed the
  stale generated example files that would otherwise fail deterministic
  regeneration checks.
- Tightened `source_relations`: the generated shim must reference exactly its
  governed base model and must not reference itself.  Added three-field
  generation proof plus a self-cycle verifier regression.
- Corrected the web request expectation: a rename carries `old_type: null`
  and `new_type: null`; the dropdown option still independently proves the
  `FLOAT` schema evidence.
- Updated Playwright replay truth: email rename 85/Critical, email remove
  100/Critical, email type change 95/Critical, and order-status rename
  75/High.

### Round-1 RED / GREEN

- The new shim regression initially failed for all three selected fields
  because `models/marts/order_details__changesafe.sql` was absent.
- The full Python suite then exposed all old target-model path expectations;
  those tests were updated to the new public artifact contract rather than
  weakening verification.
- After the minimal shim implementation and deterministic regeneration:
  full Python passed `244 passed` (one existing upstream SDK warning), web
  Vitest passed `126`, focused Playwright passed `3`, full Playwright passed
  `4` with one intentionally skipped screenshot capture, and dbt build
  reported `PASS=61`.

## Fixes Made - round 2

Fresh review found that `compatibility_test` trusted text substrings, so a
hash-valid singular test could point at the governed target, use `where false`,
and place the expected comparison only in a comment. The artifact explorer also
still preferred an obsolete generated target path, while the migration package
did not make the governed-target/shim operational sequence explicit.

- Added parsed semantic singular-test validation: exactly one top-level SELECT,
  exactly one source relation bound to the generated shim, one selected old
  field, and an operation-specific real predicate (`false` for removal or
  `NullSafeNEQ` against the expected old expression for rename/type change).
  Extra statements, comments, wrong relations, aliases, and invalid casts no
  longer satisfy the check.
- Added hash-recomputed mutation regressions for the exact comment/wrong-source
  spoof and for an appended SELECT. The original spoof was observed RED with a
  still-valid manifest before the validator change, then both are GREEN.
- Changed the artifact explorer to sort paths and select the generated
  `models/marts/*__changesafe.sql` deterministically, with the first sorted path
  as a safe fallback. Browser fixtures, catalog text, and App/explorer tests now
  expose the real `order_details__changesafe` bundle and retain the seven-file
  count.
- Made generated migration notes and PR bodies name governed `order_details`
  and compatibility `order_details__changesafe`, state that the base remains
  unchanged in phase one, instruct downstream owners to switch to the shim and
  migrate to `primary_email`, and require migration through the shim in exit
  criteria. Rollback now moves consumers back to the governed target before
  reverting/removing shim artifacts and the singular test.
- Updated current public replay copy only (no Task 8 captures) to the captured
  `cust_email` rename result: 25 downstream assets and 85/Critical. The
  field-scoped replay does not claim PII evidence.

### Round-2 RED / GREEN

- RED: `pytest apps/api/tests/test_verification.py -k hashed_comment_spoof`
  failed because `compatibility_test` passed the forged wrong-source/comment
  test despite `manifest_hashes` passing.
- GREEN: the same focused regression passed after parsed validation; the added
  appended-statement regression also passed.
- GREEN: operational artifact regression passed after generation explicitly
  described the target/shim transition and rollback ordering. The updated
  browser explorer/catalog regressions pass with the shim initially selected.

### Round-2 gates

- `python -m pytest apps/api/tests -q` - PASS: `247 passed, 1 warning`.
- `python scripts/regenerate_examples.py` and `--check` - PASS.
- Web lint, typecheck, Vitest, and production build - PASS; `126 passed`.
- Focused Playwright - PASS: `3 passed`; full Playwright - PASS: `4 passed`,
  `1 skipped` (intentional screenshot capture).
- dbt parse/build - PASS; build `PASS=61`.
- Ruff, mypy, and `git diff --check` - PASS.
- Scoped commit: `3445249 fix: harden compatibility proof artifacts`.

## Fixes Made - round 3

This review found three remaining verifier gaps despite valid recomputed
manifests: undefined qualified columns could satisfy the compatibility AST;
the model source check trusted Jinja-looking comments; and operational guidance
and rollback sequencing were not enforced by their existing blocking checks.

- The compatibility AST now requires the sole shim source to be unaliased and
  every tested column unqualified. Hash-valid `x.cust_email` / `x.primary_email`
  mutations are rejected for rename, removal, and type change.
- Jinja ref extraction is comment-safe. The model source check now requires one
  parsed table source equal to governed `order_details`, a real uncommented dbt
  ref to it, and no self-cycle. A model using `from customers -- {{ ref(...) }}`
  no longer passes by placing the governed ref in a comment.
- `migration_notes` remains one of the existing 12 blockers but now validates
  both migration and PR transition guidance: governed and shim relations,
  unchanged phase-one base, owner switch instruction, operation-specific
  migrate/retain language, and shim-based exit criteria. The generated PR body
  now carries matching exit criteria.
- `rollback_instructions` now validates the complete safe order: consumers move
  from shim to governed target, old-field availability is confirmed, and only
  then can shim SQL, YAML, and the singular test be removed. It rejects either
  consumer movement or confirmation after removal.

### Round-3 RED / GREEN

- RED: seven recomputed-manifest mutations initially passed their relevant
  compatibility, source, migration/PR, or rollback checks: three undefined
  qualifier variants, comment-only governed ref, missing migration guidance,
  missing PR switch instruction, and consumer movement after removal.
- RED (follow-up): a recomputed manifest that moved old-field confirmation
  after shim removal still passed until the ordering invariant was tightened.
- GREEN: all eight focused exploit regressions pass after the parsed/comment-
  safe and ordered validation changes.

### Round-3 gates

- Python API suite - PASS: `256 passed, 1 warning` (existing upstream SDK
  experimental warning).
- mypy, targeted Ruff, deterministic regeneration check, and `git diff --check`
  - PASS.
- Web lint, typecheck, Vitest, and production build - PASS; `126 passed`.
- Focused Playwright - PASS: `3 passed`; full Playwright - PASS: `4 passed`,
  `1 skipped` (intentional screenshot capture).
- dbt parse/build - PASS; build `PASS=61`.
- Scoped commit: `2915a4b fix: enforce verifier proof semantics`.

## Fixes Made - round 4

The final review found that independently validating raw dbt references and
parsed tables allowed a ref placed in an expression to vouch for a bare FROM
relation. It also found that positive operational substrings accepted negated
instructions, and that both a `LIMIT 0` comparison guard and a NULL preferred
projection could create a hash-valid but meaningless package.

- Added a comment- and string-aware dbt ref scanner that replaces only live
  ref tokens with sentinels. The source relation check now requires exactly one
  live ref and requires the parsed FROM table itself to be that sentinel bound
  to governed `order_details`; refs in strings/comments or additional scalar
  refs cannot authenticate a bare source.
- Tightened the model phase-one AST contract. The old field must remain an
  unqualified projection; rename aliases must come from that old column and
  type aliases must be a requested-type cast of it. NULL preferred aliases no
  longer pass.
- Made compatibility singular tests clause-strict: only expressions, FROM, and
  the required WHERE are allowed, rejecting `LIMIT 0`, DISTINCT, ordering,
  grouping, qualifying, post-filters, and other bypass clauses.
- Restructured generated migration/PR transition guidance into exact action
  lines. The existing migration check now requires each action line exactly
  once and rejects negated action lines. Rollback continues to require its
  exact numbered safe-order contract, which rejects negated confirmation.

### Round-4 RED / GREEN

- RED: eight recomputed-manifest mutations initially passed all relevant
  blockers: bare `from order_details` authenticated only by a scalar ref,
  negated migration/PR transition text, negated rollback confirmation, LIMIT 0
  on rename/type singular tests, and NULL rename/type preferred projections.
- RED (controller follow-up): an extra live scalar governed ref and a prefixed
  `Never follow:` transition line also passed before one-ref sentinel binding
  and exact-line validation.
- GREEN: all ten focused exploit regressions pass after hardening.

### Round-4 gates

- Python API suite - PASS: `266 passed, 1 warning` (existing upstream SDK
  experimental warning); focused generation/verification `57 passed`.
- mypy, targeted Ruff, deterministic regeneration check, and `git diff --check`
  - PASS.
- Web lint, typecheck, Vitest, and production build - PASS; `126 passed`.
- Focused Playwright - PASS: `3 passed`; full Playwright - PASS: `4 passed`,
  `1 skipped` (intentional screenshot capture).
- dbt parse/build - PASS; build `PASS=61`.
- Scoped commit: `3b5bbd6 fix: bind generated proof contracts`.

## Fixes Made - round 5

Final adversarial review found execution and audit-integrity bypasses that
could survive a recomputed manifest. The generated compatibility relation is
now a sealed deterministic package rather than a collection of independently
hash-valid text files.

- Compatibility singular tests permit exactly their generated live Jinja ref
  and no config macro. A permissive dbt config (or any other live directive)
  cannot turn a dbt mismatch into a warning.
- The shim model requires its exact safe table/contract config, exactly one
  unaliased/unprefixed governed `ref`, a sole `SELECT` with no row-altering
  clauses, and exact unqualified projections for every captured schema field.
  Rename/type preferred projections remain the only allowed additional output.
- Shim YAML is an exact one-model contract: safe `contract.enforced`, no
  disabled/hooks/unknown executable config, and only expected model and column
  keys, types, descriptions, and not-null tests.
- Migration/PR protected action lines reject conflicting switch/migrate/retain
  instructions. Rollback requires exactly the six generated numbered steps,
  preventing duplicate or negated pre-steps from being collapsed.
- Planner-authored narrative no longer enters authoritative migration, PR, or
  rollback bytes. Runtime generation never invokes the optional planner, makes
  no LLM reservation, and advertises no LLM generation availability; reviewed
  templates are the sole release path.
- `manifest_hashes` still validates semantic version/change/context/risk and
  declared digests, then regenerates the expected package from the request,
  replay context, and deterministic risk score. Every artifact hash and the
  manifest hash must exactly match the regenerated seven-file bundle.

### Round-5 RED / GREEN

- RED: 14 recomputed-manifest mutations initially passed: permissive config on
  rename/remove/type tests; shim row filters; conflicting PR action lines;
  duplicate rollback step; weak model configs; transformed unrelated
  projection; alias/prefixed source; and semantic manifest spoof.
- RED (final additions): disabled YAML model config, malicious valid planner
  prose, and arbitrary rehashed PR prose also initially passed their relevant
  checks. The malicious narrative proved an LLM could not author operational
  instructions safely.
- GREEN: the focused final exploit matrix passed `16` tests, and the full
  verifier module passed `51` tests.

### Round-5 gates

- `python -m pytest apps/api/tests -q` - PASS: `283 passed`; known warnings
  remain the upstream experimental DataHub SDK and an aiosqlite loop-close
  warning in the existing preflight test.
- Ruff and mypy - PASS; deterministic regeneration and `git diff --check` -
  PASS.
- Bundled-node web test/lint/typecheck/build - PASS; Vitest `126 passed`.
- Focused Playwright - PASS: `2 passed`; full Playwright - PASS: `4 passed`,
  `1 skipped` (intentional screenshot capture).
- dbt parse/build via `.venv-dbt` - PASS; build `PASS=61`.

### Round-1 commands

- `python -m pytest -q` — PASS: `244 passed, 1 warning`.
- `python scripts/regenerate_examples.py --check` — PASS.
- `pnpm --filter @changesafe/web lint`, `typecheck`, `test --run`, and
  `build` (with the bundled Node runtime) — PASS; Vitest `126 passed`.
- `pnpm exec playwright test --grep "field|golden workflow|phone"` — PASS:
  `3 passed`.
- `pnpm exec playwright test` — PASS: `4 passed`, `1 skipped` screenshot
  capture.
- `.venv-dbt\\Scripts\\dbt.exe parse` and `build` — PASS; build `61/61`.
- Targeted Ruff and `git diff --check` — PASS.
