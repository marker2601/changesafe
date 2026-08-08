from pathlib import Path
from typing import Any
from uuid import UUID

import aiosqlite
import pytest

from changesafe.config import Mode, Settings
from changesafe.context.base import (
    ContextAuthorizationError,
    ContextLoadError,
    ContextTimeoutError,
    DecisionWriteback,
)
from changesafe.context.live import LiveDataHubContext
from changesafe.context.replay import ReplayDataHubContext
from changesafe.domain import AnalysisResult, ContextMode, DataHubReceipt, RunState
from changesafe.publication.base import GitHubResult
from changesafe.publication.github import GitHubPublicationError
from changesafe.publication.service import (
    ApprovalDenied,
    PublicationFailure,
    PublicationService,
    PublicationStateError,
)
from changesafe.store import RunStore

from .helpers import analyzed_run

ADMIN_TOKEN = "owner-admin-secret"


async def persist_analysis(
    store: RunStore, run_id: UUID | str, analysis: AnalysisResult
) -> None:
    async with aiosqlite.connect(store.database) as connection:
        await connection.execute(
            "UPDATE runs SET analysis_json = ? WHERE run_id = ?",
            (analysis.model_dump_json(), str(run_id)),
        )
        await connection.commit()


class CountingGitHubPublisher:
    def __init__(self) -> None:
        self.calls = 0

    async def publish(self, **_kwargs: object) -> GitHubResult:
        self.calls += 1
        return GitHubResult(
            branch="changesafe/0198f000",
            pull_request_url="https://github.com/acme/analytics/pull/7",
        )

    async def ensure_branch(self, **_kwargs: object) -> str:
        self.calls += 1
        return "changesafe/0198f000"

    async def ensure_pull_request(self, **_kwargs: object) -> str:
        return "https://github.com/acme/analytics/pull/7"


class FlakyWritebackContext(ReplayDataHubContext):
    def __init__(self) -> None:
        replay = ReplayDataHubContext.from_default()
        super().__init__(replay.snapshot_path, replay.checksum_path)
        self.calls = 0

    async def load(self, change):
        context = await super().load(change)
        return context.model_copy(
            update={
                "provenance": context.provenance.model_copy(
                    update={"mode": ContextMode.LIVE, "snapshot_hash": None}
                )
            }
        )

    async def writeback(
        self,
        decision: DecisionWriteback,
        **_kwargs: object,
    ) -> DataHubReceipt:
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("private upstream detail")
        return DataHubReceipt(
            mode="live",
            label="WRITTEN TO DATAHUB",
            document_urn=f"urn:li:document:changesafe-{decision.run_id}",
            updated_urns=[decision.change.asset_urn],
            mutations=["save_document", "add_structured_properties", "add_tags"],
        )


class TypedFailureWritebackContext(FlakyWritebackContext):
    def __init__(self, failure: Exception) -> None:
        super().__init__()
        self.failure = failure

    async def writeback(
        self,
        decision: DecisionWriteback,
        **_kwargs: object,
    ) -> DataHubReceipt:
        del decision
        raise self.failure


def live_settings(tmp_path: Path) -> Settings:
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
    )


def writeback_only_live_settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        mode=Mode.LIVE,
        changesafe_data_path=tmp_path / "runs.db",
        datahub_gms_url="https://datahub.example.test",
        datahub_gms_token="datahub-secret",
        public_writeback_enabled=True,
        changesafe_admin_token=ADMIN_TOKEN,
    )


class BranchThenPullFailure:
    def __init__(self) -> None:
        self.branch_calls = 0
        self.pull_calls = 0

    async def ensure_branch(self, **_kwargs: object) -> str:
        self.branch_calls += 1
        return "changesafe/0198f000"

    async def ensure_pull_request(self, **_kwargs: object) -> str:
        self.pull_calls += 1
        if self.pull_calls == 1:
            raise GitHubPublicationError(
                "GITHUB_REQUEST_FAILED",
                "PR creation failed after branch creation",
                retryable=True,
            )
        return "https://github.com/acme/analytics/pull/7"

    async def publish(self, **_kwargs: object) -> GitHubResult:
        raise AssertionError("PublicationService must persist GitHub substeps")


