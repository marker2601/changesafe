"""Deterministic, parsed Snowflake validation query plans."""

from __future__ import annotations

import re
import weakref
from dataclasses import dataclass
from hashlib import sha256

from sqlglot import exp, parse
from sqlglot.errors import ParseError

from changesafe.domain import ChangeOperation, ChangeRequest, ContextBundle
from changesafe.sql_types import canonical_sql_type

SIMPLE_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
COMMENT_MARKERS = ("--", "/*", "*/")
AGGREGATE_COLUMNS = (
    "ROWS_EVALUATED",
    "POPULATED_ROW_COUNT",
)
TYPE_AGGREGATE_COLUMNS = (*AGGREGATE_COLUMNS, "UNSAFE_ROW_COUNT")
SUPPORTED_TRY_CAST_TYPES = {
    "BOOLEAN",
    "DATE",
    "FLOAT",
    "NUMBER",
    "TIME",
    "TIMESTAMP",
    "TIMESTAMP_LTZ",
    "TIMESTAMP_NTZ",
    "TIMESTAMP_TZ",
    "VARCHAR",
}


class UnsafeWarehouseQuery(ValueError):
    """Raised when a query plan falls outside the reviewed read-only contract."""


class UnsupportedWarehouseConversion(UnsafeWarehouseQuery):
    """Raised when Snowflake TRY_CAST does not document the conversion family."""


@dataclass(frozen=True, slots=True, weakref_slot=True)
class WarehouseQuery:
    code: str
    sql: str
    expected_columns: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class WarehouseValidationPlan:
    relation: str
    relation_fingerprint: str
    queries: tuple[WarehouseQuery, ...]


@dataclass(frozen=True, slots=True)
class _QueryContract:
    reference: weakref.ReferenceType[WarehouseQuery]
    operation: ChangeOperation
    code: str
    sql: str
    expected_columns: tuple[str, ...]
    relation: str
    allowed_fields: frozenset[str]
    source_field: str
    destination_field: str | None
    current_type: str | None
    target_type: str | None


_QUERY_CONTRACTS: dict[int, _QueryContract] = {}


def _generated_query(
    *, code: str, sql: str, expected_columns: tuple[str, ...]
) -> WarehouseQuery:
    return WarehouseQuery(code=code, sql=sql, expected_columns=expected_columns)


def quote_identifier(value: str) -> str:
    """Render one normalized, quoted Snowflake identifier."""

    if SIMPLE_IDENTIFIER.fullmatch(value) is None:
        raise UnsafeWarehouseQuery("Identifier is outside the supported contract")
    return f'"{value.upper()}"'


def _normalize_relation(relation: str) -> str:
    parts = relation.split(".")
    if len(parts) != 3 or any(
        SIMPLE_IDENTIFIER.fullmatch(part) is None for part in parts
    ):
        raise UnsafeWarehouseQuery(
            "Relation must contain exactly three supported identifiers"
        )
    return ".".join(part.upper() for part in parts)


def _render_relation(relation: str) -> str:
    parts = _normalize_relation(relation).split(".")
    return ".".join(quote_identifier(part) for part in parts)


def fingerprint_relation(relation: str) -> str:
    """Return a stable fingerprint without placing the relation in durable evidence."""

    normalized = _normalize_relation(relation)
    return sha256(normalized.encode()).hexdigest()


def _render_try_cast_type(value: str) -> str:
    base, parameters = canonical_sql_type(value)
    if base not in SUPPORTED_TRY_CAST_TYPES:
        raise UnsupportedWarehouseConversion(
            "Warehouse conversion is outside the documented TRY_CAST contract"
        )
    rendered_base = "DOUBLE" if base == "FLOAT" else base
    if not parameters:
        return rendered_base
    rendered_parameters = ", ".join(str(parameter) for parameter in parameters)
    return f"{rendered_base}({rendered_parameters})"


def _schema_probe_sql(field: str, relation: str) -> str:
    return f"SELECT {quote_identifier(field)}\nFROM {relation}\nWHERE 1 = 0"


