import asyncio
import json

import pytest

from changesafe.context.replay import ReplayDataHubContext
from changesafe.demo import DEMO_TARGET_URN, golden_change
from changesafe.domain import (
    ArtifactBundle,
    ArtifactFile,
    ChangeOperation,
)
from changesafe.generation.templates import GenerationNarrative, generate_artifacts
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


def replace_file_with_recomputed_manifest(
    bundle: ArtifactBundle,
    path: str,
    content: str,
) -> ArtifactBundle:
    files = dict(bundle.files)
    files[path] = ArtifactFile(path=path, content=content)
    manifest = json.loads(files["changesafe-manifest.json"].content)
    manifest["files"] = {
        artifact_path: artifact.sha256
        for artifact_path, artifact in files.items()
        if artifact_path != "changesafe-manifest.json"
    }
    manifest_content = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    files["changesafe-manifest.json"] = ArtifactFile(
        path="changesafe-manifest.json",
        content=manifest_content,
    )
    return ArtifactBundle(
        files=files,
        manifest_hash=files["changesafe-manifest.json"].sha256,
    )


def test_golden_artifacts_pass_every_blocking_check() -> None:
    change, context, bundle = golden_inputs()

    report = verify_artifacts(bundle, change, context)

    assert report.passed is True
    assert len(report.checks) == 12
    assert all(check.passed for check in report.checks if check.blocking)


@pytest.mark.parametrize(
    "context_update",
    [
        {"target_urn": "urn:li:dataset:(urn:li:dataPlatform:dbt,finance.wrong,PROD)"},
        {"field": "order_total"},
    ],
)
def test_context_alignment_rejects_context_for_a_different_request(
    context_update: dict[str, str],
) -> None:
    change, context, _bundle = golden_inputs()
    mismatched = context.model_copy(update=context_update)
    bundle = generate_artifacts(change, mismatched, score_change(change, mismatched))

    report = verify_artifacts(bundle, change, mismatched)

    assert report.check("request_context_alignment").passed is False
    assert report.passed is False


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


def test_compatibility_test_rejects_a_hashed_comment_spoof_and_wrong_relation() -> None:
    change, context, bundle = golden_inputs()
    forged = replace_file_with_recomputed_manifest(
        bundle,
        "tests/assert_cust_email_compatibility.sql",
        "select cust_email\n"
        "from {{ ref('order_details') }}\n"
        "where false\n"
        "-- primary_email is distinct from cust_email\n",
    )

    report = verify_artifacts(forged, change, context)

    assert report.check("manifest_hashes").passed is False
    assert report.check("compatibility_test").passed is False


def test_compatibility_test_rejects_a_hashed_extra_statement() -> None:
    change, context, bundle = golden_inputs()
    original = bundle.files["tests/assert_cust_email_compatibility.sql"].content
    forged = replace_file_with_recomputed_manifest(
        bundle,
        "tests/assert_cust_email_compatibility.sql",
        f"{original}\nselect 1 as unexpected_statement\n",
    )

    report = verify_artifacts(forged, change, context)

    assert report.check("manifest_hashes").passed is False
    assert report.check("compatibility_test").passed is False


@pytest.mark.parametrize(
    ("change", "test_path", "spoofed_sql"),
    [
        (
            golden_change(),
            "tests/assert_cust_email_compatibility.sql",
            "select x.cust_email\n"
            "from {{ ref('order_details__changesafe') }}\n"
            "where x.cust_email is distinct from x.primary_email\n",
        ),
        (
            golden_change().model_copy(
                update={"operation": ChangeOperation.REMOVE, "new_field": None}
            ),
            "tests/assert_cust_email_retained.sql",
            "select x.cust_email\n"
            "from {{ ref('order_details__changesafe') }}\n"
            "where false\n",
        ),
        (
            golden_change().model_copy(
                update={
                    "operation": ChangeOperation.TYPE_CHANGE,
                    "new_field": None,
                    "new_type": "VARCHAR(320)",
                }
            ),
            "tests/assert_cust_email_type_compatibility.sql",
            "select x.cust_email\n"
            "from {{ ref('order_details__changesafe') }}\n"
            "where cast(x.cust_email as VARCHAR(320)) "
            "is distinct from x.cust_email__new_type\n",
        ),
    ],
)
def test_compatibility_test_rejects_undefined_qualified_columns(
    change, test_path: str, spoofed_sql: str
) -> None:
    context = asyncio.run(ReplayDataHubContext.from_default().load(change))
    bundle = generate_artifacts(change, context, score_change(change, context))
    forged = replace_file_with_recomputed_manifest(bundle, test_path, spoofed_sql)

    report = verify_artifacts(forged, change, context)

    assert report.check("manifest_hashes").passed is False
    assert report.check("compatibility_test").passed is False


