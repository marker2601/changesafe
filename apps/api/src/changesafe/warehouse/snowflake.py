"""Serialized, aggregate-only Snowflake warehouse validation."""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Callable, Sequence
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib import import_module
from time import perf_counter
from typing import Protocol, cast

from changesafe.config import Settings
from changesafe.domain import (
    ChangeOperation,
    ChangeRequest,
    ContextBundle,
    WarehouseCheck,
    WarehouseValidationMode,
    WarehouseValidationResult,
    WarehouseValidationStatus,
)
from changesafe.sql_types import canonical_sql_type
from changesafe.warehouse.base import WarehouseValidationError
from changesafe.warehouse.queries import (
    UnsafeWarehouseQuery,
    UnsupportedWarehouseConversion,
    WarehouseQuery,
    WarehouseValidationPlan,
    build_validation_plan,
    validate_read_only_query,
)

logger = logging.getLogger(__name__)

IDENTITY_SQL = (
    "SELECT CURRENT_ROLE(), CURRENT_WAREHOUSE(), CURRENT_DATABASE(), CURRENT_SCHEMA()"
)
QUERY_TAG = "changesafe:warehouse-validation"
QUERY_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
RETRYABLE_CONNECTOR_ERRORS = {
    "badgatewayerror",
    "badrequest",
    "forbiddenerror",
    "gatewaytimeouterror",
    "internalservererror",
    "methodnotallowed",
    "otherhttpretryableerror",
    "requestexceedmaxretryerror",
    "retryrequest",
    "serviceunavailableerror",
    "toomanyrequests",
}
SNOWFLAKE_TYPES = (
    "FIXED",
    "REAL",
    "TEXT",
    "DATE",
    "TIMESTAMP",
    "VARIANT",
    "TIMESTAMP_LTZ",
    "TIMESTAMP_TZ",
    "TIMESTAMP_NTZ",
    "OBJECT",
    "ARRAY",
    "BINARY",
    "TIME",
    "BOOLEAN",
    "GEOGRAPHY",
    "GEOMETRY",
    "VECTOR",
    "MAP",
    "FILE",
    "INTERVAL_YEAR_MONTH",
    "INTERVAL_DAY_TIME",
)


class ConnectorCursor(Protocol):
    @property
    def description(self) -> Sequence[object] | None: ...

    @property
    def sfqid(self) -> str | None: ...

    def execute(self, command: str) -> object: ...

    def fetchall(self) -> Sequence[Sequence[object]]: ...

    def close(self) -> None: ...


class ConnectorConnection(Protocol):
    def cursor(self) -> ConnectorCursor: ...

    def close(self) -> None: ...


ConnectorFactory = Callable[..., ConnectorConnection]


@dataclass(frozen=True, slots=True)
class _ExecutionEvidence:
    rows_evaluated: int
    populated_row_count: int
    unsafe_row_count: int | None
    query_ids: tuple[str, ...]


class _AdapterFailure(WarehouseValidationError):
    def __init__(
        self,
        code: str,
        public_message: str,
        *,
        retryable: bool,
        query_ids: Sequence[str] = (),
    ) -> None:
        super().__init__(code, public_message, retryable=retryable)
        self.query_ids = tuple(query_ids)


def _failure(
    code: str,
    *,
    retryable: bool,
    query_ids: Sequence[str] = (),
) -> _AdapterFailure:
    messages = {
        "warehouse_authentication": "Warehouse authentication was not accepted.",
        "warehouse_cancelled": "Warehouse validation was cancelled safely.",
        "warehouse_connector": "Warehouse validation could not complete safely.",
        "warehouse_contract": "The requested warehouse validation is unsupported.",
        "warehouse_identity": (
            "The active warehouse session identity did not match configuration."
        ),
        "warehouse_query": "The warehouse query failed the read-only safety contract.",
        "warehouse_relation": (
            "The configured warehouse relation could not be validated."
        ),
        "warehouse_response": "The warehouse returned malformed aggregate evidence.",
        "warehouse_schema": (
            "The warehouse source column did not match catalog context."
        ),
        "warehouse_timeout": "Warehouse validation timed out.",
        "warehouse_transport": "The warehouse service was temporarily unavailable.",
    }
    return _AdapterFailure(
        code,
        messages[code],
        retryable=retryable,
        query_ids=query_ids,
    )


