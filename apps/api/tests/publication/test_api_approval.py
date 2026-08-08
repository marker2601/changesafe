import asyncio
from pathlib import Path

import httpx
import pytest

from changesafe.api import create_app
from changesafe.config import Mode, Settings
from changesafe.context.replay import ReplayDataHubContext

from .helpers import golden_change


@pytest.mark.asyncio
async def test_replay_approval_endpoint_returns_preview_receipt(tmp_path: Path) -> None:
    app = create_app(
        settings=Settings(
            _env_file=None,
            mode=Mode.REPLAY,
            changesafe_data_path=tmp_path / "runs.db",
        ),
        context_port=ReplayDataHubContext.from_default(),
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post(
            "/api/runs", json=golden_change().model_dump(mode="json")
        )
        run_id = created.json()["run_id"]
        for _ in range(100):
            run = await client.get(f"/api/runs/{run_id}")
            if run.json()["state"] == "awaiting_approval":
                break
            await asyncio.sleep(0.01)
        approved = await client.post(f"/api/runs/{run_id}/approve")

    assert approved.status_code == 200
    assert approved.json()["mode"] == "preview"
    assert approved.json()["writeback"]["label"] == "NOT WRITTEN — SNAPSHOT MODE"
