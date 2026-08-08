from pathlib import Path

import pytest
from pydantic import SecretStr, ValidationError

from changesafe.config import Mode, Settings, resolve_env_file


def test_replay_defaults_need_no_credentials(tmp_path: Path) -> None:
    settings = Settings(
        _env_file=None,
        changesafe_data_path=tmp_path / "changesafe.db",
    )

    assert settings.mode is Mode.REPLAY
    assert settings.live_context_enabled is False
    assert settings.public_pr_enabled is False
    assert settings.public_writeback_enabled is False


@pytest.mark.parametrize("gate", ["public_pr_enabled", "public_writeback_enabled"])
def test_external_mutation_requires_admin_token(gate: str, tmp_path: Path) -> None:
    values = {
        "mode": Mode.LIVE,
        "changesafe_data_path": tmp_path / "changesafe.db",
        gate: True,
    }

    with pytest.raises(ValidationError, match="CHANGESAFE_ADMIN_TOKEN"):
        Settings(_env_file=None, **values)


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
        "llm_available": True,
        "github_publication_available": False,
        "datahub_writeback_available": False,
        "openai_model": "gpt-5.6-luna",
    }
    assert "secret" not in str(public).lower()


def test_private_env_file_is_preferred_when_present(tmp_path: Path) -> None:
    private_file = tmp_path / "changesafe.env"
    private_file.write_text("CHANGESAFE_MODE=auto\n", encoding="utf-8")

    assert resolve_env_file(private_file) == private_file
    assert resolve_env_file(tmp_path / "missing.env") is None
