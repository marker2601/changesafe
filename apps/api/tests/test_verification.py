import asyncio

from changesafe.context.replay import ReplayDataHubContext
from changesafe.domain import (
    ArtifactBundle,
    ArtifactFile,
    ChangeOperation,
    ChangeRequest,
)
from changesafe.generation.templates import generate_artifacts
from changesafe.risk import score_change
from changesafe.verification import verify_artifacts

TARGET = "urn:li:dataset:(urn:li:dataPlatform:dbt,analytics.dim_customers,PROD)"
MODEL_SQL = "models/marts/dim_customers.sql"
MODEL_YAML = "models/marts/dim_customers.yml"


def golden_inputs():
    change = ChangeRequest(
        asset_urn=TARGET,
        operation=ChangeOperation.RENAME,
        field="customer_email",
        new_field="primary_email",
        old_type="STRING",
        new_type="STRING",
        source_commit="demo-unsafe-change",
        requested_by="demo-user",
    )
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
    assert len(report.checks) == 10
    assert all(check.passed for check in report.checks if check.blocking)


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
        "version: 2\nmodels:\n  - name: dim_customers\n    columns: []\n",
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
