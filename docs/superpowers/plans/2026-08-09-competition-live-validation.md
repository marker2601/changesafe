# ChangeSafe Competition Live Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the shared judging build dynamically analyze any discovered DataHub field and fail closed on live metadata, deterministic artifact, and optional read-only Snowflake evidence before approval.

**Architecture:** Keep DataHub as the authoritative metadata and lineage source, then add a narrow `WarehouseValidationPort` after the existing sealed-artifact verifier. A Snowflake adapter executes only reviewed, single-statement aggregate `SELECT` plans against an operator-mapped non-production relation; a shared policy evaluator combines live provenance, static checks, and warehouse results into persisted approval eligibility. The React application renders those durable states and never infers that production values were checked from metadata alone.

**Tech Stack:** Python 3.12, FastAPI, Pydantic 2, SQLite/aiosqlite, sqlglot 30.15.0, Snowflake Connector for Python 4.7.1, React 19, TypeScript, Vitest, Playwright, dbt 1.10, Docker, GitHub Actions.

## Global Constraints

- Do not connect ChangeSafe to a write-capable warehouse role.
- Do not execute arbitrary model-generated or user-supplied SQL.
- Do not return, log, store, or render raw warehouse field values.
- Do not apply migrations, remove fields, merge pull requests, or alter rows.
- Do not silently switch from live DataHub to recorded evidence.
- Do not add an OpenAI model to the ChangeSafe runtime; risk, generation, validation, and approval remain deterministic.
- Pin `snowflake-connector-python==4.7.1`; do not use the yanked 4.7.0 or a 5.0 beta.
- Python remains `>=3.12,<3.13`; all existing strict mypy, Ruff, deterministic regeneration, web, Playwright, dbt, Docker, secret-scan, and CI gates remain mandatory.
- The public browser receives capability flags and a non-secret environment label only; it never receives an account locator, username, role secret, token, private-key path, or connection string.
- The operator relation map is the only source of Snowflake relations; the browser request and DataHub-returned display name cannot select a relation.
- A recorded DataHub fallback is explicit and visibly checksum-pinned; when live evidence is required it remains diagnostic and non-publishable.
- Warehouse SQL is exactly one parsed Snowflake `SELECT` or `WITH ... SELECT`, contains no comments or semicolon, and references only the selected allowlisted relation and normalized field identifiers.
- Every failure remains inspectable, but missing, stale, mismatched, partial, unsafe, or uncertain required evidence blocks approval.
- The complete 55-field recorded catalog is exercised for Rename, Remove, and Change type: 165 deterministic field-operation cases.
- Desktop at 1440 px and phone at 430 px must have no horizontal overflow, keyboard traps, artificial progress delays, or console errors.

---

## File Structure

- `apps/api/src/changesafe/warehouse/base.py`: typed warehouse port, safe errors, and connector-independent contracts.
- `apps/api/src/changesafe/warehouse/queries.py`: deterministic Snowflake validation plans and AST safety validation.
- `apps/api/src/changesafe/warehouse/snowflake.py`: official connector adapter, identity checks, bounded execution, aggregate normalization, and redaction.
- `apps/api/src/changesafe/warehouse/factory.py`: settings-to-port construction without importing Snowflake when disabled.
- `apps/api/src/changesafe/policy.py`: one approval-policy evaluator reused after analysis and immediately before approval.
- `apps/api/src/changesafe/domain.py`: persisted warehouse result, blocker, and run-state models.
- `apps/api/src/changesafe/config.py`: strict live-evidence and Snowflake configuration plus credential-safe public projection.
- `apps/api/src/changesafe/orchestrator.py`: warehouse stage and persisted policy decision.
- `apps/api/src/changesafe/publication/service.py`: current-policy, freshness, and destination checks before any side effect.
- `apps/web/src/components/WarehouseValidationPanel.tsx`: plain-language aggregate evidence and blocking reasons.
- `apps/web/src/components/RunTimeline.tsx`: persisted warehouse stage and selected-field copy.
- `apps/web/src/components/RunProvenance.tsx`: truthful DataHub/warehouse claims with stable geometry.
- `apps/web/src/components/ApprovalPanel.tsx`: exact eligibility reason and disabled approval state.
- `scripts/smoke_competition.py`: safe live DataHub and credential-conditional Snowflake smoke without mutations or raw output.
- `tests/e2e/competition-flow.spec.ts`: all-operation judge flow, warehouse states, refresh, keyboard, and responsive proof.

### Task 1: Persisted warehouse and approval-policy contracts

**Files:**
- Create: `apps/api/src/changesafe/warehouse/__init__.py`
- Create: `apps/api/src/changesafe/warehouse/base.py`
- Modify: `apps/api/src/changesafe/domain.py`
- Modify: `apps/api/src/changesafe/config.py`
- Modify: `apps/api/src/changesafe/store.py`
- Test: `apps/api/tests/test_domain.py`
- Test: `apps/api/tests/test_config.py`
- Test: `apps/api/tests/test_store.py`

**Interfaces:**
- Consumes: existing `ChangeRequest`, `ContextBundle`, `StrictModel`, `RunState`, `Settings`, and SQLite JSON persistence.
- Produces: `WarehouseValidationPort.validate(change: ChangeRequest, context: ContextBundle) -> WarehouseValidationResult`; `WarehouseValidationPort.close() -> None | Awaitable[None]`; `WarehouseValidationResult`; `ApprovalBlocker`; `RunState.VALIDATING_WAREHOUSE`; strict settings fields `live_evidence_required`, `warehouse_validation_enabled`, `warehouse_validation_required`, `warehouse_timeout_seconds`, `warehouse_evidence_max_age_seconds`, and `warehouse_environment_label`; properties `warehouse_configured` and `warehouse_target_map`.

- [ ] **Step 1: Write failing domain and persistence tests**

```python
def test_warehouse_result_forbids_raw_rows_and_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        WarehouseValidationResult.model_validate(
            {
                "status": "passed",
                "mode": "aggregate",
                "environment_label": "competition-non-production",
                "operation": "remove",
                "field": "order_status",
                "relation_fingerprint": "a" * 64,
                "started_at": "2026-08-09T12:00:00Z",
                "completed_at": "2026-08-09T12:00:01Z",
                "rows_evaluated": 20,
                "unsafe_row_count": 0,
                "query_ids": ["safe-query-id"],
                "elapsed_ms": 1000,
                "checks": [],
                "raw_rows": [{"order_status": "secret"}],
            }
        )


@pytest.mark.asyncio
async def test_store_round_trips_warehouse_result_and_blockers(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.db")
    run = await store.create(RENAME_REQUEST)
    analysis = analysis_result(
        warehouse_validation=passed_warehouse_result(),
        approval_blockers=[],
        publication_eligible=True,
    )
    await advance_to_awaiting_approval(store, run.run_id, analysis)
    restored = await store.get(run.run_id)
    assert restored is not None
    assert restored.analysis == analysis
```

- [ ] **Step 2: Run the contract tests and observe RED**

Run: `python -m pytest -q apps/api/tests/test_domain.py apps/api/tests/test_config.py apps/api/tests/test_store.py`

Expected: FAIL because the warehouse models, state, settings, and persisted fields do not exist.

- [ ] **Step 3: Add exact strict domain models**

