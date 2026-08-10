"""Warehouse validator selection with a disabled-path lazy import boundary."""

from __future__ import annotations

from importlib import import_module
from typing import cast

from changesafe.config import Settings
from changesafe.warehouse.base import WarehouseValidationPort
from changesafe.warehouse.snowflake import (
    ConnectorFactory,
    SnowflakeWarehouseValidator,
)


def build_warehouse_port(settings: Settings) -> WarehouseValidationPort | None:
    """Return the configured read-only adapter without importing it when disabled."""

    if not settings.warehouse_configured:
        return None
    connector = import_module("snowflake.connector")
    connect = cast(ConnectorFactory, connector.connect)
    return SnowflakeWarehouseValidator(settings, connect=connect)


__all__ = ["build_warehouse_port"]
