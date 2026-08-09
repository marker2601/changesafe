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
