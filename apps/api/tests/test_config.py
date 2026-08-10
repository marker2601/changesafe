import os
from pathlib import Path

import pytest
from pydantic import SecretStr, ValidationError

from changesafe.config import Mode, Settings, resolve_env_file
from changesafe.context.factory import build_context_port
from changesafe.context.replay import ReplayDataHubContext


def test_replay_defaults_need_no_credentials(tmp_path: Path) -> None:
    settings = Settings(
        _env_file=None,
        changesafe_data_path=tmp_path / "changesafe.db",
    )

    assert settings.mode is Mode.REPLAY
    assert settings.live_context_enabled is False
    assert settings.public_pr_enabled is False
    assert settings.public_writeback_enabled is False
    assert not hasattr(settings, "llm_enabled")
    assert not hasattr(settings, "llm_max_run_cost_usd")


@pytest.mark.parametrize("gate", ["public_pr_enabled", "public_writeback_enabled"])
def test_external_mutation_requires_admin_token(gate: str, tmp_path: Path) -> None:
    values = {
        "mode": Mode.LIVE,
        "changesafe_data_path": tmp_path / "changesafe.db",
        gate: True,
    }

    with pytest.raises(ValidationError, match="CHANGESAFE_ADMIN_TOKEN"):
        Settings(_env_file=None, **values)


def test_live_writeback_requires_deterministic_document_upserts(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValidationError, match="SAVE_DOCUMENT_RESTRICT_UPDATES=false"):
        Settings(
            _env_file=None,
            mode=Mode.LIVE,
            changesafe_data_path=tmp_path / "changesafe.db",
            datahub_gms_url="https://datahub.example.com",
            datahub_gms_token="datahub-secret",
            public_writeback_enabled=True,
            changesafe_admin_token="admin-secret",
            save_document_restrict_updates=True,
        )


