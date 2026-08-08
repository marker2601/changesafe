"""Select context adapters from server configuration."""

from __future__ import annotations

from changesafe.config import Mode, Settings
from changesafe.context.base import ContextLoadError, DataHubContextPort
from changesafe.context.live import AgentContextToolRunner, LiveDataHubContext
from changesafe.context.replay import ReplayDataHubContext


def build_context_port(settings: Settings) -> DataHubContextPort:
    if settings.mode is Mode.REPLAY or not settings.live_context_enabled:
        if settings.mode is Mode.LIVE:
            raise ContextLoadError("Live mode requires DataHub URL and token")
        return ReplayDataHubContext(
            settings.changesafe_snapshot_path,
            settings.changesafe_snapshot_checksum_path,
        )

    assert settings.datahub_gms_url is not None
    assert settings.datahub_gms_token is not None
    runner = AgentContextToolRunner.connect(
        str(settings.datahub_gms_url).rstrip("/"),
        settings.datahub_gms_token.get_secret_value(),
        timeout_seconds=settings.datahub_timeout_seconds,
    )
    allowlist = {
        value.strip()
        for value in settings.demo_urn_allowlist.split(";")
        if value.strip()
    }
    return LiveDataHubContext(
        runner=runner,
        allowlist=allowlist,
        timeout_seconds=settings.datahub_timeout_seconds,
        retry_count=settings.datahub_retry_count,
    )
