"""FastAPI surface for analysis runs, artifacts, and resumable events."""

from __future__ import annotations

import asyncio
import re
import secrets
from collections import defaultdict, deque
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from decimal import Decimal
from inspect import isawaitable
from pathlib import Path
from time import monotonic
from typing import Annotated, Literal
from uuid import UUID

from fastapi import FastAPI, Header, HTTPException, Query, Request, Response, status
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from changesafe.config import Mode, Settings
from changesafe.context.base import (
    ContextAuthorizationError,
    ContextLoadError,
    DataHubContextPort,
)
from changesafe.context.factory import build_context_port
from changesafe.context.replay import ReplayDataHubContext
from changesafe.domain import (
    ChangeRequest,
    PublicationReceipt,
    ReviewActivity,
    RunState,
    RunView,
    SchemaCatalog,
)
from changesafe.generation.openai_generator import OpenAIGenerationPlanner
from changesafe.generation.service import ArtifactGenerationService
from changesafe.orchestrator import ChangeSafeOrchestrator
from changesafe.publication.service import (
    ApprovalDenied,
    PublicationFailure,
    PublicationService,
    PublicationStateError,
)
from changesafe.store import LlmBudgetExceeded, RunStore

STREAM_END_STATES = {
    RunState.AWAITING_APPROVAL,
    RunState.COMPLETED,
    RunState.FAILED,
    RunState.PUBLICATION_FAILED,
    RunState.CONTEXT_FALLBACK_REQUIRED,
}
MAX_REQUEST_BODY_BYTES = 16 * 1024
SSE_HEARTBEAT_SECONDS = 15.0
SSE_POLL_SECONDS = 0.1
CONTENT_SECURITY_POLICY = (
    "default-src 'self'; "
    "base-uri 'none'; "
    "connect-src 'self'; "
    "font-src 'self'; "
    "form-action 'self'; "
    "frame-ancestors 'none'; "
    "img-src 'self' data:; "
    "object-src 'none'; "
    "script-src 'self'; "
    "style-src 'self'"
)
SESSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{16,128}$")


