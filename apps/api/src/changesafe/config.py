"""Strict server-side configuration with credential-safe public projection."""

from __future__ import annotations

import json
import os
import re
from enum import StrEnum
from hashlib import sha256
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import urlsplit

from pydantic import (
    AliasChoices,
    AnyHttpUrl,
    Field,
    SecretStr,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from changesafe.demo import DEMO_TARGET_URN

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
        hide_input_in_errors=True,
    )

    mode: Mode = Field(
        default=Mode.REPLAY,
        validation_alias=AliasChoices("CHANGESAFE_MODE", "mode"),
    )
    changesafe_data_path: Path = Path("data/changesafe.db")
    changesafe_web_dist: Path = Path("apps/web/dist")
    changesafe_snapshot_path: Path = Path("fixtures/datahub/golden-context.json")
    changesafe_snapshot_checksum_path: Path = Path(
        "fixtures/datahub/golden-context.sha256"
    )
    datahub_gms_url: AnyHttpUrl | None = None
    datahub_gms_token: SecretStr | None = None
    datahub_ui_url: AnyHttpUrl | None = None
    datahub_timeout_seconds: float = Field(default=8.0, gt=0, le=30)
    datahub_retry_count: int = Field(default=1, ge=0, le=2)
    save_document_restrict_updates: bool = True
    demo_urn_allowlist: str = DEMO_TARGET_URN
    changesafe_runs_per_minute: int = Field(default=10, ge=1, le=1_000)
    github_token: SecretStr | None = None
    changesafe_github_repository: str | None = None
    github_base_branch: str = "main"
    public_writeback_enabled: bool = False
    public_pr_enabled: bool = False
    changesafe_admin_token: SecretStr | None = None
    live_evidence_required: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "CHANGESAFE_LIVE_EVIDENCE_REQUIRED", "live_evidence_required"
        ),
    )
    warehouse_validation_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "CHANGESAFE_WAREHOUSE_VALIDATION_ENABLED",
            "warehouse_validation_enabled",
        ),
    )
    warehouse_validation_required: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "CHANGESAFE_WAREHOUSE_VALIDATION_REQUIRED",
            "warehouse_validation_required",
        ),
    )
    warehouse_timeout_seconds: int = Field(
        default=20,
        ge=1,
        le=60,
        validation_alias=AliasChoices(
            "CHANGESAFE_WAREHOUSE_TIMEOUT_SECONDS", "warehouse_timeout_seconds"
        ),
    )
    warehouse_evidence_max_age_seconds: int = Field(
        default=900,
        ge=60,
        le=3600,
        validation_alias=AliasChoices(
            "CHANGESAFE_WAREHOUSE_EVIDENCE_MAX_AGE_SECONDS",
            "warehouse_evidence_max_age_seconds",
        ),
    )
    warehouse_environment_label: str = Field(
        default="competition-non-production",
        min_length=1,
        max_length=80,
        validation_alias=AliasChoices(
            "CHANGESAFE_WAREHOUSE_ENVIRONMENT_LABEL",
            "warehouse_environment_label",
        ),
    )
    snowflake_account: str | None = None
    snowflake_user: str | None = None
    snowflake_authenticator: str | None = None
    snowflake_private_key_path: Path | None = None
    snowflake_warehouse: str | None = None
    snowflake_database: str | None = None
    snowflake_schema: str | None = None
    snowflake_role: str | None = None
    snowflake_target_relation_allowlist: Annotated[
        dict[str, str], NoDecode
    ] = Field(default_factory=dict)

    @field_validator(
        "datahub_gms_url",
        "datahub_gms_token",
        "datahub_ui_url",
        "github_token",
        "changesafe_github_repository",
        "changesafe_admin_token",
        "snowflake_account",
        "snowflake_user",
        "snowflake_authenticator",
        "snowflake_private_key_path",
        "snowflake_warehouse",
        "snowflake_database",
        "snowflake_schema",
        "snowflake_role",
        mode="before",
    )
    @classmethod
    def blank_optional_values_are_unconfigured(cls, value: Any) -> Any:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("snowflake_target_relation_allowlist", mode="before")
    @classmethod
    def decode_snowflake_target_map(cls, value: Any) -> Any:
        if value is None or (isinstance(value, str) and not value.strip()):
            return {}
        if isinstance(value, str):
            try:
                decoded = json.loads(value)
            except json.JSONDecodeError:
                raise ValueError(
                    "SNOWFLAKE_TARGET_RELATION_ALLOWLIST must be a JSON object"
                ) from None
            if not isinstance(decoded, dict):
                raise ValueError(
                    "SNOWFLAKE_TARGET_RELATION_ALLOWLIST must be a JSON object"
                )
            return decoded
        return value

    @field_validator("datahub_ui_url")
    @classmethod
    def datahub_ui_url_must_not_contain_credentials(
        cls, value: AnyHttpUrl | None
    ) -> AnyHttpUrl | None:
        if value is not None and (value.username or value.password):
            raise ValueError("DATAHUB_UI_URL must not contain credentials")
        return value

    @model_validator(mode="after")
    def protect_external_mutations(self) -> Settings:
        if (
            self.public_pr_enabled or self.public_writeback_enabled
        ) and self.changesafe_admin_token is None:
            raise ValueError(
                "CHANGESAFE_ADMIN_TOKEN is required when external mutations are enabled"
            )
        if self.public_writeback_enabled and self.save_document_restrict_updates:
            raise ValueError(
                "SAVE_DOCUMENT_RESTRICT_UPDATES=false is required for "
                "deterministic DataHub decision document upserts"
            )
        if (
            self.warehouse_validation_required
            and not self.warehouse_validation_enabled
        ):
            raise ValueError("warehouse validation required=true requires enabled=true")

        configuration_values = (
            self.snowflake_account,
            self.snowflake_user,
            self.snowflake_authenticator,
            self.snowflake_private_key_path,
            self.snowflake_warehouse,
            self.snowflake_database,
            self.snowflake_schema,
            self.snowflake_role,
        )
        if self.warehouse_validation_enabled and (
            not all(value is not None for value in configuration_values)
            or not self.snowflake_target_relation_allowlist
        ):
            raise ValueError("enabled warehouse validation must be fully configured")
        if self.warehouse_validation_enabled and (
            self.snowflake_authenticator != "SNOWFLAKE_JWT"
        ):
            raise ValueError("SNOWFLAKE_AUTHENTICATOR must be SNOWFLAKE_JWT")

        approved_urns = {
            value for value in self.demo_urn_allowlist.split(";") if value
        }
        for urn, relation in self.snowflake_target_relation_allowlist.items():
            if urn not in approved_urns:
                raise ValueError(
                    "Snowflake target relation URN must be in DEMO_URN_ALLOWLIST"
                )
            parts = relation.split(".")
            if len(parts) != 3 or any(
                re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", part) is None
                for part in parts
            ):
                raise ValueError(
                    "Snowflake target relation must contain three simple identifiers"
                )
        return self

    @property
    def live_context_enabled(self) -> bool:
        return bool(self.datahub_gms_url and self.datahub_gms_token)

    @property
    def github_publication_enabled(self) -> bool:
        return bool(
            self.public_pr_enabled
            and self.github_token
            and self.changesafe_github_repository
            and self.changesafe_admin_token
        )

    @property
    def datahub_writeback_enabled(self) -> bool:
        return bool(
            self.public_writeback_enabled
            and self.live_context_enabled
            and self.changesafe_admin_token
        )

    @property
    def datahub_ui_origin(self) -> str | None:
        if self.datahub_ui_url is None:
            return None
        parsed = urlsplit(str(self.datahub_ui_url))
        host = parsed.hostname or ""
        if ":" in host:
            host = f"[{host}]"
        default_port = 443 if parsed.scheme == "https" else 80
        port = f":{parsed.port}" if parsed.port and parsed.port != default_port else ""
        return f"{parsed.scheme}://{host}{port}"

    @property
    def warehouse_configured(self) -> bool:
        return bool(
            self.warehouse_validation_enabled
            and self.snowflake_account
            and self.snowflake_user
            and self.snowflake_authenticator == "SNOWFLAKE_JWT"
            and self.snowflake_private_key_path
            and self.snowflake_warehouse
            and self.snowflake_database
            and self.snowflake_schema
            and self.snowflake_role
            and self.snowflake_target_relation_allowlist
        )

    @property
    def warehouse_target_map(self) -> dict[str, str]:
        return dict(self.snowflake_target_relation_allowlist)

    def warehouse_binding_fingerprint(self, asset_urn: str) -> str | None:
        relation = self.warehouse_target_map.get(asset_urn)
        values = (
            self.snowflake_account,
            self.snowflake_user,
            self.snowflake_role,
            self.snowflake_warehouse,
            self.snowflake_database,
            self.snowflake_schema,
            relation,
        )
        if not all(isinstance(value, str) and value for value in values):
            return None
        canonical = "\x1f".join(str(value).upper() for value in values)
        return sha256(canonical.encode("utf-8")).hexdigest()

    def public_config(self) -> dict[str, Any]:
        return {
            "mode": self.mode.value,
            "live_context_available": self.live_context_enabled,
            "datahub_ui_url": self.datahub_ui_origin,
            "llm_available": False,
            "github_publication_available": self.github_publication_enabled,
            "datahub_writeback_available": self.datahub_writeback_enabled,
            "owner_activity_available": self.changesafe_admin_token is not None,
            "live_evidence_required": self.live_evidence_required,
            "warehouse_validation_available": self.warehouse_configured,
            "warehouse_validation_required": self.warehouse_validation_required,
            "warehouse_environment_label": self.warehouse_environment_label,
        }


def load_settings_safely() -> Settings:
    """Load startup configuration without retaining sensitive validation input."""

    try:
        return Settings()
    except Exception:
        raise RuntimeError(
            "ChangeSafe startup configuration is invalid."
        ) from None
