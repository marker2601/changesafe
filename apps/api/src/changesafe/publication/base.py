"""Publication contracts and stable idempotency keys."""

from __future__ import annotations

import json
from hashlib import sha256
from typing import Protocol
from uuid import UUID

from changesafe.domain import ArtifactBundle, ChangeRequest, StrictModel


class GitHubResult(StrictModel):
    branch: str
    pull_request_url: str


class GitHubPublisherPort(Protocol):
    async def ensure_branch(
        self,
        *,
        run_id: UUID | str,
        change: ChangeRequest,
        artifacts: ArtifactBundle,
    ) -> str: ...

    async def ensure_pull_request(
        self,
        *,
        branch: str,
        change: ChangeRequest,
        artifacts: ArtifactBundle,
    ) -> str: ...

    async def publish(
        self,
        *,
        run_id: UUID | str,
        change: ChangeRequest,
        artifacts: ArtifactBundle,
    ) -> GitHubResult: ...


def publication_key(
    change: ChangeRequest, source_commit: str, artifact_manifest: str
) -> str:
    payload = {
        "change": change.model_dump(mode="json"),
        "source_commit": source_commit,
        "artifact_manifest": artifact_manifest,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return sha256(canonical.encode("utf-8")).hexdigest()