def test_source_relations_rejects_a_comment_only_governed_ref() -> None:
    change, context, bundle = golden_inputs()
    forged = replace_file_with_recomputed_manifest(
        bundle,
        MODEL_SQL,
        bundle.files[MODEL_SQL].content.replace(
            "from {{ ref('order_details') }}",
            "from customers -- {{ ref('order_details') }}",
        ),
    )

    report = verify_artifacts(forged, change, context)

    assert report.check("manifest_hashes").passed is False
    assert report.check("source_relations").passed is False
    assert report.passed is False


@pytest.mark.parametrize(
    ("path", "needle"),
    [
        (
            "migrations/2026-08-09-cust-email-rename.md",
            "The governed base model remains unchanged in phase one",
        ),
        ("PR_BODY.md", "order_details__changesafe"),
        ("PR_BODY.md", "Downstream owners must switch to `order_details__changesafe`"),
    ],
)
def test_operational_transition_checks_reject_hashed_missing_guidance(
    path: str, needle: str
) -> None:
    change, context, bundle = golden_inputs()
    forged = replace_file_with_recomputed_manifest(
        bundle,
        path,
        bundle.files[path].content.replace(needle, "Removed review guidance"),
    )

    report = verify_artifacts(forged, change, context)

    assert report.check("manifest_hashes").passed is False
    assert report.check("migration_notes").passed is False


def test_rollback_check_rejects_hashed_consumer_move_after_removal() -> None:
    change, context, bundle = golden_inputs()
    rollback = bundle.files["ROLLBACK.md"].content
    consumer_step = (
        "1. Move downstream consumers from `order_details__changesafe` back to "
        "`order_details` before removing generated artifacts.\n"
    )
    forged = replace_file_with_recomputed_manifest(
        bundle,
        "ROLLBACK.md",
        rollback.replace(consumer_step, "").replace(
            "2. Confirm `cust_email` remains available to every downstream consumer.\n",
            "1. Confirm `cust_email` remains available to every downstream consumer.\n"
            "6. Move downstream consumers from `order_details__changesafe` back to "
            "`order_details`.\n",
        ),
    )

    report = verify_artifacts(forged, change, context)

    assert report.check("manifest_hashes").passed is False
    assert report.check("rollback_instructions").passed is False


def test_rollback_check_rejects_hashed_confirmation_after_removal() -> None:
    change, context, bundle = golden_inputs()
    rollback = bundle.files["ROLLBACK.md"].content
    confirmation = (
        "2. Confirm `cust_email` remains available to every downstream consumer.\n"
    )
    forged = replace_file_with_recomputed_manifest(
        bundle,
        "ROLLBACK.md",
        rollback.replace(confirmation, "").replace(
            "6. Run `dbt parse` and the project test suite before republishing.\n",
            "6. Confirm `cust_email` remains available to every downstream consumer.\n"
            "7. Run `dbt parse` and the project test suite before republishing.\n",
        ),
    )

    report = verify_artifacts(forged, change, context)

    assert report.check("manifest_hashes").passed is False
    assert report.check("rollback_instructions").passed is False


def test_source_relations_binds_the_from_relation_to_a_real_dbt_ref() -> None:
    change, context, bundle = golden_inputs()
    forged = replace_file_with_recomputed_manifest(
        bundle,
        MODEL_SQL,
        bundle.files[MODEL_SQL].content.replace(
            "    order_id,",
            "    concat('{{ ref(\"order_details\") }}', order_id) as order_id,",
        ).replace("from {{ ref('order_details') }}", "from order_details"),
    )

    report = verify_artifacts(forged, change, context)

    assert report.check("manifest_hashes").passed is False
    assert report.check("source_relations").passed is False
    assert report.passed is False


