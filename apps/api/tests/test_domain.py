import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from changesafe.demo import DEMO_TARGET_URN
from changesafe.domain import (
    AffectedAsset,
    ChangeOperation,
    ChangeRequest,
    ContextBundle,
    ContextMode,
    ContextProvenance,
    LineagePrecision,
    SchemaCatalog,
    SchemaField,
    WarehouseValidationMode,
    WarehouseValidationResult,
    WarehouseValidationStatus,
)

TARGET = DEMO_TARGET_URN


def test_schema_catalog_requires_a_nonempty_unique_schema() -> None:
    provenance = ContextProvenance(
        mode=ContextMode.SNAPSHOT,
        retrieved_at="2026-08-08T20:00:00Z",
        adapter_version="recorded-catalog/2",
        snapshot_hash="a" * 64,
    )
    with pytest.raises(ValidationError, match="schema_fields"):
        SchemaCatalog(
            target_urn="urn:li:dataset:demo",
            target_name="demo",
            schema_fields=[],
            provenance=provenance,
        )
    with pytest.raises(ValidationError, match="duplicate"):
        SchemaCatalog(
            target_urn="urn:li:dataset:demo",
            target_name="demo",
            schema_fields=[
                SchemaField(name="order_id", data_type="NUMBER", nullable=False),
                SchemaField(name="ORDER_ID", data_type="NUMBER", nullable=False),
            ],
            provenance=provenance,
        )


def test_affected_asset_requires_explicit_lineage_precision() -> None:
    asset = AffectedAsset(
        urn="urn:li:dataset:upstream",
        name="upstream",
        entity_type="dataset",
        field="order_id",
        lineage_degree=1,
        lineage_precision=LineagePrecision.EXACT_FIELD,
    )
    assert asset.lineage_precision is LineagePrecision.EXACT_FIELD


def test_rename_requires_new_field() -> None:
    with pytest.raises(ValidationError, match="new_field"):
        ChangeRequest(
            asset_urn=TARGET,
            operation=ChangeOperation.RENAME,
            field="customer_email",
            source_commit="demo-unsafe-change",
            requested_by="demo-user",
        )


def test_rename_rejects_case_insensitive_no_op_before_context_loading() -> None:
    with pytest.raises(
        ValidationError,
        match="new_field must differ from field case-insensitively",
    ):
        ChangeRequest(
            asset_urn="urn:li:dataset:demo",
            operation=ChangeOperation.RENAME,
            field="Email",
            new_field="email",
            source_commit="safe-commit",
            requested_by="reviewer",
        )


@pytest.mark.parametrize(
    ("operation", "unexpected"),
    [
        (ChangeOperation.RENAME, {"old_type": "TEXT"}),
        (ChangeOperation.RENAME, {"new_type": "VARCHAR(320)"}),
        (ChangeOperation.REMOVE, {"new_field": "primary_email"}),
        (ChangeOperation.REMOVE, {"old_type": "TEXT"}),
        (ChangeOperation.REMOVE, {"new_type": "VARCHAR(320)"}),
        (ChangeOperation.TYPE_CHANGE, {"new_field": "primary_email"}),
    ],
)
def test_change_request_rejects_operation_irrelevant_fields(
    operation: ChangeOperation, unexpected: dict[str, str]
) -> None:
    values = {
        "asset_urn": TARGET,
        "operation": operation,
        "field": "customer_email",
        "source_commit": "demo-unsafe-change",
        "requested_by": "demo-user",
    }
    if operation is ChangeOperation.RENAME:
        values["new_field"] = "primary_email"
    if operation is ChangeOperation.TYPE_CHANGE:
        values.update({"old_type": "TEXT", "new_type": "VARCHAR(320)"})
    values.update(unexpected)

    with pytest.raises(ValidationError, match="only valid"):
        ChangeRequest.model_validate(values)


@pytest.mark.parametrize("missing", ["old_type", "new_type"])
def test_type_change_requires_both_type_contract_values(missing: str) -> None:
    values = {
        "asset_urn": TARGET,
        "operation": ChangeOperation.TYPE_CHANGE,
        "field": "customer_email",
        "old_type": "TEXT",
        "new_type": "VARCHAR(320)",
        "source_commit": "demo-unsafe-change",
        "requested_by": "demo-user",
    }
    values.pop(missing)

    with pytest.raises(ValidationError, match=missing):
        ChangeRequest.model_validate(values)


def test_type_change_rejects_canonically_equal_types() -> None:
    with pytest.raises(ValidationError, match="must differ"):
        ChangeRequest(
            asset_urn=TARGET,
            operation=ChangeOperation.TYPE_CHANGE,
            field="customer_email",
            old_type="TEXT",
            new_type="VARCHAR",
            source_commit="demo-unsafe-change",
            requested_by="demo-user",
        )


