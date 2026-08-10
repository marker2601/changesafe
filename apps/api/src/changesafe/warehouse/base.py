"""Connector-independent warehouse validation contracts."""

from __future__ import annotations

from typing import Protocol

from changesafe.domain import (
    ChangeRequest,
    ContextBundle,
    WarehouseValidationResult,
)


class WarehouseValidationError(RuntimeError):
    def __init__(self, code: str, public_message: str, *, retryable: bool) -> None:
        super().__init__(code)
        self.code = code
        self.public_message = public_message
        self.retryable = retryable


class WarehouseValidationPort(Protocol):
    async def validate(
        self, change: ChangeRequest, context: ContextBundle
    ) -> WarehouseValidationResult: ...

    async def close(self) -> None: ...