def test_source_relations_rejects_an_extra_live_governed_ref() -> None:
    change, context, bundle = golden_inputs()
    forged = replace_file_with_recomputed_manifest(
        bundle,
        MODEL_SQL,
        bundle.files[MODEL_SQL].content.replace(
            "    order_id,",
            "    concat({{ ref('order_details') }}, order_id) as order_id,",
        ),
    )

    report = verify_artifacts(forged, change, context)

    assert report.check("manifest_hashes").passed is False
    assert report.check("source_relations").passed is False


@pytest.mark.parametrize(
    "path",
    ["migrations/2026-08-09-cust-email-rename.md", "PR_BODY.md"],
)
def test_operational_transition_check_rejects_hashed_negated_actions(path: str) -> None:
    change, context, bundle = golden_inputs()
    forged = replace_file_with_recomputed_manifest(
        bundle,
        path,
        bundle.files[path]
        .content.replace("must switch to", "must never switch to")
        .replace("and migrate to", "and never migrate to"),
    )

    report = verify_artifacts(forged, change, context)

    assert report.check("manifest_hashes").passed is False
    assert report.check("migration_notes").passed is False


def test_operational_transition_check_rejects_hashed_prefixed_negation() -> None:
    change, context, bundle = golden_inputs()
    forged = replace_file_with_recomputed_manifest(
        bundle,
        "PR_BODY.md",
        bundle.files["PR_BODY.md"].content.replace(
            "Downstream owners must switch to",
            "Never follow: Downstream owners must switch to",
        ),
    )

    report = verify_artifacts(forged, change, context)

    assert report.check("manifest_hashes").passed is False
    assert report.check("migration_notes").passed is False


def test_rollback_check_rejects_hashed_negated_field_confirmation() -> None:
    change, context, bundle = golden_inputs()
    forged = replace_file_with_recomputed_manifest(
        bundle,
        "ROLLBACK.md",
        bundle.files["ROLLBACK.md"].content.replace(
            "Confirm `cust_email` remains available",
            "Do not confirm `cust_email` remains available",
        ),
    )

    report = verify_artifacts(forged, change, context)

    assert report.check("manifest_hashes").passed is False
    assert report.check("rollback_instructions").passed is False


@pytest.mark.parametrize(
    ("change", "test_path"),
    [
        (golden_change(), "tests/assert_cust_email_compatibility.sql"),
        (
            golden_change().model_copy(
                update={
                    "operation": ChangeOperation.TYPE_CHANGE,
                    "new_field": None,
                    "new_type": "VARCHAR(320)",
                }
            ),
            "tests/assert_cust_email_type_compatibility.sql",
        ),
    ],
)
def test_compatibility_test_rejects_hashed_limit_zero(
    change, test_path: str
) -> None:
    context = asyncio.run(ReplayDataHubContext.from_default().load(change))
    bundle = generate_artifacts(change, context, score_change(change, context))
    forged = replace_file_with_recomputed_manifest(
        bundle,
        test_path,
        bundle.files[test_path].content + "limit 0\n",
    )

    report = verify_artifacts(forged, change, context)

    assert report.check("manifest_hashes").passed is False
    assert report.check("compatibility_test").passed is False


@pytest.mark.parametrize(
    ("change", "test_path"),
    [
        (golden_change(), "tests/assert_cust_email_compatibility.sql"),
        (
            golden_change().model_copy(
                update={"operation": ChangeOperation.REMOVE, "new_field": None}
            ),
            "tests/assert_cust_email_retained.sql",
        ),
        (
            golden_change().model_copy(
                update={
                    "operation": ChangeOperation.TYPE_CHANGE,
                    "new_field": None,
                    "new_type": "VARCHAR(320)",
                }
            ),
            "tests/assert_cust_email_type_compatibility.sql",
        ),
    ],
)
def test_compatibility_test_rejects_hashed_execution_weakening_config(
    change, test_path: str
) -> None:
    context = asyncio.run(ReplayDataHubContext.from_default().load(change))
    bundle = generate_artifacts(change, context, score_change(change, context))
    forged = replace_file_with_recomputed_manifest(
        bundle,
        test_path,
        "{{ config(severity='warn', error_if='>999999') }}\n"
        + bundle.files[test_path].content,
    )

    report = verify_artifacts(forged, change, context)

    assert report.check("manifest_hashes").passed is False
    assert report.check("compatibility_test").passed is False