```python
class WarehouseValidationStatus(StrEnum):
    NOT_RUN = "not_run"
    PASSED = "passed"
    BLOCKED = "blocked"


class WarehouseValidationMode(StrEnum):
    NONE = "none"
    AGGREGATE = "aggregate"


class WarehouseCheck(StrictModel):
    code: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    label: str = Field(min_length=1, max_length=120)
    passed: bool
    retryable: bool = False
    detail: str = Field(min_length=1, max_length=500)
    observed_count: int | None = Field(default=None, ge=0)


class WarehouseValidationResult(StrictModel):
    status: WarehouseValidationStatus
    mode: WarehouseValidationMode
    environment_label: str = Field(min_length=1, max_length=80)
    operation: ChangeOperation
    field: str = Field(min_length=1, max_length=128)
    relation_fingerprint: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )
    started_at: datetime | None = None
    completed_at: datetime | None = None
    rows_evaluated: int | None = Field(default=None, ge=0)
    populated_row_count: int | None = Field(default=None, ge=0)
    unsafe_row_count: int | None = Field(default=None, ge=0)
    query_ids: list[str] = Field(default_factory=list, max_length=8)
    elapsed_ms: int | None = Field(default=None, ge=0)
    checks: list[WarehouseCheck] = Field(default_factory=list, max_length=8)

    @model_validator(mode="after")
    def status_matches_evidence(self) -> WarehouseValidationResult:
        if self.status is WarehouseValidationStatus.PASSED:
            if self.mode is not WarehouseValidationMode.AGGREGATE:
                raise ValueError("passed warehouse evidence must be aggregate")
            if not self.checks or any(not check.passed for check in self.checks):
                raise ValueError("passed warehouse evidence requires passed checks")
        if self.status is WarehouseValidationStatus.NOT_RUN and (
            self.started_at is not None or self.query_ids
        ):
            raise ValueError("not-run evidence cannot claim execution")
        return self


class ApprovalBlocker(StrictModel):
    code: str = Field(pattern=r"^[A-Z][A-Z0-9_]*$")
    message: str = Field(min_length=1, max_length=500)
    retryable: bool = False
```

Add `RunState.VALIDATING_WAREHOUSE = "validating_warehouse"`. Add backward-compatible defaults to `AnalysisResult`:

```python
warehouse_validation: WarehouseValidationResult = Field(
    default_factory=lambda: WarehouseValidationResult(
        status=WarehouseValidationStatus.NOT_RUN,
        mode=WarehouseValidationMode.NONE,
        environment_label="not configured",
        operation=ChangeOperation.RENAME,
        field="unavailable",
        checks=[],
    )
)
approval_blockers: list[ApprovalBlocker] = Field(default_factory=list)
```

Do not use that generic factory for newly created analyses; orchestration must construct an operation- and field-specific result. The default exists only so stored pre-upgrade runs deserialize and then fail the current-policy approval gate.

- [ ] **Step 4: Add the connector-independent port and safe exception hierarchy**

```python
class WarehouseValidationError(RuntimeError):
    def __init__(self, code: str, public_message: str, *, retryable: bool) -> None:
        super().__init__(code)
        self.code = code
        self.public_message = public_message
        self.retryable = retryable


class WarehouseValidationPort(Protocol):
    async def validate(
        self, change: ChangeRequest, context: ContextBundle
    ) -> WarehouseValidationResult: ...

    async def close(self) -> None: ...
```

Export only `WarehouseValidationError` and `WarehouseValidationPort` from `warehouse/__init__.py`; concrete connector types stay server-internal.

- [ ] **Step 5: Add strict all-or-none Snowflake settings**

```python
live_evidence_required: bool = Field(
    default=False,
    validation_alias=AliasChoices(
        "CHANGESAFE_LIVE_EVIDENCE_REQUIRED", "live_evidence_required"
    ),
)
warehouse_validation_enabled: bool = Field(
    default=False,
    validation_alias=AliasChoices(
        "CHANGESAFE_WAREHOUSE_VALIDATION_ENABLED",
        "warehouse_validation_enabled",
    ),
)
warehouse_validation_required: bool = Field(
    default=False,
    validation_alias=AliasChoices(
        "CHANGESAFE_WAREHOUSE_VALIDATION_REQUIRED",
        "warehouse_validation_required",
    ),
)
warehouse_timeout_seconds: int = Field(
    default=20,
    ge=1,
    le=60,
    validation_alias=AliasChoices(
        "CHANGESAFE_WAREHOUSE_TIMEOUT_SECONDS", "warehouse_timeout_seconds"
    ),
)
warehouse_evidence_max_age_seconds: int = Field(
    default=900,
    ge=60,
    le=3600,
    validation_alias=AliasChoices(
        "CHANGESAFE_WAREHOUSE_EVIDENCE_MAX_AGE_SECONDS",
        "warehouse_evidence_max_age_seconds",
    ),
)
warehouse_environment_label: str = Field(
    default="competition-non-production",
    min_length=1,
    max_length=80,
    validation_alias=AliasChoices(
        "CHANGESAFE_WAREHOUSE_ENVIRONMENT_LABEL",
        "warehouse_environment_label",
    ),
)
snowflake_account: str | None = None
snowflake_user: str | None = None
snowflake_authenticator: str | None = None
snowflake_private_key_path: Path | None = None
snowflake_warehouse: str | None = None
snowflake_database: str | None = None
snowflake_schema: str | None = None
snowflake_role: str | None = None
snowflake_target_relation_allowlist: dict[str, str] = Field(default_factory=dict)
```

The model validator must reject `required=true/enabled=false`; reject a partially configured enabled adapter; require `SNOWFLAKE_AUTHENTICATOR=SNOWFLAKE_JWT`; require every relation map value to be exactly three simple identifiers; and require every map key to also be present in `DEMO_URN_ALLOWLIST`. Do not resolve or read the private-key file during settings parsing.

Public projection additions are exact booleans/labels only:

```python
"live_evidence_required": self.live_evidence_required,
"warehouse_validation_available": self.warehouse_configured,
"warehouse_validation_required": self.warehouse_validation_required,
"warehouse_environment_label": self.warehouse_environment_label,
```

- [ ] **Step 6: Extend legal state transitions and event persistence**

Change `VALIDATING` to allow `VALIDATING_WAREHOUSE`, `AWAITING_APPROVAL`, or `FAILED`; change `VALIDATING_WAREHOUSE` to allow `AWAITING_APPROVAL` or `FAILED`. Add store tests proving an illegal direct `LOADING_CONTEXT -> VALIDATING_WAREHOUSE` transition is rejected and that ordered warehouse events survive restart.

- [ ] **Step 7: Run focused tests and static gates**

Run: `python -m pytest -q apps/api/tests/test_domain.py apps/api/tests/test_config.py apps/api/tests/test_store.py`

Run: `python -m ruff check apps/api/src/changesafe/domain.py apps/api/src/changesafe/config.py apps/api/src/changesafe/store.py apps/api/src/changesafe/warehouse apps/api/tests/test_domain.py apps/api/tests/test_config.py apps/api/tests/test_store.py`

Run: `python -m mypy apps/api/src`

Expected: all PASS.

- [ ] **Step 8: Commit the contracts**

```bash
git add apps/api/src/changesafe/domain.py apps/api/src/changesafe/config.py apps/api/src/changesafe/store.py apps/api/src/changesafe/warehouse apps/api/tests/test_domain.py apps/api/tests/test_config.py apps/api/tests/test_store.py
git commit -m "feat: define warehouse validation contracts"
```

