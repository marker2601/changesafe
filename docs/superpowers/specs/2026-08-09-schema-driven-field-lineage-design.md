# ChangeSafe Schema-Driven Field Analysis and Exact Lineage

**Date:** 2026-08-09

**Status:** Product behavior approved; proof requirements added for review

## 1. Decision

ChangeSafe will analyze any supported field in the selected DataHub dataset. The
`cust_email` to `primary_email` rename remains a useful example, not a product
restriction.

The current field control will be populated from the selected dataset's recorded
or live DataHub schema. Selecting a different field must change every
field-dependent result: type information, governance, lineage, impact findings,
risk, generated migration files, verification evidence, and approval summary.

The dependency experience will distinguish two separate ideas:

1. the proposed contract change, such as `cust_email -> primary_email`; and
2. the observed data route, such as
   `stg_order_details.cust_email -> order_details.cust_email -> Customer Analytics Measures.cust_email`.

ChangeSafe must never fill an unknown intermediate field or destination field
with an inferred name merely to make a route look complete.

## 2. Why the current behavior is insufficient

The current form accepts free text for `field`, but the shared recorded context is
anchored to `cust_email`. The snapshot contains 55 schema fields, while its
field-level governance and lineage evidence describe the email field. Allowing a
different typed value without acquiring matching context could associate email
evidence with an unrelated field.

The existing graph also emphasizes assets and hop counts. It records endpoint
fields in the data contract, but it does not make the full source-column to
destination-column route prominent enough for a non-technical reviewer.

The redesign therefore treats schema discovery and field-scoped evidence as
correctness requirements, not presentation-only changes.

## 3. Approaches considered

### Static demo choices

Add several hardcoded field options to the frontend and continue using the same
context bundle. This is small, but it is rejected because the choices can drift
from DataHub and could reuse incorrect evidence.

### Dynamic choices with a shared dependency graph

Load the real schema but reuse dataset-level or `cust_email` lineage for every
selection. This improves the control while leaving the analysis misleading. It
is rejected.

### Field-scoped schema and lineage evidence

Load schema options from the active evidence source, then acquire context for the
selected field before scoring or generation. Render exact field endpoints when
DataHub supplies them and disclose missing precision otherwise. This is the
selected approach.

## 4. Field selection experience

### Loading the choices

- The selected Dataset URN is the source of truth.
- A bounded, read-only API retrieves that asset's schema through the configured
  DataHub context adapter.
- The existing dataset allowlist applies to discovery as well as analysis.
- The response includes the asset identity, schema fields, evidence provenance,
  and retrieval time. It contains no credentials.
- The frontend caches a successful response for the current Dataset URN during
  the browser session and ignores stale responses when the URN changes quickly.

### Current field control

- Replace the free-text `Current field` input with an accessible searchable
  combobox/dropdown.
- Each option shows field name, native type, and `required` or `nullable`.
- The official `order_details` scenario exposes its complete supported schema,
  including fields such as `order_id`, `order_status`, `order_total`,
  `customer_id`, `phone_number`, and `cust_email`.
- A loading state says that schema is being read; it does not display static
  fallback options as if they came from DataHub.
- A discovery error leaves Analyze disabled and explains how to retry or use the
  explicitly labelled recorded evidence path.
- An empty schema is a safe failure, not a free-text escape hatch.

### Operation behavior

- Rename keeps `New field` editable. ChangeSafe does not automatically prefix
  every replacement with `primary_`.
- Type change derives `Current type` from the selected schema field and makes it
  read-only evidence. `New type` remains a validated user choice.
- Remove requires no destination field and retains the phase-one safety model.
- Selecting another current field clears operation values that are no longer
  semantically valid and invalidates any previous result.
- After submission, the selected request is immutable and remains bound to the
  returned evidence and artifacts.

## 5. Live and recorded evidence behavior

### Live DataHub

Live mode queries the selected asset's complete schema for the dropdown and then
performs field-scoped lineage, governance, ownership, usage, and query reads for
the selected field during analysis. The result reflects DataHub at the recorded
retrieval time.

### Recorded DataHub evidence

Recorded mode must remain useful without pretending that one email snapshot
proves every field. The official evidence package will be expanded into a
checksummed dataset catalog plus field-scoped contexts.

- All supported schema fields are available for selection.
- Each selected field receives its own type and its own recorded field-level
  evidence.
- When the captured DataHub result contains no field-level lineage, the result
  says so and may show separately recorded dataset-level relationships.
- Governance tags or terms recorded for `cust_email` are not copied to another
  field.
- The selected field and evidence checksum participate in deterministic result
  identity.

This permits a reviewer to compare materially different fields without needing
credentials while keeping every claim tied to a real capture.

## 6. Exact lineage contract

Every rendered dependency is normalized into a directional route with:

- direction: upstream or downstream;
- source asset URN and display name;
- source field when DataHub supplies it;
- destination asset URN and display name;
- destination field when DataHub supplies it;
- authoritative hop degree when present;
- ordered asset path when present;
- evidence precision: exact field route, endpoint-only field route, or
  dataset-level relationship; and
- provenance link and retrieval time.

For an upstream dependency, the route is rendered from the upstream endpoint to
the governed target field. For a downstream dependency, it is rendered from the
governed target field to the dependent endpoint.

Examples:

```text
stg_order_details.cust_email -> order_details.cust_email
order_details.cust_email -> ORDER_DETAILS.cust_email
order_details.order_total -> Customer Analytics Measures.order_total
```

If DataHub returns a two-hop endpoint result but not the intermediate column
mapping, ChangeSafe renders:

```text
order_details.order_total -> Customer Analytics Measures.order_total
2 hops; intermediate column mapping not returned by DataHub
```

