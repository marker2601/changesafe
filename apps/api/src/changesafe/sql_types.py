"""Validated Snowflake scalar type semantics shared by every safety gate."""

from __future__ import annotations

import re
from typing import Literal

TYPE_EXPRESSION = re.compile(
    r"^([A-Z][A-Z0-9_ ]*?)(?:\(\s*(\d+)(?:\s*,\s*(\d+))?\s*\))?$"
)

NUMBER_TYPES = {"NUMBER", "DEC", "DECIMAL", "NUMERIC"}
INTEGER_TYPES = {"BIGINT", "BYTEINT", "INT", "INTEGER", "SMALLINT", "TINYINT"}
FLOAT_TYPES = {"DOUBLE", "DOUBLE PRECISION", "FLOAT", "FLOAT4", "FLOAT8", "REAL"}
CHAR_TYPES = {"CHAR", "CHARACTER", "NCHAR", "NATIONAL CHAR", "NATIONAL CHARACTER"}
VARCHAR_TYPES = {
    "CHAR VARYING",
    "CHARACTER VARYING",
    "NCHAR VARYING",
    "NATIONAL CHAR VARYING",
    "NATIONAL CHARACTER VARYING",
    "NVARCHAR",
    "NVARCHAR2",
    "STRING",
    "TEXT",
    "VARCHAR",
    "VARCHAR2",
}
BINARY_TYPES = {"BINARY", "VARBINARY"}
TIMESTAMP_TYPES = {
    "DATETIME",
    "TIME",
    "TIMESTAMP",
    "TIMESTAMP_LTZ",
    "TIMESTAMP_NTZ",
    "TIMESTAMP_TZ",
}
PARAMETERLESS_TYPES = {
    "ARRAY",
    "BOOLEAN",
    "DATE",
    "DECFLOAT",
    "GEOGRAPHY",
    "GEOMETRY",
    "OBJECT",
    "UUID",
    "VARIANT",
}

VARCHAR_DEFAULT_LENGTH = 16_777_216
VARCHAR_MAX_LENGTH = 134_217_728
BINARY_DEFAULT_LENGTH = 8_388_608
BINARY_MAX_LENGTH = 67_108_864


def _normalized_parts(value: str) -> tuple[str, tuple[int, ...]]:
    normalized = " ".join(value.upper().split())
    match = TYPE_EXPRESSION.fullmatch(normalized)
    if match is None:
        raise ValueError("type syntax is not supported")
    raw_base, first, second = match.groups()
    parameters = tuple(int(item) for item in (first, second) if item is not None)
    return raw_base, parameters


def canonical_sql_type(value: str) -> tuple[str, tuple[int, ...]]:
    """Return a validated canonical Snowflake scalar type and its parameters."""

    raw_base, parameters = _normalized_parts(value)
    if raw_base in INTEGER_TYPES:
        if parameters:
            raise ValueError(f"{raw_base} does not accept precision or scale")
        return "NUMBER", (38, 0)

    if raw_base in NUMBER_TYPES:
        if len(parameters) > 2:
            raise ValueError("NUMBER accepts at most precision and scale")
        precision = parameters[0] if parameters else 38
        scale = parameters[1] if len(parameters) == 2 else 0
        if not 1 <= precision <= 38:
            raise ValueError("NUMBER precision must be between 1 and 38")
        if not 0 <= scale <= min(precision, 37):
            raise ValueError(
                "NUMBER scale must be between 0 and the lesser of precision and 37"
            )
        return "NUMBER", (precision, scale)

    if raw_base in FLOAT_TYPES:
        if parameters:
            raise ValueError(f"{raw_base} does not accept parameters")
        return "FLOAT", ()

    if raw_base in CHAR_TYPES | VARCHAR_TYPES:
        if len(parameters) > 1:
            raise ValueError(f"{raw_base} accepts only one length parameter")
        default_length = 1 if raw_base in CHAR_TYPES else VARCHAR_DEFAULT_LENGTH
        length = parameters[0] if parameters else default_length
        if not 1 <= length <= VARCHAR_MAX_LENGTH:
            raise ValueError(
                f"{raw_base} length must be between 1 and {VARCHAR_MAX_LENGTH}"
            )
        return "VARCHAR", (length,)

    if raw_base in BINARY_TYPES:
        if len(parameters) > 1:
            raise ValueError(f"{raw_base} accepts only one length parameter")
        length = parameters[0] if parameters else BINARY_DEFAULT_LENGTH
        if not 1 <= length <= BINARY_MAX_LENGTH:
            raise ValueError(
                f"{raw_base} length must be between 1 and {BINARY_MAX_LENGTH}"
            )
        return "BINARY", (length,)

    if raw_base in TIMESTAMP_TYPES:
        if len(parameters) > 1:
            raise ValueError(f"{raw_base} accepts only one precision parameter")
        precision = parameters[0] if parameters else 9
        if not 0 <= precision <= 9:
            raise ValueError(f"{raw_base} precision must be between 0 and 9")
        base = "TIMESTAMP_NTZ" if raw_base == "DATETIME" else raw_base
        return base, (precision,)

    if raw_base in PARAMETERLESS_TYPES:
        if parameters:
            raise ValueError(f"{raw_base} does not accept parameters")
        return raw_base, ()

    raise ValueError(f"unsupported Snowflake scalar type: {raw_base}")


def validate_snowflake_type(value: str) -> None:
    canonical_sql_type(value)


def type_change_kind(
    current_type: str, new_type: str
) -> Literal["no_op", "widening", "incompatible"]:
    current_base, current_parameters = canonical_sql_type(current_type)
    new_base, new_parameters = canonical_sql_type(new_type)
    if (current_base, current_parameters) == (new_base, new_parameters):
        return "no_op"
    if current_base != new_base:
        return "incompatible"
    if current_base in {"VARCHAR", "BINARY"}:
        return (
            "widening"
            if new_parameters[0] > current_parameters[0]
            else "incompatible"
        )
    if current_base == "NUMBER":
        current_precision, current_scale = current_parameters
        new_precision, new_scale = new_parameters
        preserves_integer_digits = (
            new_precision - new_scale >= current_precision - current_scale
        )
        return (
            "widening"
            if new_scale >= current_scale and preserves_integer_digits
            else "incompatible"
        )
    return "incompatible"
