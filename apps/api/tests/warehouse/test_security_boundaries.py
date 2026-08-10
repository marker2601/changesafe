from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import httpx
import pytest

from changesafe.api import create_app
from changesafe.config import Mode
from changesafe.context.replay import ReplayDataHubContext
from changesafe.demo import DEMO_TARGET_URN, golden_change
from changesafe.domain import (
    ChangeOperation,
    ChangeRequest,
    ContextBundle,
    ContextMode,
    RunState,
    WarehouseValidationStatus,
)
from changesafe.warehouse.snowflake import SnowflakeWarehouseValidator

from .test_snowflake import (
    ConnectSpy,
    CursorResponse,
    FakeConnection,
    context,
    metadata,
    request_for,
    settings,
    success_responses,
)

SENSITIVE_VALUES = [
    "customer@example.com",
    "-" * 5 + "BEGIN PRIVATE" + " KEY" + "-" * 5 + "not-a-real-key",
    "xy12345.us-east-1",
    "snowflake://private-user:private-password@private-account/database",
    "/* secret warehouse comment */",
    "safe_value; SELECT * FROM private_table",
]


class InvalidCredential(Exception):
    pass


class LiveReplayContext:
    def __init__(self) -> None:
        self.replay = ReplayDataHubContext.from_default()

    async def load(self, change: ChangeRequest):
        loaded = await self.replay.load(change)
        return loaded.model_copy(
            update={
                "provenance": loaded.provenance.model_copy(
                    update={"mode": ContextMode.LIVE, "snapshot_hash": None}
                )
            }
        )


def validator_for(
    responses: list[CursorResponse] | None = None,
    *,
    connection_error: BaseException | None = None,
    configured=None,
) -> tuple[SnowflakeWarehouseValidator, ConnectSpy]:
    connection = FakeConnection(responses or success_responses())
    connect = ConnectSpy(connection, error=connection_error)
    validator = SnowflakeWarehouseValidator(
        configured or settings(), connect=connect
    )
    return validator, connect


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("boundary", "expected_code"),
    [
        ("invalid_credential", "warehouse_authentication"),
        ("wrong_identity", "warehouse_identity"),
        ("missing_relation", "warehouse_relation"),
        ("missing_field", "warehouse_schema"),
        ("schema_drift", "warehouse_schema"),
        ("timeout", "warehouse_timeout"),
        ("cancel", "warehouse_cancelled"),
        ("malformed_aggregate", "warehouse_response"),
        ("multiple_rows", "warehouse_response"),
    ],
)
async def test_each_warehouse_uncertainty_boundary_fails_closed(
    boundary: str, expected_code: str
) -> None:
    configured = settings()
    responses = success_responses()
    connection_error: BaseException | None = None

    if boundary == "invalid_credential":
        connection_error = InvalidCredential(SENSITIVE_VALUES[1])
    elif boundary == "wrong_identity":
        responses = success_responses(
            identity=[("WRONG_ROLE", "COMPUTE_WH", "SAFE_DB", "SAFE_SCHEMA")]
        )
    elif boundary == "missing_relation":
        configured = configured.model_copy(
            update={"snowflake_target_relation_allowlist": {}}
        )
    elif boundary == "missing_field":
        responses = success_responses(schema_description=[])
    elif boundary == "schema_drift":
        responses = success_responses(
            schema_description=[
                metadata(
                    "CUST_EMAIL",
                    0,
                    internal_size=None,
                    precision=38,
                    scale=0,
                )
            ]
        )
    elif boundary == "timeout":
        connection_error = TimeoutError(SENSITIVE_VALUES[0])
    elif boundary == "cancel":
        responses[1] = CursorResponse(error=asyncio.CancelledError(SENSITIVE_VALUES[0]))
    elif boundary == "malformed_aggregate":
        responses = success_responses(aggregate_rows=[(3, SENSITIVE_VALUES[0])])
    elif boundary == "multiple_rows":
        responses = success_responses(aggregate_rows=[(3, 2), (3, 2)])

    validator, connect = validator_for(
        responses,
        connection_error=connection_error,
        configured=configured,
    )
    result = await validator.validate(
        request_for(ChangeOperation.RENAME), context()
    )

    assert result.status is WarehouseValidationStatus.BLOCKED
    assert result.checks[-1].code == expected_code
    assert not any(value in result.model_dump_json() for value in SENSITIVE_VALUES)
    if boundary == "missing_relation":
        assert connect.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("operation", "rows", "expected_code"),
    [
        (ChangeOperation.RENAME, (0, 0), "empty_relation"),
        (ChangeOperation.RENAME, (8, 0), "all_null_field"),
        (ChangeOperation.REMOVE, (0, 0), "empty_relation"),
        (ChangeOperation.REMOVE, (8, 0), "all_null_field"),
        (ChangeOperation.TYPE_CHANGE, (0, 0, 0), "empty_relation"),
        (ChangeOperation.TYPE_CHANGE, (8, 0, 0), "all_null_field"),
    ],
)
async def test_zero_and_all_null_aggregate_boundaries_are_blocked_inconclusive(
    operation: ChangeOperation, rows: tuple[int, ...], expected_code: str
) -> None:
    responses = success_responses(operation, aggregate_rows=[rows])
    validator, _ = validator_for(responses)

    result = await validator.validate(request_for(operation), context())

    assert result.status is WarehouseValidationStatus.BLOCKED
    assert result.rows_evaluated == rows[0]
    assert result.populated_row_count == rows[1]
    assert result.unsafe_row_count == (rows[2] if len(rows) == 3 else None)
    assert result.checks[-1].code == expected_code
    assert result.checks[-1].passed is False
    assert result.checks[-1].retryable is True


