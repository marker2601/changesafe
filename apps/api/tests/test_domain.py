import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from changesafe.domain import (
    ChangeOperation,
    ChangeRequest,
    ContextBundle,
    ContextMode,
    ContextProvenance,
)

TARGET = "urn:li:dataset:(urn:li:dataPlatform:dbt,analytics.dim_customers,PROD)"


def test_rename_requires_new_field() -> None:
    with pytest.raises(ValidationError, match="new_field"):
        ChangeRequest(
            asset_urn=TARGET,
            operation=ChangeOperation.RENAME,
            field="customer_email",
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
