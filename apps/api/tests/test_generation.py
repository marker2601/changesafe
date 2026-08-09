import asyncio
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from changesafe.context.replay import ReplayDataHubContext
from changesafe.demo import DEMO_TARGET_URN, golden_change
from changesafe.domain import (
    AffectedAsset,
    ChangeOperation,
    ChangeRequest,
    LineagePrecision,
    SchemaField,
)
from changesafe.generation.templates import (
    GenerationNarrative,
    expected_artifact_paths,
    generate_artifacts,
)
from changesafe.risk import score_change
from changesafe.verification import verify_artifacts

TARGET = DEMO_TARGET_URN


def test_golden_rename_generates_exact_manifest() -> None:
    change = golden_change()
    context = asyncio.run(ReplayDataHubContext.from_default().load(change))
    risk = score_change(change, context)

    bundle = generate_artifacts(change, context, risk)

    assert sorted(bundle.files) == sorted(expected_artifact_paths(change, context))
    model = bundle.files["models/marts/order_details__changesafe.sql"].content
    assert "cust_email" in model
    assert "cust_email as primary_email" in model.lower()
    assert bundle.manifest_hash == bundle.files["changesafe-manifest.json"].sha256


@pytest.mark.parametrize(
    ("field", "new_field"),
    [
        ("cust_email", "primary_email"),
        ("order_total", "preferred_order_total"),
        ("order_status", "preferred_order_status"),
    ],
)
def test_compatibility_shim_uses_the_governed_model_as_its_only_source(
    field: str,
    new_field: str,
) -> None:
    """Field lineage cannot stand in for a complete 55-column source relation."""
    change = golden_change().model_copy(
        update={
            "field": field,
            "new_field": new_field,
            "source_commit": f"shim-source-{field}",
        }
    )
    context = asyncio.run(ReplayDataHubContext.from_default().load(change))

    bundle = generate_artifacts(change, context, score_change(change, context))

    shim = "models/marts/order_details__changesafe.sql"
    shim_yaml = "models/marts/order_details__changesafe.yml"
    compatibility_test = f"tests/assert_{field}_compatibility.sql"
    assert shim in bundle.files
    assert shim_yaml in bundle.files
    assert f"{field} as {new_field}" in bundle.files[shim].content.lower()
    assert "ref('order_details')" in bundle.files[shim].content
    assert "ref('customers')" not in bundle.files[shim].content
    assert "ref('orders')" not in bundle.files[shim].content
    assert "ref('order_details__changesafe')" not in bundle.files[shim].content
    assert "name: order_details__changesafe" in bundle.files[shim_yaml].content
    assert (
        "ref('order_details__changesafe')"
        in bundle.files[compatibility_test].content
    )


@pytest.mark.parametrize(
    ("field", "new_field"),
    [
        ("cust_email", "primary_email"),
        ("order_total", "preferred_order_total"),
        ("order_status", "preferred_order_status"),
    ],
)
def test_rename_generation_uses_the_selected_field_in_the_model_and_manifest(
    field: str,
    new_field: str,
) -> None:
    """Changing the selected field changes the generated compatibility package."""
    change = golden_change().model_copy(
        update={
            "field": field,
            "new_field": new_field,
            "source_commit": f"generation-proof-{field}",
        }
    )
    context = asyncio.run(ReplayDataHubContext.from_default().load(change))

    bundle = generate_artifacts(change, context, score_change(change, context))

    model = bundle.files["models/marts/order_details__changesafe.sql"].content
    assert f"{field} as {new_field}" in model.lower()
    assert f"tests/assert_{field}_compatibility.sql" in bundle.files
    assert bundle.manifest_hash == bundle.files["changesafe-manifest.json"].sha256


def test_generation_narrative_rejects_fields_outside_the_bounded_schema() -> None:
    with pytest.raises(ValidationError, match="extra_forbidden"):
        GenerationNarrative.model_validate(
            {
                "transformation_expression": "customer_email",
                "explanation": "Preserve the source value.",
                "deprecation_language": "Keep for 30 days.",
                "migration_summary": "Add the compatibility alias.",
                "rollback_summary": "Revert the generated files.",
                "pr_prose": "Introduces a safe alias.",
                "risk_score": 0,
            }
        )


def test_checked_in_example_bytes_match_deterministic_generation() -> None:
    change = golden_change()
    context = asyncio.run(ReplayDataHubContext.from_default().load(change))
    bundle = generate_artifacts(change, context, score_change(change, context))
    root = Path("examples/generated-safe-change")

    for path, artifact in bundle.files.items():
        assert (root / path).read_text(encoding="utf-8") == artifact.content


def test_sample_dbt_project_matches_the_generated_golden_migration() -> None:
    change = golden_change()
    context = asyncio.run(ReplayDataHubContext.from_default().load(change))
    bundle = generate_artifacts(change, context, score_change(change, context))
    root = Path("fixtures/dbt_project")

    for path in (
        "models/marts/order_details__changesafe.sql",
        "models/marts/order_details__changesafe.yml",
        "tests/assert_cust_email_compatibility.sql",
    ):
        assert (root / path).read_text(encoding="utf-8") == bundle.files[path].content


