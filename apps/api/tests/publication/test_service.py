from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from changesafe.config import Mode, Settings
from changesafe.demo import DEMO_TARGET_URN
from changesafe.domain import (
    ApprovalBlocker,
    ChangeOperation,
    WarehouseCheck,
    WarehouseValidationMode,
    WarehouseValidationResult,
    WarehouseValidationStatus,
)
from changesafe.publication.base import publication_key
from changesafe.publication.service import (
    PublicationService,
    PublicationStateError,
)
from changesafe.store import RunStore
from changesafe.warehouse.queries import fingerprint_relation

from .helpers import analyzed_run
from .test_idempotency import (
    ADMIN_TOKEN,
    CountingGitHubPublisher,
    FlakyWritebackContext,
    persist_analysis,
)

RELATION = "SAFE_DB.SAFE_SCHEMA.ORDER_DETAILS"


def warehouse_result(
    run,
    *,
    completed_at: datetime,
    relation: str = RELATION,
) -> WarehouseValidationResult:
    return WarehouseValidationResult(
        status=WarehouseValidationStatus.PASSED,
        mode=WarehouseValidationMode.AGGREGATE,
        environment_label="competition-non-production",
        operation=run.request.operation,
        field=run.request.field,
        relation_fingerprint=fingerprint_relation(relation),
        started_at=completed_at - timedelta(seconds=1),
        completed_at=completed_at,
        rows_evaluated=20,
        populated_row_count=20,
        query_ids=["safe-query-id"],
        elapsed_ms=1_000,
        checks=[
            WarehouseCheck(
                code="aggregate_validation",
                label="Aggregate validation",
                passed=True,
                detail="Aggregate checks passed.",
            )
        ],
    )


def live_warehouse_settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        mode=Mode.LIVE,
        changesafe_data_path=tmp_path / "runs.db",
        datahub_gms_url="https://datahub.example.test",
        datahub_gms_token="datahub-secret",
        github_token="github-secret",
        changesafe_github_repository="acme/analytics",
        public_writeback_enabled=True,
        public_pr_enabled=True,
        changesafe_admin_token=ADMIN_TOKEN,
        save_document_restrict_updates=False,
        warehouse_validation_enabled=True,
        warehouse_validation_required=True,
        snowflake_account="account-test",
        snowflake_user="user-test",
        snowflake_authenticator="SNOWFLAKE_JWT",
        snowflake_private_key_path=tmp_path / "test-key.p8",
        snowflake_warehouse="warehouse-test",
        snowflake_database="safe_db",
        snowflake_schema="safe_schema",
        snowflake_role="readonly-test",
        snowflake_target_relation_allowlist={DEMO_TARGET_URN: RELATION},
    )


@pytest.mark.asyncio
async def test_stale_passed_evidence_blocks_before_ledger_or_external_calls(
    tmp_path: Path,
) -> None:
    context = FlakyWritebackContext()
    store, _, run = await analyzed_run(tmp_path, context_port=context)
    assert run.analysis is not None
    settings = live_warehouse_settings(tmp_path)
    stale = datetime.now(UTC) - timedelta(
        seconds=settings.warehouse_evidence_max_age_seconds + 1
    )
    await persist_analysis(
        store,
        run.run_id,
        run.analysis.model_copy(
            update={
                "warehouse_validation": warehouse_result(
                    run, completed_at=stale
                ),
                "approval_blockers": [],
                "publication_eligible": True,
            }
        ),
    )
    publisher = CountingGitHubPublisher()
    service = PublicationService(
        store=store,
        settings=settings,
        context_port=context,
        github_publisher=publisher,
    )
    artifact_hash = run.analysis.artifacts.manifest_hash
    assert artifact_hash is not None
    key = publication_key(run.request, run.request.source_commit, artifact_hash)

    with pytest.raises(PublicationStateError, match="current safety policy"):
        await service.approve(run.run_id, supplied_admin_token=ADMIN_TOKEN)

    persisted = await store.get(run.run_id)
    assert persisted is not None
    assert persisted.state.value == "awaiting_approval"
    assert await store.get_publication(key) is None
    assert publisher.calls == 0
    assert context.calls == 0


@pytest.mark.asyncio
async def test_persisted_blocker_prevents_any_external_side_effect(
    tmp_path: Path,
) -> None:
    context = FlakyWritebackContext()
    store, _, run = await analyzed_run(tmp_path, context_port=context)
    assert run.analysis is not None
    blocked = run.analysis.model_copy(
        update={
            "approval_blockers": [
                ApprovalBlocker(
                    code="OPERATOR_HOLD",
                    message="The persisted analysis remains blocked.",
                )
            ],
            "publication_eligible": True,
        }
    )
    await persist_analysis(store, run.run_id, blocked)
    publisher = CountingGitHubPublisher()
    service = PublicationService(
        store=store,
        settings=live_warehouse_settings(tmp_path).model_copy(
            update={
                "warehouse_validation_enabled": False,
                "warehouse_validation_required": False,
            }
        ),
        context_port=context,
        github_publisher=publisher,
    )

    with pytest.raises(PublicationStateError, match="current safety policy"):
        await service.approve(run.run_id, supplied_admin_token=ADMIN_TOKEN)

    assert publisher.calls == 0
    assert context.calls == 0


