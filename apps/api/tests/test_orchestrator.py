import json
from pathlib import Path

import pytest

from changesafe.context.replay import ReplayDataHubContext
from changesafe.demo import golden_change
from changesafe.domain import ImpactCategory, RunState
from changesafe.generation.service import ArtifactGenerationService
from changesafe.orchestrator import ChangeSafeOrchestrator
from changesafe.store import RunStore


@pytest.mark.asyncio
async def test_golden_pipeline_reaches_awaiting_approval(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.db")
    await store.initialize()
    orchestrator = ChangeSafeOrchestrator(
        store=store,
        context_port=ReplayDataHubContext.from_default(),
        generator=ArtifactGenerationService(),
    )
    run = await store.create(golden_change())

    result = await orchestrator.analyze(run.run_id)

    assert result.state is RunState.AWAITING_APPROVAL
    assert result.analysis is not None
    assert result.analysis.risk.score == 85
    assert result.analysis.validation.passed is True
    assert len(result.analysis.artifacts.files) == 7
    assert [impact.category for impact in result.analysis.impacts] == list(
        ImpactCategory
    )
    assert [event.state for event in await store.events(run.run_id)] == [
        RunState.CREATED,
        RunState.LOADING_CONTEXT,
        RunState.SCORING_RISK,
        RunState.GENERATING,
        RunState.VALIDATING,
        RunState.AWAITING_APPROVAL,
    ]
    events = await store.events(run.run_id)
    assert [event.public_message for event in events[1:]] == [
        "Reading the existing data contract",
        "Classifying business and technical impact",
        "Preparing a compatible migration",
        "Proving the generated change is safe",
        "Waiting for the accountable owner",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "new_field", "expected_type"),
    [
        ("cust_email", "primary_email", "TEXT"),
        ("order_total", "preferred_order_total", "FLOAT"),
        ("order_status", "preferred_order_status", "NUMBER"),
    ],
)
async def test_replay_analysis_binds_each_selected_field_to_its_own_evidence(
    tmp_path: Path,
    field: str,
    new_field: str,
    expected_type: str,
) -> None:
    """A replay run must not fall back to the default email context."""
    store = RunStore(tmp_path / f"{field}.db")
    await store.initialize()
    orchestrator = ChangeSafeOrchestrator(
        store=store,
        context_port=ReplayDataHubContext.from_default(),
        generator=ArtifactGenerationService(),
    )
    change = golden_change().model_copy(
        update={
            "field": field,
            "new_field": new_field,
            "source_commit": f"multi-field-{field}",
        }
    )
    run = await store.create(change)

    result = await orchestrator.analyze(run.run_id)

    assert result.state is RunState.AWAITING_APPROVAL
    assert result.analysis is not None
    assert result.analysis.context.field == change.field
    assert result.analysis.context.field_type == expected_type
    assert result.analysis.publication_eligible is True
    assert result.analysis.validation.passed is True
    assert all(
        check.passed
        for check in result.analysis.validation.checks
        if check.blocking
    )
    model = result.analysis.artifacts.files[
        "models/marts/order_details__changesafe.sql"
    ].content
    assert change.field in model
    assert result.analysis.artifacts.manifest_hash is not None

    context = result.analysis.context
    saved_urns = {
        context.target_urn,
        *context.field_tags,
        *context.glossary_terms,
        *context.queries,
        *(item.urn for item in context.evidence),
        *(item.urn for item in context.upstream_assets),
        *(item.urn for item in context.downstream_assets),
    }
    for factor in result.analysis.risk.factors:
        assert set(factor.evidence_urns) <= saved_urns

    if field == "cust_email":
        return

    field_scoped = {
        "field_tags": context.field_tags,
        "glossary_terms": context.glossary_terms,
        "queries": context.queries,
        "evidence": [item.model_dump(mode="json") for item in context.evidence],
        "upstream_assets": [
            item.model_dump(mode="json") for item in context.upstream_assets
        ],
        "downstream_assets": [
            item.model_dump(mode="json") for item in context.downstream_assets
        ],
    }
    assert "cust_email" not in json.dumps(field_scoped).casefold()


@pytest.mark.asyncio
async def test_context_contract_failure_persists_safe_public_error(
    tmp_path: Path,
) -> None:
    store = RunStore(tmp_path / "runs.db")
    await store.initialize()
    orchestrator = ChangeSafeOrchestrator(
        store=store,
        context_port=ReplayDataHubContext.from_default(),
        generator=ArtifactGenerationService(),
    )
    incompatible = golden_change().model_copy(update={"field": "missing_field"})
    run = await store.create(incompatible)

    result = await orchestrator.analyze(run.run_id)

    assert result.state is RunState.FAILED
    assert result.error is not None
    assert result.error.code == "CONTEXT_LOAD_FAILED"
    assert "snapshot" not in result.error.message.lower()


@pytest.mark.asyncio
async def test_wait_for_idle_drains_background_analysis_before_shutdown(
    tmp_path: Path,
) -> None:
    store = RunStore(tmp_path / "runs.db")
    orchestrator = ChangeSafeOrchestrator(
        store=store,
        context_port=ReplayDataHubContext.from_default(),
        generator=ArtifactGenerationService(),
    )

    run = await orchestrator.start(golden_change())
    await orchestrator.wait_for_idle()

    completed = await store.get(run.run_id)
    assert completed is not None
    assert completed.state is RunState.AWAITING_APPROVAL
