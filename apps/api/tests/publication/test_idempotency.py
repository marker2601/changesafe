from pathlib import Path

import pytest

from changesafe.config import Mode, Settings
from changesafe.context.base import DecisionWriteback
from changesafe.context.replay import ReplayDataHubContext
from changesafe.domain import DataHubReceipt, RunState
from changesafe.publication.base import GitHubResult
from changesafe.publication.service import (
    ApprovalDenied,
    PublicationFailure,
    PublicationService,
)
from changesafe.store import RunStore

from .helpers import analyzed_run

ADMIN_TOKEN = "owner-admin-secret"


class CountingGitHubPublisher:
    def __init__(self) -> None:
        self.calls = 0

    async def publish(self, **_kwargs: object) -> GitHubResult:
        self.calls += 1
        return GitHubResult(
            branch="changesafe/0198f000",
            pull_request_url="https://github.com/acme/analytics/pull/7",
        )


class FlakyWritebackContext(ReplayDataHubContext):
    def __init__(self) -> None:
        replay = ReplayDataHubContext.from_default()
        super().__init__(replay.snapshot_path, replay.checksum_path)
        self.calls = 0

    async def writeback(self, decision: DecisionWriteback) -> DataHubReceipt:
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("private upstream detail")
        return DataHubReceipt(
            mode="live",
            label="WRITTEN TO DATAHUB",
            document_urn=f"urn:li:document:changesafe-{decision.run_id}",
            updated_urns=[decision.change.asset_urn],
            mutations=["save_document", "add_tags"],
        )


def live_settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        mode=Mode.LIVE,
        changesafe_data_path=tmp_path / "runs.db",
        datahub_gms_url="https://datahub.example.test",
        datahub_gms_token="datahub-secret",
        github_token="github-secret",
        github_repository="acme/analytics",
        public_writeback_enabled=True,
        public_pr_enabled=True,
        changesafe_admin_token=ADMIN_TOKEN,
    )


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