class SimulatedProcessCrash(BaseException):
    pass


class CrashBeforeBranchPublisher:
    async def ensure_branch(self, **_kwargs: object) -> str:
        raise SimulatedProcessCrash()

    async def ensure_pull_request(self, **_kwargs: object) -> str:
        raise AssertionError("pull request must follow a persisted branch")

    async def publish(self, **_kwargs: object) -> GitHubResult:
        raise AssertionError("PublicationService must persist GitHub substeps")


class PartialDataHubRunner:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.property_attempts = 0

    async def call(self, tool: str, **parameters: Any) -> Any:
        self.calls.append((tool, parameters))
        if tool == "save_document":
            assert parameters["urn"].startswith("urn:li:document:changesafe-")
            assert "## Risk factors" in parameters["content"]
            assert "## Validation" in parameters["content"]
            assert "## Migration" in parameters["content"]
            assert "## Rollback" in parameters["content"]
            return {"success": True, "urn": parameters["urn"]}
        if tool == "add_structured_properties":
            self.property_attempts += 1
            if self.property_attempts == 1:
                raise RuntimeError("fail after document creation")
            return {"success": True}
        if tool == "add_tags":
            return {"success": True}
        raise AssertionError(tool)


@pytest.mark.asyncio
async def test_approval_rejects_artifacts_that_fail_the_current_verifier(
    tmp_path: Path,
) -> None:
    store, context, run = await analyzed_run(tmp_path)
    assert run.analysis is not None
    conflicting_field = run.analysis.context.schema_fields[0].model_copy(
        update={"name": "primary_email"}
    )
    stale_context = run.analysis.context.model_copy(
        update={
            "schema_fields": [
                *run.analysis.context.schema_fields,
                conflicting_field,
            ]
        }
    )
    stale_validation = run.analysis.validation.model_copy(
        update={
            "checks": [
                check
                for check in run.analysis.validation.checks
                if check.code
                not in {"request_context_alignment", "unique_output_names"}
            ]
        }
    )
    stale_analysis = run.analysis.model_copy(
        update={
            "context": stale_context,
            "validation": stale_validation,
            "publication_eligible": True,
        }
    )
    await persist_analysis(store, run.run_id, stale_analysis)
    service = PublicationService(
        store=RunStore(store.database),
        settings=Settings(
            _env_file=None,
            mode=Mode.REPLAY,
            changesafe_data_path=store.database,
        ),
        context_port=context,
    )

    with pytest.raises(PublicationStateError, match="current safety policy"):
        await service.approve(run.run_id, supplied_admin_token=None)

    persisted = await service.store.get(run.run_id)
    assert persisted is not None
    assert persisted.state is RunState.AWAITING_APPROVAL