### Task 2: Deterministic, parsed Snowflake query plans

**Files:**
- Create: `apps/api/src/changesafe/warehouse/queries.py`
- Create: `apps/api/tests/warehouse/__init__.py`
- Create: `apps/api/tests/warehouse/test_queries.py`
- Modify: `apps/api/src/changesafe/warehouse/__init__.py`
- Read: `apps/api/src/changesafe/sql_types.py`

**Interfaces:**
- Consumes: `ChangeRequest`, `ContextBundle`, `ChangeOperation`, `canonical_sql_type()`, validated simple field identifiers, and a three-part operator relation.
- Produces: `WarehouseQuery(code: str, sql: str, expected_columns: tuple[str, ...])`; `WarehouseValidationPlan(relation: str, relation_fingerprint: str, queries: tuple[WarehouseQuery, ...])`; `fingerprint_relation(relation: str) -> str`; `build_validation_plan(change, context, relation) -> WarehouseValidationPlan`; `validate_read_only_query(query, relation, allowed_fields) -> None`.

- [ ] **Step 1: Write RED tests for each operation and every prohibited SQL shape**

```python
@pytest.mark.parametrize("operation", list(ChangeOperation))
def test_plan_contains_only_single_read_only_statements(operation: ChangeOperation) -> None:
    change = request_for(operation)
    plan = build_validation_plan(change, golden_context(change.field), RELATION)
    assert plan.queries
    for query in plan.queries:
        allowed = {change.field}
        if change.new_field is not None:
            allowed.add(change.new_field)
        validate_read_only_query(query, RELATION, allowed)
        assert ";" not in query.sql
        assert "--" not in query.sql
        assert "/*" not in query.sql


@pytest.mark.parametrize(
    "sql",
    [
        "select * from SAFE_DB.SAFE_SCHEMA.ORDER_DETAILS; drop table x",
        "delete from SAFE_DB.SAFE_SCHEMA.ORDER_DETAILS",
        "select cust_email from OTHER_DB.X.Y",
        "select secret_column from SAFE_DB.SAFE_SCHEMA.ORDER_DETAILS",
        "call system$wait(10)",
        "select cust_email from SAFE_DB.SAFE_SCHEMA.ORDER_DETAILS -- trusted",
    ],
)
def test_query_guard_rejects_unsafe_or_unallowlisted_sql(sql: str) -> None:
    with pytest.raises(UnsafeWarehouseQuery):
        validate_read_only_query(
            WarehouseQuery(code="probe", sql=sql, expected_columns=()),
            RELATION,
            {"cust_email"},
        )
```

Add exact tests for rename collision, mismatched `context.field`, schema type mismatch, NUMBER precision/scale, VARCHAR/BINARY length narrowing, zero-row-safe aggregates, quoting, relation-map injection, and query result aliases.

- [ ] **Step 2: Run focused query tests and observe RED**

Run: `python -m pytest -q apps/api/tests/warehouse/test_queries.py`

Expected: FAIL because `queries.py` and its contracts do not exist.

- [ ] **Step 3: Implement immutable query-plan models and identifier rendering**

```python
@dataclass(frozen=True, slots=True)
class WarehouseQuery:
    code: str
    sql: str
    expected_columns: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class WarehouseValidationPlan:
    relation: str
    relation_fingerprint: str
    queries: tuple[WarehouseQuery, ...]


def quote_identifier(value: str) -> str:
    if SIMPLE_IDENTIFIER.fullmatch(value) is None:
        raise UnsafeWarehouseQuery("Identifier is outside the supported contract")
    return f'"{value.upper()}"'
```

Render relations by splitting exactly three simple identifiers and quoting each segment. Implement `fingerprint_relation(relation)` as `sha256(normalized_three_part_relation(relation).encode()).hexdigest()`; never persist the relation itself.

- [ ] **Step 4: Implement exact operation plans**

The common schema probe is:

```sql
SELECT "CURRENT_FIELD"
FROM "DATABASE"."SCHEMA"."TABLE"
WHERE 1 = 0
```

Rename aggregate evidence is:

```sql
WITH projected AS (
  SELECT "CURRENT_FIELD" AS "PROPOSED_FIELD"
  FROM "DATABASE"."SCHEMA"."TABLE"
)
SELECT COUNT(*) AS rows_evaluated,
       COUNT("PROPOSED_FIELD") AS populated_row_count
FROM projected
```

Remove evidence is:

```sql
SELECT COUNT(*) AS rows_evaluated,
       COUNT("CURRENT_FIELD") AS populated_row_count
FROM "DATABASE"."SCHEMA"."TABLE"
```

Type-change evidence is generated only from `canonical_sql_type()` output:

```sql
SELECT COUNT(*) AS rows_evaluated,
       COUNT("CURRENT_FIELD") AS populated_row_count,
       COUNT_IF(
         "CURRENT_FIELD" IS NOT NULL AND (
           TRY_CAST("CURRENT_FIELD" AS TARGET_TYPE) IS NULL OR
           TRY_CAST(
             TRY_CAST("CURRENT_FIELD" AS TARGET_TYPE) AS CURRENT_TYPE
           ) IS DISTINCT FROM "CURRENT_FIELD"
         )
       ) AS unsafe_row_count
FROM "DATABASE"."SCHEMA"."TABLE"
```

The round-trip predicate deliberately flags silent truncation or rounding. `TARGET_TYPE` and `CURRENT_TYPE` are rendered from canonical base/parameters, never concatenated from unchecked request text.

- [ ] **Step 5: Implement the sqlglot AST guard**

Use `sqlglot.parse(sql, read="snowflake")`; require one expression and `isinstance(expression, exp.Select)`. Reject comments before parsing. Require every `exp.Table` to normalize to the one allowlisted relation; require every `exp.Column` that is not a generated output alias to be in the selected-field/destination set; reject `exp.Star`, DDL/DML nodes, external functions, anonymous functions outside the exact generated allowlist, multiple statements, and any catalog/schema qualifier inconsistent with the configured relation. Re-render with `expression.sql(dialect="snowflake")` and parse it again to prove a stable single statement.

- [ ] **Step 6: Add metamorphic query tests**

For every generated query, mutate one property at a time—table, selected field, second statement, comment, function, wildcard, subquery, join, and type token—and assert the guard rejects it. Assert both source and destination are present in the rename AST, and the type-change AST contains the exact canonical requested type.

- [ ] **Step 7: Run focused and shared type tests**

Run: `python -m pytest -q apps/api/tests/warehouse/test_queries.py apps/api/tests/test_sql_types.py apps/api/tests/test_domain.py`

Run: `python -m ruff check apps/api/src/changesafe/warehouse apps/api/tests/warehouse`

Run: `python -m mypy apps/api/src`

Expected: all PASS.

- [ ] **Step 8: Commit the reviewed query layer**

```bash
git add apps/api/src/changesafe/warehouse apps/api/tests/warehouse
git commit -m "feat: build safe warehouse validation queries"
```

### Task 3: Read-only Snowflake adapter

**Files:**
- Create: `apps/api/src/changesafe/warehouse/snowflake.py`
- Create: `apps/api/src/changesafe/warehouse/factory.py`
- Create: `apps/api/tests/warehouse/test_snowflake.py`
- Create: `apps/api/tests/warehouse/test_factory.py`
- Modify: `pyproject.toml`

