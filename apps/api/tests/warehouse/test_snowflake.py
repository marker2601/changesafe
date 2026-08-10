from __future__ import annotations

import asyncio
import logging
import time
from collections import namedtuple
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest
from snowflake.connector.errors import (
    BadGatewayError,
    InternalServerError,
    OtherHTTPRetryableError,
    RequestExceedMaxRetryError,
)

from changesafe.config import Settings
from changesafe.demo import DEMO_TARGET_URN
from changesafe.domain import (
    ChangeOperation,
    ChangeRequest,
    ContextBundle,
    ContextMode,
    ContextProvenance,
    SchemaField,
    WarehouseValidationStatus,
)
from changesafe.warehouse.snowflake import SnowflakeWarehouseValidator

RELATION = "SAFE_DB.SAFE_SCHEMA.ORDER_DETAILS"
IDENTITY_SQL = (
    "SELECT CURRENT_ROLE(), CURRENT_WAREHOUSE(), CURRENT_DATABASE(), CURRENT_SCHEMA()"
)
Metadata = namedtuple(
    "Metadata",
    (
        "name",
        "type_code",
        "display_size",
        "internal_size",
        "precision",
        "scale",
        "is_nullable",
    ),
)


class CursorResponse:
    def __init__(
        self,
        *,
        rows: Sequence[Sequence[object]] = (),
        description: Sequence[object] | None = (),
        sfqid: str | None = None,
        error: BaseException | None = None,
    ) -> None:
        self.rows = rows
        self.description = description
        self.sfqid = sfqid
        self.error = error


class FakeCursor:
    def __init__(
        self, responses: Sequence[CursorResponse], executed: list[str]
    ) -> None:
        self._responses = list(responses)
        self._executed = executed
        self._active: CursorResponse | None = None
        self.closed = False

    @property
    def description(self) -> Sequence[object] | None:
        return None if self._active is None else self._active.description

    @property
    def sfqid(self) -> str | None:
        return None if self._active is None else self._active.sfqid

    def execute(self, sql: str) -> FakeCursor:
        self._executed.append(sql)
        if not self._responses:
            raise AssertionError("unexpected query")
        self._active = self._responses.pop(0)
        if self._active.error is not None:
            raise self._active.error
        return self

    def fetchall(self) -> Sequence[Sequence[object]]:
        if self._active is None:
            raise AssertionError("fetch before execute")
        return self._active.rows

    def close(self) -> None:
        self.closed = True


class FakeConnection:
    def __init__(self, responses: Sequence[CursorResponse]) -> None:
        self.executed: list[str] = []
        self.cursor_instance = FakeCursor(responses, self.executed)
        self.closed = False

    def cursor(self) -> FakeCursor:
        return self.cursor_instance

    def close(self) -> None:
        self.closed = True


class ConnectSpy:
    def __init__(
        self,
        connection: FakeConnection | None = None,
        *,
        error: BaseException | None = None,
    ) -> None:
        self.connection = connection
        self.error = error
        self.calls: list[dict[str, Any]] = []

    def __call__(self, **kwargs: Any) -> FakeConnection:
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        if self.connection is None:
            raise AssertionError("connection was not configured")
        return self.connection


def settings() -> Settings:
    return Settings(
        _env_file=None,
        warehouse_validation_enabled=True,
        warehouse_timeout_seconds=20,
        warehouse_environment_label="competition-test",
        snowflake_account="private-account",
        snowflake_user="private-user",
        snowflake_authenticator="SNOWFLAKE_JWT",
        snowflake_private_key_path=Path("C:/private/credential.p8"),
        snowflake_warehouse="COMPUTE_WH",
        snowflake_database="SAFE_DB",
        snowflake_schema="SAFE_SCHEMA",
        snowflake_role="CHANGESAFE_READONLY",
        snowflake_target_relation_allowlist={DEMO_TARGET_URN: RELATION},
    )


def request_for(operation: ChangeOperation) -> ChangeRequest:
    values: dict[str, object] = {
        "asset_urn": DEMO_TARGET_URN,
        "operation": operation,
        "field": "cust_email",
        "source_commit": "safe-commit",
        "requested_by": "test-owner",
    }
    if operation is ChangeOperation.RENAME:
        values["new_field"] = "customer_email"
    elif operation is ChangeOperation.TYPE_CHANGE:
        values["old_type"] = "VARCHAR"
        values["new_type"] = "NUMBER"
    return ChangeRequest.model_validate(values)