def _rename_sql(field: str, new_field: str, relation: str) -> str:
    return (
        "WITH projected AS (\n"
        f"  SELECT {quote_identifier(field)} AS {quote_identifier(new_field)}\n"
        f"  FROM {relation}\n"
        ")\n"
        "SELECT COUNT(*) AS rows_evaluated,\n"
        f"       COUNT({quote_identifier(new_field)}) AS populated_row_count\n"
        "FROM projected"
    )


def _remove_sql(field: str, relation: str) -> str:
    return (
        "SELECT COUNT(*) AS rows_evaluated,\n"
        f"       COUNT({quote_identifier(field)}) AS populated_row_count\n"
        f"FROM {relation}"
    )


def _type_change_sql(
    field: str,
    current_type: str,
    target_type: str,
    relation: str,
) -> str:
    quoted_field = quote_identifier(field)
    source_text = f"TO_VARCHAR({quoted_field})"
    target_value = f"TRY_CAST({source_text} AS {target_type})"
    return (
        "SELECT COUNT(*) AS rows_evaluated,\n"
        f"       COUNT({quoted_field}) AS populated_row_count,\n"
        "       COUNT_IF(\n"
        f"         {quoted_field} IS NOT NULL AND (\n"
        f"           {target_value} IS NULL OR\n"
        "           TRY_CAST(\n"
        f"             TO_VARCHAR({target_value}) AS {current_type}\n"
        f"           ) IS DISTINCT FROM {quoted_field}\n"
        "         )\n"
        "       ) AS unsafe_row_count\n"
        f"FROM {relation}"
    )


def _trusted_contract_sql(contract: _QueryContract) -> str:
    rendered_relation = _render_relation(contract.relation)
    if contract.code == "schema_probe":
        return _schema_probe_sql(contract.source_field, rendered_relation)
    if (
        contract.code == "rename_projection"
        and contract.operation is ChangeOperation.RENAME
        and contract.destination_field is not None
    ):
        return _rename_sql(
            contract.source_field,
            contract.destination_field,
            rendered_relation,
        )
    if (
        contract.code == "remove_impact"
        and contract.operation is ChangeOperation.REMOVE
    ):
        return _remove_sql(contract.source_field, rendered_relation)
    if (
        contract.code == "type_conversion"
        and contract.operation is ChangeOperation.TYPE_CHANGE
        and contract.current_type is not None
        and contract.target_type is not None
    ):
        return _type_change_sql(
            contract.source_field,
            contract.current_type,
            contract.target_type,
            rendered_relation,
        )
    raise UnsafeWarehouseQuery("Registered query semantics are inconsistent")


def _trusted_contract_columns(contract: _QueryContract) -> tuple[str, ...]:
    if contract.code == "schema_probe":
        return (contract.source_field,)
    if contract.code in {"rename_projection", "remove_impact"}:
        return AGGREGATE_COLUMNS
    if contract.code == "type_conversion":
        return TYPE_AGGREGATE_COLUMNS
    raise UnsafeWarehouseQuery("Registered query code is unsupported")


def _validated_context_field(change: ChangeRequest, context: ContextBundle) -> None:
    if change.asset_urn != context.target_urn or (
        change.field.casefold() != context.field.casefold()
    ):
        raise UnsafeWarehouseQuery("Request and context identity do not match")

    matching_fields = [
        field
        for field in context.schema_fields
        if field.name.casefold() == change.field.casefold()
    ]
    if len(matching_fields) != 1:
        raise UnsafeWarehouseQuery(
            "The selected field is not uniquely present in the context schema"
        )
    try:
        context_type = canonical_sql_type(context.field_type)
        schema_type = canonical_sql_type(matching_fields[0].data_type)
    except ValueError as exc:
        raise UnsafeWarehouseQuery("Context schema type is unsupported") from exc
    if context_type != schema_type:
        raise UnsafeWarehouseQuery("Context field and schema type do not match")

    if change.operation is ChangeOperation.RENAME:
        if change.new_field is None:
            raise UnsafeWarehouseQuery("Rename destination is required")
        quote_identifier(change.new_field)
        if change.field.casefold() == change.new_field.casefold():
            raise UnsafeWarehouseQuery(
                "Rename destination must differ from the selected field"
            )
        if any(
            field.name.casefold() == change.new_field.casefold()
            for field in context.schema_fields
        ):
            raise UnsafeWarehouseQuery(
                "Rename destination collides with an existing schema field"
            )

    if change.operation is ChangeOperation.TYPE_CHANGE:
        if change.old_type is None or change.new_type is None:
            raise UnsafeWarehouseQuery("Type change contract is incomplete")
        try:
            request_current_type = canonical_sql_type(change.old_type)
        except ValueError as exc:
            raise UnsafeWarehouseQuery("Requested current type is unsupported") from exc
        if request_current_type != context_type:
            raise UnsafeWarehouseQuery(
                "Requested current type does not match the context"
            )