@pytest.mark.asyncio
async def test_approval_rejects_a_stale_deterministic_risk_result(
    tmp_path: Path,
) -> None:
    store, context, run = await analyzed_run(tmp_path)
    assert run.analysis is not None
    stale_analysis = run.analysis.model_copy(
        update={"risk": run.analysis.risk.model_copy(update={"score": 89})}
    )
    await persist_analysis(store, run.run_id, stale_analysis)
    service = PublicationService(
        store=RunStore(store.database),
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
async def test_partial_writeback_retry_does_not_duplicate_github_side_effect(
    tmp_path: Path,
) -> None:
    context = FlakyWritebackContext()
    store, _, run = await analyzed_run(tmp_path, context_port=context)
    publisher = CountingGitHubPublisher()
    service = PublicationService(
        store=store,
        settings=live_settings(tmp_path),
        context_port=context,
        github_publisher=publisher,
    )

    with pytest.raises(PublicationFailure) as captured:
        await service.approve(run.run_id, supplied_admin_token=ADMIN_TOKEN)

    partial = await store.get(run.run_id)
    assert captured.value.code == "DATAHUB_WRITEBACK_FAILED"
    assert "private upstream detail" not in str(captured.value)
    assert partial is not None
    assert partial.state is RunState.PUBLICATION_FAILED
    assert partial.publication is not None
    assert partial.publication.pull_request_url is not None

    reopened = RunStore(tmp_path / "runs.db")
    retry_service = PublicationService(
        store=reopened,
        settings=live_settings(tmp_path),
        context_port=context,
        github_publisher=publisher,
    )
    receipt = await retry_service.approve(
        run.run_id, supplied_admin_token=ADMIN_TOKEN
    )
    duplicate = await retry_service.approve(
        run.run_id, supplied_admin_token=ADMIN_TOKEN
    )
    completed = await reopened.get(run.run_id)

    assert publisher.calls == 1
    assert context.calls == 2
    assert duplicate == receipt
    assert completed is not None
    assert completed.state is RunState.COMPLETED
    assert completed.error is None


@pytest.mark.asyncio
async def test_incomplete_publication_cannot_be_resumed_by_another_run(
    tmp_path: Path,
) -> None:
    context = FlakyWritebackContext()
    store, _, first_run = await analyzed_run(tmp_path, context_port=context)
    publisher = CountingGitHubPublisher()
    service = PublicationService(
        store=store,
        settings=live_settings(tmp_path),
        context_port=context,
        github_publisher=publisher,
    )
    with pytest.raises(PublicationFailure):
        await service.approve(first_run.run_id, supplied_admin_token=ADMIN_TOKEN)

    second_store, _, second_run = await analyzed_run(
        tmp_path, context_port=context
    )
    restarted = PublicationService(
        store=second_store,
        settings=live_settings(tmp_path),
        context_port=context,
        github_publisher=publisher,
    )

    with pytest.raises(PublicationStateError, match="original run"):
        await restarted.approve(
            second_run.run_id, supplied_admin_token=ADMIN_TOKEN
        )

    assert context.calls == 1
    assert publisher.calls == 1


@pytest.mark.asyncio
async def test_partial_live_publication_cannot_downgrade_to_preview_after_restart(
    tmp_path: Path,
) -> None:
    context = FlakyWritebackContext()
    store, _, run = await analyzed_run(tmp_path, context_port=context)
    publisher = CountingGitHubPublisher()
    service = PublicationService(
        store=store,
        settings=live_settings(tmp_path),
        context_port=context,
        github_publisher=publisher,
    )

    with pytest.raises(PublicationFailure):
        await service.approve(run.run_id, supplied_admin_token=ADMIN_TOKEN)

    disabled = Settings(
        _env_file=None,
        mode=Mode.LIVE,
        changesafe_data_path=tmp_path / "runs.db",
        datahub_gms_url="https://datahub.example.test",
        datahub_gms_token="datahub-secret",
        changesafe_admin_token=ADMIN_TOKEN,
    )
    restarted = PublicationService(
        store=RunStore(tmp_path / "runs.db"),
        settings=disabled,
        context_port=context,
        github_publisher=publisher,
    )

    with pytest.raises(PublicationFailure) as captured:
        await restarted.approve(run.run_id, supplied_admin_token=ADMIN_TOKEN)

    persisted = await restarted.store.get(run.run_id)
    assert captured.value.code == "DATAHUB_NOT_CONFIGURED"
    assert captured.value.retryable is False
    assert persisted is not None
    assert persisted.state is RunState.PUBLICATION_FAILED
    assert persisted.publication is not None
    assert persisted.publication.mode == "live"
    ledger = await restarted.store.get_publication(
        persisted.publication.idempotency_key
    )
    assert ledger is not None
    assert ledger.publication_mode == "live"
    assert ledger.github_required is True
    assert ledger.datahub_required is True


@pytest.mark.asyncio
async def test_live_publication_resumes_from_publishing_after_process_crash(
    tmp_path: Path,
) -> None:
    context = FlakyWritebackContext()
    store, _, run = await analyzed_run(tmp_path, context_port=context)
    github_only = live_settings(tmp_path).model_copy(
        update={"public_writeback_enabled": False}
    )
    crashing = PublicationService(
        store=store,
        settings=github_only,
        context_port=context,
        github_publisher=CrashBeforeBranchPublisher(),
    )

    with pytest.raises(SimulatedProcessCrash):
        await crashing.approve(run.run_id, supplied_admin_token=ADMIN_TOKEN)

    interrupted = await store.get(run.run_id)
    assert interrupted is not None
    assert interrupted.state is RunState.PUBLISHING

    publisher = CountingGitHubPublisher()
    restarted = PublicationService(
        store=RunStore(tmp_path / "runs.db"),
        settings=github_only,
        context_port=context,
        github_publisher=publisher,
    )
    receipt = await restarted.approve(run.run_id, supplied_admin_token=ADMIN_TOKEN)

    assert receipt.mode == "live"
    assert receipt.pull_request_url == "https://github.com/acme/analytics/pull/7"
    assert publisher.calls == 1


@pytest.mark.asyncio
async def test_live_publication_rejects_github_destination_drift_after_crash(
    tmp_path: Path,
) -> None:
    context = FlakyWritebackContext()
    store, _, run = await analyzed_run(tmp_path, context_port=context)
    original = live_settings(tmp_path).model_copy(
        update={"public_writeback_enabled": False}
    )
    crashing = PublicationService(
        store=store,
        settings=original,
        context_port=context,
        github_publisher=CrashBeforeBranchPublisher(),
    )

    with pytest.raises(SimulatedProcessCrash):
        await crashing.approve(run.run_id, supplied_admin_token=ADMIN_TOKEN)

    changed = original.model_copy(
        update={"changesafe_github_repository": "acme/other-repo"}
    )
    publisher = CountingGitHubPublisher()
    restarted = PublicationService(
        store=RunStore(tmp_path / "runs.db"),
        settings=changed,
        context_port=context,
        github_publisher=publisher,
    )

    with pytest.raises(PublicationFailure) as captured:
        await restarted.approve(run.run_id, supplied_admin_token=ADMIN_TOKEN)

    assert captured.value.code == "PUBLICATION_DESTINATION_MISMATCH"
    assert captured.value.retryable is False
    assert publisher.calls == 0


@pytest.mark.asyncio
async def test_live_publication_rejects_datahub_destination_drift_after_failure(
    tmp_path: Path,
) -> None:
    context = FlakyWritebackContext()
    store, _, run = await analyzed_run(tmp_path, context_port=context)
    settings = writeback_only_live_settings(tmp_path)
    service = PublicationService(
        store=store,
        settings=settings,
        context_port=context,
    )

    with pytest.raises(PublicationFailure):
        await service.approve(run.run_id, supplied_admin_token=ADMIN_TOKEN)

    changed = settings.model_copy(
        update={"datahub_gms_url": "https://other-datahub.example.test"}
    )
    restarted = PublicationService(
        store=RunStore(tmp_path / "runs.db"),
        settings=changed,
        context_port=context,
    )

    with pytest.raises(PublicationFailure) as captured:
        await restarted.approve(run.run_id, supplied_admin_token=ADMIN_TOKEN)

    assert captured.value.code == "PUBLICATION_DESTINATION_MISMATCH"
    assert captured.value.retryable is False
    assert context.calls == 1


@pytest.mark.asyncio
async def test_preview_resumes_from_preparing_after_process_crash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = Settings(
        _env_file=None,
        mode=Mode.REPLAY,
        changesafe_data_path=tmp_path / "runs.db",
    )
    store, context, run = await analyzed_run(tmp_path)
    service = PublicationService(
        store=store,
        settings=settings,
        context_port=context,
    )
    real_save = store.save_publication
    crashed = False

    async def crash_before_completed_ledger(entry):
        nonlocal crashed
        if entry.completed and not crashed:
            crashed = True
            raise SimulatedProcessCrash()
        return await real_save(entry)

    monkeypatch.setattr(store, "save_publication", crash_before_completed_ledger)
    with pytest.raises(SimulatedProcessCrash):
        await service.approve(run.run_id, supplied_admin_token=None)

    interrupted = await store.get(run.run_id)
    assert interrupted is not None
    assert interrupted.state is RunState.PREPARING_PREVIEW

    restarted = PublicationService(
        store=RunStore(tmp_path / "runs.db"),
        settings=settings,
        context_port=context,
    )
    receipt = await restarted.approve(run.run_id, supplied_admin_token=None)

    assert receipt.mode == "preview"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("failure", "expected_code", "retryable"),
    [
        (
            ContextAuthorizationError("private authorization detail"),
            "DATAHUB_AUTHORIZATION_FAILED",
            False,
        ),
        (
            ContextLoadError("malformed acknowledgement"),
            "DATAHUB_WRITEBACK_REJECTED",
            False,
        ),
        (
            ContextTimeoutError("private timeout detail"),
            "DATAHUB_WRITEBACK_FAILED",
            True,
        ),
    ],
)
async def test_datahub_writeback_failure_retryability_is_typed(
    tmp_path: Path,
    failure: Exception,
    expected_code: str,
    retryable: bool,
) -> None:
    context = TypedFailureWritebackContext(failure)
    store, _, run = await analyzed_run(tmp_path, context_port=context)
    service = PublicationService(
        store=store,
        settings=writeback_only_live_settings(tmp_path),
        context_port=context,
    )

    with pytest.raises(PublicationFailure) as captured:
        await service.approve(run.run_id, ADMIN_TOKEN)

    assert captured.value.code == expected_code
    assert captured.value.retryable is retryable