def test_change_request_bounds_field_identifiers() -> None:
    with pytest.raises(ValidationError, match="at most 128"):
        ChangeRequest(
            asset_urn=TARGET,
            operation=ChangeOperation.REMOVE,
            field="a" * 129,
            source_commit="demo-unsafe-change",
            requested_by="demo-user",
        )


def test_type_change_requires_new_type() -> None:
    with pytest.raises(ValidationError, match="new_type"):
        ChangeRequest(
            asset_urn=TARGET,
            operation=ChangeOperation.TYPE_CHANGE,
            field="customer_email",
            old_type="STRING",
            source_commit="demo-unsafe-change",
            requested_by="demo-user",
        )


def test_type_change_rejects_sql_tokens_in_type_name() -> None:
    with pytest.raises(ValidationError, match="new_type"):
        ChangeRequest(
            asset_urn=TARGET,
            operation=ChangeOperation.TYPE_CHANGE,
            field="customer_email",
            old_type="STRING",
            new_type="STRING); drop table secrets; --",
            source_commit="demo-unsafe-change",
            requested_by="demo-user",
        )


@pytest.mark.parametrize(
    "new_type",
    [
        "NUMBER(1,99)",
        "NUMBER(1,2)",
        "NUMBER(38,38)",
        "NUMBER(39,0)",
        "DECIMAL(0,0)",
        "VARCHAR(0)",
        "VARCHAR(134217729)",
        "BINARY(67108865)",
        "BOOLEAN(1)",
        "TIMESTAMP(1,2)",
        "TIMESTAMP(10)",
        "INTEGER(10)",
        "UNSUPPORTED_TYPE",
    ],
)
def test_type_change_rejects_invalid_snowflake_type_parameters(
    new_type: str,
) -> None:
    with pytest.raises(ValidationError, match="new_type"):
        ChangeRequest(
            asset_urn=TARGET,
            operation=ChangeOperation.TYPE_CHANGE,
            field="customer_email",
            old_type="STRING",
            new_type=new_type,
            source_commit="invalid-type-parameters",
            requested_by="demo-user",
        )


@pytest.mark.parametrize(
    "new_type",
    [
        "NUMBER(38,37)",
        "NUMBER(1,1)",
        "VARCHAR(134217728)",
        "VARCHAR(99999999)",
        "BINARY(67108864)",
        "TIMESTAMP_NTZ(9)",
        "TIME(0)",
        "BOOLEAN",
    ],
)
def test_type_change_accepts_documented_snowflake_type_bounds(
    new_type: str,
) -> None:
    change = ChangeRequest(
        asset_urn=TARGET,
        operation=ChangeOperation.TYPE_CHANGE,
        field="customer_email",
        old_type="STRING",
        new_type=new_type,
        source_commit="valid-type-parameters",
        requested_by="demo-user",
    )

    assert change.new_type == new_type


def test_unknown_change_keys_are_rejected() -> None:
    with pytest.raises(ValidationError, match="extra_forbidden"):
        ChangeRequest.model_validate(
            {
                "asset_urn": TARGET,
                "operation": "remove",
                "field": "customer_email",
                "source_commit": "demo-unsafe-change",
                "requested_by": "demo-user",
                "warehouse_password": "must-not-be-accepted",
            }
        )


def test_context_requires_snapshot_hash_only_in_snapshot_mode() -> None:
    base = {
        "target_urn": TARGET,
        "target_name": "dim_customers",
        "target_domain": "Analytics",
        "field": "customer_email",
        "field_type": "STRING",
        "provenance": ContextProvenance(
            mode=ContextMode.SNAPSHOT,
            retrieved_at=datetime(2026, 8, 6, tzinfo=UTC),
            adapter_version="1.0.0",
        ),
    }

    with pytest.raises(ValidationError, match="snapshot_hash"):
        ContextBundle.model_validate(base)


def test_documented_golden_change_is_a_valid_request() -> None:
    example = Path("examples/unsafe-change/change.json")

    change = ChangeRequest.model_validate(
        json.loads(example.read_text(encoding="utf-8"))
    )

    assert change.asset_urn == TARGET
    assert change.operation is ChangeOperation.RENAME
    assert change.new_field == "primary_email"


def test_warehouse_result_forbids_raw_rows_and_unknown_fields() -> None:
    with pytest.raises(ValidationError) as exc_info:
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
                "checks": [
                    {
                        "code": "no_unsafe_rows",
                        "label": "No unsafe rows",
                        "passed": True,
                        "detail": "No unsafe rows were found.",
                    }
                ],
                "raw_rows": [{"order_status": "secret"}],
            }
        )

    assert any(
        error["loc"] == ("raw_rows",) and error["type"] == "extra_forbidden"
        for error in exc_info.value.errors()
    )