**Interfaces:**
- Consumes: Task 1 port/results/settings and Task 2 `build_validation_plan()`.
- Produces: `SnowflakeWarehouseValidator(settings: Settings, connect: ConnectorFactory | None = None)` implementing `WarehouseValidationPort`; `build_warehouse_port(settings: Settings) -> WarehouseValidationPort | None`.

- [ ] **Step 1: Add the pinned optional dependency and typing override**

```toml
[project.optional-dependencies]
warehouse = ["snowflake-connector-python==4.7.1"]
```

Add `"snowflake.*"` to the existing mypy missing-import override. Install with `python -m pip install -e ".[dev,live,warehouse]"` and verify `python -c "import snowflake.connector; print(snowflake.connector.__version__)"` prints `4.7.1`.

- [ ] **Step 2: Write fake-connector RED tests**

Build small `FakeConnection`/`FakeCursor` test doubles that record connection kwargs and SQL but return only configured tuples. Tests must prove:

```python
assert connect_kwargs["role"] == "CHANGESAFE_READONLY"
assert connect_kwargs["warehouse"] == "COMPUTE_WH"
assert connect_kwargs["database"] == "SAFE_DB"
assert connect_kwargs["schema"] == "SAFE_SCHEMA"
assert connect_kwargs["session_parameters"] == {
    "QUERY_TAG": "changesafe:warehouse-validation",
    "STATEMENT_TIMEOUT_IN_SECONDS": 20,
}
assert all(sql.lstrip().upper().startswith(("SELECT", "WITH")) for sql in executed)
assert connection.closed
```

Also assert wrong role/warehouse/database/schema, missing column, duplicate column, nonzero unsafe conversions, timeout, network failure, connector messages containing credentials, and cancellation produce safe typed outcomes with no exception text or raw row data.

- [ ] **Step 3: Run adapter tests and observe RED**

Run: `python -m pytest -q apps/api/tests/warehouse/test_snowflake.py apps/api/tests/warehouse/test_factory.py`

Expected: FAIL because the adapter/factory do not exist.

- [ ] **Step 4: Implement bounded connector construction**

Use a lazily imported connector in the factory so replay images/tests do not import Snowflake when disabled. Connect inside `asyncio.to_thread` under a one-call `asyncio.Lock` with:

```python
connect(
    account=settings.snowflake_account,
    user=settings.snowflake_user,
    authenticator="SNOWFLAKE_JWT",
    private_key_file=str(settings.snowflake_private_key_path),
    warehouse=settings.snowflake_warehouse,
    database=settings.snowflake_database,
    schema=settings.snowflake_schema,
    role=settings.snowflake_role,
    login_timeout=settings.warehouse_timeout_seconds,
    network_timeout=settings.warehouse_timeout_seconds,
    socket_timeout=settings.warehouse_timeout_seconds,
    client_session_keep_alive=False,
    session_parameters={
        "QUERY_TAG": "changesafe:warehouse-validation",
        "STATEMENT_TIMEOUT_IN_SECONDS": settings.warehouse_timeout_seconds,
    },
)
```

Do not enable secondary roles. Never set autocommit for a write path; the adapter executes only guarded SELECT statements and closes the cursor/connection in `finally`.

- [ ] **Step 5: Verify exact active session identity before the relation query**

Execute exactly:

```sql
SELECT CURRENT_ROLE(), CURRENT_WAREHOUSE(), CURRENT_DATABASE(), CURRENT_SCHEMA()
```

Compare all four returned identifiers case-insensitively with configured values. A missing or multiple row, `None`, or mismatch returns a non-retryable `warehouse_identity` failed check and executes no relation query.

- [ ] **Step 6: Normalize only aggregate results**

Map cursor descriptions to the expected aliases, require exactly one row for each aggregate query, require integer nonnegative counts, require `populated_row_count <= rows_evaluated`, and require `unsafe_row_count <= populated_row_count`. Copy only the cursor `sfqid`; never copy row values, SQL, relation, account, or connector exceptions into `WarehouseValidationResult`. Use the schema probe cursor description to require exactly one source column and canonical type equality with `context.field_type`.

- [ ] **Step 7: Classify safe failures**

- Authentication, identity, relation, schema, unsupported contract, malformed response, or unsafe query: non-retryable and blocked.
- Connector transport, server unavailable, or timeout: retryable and blocked.
- `unsafe_row_count > 0`: non-retryable and blocked with the count only.
- Zero rows/all-null rows: valid aggregate evidence for rename/remove; type change passes only when unsafe count is zero, with the empty/all-null limitation stated.

All exception logging must be `logger.warning("Warehouse validation failed", extra={"code": code})` without `exc_info`, `str(exc)`, connection kwargs, SQL, or identifiers.

- [ ] **Step 8: Run adapter, security, and static gates**

Run: `python -m pytest -q apps/api/tests/warehouse`

Run: `python -m ruff check apps/api/src/changesafe/warehouse apps/api/tests/warehouse pyproject.toml`

Run: `python -m mypy apps/api/src`

Run: `python scripts/check_secrets.py`

Expected: all PASS, and fake logs contain none of the injected secret strings.

- [ ] **Step 9: Commit the adapter**

```bash
git add pyproject.toml apps/api/src/changesafe/warehouse apps/api/tests/warehouse
git commit -m "feat: validate changes with read-only Snowflake"
```

### Task 4: Orchestration, fail-closed policy, API, and approval recheck

**Files:**
- Create: `apps/api/src/changesafe/policy.py`
- Create: `apps/api/tests/test_policy.py`
- Modify: `apps/api/src/changesafe/orchestrator.py`
- Modify: `apps/api/src/changesafe/api.py`
- Modify: `apps/api/src/changesafe/publication/service.py`
- Modify: `apps/api/tests/test_orchestrator.py`
- Modify: `apps/api/tests/test_api.py`
- Modify: `apps/api/tests/publication/test_service.py`

**Interfaces:**
- Consumes: Task 1 models/settings, Task 3 factory/port, DataHub context provenance, existing static verifier/risk/impact checks.
- Produces: `evaluate_approval_policy(...) -> list[ApprovalBlocker]`; `create_app(..., warehouse_port: WarehouseValidationPort | None = None)`; persisted `validating_warehouse` events and truthful eligibility.

- [ ] **Step 1: Write policy truth-table tests first**

```python
@pytest.mark.parametrize(
    ("context_mode", "warehouse_status", "require_live", "require_warehouse", "codes"),
    [
        ("live", "passed", True, True, set()),
        ("snapshot", "passed", True, True, {"LIVE_EVIDENCE_REQUIRED"}),
        ("live", "not_run", True, True, {"WAREHOUSE_EVIDENCE_REQUIRED"}),
        ("live", "blocked", True, True, {"WAREHOUSE_VALIDATION_FAILED"}),
        ("snapshot", "not_run", False, False, set()),
    ],
)
def test_approval_policy_matrix(...):
    blockers = evaluate_approval_policy(...)
    assert {item.code for item in blockers} == codes
```

Add freshness tests at exactly max age, one second over max age, relation fingerprint/config drift, static validation failure, and pre-upgrade default warehouse result.

- [ ] **Step 2: Add RED orchestrator/API/publication tests**

