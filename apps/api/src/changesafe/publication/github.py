"""Repository-scoped GitHub Git Data API publisher."""

from __future__ import annotations

import re
from typing import Any, cast
from urllib.parse import quote
from uuid import UUID

import httpx

from changesafe.domain import ArtifactBundle, ChangeRequest
from changesafe.generation.templates import PR_BODY
from changesafe.publication.base import GitHubResult

API_ROOT = "https://api.github.com"
REPOSITORY_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


class GitHubPublicationError(RuntimeError):
    def __init__(self, code: str, message: str, *, retryable: bool) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.retryable = retryable


class GitHubPublisher:
    def __init__(
        self,
        *,
        token: str,
        repository: str,
        base_branch: str,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not REPOSITORY_PATTERN.fullmatch(repository):
            raise ValueError("repository must use the owner/name format")
        self._token = token
        self.repository = repository
        self.base_branch = base_branch
        self._client = client

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self._token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "ChangeSafe/0.1",
        }

    async def publish(
        self,
        *,
        run_id: UUID | str,
        change: ChangeRequest,
        artifacts: ArtifactBundle,
    ) -> GitHubResult:
        branch = await self.ensure_branch(
            run_id=run_id, change=change, artifacts=artifacts
        )
        pull_request_url = await self.ensure_pull_request(
            branch=branch, change=change, artifacts=artifacts
        )
        return GitHubResult(branch=branch, pull_request_url=pull_request_url)

    async def ensure_branch(
        self,
        *,
        run_id: UUID | str,
        change: ChangeRequest,
        artifacts: ArtifactBundle,
    ) -> str:
        if self._client is not None:
            return await self._ensure_branch(
                self._client, run_id, change, artifacts
            )
        async with httpx.AsyncClient(timeout=10.0) as client:
            return await self._ensure_branch(client, run_id, change, artifacts)

    async def _ensure_branch(
        self,
        client: httpx.AsyncClient,
        run_id: UUID | str,
        change: ChangeRequest,
        artifacts: ArtifactBundle,
    ) -> str:
        repository_url = f"{API_ROOT}/repos/{self.repository}"
        branch = f"changesafe/{str(run_id)[:8]}"
        existing = await self._request_json(
            client,
            "GET",
            f"{repository_url}/git/ref/heads/{quote(branch, safe='')}",
            allow_not_found=True,
        )
        if existing:
            return branch
        base_ref = await self._request_json(
            client,
            "GET",
            f"{repository_url}/git/ref/heads/{quote(self.base_branch, safe='')}",
        )
        base_sha = self._nested_string(base_ref, "object", "sha")
        base_commit = await self._request_json(
            client, "GET", f"{repository_url}/git/commits/{base_sha}"
        )
        base_tree = self._nested_string(base_commit, "tree", "sha")

        tree_entries: list[dict[str, str]] = []
        for path in sorted(artifacts.files):
            blob = await self._request_json(
                client,
                "POST",
                f"{repository_url}/git/blobs",
                json_body={
                    "content": artifacts.files[path].content,
                    "encoding": "utf-8",
                },
            )
            tree_entries.append(
                {
                    "path": path,
                    "mode": "100644",
                    "type": "blob",
                    "sha": self._string(blob, "sha"),
                }
            )

        tree = await self._request_json(
            client,
            "POST",
            f"{repository_url}/git/trees",
            json_body={"base_tree": base_tree, "tree": tree_entries},
        )
        commit = await self._request_json(
            client,
            "POST",
            f"{repository_url}/git/commits",
            json_body={
                "message": f"ChangeSafe migration for {change.field}",
                "tree": self._string(tree, "sha"),
                "parents": [base_sha],
            },
        )
        commit_sha = self._string(commit, "sha")
        try:
            await self._request_json(
                client,
                "POST",
                f"{repository_url}/git/refs",
                json_body={"ref": f"refs/heads/{branch}", "sha": commit_sha},
            )
        except GitHubPublicationError as exc:
            if exc.code != "GITHUB_CONFLICT":
                raise
            reconciled = await self._request_json(
                client,
                "GET",
                f"{repository_url}/git/ref/heads/{quote(branch, safe='')}",
                allow_not_found=True,
            )
            if not reconciled:
                raise
        return branch

    async def ensure_pull_request(
        self,
        *,
        branch: str,
        change: ChangeRequest,
        artifacts: ArtifactBundle,
    ) -> str:
        if self._client is not None:
            return await self._ensure_pull_request(
                self._client, branch, change, artifacts
            )
        async with httpx.AsyncClient(timeout=10.0) as client:
            return await self._ensure_pull_request(client, branch, change, artifacts)

    async def _ensure_pull_request(
        self,
        client: httpx.AsyncClient,
        branch: str,
        change: ChangeRequest,
        artifacts: ArtifactBundle,
    ) -> str:
        repository_url = f"{API_ROOT}/repos/{self.repository}"
        owner = self.repository.split("/", 1)[0]
        existing = await self._request_json(
            client,
            "GET",
            f"{repository_url}/pulls",
            query={
                "state": "open",
                "head": f"{owner}:{branch}",
                "base": self.base_branch,
            },
        )
        if isinstance(existing, list) and existing:
            first = existing[0]
            if isinstance(first, dict):
                return self._string(cast(dict[str, Any], first), "html_url")
        pull = await self._request_json(
            client,
            "POST",
            f"{repository_url}/pulls",
            json_body={
                "title": f"ChangeSafe: {change.operation.value} {change.field}",
                "head": branch,
                "base": self.base_branch,
                "body": artifacts.files[PR_BODY].content,
            },
        )
        if not isinstance(pull, dict):
            raise GitHubPublicationError(
                "GITHUB_INVALID_RESPONSE",
                "GitHub returned an invalid pull request response.",
                retryable=False,
            )
        return self._string(cast(dict[str, Any], pull), "html_url")

    async def _request_json(
        self,
        client: httpx.AsyncClient,
        method: str,
        url: str,
        *,
        json_body: dict[str, Any] | None = None,
        query: dict[str, str] | None = None,
        allow_not_found: bool = False,
    ) -> Any:
        try:
            response = await client.request(
                method,
                url,
                headers=self._headers,
                json=json_body,
                params=query,
            )
        except httpx.TimeoutException as exc:
            raise GitHubPublicationError(
                "GITHUB_TIMEOUT", "GitHub did not respond in time.", retryable=True
            ) from exc
        except httpx.RequestError as exc:
            raise GitHubPublicationError(
                "GITHUB_UNAVAILABLE", "GitHub could not be reached.", retryable=True
            ) from exc
        if response.status_code == 404 and allow_not_found:
            return None
        if response.status_code >= 400:
            if response.status_code in {401, 403}:
                raise GitHubPublicationError(
                    "GITHUB_AUTH_FAILED",
                    "GitHub rejected the configured repository credential.",
                    retryable=False,
                )
            if response.status_code in {409, 422}:
                raise GitHubPublicationError(
                    "GITHUB_CONFLICT",
                    "GitHub reported an existing publication resource.",
                    retryable=True,
                )
            raise GitHubPublicationError(
                "GITHUB_REQUEST_FAILED",
                f"GitHub returned HTTP {response.status_code}.",
                retryable=response.status_code >= 500,
            )
        try:
            return response.json()
        except ValueError as exc:
            raise GitHubPublicationError(
                "GITHUB_INVALID_RESPONSE",
                "GitHub returned an invalid response.",
                retryable=False,
            ) from exc

    @staticmethod
    def _string(payload: dict[str, Any], key: str) -> str:
        value = payload.get(key)
        if not isinstance(value, str) or not value:
            raise GitHubPublicationError(
                "GITHUB_INVALID_RESPONSE",
                "GitHub response omitted a required identifier.",
                retryable=False,
            )
        return value

    @classmethod
    def _nested_string(cls, payload: dict[str, Any], parent: str, key: str) -> str:
        nested = payload.get(parent)
        if not isinstance(nested, dict):
            raise GitHubPublicationError(
                "GITHUB_INVALID_RESPONSE",
                "GitHub response omitted a required object.",
                retryable=False,
            )
        return cls._string(cast(dict[str, Any], nested), key)