def build_validation_plan(
    change: ChangeRequest,
    context: ContextBundle,
    relation: str,
) -> WarehouseValidationPlan:
    """Build and guard the exact query sequence for one supported operation."""

    quote_identifier(change.field)
    _validated_context_field(change, context)
    normalized_relation = _normalize_relation(relation)
    rendered_relation = _render_relation(normalized_relation)
    destination_field = (
        change.new_field.upper() if change.new_field is not None else None
    )
    current_type: str | None = None
    target_type: str | None = None
    if change.operation is ChangeOperation.TYPE_CHANGE:
        assert change.old_type is not None
        assert change.new_type is not None
        current_type = _render_try_cast_type(change.old_type)
        target_type = _render_try_cast_type(change.new_type)
    allowed_fields = {change.field.upper()}
    if destination_field is not None:
        allowed_fields.add(destination_field)

    def registered_query(
        *, code: str, sql: str, expected_columns: tuple[str, ...]
    ) -> WarehouseQuery:
        query = _generated_query(
            code=code,
            sql=sql,
            expected_columns=expected_columns,
        )
        query_id = id(query)

        def release(reference: weakref.ReferenceType[WarehouseQuery]) -> None:
            registered = _QUERY_CONTRACTS.get(query_id)
            if registered is not None and registered.reference is reference:
                _QUERY_CONTRACTS.pop(query_id, None)

        reference = weakref.ref(query, release)
        _QUERY_CONTRACTS[query_id] = _QueryContract(
            reference=reference,
            operation=change.operation,
            code=code,
            sql=sql,
            expected_columns=expected_columns,
            relation=normalized_relation,
            allowed_fields=frozenset(allowed_fields),
            source_field=change.field.upper(),
            destination_field=destination_field,
            current_type=current_type,
            target_type=target_type,
        )
        return query

    queries = [
        registered_query(
            code="schema_probe",
            sql=_schema_probe_sql(change.field, rendered_relation),
            expected_columns=(change.field.upper(),),
        )
    ]

    if change.operation is ChangeOperation.RENAME:
        assert change.new_field is not None
        queries.append(
            registered_query(
                code="rename_projection",
                sql=_rename_sql(change.field, change.new_field, rendered_relation),
                expected_columns=AGGREGATE_COLUMNS,
            )
        )
    elif change.operation is ChangeOperation.REMOVE:
        queries.append(
            registered_query(
                code="remove_impact",
                sql=_remove_sql(change.field, rendered_relation),
                expected_columns=AGGREGATE_COLUMNS,
            )
        )
    elif change.operation is ChangeOperation.TYPE_CHANGE:
        assert current_type is not None
        assert target_type is not None
        queries.append(
            registered_query(
                code="type_conversion",
                sql=_type_change_sql(
                    change.field,
                    current_type,
                    target_type,
                    rendered_relation,
                ),
                expected_columns=TYPE_AGGREGATE_COLUMNS,
            )
        )
    else:  # pragma: no cover - Pydantic constrains the operation enum.
        raise UnsafeWarehouseQuery("Change operation is unsupported")

    for query in queries:
        validate_read_only_query(query, normalized_relation, allowed_fields)

    return WarehouseValidationPlan(
        relation=normalized_relation,
        relation_fingerprint=fingerprint_relation(normalized_relation),
        queries=tuple(queries),
    )


def _parse_single_select(sql: str) -> exp.Select:
    if ";" in sql or any(marker in sql for marker in COMMENT_MARKERS):
        raise UnsafeWarehouseQuery("Comments and statement delimiters are forbidden")
    try:
        expressions = parse(sql, read="snowflake")
    except ParseError as exc:
        raise UnsafeWarehouseQuery("Query does not parse as Snowflake SQL") from exc
    if len(expressions) != 1 or not isinstance(expressions[0], exp.Select):
        raise UnsafeWarehouseQuery("Query must be exactly one SELECT statement")
    return expressions[0]