Tests must prove: required warehouse pass reaches `awaiting_approval`; missing/failed/timeout result preserves analysis in `failed`; optional disabled validation truthfully records `not_run`; explicit replay fallback is non-publishable when live is required; API closes the warehouse port; public config exposes no credentials; approval rechecks policy/freshness before transition; a stale passed result cannot publish; no external publisher/writeback receives a call on any blocker.

- [ ] **Step 3: Run focused tests and observe RED**

Run: `python -m pytest -q apps/api/tests/test_policy.py apps/api/tests/test_orchestrator.py apps/api/tests/test_api.py apps/api/tests/publication/test_service.py`

Expected: FAIL because policy evaluation and warehouse orchestration are absent.

- [ ] **Step 4: Implement one shared policy evaluator**

```python
def evaluate_approval_policy(
    *,
    change: ChangeRequest,
    context: ContextBundle,
    validation: ValidationReport,
    warehouse: WarehouseValidationResult,
    require_live_evidence: bool,
    require_warehouse: bool,
    warehouse_max_age_seconds: int,
    expected_relation_fingerprint: str | None,
    now: datetime | None = None,
) -> list[ApprovalBlocker]:
    ...
```

Return blockers in stable order: static verification, request/context identity, live provenance, warehouse presence/status, warehouse operation/field identity, relation fingerprint, then freshness. Compare `context.target_urn == change.asset_urn` and `context.field == change.field` even though the adapter already enforces them.

- [ ] **Step 5: Insert the durable warehouse stage**

After sealed static verification succeeds:

1. Construct a selected-operation/field `not_run` result.
2. If a warehouse port exists, transition to `VALIDATING_WAREHOUSE`, call it once, and persist its result.
3. Evaluate policy and set `publication_eligible = validation.passed and not blockers`.
4. If blockers exist, persist the complete analysis in `FAILED` with the first stable blocker code/message/retryability.
5. Otherwise transition to `AWAITING_APPROVAL`.

Never run Snowflake if static verification failed. Never silently turn a failed warehouse attempt into `not_run`.

- [ ] **Step 6: Wire factory and lifecycle into FastAPI**

Add `warehouse_port` dependency injection to `create_app`; when the argument is omitted call `build_warehouse_port(active_settings)`. Store it on `app.state`, pass it to the orchestrator, and await its `close()` after `orchestrator.wait_for_idle()` during lifespan shutdown. Public config continues to come only from `Settings.public_config()`.

- [ ] **Step 7: Re-run policy immediately before approval**

Extend `PublicationService._require_current_policy` to call `evaluate_approval_policy` with current time and current configured relation fingerprint. Require the recomputed blockers to equal the persisted blocker list and be empty. This check runs before completed-receipt reuse, intent binding, state transition, GitHub, or DataHub writeback.

- [ ] **Step 8: Run focused tests and full API gate**

Run: `python -m pytest -q apps/api/tests/test_policy.py apps/api/tests/test_orchestrator.py apps/api/tests/test_api.py apps/api/tests/publication/test_service.py`

Run: `python -m pytest -q -W error::pytest.PytestUnhandledThreadExceptionWarning`

Run: `python -m ruff check .`

Run: `python -m mypy apps/api/src`

Expected: all tests PASS; the only permitted warning is the already documented third-party DataHub experimental warning.

- [ ] **Step 9: Commit orchestration and approval policy**

```bash
git add apps/api/src/changesafe/policy.py apps/api/src/changesafe/orchestrator.py apps/api/src/changesafe/api.py apps/api/src/changesafe/publication/service.py apps/api/tests/test_policy.py apps/api/tests/test_orchestrator.py apps/api/tests/test_api.py apps/api/tests/publication/test_service.py
git commit -m "feat: gate approval on persisted live evidence"
```

### Task 5: Exhaustive field-operation and failure-boundary proof

**Files:**
- Create: `apps/api/tests/test_competition_matrix.py`
- Create: `apps/api/tests/warehouse/test_security_boundaries.py`
- Modify: `apps/api/tests/context/test_live_mapping.py`
- Modify: `apps/api/tests/test_verification.py`
- Modify: `apps/api/tests/test_risk.py`
- Modify: `apps/api/tests/publication/test_service.py`

**Interfaces:**
- Consumes: the 55-field recorded `SchemaCatalog`, replay context, deterministic generator/verifier, query planner, warehouse result, and current publication service.
- Produces: executable proof that no field-name preset controls scoring or artifacts and every uncertainty boundary fails closed.

- [ ] **Step 1: Write the exact 165-case matrix**

```python
SNAPSHOT = Path("fixtures/datahub/golden-context.json")
RECORDED_FIELDS = [
    SchemaField.model_validate(item)
    for item in json.loads(SNAPSHOT.read_text(encoding="utf-8"))["schema_fields"]
]


def alternate_type(current: str) -> str:
    base, _ = canonical_sql_type(current)
    return "NUMBER(38,0)" if base == "VARCHAR" else "VARCHAR(320)"


def valid_change_for(field: SchemaField, operation: ChangeOperation) -> ChangeRequest:
    common = {
        "asset_urn": DEMO_TARGET_URN,
        "operation": operation,
        "field": field.name,
        "source_commit": f"matrix-{field.name}-{operation.value}",
        "requested_by": "competition-matrix",
    }
    if operation is ChangeOperation.RENAME:
        return ChangeRequest(**common, new_field=f"changesafe_{field.name}")
    if operation is ChangeOperation.TYPE_CHANGE:
        return ChangeRequest(
            **common,
            old_type=field.data_type,
            new_type=alternate_type(field.data_type),
        )
    return ChangeRequest(**common)


@pytest.mark.parametrize("field", RECORDED_FIELDS, ids=lambda field: field.name)
@pytest.mark.parametrize("operation", list(ChangeOperation))
@pytest.mark.asyncio
async def test_every_recorded_field_operation_is_deterministic(
    field: SchemaField, operation: ChangeOperation
) -> None:
    change = valid_change_for(field, operation)
    context = await ReplayDataHubContext.from_default().load(change)
    risk = score_change(change, context)
    generator = ArtifactGenerationService()
    first = await generator.generate(change, context, risk)
    second = await generator.generate(change, context, risk)
    validation = verify_artifacts(first, change, context)
    manifest = json.loads(first.files["changesafe-manifest.json"].content)
    assert first == second
    assert validation.passed
    assert manifest["change"] == change.model_dump(mode="json")
    assert manifest["context"]["field"] == field.name
    assert manifest["context"]["field_type"] == field.data_type
```

For rename use a deterministic `changesafe_<field>` destination and assert case-insensitive non-collision. For remove send no irrelevant fields. For type change send exact `old_type=field.data_type` and the alternate type.

- [ ] **Step 2: Observe RED against any lingering field-specific assumption**

Run: `python -m pytest -q apps/api/tests/test_competition_matrix.py -x`

Expected: any hard-coded `cust_email`, fixed source relation, or stale fixture expectation fails with the exact field/operation id; otherwise the new test itself fails until its helpers/contracts are completed.

- [ ] **Step 3: Add request-boundary parametrization**

Cover empty/1/128/129 characters, invalid first characters, whitespace, quotes, Unicode, controls, case-insensitive rename equality/collision, irrelevant operation fields, missing fields, extra properties, type aliases/no-ops, and every minimum/maximum/invalid bound supported by `canonical_sql_type()`. Each invalid case must fail at `ChangeRequest.model_validate` or the context-bound generation gate before producing an eligible package.