def test_warehouse_result_requires_passing_aggregate_checks_for_passed_status() -> None:
    with pytest.raises(ValidationError, match="passed warehouse evidence"):
        WarehouseValidationResult(
            status=WarehouseValidationStatus.PASSED,
            mode=WarehouseValidationMode.AGGREGATE,
            environment_label="competition-non-production",
            operation=ChangeOperation.REMOVE,
            field="order_status",
        )


def test_not_run_warehouse_result_cannot_claim_query_execution() -> None:
    with pytest.raises(ValidationError, match="not-run evidence"):
        WarehouseValidationResult(
            status=WarehouseValidationStatus.NOT_RUN,
            mode=WarehouseValidationMode.NONE,
            environment_label="competition-non-production",
            operation=ChangeOperation.REMOVE,
            field="order_status",
            query_ids=["query-id"],
        )


def test_warehouse_counts_require_an_explicit_started_query() -> None:
    with pytest.raises(ValidationError, match="counts require an aggregate query"):
        WarehouseValidationResult(
            status=WarehouseValidationStatus.BLOCKED,
            mode=WarehouseValidationMode.AGGREGATE,
            environment_label="competition-non-production",
            operation=ChangeOperation.REMOVE,
            field="order_status",
            aggregate_query_started=False,
            rows_evaluated=0,
        )


def complete_passed_warehouse_payload(
    operation: ChangeOperation = ChangeOperation.RENAME,
) -> dict[str, object]:
    operation_code = {
        ChangeOperation.RENAME: "rename_projection",
        ChangeOperation.REMOVE: "remove_impact",
        ChangeOperation.TYPE_CHANGE: "type_conversion",
    }[operation]
    return {
        "status": "passed",
        "mode": "aggregate",
        "environment_label": "competition-non-production",
        "operation": operation.value,
        "field": "customer_email",
        "aggregate_query_started": True,
        "binding_fingerprint": "a" * 64,
        "started_at": "2026-08-09T12:00:00Z",
        "completed_at": "2026-08-09T12:00:01Z",
        "rows_evaluated": 20,
        "populated_row_count": 10,
        "unsafe_row_count": 0 if operation is ChangeOperation.TYPE_CHANGE else None,
        "query_ids": ["identity-query-id", "schema-query-id", "aggregate-query-id"],
        "elapsed_ms": 1000,
        "checks": [
            {
                "code": "warehouse_identity",
                "label": "Warehouse identity",
                "passed": True,
                "detail": "Identity passed.",
            },
            {
                "code": "warehouse_schema",
                "label": "Warehouse schema",
                "passed": True,
                "detail": "Schema passed.",
            },
            {
                "code": operation_code,
                "label": "Operation evidence",
                "passed": True,
                "detail": "Operation evidence passed.",
                "observed_count": (
                    0 if operation is ChangeOperation.TYPE_CHANGE else None
                ),
            },
        ],
    }


@pytest.mark.parametrize(
    "update",
    [
        {"started_at": None},
        {"started_at": "2026-08-09T12:00:00"},
        {"completed_at": None},
        {"completed_at": "2026-08-09T12:00:01"},
        {"rows_evaluated": 0},
        {"populated_row_count": 0},
        {"query_ids": []},
        {"query_ids": ["unsafe query id"]},
        {
            "checks": [
                {
                    "code": "warehouse_identity",
                    "label": "Warehouse identity",
                    "passed": True,
                    "detail": "Identity passed.",
                },
                {
                    "code": "warehouse_schema",
                    "label": "Warehouse schema",
                    "passed": True,
                    "detail": "Schema passed.",
                },
            ]
        },
    ],
)
def test_passed_warehouse_evidence_requires_complete_semantics(
    update: dict[str, object],
) -> None:
    payload = {**complete_passed_warehouse_payload(), **update}

    with pytest.raises(ValidationError, match="complete warehouse evidence"):
        WarehouseValidationResult.model_validate(payload)


def test_passed_type_change_requires_zero_unsafe_conversions() -> None:
    payload = complete_passed_warehouse_payload(ChangeOperation.TYPE_CHANGE)
    payload["unsafe_row_count"] = 1
    checks = payload["checks"]
    assert isinstance(checks, list)
    operation_check = checks[-1]
    assert isinstance(operation_check, dict)
    operation_check["observed_count"] = 1

    with pytest.raises(ValidationError, match="complete warehouse evidence"):
        WarehouseValidationResult.model_validate(payload)