def test_dbt_fixture_keeps_the_governed_model_separate_from_the_shim() -> None:
    root = Path("fixtures/dbt_project/models/marts")

    base_sql = (root / "order_details.sql").read_text(encoding="utf-8")
    base_yaml = (root / "order_details.yml").read_text(encoding="utf-8")

    assert "ref('stg_order_details')" in base_sql
    assert "primary_email" not in base_sql
    assert "customers" not in base_sql
    assert "name: order_details" in base_yaml
    assert "order_details__changesafe" not in base_yaml
    assert "primary_email" not in base_yaml


@pytest.mark.parametrize(
    ("change", "expected_test", "expected_projection"),
    [
        (
            ChangeRequest(
                asset_urn=TARGET,
                operation=ChangeOperation.REMOVE,
                field="cust_email",
                old_type="TEXT",
                source_commit="remove-email",
                requested_by="demo-user",
            ),
            "tests/assert_cust_email_retained.sql",
            "cust_email",
        ),
        (
            ChangeRequest(
                asset_urn=TARGET,
                operation=ChangeOperation.TYPE_CHANGE,
                field="cust_email",
                old_type="TEXT",
                new_type="VARCHAR(320)",
                source_commit="type-email",
                requested_by="demo-user",
            ),
            "tests/assert_cust_email_type_compatibility.sql",
            "cast(cust_email as VARCHAR(320)) as cust_email__new_type",
        ),
    ],
)
def test_each_supported_operation_generates_and_verifies(
    change: ChangeRequest,
    expected_test: str,
    expected_projection: str,
) -> None:
    context = asyncio.run(ReplayDataHubContext.from_default().load(change))
    risk = score_change(change, context)

    bundle = generate_artifacts(change, context, risk)
    report = verify_artifacts(bundle, change, context)

    assert report.passed is True
    assert set(bundle.files) == set(expected_artifact_paths(change, context))
    assert expected_test in bundle.files
    assert (
        expected_projection
        in bundle.files["models/marts/order_details__changesafe.sql"].content
    )


def test_remove_guard_explains_zero_row_and_warehouse_execution_semantics() -> None:
    change = ChangeRequest(
        asset_urn=TARGET,
        operation=ChangeOperation.REMOVE,
        field="cust_email",
        source_commit="showcase-ecommerce-safe-remove",
        requested_by="changesafe-demo",
    )
    context = asyncio.run(ReplayDataHubContext.from_default().load(change))

    bundle = generate_artifacts(change, context, score_change(change, context))

    assert bundle.files["tests/assert_cust_email_retained.sql"].content == (
        "-- Phase-one safety guard: dbt returns zero rows while this field exists.\n"
        "-- If cust_email is removed too early, warehouse execution fails on the "
        "missing column.\n"
        "select cust_email\n"
        "from {{ ref('order_details__changesafe') }}\n"
        "where false\n"
    )


def test_type_change_uses_shared_alias_aware_metadata_comparison() -> None:
    change = ChangeRequest(
        asset_urn=TARGET,
        operation=ChangeOperation.TYPE_CHANGE,
        field="cust_email",
        old_type="TEXT",
        new_type="VARCHAR(200)",
        source_commit="alias-aware-type-change",
        requested_by="demo-user",
    )
    context = asyncio.run(ReplayDataHubContext.from_default().load(change))
    context = context.model_copy(
        update={
            "field_type": "VARCHAR",
            "schema_fields": [
                field.model_copy(update={"data_type": "VARCHAR"})
                if field.name == change.field
                else field
                for field in context.schema_fields
            ],
        }
    )

    risk = score_change(change, context)
    bundle = generate_artifacts(change, context, risk)
    report = verify_artifacts(bundle, change, context)

    assert risk.factors[0].code == "base_type_change"
    assert report.passed is True


def test_custom_seeded_field_and_model_names_are_not_hard_coded() -> None:
    change = ChangeRequest(
        asset_urn="urn:li:dataset:(urn:li:dataPlatform:dbt,analytics.fct_orders,PROD)",
        operation=ChangeOperation.RENAME,
        field="loyalty_code",
        new_field="customer_loyalty_code",
        old_type="STRING",
        source_commit="rename-loyalty",
        requested_by="demo-user",
    )
    base_context = asyncio.run(
        ReplayDataHubContext.from_default().load(golden_change())
    )
    context = base_context.model_copy(
        update={
            "target_urn": change.asset_urn,
            "target_name": "fct_orders",
            "field": "loyalty_code",
            "field_type": "STRING",
            "schema_fields": [
                SchemaField(name="order_id", data_type="STRING", nullable=False),
                SchemaField(name="loyalty_code", data_type="STRING"),
            ],
            "upstream_assets": [
                AffectedAsset(
                    urn=(
                        "urn:li:dataset:(urn:li:dataPlatform:dbt,"
                        "analytics.stg_orders,PROD)"
                    ),
                    name="stg_orders",
                    entity_type="dataset",
                    field="loyalty_code",
                    lineage_precision=LineagePrecision.ENDPOINT_FIELD,
                )
            ],
        }
    )
    bundle = generate_artifacts(change, context, score_change(change, context))

    assert "models/marts/fct_orders__changesafe.sql" in bundle.files
    assert "models/marts/fct_orders__changesafe.yml" in bundle.files
    model = bundle.files["models/marts/fct_orders__changesafe.sql"].content
    assert "order_id" in model
    assert "loyalty_code as customer_loyalty_code" in model
    assert "ref('fct_orders')" in model
    assert verify_artifacts(bundle, change, context).passed is True