- [ ] **Step 4: Add live evidence adversarial tests**

Extend the realistic DataHub 1.7 envelopes with wrong entity/schema URNs, unknown/duplicate/null-type fields, nested fields, unsupported quoted top-level fields, empty/repeated/inconsistent pages, degree-only and concrete lineage, missing endpoints, missing ownership/governance/usage, authorization, timeout, transport, and explicit snapshot fallback. Assert no lineage/query calls occur after a schema identity failure.

- [ ] **Step 5: Add warehouse security boundaries**

Inject values such as `customer@example.com`, private-key text, account locator, connector DSN, SQL comments, and a second statement into fake exceptions/results. Assert none appears in `WarehouseValidationResult.model_dump_json()`, `RunView.model_dump_json()`, SQLite bytes, `caplog.text`, API responses, or artifacts. Cover invalid credential, wrong identity, missing relation/field, schema drift, zero rows, all-null rows, unsafe conversion, VARCHAR and NUMBER narrowing, timeout/cancel, malformed aggregate, and unexpected multiple rows.

- [ ] **Step 6: Retain publication/recovery invariants**

Parameterize required-warehouse failures through duplicate approval, lost response, terminal SSE closure, process restart at each publication checkpoint, partial external completion, destination drift, retryability, completed reuse, and exact artifact-byte publication. Assert warehouse failure always produces zero mutation calls.

- [ ] **Step 7: Run the matrix and full backend gates**

Run: `python -m pytest -q apps/api/tests/test_competition_matrix.py apps/api/tests/warehouse/test_security_boundaries.py`

Run: `python -m pytest -q`

Run: `python -m ruff check .`

Run: `python -m mypy apps/api/src`

Run: `python scripts/regenerate_examples.py --check`

Run: `python scripts/check_secrets.py`

Expected: 165/165 matrix cases plus every existing test PASS; secret scan prints no tracked credential finding.

- [ ] **Step 8: Commit the proof matrix**

```bash
git add apps/api/tests/test_competition_matrix.py apps/api/tests/warehouse/test_security_boundaries.py apps/api/tests/context/test_live_mapping.py apps/api/tests/test_verification.py apps/api/tests/test_risk.py apps/api/tests/publication/test_service.py
git commit -m "test: prove every field operation fails safely"
```

### Task 6: Truthful live-validation interface

**Files:**
- Create: `apps/web/src/components/WarehouseValidationPanel.tsx`
- Create: `apps/web/tests/WarehouseValidationPanel.test.tsx`
- Modify: `apps/web/src/types.ts`
- Modify: `apps/web/src/fixtures.ts`
- Modify: `apps/web/src/App.tsx`
- Modify: `apps/web/src/components/ChangeForm.tsx`
- Modify: `apps/web/src/components/RunTimeline.tsx`
- Modify: `apps/web/src/components/RunProvenance.tsx`
- Modify: `apps/web/src/components/ApprovalPanel.tsx`
- Modify: `apps/web/src/components/CommandRail.tsx`
- Modify: `apps/web/src/styles.css`
- Modify: `apps/web/tests/App.test.tsx`
- Modify: `apps/web/tests/ChangeForm.test.tsx`
- Modify: `apps/web/tests/RunTimeline.test.tsx`
- Modify: `apps/web/tests/RunProvenance.test.tsx`
- Modify: `apps/web/tests/ApprovalPanel.test.tsx`

**Interfaces:**
- Consumes: backend `WarehouseValidationResult`, `ApprovalBlocker`, `RunState.VALIDATING_WAREHOUSE`, and four new public config properties.
- Produces: visible live/recorded/warehouse truth, a persisted warehouse timeline stage, an inspectable aggregate panel, and exact approval blocking copy.

- [ ] **Step 1: Extend TypeScript contracts and fixtures, then observe RED**

Add exact string unions matching Python and make pre-upgrade fixture fields explicit rather than optional:

```ts
export type WarehouseValidationStatus = "not_run" | "passed" | "blocked";
export type WarehouseValidationMode = "none" | "aggregate";

export interface WarehouseCheck {
  code: string;
  label: string;
  passed: boolean;
  retryable: boolean;
  detail: string;
  observed_count: number | null;
}

export interface WarehouseValidationResult {
  status: WarehouseValidationStatus;
  mode: WarehouseValidationMode;
  environment_label: string;
  operation: ChangeOperation;
  field: string;
  relation_fingerprint: string | null;
  started_at: string | null;
  completed_at: string | null;
  rows_evaluated: number | null;
  populated_row_count: number | null;
  unsafe_row_count: number | null;
  query_ids: string[];
  elapsed_ms: number | null;
  checks: WarehouseCheck[];
}
```

Run: `pnpm --filter @changesafe/web typecheck`

Expected: FAIL until every fixture and consumer handles the new fields/state.

- [ ] **Step 2: Write component behavior tests before components**

Test these exact visible claims:

- `Live DataHub metadata checked` only for live provenance.
- `Recorded DataHub evidence checked` plus checksum/retrieval time after fallback.
- `Warehouse values checked · competition-non-production` only for passed aggregate evidence.
- `Production rows not queried` for `not_run`, snapshot, or blocked-before-query results.
- Aggregate counts render with labels; no source value, SQL, relation, account, or query text renders.
- Approval is disabled and the first `approval_blocker.message` is visible when ineligible.
- Failed evidence still exposes artifacts, static checks, warehouse checks, Retry/New analysis as applicable.

- [ ] **Step 3: Implement `WarehouseValidationPanel`**

Render a semantic `<section aria-labelledby="warehouse-validation-heading">` with status icon/text, environment label, operation/field, aggregate counts, elapsed time, and an ordered check list. Show query identifiers only inside a collapsed `details` element named `Technical audit identifiers`. Never render the relation fingerprint; it is an API/policy binding, not useful judge copy.

- [ ] **Step 4: Make form and provenance copy state-derived**

Before analysis, use schema hook provenance: `Live DataHub schema`, `Recorded DataHub schema`, `Loading DataHub schema`, or `Schema unavailable`. After analysis, use persisted context and warehouse result. Reserve one fixed-height truth row in every hero state so Analyze does not resize the header/hero. Remove all generic wording that could imply production rows were checked.

- [ ] **Step 5: Add a real persisted warehouse stage to the timeline**

Insert `Validating aggregate warehouse evidence` after static artifact validation only when `config.warehouse_validation_required` or an event/result exists. `activeIndex`, `phaseIndex`, interruption recovery, and event metadata must use `validating_warehouse`. Replace the remaining hard-coded `cust_email` base label with the `field` prop. A failed warehouse stage is `Interrupted`, never `Complete`.

- [ ] **Step 6: Gate approval and command summary from persisted policy**

`ApprovalPanel` uses `run.analysis.publication_eligible` and `approval_blockers`; state alone is insufficient. Button text remains `Approve preview`/`Publish approved change`, but it is disabled whenever blockers exist. The note says the exact first blocker; it never says “all checks passed” when only static checks passed. `CommandRail` displays static checks and a separate warehouse badge instead of inflating the existing 12/12 count.

- [ ] **Step 7: Add accessibility and responsive styling**