def _default_connector() -> ConnectorFactory:
    module = import_module("snowflake.connector")
    return cast(ConnectorFactory, module.connect)


def _safe_query_id(cursor: ConnectorCursor) -> str | None:
    value = cursor.sfqid
    return value if isinstance(value, str) and QUERY_ID.fullmatch(value) else None


def _metadata_value(column: object, name: str, position: int) -> object:
    if hasattr(column, name):
        return getattr(column, name)
    if (
        isinstance(column, Sequence)
        and not isinstance(column, (str, bytes))
        and len(column) > position
    ):
        return column[position]
    raise ValueError("malformed cursor description")


def _column_name(column: object) -> str:
    value = _metadata_value(column, "name", 0)
    if not isinstance(value, str) or not value:
        raise ValueError("malformed cursor column name")
    return value.upper()


def _optional_int(column: object, name: str, position: int) -> int | None:
    value = _metadata_value(column, name, position)
    if value is None:
        return None
    if type(value) is not int:
        raise ValueError("malformed cursor type metadata")
    return value


def _snowflake_type_name(column: object) -> str:
    raw_type = _metadata_value(column, "type_code", 1)
    if type(raw_type) is int and 0 <= raw_type < len(SNOWFLAKE_TYPES):
        return SNOWFLAKE_TYPES[raw_type]
    raise ValueError("unsupported cursor type code")


def _description_sql_type(column: object) -> tuple[str, tuple[int, ...]]:
    type_name = _snowflake_type_name(column)
    internal_size = _optional_int(column, "internal_size", 3)
    precision = _optional_int(column, "precision", 4)
    scale = _optional_int(column, "scale", 5)
    if type_name == "FIXED":
        rendered = f"NUMBER({precision or 38},{scale or 0})"
    elif type_name == "REAL":
        rendered = "FLOAT"
    elif type_name == "TEXT":
        rendered = f"VARCHAR({internal_size or 16_777_216})"
    elif type_name == "BINARY":
        rendered = f"BINARY({internal_size or 8_388_608})"
    elif type_name in {
        "TIME",
        "TIMESTAMP",
        "TIMESTAMP_LTZ",
        "TIMESTAMP_NTZ",
        "TIMESTAMP_TZ",
    }:
        rendered = f"{type_name}({9 if scale is None else scale})"
    else:
        rendered = type_name
    return canonical_sql_type(rendered)


def _normalized_description(
    description: Sequence[object] | None,
) -> tuple[object, ...]:
    if description is None or isinstance(description, (str, bytes)):
        raise ValueError("missing cursor description")
    return tuple(description)


def _validate_aggregate_metadata(column: object) -> None:
    if _snowflake_type_name(column) != "FIXED":
        raise ValueError("aggregate output is not fixed numeric")
    internal_size = _optional_int(column, "internal_size", 3)
    precision = _optional_int(column, "precision", 4)
    scale = _optional_int(column, "scale", 5)
    if precision is None or not 1 <= precision <= 38:
        raise ValueError("aggregate precision is invalid")
    if scale != 0:
        raise ValueError("aggregate scale is invalid")
    if internal_size is not None and internal_size <= 0:
        raise ValueError("aggregate internal size is invalid")


def _contain_connector_logs() -> None:
    connector_logger = logging.getLogger("snowflake.connector")
    connector_logger.handlers.clear()
    connector_logger.addHandler(logging.NullHandler())
    connector_logger.propagate = False
    connector_logger.setLevel(logging.CRITICAL + 1)


def _close_resources(
    cursor: ConnectorCursor | None,
    connection: ConnectorConnection | None,
) -> BaseException | None:
    close_error: BaseException | None = None
    for resource in (cursor, connection):
        if resource is None:
            continue
        try:
            resource.close()
        except BaseException as exc:  # ensure the other resource is still closed
            if close_error is None:
                close_error = exc
    return close_error


