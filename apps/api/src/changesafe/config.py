"""Strict server-side configuration with credential-safe public projection."""

from __future__ import annotations

import os
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import AliasChoices, AnyHttpUrl, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_PRIVATE_ENV = Path("C:/Users/harik/ChangeSafe/private/changesafe.env")


class Mode(StrEnum):
    REPLAY = "replay"
    LIVE = "live"
    AUTO = "auto"


def resolve_env_file(candidate: Path | None = None) -> Path | None:
    """Return a real private env file, preferring an explicit path."""

    if candidate is not None:
        return candidate if candidate.is_file() else None

    configured = os.getenv("CHANGESAFE_ENV_FILE")
    candidates = [Path(configured)] if configured else []
    candidates.extend([DEFAULT_PRIVATE_ENV, Path(".env")])
    return next((path for path in candidates if path.is_file()), None)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=resolve_env_file(),
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    mode: Mode = Field(
        default=Mode.REPLAY,
        validation_alias=AliasChoices("CHANGESAFE_MODE", "mode"),
    )
    changesafe_data_path: Path = Path("data/changesafe.db")
    datahub_gms_url: AnyHttpUrl | None = None
    datahub_gms_token: SecretStr | None = None
    demo_urn_allowlist: str = (
        "urn:li:dataset:(urn:li:dataPlatform:dbt,analytics.dim_customers,PROD)"
    )
    openai_api_key: SecretStr | None = None
    openai_model: str = "gpt-5.6-luna"
    github_token: SecretStr | None = None
    github_repository: str | None = None
    github_base_branch: str = "main"
    public_writeback_enabled: bool = False
    public_pr_enabled: bool = False
    changesafe_admin_token: SecretStr | None = None
    changesafe_public_url: AnyHttpUrl | None = None
    sentry_dsn: str | None = None

    @model_validator(mode="after")
    def protect_external_mutations(self) -> Settings:
        if (
            self.public_pr_enabled or self.public_writeback_enabled
        ) and self.changesafe_admin_token is None:
            raise ValueError(
                "CHANGESAFE_ADMIN_TOKEN is required when external mutations are enabled"
            )
        return self

    @property
    def live_context_enabled(self) -> bool:
        return bool(self.datahub_gms_url and self.datahub_gms_token)

    @property
    def llm_enabled(self) -> bool:
        return self.openai_api_key is not None

    @property
    def github_publication_enabled(self) -> bool:
        return bool(
            self.public_pr_enabled
            and self.github_token
            and self.github_repository
            and self.changesafe_admin_token
        )

    @property
    def datahub_writeback_enabled(self) -> bool:
        return bool(
            self.public_writeback_enabled
            and self.live_context_enabled
            and self.changesafe_admin_token
        )

    def public_config(self) -> dict[str, Any]:
        return {
            "mode": self.mode.value,
            "live_context_available": self.live_context_enabled,
            "llm_available": self.llm_enabled,
            "github_publication_available": self.github_publication_enabled,
            "datahub_writeback_available": self.datahub_writeback_enabled,
            "openai_model": self.openai_model,
        }
