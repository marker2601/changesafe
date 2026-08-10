import builtins
from pathlib import Path

from changesafe.config import Settings
from changesafe.demo import DEMO_TARGET_URN
from changesafe.warehouse.factory import build_warehouse_port
from changesafe.warehouse.snowflake import SnowflakeWarehouseValidator


def configured_settings(*, enabled: bool) -> Settings:
    return Settings(
        _env_file=None,
        warehouse_validation_enabled=enabled,
        snowflake_account="private-account",
        snowflake_user="private-user",
        snowflake_authenticator="SNOWFLAKE_JWT",
        snowflake_private_key_path=Path("C:/private/credential.p8"),
        snowflake_warehouse="COMPUTE_WH",
        snowflake_database="SAFE_DB",
        snowflake_schema="SAFE_SCHEMA",
        snowflake_role="CHANGESAFE_READONLY",
        snowflake_target_relation_allowlist={
            DEMO_TARGET_URN: "SAFE_DB.SAFE_SCHEMA.ORDER_DETAILS"
        },
    )


def test_disabled_factory_does_not_import_snowflake(
    monkeypatch: object,
) -> None:
    original_import = builtins.__import__

    def guarded_import(name: str, *args: object, **kwargs: object) -> object:
        if name.startswith("snowflake"):
            raise AssertionError("disabled warehouse adapter imported Snowflake")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)  # type: ignore[attr-defined]

    assert build_warehouse_port(configured_settings(enabled=False)) is None


def test_enabled_factory_builds_snowflake_validator() -> None:
    validator = build_warehouse_port(configured_settings(enabled=True))

    assert isinstance(validator, SnowflakeWarehouseValidator)