Use existing design tokens, strong contrast, wrapping count rows, `min-width: 0`, and a single-column panel below 430 px. Status is conveyed by text/icon as well as color. Keep focus visible, details keyboard-operable, and reduced-motion behavior unchanged. Do not add fake timers, progress percentages, skeleton delay, or animated completion.

- [ ] **Step 8: Run the full web gate**

Run: `pnpm --filter @changesafe/web test --run`

Run: `pnpm --filter @changesafe/web lint`

Run: `pnpm --filter @changesafe/web typecheck`

Run: `pnpm --filter @changesafe/web build`

Expected: all PASS; no snapshot relies on obsolete `cust_email` or static warehouse claims.

- [ ] **Step 9: Commit the interface**

```bash
git add apps/web/src apps/web/tests
git commit -m "feat: show truthful live validation evidence"
```

### Task 7: Runtime packaging, private configuration template, and conditional smoke

**Files:**
- Create: `scripts/smoke_competition.py`
- Create: `apps/api/tests/test_smoke_competition.py`
- Modify: `.env.example`
- Modify: `Dockerfile`
- Modify: `docker-compose.yml`
- Modify: `.github/workflows/ci.yml`
- Modify: `README.md`
- Modify outside Git: `C:/Users/harik/ChangeSafe/private/changesafe.env`

**Interfaces:**
- Consumes: Task 3 optional dependency/factory, Task 4 public config/API, existing DataHub live settings, and the official showcase-ecommerce URN.
- Produces: a container that can run live DataHub plus read-only Snowflake, an operator-safe local placeholder file, and a no-mutation competition smoke.

- [ ] **Step 1: Write smoke tests before the script**

Tests inject fake HTTP and warehouse ports and assert `--datahub-only` never imports Snowflake, default mode performs no external mutation, unsafe/missing required warehouse configuration exits nonzero with a safe message, and JSON output contains only status/count/provenance identifiers.

- [ ] **Step 2: Add documented placeholders**

Append these exact entries to `.env.example` with empty values and comments describing the JSON relation map:

```dotenv
# Competition approval evidence policy
CHANGESAFE_LIVE_EVIDENCE_REQUIRED=false
CHANGESAFE_WAREHOUSE_VALIDATION_ENABLED=false
CHANGESAFE_WAREHOUSE_VALIDATION_REQUIRED=false
CHANGESAFE_WAREHOUSE_TIMEOUT_SECONDS=20
CHANGESAFE_WAREHOUSE_EVIDENCE_MAX_AGE_SECONDS=900
CHANGESAFE_WAREHOUSE_ENVIRONMENT_LABEL=competition-non-production

# Read-only Snowflake key-pair identity; server-side only
SNOWFLAKE_ACCOUNT=
SNOWFLAKE_USER=
SNOWFLAKE_AUTHENTICATOR=SNOWFLAKE_JWT
SNOWFLAKE_PRIVATE_KEY_PATH=
SNOWFLAKE_WAREHOUSE=
SNOWFLAKE_DATABASE=
SNOWFLAKE_SCHEMA=
SNOWFLAKE_ROLE=
# JSON: {"urn:li:dataset:(...)":"DATABASE.SCHEMA.TABLE"}
SNOWFLAKE_TARGET_RELATION_ALLOWLIST={}
```

The committed template, Compose file, settings aliases, CI secrets, and private file must all use these exact names; do not introduce an unprefixed `LIVE_EVIDENCE_REQUIRED` variant.

- [ ] **Step 3: Patch the existing private file without exposing its contents**

Use `apply_patch` to append only missing Snowflake keys to `C:/Users/harik/ChangeSafe/private/changesafe.env`. Preserve every existing line/value, keep enabled/required/live-required false until credentials and relation identity are supplied, and confirm only the key names with:

```powershell
Get-Content 'C:/Users/harik/ChangeSafe/private/changesafe.env' |
  ForEach-Object { ($_ -split '=', 2)[0] } |
  Where-Object { $_ -match 'WAREHOUSE|SNOWFLAKE|LIVE_EVIDENCE' }
```

Never print the values.

- [ ] **Step 4: Package the connector only in the server image**

Change Docker install to `python -m pip install --no-cache-dir ".[live,warehouse]"`. Pass the non-secret flags and secret settings through Compose without defaults that accidentally enable validation. The private-key file is mounted read-only by the operator; do not bake or COPY it into the image.

- [ ] **Step 5: Implement `smoke_competition.py`**

The script must:

1. load `Settings` through the normal private env path;
2. require AUTO or LIVE for `--require-live-datahub`;
3. discover the schema and assert 55 unique concrete fields;
4. run Rename, Remove, and Change type on three selected catalog fields through the API/orchestrator path;
5. assert live provenance when requested, 7 sealed artifacts, 12/12 static checks, and expected warehouse policy;
6. approve preview only, with GitHub/DataHub mutations forced off in the smoke process;
7. print a safe JSON summary of field, operation, context mode, lineage counts, deterministic score, warehouse status/counts, and receipt mode.

No credential, SQL, relation, raw field value, or exception string may be printed.

- [ ] **Step 6: Add credential-conditional CI**

Install `.[dev,live,warehouse]` in quality. Keep default CI replay/warehouse-disabled. In `optional-live-readiness`, map Snowflake secrets only from GitHub secrets, and run `python scripts/smoke_competition.py --require-live-datahub --require-warehouse` only when every required Snowflake secret is nonempty. Pull requests without secrets must explicitly report the safe skip and still run fake-adapter/security tests.

- [ ] **Step 7: Document where each value comes from**

README table:

- DataHub URL/token: self-hosted GMS or DataHub Cloud admin/service-account token; live metadata only.
- Snowflake account/user: account identifier and dedicated service user.
- Authenticator/private key: `SNOWFLAKE_JWT` and operator-mounted PKCS#8 private key whose public key is assigned to that user.
- Warehouse/database/schema/role: dedicated non-production compute and exact read-only role with `USAGE` plus `SELECT` only on the mapped relation.
- Relation map: DataHub URN to exact three-part Snowflake relation, configured server-side.
- GitHub/admin token: needed only if owner deliberately enables publication; unnecessary for preview judging.

State plainly that the DataHub token is required for live judging but not for credential-free replay, and Snowflake is required only when the warehouse-required flag is true.

- [ ] **Step 8: Run packaging gates**

Run: `python -m pytest -q apps/api/tests/test_smoke_competition.py`

Run: `python scripts/smoke_competition.py --datahub-only` using the local live DataHub stack.

Run: `docker compose config`

Run: `docker build -t changesafe:competition .`

Run: `python scripts/check_secrets.py`

Expected: all PASS; `docker history changesafe:competition` and `docker inspect` contain no private-key bytes or secret values.

- [ ] **Step 9: Commit packaging and operator guidance**

```bash
git add .env.example Dockerfile docker-compose.yml .github/workflows/ci.yml README.md scripts/smoke_competition.py apps/api/tests/test_smoke_competition.py
git commit -m "build: package competition live validation"
```

Do not add the private environment file to Git.

### Task 8: Judge-flow browser acceptance and public proof