def context(*, field_type: str = "VARCHAR") -> ContextBundle:
    return ContextBundle(
        target_urn=DEMO_TARGET_URN,
        target_name="order_details",
        field="cust_email",
        field_type=field_type,
        schema_fields=[SchemaField(name="cust_email", data_type=field_type)],
        provenance=ContextProvenance(
            mode=ContextMode.LIVE,
            retrieved_at="2026-08-09T12:00:00Z",
            adapter_version="test/1",
        ),
    )


def metadata(
    name: str,
    type_code: int = 2,
    *,
    internal_size: int | None = 16_777_216,
    precision: int | None = None,
    scale: int | None = None,
) -> Metadata:
    return Metadata(
        name,
        type_code,
        None,
        internal_size,
        precision,
        scale,
        True,
    )


def success_responses(
    operation: ChangeOperation = ChangeOperation.RENAME,
    *,
    identity: Sequence[Sequence[object]] | None = None,
    schema_description: Sequence[object] | None = None,
    aggregate_description: Sequence[object] | None = None,
    aggregate_rows: Sequence[Sequence[object]] | None = None,
) -> list[CursorResponse]:
    identity_rows = identity or [
        ("CHANGESAFE_READONLY", "COMPUTE_WH", "SAFE_DB", "SAFE_SCHEMA")
    ]
    schema_columns = (
        [metadata("CUST_EMAIL")] if schema_description is None else schema_description
    )
    aggregate_columns = aggregate_description
    if aggregate_columns is None:
        aggregate_columns = [
            metadata("ROWS_EVALUATED", 0, internal_size=None, precision=38, scale=0),
            metadata(
                "POPULATED_ROW_COUNT",
                0,
                internal_size=None,
                precision=38,
                scale=0,
            ),
        ]
        if operation is ChangeOperation.TYPE_CHANGE:
            aggregate_columns = [
                *aggregate_columns,
                metadata(
                    "UNSAFE_ROW_COUNT",
                    0,
                    internal_size=None,
                    precision=38,
                    scale=0,
                ),
            ]
    aggregate_values = aggregate_rows
    if aggregate_values is None:
        aggregate_values = (
            [(12, 10, 0)] if operation is ChangeOperation.TYPE_CHANGE else [(12, 10)]
        )
    return [
        CursorResponse(rows=identity_rows, sfqid="identity-query-id"),
        CursorResponse(
            rows=(),
            description=schema_columns,
            sfqid="schema-query-id",
        ),
        CursorResponse(
            rows=aggregate_values,
            description=aggregate_columns,
            sfqid="aggregate-query-id",
        ),
    ]


async def validate_with(
    responses: Sequence[CursorResponse],
    *,
    operation: ChangeOperation = ChangeOperation.RENAME,
    bundle: ContextBundle | None = None,
) -> tuple[object, FakeConnection, ConnectSpy]:
    connection = FakeConnection(responses)
    connect = ConnectSpy(connection)
    validator = SnowflakeWarehouseValidator(settings(), connect=connect)
    result = await validator.validate(request_for(operation), bundle or context())
    return result, connection, connect


