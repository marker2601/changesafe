# ChangeSafe Competition Live Validation Design

**Date:** 2026-08-09  
**Status:** Approved direction; implementation pending  
**Target:** DataHub hackathon judging build

## Objective

ChangeSafe must behave as a live, evidence-driven safety system during judging.
The selected field and operation must determine the context, score, generated
artifacts, warehouse evidence, and approval decision. No field has a hard-coded
score or prewritten result.

The judging build will:

1. read the current allowlisted schema and field context from DataHub;
2. compute deterministic risk from the returned metadata;
3. generate and statically verify the operation-specific compatibility package;
4. optionally validate the selected field against a read-only, non-production
   Snowflake relation without returning raw values; and
5. block approval whenever required evidence is missing, ambiguous, stale,
   mismatched, or failed.

## Truth boundaries

The interface and API must distinguish these claims:

- **Live DataHub metadata checked:** current schema, lineage, ownership,
  governance, domains, and available usage context were read from DataHub.
- **Recorded DataHub evidence checked:** a checksum-pinned recording was used
  only after an explicit fallback decision.
- **Warehouse values checked:** aggregate, read-only validation ran against the
  configured non-production Snowflake relation.
- **Production rows not queried:** shown whenever warehouse validation is absent
  or configured against a non-production target.

Recorded evidence may produce a diagnostic preview, but it cannot inherit a
live-verification claim. Missing required live or warehouse evidence blocks the
approval action while leaving the failure explanation inspectable.

## Non-goals

- Do not connect ChangeSafe to a write-capable warehouse role.
- Do not execute arbitrary model-generated or user-supplied SQL.
- Do not return, log, store, or render raw warehouse field values.
- Do not apply migrations, remove fields, merge pull requests, or alter rows.
- Do not silently switch from live DataHub to recorded evidence.
- Do not add an OpenAI model to the ChangeSafe runtime. Risk, generation,
  validation, and approval remain deterministic.
- Do not claim that a metadata-only check validated warehouse values.

## Runtime modes

### Shared judging mode

The shared application runs with `CHANGESAFE_MODE=auto` and server-side DataHub
credentials. Schema discovery and analysis attempt live DataHub first.

If live DataHub fails before analysis completes:

1. the run pauses in the existing explicit fallback state;
2. the UI identifies the live failure without exposing credentials or internals;
3. the reviewer may deliberately choose recorded evidence; and
4. the resulting run remains clearly recorded and non-publishable whenever the
   competition policy requires live evidence.

No fallback is permitted after publication begins.

### Mutation policy

Live reads and warehouse validation do not authorize writes. GitHub publication
and DataHub writeback remain disabled in the public judging container until the
owner deliberately enables each existing mutation switch and provides the owner
token.

## Evidence pipeline

The run pipeline is:

1. Validate the strict operation request.
2. Discover the complete allowlisted schema from live DataHub.
3. Verify that the selected field exists exactly once and has a concrete type.
4. Load field-scoped DataHub context.
5. Bind the returned entity and schema identity to the requested URN and field.
6. Compute the deterministic risk factors and impact classifications.
7. Generate the seven deterministic compatibility artifacts.
8. Run the existing twelve blocking static checks and exact bundle-byte seal.
9. Run the warehouse validation contract when it is required and configured.
10. Combine static and warehouse evidence into one approval-eligibility result.
11. Persist the complete decision before enabling owner approval.

Every stage emits a durable event. A failed stage cannot be represented as
complete, and a network disconnect cannot erase the persisted run state.

## Warehouse validation architecture

### Port

Add a `WarehouseValidationPort` so orchestration and tests do not depend directly
on Snowflake. Its only public operation validates a `ChangeRequest` plus its
already-normalized `ContextBundle` and returns a typed aggregate result.

The result records:

- validation mode and target environment label;
- operation and selected field;
- relation fingerprint without credentials;
- start and completion timestamps;
- rows evaluated or an explicitly labelled compile-only result;
- aggregate failure count where meaningful;
- safe query identifier and elapsed time;
- individual checks with pass/fail, retryability, and public explanation; and
- an overall `passed` value.

No field value may appear in this result.

### Snowflake adapter

Implement a `SnowflakeWarehouseValidator` using the official Python connector.
It receives all connection settings server-side and connects with an exact
read-only role, warehouse, database, and schema. The target relation comes from
an operator allowlist, never directly from a browser request.

Before validation, the adapter confirms its active account context and exact
allowed role/database/schema/warehouse. A mismatch fails closed.

Every query must:

