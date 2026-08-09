import asyncio
from pathlib import Path

import httpx
import pytest

import changesafe.api as api_module
from changesafe.api import create_app
from changesafe.config import Mode, Settings
from changesafe.context.base import ContextTransportError, DecisionWriteback
from changesafe.context.replay import ReplayDataHubContext
from changesafe.demo import DEMO_TARGET_URN, golden_change
from changesafe.domain import ChangeRequest, DataHubReceipt, RunState, SchemaCatalog
from changesafe.generation.openai_generator import OpenAIGenerationPlanner
from changesafe.publication.service import PublicationFailure

GOLDEN_CHANGE = golden_change().model_dump(mode="json")


class UnavailableLiveContext:
    async def load(self, change: ChangeRequest):
        del change
        raise ContextTransportError("private upstream failure")

    async def discover_schema(self, asset_urn: str) -> SchemaCatalog:
        del asset_urn
        raise ContextTransportError("private upstream failure")

    async def writeback(
        self,
        decision: DecisionWriteback,
        **_kwargs: object,
    ) -> DataHubReceipt:
        raise AssertionError(f"unexpected writeback for {decision.run_id}")


class ClosableReplayContext:
    def __init__(self) -> None:
        self.delegate = ReplayDataHubContext.from_default()
        self.closed = False

    async def load(self, change: ChangeRequest):
        return await self.delegate.load(change)

    async def discover_schema(self, asset_urn: str) -> SchemaCatalog:
        context = await self.delegate.load(golden_change())
        if context.target_urn != asset_urn:
            raise ContextTransportError("Snapshot does not contain the requested asset")
        return SchemaCatalog(
            target_urn=context.target_urn,
            target_name=context.target_name,
            schema_fields=context.schema_fields,
            provenance=context.provenance,
        )

    async def writeback(self, decision, **kwargs):
        return await self.delegate.writeback(decision, **kwargs)

    def close(self) -> None:
        self.closed = True


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
            f"/api/runs/{run_id}/artifacts/models/marts/order_details.sql"
        )

    assert run["analysis"]["risk"]["score"] == 85
    assert len(run["analysis"]["context"]["downstream_assets"]) == 25
    assert artifact.status_code == 200
    assert "cust_email as primary_email" in artifact.text.lower()