@pytest.mark.asyncio
async def test_executes_only_identity_and_registered_selects_with_bounded_session() -> (
    None
):
    result, connection, connect = await validate_with(success_responses())

    assert result.status is WarehouseValidationStatus.PASSED
    assert result.rows_evaluated == 12
    assert result.populated_row_count == 10
    assert result.unsafe_row_count is None
    assert result.query_ids == [
        "identity-query-id",
        "schema-query-id",
        "aggregate-query-id",
    ]
    assert connect.calls == [
        {
            "account": "private-account",
            "user": "private-user",
            "authenticator": "SNOWFLAKE_JWT",
            "private_key_file": "C:\\private\\credential.p8",
            "warehouse": "COMPUTE_WH",
            "database": "SAFE_DB",
            "schema": "SAFE_SCHEMA",
            "role": "CHANGESAFE_READONLY",
            "login_timeout": 20,
            "network_timeout": 20,
            "socket_timeout": 20,
            "client_session_keep_alive": False,
            "session_parameters": {
                "QUERY_TAG": "changesafe:warehouse-validation",
                "STATEMENT_TIMEOUT_IN_SECONDS": 20,
            },
        }
    ]
    assert connection.executed[0] == IDENTITY_SQL
    assert all(
        sql.lstrip().upper().startswith(("SELECT", "WITH"))
        for sql in connection.executed
    )
    assert connection.closed
    assert connection.cursor_instance.closed


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("position", "actual"),
    [
        (0, "ANOTHER_ROLE"),
        (1, "ANOTHER_WAREHOUSE"),
        (2, "ANOTHER_DATABASE"),
        (3, "ANOTHER_SCHEMA"),
    ],
)
async def test_identity_mismatch_blocks_before_relation_query(
    position: int, actual: str
) -> None:
    identity = [["CHANGESAFE_READONLY", "COMPUTE_WH", "SAFE_DB", "SAFE_SCHEMA"]]
    identity[0][position] = actual

    result, connection, _ = await validate_with(success_responses(identity=identity))

    assert result.status is WarehouseValidationStatus.BLOCKED
    assert result.checks[-1].code == "warehouse_identity"
    assert result.checks[-1].retryable is False
    assert connection.executed == [IDENTITY_SQL]
    assert connection.closed


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "identity",
    [
        [],
        [
            ("CHANGESAFE_READONLY", "COMPUTE_WH", "SAFE_DB", "SAFE_SCHEMA"),
            ("CHANGESAFE_READONLY", "COMPUTE_WH", "SAFE_DB", "SAFE_SCHEMA"),
        ],
        [("CHANGESAFE_READONLY", "COMPUTE_WH", "SAFE_DB", None)],
    ],
)
async def test_malformed_identity_blocks_before_relation_query(
    identity: Sequence[Sequence[object]],
) -> None:
    responses = success_responses()
    responses[0] = CursorResponse(rows=identity, sfqid="identity-query-id")

    result, connection, _ = await validate_with(responses)

    assert result.status is WarehouseValidationStatus.BLOCKED
    assert result.checks[-1].code == "warehouse_identity"
    assert result.checks[-1].retryable is False
    assert connection.executed == [IDENTITY_SQL]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "schema_description",
    [
        [],
        [metadata("CUST_EMAIL"), metadata("CUST_EMAIL")],
        [metadata("ANOTHER_COLUMN")],
        [metadata("CUST_EMAIL", 0, internal_size=None, precision=38, scale=0)],
    ],
)
async def test_schema_probe_requires_one_matching_source_column_and_type(
    schema_description: Sequence[object],
) -> None:
    result, connection, _ = await validate_with(
        success_responses(schema_description=schema_description)
    )

    assert result.status is WarehouseValidationStatus.BLOCKED
    assert result.checks[-1].code == "warehouse_schema"
    assert result.checks[-1].retryable is False
    assert len(connection.executed) == 2
    assert connection.closed


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "aggregate_description",
    [
        [metadata("ROWS_EVALUATED", 0, precision=38, scale=0)],
        [
            metadata("ROWS_EVALUATED", 0, precision=38, scale=0),
            metadata("ROWS_EVALUATED", 0, precision=38, scale=0),
        ],
    ],
)
async def test_aggregate_response_rejects_missing_or_duplicate_columns(
    aggregate_description: Sequence[object],
) -> None:
    result, connection, _ = await validate_with(
        success_responses(aggregate_description=aggregate_description)
    )

    assert result.status is WarehouseValidationStatus.BLOCKED
    assert result.checks[-1].code == "warehouse_response"
    assert result.checks[-1].retryable is False
    assert connection.closed


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "aggregate_description",
    [
        [
            metadata("ROWS_EVALUATED", 0, precision=38, scale=0),
            metadata("POPULATED_ROW_COUNT", 0, precision=38, scale=0),
        ],
        [
            metadata("ROWS_EVALUATED", 0, precision=38, scale=0),
            metadata("POPULATED_ROW_COUNT", 0, precision=38, scale=0),
            metadata("POPULATED_ROW_COUNT", 0, precision=38, scale=0),
        ],
    ],
)
async def test_type_aggregate_requires_one_unsafe_count_column(
    aggregate_description: Sequence[object],
) -> None:
    result, connection, _ = await validate_with(
        success_responses(
            ChangeOperation.TYPE_CHANGE,
            aggregate_description=aggregate_description,
        ),
        operation=ChangeOperation.TYPE_CHANGE,
    )

    assert result.status is WarehouseValidationStatus.BLOCKED
    assert result.checks[-1].code == "warehouse_response"
    assert result.checks[-1].retryable is False
    assert connection.closed


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "aggregate_rows",
    [
        [],
        [(12, 10), (12, 10)],
        [(-1, 0)],
        [(True, 0)],
        [(3, 4)],
        [(3, "raw-secret-row")],
    ],
)
async def test_aggregate_response_rejects_malformed_or_impossible_counts(
    aggregate_rows: Sequence[Sequence[object]],
) -> None:
    result, connection, _ = await validate_with(
        success_responses(aggregate_rows=aggregate_rows)
    )

    assert result.status is WarehouseValidationStatus.BLOCKED
    assert result.checks[-1].code == "warehouse_response"
    assert "raw-secret-row" not in result.model_dump_json()
    assert connection.closed


