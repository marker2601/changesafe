"""Approval gates, previews, publication, and durable side-effect retries."""

from __future__ import annotations

import asyncio
import secrets
from datetime import UTC, datetime
from uuid import UUID

from changesafe.config import Settings
from changesafe.context.base import (
    ContextAuthorizationError,
    ContextLoadError,
    ContextTimeoutError,
    ContextTransportError,
    DataHubContextPort,
    DecisionWriteback,
)
from changesafe.domain import (
    DataHubReceipt,
    PublicationLedgerEntry,
    PublicationReceipt,
    PublicError,
    RunState,
    RunView,
)
from changesafe.impact import classify_impacts
from changesafe.policy import evaluate_approval_policy
from changesafe.publication.base import GitHubPublisherPort, publication_key
from changesafe.publication.github import GitHubPublicationError, GitHubPublisher
from changesafe.publication.preview import build_unified_patch
from changesafe.risk import score_change
from changesafe.store import RunStore
from changesafe.verification import verify_artifacts
from changesafe.warehouse.queries import fingerprint_relation


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
        assert self.settings.changesafe_github_repository is not None
        return GitHubPublisher(
            token=self.settings.github_token.get_secret_value(),
            repository=self.settings.changesafe_github_repository,
            base_branch=self.settings.github_base_branch,
        )

    def _require_current_policy(self, run: RunView) -> None:
        assert run.analysis is not None
        try:
            current_risk = score_change(run.request, run.analysis.context)
            current_impacts = classify_impacts(
                run.request, run.analysis.context
            )
            current_validation = verify_artifacts(
                run.analysis.artifacts,
                run.request,
                run.analysis.context,
            )
            relation = self.settings.warehouse_target_map.get(run.request.asset_urn)
            expected_relation_fingerprint = (
                fingerprint_relation(relation) if relation is not None else None
            )
            current_blockers = evaluate_approval_policy(
                change=run.request,
                context=run.analysis.context,
                validation=current_validation,
                warehouse=run.analysis.warehouse_validation,
                require_live_evidence=self.settings.live_evidence_required,
                require_warehouse=self.settings.warehouse_validation_required,
                warehouse_max_age_seconds=(
                    self.settings.warehouse_evidence_max_age_seconds
                ),
                expected_relation_fingerprint=expected_relation_fingerprint,
                now=_now(),
            )
        except Exception as exc:
            raise PublicationStateError(
                "Run does not satisfy the current safety policy; submit a new analysis."
            ) from exc
        if (
            not current_validation.passed
            or current_risk != run.analysis.risk
            or current_impacts != run.analysis.impacts
            or current_validation != run.analysis.validation
            or current_blockers != run.analysis.approval_blockers
            or bool(current_blockers)
            or not run.analysis.publication_eligible
        ):
            raise PublicationStateError(
                "Run does not satisfy the current safety policy; submit a new analysis."
            )

    @property
    def _external_publication_configured(self) -> bool:
        return (
            self.settings.github_publication_enabled
            or self.settings.datahub_writeback_enabled
        )

    def _configured_intent(self, run: RunView) -> dict[str, object]:
        live = bool(
            run.analysis is not None
            and run.analysis.context.provenance.mode.value == "live"
            and self._external_publication_configured
        )
        github_required = live and self.settings.github_publication_enabled
        datahub_required = live and self.settings.datahub_writeback_enabled
        return {
            "publication_mode": "live" if live else "preview",
            "github_required": github_required,
            "datahub_required": datahub_required,
            "github_repository": (
                self.settings.changesafe_github_repository
                if github_required
                else None
            ),
            "github_base_branch": (
                self.settings.github_base_branch if github_required else None
            ),
            "datahub_server": (
                str(self.settings.datahub_gms_url).rstrip("/")
                if datahub_required and self.settings.datahub_gms_url is not None
                else None
            ),
            "datahub_target_urn": run.request.asset_urn if datahub_required else None,
        }

    def _bind_intent(
        self, run: RunView, entry: PublicationLedgerEntry
    ) -> PublicationLedgerEntry:
        if entry.publication_mode is not None:
            return entry
        if entry.receipt is not None:
            receipt = entry.receipt
            return entry.model_copy(
                update={
                    **self._configured_intent(run),
                    "publication_mode": receipt.mode,
                    "github_required": bool(
                        entry.branch or entry.pull_request_url
                    ),
                    "datahub_required": receipt.writeback.mode == "live",
                }
            )
        has_side_effect_checkpoint = bool(
            entry.branch or entry.pull_request_url or entry.writeback
        )
        if has_side_effect_checkpoint or run.state is not RunState.AWAITING_APPROVAL:
            raise PublicationStateError(
                "Publication ledger is missing its durable publication intent."
            )
        return entry.model_copy(update=self._configured_intent(run))

    def _destination_mismatch(
        self, run: RunView, entry: PublicationLedgerEntry
    ) -> bool:
        if entry.github_required and entry.pull_request_url is None and (
            entry.github_repository != self.settings.changesafe_github_repository
            or entry.github_base_branch != self.settings.github_base_branch
        ):
            return True
        configured_datahub = (
            str(self.settings.datahub_gms_url).rstrip("/")
            if self.settings.datahub_gms_url is not None
            else None
        )
        return bool(
            entry.datahub_required
            and (
                entry.writeback is None
                or entry.writeback.label != "WRITTEN TO DATAHUB"
            )
            and (
                entry.datahub_server != configured_datahub
                or entry.datahub_target_urn != run.request.asset_urn
            )
        )

    def _intent_matches_current_configuration(
        self, run: RunView, entry: PublicationLedgerEntry
    ) -> bool:
        configured = self._configured_intent(run)
        return all(
            getattr(entry, field) == value
            for field, value in configured.items()
        )

    def _authorize(
        self,
        supplied_admin_token: str | None,
        run: RunView,
        *,
        live_required: bool,
    ) -> None:
        if not live_required:
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
            if run.analysis is None:
                raise PublicationStateError(
                    "Run has no verified publication artifacts."
                )
            self._require_current_policy(run)
            artifact_hash = run.analysis.artifacts.manifest_hash
            if artifact_hash is None:
                raise PublicationStateError("Verified artifact manifest is missing.")
            key = publication_key(run.request, run.request.source_commit, artifact_hash)
            existing = await self.store.get_publication(key)

            if run.state not in {
                RunState.AWAITING_APPROVAL,
                RunState.PUBLICATION_FAILED,
                RunState.PREPARING_PREVIEW,
                RunState.PUBLISHING,
                RunState.COMPLETED,
            }:
                raise PublicationStateError(
                    f"Run cannot be approved from state {run.state.value}."
                )

            now = _now()
            entry = existing
            if (
                entry is not None
                and not entry.completed
                and entry.run_id != run.run_id
            ):
                raise PublicationStateError(
                    "Incomplete publication must be resumed from its original run."
                )
            if entry is None:
                entry = PublicationLedgerEntry(
                    idempotency_key=key,
                    run_id=run.run_id,
                    artifact_hash=artifact_hash,
                    approved_at=now,
                    created_at=now,
                    updated_at=now,
                ).model_copy(update=self._configured_intent(run))
            entry = self._bind_intent(run, entry)
            if (
                run.state is RunState.PUBLISHING
                and entry.publication_mode != "live"
            ) or (
                run.state is RunState.PREPARING_PREVIEW
                and entry.publication_mode != "preview"
            ):
                raise PublicationStateError(
                    "Run state conflicts with persisted publication intent."
                )
            self._authorize(
                supplied_admin_token,
                run,
                live_required=entry.publication_mode == "live",
            )
            if existing is not None and existing.completed and existing.receipt:
                if (
                    entry.run_id != run.run_id
                    and not self._intent_matches_current_configuration(run, entry)
                ):
                    raise PublicationStateError(
                        "Completed receipt is bound to a different publication intent."
                    )
                return await self._reuse_completed_receipt(run, existing.receipt)
            entry = await self.store.save_publication(entry)
            patch = build_unified_patch(run.analysis.artifacts)
            if entry.publication_mode == "preview":
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
        if run.state not in {RunState.PREPARING_PREVIEW, RunState.PUBLISHING}:
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
        if run.state is not RunState.PREPARING_PREVIEW:
            await self.store.transition(
                run.run_id,
                RunState.PREPARING_PREVIEW,
                public_message="Preparing credential-free publication preview",
                clear_error=run.state is RunState.PUBLICATION_FAILED,
            )
        assert run.analysis is not None
        snapshot = run.analysis.context.provenance.mode.value == "snapshot"
        writeback = DataHubReceipt(
            mode="preview",
            label=(
                "NOT WRITTEN — SNAPSHOT MODE"
                if snapshot
                else "NOT WRITTEN — PUBLICATION DISABLED"
            ),
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
        if run.state is not RunState.PUBLISHING:
            await self.store.transition(
                run.run_id,
                RunState.PUBLISHING,
                public_message="Publishing the approved change and evidence",
                clear_error=run.state is RunState.PUBLICATION_FAILED,
            )

        if self._destination_mismatch(run, entry):
            return await self._fail(
                run,
                entry,
                patch,
                code="PUBLICATION_DESTINATION_MISMATCH",
                message=(
                    "The configured publication destination changed after approval."
                ),
                retryable=False,
            )

        if entry.github_required and entry.pull_request_url is None:
            if (
                not self.settings.github_publication_enabled
                or self.github_publisher is None
            ):
                return await self._fail(
                    run,
                    entry,
                    patch,
                    code="GITHUB_NOT_CONFIGURED",
                    message="GitHub publication is unavailable.",
                    retryable=False,
                )
            try:
                if entry.branch is None:
                    branch = await self.github_publisher.ensure_branch(
                        run_id=run.run_id,
                        change=run.request,
                        artifacts=run.analysis.artifacts,
                    )
                    entry = await self.store.save_publication(
                        entry.model_copy(update={"branch": branch})
                    )
                assert entry.branch is not None
                pull_request_url = await self.github_publisher.ensure_pull_request(
                    branch=entry.branch,
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
            entry = entry.model_copy(update={"pull_request_url": pull_request_url})
            entry = await self.store.save_publication(entry)

        if entry.datahub_required and (
            entry.writeback is None
            or entry.writeback.label != "WRITTEN TO DATAHUB"
        ):
            if not self.settings.datahub_writeback_enabled:
                return await self._fail(
                    run,
                    entry,
                    patch,
                    code="DATAHUB_NOT_CONFIGURED",
                    message="DataHub writeback is unavailable.",
                    retryable=False,
                )
            decision = DecisionWriteback(
                run_id=str(run.run_id),
                change=run.request,
                risk_score=run.analysis.risk.score,
                risk_band=run.analysis.risk.band,
                artifact_hash=entry.artifact_hash,
                approved_at=entry.approved_at,
                pull_request_url=entry.pull_request_url,
                idempotency_key=entry.idempotency_key,
                risk_factors=run.analysis.risk.factors,
                evidence=run.analysis.context.evidence,
                validation_checks=run.analysis.validation.checks,
                migration_summary=next(
                    artifact.content
                    for path, artifact in run.analysis.artifacts.files.items()
                    if path.startswith("migrations/")
                ),
                rollback_summary=run.analysis.artifacts.files[
                    "ROLLBACK.md"
                ].content,
            )

            async def persist_writeback(progress: DataHubReceipt) -> None:
                nonlocal entry
                entry = await self.store.save_publication(
                    entry.model_copy(update={"writeback": progress})
                )

            try:
                writeback = await self.context_port.writeback(
                    decision,
                    progress=entry.writeback,
                    on_progress=persist_writeback,
                )
            except ContextAuthorizationError:
                return await self._fail(
                    run,
                    entry,
                    patch,
                    code="DATAHUB_AUTHORIZATION_FAILED",
                    message="DataHub rejected the writeback credential.",
                    retryable=False,
                )
            except (ContextTimeoutError, ContextTransportError):
                return await self._fail(
                    run,
                    entry,
                    patch,
                    code="DATAHUB_WRITEBACK_FAILED",
                    message="DataHub writeback did not complete.",
                    retryable=True,
                )
            except ContextLoadError:
                return await self._fail(
                    run,
                    entry,
                    patch,
                    code="DATAHUB_WRITEBACK_REJECTED",
                    message="DataHub returned an invalid writeback acknowledgement.",
                    retryable=False,
                )
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
