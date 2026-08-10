import subprocess
import sys
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


def test_disabled_factory_is_a_real_cold_import_boundary() -> None:
    script = """
import sys
from changesafe.config import Settings
from changesafe.warehouse.factory import build_warehouse_port

assert not any(
    name == "snowflake" or name.startswith("snowflake.")
    for name in sys.modules
)
assert build_warehouse_port(
    Settings(_env_file=None, warehouse_validation_enabled=False)
) is None
assert not any(
    name == "snowflake" or name.startswith("snowflake.")
    for name in sys.modules
)
"""

    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).resolve().parents[4],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr


def test_enabled_factory_builds_snowflake_validator() -> None:
    validator = build_warehouse_port(configured_settings(enabled=True))

    assert isinstance(validator, SnowflakeWarehouseValidator)