@pytest.mark.asyncio
async def test_populated_zero_unsafe_type_conversion_remains_passing() -> None:
    responses = success_responses(
        ChangeOperation.TYPE_CHANGE,
        aggregate_rows=[(12, 10, 0)],
    )
    validator, _ = validator_for(responses)

    result = await validator.validate(
        request_for(ChangeOperation.TYPE_CHANGE), context()
    )

    assert result.status is WarehouseValidationStatus.PASSED
    assert result.rows_evaluated == 12
    assert result.populated_row_count == 10
    assert result.unsafe_row_count == 0
    assert result.checks[-1].code == "type_conversion"
    assert result.checks[-1].passed is True
    assert result.checks[-1].observed_count == 0


def narrowing_case(family: str) -> tuple[ChangeRequest, ContextBundle, CursorResponse]:
    if family == "varchar":
        old_type = "VARCHAR(320)"
        new_type = "VARCHAR(32)"
        schema = CursorResponse(
            description=[metadata("CUST_EMAIL", 2, internal_size=320)]
        )
    else:
        old_type = "NUMBER(10,2)"
        new_type = "NUMBER(8,1)"
        schema = CursorResponse(
            description=[
                metadata(
                    "CUST_EMAIL",
                    0,
                    internal_size=None,
                    precision=10,
                    scale=2,
                )
            ]
        )
    change = ChangeRequest(
        asset_urn=DEMO_TARGET_URN,
        operation=ChangeOperation.TYPE_CHANGE,
        field="cust_email",
        old_type=old_type,
        new_type=new_type,
        source_commit=f"{family}-narrowing",
        requested_by="competition-matrix",
    )
    return change, context(field_type=old_type), schema


@pytest.mark.asyncio
@pytest.mark.parametrize("family", ["varchar", "number"])
async def test_varchar_and_number_narrowing_block_unsafe_conversions(
    family: str,
) -> None:
    change, bundle, schema = narrowing_case(family)
    responses = success_responses(
        ChangeOperation.TYPE_CHANGE,
        aggregate_rows=[(12, 10, 2)],
    )
    responses[1] = schema
    validator, _ = validator_for(responses)

    result = await validator.validate(change, bundle)

    assert result.status is WarehouseValidationStatus.BLOCKED
    assert result.unsafe_row_count == 2
    assert result.checks[-1].code == "unsafe_conversion"
    assert result.checks[-1].observed_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("secret", SENSITIVE_VALUES)
async def test_warehouse_failure_never_reaches_public_or_persisted_surfaces(
    secret: str,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    configured = settings().model_copy(
        update={
            "mode": Mode.REPLAY,
            "changesafe_data_path": tmp_path / "runs.db",
            "warehouse_validation_required": True,
        }
    )
    validator = SnowflakeWarehouseValidator(
        configured,
        connect=ConnectSpy(error=InvalidCredential(secret)),
    )
    app = create_app(
        settings=configured,
        context_port=LiveReplayContext(),
        warehouse_port=validator,
    )
    transport = httpx.ASGITransport(app=app)

    with caplog.at_level(logging.WARNING):
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            created = await client.post(
                "/api/runs", json=golden_change().model_dump(mode="json")
            )
            assert created.status_code == 202
            run_id = created.json()["run_id"]
            for _ in range(200):
                response = await client.get(f"/api/runs/{run_id}")
                payload = response.json()
                if payload["state"] == RunState.FAILED.value:
                    break
                await asyncio.sleep(0.005)
            else:
                raise AssertionError("warehouse-blocked run did not terminate")

    persisted = await app.state.store.get(run_id)
    assert persisted is not None
    assert persisted.analysis is not None
    warehouse = persisted.analysis.warehouse_validation
    artifacts = persisted.analysis.artifacts
    serialized_surfaces = [
        warehouse.model_dump_json(),
        persisted.model_dump_json(),
        response.text,
        caplog.text,
        (tmp_path / "runs.db").read_bytes().decode("utf-8", errors="ignore"),
        *[artifact.content for artifact in artifacts.files.values()],
    ]

    assert warehouse.status is WarehouseValidationStatus.BLOCKED
    assert warehouse.checks[-1].code == "warehouse_authentication"
    assert all(secret not in surface for surface in serialized_surfaces)
