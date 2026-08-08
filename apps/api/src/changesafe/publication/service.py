"""Approval gates, previews, publication, and durable side-effect retries."""

from __future__ import annotations

import asyncio
import secrets
from datetime import UTC, datetime
from uuid import UUID

from changesafe.config import Mode, Settings
from changesafe.context.base import DataHubContextPort, DecisionWriteback
from changesafe.domain import (
    DataHubReceipt,
    PublicationLedgerEntry,
    PublicationReceipt,
    PublicError,
    RunState,
    RunView,
)
from changesafe.publication.base import GitHubPublisherPort, publication_key
from changesafe.publication.github import GitHubPublicationError, GitHubPublisher
from changesafe.publication.preview import build_unified_patch
from changesafe.store import RunStore


class ApprovalDenied(PermissionError):
    """Approval did not satisfy the configured owner gate."""


class PublicationStateError(ValueError):
    """The selected run is not eligible for approval."""


class PublicationFailure(RuntimeError):
    def __init__(self, code: str, message: str, *, retryable: bool = True) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.retryable = retryable


def _now() -> datetime:
    return datetime.now(UTC)


class PublicationService:
    def __init__(
        self,
        *,
        store: RunStore,
        settings: Settings,
        context_port: DataHubContextPort,
        github_publisher: GitHubPublisherPort | None = None,
    ) -> None:
        self.store = store
        self.settings = settings
        self.context_port = context_port
        self.github_publisher = github_publisher or self._configured_publisher()
        self._approval_lock = asyncio.Lock()

    def _configured_publisher(self) -> GitHubPublisherPort | None:
        if not self.settings.github_publication_enabled:
            return None
        assert self.settings.github_token is not None
        assert self.settings.github_repository is not None
        return GitHubPublisher(
            token=self.settings.github_token.get_secret_value(),
            repository=self.settings.github_repository,
            base_branch=self.settings.github_base_branch,
        )

    @property
    def _live_enabled(self) -> bool:
        return self.settings.mode is not Mode.REPLAY and (
            self.settings.github_publication_enabled
            or self.settings.datahub_writeback_enabled
        )

    def _authorize(self, supplied_admin_token: str | None, run: RunView) -> None:
        if not self._live_enabled:
            return
        configured = self.settings.changesafe_admin_token
        token_matches = (
            configured is not None
            and supplied_admin_token is not None
            and secrets.compare_digest(
                supplied_admin_token, configured.get_secret_value()
            )
        )
        if not token_matches:
            raise ApprovalDenied(
                "Owner authorization is required for live publication."
            )

        allowlist = [
            item.strip()
            for item in self.settings.demo_urn_allowlist.split(";")
            if item.strip()
        ]
        allowed = any(
            run.request.asset_urn == item
            or (item.endswith("*") and run.request.asset_urn.startswith(item[:-1]))
            for item in allowlist
        )
        if not allowed:
            raise ApprovalDenied(
                "The target asset is outside the publication allowlist."
            )

    async def approve(
        self, run_id: UUID | str, supplied_admin_token: str | None
    ) -> PublicationReceipt:
        async with self._approval_lock:
            run = await self.store.get(run_id)
            if run is None:
                raise KeyError(str(run_id))
            self._authorize(supplied_admin_token, run)
            if run.analysis is None or not run.analysis.publication_eligible:
                raise PublicationStateError(
                    "Run has no verified publication artifacts."
                )
            if run.state not in {
                RunState.AWAITING_APPROVAL,
                RunState.PUBLICATION_FAILED,
                RunState.COMPLETED,
            }:
                raise PublicationStateError(
                    f"Run cannot be approved from state {run.state.value}."
                )

            artifact_hash = run.analysis.artifacts.manifest_hash
            if artifact_hash is None:
                raise PublicationStateError("Verified artifact manifest is missing.")
            key = publication_key(run.request, run.request.source_commit, artifact_hash)
            existing = await self.store.get_publication(key)
            if existing is not None and existing.completed and existing.receipt:
                return await self._reuse_completed_receipt(run, existing.receipt)

            now = _now()
            entry = existing or PublicationLedgerEntry(
                idempotency_key=key,
                run_id=run.run_id,
                artifact_hash=artifact_hash,
                approved_at=now,
                created_at=now,
                updated_at=now,
            )
            entry = await self.store.save_publication(entry)
            patch = build_unified_patch(run.analysis.artifacts)
            if not self._live_enabled:
                return await self._approve_preview(run, entry, patch)
            return await self._approve_live(run, entry, patch)

    async def _reuse_completed_receipt(
        self,
        run: RunView,
        receipt: PublicationReceipt,
    ) -> PublicationReceipt:
        if run.state is RunState.COMPLETED and run.publication is not None:
            return run.publication

        transition = (
            RunState.PREPARING_PREVIEW
            if receipt.mode == "preview"
            else RunState.PUBLISHING
        )
        reused = receipt.model_copy(
            update={
                "writeback": receipt.writeback.model_copy(
                    update={"idempotent_reuse": True}
                )
            }
        )
        await self.store.transition(
            run.run_id,
            transition,
            public_message="Reusing completed publication receipt",
        )
        await self.store.transition(
            run.run_id,
            RunState.COMPLETED,
            public_message="Publication receipt reused",
            publication=reused,
        )
        return reused

    async def _approve_preview(
        self, run: RunView, entry: PublicationLedgerEntry, patch: str
    ) -> PublicationReceipt:
        if run.state is RunState.COMPLETED and run.publication is not None:
            return run.publication
        await self.store.transition(
            run.run_id,
            RunState.PREPARING_PREVIEW,
            public_message="Preparing credential-free publication preview",
        )
        writeback = DataHubReceipt(
            mode="preview",
            label="NOT WRITTEN — SNAPSHOT MODE",
            updated_urns=[run.request.asset_urn],
        )
        receipt = PublicationReceipt(
            mode="preview",
            idempotency_key=entry.idempotency_key,
            artifact_hash=entry.artifact_hash,
            patch=patch,
            writeback=writeback,
        )
        entry = entry.model_copy(
            update={"writeback": writeback, "receipt": receipt, "completed": True}
        )
        await self.store.save_publication(entry)
        await self.store.transition(
            run.run_id,
            RunState.COMPLETED,
            public_message="Publication preview ready",
            publication=receipt,
        )
        return receipt

    async def _approve_live(
        self, run: RunView, entry: PublicationLedgerEntry, patch: str
    ) -> PublicationReceipt:
        assert run.analysis is not None
        await self.store.transition(
            run.run_id,
            RunState.PUBLISHING,
            public_message="Publishing verified artifacts",
        )

        if self.settings.github_publication_enabled and entry.pull_request_url is None:
            if self.github_publisher is None:
                return await self._fail(
                    run,
                    entry,
                    patch,
                    code="GITHUB_NOT_CONFIGURED",
                    message="GitHub publication is unavailable.",
                    retryable=False,
                )
            try:
                github = await self.github_publisher.publish(
                    run_id=run.run_id,
                    change=run.request,
                    artifacts=run.analysis.artifacts,
                )
            except GitHubPublicationError as exc:
                return await self._fail(
                    run,
                    entry,
                    patch,
                    code=exc.code,
                    message="GitHub publication did not complete.",
                    retryable=exc.retryable,
                )
            except Exception:
                return await self._fail(
                    run,
                    entry,
                    patch,
                    code="GITHUB_PUBLICATION_FAILED",
                    message="GitHub publication did not complete.",
                )
            entry = entry.model_copy(
                update={
                    "branch": github.branch,
                    "pull_request_url": github.pull_request_url,
                }
            )
            entry = await self.store.save_publication(entry)

        if self.settings.datahub_writeback_enabled and entry.writeback is None:
            decision = DecisionWriteback(
                run_id=str(run.run_id),
                change=run.request,
                risk_score=run.analysis.risk.score,
                risk_band=run.analysis.risk.band,
                artifact_hash=entry.artifact_hash,
                approved_at=entry.approved_at,
                pull_request_url=entry.pull_request_url,
            )
            try:
                writeback = await self.context_port.writeback(decision)
            except Exception:
                return await self._fail(
                    run,
                    entry,
                    patch,
                    code="DATAHUB_WRITEBACK_FAILED",
                    message="DataHub writeback did not complete.",
                )
            entry = entry.model_copy(update={"writeback": writeback})
            entry = await self.store.save_publication(entry)

        writeback = entry.writeback or DataHubReceipt(
            mode="preview",
            label="NOT WRITTEN — WRITEBACK DISABLED",
            updated_urns=[run.request.asset_urn],
        )
        receipt = PublicationReceipt(
            mode="live",
            idempotency_key=entry.idempotency_key,
            artifact_hash=entry.artifact_hash,
            branch=entry.branch,
            pull_request_url=entry.pull_request_url,
            patch=patch,
            writeback=writeback,
        )
        entry = entry.model_copy(
            update={"writeback": writeback, "receipt": receipt, "completed": True}
        )
        await self.store.save_publication(entry)
        await self.store.transition(
            run.run_id,
            RunState.COMPLETED,
            public_message="Publication completed",
            publication=receipt,
        )
        return receipt

    async def _fail(
        self,
        run: RunView,
        entry: PublicationLedgerEntry,
        patch: str,
        *,
        code: str,
        message: str,
        retryable: bool = True,
    ) -> PublicationReceipt:
        pending = DataHubReceipt(
            mode="preview",
            label="WRITEBACK PENDING — RETRY REQUIRED",
            updated_urns=[run.request.asset_urn],
        )
        partial = PublicationReceipt(
            mode="live",
            idempotency_key=entry.idempotency_key,
            artifact_hash=entry.artifact_hash,
            branch=entry.branch,
            pull_request_url=entry.pull_request_url,
            patch=patch,
            writeback=entry.writeback or pending,
        )
        await self.store.save_publication(entry.model_copy(update={"receipt": partial}))
        await self.store.transition(
            run.run_id,
            RunState.PUBLICATION_FAILED,
            public_message="Publication requires retry",
            publication=partial,
            error=PublicError(code=code, message=message, retryable=retryable),
        )
        raise PublicationFailure(code, message, retryable=retryable)