@pytest.mark.asyncio
async def test_owner_activity_is_private_and_session_limited(tmp_path: Path) -> None:
    settings = Settings(
        _env_file=None,
        mode=Mode.REPLAY,
        changesafe_data_path=tmp_path / "runs.db",
        changesafe_admin_token="owner-secret",
    )
    app = create_app(
        settings=settings, context_port=ReplayDataHubContext.from_default()
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post(
            "/api/runs",
            json=GOLDEN_CHANGE,
            headers={"X-ChangeSafe-Session-ID": "judge_session_0123456789"},
        )
        run_id = created.json()["run_id"]
        await wait_for_state(client, run_id, RunState.AWAITING_APPROVAL)
        missing = await client.get("/api/owner/activity")
        wrong = await client.get(
            "/api/owner/activity",
            headers={"X-ChangeSafe-Admin-Token": "wrong-secret"},
        )
        allowed = await client.get(
            "/api/owner/activity",
            headers={"X-ChangeSafe-Admin-Token": "owner-secret"},
        )

    assert missing.status_code == 403
    assert wrong.status_code == 403
    assert allowed.status_code == 200
    assert allowed.json()[0]["run_id"] == run_id
    serialized = allowed.text
    assert "cust_email" not in serialized
    assert "requested_by" not in serialized
    assert "judge_session_0123456789" not in serialized


@pytest.mark.asyncio
async def test_malformed_session_id_is_rejected_with_neutral_copy(
    tmp_path: Path,
) -> None:
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
        response = await client.post(
            "/api/runs",
            json=GOLDEN_CHANGE,
            headers={"X-ChangeSafe-Session-ID": "person@example.com"},
        )

    assert response.status_code == 400
    assert response.json()["detail"] == (
        "Session ID must be a 16-128 character opaque value."
    )


@pytest.mark.asyncio
async def test_run_creation_is_rate_limited_per_client(tmp_path: Path) -> None:
    settings = Settings(
        _env_file=None,
        mode=Mode.REPLAY,
        changesafe_data_path=tmp_path / "runs.db",
        changesafe_runs_per_minute=1,
    )
    app = create_app(
        settings=settings, context_port=ReplayDataHubContext.from_default()
    )
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        accepted = await client.post("/api/runs", json=GOLDEN_CHANGE)
        limited = await client.post("/api/runs", json=GOLDEN_CHANGE)
        await wait_for_state(
            client, accepted.json()["run_id"], RunState.AWAITING_APPROVAL
        )

    assert accepted.status_code == 202
    assert limited.status_code == 429
    assert limited.headers["retry-after"] == "60"


@pytest.mark.asyncio
async def test_schema_endpoint_returns_recorded_fields_without_credentials(
    tmp_path: Path,
) -> None:
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
        response = await client.get(
            "/api/schema-fields",
            params={"asset_urn": DEMO_TARGET_URN, "source": "active"},
        )

    assert response.status_code == 200
    assert len(response.json()["schema_fields"]) == 55
    assert response.json()["provenance"]["mode"] == "snapshot"
    assert "token" not in response.text.casefold()


@pytest.mark.asyncio
async def test_schema_endpoint_rejects_malformed_and_out_of_allowlist_assets(
    tmp_path: Path,
) -> None:
    settings = Settings(
        _env_file=None,
        mode=Mode.REPLAY,
        changesafe_data_path=tmp_path / "runs.db",
    )
    malformed_app = create_app(
        settings=settings,
        context_port=ReplayDataHubContext.from_default(),
    )
    denied_app = create_app(
        settings=Settings(
            _env_file=None,
            mode=Mode.REPLAY,
            changesafe_data_path=tmp_path / "denied-runs.db",
            demo_urn_allowlist=(
                "urn:li:dataset:(urn:li:dataPlatform:snowflake,"
                "example.unrelated,PROD)"
            ),
        ),
        context_port=ReplayDataHubContext.from_default(),
    )
    malformed_transport = httpx.ASGITransport(app=malformed_app)
    denied_transport = httpx.ASGITransport(app=denied_app)

    async with httpx.AsyncClient(
        transport=malformed_transport, base_url="http://test"
    ) as client:
        malformed = await client.get(
            "/api/schema-fields", params={"asset_urn": "invalid"}
        )
    async with httpx.AsyncClient(
        transport=denied_transport, base_url="http://test"
    ) as client:
        denied = await client.get(
            "/api/schema-fields", params={"asset_urn": DEMO_TARGET_URN}
        )

    assert malformed.status_code == 422
    assert denied.status_code == 403
    assert denied.json()["detail"] == "Asset is outside the configured allowlist"
    assert "private" not in denied.text


@pytest.mark.asyncio
async def test_schema_endpoint_rejects_snapshot_target_outside_auto_allowlist(
    tmp_path: Path,
) -> None:
    app = create_app(
        settings=Settings(
            _env_file=None,
            mode=Mode.AUTO,
            changesafe_data_path=tmp_path / "runs.db",
            datahub_gms_url="https://datahub.example.test",
            datahub_gms_token="private-token",
            demo_urn_allowlist=(
                "urn:li:dataset:(urn:li:dataPlatform:snowflake,"
                "example.unrelated,PROD)"
            ),
        ),
        context_port=UnavailableLiveContext(),
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/api/schema-fields",
            params={"asset_urn": DEMO_TARGET_URN, "source": "recorded"},
        )

    assert response.status_code == 403
    assert response.json()["detail"] == "Asset is outside the configured allowlist"
    assert "private" not in response.text


@pytest.mark.asyncio
async def test_schema_endpoint_returns_safe_transport_failure(tmp_path: Path) -> None:
    app = create_app(
        settings=Settings(
            _env_file=None,
            mode=Mode.LIVE,
            changesafe_data_path=tmp_path / "runs.db",
            datahub_gms_url="https://datahub.example.test",
            datahub_gms_token="private-token",
        ),
        context_port=UnavailableLiveContext(),
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/api/schema-fields", params={"asset_urn": DEMO_TARGET_URN}
        )

    assert response.status_code == 502
    assert response.json()["detail"] == "DataHub schema could not be loaded"
    assert "private" not in response.text
    assert "token" not in response.text.casefold()


@pytest.mark.asyncio
async def test_schema_endpoint_can_explicitly_use_recorded_evidence_in_auto_mode(
    tmp_path: Path,
) -> None:
    app = create_app(
        settings=Settings(
            _env_file=None,
            mode=Mode.AUTO,
            changesafe_data_path=tmp_path / "runs.db",
            datahub_gms_url="https://datahub.example.test",
            datahub_gms_token="private-token",
        ),
        context_port=UnavailableLiveContext(),
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/api/schema-fields",
            params={"asset_urn": DEMO_TARGET_URN, "source": "recorded"},
        )

    assert response.status_code == 200
    assert response.json()["provenance"]["mode"] == "snapshot"


@pytest.mark.asyncio
async def test_schema_endpoint_rejects_unconfigured_recorded_evidence(
    tmp_path: Path,
) -> None:
    app = create_app(
        settings=Settings(
            _env_file=None,
            mode=Mode.LIVE,
            changesafe_data_path=tmp_path / "runs.db",
            datahub_gms_url="https://datahub.example.test",
            datahub_gms_token="private-token",
        ),
        context_port=UnavailableLiveContext(),
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/api/schema-fields",
            params={"asset_urn": DEMO_TARGET_URN, "source": "recorded"},
        )

    assert response.status_code == 409
    assert response.json()["detail"] == "Recorded DataHub evidence is not configured."


@pytest.mark.asyncio
async def test_schema_rate_limit_does_not_consume_run_creation_quota(
    tmp_path: Path,
) -> None:
    app = create_app(
        settings=Settings(
            _env_file=None,
            mode=Mode.REPLAY,
            changesafe_data_path=tmp_path / "runs.db",
            changesafe_runs_per_minute=1,
        ),
        context_port=ReplayDataHubContext.from_default(),
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        first_schema = await client.get(
            "/api/schema-fields", params={"asset_urn": DEMO_TARGET_URN}
        )
        limited_schema = await client.get(
            "/api/schema-fields", params={"asset_urn": DEMO_TARGET_URN}
        )
        created = await client.post("/api/runs", json=GOLDEN_CHANGE)
        await wait_for_state(
            client, created.json()["run_id"], RunState.AWAITING_APPROVAL
        )

    assert first_schema.status_code == 200
    assert limited_schema.status_code == 429
    assert limited_schema.headers["retry-after"] == "60"
    assert created.status_code == 202


@pytest.mark.asyncio
async def test_rate_limiter_prunes_expired_client_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = 100.0
    monkeypatch.setattr(api_module, "monotonic", lambda: now)
    limiter = api_module.RunRateLimiter(limit=1, window_seconds=60)

    assert await limiter.allow("expired-client") is True
    now = 161.0
    assert await limiter.allow("active-client") is True

    assert set(limiter._requests) == {"active-client"}


@pytest.mark.asyncio
async def test_app_lifespan_closes_the_context_adapter(tmp_path: Path) -> None:
    context = ClosableReplayContext()
    settings = Settings(
        _env_file=None,
        mode=Mode.REPLAY,
        changesafe_data_path=tmp_path / "runs.db",
    )
    app = create_app(settings=settings, context_port=context)

    async with app.router.lifespan_context(app):
        assert context.closed is False

    assert context.closed is True


@pytest.mark.asyncio
async def test_run_creation_fails_before_llm_call_when_budget_is_exhausted(
    tmp_path: Path,
) -> None:
    settings = Settings(
        _env_file=None,
        mode=Mode.AUTO,
        changesafe_data_path=tmp_path / "runs.db",
        openai_api_key="configured-test-key",
        changesafe_llm_budget_usd="0.01",
    )
    app = create_app(
        settings=settings, context_port=ReplayDataHubContext.from_default()
    )
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/runs", json=GOLDEN_CHANGE)

    assert response.status_code == 429
    assert response.json()["detail"] == (
        "The configured project LLM budget is exhausted."
    )


@pytest.mark.asyncio
async def test_preflight_llm_fallback_releases_budget_reservation(
    tmp_path: Path,
) -> None:
    settings = Settings(
        _env_file=None,
        mode=Mode.AUTO,
        changesafe_data_path=tmp_path / "runs.db",
        openai_api_key="configured-test-key",
        openai_max_input_tokens_per_call=512,
        changesafe_llm_budget_usd="0.3",
    )
    app = create_app(
        settings=settings, context_port=ReplayDataHubContext.from_default()
    )
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        for _ in range(3):
            created = await client.post("/api/runs", json=GOLDEN_CHANGE)
            assert created.status_code == 202
            await wait_for_state(
                client,
                created.json()["run_id"],
                RunState.AWAITING_APPROVAL,
            )

    assert await app.state.store.llm_committed_cost_usd() == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("retryable", "expected_message"),
    [
        (True, "Publication did not complete; retry is available."),
        (False, "Publication stopped and requires operator action."),
    ],
)
async def test_publication_failure_message_matches_retryability(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    retryable: bool,
    expected_message: str,
) -> None:
    settings = Settings(
        _env_file=None,
        mode=Mode.REPLAY,
        changesafe_data_path=tmp_path / "runs.db",
    )
    app = create_app(
        settings=settings, context_port=ReplayDataHubContext.from_default()
    )

    async def fail_approval(*_args: object, **_kwargs: object) -> DataHubReceipt:
        raise PublicationFailure(
            "PUBLICATION_CONFLICT",
            "private detail",
            retryable=retryable,
        )

    monkeypatch.setattr(app.state.publication_service, "approve", fail_approval)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/runs/0198f2b8-a68d-7af3-8958-cb18c7337e91/approve"
        )

    assert response.status_code == 502
    assert response.json()["detail"] == {
        "code": "PUBLICATION_CONFLICT",
        "message": expected_message,
        "retryable": retryable,
    }


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
async def test_production_app_serves_built_web_assets_without_shadowing_api(
    tmp_path: Path,
) -> None:
    web_dist = tmp_path / "web"
    assets = web_dist / "assets"
    assets.mkdir(parents=True)
    (web_dist / "index.html").write_text(
        '<!doctype html><main id="root">ChangeSafe production</main>',
        encoding="utf-8",
    )
    (assets / "app.js").write_text("window.CHANGESAFE = true;", encoding="utf-8")
    settings = Settings(
        _env_file=None,
        mode=Mode.REPLAY,
        changesafe_data_path=tmp_path / "runs.db",
    )
    app = create_app(
        settings=settings,
        context_port=ReplayDataHubContext.from_default(),
        web_dist=web_dist,
    )
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        index = await client.get("/")
        javascript = await client.get("/assets/app.js")
        config = await client.get("/api/public-config")

    assert index.status_code == 200
    assert "ChangeSafe production" in index.text
    assert javascript.text == "window.CHANGESAFE = true;"
    assert config.headers["content-type"].startswith("application/json")


