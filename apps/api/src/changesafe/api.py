"""FastAPI surface for analysis runs, artifacts, and resumable events."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from uuid import UUID

from fastapi import FastAPI, Header, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import RequestResponseEndpoint

from changesafe.config import Settings
from changesafe.context.base import DataHubContextPort
from changesafe.context.factory import build_context_port
from changesafe.domain import ChangeRequest, PublicationReceipt, RunState, RunView
from changesafe.generation.openai_generator import OpenAIGenerationPlanner
from changesafe.generation.service import ArtifactGenerationService
from changesafe.orchestrator import ChangeSafeOrchestrator
from changesafe.publication.service import (
    ApprovalDenied,
    PublicationFailure,
    PublicationService,
    PublicationStateError,
)
from changesafe.store import RunStore

STREAM_END_STATES = {
    RunState.AWAITING_APPROVAL,
    RunState.COMPLETED,
    RunState.FAILED,
    RunState.PUBLICATION_FAILED,
}
MAX_REQUEST_BODY_BYTES = 16 * 1024
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
    active_generator = generator
    if active_generator is None and active_settings.openai_api_key is not None:
        active_generator = ArtifactGenerationService(
            planner=OpenAIGenerationPlanner(
                api_key=active_settings.openai_api_key.get_secret_value(),
                model=active_settings.openai_model,
            )
        )
    orchestrator = ChangeSafeOrchestrator(
        store=store,
        context_port=active_context,
        generator=active_generator or ArtifactGenerationService(),
    )
    publication_service = PublicationService(
        store=store,
        settings=active_settings,
        context_port=active_context,
    )
    app = FastAPI(title="ChangeSafe API", version="0.1.0")
    app.state.settings = active_settings
    app.state.store = store
    app.state.orchestrator = orchestrator
    app.state.publication_service = publication_service

    def protect_response(response: Response) -> Response:
        response.headers["Content-Security-Policy"] = CONTENT_SECURITY_POLICY
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        response.headers["Permissions-Policy"] = (
            "camera=(), geolocation=(), microphone=()"
        )
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        return response

    @app.middleware("http")
    async def enforce_http_boundary(
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        raw_length = request.headers.get("content-length")
        if raw_length is not None:
            try:
                too_large = int(raw_length) > MAX_REQUEST_BODY_BYTES
            except ValueError:
                too_large = True
            if too_large:
                return protect_response(
                    JSONResponse(
                        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                        content={"detail": "Request body is too large"},
                    )
                )

        response = await call_next(request)
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return protect_response(response)

    @app.get("/healthz")
    async def health() -> dict[str, str]:
        await store.initialize()
        return {"status": "ok"}

    @app.get("/api/public-config")
    async def public_config() -> dict[str, object]:
        return active_settings.public_config()

    @app.post("/api/runs", response_model=RunView, status_code=status.HTTP_202_ACCEPTED)
    async def create_run(change: ChangeRequest) -> RunView:
        return await orchestrator.start(change)

    @app.get("/api/runs/{run_id}", response_model=RunView)
    async def get_run(run_id: UUID) -> RunView:
        run = await store.get(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="Run not found")
        return run

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
                    "message": "Publication did not complete; retry is available.",
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
        while True:
            run = await store.get(run_id)
            if run is None:
                return
            events = await store.events(run_id, after_sequence=cursor)
            for event in events:
                cursor = event.sequence
                yield (
                    f"id: {event.sequence}\n"
                    "event: run_state\n"
                    f"data: {event.model_dump_json()}\n\n"
                )
            if run.state in STREAM_END_STATES and not await store.events(
                run_id, after_sequence=cursor
            ):
                return
            if not events:
                yield ": heartbeat\n\n"
            await asyncio.sleep(0.1)

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