@pytest.mark.asyncio
async def test_pre_upgrade_default_warehouse_evidence_cannot_publish(
    tmp_path: Path,
) -> None:
    store, context, run = await analyzed_run(tmp_path)
    assert run.analysis is not None
    legacy = run.analysis.model_copy(
        update={
            "warehouse_validation": WarehouseValidationResult(
                status=WarehouseValidationStatus.NOT_RUN,
                mode=WarehouseValidationMode.NONE,
                environment_label="not configured",
                operation="rename",
                field="unavailable",
            ),
            "approval_blockers": [],
            "publication_eligible": True,
        }
    )
    await persist_analysis(store, run.run_id, legacy)
    service = PublicationService(
        store=store,
        settings=Settings(
            _env_file=None,
            mode=Mode.REPLAY,
            changesafe_data_path=store.database,
        ),
        context_port=context,
    )

    with pytest.raises(PublicationStateError, match="current safety policy"):
        await service.approve(run.run_id, supplied_admin_token=None)


@pytest.mark.asyncio
async def test_completed_receipt_reuse_rechecks_warehouse_freshness(
    tmp_path: Path,
) -> None:
    store, context, run = await analyzed_run(tmp_path)
    assert run.analysis is not None
    settings = Settings(
        _env_file=None,
        mode=Mode.REPLAY,
        changesafe_data_path=store.database,
        snowflake_target_relation_allowlist={DEMO_TARGET_URN: RELATION},
    )
    fresh = warehouse_result(run, completed_at=datetime.now(UTC))
    await persist_analysis(
        store,
        run.run_id,
        run.analysis.model_copy(
            update={
                "warehouse_validation": fresh,
                "approval_blockers": [],
                "publication_eligible": True,
            }
        ),
    )
    service = PublicationService(
        store=store,
        settings=settings,
        context_port=context,
    )
    first = await service.approve(run.run_id, supplied_admin_token=None)
    stale = fresh.model_copy(
        update={
            "started_at": datetime.now(UTC)
            - timedelta(seconds=settings.warehouse_evidence_max_age_seconds + 2),
            "completed_at": datetime.now(UTC)
            - timedelta(seconds=settings.warehouse_evidence_max_age_seconds + 1),
        }
    )
    await persist_analysis(
        store,
        run.run_id,
        run.analysis.model_copy(
            update={
                "warehouse_validation": stale,
                "approval_blockers": [],
                "publication_eligible": True,
            }
        ),
    )

    with pytest.raises(PublicationStateError, match="current safety policy"):
        await service.approve(run.run_id, supplied_admin_token=None)

    persisted = await store.get(run.run_id)
    assert persisted is not None
    assert persisted.publication == first


def warehouse_boundary_result(run, boundary: str) -> WarehouseValidationResult:
    now = datetime.now(UTC)
    if boundary == "not_run":
        return WarehouseValidationResult(
            status=WarehouseValidationStatus.NOT_RUN,
            mode=WarehouseValidationMode.NONE,
            environment_label="competition-non-production",
            operation=run.request.operation,
            field=run.request.field,
        )
    if boundary in {"blocked_permanent", "blocked_retryable"}:
        retryable = boundary == "blocked_retryable"
        return WarehouseValidationResult(
            status=WarehouseValidationStatus.BLOCKED,
            mode=WarehouseValidationMode.AGGREGATE,
            environment_label="competition-non-production",
            operation=run.request.operation,
            field=run.request.field,
            relation_fingerprint=fingerprint_relation(RELATION),
            started_at=now - timedelta(seconds=1),
            completed_at=now,
            checks=[
                WarehouseCheck(
                    code=("warehouse_timeout" if retryable else "unsafe_conversion"),
                    label="Warehouse validation",
                    passed=False,
                    retryable=retryable,
                    detail="Warehouse evidence did not pass.",
                )
            ],
        )

    passed = warehouse_result(run, completed_at=now)
    if boundary == "wrong_relation":
        return passed.model_copy(
            update={"relation_fingerprint": fingerprint_relation("OTHER.DB.TABLE")}
        )
    if boundary == "wrong_field":
        return passed.model_copy(update={"field": "another_field"})
    if boundary == "wrong_operation":
        return passed.model_copy(update={"operation": ChangeOperation.REMOVE})
    if boundary == "stale":
        return passed.model_copy(
            update={
                "started_at": now - timedelta(days=2, seconds=1),
                "completed_at": now - timedelta(days=2),
            }
        )
    raise AssertionError(boundary)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "boundary",
    [
        "not_run",
        "blocked_permanent",
        "blocked_retryable",
        "wrong_relation",
        "wrong_field",
        "wrong_operation",
        "stale",
    ],
)
async def test_required_warehouse_failure_survives_duplicate_approval_and_restart(
    boundary: str,
    tmp_path: Path,
) -> None:
    context = FlakyWritebackContext()
    store, _, run = await analyzed_run(tmp_path, context_port=context)
    assert run.analysis is not None
    analysis = run.analysis.model_copy(
        update={
            "warehouse_validation": warehouse_boundary_result(run, boundary),
            "approval_blockers": [],
            "publication_eligible": True,
        }
    )
    await persist_analysis(store, run.run_id, analysis)
    publisher = CountingGitHubPublisher()
    artifact_hash = analysis.artifacts.manifest_hash
    assert artifact_hash is not None
    key = publication_key(run.request, run.request.source_commit, artifact_hash)

    for _ in range(2):
        reopened = RunStore(store.database)
        service = PublicationService(
            store=reopened,
            settings=live_warehouse_settings(tmp_path),
            context_port=context,
            github_publisher=publisher,
        )
        with pytest.raises(PublicationStateError, match="current safety policy"):
            await service.approve(run.run_id, supplied_admin_token=ADMIN_TOKEN)
        assert await reopened.get_publication(key) is None

    assert publisher.calls == 0
    assert context.calls == 0