@pytest.mark.parametrize("suffix", ["where false\n", "limit 0\n"])
def test_source_relations_rejects_a_hashed_filtering_shim_model(suffix: str) -> None:
    change, context, bundle = golden_inputs()
    forged = replace_file_with_recomputed_manifest(
        bundle,
        MODEL_SQL,
        bundle.files[MODEL_SQL].content + suffix,
    )

    report = verify_artifacts(forged, change, context)

    assert report.check("manifest_hashes").passed is False
    assert report.check("source_relations").passed is False


@pytest.mark.parametrize(
    "conflicting_action",
    [
        "Downstream owners must not migrate to `primary_email`.\n",
        "Do not migrate to `primary_email`.\n",
    ],
)
def test_operational_transition_check_rejects_hashed_conflicting_action(
    conflicting_action: str,
) -> None:
    change, context, bundle = golden_inputs()
    forged = replace_file_with_recomputed_manifest(
        bundle,
        "PR_BODY.md",
        bundle.files["PR_BODY.md"].content + f"\n{conflicting_action}",
    )

    report = verify_artifacts(forged, change, context)

    assert report.check("manifest_hashes").passed is False
    assert report.check("migration_notes").passed is False


def test_rollback_check_rejects_a_hashed_duplicate_negated_step() -> None:
    change, context, bundle = golden_inputs()
    forged = replace_file_with_recomputed_manifest(
        bundle,
        "ROLLBACK.md",
        "1. Do not move downstream consumers from `order_details__changesafe` back "
        "to `order_details`.\n"
        + bundle.files["ROLLBACK.md"].content,
    )

    report = verify_artifacts(forged, change, context)

    assert report.check("manifest_hashes").passed is False
    assert report.check("rollback_instructions").passed is False


@pytest.mark.parametrize(
    "config",
    [
        "{{ config(enabled=false) }}",
        "{{ config(materialized='view', contract={'enforced': true}) }}",
    ],
)
def test_source_relations_rejects_a_hashed_weakened_shim_config(config: str) -> None:
    change, context, bundle = golden_inputs()
    forged = replace_file_with_recomputed_manifest(
        bundle,
        MODEL_SQL,
        bundle.files[MODEL_SQL].content.replace(
            "{{ config(materialized='table', contract={'enforced': true}) }}",
            config,
        ),
    )

    report = verify_artifacts(forged, change, context)

    assert report.check("manifest_hashes").passed is False
    assert report.check("source_relations").passed is False


def test_phase_one_contract_rejects_a_hashed_unrelated_column_transform() -> None:
    change, context, bundle = golden_inputs()
    forged = replace_file_with_recomputed_manifest(
        bundle,
        MODEL_SQL,
        bundle.files[MODEL_SQL].content.replace(
            "    order_id,", "    null as order_id,"
        ),
    )

    report = verify_artifacts(forged, change, context)

    assert report.check("manifest_hashes").passed is False
    assert report.check("phase_one_compatibility").passed is False


@pytest.mark.parametrize(
    "source",
    [
        "{{ ref('order_details') }} as source_alias",
        "analytics.{{ ref('order_details') }}",
    ],
)
def test_source_relations_rejects_an_aliased_or_prefixed_shim_ref(source: str) -> None:
    change, context, bundle = golden_inputs()
    forged = replace_file_with_recomputed_manifest(
        bundle,
        MODEL_SQL,
        bundle.files[MODEL_SQL].content.replace(
            "{{ ref('order_details') }}",
            source,
        ),
    )

    report = verify_artifacts(forged, change, context)

    assert report.check("manifest_hashes").passed is False
    assert report.check("source_relations").passed is False


