import json
from pathlib import Path

import httpx
import pytest
import respx

from changesafe.context.replay import ReplayDataHubContext
from changesafe.domain import ArtifactBundle, ChangeRequest
from changesafe.generation.service import ArtifactGenerationService
from changesafe.publication.github import GitHubPublicationError, GitHubPublisher
from changesafe.risk import score_change

from .helpers import golden_change


async def artifact_bundle() -> tuple[ChangeRequest, ArtifactBundle]:
    change = golden_change()
    context = await ReplayDataHubContext.from_default().load(change)
    return change, await ArtifactGenerationService().generate(
        change, context, score_change(change, context)
    )


@pytest.mark.asyncio
@respx.mock
async def test_github_publisher_maps_verified_bundle_to_git_data_api(
    tmp_path: Path,
) -> None:
    del tmp_path
    change, artifacts = await artifact_bundle()
    root = "https://api.github.com/repos/acme/analytics"
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
    publisher = GitHubPublisher(
        token="repository-secret",
        repository="acme/analytics",
        base_branch="main",
    )

    result = await publisher.publish(
        run_id="0198f000-0000-7000-8000-000000000000",
        change=change,
        artifacts=artifacts,
    )

    assert blob_count == 7
    assert result.branch == "changesafe/0198f000"
    assert result.pull_request_url == "https://github.com/acme/analytics/pull/7"
    assert json.loads(tree.calls.last.request.content)["base_tree"] == "base-tree"
    assert json.loads(branch.calls.last.request.content) == {
        "ref": "refs/heads/changesafe/0198f000",
        "sha": "new-commit",
    }
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
            run_id="0198f000-0000-7000-8000-000000000000",
            change=change,
            artifacts=artifacts,
        )

    assert captured.value.code == "GITHUB_AUTH_FAILED"
    assert captured.value.retryable is False
    assert "never-print-this" not in str(captured.value)