@pytest.mark.asyncio
async def test_live_publication_requires_matching_admin_token(tmp_path: Path) -> None:
    context = FlakyWritebackContext()
    store, _, run = await analyzed_run(tmp_path, context_port=context)
    publisher = CountingGitHubPublisher()
    service = PublicationService(
        store=store,
        settings=live_settings(tmp_path),
        context_port=context,
        github_publisher=publisher,
    )

    with pytest.raises(ApprovalDenied):
        await service.approve(run.run_id, supplied_admin_token="wrong-token")

    persisted = await store.get(run.run_id)
    assert persisted is not None
    assert persisted.state is RunState.AWAITING_APPROVAL
    assert publisher.calls == 0
    assert context.calls == 0


@pytest.mark.asyncio
async def test_completed_ledger_reuse_completes_a_new_identical_run(
    tmp_path: Path,
) -> None:
    settings = Settings(
        _env_file=None,
        mode=Mode.REPLAY,
        changesafe_data_path=tmp_path / "runs.db",
    )
    first_store, context, first_run = await analyzed_run(tmp_path)
    first_service = PublicationService(
        store=first_store,
        settings=settings,
        context_port=context,
    )
    first_receipt = await first_service.approve(
        first_run.run_id, supplied_admin_token=None
    )

    second_store, _, second_run = await analyzed_run(
        tmp_path, context_port=context
    )
    second_service = PublicationService(
        store=second_store,
        settings=settings,
        context_port=context,
    )

    reused = await second_service.approve(
        second_run.run_id, supplied_admin_token=None
    )
    persisted = await second_store.get(second_run.run_id)

    assert reused.idempotency_key == first_receipt.idempotency_key
    assert reused.writeback.idempotent_reuse is True
    assert persisted is not None
    assert persisted.state is RunState.COMPLETED
    assert persisted.publication == reused