- be produced by reviewed deterministic templates;
- parse as exactly one Snowflake `SELECT` or `WITH ... SELECT` statement;
- reference only the configured allowlisted relation and selected identifier;
- use a ChangeSafe query tag;
- run with a bounded statement timeout;
- return aggregates or compile status only; and
- close or cancel cleanly on timeout or disconnect.

DDL, DML, stored procedures, external functions, multiple statements, comments
that alter parsing, and unallowlisted relations are rejected before execution.

### Operation-specific evidence

#### Rename

Validate that the current field is present and that a projection to the proposed
name compiles against the live relation. Record row and non-null counts only when
the competition connection permits an aggregate scan. Explain that rename is a
projection with no value transformation; do not invent a value-comparison claim.

The destination must remain a valid identifier, differ case-insensitively from
the source, and not collide case-insensitively with any existing field.

#### Remove

Validate that the current field still exists for the phase-one compatibility
window. Record only total and populated-row counts. A populated count is impact
evidence, not permission to remove the field. The generated guard remains a
deferred dbt test; ChangeSafe does not perform the phase-two removal.

#### Change type

Validate the source type against live DataHub and live warehouse schema, then run
an aggregate conversion-safety query. Count non-null source rows and rows that
cannot be represented by the requested type. Type-family checks must detect
silent narrowing, including string length and fixed-point precision/scale, rather
than relying only on `TRY_CAST` returning non-null.

Canonical no-ops, unsupported Snowflake types, invalid arity or bounds, metadata
type mismatches, and any nonzero unsafe-conversion count block approval.

## Fail-closed policy

| Condition | Diagnostic view | Approval |
|---|---|---|
| DataHub authorization or transport failure | Show safe failure and explicit recorded option when permitted | Blocked |
| Requested URN or field differs from returned evidence | Show context identity failure | Blocked |
| Field missing, duplicated, or missing a concrete type | Show schema-contract failure | Blocked |
| Partial or inconsistent pagination | Show incomplete-evidence failure | Blocked |
| Rename destination collision or invalid identifier | Show exact request correction | Blocked |
| Type mismatch, no-op, unsupported type, or invalid bounds | Show exact type correction | Blocked |
| Static artifact or manifest check fails | Preserve failed checks and artifacts for inspection | Blocked |
| Warehouse credentials unavailable when required | Show warehouse validation unavailable | Blocked |
| Warehouse role or target identity mismatch | Show operator configuration failure | Blocked |
| Warehouse timeout or transient transport failure | Show retryable warehouse failure | Blocked until successful retry |
| Warehouse query violates deterministic safety guard | Show non-retryable safety failure | Blocked |
| Unsafe conversion count is nonzero | Show aggregate failure count only | Blocked |
| Browser loses approval response after durable completion | Reconcile persisted receipt | Completed without duplicate action |
| Recorded fallback is selected | Show checksum and retrieval provenance | Diagnostic preview only under live-required policy |

## Dynamic scoring contract

Risk is a deterministic score out of 100, not a percentage or a random model
prediction. Fixed policy weights are acceptable; fixed field results are not.

Each run must persist and render the factor ledger that produced its score. The
selected field's current DataHub evidence controls which factors apply. Two
fields may receive the same score only when their evidence activates the same
weighted factors; their field context, routes, counts, explanations, and
artifacts must still remain field-specific.

Tests must prove that changing evidence changes the applicable factors and that
no field-name lookup table or preset result controls the score.

## Interface contract

Before analysis, the form shows where the dropdown schema came from: live
DataHub, recorded evidence, loading, or unavailable.

After analysis, the overview reserves stable space for:

- DataHub evidence source and retrieval time;
- selected field and current live type;
- warehouse validation status and environment label;
- `Production rows not queried` when applicable;
- deterministic score and expandable factor ledger; and
- approval eligibility with the exact blocking reason.

The process timeline includes a separate warehouse-validation stage only when
that capability is required. It must visibly progress from pending to running to
passed or blocked using persisted server events, not artificial delays.

All controls remain keyboard accessible and usable at 430 px. Error states must
offer a truthful retry, fallback, or new-analysis action; no terminal state may
trap the reviewer.

## Boundary and validation matrix

### Exhaustive deterministic matrix

Against the checksum-pinned 55-field catalog, run all three operations for every
field using generated non-colliding rename destinations and valid alternate type
fixtures. This produces 165 field-operation cases. Each case must either produce
a sealed, eligible package or a documented, expected fail-closed result based on
its schema semantics.

### Request boundaries

Cover empty, 1-character, 128-character, and 129-character identifiers; invalid
first characters; whitespace and quoting; Unicode and control characters;
case-insensitive equality and collisions; irrelevant operation fields; missing
required fields; extra JSON properties; canonical type aliases; no-op types; and
every supported type family's minimum, maximum, widening, narrowing, invalid
arity, and invalid-bound cases.