@pytest.mark.parametrize(
    ("section", "key", "spoofed_value"),
    [
        ("change", "field", "not_the_real_field"),
        ("context", "target_urn", "urn:li:dataset:(wrong,target,PROD)"),
        ("context", "field", "not_the_real_field"),
        ("context", "field_type", "NUMBER(38,0)"),
        ("risk", "score", 0),
    ],
)
def test_manifest_hashes_reject_a_hashed_semantic_context_spoof(
    section: str, key: str, spoofed_value: object
) -> None:
    change, context, bundle = golden_inputs()
    files = dict(bundle.files)
    manifest = json.loads(files["changesafe-manifest.json"].content)
    manifest[section][key] = spoofed_value
    files["changesafe-manifest.json"] = ArtifactFile(
        path="changesafe-manifest.json",
        content=json.dumps(manifest, indent=2, sort_keys=True) + "\n",
    )
    forged = ArtifactBundle(
        files=files,
        manifest_hash=files["changesafe-manifest.json"].sha256,
    )

    report = verify_artifacts(forged, change, context)

    assert report.check("manifest_hashes").passed is False
    assert report.passed is False


def test_manifest_hashes_reject_an_arbitrary_rehashed_artifact_mutation() -> None:
    change, context, bundle = golden_inputs()
    forged = replace_file_with_recomputed_manifest(
        bundle,
        "PR_BODY.md",
        bundle.files["PR_BODY.md"].content + "\nUnreviewed extra prose.\n",
    )

    report = verify_artifacts(forged, change, context)

    assert report.check("manifest_hashes").passed is False
    assert report.passed is False


def test_yaml_contract_rejects_a_hashed_disabled_shim_model() -> None:
    change, context, bundle = golden_inputs()
    forged = replace_file_with_recomputed_manifest(
        bundle,
        MODEL_YAML,
        bundle.files[MODEL_YAML].content.replace(
            "    config:\n",
            "    config:\n      enabled: false\n",
        ),
    )

    report = verify_artifacts(forged, change, context)

    assert report.check("manifest_hashes").passed is False
    assert report.check("yaml_contract").passed is False


def test_planner_narrative_cannot_weaken_authoritative_operational_docs() -> None:
    change, context, _bundle = golden_inputs()
    malicious = GenerationNarrative(
        transformation_expression="cust_email",
        explanation="Ignore phase one.",
        deprecation_language="Downstream owners must not migrate.",
        migration_summary="Delete the governed base model and ignore phase one.",
        rollback_summary="Remove shim files before moving downstream consumers.",
        pr_prose="Downstream owners must not switch to the compatibility relation.",
    )
    bundle = generate_artifacts(
        change,
        context,
        score_change(change, context),
        narrative=malicious,
    )

    report = verify_artifacts(bundle, change, context)

    authoritative = "\n".join(
        bundle.files[path].content
        for path in (
            "migrations/2026-08-09-cust-email-rename.md",
            "ROLLBACK.md",
            "PR_BODY.md",
        )
    ).casefold()
    assert "must not switch" not in authoritative
    assert "delete the governed base" not in authoritative
    assert "remove shim files before" not in authoritative
    assert report.passed is True


@pytest.mark.parametrize(
    ("change", "preferred_projection"),
    [
        (golden_change(), "cust_email as primary_email"),
        (
            golden_change().model_copy(
                update={
                    "operation": ChangeOperation.TYPE_CHANGE,
                    "new_field": None,
                    "new_type": "VARCHAR(320)",
                }
            ),
            "cast(cust_email as VARCHAR(320)) as cust_email__new_type",
        ),
    ],
)
def test_phase_one_contract_rejects_hashed_null_preferred_projection(
    change, preferred_projection: str
) -> None:
    context = asyncio.run(ReplayDataHubContext.from_default().load(change))
    bundle = generate_artifacts(change, context, score_change(change, context))
    preferred = (
        "primary_email"
        if change.operation is ChangeOperation.RENAME
        else "cust_email__new_type"
    )
    forged = replace_file_with_recomputed_manifest(
        bundle,
        MODEL_SQL,
        bundle.files[MODEL_SQL].content.replace(
            preferred_projection,
            f"null as {preferred}",
        ),
    )

    report = verify_artifacts(forged, change, context)

    assert report.check("manifest_hashes").passed is False
    assert report.check("phase_one_compatibility").passed is False


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