def test_llm_transformation_expression_is_advisory_not_executable() -> None:
    change = golden_change()
    context = asyncio.run(ReplayDataHubContext.from_default().load(change))
    narrative = GenerationNarrative(
        transformation_expression=(
            "cust_email || (select max(secret) from sensitive_table)"
        ),
        explanation="Explain the change.",
        deprecation_language="Retain the old field for 30 days.",
        migration_summary="Use a compatibility alias.",
        rollback_summary="Revert the generated files.",
        pr_prose="Introduce the safe migration.",
    )

    bundle = generate_artifacts(
        change, context, score_change(change, context), narrative
    )
    model = bundle.files["models/marts/order_details__changesafe.sql"].content

    assert "sensitive_table" not in model
    assert "cust_email as primary_email" in model


def test_rename_rejects_case_insensitive_destination_collision() -> None:
    change = golden_change().model_copy(update={"new_field": "CUSTOMER_ID"})
    context = asyncio.run(ReplayDataHubContext.from_default().load(change))

    with pytest.raises(ValueError, match="already exists in the DataHub schema"):
        generate_artifacts(change, context, score_change(change, context))


def test_type_change_rejects_generated_alias_collision() -> None:
    change = ChangeRequest(
        asset_urn=TARGET,
        operation=ChangeOperation.TYPE_CHANGE,
        field="cust_email",
        old_type="TEXT",
        new_type="VARCHAR(320)",
        source_commit="type-alias-collision",
        requested_by="demo-user",
    )
    context = asyncio.run(ReplayDataHubContext.from_default().load(change))
    context = context.model_copy(
        update={
            "schema_fields": [
                *context.schema_fields,
                SchemaField(
                    name="CUST_EMAIL__NEW_TYPE",
                    data_type="VARCHAR(320)",
                ),
            ]
        }
    )

    with pytest.raises(ValueError, match="already exists in the DataHub schema"):
        generate_artifacts(change, context, score_change(change, context))


def test_rename_contract_uses_datahub_type_not_request_hints() -> None:
    change = golden_change()
    context = asyncio.run(ReplayDataHubContext.from_default().load(change))
    context = context.model_copy(
        update={
            "field_type": "INT",
            "schema_fields": [
                field.model_copy(update={"data_type": "INT"})
                if field.name == change.field
                else field
                for field in context.schema_fields
            ],
        }
    )

    bundle = generate_artifacts(change, context, score_change(change, context))
    contract = yaml.safe_load(
        bundle.files["models/marts/order_details__changesafe.yml"].content
    )
    columns = contract["models"][0]["columns"]
    preferred = next(column for column in columns if column["name"] == "primary_email")

    assert preferred["data_type"] == "INT"


def test_nullable_alias_inherits_nullability_without_invented_not_null() -> None:
    change = golden_change()
    context = asyncio.run(ReplayDataHubContext.from_default().load(change))
    context = context.model_copy(
        update={
            "schema_fields": [
                field.model_copy(update={"nullable": True})
                if field.name == change.field
                else field
                for field in context.schema_fields
            ]
        }
    )

    bundle = generate_artifacts(change, context, score_change(change, context))
    contract = yaml.safe_load(
        bundle.files["models/marts/order_details__changesafe.yml"].content
    )
    columns = contract["models"][0]["columns"]
    changed = {
        column["name"]: column.get("tests", [])
        for column in columns
        if column["name"] in {"cust_email", "primary_email"}
    }

    assert changed == {"cust_email": [], "primary_email": []}


def test_non_null_id_fields_do_not_invent_uniqueness_constraints() -> None:
    change = ChangeRequest(
        asset_urn=TARGET,
        operation=ChangeOperation.RENAME,
        field="customer_id",
        new_field="account_id",
        old_type="STRING",
        source_commit="rename-customer-id",
        requested_by="demo-user",
    )
    context = asyncio.run(ReplayDataHubContext.from_default().load(golden_change()))
    context = context.model_copy(
        update={"field": "customer_id", "field_type": "NUMBER"}
    )

    bundle = generate_artifacts(change, context, score_change(change, context))
    contract = yaml.safe_load(
        bundle.files["models/marts/order_details__changesafe.yml"].content
    )
    columns = contract["models"][0]["columns"]
    changed = {
        column["name"]: column.get("tests", [])
        for column in columns
        if column["name"] in {"customer_id", "account_id"}
    }

    assert changed == {"customer_id": ["not_null"], "account_id": ["not_null"]}