@pytest.mark.asyncio
async def test_type_change_blocks_nonzero_unsafe_conversions_with_count_only() -> None:
    result, connection, _ = await validate_with(
        success_responses(
            ChangeOperation.TYPE_CHANGE,
            aggregate_rows=[(12, 10, 2)],
        ),
        operation=ChangeOperation.TYPE_CHANGE,
    )

    assert result.status is WarehouseValidationStatus.BLOCKED
    assert result.rows_evaluated == 12
    assert result.populated_row_count == 10
    assert result.unsafe_row_count == 2
    assert result.checks[-1].code == "unsafe_conversion"
    assert result.checks[-1].observed_count == 2
    assert result.checks[-1].retryable is False
    assert RELATION not in result.model_dump_json()
    assert connection.closed


@pytest.mark.asyncio
async def test_type_change_rejects_unsafe_count_above_populated_count() -> None:
    result, connection, _ = await validate_with(
        success_responses(
            ChangeOperation.TYPE_CHANGE,
            aggregate_rows=[(5, 2, 3)],
        ),
        operation=ChangeOperation.TYPE_CHANGE,
    )

    assert result.status is WarehouseValidationStatus.BLOCKED
    assert result.checks[-1].code == "warehouse_response"
    assert result.unsafe_row_count is None
    assert connection.closed


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("operation", "counts", "limitation"),
    [
        (ChangeOperation.RENAME, (0, 0), "no rows"),
        (ChangeOperation.REMOVE, (5, 0), "null"),
        (ChangeOperation.TYPE_CHANGE, (0, 0, 0), "no rows"),
        (ChangeOperation.TYPE_CHANGE, (5, 0, 0), "null"),
    ],
)
async def test_empty_and_all_null_aggregates_are_valid_limited_evidence(
    operation: ChangeOperation,
    counts: tuple[int, ...],
    limitation: str,
) -> None:
    result, _, _ = await validate_with(
        success_responses(operation, aggregate_rows=[counts]),
        operation=operation,
    )

    assert result.status is WarehouseValidationStatus.PASSED
    assert limitation in result.checks[-1].detail.casefold()


class AuthenticationFailure(Exception):
    pass


class ServerUnavailable(Exception):
    pass


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "code", "retryable"),
    [
        (AuthenticationFailure("private-password"), "warehouse_authentication", False),
        (TimeoutError("private-password"), "warehouse_timeout", True),
        (ConnectionError("private-password"), "warehouse_transport", True),
        (ServerUnavailable("private-password"), "warehouse_transport", True),
    ],
)
async def test_connect_failures_are_safely_classified_without_exception_text(
    error: BaseException,
    code: str,
    retryable: bool,
    caplog: pytest.LogCaptureFixture,
) -> None:
    validator = SnowflakeWarehouseValidator(settings(), connect=ConnectSpy(error=error))

    with caplog.at_level(logging.WARNING):
        result = await validator.validate(
            request_for(ChangeOperation.RENAME), context()
        )

    assert result.status is WarehouseValidationStatus.BLOCKED
    assert result.checks[-1].code == code
    assert result.checks[-1].retryable is retryable
    assert "private-password" not in result.model_dump_json()
    assert "private-password" not in caplog.text
    assert RELATION not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error_type",
    [
        InternalServerError,
        BadGatewayError,
        OtherHTTPRetryableError,
        RequestExceedMaxRetryError,
    ],
)
async def test_pinned_connector_server_failures_are_retryable(
    error_type: type[Exception],
) -> None:
    validator = SnowflakeWarehouseValidator(
        settings(),
        connect=ConnectSpy(error=error_type(msg="private-password")),
    )

    result = await validator.validate(request_for(ChangeOperation.RENAME), context())

    assert result.status is WarehouseValidationStatus.BLOCKED
    assert result.checks[-1].code == "warehouse_transport"
    assert result.checks[-1].retryable is True
    assert "private-password" not in result.model_dump_json()


@pytest.mark.asyncio
async def test_relation_exception_closes_and_never_exposes_message_or_rows(
    caplog: pytest.LogCaptureFixture,
) -> None:
    secret = "credential=super-secret raw-row@example.com"
    responses = success_responses()
    responses[2] = CursorResponse(error=ValueError(secret))

    with caplog.at_level(logging.WARNING):
        result, connection, _ = await validate_with(responses)

    assert result.status is WarehouseValidationStatus.BLOCKED
    assert result.checks[-1].code == "warehouse_relation"
    assert result.checks[-1].retryable is False
    assert secret not in result.model_dump_json()
    assert secret not in caplog.text
    assert "private-account" not in caplog.text
    assert RELATION not in caplog.text
    assert connection.closed
    assert connection.cursor_instance.closed