**Files:**
- Create: `tests/e2e/competition-flow.spec.ts`
- Modify: `tests/e2e/golden-flow.spec.ts`
- Modify: `tests/e2e/capture-screenshots.spec.ts`
- Modify: `docs/demo-script.md`
- Modify: `docs/architecture.md`
- Modify: `docs/devpost-submission.md`
- Modify: `design-qa.md`
- Modify: `docs/screenshots/changesafe-desktop-replay.png`
- Modify: `docs/screenshots/changesafe-mobile-replay.png`
- Create: `docs/screenshots/changesafe-desktop-live-validation.png`
- Create: `docs/screenshots/changesafe-mobile-live-validation.png`

**Interfaces:**
- Consumes: final API/UI, local live DataHub, optional Snowflake credentials, persisted browser session recovery, and the existing screenshot harness.
- Produces: repeatable Rename/Remove/Change type judge proof and truthful desktop/mobile evidence.

- [ ] **Step 1: Write RED Playwright flows for all operations**

Use the actual Current field combobox and keyboard selection, not direct API payloads:

```ts
for (const scenario of [
  { field: "cust_email", operation: "Rename", destination: "primary_email" },
  { field: "order_status", operation: "Remove" },
  { field: "order_total", operation: "Change type", newType: "VARCHAR(320)" },
]) {
  test(`${scenario.operation} uses selected-field evidence`, async ({ page }) => {
    await page.goto("/");
    await selectFieldByKeyboard(page, scenario.field);
    await chooseOperation(page, scenario.operation);
    await completeOperationFields(page, scenario);
    await page.getByRole("button", { name: "Analyze change" }).click();
    await expect(page.getByText(scenario.field, { exact: false })).toBeVisible();
    await expect(page.getByRole("heading", { name: /Warehouse validation/i })).toBeVisible();
  });
}
```

Add invalid rename collision, unsafe type result, missing field, simulated live outage with explicit fallback, warehouse timeout, failed required validation, approval enabled only after pass, refresh in `validating_warehouse`, terminal SSE EOF, and lost approval response.

- [ ] **Step 2: Run Playwright and observe RED**

Run: `pnpm exec playwright test tests/e2e/competition-flow.spec.ts --project=chromium`

Expected: FAIL until all state/copy/accessibility expectations are wired.

- [ ] **Step 3: Complete only test-discovered integration fixes**

Fix actual API/UI integration defects exposed by the RED tests; do not add sleeps, mocked percentage progress, field-name branches, or copy that claims warehouse values when the result is `not_run`/blocked.

- [ ] **Step 4: Add desktop and phone geometry/keyboard assertions**

At 1440 px and 430 px assert `document.documentElement.scrollWidth === document.documentElement.clientWidth`, hero bounding-box height differs by less than 1 px before/after analysis, every route/drawer is reachable by keyboard, modal focus returns, reduced motion removes travelling-light decoration, and browser console/error arrays stay empty.

- [ ] **Step 5: Run the complete release gate from a clean tree**

Run: `python -m pytest -q -W error::pytest.PytestUnhandledThreadExceptionWarning`

Run: `python -m ruff check .`

Run: `python -m mypy apps/api/src`

Run: `python scripts/regenerate_examples.py --check`

Run: `python scripts/check_secrets.py`

Run: `pnpm --filter @changesafe/web lint`

Run: `pnpm --filter @changesafe/web typecheck`

Run: `pnpm --filter @changesafe/web test --run`

Run: `pnpm --filter @changesafe/web build`

Run: `pnpm exec playwright test`

Run: `dbt parse --project-dir fixtures/dbt_project --profiles-dir fixtures/dbt_project`

Run: `dbt build --project-dir fixtures/dbt_project --profiles-dir fixtures/dbt_project`

Run: `docker build -t changesafe:release .`

Run: the container-smoke commands from `.github/workflows/ci.yml`.

Expected: every command PASS and `git diff --check` reports no whitespace errors.

- [ ] **Step 6: Run final live evidence smoke**

With local DataHub credentials, run all three operations and record the actual returned field, type, 6 upstream routes, field-specific downstream count, factor ledger, seven artifacts, 12/12 static checks, and live provenance. If read-only Snowflake credentials have been supplied, also run `--require-warehouse` and record aggregate counts/status. If they have not been supplied, state `Production rows not queried` and do not claim competition warehouse proof.

- [ ] **Step 7: Regenerate truthful screenshots after the final source change**

Capture overview and lower evidence/approval states at 1440 px and 430 px from the final built image. The live screenshots must visibly show Live DataHub and passed non-production warehouse evidence; if Snowflake access is unavailable, do not create or label live-warehouse screenshots. Verify PNG dimensions and capture timestamps after the final commit.

- [ ] **Step 8: Update judge copy and demonstration script**

Describe the product in plain language: a reviewer selects any DataHub field, ChangeSafe traces exact metadata routes, computes a deterministic factor score, generates a compatibility shim, verifies exact bytes, optionally checks aggregate non-production warehouse safety, and pauses for owner approval. Include the three operation walkthrough, the invalid examples, replay limitation, no-raw-data guarantee, and current 55-field counts. Remove obsolete scores, counts, URLs, headers, screenshots, or claims.

- [ ] **Step 9: Recreate shared judge deployment in live-first mode**

Recreate the shared container with `CHANGESAFE_MODE=auto`, live DataHub server credentials, mutation flags false, and warehouse flags matching actual configured access. Verify `/api/public-config`, `/healthz`, schema discovery, all three operations, approval preview, patch download, refresh, and activity panel through the public origin.

The existing anonymous localhost.run address is a temporary QA link only. A final stable URL requires the user's hosting account/custom tunnel domain; do not call an anonymous rotating URL the judge deployment.

- [ ] **Step 10: Commit final proof and docs**

```bash
git add tests/e2e docs design-qa.md
git commit -m "docs: prove competition live validation"
```

### Task 9: Independent release review, merge, and publish

**Files:**
- Review: all files changed since `2e70d94`
- Modify only for verified review findings.

**Interfaces:**
- Consumes: Tasks 1–8 and their green gates.
- Produces: independently reviewed master, pushed GitHub repository, and a precise external-access handoff.

- [ ] **Step 1: Request two-stage review**

Dispatch one fresh reviewer for spec compliance and one fresh reviewer for code quality/security. They must inspect the actual diff and reproduce important findings, especially SQL query safety, raw-data redaction, persisted-policy freshness, DataHub/warehouse identity binding, browser claims, and public screenshots.

- [ ] **Step 2: Fix findings with RED/GREEN tests**

For each reproduced Critical or Important finding, add the smallest failing regression, observe RED, implement the fix, observe GREEN, rerun the affected full gate, and commit a scoped fix. Do not waive a failing gate as “demo only.”

- [ ] **Step 3: Verify repository state and history safety**

Run:

```powershell
git status --short
git diff --check 2e70d94..HEAD
git log --oneline --decorate -20
python scripts/check_secrets.py
```

Expected: clean worktree, clean diff, understandable scoped commits, and no tracked credentials/private keys.

- [ ] **Step 4: Push master only after every gate is green**

```powershell
git push origin master
```

Verify the remote SHA equals local `git rev-parse HEAD` and the GitHub Actions workflow is green. Do not force-push or rewrite the user's history.

- [ ] **Step 5: Final handoff**

Provide the stable repository URL, current shared/stable judge URL, exact test commands, current live DataHub/Snowflake status, and only the missing external access items. Explain that DataHub access proves metadata/lineage and Snowflake access proves aggregate value compatibility; neither authorizes data or catalog mutation.