If only an asset-level relationship exists, ChangeSafe renders:

```text
order_details.order_status -> Order Details dashboard
Dataset-level relationship; destination field not returned by DataHub
```

It does not render `Order Details dashboard.order_status` unless that destination
field was actually returned.

## 7. Dependency visualization

The current left-to-right upstream, governed-model, downstream structure remains,
but field routes become the primary labels.

- The target node shows `asset.field`, type, and recorded policy.
- Each upstream card shows `source asset.field -> target asset.field`.
- Each downstream card shows `target asset.field -> destination asset.field`.
- A route badge states `direct`, `N hops`, or `dataset-level`.
- Selecting a card opens an evidence drawer with full URNs, ordered asset path,
  field endpoints, precision limitation, provenance, and DataHub links.
- The accessible dependency list exposes the same routes and limitations in the
  same direction.
- Motion continues to indicate data direction, respects reduced motion, and does
  not imply that an unknown intermediate route is known.
- Mobile layouts preserve reading order from source to destination without
  horizontal scrolling.

## 8. Dynamic impact and generation

No field selection directly chooses an impact category. After analysis:

- risk factors are recalculated using that field's actual type, governance,
  lineage, owners, usage, and consumers;
- impact summaries and evidence links refer to the selected field;
- unrelated PII or financial claims do not carry over from a prior run;
- generated SQL, YAML, compatibility tests, migration notes, rollback guide, PR
  body, and manifest use the selected field and its recorded schema contract; and
- the twelve blocking verification checks run against the new bundle.

Repeated analysis of the same field, request, source commit, and evidence remains
deterministic. Selecting another field creates a new request and should normally
produce different evidence, risk, and generated bytes.

## 9. Proof required before claiming the feature works

The dropdown and route labels alone are not sufficient proof. Completion requires
all of the following evidence.

### Backend contract proof

- Schema discovery returns the complete allowlisted asset schema with provenance.
- Unknown assets, unknown fields, duplicate fields, partial schema pages,
  unsupported top-level names, and missing native types fail closed.
- Recorded analysis of at least three meaningfully different fields does not leak
  email governance or lineage into other fields.
- Live DataHub 1.7 response-envelope tests preserve exact endpoint columns,
  degree, and paths without fabricating intermediates.
- Field selection changes the request-bound context, deterministic risk, artifact
  manifest, and verification input.

### Frontend proof

- The dropdown handles loading, success, empty, error, keyboard selection, and a
  changed Dataset URN.
- Type and nullability displayed in the option match returned schema evidence.
- Choosing a different field updates the proposed change immediately and the
  analyzed result only after a new run.
- Exact upstream and downstream routes appear in the graph, drawer, and accessible
  list.
- Missing fields and intermediate columns receive explicit limitation labels.
- A late schema response cannot replace options for a newer Dataset URN.

### Scenario proof

At least three official showcase fields will be exercised end to end, chosen to
represent different evidence profiles. The expected examples are:

- `cust_email`: governed personal-data rename;
- `order_total`: numeric type or rename change with financial/metric consumers;
  and
- `order_status` or `customer_id`: operational or join-integrity change.

The exact classifications must follow captured metadata rather than these sample
descriptions. If DataHub lacks evidence for one expected claim, the UI must report
the lower-confidence result instead of forcing differentiation.

For each scenario, proof includes the selected field, evidence source, route
precision, risk factors, generated file hashes, and all blocking verifier results.

### Executable and browser proof

- Generated dbt packages for the representative operations continue to parse and
  build against the fixture project.
- A browser end-to-end test selects two different fields and proves that their
  request, lineage text, and generated artifacts differ.
- Desktop and mobile browser checks verify dropdown usability, exact route
  readability, evidence-drawer behavior, no overflow, and no console errors.
- Replay and live smoke tests are both recorded in the design QA report.
- Ruff, strict mypy, Python tests, fixture checksums, secret scan, frontend lint,
  TypeScript, Vitest, production build, Playwright, dbt, Docker, and
  `git diff --check` pass before merge.

## 10. Failure and recovery behavior

- Schema discovery never mutates DataHub.
- Analysis stays disabled until a returned field is selected.
- If a selected field disappears before live analysis completes, ChangeSafe stops
  with a schema-context mismatch and produces no publishable artifacts.
- A live read failure follows the existing explicit recorded-evidence fallback;
  it does not silently substitute snapshot options.
- Restored runs continue to display the immutable field and route evidence saved
  with that run, regardless of the current dropdown selection.
- DataHub credentials remain server-side and are never sent to the browser.

## 11. Acceptance criteria

The feature is complete only when:

- `Current field` is populated from the selected asset's active evidence source;
- all supported official schema fields can be selected in recorded mode;
- live mode supports any valid returned field on an allowlisted dataset;
- non-email fields receive their own field-scoped evidence and never inherit
  `cust_email` claims;
- every dependency clearly identifies known source and destination assets and
  columns;
- unavailable destination or intermediate columns are plainly disclosed;
- at least three distinct fields pass end-to-end analysis and verification with
  evidence-appropriate results;
- the shared replay remains deterministic and credential-free;
- the live smoke flow proves the same API against DataHub; and
- the full automated, browser, dbt, Docker, and repository gates pass.

## 12. Non-goals

- No invented semantic replacement name for the selected field.
- No inferred column mapping based only on matching names.
- No claim that a dataset-level dependency is field-level lineage.
- No unrestricted browsing of datasets outside the configured allowlist.
- No automatic warehouse migration, phase-two removal, PR merge, or DataHub
  mutation before the existing owner approval gate.
- No artificial delay to make different field analyses appear more dynamic.