def test_app_activates_bounded_openai_planner_when_configured(tmp_path: Path) -> None:
    settings = Settings(
        _env_file=None,
        mode=Mode.AUTO,
        changesafe_data_path=tmp_path / "runs.db",
        openai_api_key="configured-test-key",
        openai_model="configured-test-model",
    )

    app = create_app(
        settings=settings,
        context_port=ReplayDataHubContext.from_default(),
        web_dist=tmp_path / "missing-web",
    )

    planner = app.state.orchestrator.generator.planner
    assert isinstance(planner, OpenAIGenerationPlanner)
    assert planner.model == "configured-test-model"


def test_replay_mode_never_activates_paid_planning(tmp_path: Path) -> None:
    settings = Settings(
        _env_file=None,
        mode=Mode.REPLAY,
        changesafe_data_path=tmp_path / "runs.db",
        openai_api_key="configured-but-disabled-test-key",
    )

    app = create_app(
        settings=settings,
        context_port=ReplayDataHubContext.from_default(),
        web_dist=tmp_path / "missing-web",
    )

    assert app.state.orchestrator.generator.planner is None
    assert settings.public_config()["llm_available"] is False


@pytest.mark.asyncio
async def test_http_boundary_rejects_oversized_requests_and_sets_security_headers(
    tmp_path: Path,
) -> None:
    settings = Settings(
        _env_file=None,
        mode=Mode.REPLAY,
        changesafe_data_path=tmp_path / "runs.db",
    )
    app = create_app(
        settings=settings,
        context_port=ReplayDataHubContext.from_default(),
        web_dist=tmp_path / "missing-web",
    )
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        health = await client.get("/healthz")
        oversized = await client.post(
            "/api/runs",
            json={"padding": "x" * 17_000},
        )

    assert health.headers["x-content-type-options"] == "nosniff"
    assert health.headers["x-frame-options"] == "DENY"
    assert "default-src 'self'" in health.headers["content-security-policy"]
    assert oversized.status_code == 413
    assert oversized.json()["detail"] == "Request body is too large"