def _connector_failure(
    error: Exception,
    phase: str,
    query_ids: Sequence[str],
) -> _AdapterFailure:
    class_names = {item.__name__.casefold() for item in type(error).__mro__}
    if phase == "connect" and "forbiddenerror" in class_names:
        return _failure(
            "warehouse_authentication", retryable=False, query_ids=query_ids
        )
    if isinstance(error, TimeoutError) or any(
        "timeout" in name for name in class_names
    ):
        return _failure("warehouse_timeout", retryable=True, query_ids=query_ids)
    if (
        isinstance(error, (ConnectionError, OSError))
        or class_names & RETRYABLE_CONNECTOR_ERRORS
        or any(
            marker in name
            for name in class_names
            for marker in ("network", "operational", "unavailable")
        )
    ):
        return _failure("warehouse_transport", retryable=True, query_ids=query_ids)
    if any("auth" in name for name in class_names) or phase == "connect":
        return _failure(
            "warehouse_authentication", retryable=False, query_ids=query_ids
        )
    if phase == "identity":
        return _failure("warehouse_identity", retryable=False, query_ids=query_ids)
    if phase in {"schema", "aggregate"}:
        return _failure("warehouse_relation", retryable=False, query_ids=query_ids)
    return _failure("warehouse_connector", retryable=False, query_ids=query_ids)