def test_live_factory_exports_document_upsert_policy(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("SAVE_DOCUMENT_RESTRICT_UPDATES", raising=False)
    monkeypatch.setattr(
        "changesafe.context.factory.AgentContextToolRunner.connect",
        lambda *args, **kwargs: object(),
    )
    settings = Settings(
        _env_file=None,
        mode=Mode.LIVE,
        changesafe_data_path=tmp_path / "changesafe.db",
        datahub_gms_url="https://datahub.example.com",
        datahub_gms_token="datahub-secret",
        save_document_restrict_updates=False,
    )

    build_context_port(settings)

    assert os.environ["SAVE_DOCUMENT_RESTRICT_UPDATES"] == "false"


def test_live_context_requires_url_and_token(tmp_path: Path) -> None:
    incomplete = Settings(
        _env_file=None,
        mode=Mode.LIVE,
        changesafe_data_path=tmp_path / "changesafe.db",
        datahub_gms_url="https://datahub.example.com",
    )
    complete = incomplete.model_copy(
        update={"datahub_gms_token": SecretStr("token-value")}
    )

    assert incomplete.live_context_enabled is False
    assert complete.live_context_enabled is True


def test_public_config_never_contains_credentials(tmp_path: Path) -> None:
    settings = Settings(
        _env_file=None,
        mode=Mode.AUTO,
        changesafe_data_path=tmp_path / "changesafe.db",
        datahub_gms_url="https://datahub.example.com",
        datahub_gms_token="datahub-secret",
        openai_api_key="openai-secret",
        github_token="github-secret",
        changesafe_admin_token="admin-secret",
    )

    public = settings.public_config()

    assert public == {
        "mode": "auto",
        "live_context_available": True,
        "datahub_ui_url": None,
        "llm_available": False,
        "github_publication_available": False,
        "datahub_writeback_available": False,
        "owner_activity_available": True,
        "live_evidence_required": False,
        "warehouse_validation_available": False,
        "warehouse_validation_required": False,
        "warehouse_environment_label": "competition-non-production",
    }
    assert "secret" not in str(public).lower()


def test_public_config_exposes_only_normalized_datahub_ui_origin(
    tmp_path: Path,
) -> None:
    settings = Settings(
        _env_file=None,
        changesafe_data_path=tmp_path / "changesafe.db",
        datahub_ui_url="https://datahub.example.com/catalog/search?source=changesafe",
    )

    public = settings.public_config()

    assert public["datahub_ui_url"] == "https://datahub.example.com"
    assert "/catalog" not in str(public["datahub_ui_url"])


def test_private_env_file_is_preferred_when_present(tmp_path: Path) -> None:
    private_file = tmp_path / "changesafe.env"
    private_file.write_text("CHANGESAFE_MODE=auto\n", encoding="utf-8")

    assert resolve_env_file(private_file) == private_file
    assert resolve_env_file(tmp_path / "missing.env") is None


def test_blank_optional_env_placeholders_are_treated_as_unconfigured(
    tmp_path: Path,
) -> None:
    private_file = tmp_path / "changesafe.env"
    private_file.write_text(
        "\n".join(
            [
                "DATAHUB_GMS_URL=",
                "DATAHUB_GMS_TOKEN=",
                "DATAHUB_UI_URL=",
                "OPENAI_API_KEY=",
                "GITHUB_TOKEN=",
                "CHANGESAFE_GITHUB_REPOSITORY=",
                "CHANGESAFE_ADMIN_TOKEN=",
            ]
        ),
        encoding="utf-8",
    )

    settings = Settings(_env_file=private_file)

    assert settings.datahub_gms_url is None
    assert settings.datahub_gms_token is None
    assert settings.datahub_ui_url is None
    assert "openai_api_key" not in settings.__class__.model_fields
    assert settings.github_token is None
    assert settings.changesafe_github_repository is None
    assert settings.changesafe_admin_token is None


def test_datahub_ui_url_rejects_embedded_credentials(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="must not contain credentials"):
        Settings(
            _env_file=None,
            changesafe_data_path=tmp_path / "changesafe.db",
            datahub_ui_url="https://user:secret@datahub.example.com",
        )


def test_github_actions_repository_env_does_not_configure_publication(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GITHUB_REPOSITORY", "marker2601/changesafe")

    settings = Settings(_env_file=None)

    assert settings.changesafe_github_repository is None


def test_replay_factory_uses_configured_snapshot_paths(tmp_path: Path) -> None:
    snapshot = tmp_path / "context.json"
    checksum = tmp_path / "context.sha256"
    settings = Settings(
        _env_file=None,
        mode=Mode.REPLAY,
        changesafe_snapshot_path=snapshot,
        changesafe_snapshot_checksum_path=checksum,
    )

    port = build_context_port(settings)

    assert isinstance(port, ReplayDataHubContext)
    assert port.snapshot_path == snapshot
    assert port.checksum_path == checksum
    assert settings.public_config()["llm_available"] is False


def test_warehouse_settings_accept_exact_changesafe_environment_aliases(
    tmp_path: Path,
) -> None:
    environment = tmp_path / "warehouse.env"
    environment.write_text(
        "\n".join(
            [
                "CHANGESAFE_LIVE_EVIDENCE_REQUIRED=true",
                "CHANGESAFE_WAREHOUSE_VALIDATION_ENABLED=false",
                "CHANGESAFE_WAREHOUSE_VALIDATION_REQUIRED=false",
                "CHANGESAFE_WAREHOUSE_TIMEOUT_SECONDS=30",
                "CHANGESAFE_WAREHOUSE_EVIDENCE_MAX_AGE_SECONDS=120",
                "CHANGESAFE_WAREHOUSE_ENVIRONMENT_LABEL=competition-staging",
            ]
        ),
        encoding="utf-8",
    )

    settings = Settings(_env_file=environment)

    assert settings.live_evidence_required is True
    assert settings.warehouse_validation_enabled is False
    assert settings.warehouse_validation_required is False
    assert settings.warehouse_timeout_seconds == 30
    assert settings.warehouse_evidence_max_age_seconds == 120
    assert settings.warehouse_environment_label == "competition-staging"


def test_required_warehouse_validation_must_be_enabled(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="required"):
        Settings(
            _env_file=None,
            changesafe_data_path=tmp_path / "changesafe.db",
            warehouse_validation_required=True,
        )


def test_enabled_warehouse_validation_requires_complete_safe_snowflake_config(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValidationError, match="configured"):
        Settings(
            _env_file=None,
            changesafe_data_path=tmp_path / "changesafe.db",
            warehouse_validation_enabled=True,
            snowflake_account="account",
        )


def test_warehouse_settings_reject_unsafe_authenticator_and_target_map(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValidationError, match="SNOWFLAKE_JWT"):
        Settings(
            _env_file=None,
            changesafe_data_path=tmp_path / "changesafe.db",
            warehouse_validation_enabled=True,
            snowflake_account="account",
            snowflake_user="user",
            snowflake_authenticator="externalbrowser",
            snowflake_private_key_path=tmp_path / "missing-key.pem",
            snowflake_warehouse="warehouse",
            snowflake_database="database",
            snowflake_schema="schema",
            snowflake_role="role",
            snowflake_target_relation_allowlist={
                "urn:li:dataset:unapproved": "database.schema.relation"
            },
        )


def test_warehouse_settings_publish_a_safe_target_map_only_when_configured(
    tmp_path: Path,
) -> None:
    settings = Settings(
        _env_file=None,
        changesafe_data_path=tmp_path / "changesafe.db",
        warehouse_validation_enabled=True,
        snowflake_account="account",
        snowflake_user="user",
        snowflake_authenticator="SNOWFLAKE_JWT",
        snowflake_private_key_path=tmp_path / "missing-key.pem",
        snowflake_warehouse="warehouse",
        snowflake_database="database",
        snowflake_schema="schema",
        snowflake_role="role",
        snowflake_target_relation_allowlist={
            "urn:li:dataset:(urn:li:dataPlatform:dbt,"
            "b2fd91.ORDER_ENTRY_DB.analytics.order_details,PROD)": (
                "ORDER_ENTRY_DB.analytics.order_details"
            )
        },
    )

    assert settings.warehouse_configured is True
    assert settings.warehouse_target_map == {
        "urn:li:dataset:(urn:li:dataPlatform:dbt,"
        "b2fd91.ORDER_ENTRY_DB.analytics.order_details,PROD)": (
            "ORDER_ENTRY_DB.analytics.order_details"
        )
    }


@pytest.mark.parametrize(
    ("target_urn", "relation", "message"),
    [
        (
            "urn:li:dataset:unapproved",
            "database.schema.relation",
            "DEMO_URN_ALLOWLIST",
        ),
        (
            "urn:li:dataset:(urn:li:dataPlatform:dbt,"
            "b2fd91.ORDER_ENTRY_DB.analytics.order_details,PROD)",
            "database.schema.bad-name",
            "three simple identifiers",
        ),
    ],
)
def test_warehouse_settings_reject_unapproved_or_unsafe_target_relations(
    target_urn: str,
    relation: str,
    message: str,
    tmp_path: Path,
) -> None:
    with pytest.raises(ValidationError, match=message):
        Settings(
            _env_file=None,
            changesafe_data_path=tmp_path / "changesafe.db",
            warehouse_validation_enabled=True,
            snowflake_account="account",
            snowflake_user="user",
            snowflake_authenticator="SNOWFLAKE_JWT",
            snowflake_private_key_path=tmp_path / "not-read.pem",
            snowflake_warehouse="warehouse",
            snowflake_database="database",
            snowflake_schema="schema",
            snowflake_role="role",
            snowflake_target_relation_allowlist={target_urn: relation},
        )