@pytest.mark.asyncio
async def test_http_boundary_counts_chunked_body_without_content_length(
    tmp_path: Path,
) -> None:
    settings = Settings(
        _env_file=None,
        mode=Mode.REPLAY,
        changesafe_data_path=tmp_path / "runs.db",
    )
    app = create_app(
        settings=settings,
        context_port=ReplayDataHubContext.from_default(),
        web_dist=tmp_path / "missing-web",
    )
    transport = httpx.ASGITransport(app=app)

    async def oversized_chunks():
        for _ in range(20):
            yield b"x" * 1024

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/runs",
            content=oversized_chunks(),
            headers={"Content-Type": "application/json"},
        )

    assert response.status_code == 413
    assert response.json()["detail"] == "Request body is too large"


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


@pytest.mark.asyncio
async def test_auto_mode_requires_explicit_persisted_snapshot_fallback(
    tmp_path: Path,
) -> None:
    settings = Settings(
        _env_file=None,
        mode=Mode.AUTO,
        changesafe_data_path=tmp_path / "runs.db",
        datahub_gms_url="https://datahub.example.test",
        datahub_gms_token="private-token",
    )
    app = create_app(settings=settings, context_port=UnavailableLiveContext())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post("/api/runs", json=GOLDEN_CHANGE)
        run_id = created.json()["run_id"]
        stopped = await wait_for_state(
            client, run_id, RunState.CONTEXT_FALLBACK_REQUIRED
        )
        continued = await client.post(
            f"/api/runs/{run_id}/continue-with-snapshot"
        )
        completed = await wait_for_state(
            client, run_id, RunState.AWAITING_APPROVAL
        )

    assert stopped["error"] == {
        "code": "LIVE_CONTEXT_UNAVAILABLE",
        "message": (
            "Live metadata context is unavailable. Snapshot replay requires "
            "confirmation."
        ),
        "retryable": True,
    }
    assert continued.status_code == 202
    assert completed["analysis"]["context"]["provenance"]["mode"] == "snapshot"
    assert completed["error"] is None


