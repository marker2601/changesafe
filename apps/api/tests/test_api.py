import asyncio
from pathlib import Path

import httpx
import pytest

from changesafe.api import create_app
from changesafe.config import Mode, Settings
from changesafe.context.replay import ReplayDataHubContext
from changesafe.domain import RunState

GOLDEN_CHANGE = {
    "asset_urn": (
        "urn:li:dataset:(urn:li:dataPlatform:dbt,analytics.dim_customers,PROD)"
    ),
    "operation": "rename",
    "field": "customer_email",
    "new_field": "primary_email",
    "old_type": "STRING",
    "new_type": "STRING",
    "source_commit": "demo-unsafe-change",
    "requested_by": "demo-user",
}


async def wait_for_state(
    client: httpx.AsyncClient, run_id: str, state: RunState
) -> dict:
    for _ in range(100):
        response = await client.get(f"/api/runs/{run_id}")
        payload = response.json()
        if payload["state"] == state.value:
            return payload
        await asyncio.sleep(0.01)
    raise AssertionError(f"run {run_id} did not reach {state.value}")


@pytest.mark.asyncio
async def test_api_runs_complete_replay_analysis_and_serves_artifact(
    tmp_path: Path,
) -> None:
    settings = Settings(
        _env_file=None,
        mode=Mode.REPLAY,
        changesafe_data_path=tmp_path / "runs.db",
    )
    app = create_app(
        settings=settings, context_port=ReplayDataHubContext.from_default()
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post("/api/runs", json=GOLDEN_CHANGE)
        assert created.status_code == 202
        run_id = created.json()["run_id"]

        run = await wait_for_state(client, run_id, RunState.AWAITING_APPROVAL)
        artifact = await client.get(
            f"/api/runs/{run_id}/artifacts/models/marts/dim_customers.sql"
        )

    assert run["analysis"]["risk"]["score"] == 90
    assert len(run["analysis"]["context"]["downstream_assets"]) == 4
    assert artifact.status_code == 200
    assert "customer_email as primary_email" in artifact.text.lower()


@pytest.mark.asyncio
async def test_public_config_and_health_never_expose_secrets(tmp_path: Path) -> None:
    settings = Settings(
        _env_file=None,
        mode=Mode.AUTO,
        changesafe_data_path=tmp_path / "runs.db",
        openai_api_key="openai-private",
        github_token="github-private",
        changesafe_admin_token="admin-private",
    )
    app = create_app(
        settings=settings, context_port=ReplayDataHubContext.from_default()
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        config = await client.get("/api/public-config")
        health = await client.get("/healthz")

    assert config.status_code == 200
    assert health.json() == {"status": "ok"}
    serialized = config.text.lower()
    assert "private" not in serialized
    assert "token" not in serialized


@pytest.mark.asyncio
async def test_sse_stream_contains_real_ordered_state_events(tmp_path: Path) -> None:
    settings = Settings(
        _env_file=None,
        mode=Mode.REPLAY,
        changesafe_data_path=tmp_path / "runs.db",
    )
    app = create_app(
        settings=settings, context_port=ReplayDataHubContext.from_default()
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        created = (await client.post("/api/runs", json=GOLDEN_CHANGE)).json()
        await wait_for_state(client, created["run_id"], RunState.AWAITING_APPROVAL)
        stream = await client.get(f"/api/runs/{created['run_id']}/events")

    assert stream.status_code == 200
    assert "event: run_state" in stream.text
    assert '"state":"loading_context"' in stream.text
    assert '"state":"awaiting_approval"' in stream.text


@pytest.mark.asyncio
async def test_sse_query_cursor_resumes_without_replaying_old_events(
    tmp_path: Path,
) -> None:
    settings = Settings(
        _env_file=None,
        mode=Mode.REPLAY,
        changesafe_data_path=tmp_path / "runs.db",
    )
    app = create_app(
        settings=settings, context_port=ReplayDataHubContext.from_default()
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        created = (await client.post("/api/runs", json=GOLDEN_CHANGE)).json()
        await wait_for_state(client, created["run_id"], RunState.AWAITING_APPROVAL)
        stream = await client.get(f"/api/runs/{created['run_id']}/events?after=4")

    assert stream.status_code == 200
    assert '"sequence":1' not in stream.text
    assert '"sequence":5' in stream.text
    assert '"state":"awaiting_approval"' in stream.text
