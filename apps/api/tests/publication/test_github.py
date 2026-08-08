import json
from hashlib import sha1
from pathlib import Path

import httpx
import pytest
import respx

from changesafe.context.replay import ReplayDataHubContext
from changesafe.domain import ArtifactBundle, ChangeRequest
from changesafe.generation.service import ArtifactGenerationService
from changesafe.publication.base import publication_key
from changesafe.publication.github import GitHubPublicationError, GitHubPublisher
from changesafe.risk import score_change

from .helpers import golden_change

RUN_ID = "0198f000-0000-7000-8000-000000000000"


def expected_branch(
    change: ChangeRequest, artifacts: ArtifactBundle
) -> tuple[str, str]:
    assert artifacts.manifest_hash is not None
    key = publication_key(change, change.source_commit, artifacts.manifest_hash)
    return f"changesafe/{RUN_ID[:8]}-{key[:16]}", key


async def artifact_bundle() -> tuple[ChangeRequest, ArtifactBundle]:
    change = golden_change()
    context = await ReplayDataHubContext.from_default().load(change)
    return change, await ArtifactGenerationService().generate(
        change, context, score_change(change, context)
    )


def git_tree(artifacts: ArtifactBundle) -> dict[str, object]:
    return {
        "truncated": False,
        "tree": [
            {
                "path": "models",
                "mode": "040000",
                "type": "tree",
                "sha": "models-tree",
            },
            {
                "path": "models/marts",
                "mode": "040000",
                "type": "tree",
                "sha": "marts-tree",
            },
            *[
            {
                "path": path,
                "mode": "100644",
                "type": "blob",
                "sha": sha1(
                    b"blob "
                    + str(len(artifact.content.encode("utf-8"))).encode("ascii")
                    + b"\0"
                    + artifact.content.encode("utf-8"),
                    usedforsecurity=False,
                ).hexdigest(),
            }
            for path, artifact in sorted(artifacts.files.items())
            ],
        ],
    }


@pytest.mark.asyncio
@respx.mock
async def test_github_publisher_maps_verified_bundle_to_git_data_api(
    tmp_path: Path,
) -> None:
    del tmp_path
    change, artifacts = await artifact_bundle()
    expected, key = expected_branch(change, artifacts)
    root = "https://api.github.com/repos/acme/analytics"
    respx.get(f"{root}/git/ref/heads/{expected.replace('/', '%2F')}").mock(
        return_value=httpx.Response(404, json={"message": "not found"})
    )
    respx.get(f"{root}/git/ref/heads/main").mock(
        return_value=httpx.Response(200, json={"object": {"sha": "base-commit"}})
    )
    respx.get(f"{root}/git/commits/base-commit").mock(
        return_value=httpx.Response(200, json={"tree": {"sha": "base-tree"}})
    )
    blob_count = 0

    def blob_response(_request: httpx.Request) -> httpx.Response:
        nonlocal blob_count
        blob_count += 1
        return httpx.Response(201, json={"sha": f"blob-{blob_count}"})

    respx.post(f"{root}/git/blobs").mock(side_effect=blob_response)
    tree = respx.post(f"{root}/git/trees").mock(
        return_value=httpx.Response(201, json={"sha": "new-tree"})
    )
    respx.post(f"{root}/git/commits").mock(
        return_value=httpx.Response(201, json={"sha": "new-commit"})
    )
    branch = respx.post(f"{root}/git/refs").mock(
        return_value=httpx.Response(201, json={"ref": "created"})
    )
    pull = respx.post(f"{root}/pulls").mock(
        return_value=httpx.Response(
            201, json={"html_url": "https://github.com/acme/analytics/pull/7"}
        )
    )
    respx.get(
        f"{root}/pulls",
        params={
            "state": "open",
            "head": f"acme:{expected}",
            "base": "main",
        },
    ).mock(return_value=httpx.Response(200, json=[]))
    publisher = GitHubPublisher(
        token="repository-secret",
        repository="acme/analytics",
        base_branch="main",
    )

    result = await publisher.publish(
        run_id=RUN_ID,
        change=change,
        artifacts=artifacts,
    )

    assert blob_count == 7
    assert result.branch == expected
    assert result.pull_request_url == "https://github.com/acme/analytics/pull/7"
    assert json.loads(tree.calls.last.request.content)["base_tree"] == "base-tree"
    assert json.loads(branch.calls.last.request.content) == {
        "ref": f"refs/heads/{expected}",
        "sha": "new-commit",
    }
    commit_requests = [
        call.request
        for call in respx.calls
        if call.request.url.path.endswith("/git/commits")
    ]
    assert key in json.loads(commit_requests[-1].content)["message"]
    assert (
        json.loads(pull.calls.last.request.content)["body"]
        == artifacts.files["PR_BODY.md"].content
    )
    assert all(
        call.request.headers["Authorization"] == "Bearer repository-secret"
        for call in respx.calls
    )
    assert all(call.request.url.host == "api.github.com" for call in respx.calls)


@pytest.mark.asyncio
@respx.mock
async def test_github_auth_failure_is_typed_and_does_not_expose_token() -> None:
    change, artifacts = await artifact_bundle()
    expected, _ = expected_branch(change, artifacts)
    respx.get(
        "https://api.github.com/repos/acme/analytics/git/ref/heads/"
        f"{expected.replace('/', '%2F')}"
    ).mock(return_value=httpx.Response(404, json={"message": "not found"}))
    respx.get("https://api.github.com/repos/acme/analytics/git/ref/heads/main").mock(
        return_value=httpx.Response(403, json={"message": "denied"})
    )
    publisher = GitHubPublisher(
        token="never-print-this",
        repository="acme/analytics",
        base_branch="main",
    )

    with pytest.raises(GitHubPublicationError) as captured:
        await publisher.publish(
            run_id=RUN_ID,
            change=change,
            artifacts=artifacts,
        )

    assert captured.value.code == "GITHUB_AUTH_FAILED"
    assert captured.value.retryable is False
    assert "never-print-this" not in str(captured.value)