@pytest.mark.asyncio
async def test_cancellation_is_safe_and_waits_for_resource_cleanup(
    caplog: pytest.LogCaptureFixture,
) -> None:
    responses = success_responses()
    responses[1] = CursorResponse(error=asyncio.CancelledError("private-password"))

    with caplog.at_level(logging.WARNING):
        result, connection, _ = await validate_with(responses)

    assert result.status is WarehouseValidationStatus.BLOCKED
    assert result.checks[-1].code == "warehouse_cancelled"
    assert result.checks[-1].retryable is True
    assert "private-password" not in result.model_dump_json()
    assert "private-password" not in caplog.text
    assert connection.closed
    assert connection.cursor_instance.closed


@pytest.mark.asyncio
async def test_actual_builder_identity_guard_runs_before_each_relation_execute(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from changesafe.warehouse import snowflake as adapter_module

    original = adapter_module.validate_read_only_query
    validated_sql: list[str] = []

    def recording_guard(query: object, relation: str, fields: set[str]) -> None:
        original(query, relation, fields)  # type: ignore[arg-type]
        validated_sql.append(query.sql)  # type: ignore[attr-defined]

    monkeypatch.setattr(adapter_module, "validate_read_only_query", recording_guard)
    _, connection, _ = await validate_with(success_responses())

    assert validated_sql == connection.executed[1:]


@pytest.mark.asyncio
async def test_mutated_builder_query_is_blocked_by_identity_registry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from changesafe.warehouse import snowflake as adapter_module

    original = adapter_module.build_validation_plan

    def mutated_plan(*args: object, **kwargs: object) -> object:
        plan = original(*args, **kwargs)  # type: ignore[arg-type]
        object.__setattr__(plan.queries[0], "sql", "SELECT CURRENT_USER()")
        return plan

    monkeypatch.setattr(adapter_module, "build_validation_plan", mutated_plan)
    result, connection, _ = await validate_with(success_responses())

    assert result.status is WarehouseValidationStatus.BLOCKED
    assert result.checks[-1].code == "warehouse_query"
    assert connection.executed == [IDENTITY_SQL]
    assert connection.closed


@pytest.mark.asyncio
async def test_calls_are_serialized_by_one_validator() -> None:
    active = 0
    maximum_active = 0
    connections: list[FakeConnection] = []

    def connect(**kwargs: object) -> FakeConnection:
        nonlocal active, maximum_active
        del kwargs
        active += 1
        maximum_active = max(maximum_active, active)
        time.sleep(0.03)
        connection = FakeConnection(success_responses())
        original_close = connection.close

        def close() -> None:
            nonlocal active
            original_close()
            active -= 1

        connection.close = close  # type: ignore[method-assign]
        connections.append(connection)
        return connection

    validator = SnowflakeWarehouseValidator(settings(), connect=connect)
    await asyncio.gather(
        validator.validate(request_for(ChangeOperation.RENAME), context()),
        validator.validate(request_for(ChangeOperation.RENAME), context()),
    )

    assert maximum_active == 1
    assert len(connections) == 2
    assert all(connection.closed for connection in connections)


@pytest.mark.asyncio
async def test_missing_target_relation_is_nonretryable_without_connecting() -> None:
    configured = settings().model_copy(
        update={"snowflake_target_relation_allowlist": {}}
    )
    connect = ConnectSpy(error=AssertionError("must not connect"))
    validator = SnowflakeWarehouseValidator(configured, connect=connect)

    result = await validator.validate(request_for(ChangeOperation.RENAME), context())

    assert result.status is WarehouseValidationStatus.BLOCKED
    assert result.checks[-1].code == "warehouse_relation"
    assert result.checks[-1].retryable is False
    assert connect.calls == []


@pytest.mark.asyncio
async def test_unsupported_contract_is_nonretryable_without_connecting() -> None:
    request = ChangeRequest(
        asset_urn=DEMO_TARGET_URN,
        operation=ChangeOperation.TYPE_CHANGE,
        field="cust_email",
        old_type="VARIANT",
        new_type="VARCHAR",
        source_commit="safe-commit",
        requested_by="test-owner",
    )
    connect = ConnectSpy(error=AssertionError("must not connect"))
    validator = SnowflakeWarehouseValidator(settings(), connect=connect)

    result = await validator.validate(request, context(field_type="VARIANT"))

    assert result.status is WarehouseValidationStatus.BLOCKED
    assert result.checks[-1].code == "warehouse_contract"
    assert result.checks[-1].retryable is False
    assert connect.calls == []
