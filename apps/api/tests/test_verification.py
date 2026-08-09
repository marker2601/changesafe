import asyncio

import pytest

from changesafe.context.replay import ReplayDataHubContext
from changesafe.demo import DEMO_TARGET_URN, golden_change
from changesafe.domain import (
    ArtifactBundle,
    ArtifactFile,
    ChangeOperation,
)
from changesafe.generation.templates import generate_artifacts
from changesafe.risk import score_change
from changesafe.verification import verify_artifacts

TARGET = DEMO_TARGET_URN
MODEL_SQL = "models/marts/order_details__changesafe.sql"
MODEL_YAML = "models/marts/order_details__changesafe.yml"


def golden_inputs():
    change = golden_change()
    context = asyncio.run(ReplayDataHubContext.from_default().load(change))
    bundle = generate_artifacts(change, context, score_change(change, context))
    return change, context, bundle


def replace_file(bundle: ArtifactBundle, path: str, content: str) -> ArtifactBundle:
    files = dict(bundle.files)
    files[path] = ArtifactFile(path=path, content=content)
    return ArtifactBundle(files=files, manifest_hash=bundle.manifest_hash)


def test_golden_artifacts_pass_every_blocking_check() -> None:
    change, context, bundle = golden_inputs()

    report = verify_artifacts(bundle, change, context)

    assert report.passed is True
    assert len(report.checks) == 12
    assert all(check.passed for check in report.checks if check.blocking)


@pytest.mark.parametrize(
    ("field", "new_field"),
    [
        ("cust_email", "primary_email"),
        ("order_total", "preferred_order_total"),
        ("order_status", "preferred_order_status"),
    ],
)
def test_all_blocking_checks_validate_each_selected_field_package(
    field: str,
    new_field: str,
) -> None:
    """Verification must validate the package bound to the selected context."""
    change = golden_change().model_copy(
        update={
            "field": field,
            "new_field": new_field,
            "source_commit": f"verification-proof-{field}",
        }
    )
    context = asyncio.run(ReplayDataHubContext.from_default().load(change))
    bundle = generate_artifacts(change, context, score_change(change, context))

    report = verify_artifacts(bundle, change, context)

    assert context.field == change.field
    assert report.passed is True
    assert len(report.checks) == 12
    assert all(check.passed for check in report.checks if check.blocking)


def test_remove_guard_has_operation_specific_validation_language() -> None:
    change = golden_change().model_copy(
        update={"operation": ChangeOperation.REMOVE, "new_field": None}
    )
    context = asyncio.run(ReplayDataHubContext.from_default().load(change))
    bundle = generate_artifacts(change, context, score_change(change, context))

    check = verify_artifacts(bundle, change, context).check("compatibility_test")

    assert check.label == "Phase-one removal guard references the field"
    assert "when dbt executes it" in check.detail
    assert "missing-column error" in check.detail


def test_legacy_invalid_type_parameters_fail_context_alignment() -> None:
    rename, context, _bundle = golden_inputs()
    valid = rename.model_copy(
        update={
            "operation": ChangeOperation.TYPE_CHANGE,
            "new_field": None,
            "old_type": "STRING",
            "new_type": "NUMBER(10,2)",
        }
    )
    bundle = generate_artifacts(valid, context, score_change(valid, context))
    legacy_invalid = valid.model_copy(update={"new_type": "NUMBER(1,99)"})

    report = verify_artifacts(bundle, legacy_invalid, context)

    assert report.passed is False
    assert report.check("request_context_alignment").passed is False


def test_select_star_in_model_blocks_publication() -> None:
    change, context, bundle = golden_inputs()
    invalid = replace_file(
        bundle,
        MODEL_SQL,
        "select * from {{ ref('stg_customers') }}\n",
    )

    report = verify_artifacts(invalid, change, context)

    assert report.passed is False
    assert report.check("no_select_star").passed is False


def test_compatibility_shim_cannot_reference_itself_or_an_inferred_source() -> None:
    change, context, bundle = golden_inputs()
    invalid = replace_file(
        bundle,
        MODEL_SQL,
        bundle.files[MODEL_SQL].content.replace(
            "ref('order_details')",
            "ref('order_details__changesafe')",
        ),
    )

    report = verify_artifacts(invalid, change, context)

    assert report.passed is False
    assert report.check("source_relations").passed is False


def test_path_traversal_blocks_publication() -> None:
    change, context, bundle = golden_inputs()
    files = dict(bundle.files)
    files["../escape.sql"] = ArtifactFile(
        path="../escape.sql", content="select 1 as safe_value\n"
    )

    report = verify_artifacts(
        ArtifactBundle(files=files, manifest_hash=bundle.manifest_hash),
        change,
        context,
    )

    assert report.passed is False
    assert report.check("paths_confined").passed is False


def test_yaml_missing_new_field_blocks_publication() -> None:
    change, context, bundle = golden_inputs()
    invalid = replace_file(
        bundle,
        MODEL_YAML,
        "version: 2\nmodels:\n  - name: order_details__changesafe\n    columns: []\n",
    )

    report = verify_artifacts(invalid, change, context)

    assert report.passed is False
    assert report.check("yaml_contract").passed is False


def test_manifest_hash_tampering_blocks_publication() -> None:
    change, context, bundle = golden_inputs()
    invalid = replace_file(
        bundle,
        "PR_BODY.md",
        bundle.files["PR_BODY.md"].content + "\nUnverified edit.\n",
    )

    report = verify_artifacts(invalid, change, context)

    assert report.passed is False
    assert report.check("manifest_hashes").passed is False


def test_generated_expression_cannot_smuggle_a_subquery() -> None:
    change, context, bundle = golden_inputs()
    unsafe_sql = bundle.files[MODEL_SQL].content.replace(
        "cust_email as primary_email",
        (
            "cust_email || "
            "(select max(secret) from sensitive_table) as primary_email"
        ),
    )
    invalid = replace_file(bundle, MODEL_SQL, unsafe_sql)

    report = verify_artifacts(invalid, change, context)

    assert report.passed is False
    assert report.check("source_relations").passed is False


def test_duplicate_case_insensitive_output_names_block_publication() -> None:
    change, context, bundle = golden_inputs()
    duplicate_sql = bundle.files[MODEL_SQL].content.replace(
        "cust_email as primary_email",
        "cust_email as CUSTOMER_ID",
    )
    duplicate_yaml = bundle.files[MODEL_YAML].content.replace(
        "name: primary_email",
        "name: CUSTOMER_ID",
    )
    invalid = replace_file(bundle, MODEL_SQL, duplicate_sql)
    invalid = replace_file(invalid, MODEL_YAML, duplicate_yaml)

    report = verify_artifacts(invalid, change, context)

    assert report.passed is False
    assert report.check("unique_output_names").passed is False