@pytest.mark.asyncio
@respx.mock
async def test_github_publisher_reconciles_existing_branch_and_pull_request() -> None:
    change, artifacts = await artifact_bundle()
    expected, key = expected_branch(change, artifacts)
    root = "https://api.github.com/repos/acme/analytics"
    respx.get(f"{root}/git/ref/heads/{expected.replace('/', '%2F')}").mock(
        return_value=httpx.Response(200, json={"object": {"sha": "existing"}})
    )
    respx.get(f"{root}/git/commits/existing").mock(
        return_value=httpx.Response(
            200,
            json={
                "message": f"ChangeSafe migration\n\nChangeSafe-Idempotency-Key: {key}",
                "tree": {"sha": "existing-tree"},
                "parents": [{"sha": "parent-commit"}],
            },
        )
    )
    respx.get(f"{root}/git/commits/parent-commit").mock(
        return_value=httpx.Response(200, json={"tree": {"sha": "parent-tree"}})
    )
    respx.get(
        f"{root}/git/trees/existing-tree", params={"recursive": "1"}
    ).mock(return_value=httpx.Response(200, json=git_tree(artifacts)))
    respx.get(
        f"{root}/git/trees/parent-tree", params={"recursive": "1"}
    ).mock(return_value=httpx.Response(200, json={"truncated": False, "tree": []}))
    respx.get(
        f"{root}/pulls",
        params={
            "state": "open",
            "head": f"acme:{expected}",
            "base": "main",
        },
    ).mock(
        return_value=httpx.Response(
            200,
            json=[{"html_url": "https://github.com/acme/analytics/pull/7"}],
        )
    )
    publisher = GitHubPublisher(
        token="repository-secret",
        repository="acme/analytics",
        base_branch="main",
    )

    branch = await publisher.ensure_branch(
        run_id=RUN_ID,
        change=change,
        artifacts=artifacts,
    )
    pull_request_url = await publisher.ensure_pull_request(
        branch=branch,
        change=change,
        artifacts=artifacts,
    )

    assert branch == expected
    assert pull_request_url == "https://github.com/acme/analytics/pull/7"
    assert not any(call.request.method == "POST" for call in respx.calls)


@pytest.mark.asyncio
@respx.mock
async def test_github_publisher_rejects_preexisting_mismatched_branch() -> None:
    change, artifacts = await artifact_bundle()
    expected, _ = expected_branch(change, artifacts)
    root = "https://api.github.com/repos/acme/analytics"
    respx.get(f"{root}/git/ref/heads/{expected.replace('/', '%2F')}").mock(
        return_value=httpx.Response(200, json={"object": {"sha": "unexpected"}})
    )
    respx.get(f"{root}/git/commits/unexpected").mock(
        return_value=httpx.Response(
            200,
            json={"message": "Unrelated commit", "tree": {"sha": "other"}},
        )
    )
    publisher = GitHubPublisher(
        token="repository-secret",
        repository="acme/analytics",
        base_branch="main",
    )

    with pytest.raises(GitHubPublicationError) as captured:
        await publisher.ensure_branch(
            run_id=RUN_ID,
            change=change,
            artifacts=artifacts,
        )

    assert captured.value.code == "GITHUB_BRANCH_CONFLICT"
    assert captured.value.retryable is False


@pytest.mark.asyncio
@respx.mock
async def test_github_publisher_rejects_same_marker_with_different_tree() -> None:
    change, artifacts = await artifact_bundle()
    expected, key = expected_branch(change, artifacts)
    root = "https://api.github.com/repos/acme/analytics"
    respx.get(f"{root}/git/ref/heads/{expected.replace('/', '%2F')}").mock(
        return_value=httpx.Response(200, json={"object": {"sha": "tampered"}})
    )
    respx.get(f"{root}/git/commits/tampered").mock(
        return_value=httpx.Response(
            200,
            json={
                "message": f"ChangeSafe migration\n\nChangeSafe-Idempotency-Key: {key}",
                "tree": {"sha": "tampered-tree"},
                "parents": [{"sha": "parent-commit"}],
            },
        )
    )
    respx.get(f"{root}/git/commits/parent-commit").mock(
        return_value=httpx.Response(200, json={"tree": {"sha": "parent-tree"}})
    )
    tampered = git_tree(artifacts)
    assert isinstance(tampered["tree"], list)
    first_blob = next(
        entry for entry in tampered["tree"] if entry["type"] == "blob"
    )
    first_blob["sha"] = "different-blob"
    respx.get(
        f"{root}/git/trees/tampered-tree", params={"recursive": "1"}
    ).mock(return_value=httpx.Response(200, json=tampered))
    respx.get(
        f"{root}/git/trees/parent-tree", params={"recursive": "1"}
    ).mock(return_value=httpx.Response(200, json={"truncated": False, "tree": []}))
    publisher = GitHubPublisher(
        token="repository-secret",
        repository="acme/analytics",
        base_branch="main",
    )

    with pytest.raises(GitHubPublicationError) as captured:
        await publisher.ensure_branch(
            run_id=RUN_ID,
            change=change,
            artifacts=artifacts,
        )

    assert captured.value.code == "GITHUB_BRANCH_CONFLICT"
    assert captured.value.retryable is False
