import asyncio
from pathlib import Path

import pytest
from pydantic import ValidationError

from changesafe.context.replay import ReplayDataHubContext
from changesafe.domain import ChangeOperation, ChangeRequest
from changesafe.generation.templates import (
    EXPECTED_GOLDEN_PATHS,
    GenerationNarrative,
    generate_artifacts,
)
from changesafe.risk import score_change

TARGET = "urn:li:dataset:(urn:li:dataPlatform:dbt,analytics.dim_customers,PROD)"


def golden_change() -> ChangeRequest:
    return ChangeRequest(
        asset_urn=TARGET,
        operation=ChangeOperation.RENAME,
        field="customer_email",
        new_field="primary_email",
        old_type="STRING",
        new_type="STRING",
        source_commit="demo-unsafe-change",
        requested_by="demo-user",
    )


def test_golden_rename_generates_exact_manifest() -> None:
    change = golden_change()
    context = asyncio.run(ReplayDataHubContext.from_default().load(change))
    risk = score_change(change, context)

    bundle = generate_artifacts(change, context, risk)

    assert sorted(bundle.files) == sorted(EXPECTED_GOLDEN_PATHS)
    model = bundle.files["models/marts/dim_customers.sql"].content
    assert "customer_email" in model
    assert "customer_email as primary_email" in model.lower()
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