class SnowflakeWarehouseValidator:
    """Validate one allowlisted relation through safe aggregate queries only."""

    def __init__(
        self,
        settings: Settings,
        connect: ConnectorFactory | None = None,
    ) -> None:
        _contain_connector_logs()
        self._settings = settings
        self._connect = connect
        self._lock = asyncio.Lock()

    async def close(self) -> None:
        async with self._lock:
            return

    async def validate(
        self,
        change: ChangeRequest,
        context: ContextBundle,
    ) -> WarehouseValidationResult:
        async with self._lock:
            return await self._validate_serialized(change, context)

    async def _validate_serialized(
        self,
        change: ChangeRequest,
        context: ContextBundle,
    ) -> WarehouseValidationResult:
        started_at = datetime.now(UTC)
        started_clock = perf_counter()
        plan: WarehouseValidationPlan | None = None
        try:
            relation = self._settings.warehouse_target_map.get(change.asset_urn)
            if relation is None:
                raise _failure("warehouse_relation", retryable=False)
            try:
                plan = build_validation_plan(change, context, relation)
            except UnsupportedWarehouseConversion:
                raise _failure("warehouse_contract", retryable=False) from None
            except UnsafeWarehouseQuery:
                raise _failure("warehouse_contract", retryable=False) from None

            worker = asyncio.create_task(
                asyncio.to_thread(self._execute_plan, plan, change, context)
            )
            try:
                evidence = await asyncio.shield(worker)
            except asyncio.CancelledError:
                while not worker.done():
                    try:
                        await asyncio.shield(worker)
                    except asyncio.CancelledError:
                        continue
                    except BaseException:
                        break
                with suppress(BaseException):
                    worker.result()
                raise

            checks = [
                WarehouseCheck(
                    code="warehouse_identity",
                    label="Warehouse session identity",
                    passed=True,
                    detail="Configured read-only session identity was verified.",
                ),
                WarehouseCheck(
                    code="warehouse_schema",
                    label="Warehouse source schema",
                    passed=True,
                    detail="The source column type matches catalog context.",
                ),
            ]
            operation_check = self._operation_check(change.operation, evidence)
            checks.append(operation_check)
            status = (
                WarehouseValidationStatus.PASSED
                if operation_check.passed
                else WarehouseValidationStatus.BLOCKED
            )
            return WarehouseValidationResult(
                status=status,
                mode=WarehouseValidationMode.AGGREGATE,
                environment_label=self._settings.warehouse_environment_label,
                operation=change.operation,
                field=change.field,
                relation_fingerprint=plan.relation_fingerprint,
                started_at=started_at,
                completed_at=datetime.now(UTC),
                rows_evaluated=evidence.rows_evaluated,
                populated_row_count=evidence.populated_row_count,
                unsafe_row_count=evidence.unsafe_row_count,
                query_ids=list(evidence.query_ids),
                elapsed_ms=max(0, int((perf_counter() - started_clock) * 1000)),
                checks=checks,
            )
        except _AdapterFailure as failure:
            logger.warning("Warehouse validation failed", extra={"code": failure.code})
            return WarehouseValidationResult(
                status=WarehouseValidationStatus.BLOCKED,
                mode=WarehouseValidationMode.AGGREGATE,
                environment_label=self._settings.warehouse_environment_label,
                operation=change.operation,
                field=change.field,
                relation_fingerprint=(
                    plan.relation_fingerprint if plan is not None else None
                ),
                started_at=started_at,
                completed_at=datetime.now(UTC),
                query_ids=list(failure.query_ids),
                elapsed_ms=max(0, int((perf_counter() - started_clock) * 1000)),
                checks=[
                    WarehouseCheck(
                        code=failure.code,
                        label="Warehouse validation",
                        passed=False,
                        retryable=failure.retryable,
                        detail=failure.public_message,
                    )
                ],
            )

    def _connector_kwargs(self) -> dict[str, object]:
        values = (
            self._settings.snowflake_account,
            self._settings.snowflake_user,
            self._settings.snowflake_private_key_path,
            self._settings.snowflake_warehouse,
            self._settings.snowflake_database,
            self._settings.snowflake_schema,
            self._settings.snowflake_role,
        )
        if not all(value is not None for value in values):
            raise _failure("warehouse_authentication", retryable=False)
        timeout = self._settings.warehouse_timeout_seconds
        return {
            "account": self._settings.snowflake_account,
            "user": self._settings.snowflake_user,
            "authenticator": "SNOWFLAKE_JWT",
            "private_key_file": str(self._settings.snowflake_private_key_path),
            "warehouse": self._settings.snowflake_warehouse,
            "database": self._settings.snowflake_database,
            "schema": self._settings.snowflake_schema,
            "role": self._settings.snowflake_role,
            "secondary_roles": "NONE",
            "login_timeout": timeout,
            "network_timeout": timeout,
            "socket_timeout": timeout,
            "client_session_keep_alive": False,
            "session_parameters": {
                "QUERY_TAG": QUERY_TAG,
                "STATEMENT_TIMEOUT_IN_SECONDS": timeout,
            },
        }

    def _execute_plan(
        self,
        plan: WarehouseValidationPlan,
        change: ChangeRequest,
        context: ContextBundle,
    ) -> _ExecutionEvidence:
        connection: ConnectorConnection | None = None
        cursor: ConnectorCursor | None = None
        evidence: _ExecutionEvidence | None = None
        pending: BaseException | None = None
        query_ids: list[str] = []
        phase = "connect"
        try:
            connector = self._connect or _default_connector()
            connection = connector(**self._connector_kwargs())
            cursor = connection.cursor()
            phase = "identity"
            cursor.execute(IDENTITY_SQL)
            self._remember_query_id(cursor, query_ids)
            self._verify_identity(cursor.fetchall())

            allowed_fields = {change.field}
            if change.new_field is not None:
                allowed_fields.add(change.new_field)
            aggregate: tuple[int, int, int | None] | None = None
            for query in plan.queries:
                phase = "schema" if query.code == "schema_probe" else "aggregate"
                try:
                    validate_read_only_query(query, plan.relation, allowed_fields)
                except UnsafeWarehouseQuery:
                    raise _failure(
                        "warehouse_query", retryable=False, query_ids=query_ids
                    ) from None
                cursor.execute(query.sql)
                self._remember_query_id(cursor, query_ids)
                if query.code == "schema_probe":
                    self._verify_schema(cursor, query, context)
                else:
                    aggregate = self._aggregate_counts(cursor, query)
            if aggregate is None:
                raise _failure(
                    "warehouse_response", retryable=False, query_ids=query_ids
                )
            evidence = _ExecutionEvidence(*aggregate, tuple(query_ids))
        except BaseException as error:
            pending = error
        close_error = _close_resources(cursor, connection)
        if pending is not None:
            if isinstance(pending, _AdapterFailure):
                raise pending
            if isinstance(pending, asyncio.CancelledError):
                raise _failure(
                    "warehouse_cancelled", retryable=True, query_ids=query_ids
                ) from None
            if isinstance(pending, Exception):
                raise _connector_failure(pending, phase, query_ids) from None
            raise pending
        if close_error is not None:
            raise _failure("warehouse_connector", retryable=False, query_ids=query_ids)
        if evidence is None:
            raise _failure("warehouse_response", retryable=False, query_ids=query_ids)
        return evidence

    def _verify_identity(self, rows: Sequence[Sequence[object]]) -> None:
        expected = (
            self._settings.snowflake_role,
            self._settings.snowflake_warehouse,
            self._settings.snowflake_database,
            self._settings.snowflake_schema,
        )
        if (
            len(rows) != 1
            or len(rows[0]) != 4
            or any(value is None for value in rows[0])
        ):
            raise _failure("warehouse_identity", retryable=False)
        if any(
            not isinstance(actual, str)
            or configured is None
            or actual.casefold() != configured.casefold()
            for actual, configured in zip(rows[0], expected, strict=True)
        ):
            raise _failure("warehouse_identity", retryable=False)

    def _verify_schema(
        self,
        cursor: ConnectorCursor,
        query: WarehouseQuery,
        context: ContextBundle,
    ) -> None:
        try:
            columns = _normalized_description(cursor.description)
            if (
                len(columns) != 1
                or _column_name(columns[0]) != query.expected_columns[0]
            ):
                raise ValueError("schema column mismatch")
            if _description_sql_type(columns[0]) != canonical_sql_type(
                context.field_type
            ):
                raise ValueError("schema type mismatch")
        except ValueError:
            raise _failure("warehouse_schema", retryable=False) from None

    def _aggregate_counts(
        self,
        cursor: ConnectorCursor,
        query: WarehouseQuery,
    ) -> tuple[int, int, int | None]:
        try:
            columns = _normalized_description(cursor.description)
            names = tuple(_column_name(column) for column in columns)
            expected = tuple(name.upper() for name in query.expected_columns)
            if names != expected or len(names) != len(set(names)):
                raise ValueError("aggregate columns mismatch")
            for column in columns:
                _validate_aggregate_metadata(column)
            rows = cursor.fetchall()
            if len(rows) != 1 or len(rows[0]) != len(expected):
                raise ValueError("aggregate row shape mismatch")
            counts = tuple(rows[0])
            if any(type(value) is not int or value < 0 for value in counts):
                raise ValueError("aggregate count is invalid")
            rows_evaluated = cast(int, counts[0])
            populated_row_count = cast(int, counts[1])
            unsafe_row_count = cast(int, counts[2]) if len(counts) == 3 else None
            if populated_row_count > rows_evaluated or (
                unsafe_row_count is not None and unsafe_row_count > populated_row_count
            ):
                raise ValueError("aggregate count relationship is invalid")
            return rows_evaluated, populated_row_count, unsafe_row_count
        except (IndexError, TypeError, ValueError):
            raise _failure("warehouse_response", retryable=False) from None

    @staticmethod
    def _remember_query_id(cursor: ConnectorCursor, query_ids: list[str]) -> None:
        query_id = _safe_query_id(cursor)
        if query_id is not None:
            query_ids.append(query_id)

    @staticmethod
    def _operation_check(
        operation: ChangeOperation,
        evidence: _ExecutionEvidence,
    ) -> WarehouseCheck:
        if (
            operation is ChangeOperation.TYPE_CHANGE
            and evidence.unsafe_row_count is None
        ):
            raise _failure("warehouse_response", retryable=False)
        if evidence.rows_evaluated == 0:
            return WarehouseCheck(
                code="empty_relation",
                label="Warehouse aggregate evidence",
                passed=False,
                retryable=True,
                detail=(
                    "Warehouse evidence is inconclusive because no rows were available."
                ),
            )
        if evidence.populated_row_count == 0:
            return WarehouseCheck(
                code="all_null_field",
                label="Warehouse aggregate evidence",
                passed=False,
                retryable=True,
                detail=(
                    "Warehouse evidence is inconclusive because every selected field "
                    "entry was null."
                ),
            )
        if operation is ChangeOperation.TYPE_CHANGE:
            unsafe = cast(int, evidence.unsafe_row_count)
            if unsafe > 0:
                return WarehouseCheck(
                    code="unsafe_conversion",
                    label="Warehouse type conversion",
                    passed=False,
                    detail="Some populated rows cannot be converted safely.",
                    observed_count=unsafe,
                )
            return WarehouseCheck(
                code="type_conversion",
                label="Warehouse type conversion",
                passed=True,
                detail=(
                    "Aggregate warehouse validation completed without unsafe evidence."
                ),
                observed_count=0,
            )
        code = (
            "rename_projection"
            if operation is ChangeOperation.RENAME
            else "remove_impact"
        )
        return WarehouseCheck(
            code=code,
            label="Warehouse aggregate evidence",
            passed=True,
            detail="Aggregate warehouse validation completed without unsafe evidence.",
        )


__all__ = ["ConnectorFactory", "SnowflakeWarehouseValidator"]