@pytest.mark.asyncio
async def test_completed_live_receipt_is_not_reused_for_another_repository(
    tmp_path: Path,
) -> None:
    context = FlakyWritebackContext()
    settings = live_settings(tmp_path).model_copy(
        update={"public_writeback_enabled": False}
    )
    first_store, _, first_run = await analyzed_run(tmp_path, context_port=context)
    first_publisher = CountingGitHubPublisher()
    first_service = PublicationService(
        store=first_store,
        settings=settings,
        context_port=context,
        github_publisher=first_publisher,
    )
    await first_service.approve(first_run.run_id, ADMIN_TOKEN)

    second_store, _, second_run = await analyzed_run(
        tmp_path, context_port=context
    )
    changed = settings.model_copy(
        update={"changesafe_github_repository": "acme/other-repo"}
    )
    second_publisher = CountingGitHubPublisher()
    second_service = PublicationService(
        store=second_store,
        settings=changed,
        context_port=context,
        github_publisher=second_publisher,
    )

    with pytest.raises(PublicationStateError, match="different publication intent"):
        await second_service.approve(second_run.run_id, ADMIN_TOKEN)

    assert second_publisher.calls == 0


@pytest.mark.asyncio
async def test_github_branch_is_persisted_before_pull_request_retry(
    tmp_path: Path,
) -> None:
    context = FlakyWritebackContext()
    store, _, run = await analyzed_run(tmp_path, context_port=context)
    publisher = BranchThenPullFailure()
    settings = live_settings(tmp_path).model_copy(
        update={"public_writeback_enabled": False}
    )
    service = PublicationService(
        store=store,
        settings=settings,
        context_port=context,
        github_publisher=publisher,
    )

    with pytest.raises(PublicationFailure):
        await service.approve(run.run_id, ADMIN_TOKEN)

    receipt = await service.approve(run.run_id, ADMIN_TOKEN)

    assert publisher.branch_calls == 1
    assert publisher.pull_calls == 2
    assert receipt.branch == "changesafe/0198f000"
    assert receipt.pull_request_url == "https://github.com/acme/analytics/pull/7"