class HttpBoundaryMiddleware:
    def __init__(self, app: ASGIApp, *, max_body_bytes: int) -> None:
        self.app = app
        self.max_body_bytes = max_body_bytes

    async def __call__(
        self, scope: Scope, receive: Receive, send: Send
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def protected_send(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["Content-Security-Policy"] = CONTENT_SECURITY_POLICY
                headers["Cross-Origin-Opener-Policy"] = "same-origin"
                headers["Permissions-Policy"] = (
                    "camera=(), geolocation=(), microphone=()"
                )
                headers["Referrer-Policy"] = "no-referrer"
                headers["X-Content-Type-Options"] = "nosniff"
                headers["X-Frame-Options"] = "DENY"
                path = str(scope.get("path", ""))
                if path.startswith("/api/"):
                    headers["Cache-Control"] = "no-store"
            await send(message)

        request_headers = Headers(scope=scope)
        raw_length = request_headers.get("content-length")
        if raw_length is not None:
            try:
                too_large = int(raw_length) > self.max_body_bytes
            except ValueError:
                too_large = True
            if too_large:
                await self._reject(scope, receive, protected_send)
                return

        buffered: list[Message] = []
        received = 0
        more_body = True
        while more_body:
            message = await receive()
            buffered.append(message)
            if message["type"] == "http.disconnect":
                break
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_body_bytes:
                    await self._reject(scope, receive, protected_send)
                    return
                more_body = bool(message.get("more_body", False))

        async def replay_receive() -> Message:
            if buffered:
                return buffered.pop(0)
            return await receive()

        await self.app(scope, replay_receive, protected_send)

    @staticmethod
    async def _reject(scope: Scope, receive: Receive, send: Send) -> None:
        response = JSONResponse(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            content={"detail": "Request body is too large"},
        )
        await response(scope, receive, send)


class RunRateLimiter:
    def __init__(self, limit: int, *, window_seconds: float = 60.0) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._requests: dict[str, deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def allow(self, client: str) -> bool:
        now = monotonic()
        cutoff = now - self.window_seconds
        async with self._lock:
            expired_clients: list[str] = []
            for tracked_client, tracked_requests in self._requests.items():
                while tracked_requests and tracked_requests[0] <= cutoff:
                    tracked_requests.popleft()
                if not tracked_requests:
                    expired_clients.append(tracked_client)
            for expired_client in expired_clients:
                del self._requests[expired_client]

            requests = self._requests[client]
            if len(requests) >= self.limit:
                return False
            requests.append(now)
            return True


def create_app(
    *,
    settings: Settings | None = None,
    context_port: DataHubContextPort | None = None,
    generator: ArtifactGenerationService | None = None,
    web_dist: Path | None = None,
) -> FastAPI:
    active_settings = settings or Settings()
    store = RunStore(active_settings.changesafe_data_path)
    active_context = context_port or build_context_port(active_settings)
    snapshot_context = (
        ReplayDataHubContext(
            active_settings.changesafe_snapshot_path,
            active_settings.changesafe_snapshot_checksum_path,
        )
        if (
            active_settings.mode is Mode.AUTO
            and active_settings.live_context_enabled
        )
        else None
    )
    active_generator = generator
    if (
        active_generator is None
        and active_settings.openai_api_key is not None
        and active_settings.mode is not Mode.REPLAY
    ):
        active_generator = ArtifactGenerationService(
            planner=OpenAIGenerationPlanner(
                api_key=active_settings.openai_api_key.get_secret_value(),
                model=active_settings.openai_model,
                input_cost_per_million_usd=(
                    active_settings.openai_input_cost_per_million_usd
                ),
                output_cost_per_million_usd=(
                    active_settings.openai_output_cost_per_million_usd
                ),
                max_input_tokens=active_settings.openai_max_input_tokens_per_call,
                max_output_tokens=active_settings.openai_max_output_tokens_per_call,
            )
        )
    active_generator = active_generator or ArtifactGenerationService()
    llm_planning_enabled = active_generator.planner is not None
    orchestrator = ChangeSafeOrchestrator(
        store=store,
        context_port=active_context,
        generator=active_generator,
        snapshot_context_port=snapshot_context,
        llm_reservation_usd=(
            active_settings.llm_max_run_cost_usd
            if llm_planning_enabled
            else Decimal(0)
        ),
        llm_budget_usd=(
            active_settings.changesafe_llm_budget_usd
            if llm_planning_enabled
            else None
        ),
    )
    publication_service = PublicationService(
        store=store,
        settings=active_settings,
        context_port=active_context,
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            close = getattr(active_context, "close", None)
            if callable(close):
                result = close()
                if isawaitable(result):
                    await result

    app = FastAPI(title="ChangeSafe API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        HttpBoundaryMiddleware,
        max_body_bytes=MAX_REQUEST_BODY_BYTES,
    )
    app.state.settings = active_settings
    app.state.store = store
    app.state.orchestrator = orchestrator
    app.state.publication_service = publication_service
    run_rate_limiter = RunRateLimiter(active_settings.changesafe_runs_per_minute)
    app.state.run_rate_limiter = run_rate_limiter
    schema_rate_limiter = RunRateLimiter(active_settings.changesafe_runs_per_minute)
    app.state.schema_rate_limiter = schema_rate_limiter

    @app.get("/healthz")
    async def health() -> dict[str, str]:
        await store.initialize()
        return {"status": "ok"}

    @app.get("/api/public-config")
    async def public_config() -> dict[str, object]:
        return active_settings.public_config()

    @app.get("/api/schema-fields", response_model=SchemaCatalog)
    async def schema_fields(
        request: Request,
        asset_urn: Annotated[str, Query(min_length=8, pattern=r"^urn:li:")],
        source: Literal["active", "recorded"] = "active",
    ) -> SchemaCatalog:
        client = request.client.host if request.client is not None else "unknown"
        if not await schema_rate_limiter.allow(f"schema:{client}"):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Schema lookup rate limit exceeded; retry in one minute.",
                headers={"Retry-After": "60"},
            )
        selected = active_context
        if source == "recorded":
            if isinstance(active_context, ReplayDataHubContext):
                selected = active_context
            elif snapshot_context is not None:
                selected = snapshot_context
            else:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Recorded DataHub evidence is not configured.",
                )
        try:
            return await selected.discover_schema(asset_urn)
        except PermissionError as exc:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Asset is outside the configured allowlist",
            ) from exc
        except ContextAuthorizationError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="DataHub authorization is unavailable",
            ) from exc
        except ContextLoadError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="DataHub schema could not be loaded",
            ) from exc

    @app.post("/api/runs", response_model=RunView, status_code=status.HTTP_202_ACCEPTED)
    async def create_run(
        request: Request,
        change: ChangeRequest,
        x_changesafe_session_id: str | None = Header(default=None),
    ) -> RunView:
        if (
            x_changesafe_session_id is not None
            and SESSION_ID_PATTERN.fullmatch(x_changesafe_session_id) is None
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Session ID must be a 16-128 character opaque value.",
            )
        client = request.client.host if request.client is not None else "unknown"
        if not await run_rate_limiter.allow(client):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Run rate limit exceeded; retry in one minute.",
                headers={"Retry-After": "60"},
            )
        try:
            return await orchestrator.start(
                change, session_id=x_changesafe_session_id
            )
        except LlmBudgetExceeded as exc:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="The configured project LLM budget is exhausted.",
            ) from exc

    @app.get("/api/runs/{run_id}", response_model=RunView)
    async def get_run(run_id: UUID) -> RunView:
        run = await store.get(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="Run not found")
        return run

    @app.get("/api/owner/activity", response_model=list[ReviewActivity])
    async def owner_activity(
        x_changesafe_admin_token: str | None = Header(default=None),
    ) -> list[ReviewActivity]:
        configured = active_settings.changesafe_admin_token
        if configured is None or x_changesafe_admin_token is None:
            raise HTTPException(status_code=403, detail="Owner access is required")
        if not secrets.compare_digest(
            x_changesafe_admin_token, configured.get_secret_value()
        ):
            raise HTTPException(status_code=403, detail="Owner access is required")
        return await store.recent_activity(limit=50)

    @app.post(
        "/api/runs/{run_id}/continue-with-snapshot",
        response_model=RunView,
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def continue_with_snapshot(run_id: UUID) -> RunView:
        try:
            return await orchestrator.continue_with_snapshot(run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Run not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/api/runs/{run_id}/artifacts/{artifact_path:path}")
    async def get_artifact(run_id: UUID, artifact_path: str) -> Response:
        run = await store.get(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="Run not found")
        if run.analysis is None or artifact_path not in run.analysis.artifacts.files:
            raise HTTPException(status_code=404, detail="Artifact not found")
        artifact = run.analysis.artifacts.files[artifact_path]
        media_type = (
            "application/sql" if artifact_path.endswith(".sql") else "text/plain"
        )
        return Response(content=artifact.content, media_type=media_type)

    @app.post(
        "/api/runs/{run_id}/approve",
        response_model=PublicationReceipt,
    )
    async def approve_run(
        run_id: UUID,
        x_changesafe_admin_token: str | None = Header(default=None),
    ) -> PublicationReceipt:
        try:
            return await publication_service.approve(
                run_id, supplied_admin_token=x_changesafe_admin_token
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Run not found") from exc
        except ApprovalDenied as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except PublicationStateError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except PublicationFailure as exc:
            raise HTTPException(
                status_code=502,
                detail={
                    "code": exc.code,
                    "message": (
                        "Publication did not complete; retry is available."
                        if exc.retryable
                        else "Publication stopped and requires operator action."
                    ),
                    "retryable": exc.retryable,
                },
            ) from exc

    @app.get("/api/runs/{run_id}/publication.patch")
    async def publication_patch(run_id: UUID) -> Response:
        run = await store.get(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="Run not found")
        if run.publication is None or run.publication.patch is None:
            raise HTTPException(status_code=404, detail="Publication patch not found")
        return Response(
            content=run.publication.patch,
            media_type="text/x-diff",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="changesafe-{run_id}.patch"'
                )
            },
        )

    async def event_stream(run_id: UUID, after_sequence: int) -> AsyncIterator[str]:
        cursor = after_sequence
        last_emit = monotonic()
        while True:
            run = await store.get(run_id)
            if run is None:
                return
            events = await store.events(run_id, after_sequence=cursor)
            for event in events:
                cursor = event.sequence
                last_emit = monotonic()
                yield (
                    f"id: {event.sequence}\n"
                    "event: run_state\n"
                    f"data: {event.model_dump_json()}\n\n"
                )
            if run.state in STREAM_END_STATES and not await store.events(
                run_id, after_sequence=cursor
            ):
                return
            now = monotonic()
            if not events and now - last_emit >= SSE_HEARTBEAT_SECONDS:
                yield ": heartbeat\n\n"
                last_emit = now
            until_heartbeat = max(
                0.0, SSE_HEARTBEAT_SECONDS - (monotonic() - last_emit)
            )
            await asyncio.sleep(min(SSE_POLL_SECONDS, until_heartbeat))

    @app.get("/api/runs/{run_id}/events")
    async def run_events(
        run_id: UUID,
        after: int = 0,
        last_event_id: int | None = Header(default=None),
    ) -> StreamingResponse:
        if await store.get(run_id) is None:
            raise HTTPException(status_code=404, detail="Run not found")
        return StreamingResponse(
            event_stream(run_id, max(after, last_event_id or 0)),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    static_root = web_dist or active_settings.changesafe_web_dist
    if (static_root / "index.html").is_file():
        app.mount(
            "/",
            StaticFiles(directory=static_root, html=True),
            name="web",
        )

    return app