### Evidence boundaries

Cover unknown fields, duplicate fields, null or unknown native types, nested
field paths, unsupported quoted top-level identifiers, wrong entity URNs, wrong
schema URNs, empty pages, repeated pages, totals that shrink or grow, degree-only
lineage, concrete paths, missing endpoint fields, absent governance, absent
owners, absent query usage, authorization errors, timeouts, transport errors, and
explicit recorded fallback.

### Warehouse boundaries

Cover missing configuration, invalid credential, wrong role, wrong target,
missing relation, missing field, schema drift after DataHub read, zero rows, all
null rows, conversion failures, silent string and decimal narrowing, timeout,
cancel, connector error redaction, unsafe query rejection, and proof that no raw
value reaches logs, API models, database state, or the browser.

### Publication and recovery boundaries

Retain and extend the existing tests for duplicate approval, lost response,
terminal event-stream closure, process restart at every publication checkpoint,
partial external completion, destination drift, permanent versus retryable
errors, completed receipt reuse, and exact verified artifact bytes.

### Browser boundaries

Test every operation using pointer and keyboard selection, invalid and corrected
destinations, live/recorded provenance changes, warehouse pass/fail states,
approval disabled/enabled transitions, refresh recovery, 1440 px and 430 px
containment, reduced motion, and an empty console.

## Test strategy

Implementation follows test-driven development:

1. unit tests for operation, type, query-template, and redaction contracts;
2. adapter contract tests with a fake Snowflake connection;
3. API tests for eligibility and safe error mapping;
4. the 165-case recorded matrix;
5. web component and hook tests for all states;
6. Playwright competition flows for Rename, Remove, and Change type;
7. Docker image smoke tests in live-DataHub-first mode; and
8. a credential-conditional read-only Snowflake smoke that never runs in pull
   requests without operator-provided secrets.

The existing Python, Ruff, mypy, deterministic-regeneration, secret-scan, web
lint/typecheck/test/build, Playwright, dbt parse/build, Docker smoke, and GitHub CI
gates remain mandatory.

## Configuration and secret handling

Add documented placeholders, never real values, for:

- `CHANGESAFE_WAREHOUSE_VALIDATION_ENABLED`
- `CHANGESAFE_WAREHOUSE_VALIDATION_REQUIRED`
- `CHANGESAFE_WAREHOUSE_TIMEOUT_SECONDS`
- `SNOWFLAKE_ACCOUNT`
- `SNOWFLAKE_USER`
- `SNOWFLAKE_AUTHENTICATOR`
- `SNOWFLAKE_PRIVATE_KEY_PATH` or an approved secret-manager equivalent
- `SNOWFLAKE_WAREHOUSE`
- `SNOWFLAKE_DATABASE`
- `SNOWFLAKE_SCHEMA`
- `SNOWFLAKE_ROLE`
- `SNOWFLAKE_TARGET_RELATION_ALLOWLIST`

The local private environment file and hosting provider's encrypted secret store
hold actual values. The API returns capability flags and safe environment labels,
never credentials, account locators, private keys, tokens, or connection strings.

## Competition acceptance criteria

The release is ready when all of the following are demonstrated from the shared
judge URL:

1. Public configuration reports live-DataHub-first operation.
2. The dropdown discovers the current 55-field schema from live DataHub.
3. At least two materially different fields produce different field-scoped
   evidence, routes, and artifacts; score equality is explained by factors when
   it occurs.
4. Rename, Remove, and Change type each complete a live metadata run.
5. When Snowflake validation is required, each operation displays truthful
   aggregate warehouse evidence before approval becomes available.
6. A deliberately invalid rename, unsafe type conversion, missing field, and
   simulated live outage each fail closed with an actionable explanation.
7. Recorded fallback is deliberate, visibly labelled, and non-publishable under
   the live-required competition policy.
8. No raw warehouse values or credentials appear in API responses, logs,
   screenshots, artifacts, or repository history.
9. The shared app survives refresh and a lost approval response without duplicate
   publication.
10. All automated gates pass from a clean checkout, and final desktop/mobile
    screenshots and the demonstration script match the shipped behavior.

## Required external access

DataHub live-read access is already available in the local competition stack.
Warehouse validation additionally requires an operator-provided, read-only
Snowflake identity for a non-production or masked competition dataset, plus
network reachability from the application host.

If only production credentials exist, implementation stops before connection and
requires explicit owner authorization and a separately reviewed access policy.
A stable judge URL also requires a durable hosting account or custom tunnel
domain; anonymous tunnel rotation is not an acceptable final deployment.