def _physical_tables(
    expression: exp.Select,
    normalized_relation: str,
) -> None:
    cte_names = {cte.alias.upper() for cte in expression.find_all(exp.CTE) if cte.alias}
    physical_count = 0
    for table in expression.find_all(exp.Table):
        if not table.db and not table.catalog and table.name.upper() in cte_names:
            continue
        physical_count += 1
        table_relation = ".".join(
            part.upper() for part in (table.catalog, table.db, table.name) if part
        )
        if table_relation != normalized_relation:
            raise UnsafeWarehouseQuery("Query references an unallowlisted relation")
    if physical_count != 1:
        raise UnsafeWarehouseQuery("Query must reference one allowlisted relation")


def validate_read_only_query(
    query: WarehouseQuery,
    relation: str,
    allowed_fields: set[str],
) -> None:
    """Fail closed unless a query is one exact generated read-only statement."""

    contract = _QUERY_CONTRACTS.get(id(query))
    if contract is None or contract.reference() is not query:
        raise UnsafeWarehouseQuery("Query identity was not registered by the builder")

    normalized_relation = _normalize_relation(relation)
    normalized_fields = {field.upper() for field in allowed_fields}
    if not normalized_fields:
        raise UnsafeWarehouseQuery("At least one allowlisted field is required")
    for field in allowed_fields:
        quote_identifier(field)
    if (
        query.code != contract.code
        or query.sql != contract.sql
        or query.expected_columns != contract.expected_columns
        or normalized_relation != contract.relation
        or frozenset(normalized_fields) != contract.allowed_fields
    ):
        raise UnsafeWarehouseQuery("Query does not match its registered contract")
    expected_semantic_fields = {contract.source_field}
    if contract.destination_field is not None:
        expected_semantic_fields.add(contract.destination_field)
    if contract.allowed_fields != frozenset(expected_semantic_fields):
        raise UnsafeWarehouseQuery("Registered field semantics are inconsistent")
    trusted_sql = _trusted_contract_sql(contract)
    trusted_columns = _trusted_contract_columns(contract)
    if contract.sql != trusted_sql or contract.expected_columns != trusted_columns:
        raise UnsafeWarehouseQuery("Registered query contract is inconsistent")

    expression = _parse_single_select(query.sql)
    if (
        expression.find(exp.Join) is not None
        or expression.find(exp.Subquery) is not None
    ):
        raise UnsafeWarehouseQuery("Joins and subqueries are forbidden")

    _physical_tables(expression, normalized_relation)
    for column in expression.find_all(exp.Column):
        if column.table or column.db or column.catalog:
            raise UnsafeWarehouseQuery("Qualified field references are forbidden")
        if column.name.upper() not in normalized_fields:
            raise UnsafeWarehouseQuery("Query references an unallowlisted field")
        identifier = column.this
        if not isinstance(identifier, exp.Identifier) or not identifier.args.get(
            "quoted"
        ):
            raise UnsafeWarehouseQuery("Field references must be quoted")

    actual_columns = tuple(name.upper() for name in expression.named_selects)
    expected_columns = tuple(name.upper() for name in query.expected_columns)
    if actual_columns != expected_columns:
        raise UnsafeWarehouseQuery("Query result columns do not match the contract")
    if len(expected_columns) != len(set(expected_columns)) or any(
        SIMPLE_IDENTIFIER.fullmatch(name) is None for name in expected_columns
    ):
        raise UnsafeWarehouseQuery("Query result columns are invalid")
    expected = _parse_single_select(trusted_sql)
    rendered = expression.sql(dialect="snowflake")
    expected_rendered = expected.sql(dialect="snowflake")
    if rendered != expected_rendered:
        raise UnsafeWarehouseQuery("Query differs from the generated contract")

    reparsed = _parse_single_select(rendered)
    if reparsed.sql(dialect="snowflake") != rendered:
        raise UnsafeWarehouseQuery("Query is not stable under Snowflake parsing")