@pytest.mark.asyncio
async def test_datahub_substeps_resume_without_duplicate_document_creation(
    tmp_path: Path,
) -> None:
    analysis_context = FlakyWritebackContext()
    store, _, run = await analyzed_run(tmp_path, context_port=analysis_context)
    runner = PartialDataHubRunner()
    writeback_context = LiveDataHubContext(
        runner=runner, allowlist={run.request.asset_urn}, retry_count=0
    )
    service = PublicationService(
        store=store,
        settings=writeback_only_live_settings(tmp_path),
        context_port=writeback_context,
    )

    with pytest.raises(PublicationFailure):
        await service.approve(run.run_id, ADMIN_TOKEN)

    receipt = await service.approve(run.run_id, ADMIN_TOKEN)
    tool_names = [name for name, _ in runner.calls]

    assert tool_names.count("save_document") == 1
    assert tool_names.count("add_structured_properties") == 2
    assert tool_names.count("add_tags") == 1
    assert receipt.writeback.mutations == [
        "save_document",
        "add_structured_properties",
        "add_tags",
    ]


@pytest.mark.asyncio
async def test_auto_mode_snapshot_run_cannot_publish_to_github(tmp_path: Path) -> None:
    context = ReplayDataHubContext.from_default()
    store, _, run = await analyzed_run(tmp_path, context_port=context)
    publisher = CountingGitHubPublisher()
    settings = Settings(
        _env_file=None,
        mode=Mode.AUTO,
        changesafe_data_path=tmp_path / "runs.db",
        github_token="github-secret",
        changesafe_github_repository="acme/analytics",
        public_pr_enabled=True,
        changesafe_admin_token=ADMIN_TOKEN,
    )
    service = PublicationService(
        store=store,
        settings=settings,
        context_port=context,
        github_publisher=publisher,
    )

    assert run.analysis is not None
    assert run.analysis.context.provenance.mode is ContextMode.SNAPSHOT
    receipt = await service.approve(run.run_id, supplied_admin_token=None)

    assert receipt.mode == "preview"
    assert receipt.writeback.label == "NOT WRITTEN — SNAPSHOT MODE"
    assert publisher.calls == 0


@pytest.mark.asyncio
async def test_completed_ledger_recovers_run_after_transition_crash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = Settings(
        _env_file=None,
        mode=Mode.REPLAY,
        changesafe_data_path=tmp_path / "runs.db",
    )
    store, context, run = await analyzed_run(tmp_path)
    service = PublicationService(
        store=store,
        settings=settings,
        context_port=context,
    )
    real_transition = store.transition

    async def crash_before_completed(
        run_id: object, state: RunState, **kwargs: object
    ) -> object:
        if state is RunState.COMPLETED:
            raise RuntimeError("simulated process crash")
        return await real_transition(run_id, state, **kwargs)

    monkeypatch.setattr(store, "transition", crash_before_completed)
    with pytest.raises(RuntimeError, match="simulated process crash"):
        await service.approve(run.run_id, supplied_admin_token=None)

    persisted = await store.get(run.run_id)
    assert persisted is not None
    assert persisted.state is RunState.PREPARING_PREVIEW

    reopened = PublicationService(
        store=RunStore(tmp_path / "runs.db"),
        settings=settings,
        context_port=context,
    )
    receipt = await reopened.approve(run.run_id, supplied_admin_token=None)
    recovered = await reopened.store.get(run.run_id)

    assert receipt.mode == "preview"
    assert recovered is not None
    assert recovered.state is RunState.COMPLETED