@pytest.mark.asyncio
async def test_auto_mode_without_live_credentials_fails_replay_directly(
    tmp_path: Path,
) -> None:
    snapshot = tmp_path / "invalid-context.json"
    checksum = tmp_path / "invalid-context.sha256"
    snapshot.write_text("{}\n", encoding="utf-8")
    checksum.write_text(f"{'0' * 64}  invalid-context.json\n", encoding="ascii")
    settings = Settings(
        _env_file=None,
        mode=Mode.AUTO,
        changesafe_data_path=tmp_path / "runs.db",
        changesafe_snapshot_path=snapshot,
        changesafe_snapshot_checksum_path=checksum,
    )
    app = create_app(settings=settings)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post("/api/runs", json=GOLDEN_CHANGE)
        failed = await wait_for_state(client, created.json()["run_id"], RunState.FAILED)

    assert failed["error"]["code"] == "CONTEXT_LOAD_FAILED"


@pytest.mark.asyncio
async def test_sse_heartbeat_uses_fifteen_second_production_cadence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert api_module.SSE_HEARTBEAT_SECONDS == 15.0
    monkeypatch.setattr(api_module, "SSE_HEARTBEAT_SECONDS", 0.01)
    monkeypatch.setattr(api_module, "SSE_POLL_SECONDS", 0.002)
    settings = Settings(
        _env_file=None,
        mode=Mode.REPLAY,
        changesafe_data_path=tmp_path / "runs.db",
    )
    app = create_app(
        settings=settings,
        context_port=ReplayDataHubContext.from_default(),
        web_dist=tmp_path / "missing-web",
    )
    change = ChangeRequest.model_validate(GOLDEN_CHANGE)
    run = await app.state.store.create(change)
    await app.state.store.transition(run.run_id, RunState.LOADING_CONTEXT)

    async def finish_run() -> None:
        await asyncio.sleep(0.08)
        await app.state.store.transition(run.run_id, RunState.FAILED)

    task = asyncio.create_task(finish_run())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        stream = await client.get(f"/api/runs/{run.run_id}/events")
    await task

    assert stream.text.count(": heartbeat\n\n") >= 1
