"""Credential-free replay adapter backed by a checksummed canonical snapshot."""

from __future__ import annotations

import json
import os
from hashlib import sha256
from pathlib import Path
from typing import Any

from changesafe.context.base import (
    ContextLoadError,
    DecisionWriteback,
    WritebackProgress,
)
from changesafe.domain import (
    ChangeRequest,
    ContextBundle,
    ContextMode,
    DataHubReceipt,
)

REPO_ROOT = Path(__file__).resolve().parents[5]
DEFAULT_SNAPSHOT = REPO_ROOT / "fixtures" / "datahub" / "golden-context.json"
DEFAULT_CHECKSUM = REPO_ROOT / "fixtures" / "datahub" / "golden-context.sha256"


class ReplayDataHubContext:
    def __init__(self, snapshot_path: Path, checksum_path: Path) -> None:
        self.snapshot_path = snapshot_path
        self.checksum_path = checksum_path

    @classmethod
    def from_default(cls) -> ReplayDataHubContext:
        snapshot = Path(os.getenv("CHANGESAFE_SNAPSHOT_PATH", DEFAULT_SNAPSHOT))
        checksum = Path(
            os.getenv("CHANGESAFE_SNAPSHOT_CHECKSUM_PATH", DEFAULT_CHECKSUM)
        )
        return cls(snapshot, checksum)

    def _load_payload(self) -> tuple[dict[str, Any], str]:
        try:
            raw = self.snapshot_path.read_bytes()
            expected = self.checksum_path.read_text(encoding="ascii").split()[0]
        except OSError as exc:
            raise ContextLoadError("DataHub snapshot is unavailable") from exc

        actual = sha256(raw).hexdigest()
        if actual != expected:
            raise ContextLoadError("DataHub snapshot checksum mismatch")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ContextLoadError("DataHub snapshot is not valid JSON") from exc
        return payload, actual

    async def load(self, change: ChangeRequest) -> ContextBundle:
        payload, digest = self._load_payload()
        if payload.get("target_urn") != change.asset_urn:
            raise ContextLoadError("Snapshot does not contain the requested asset")
        if payload.get("field") != change.field:
            raise ContextLoadError("Snapshot does not contain the requested field")

        provenance = dict(payload.get("provenance", {}))
        provenance.update({"mode": ContextMode.SNAPSHOT, "snapshot_hash": digest})
        payload["provenance"] = provenance
        try:
            return ContextBundle.model_validate(payload)
        except ValueError as exc:
            raise ContextLoadError(
                "DataHub snapshot failed contract validation"
            ) from exc

    async def writeback(
        self,
        decision: DecisionWriteback,
        *,
        progress: DataHubReceipt | None = None,
        on_progress: WritebackProgress | None = None,
    ) -> DataHubReceipt:
        del progress
        receipt = DataHubReceipt(
            mode="preview",
            label="NOT WRITTEN — SNAPSHOT MODE",
            updated_urns=[decision.change.asset_urn],
            mutations=[],
        )
        if on_progress is not None:
            await on_progress(receipt)
        return receipt
