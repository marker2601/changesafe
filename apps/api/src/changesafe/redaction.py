"""Recursive secret redaction for evidence, errors, and logs."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

SECRET_KEY_PARTS = ("authorization", "token", "secret", "password", "api_key")
REDACTED = "[REDACTED]"


def _is_secret_key(key: object) -> bool:
    normalized = str(key).casefold().replace("-", "_")
    return any(part in normalized for part in SECRET_KEY_PARTS)


def redact(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            key: REDACTED if _is_secret_key(key) else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [redact(item) for item in value]
    return value
