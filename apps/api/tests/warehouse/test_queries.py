from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from hashlib import sha256

import pytest
from sqlglot import exp, parse_one

from changesafe.domain import (
    ChangeOperation,
    ChangeRequest,
    ContextBundle,
    ContextMode,
    ContextProvenance,
    SchemaField,
)
from changesafe.warehouse.queries import (
    UnsafeWarehouseQuery,
    UnsupportedWarehouseConversion,
    WarehouseQuery,
    build_validation_plan,
    fingerprint_relation,
    validate_read_only_query,
)

RELATION = "SAFE_DB.SAFE_SCHEMA.ORDER_DETAILS"
TARGET = "urn:li:dataset:warehouse-query-tests"


def request_for(
    operation: ChangeOperation,
    *,
    old_type: str = "TEXT",
    new_type: str = "VARCHAR(16)",
) -> ChangeRequest:
    values: dict[str, object] = {
        "asset_urn": TARGET,
        "operation": operation,
        "field": "cust_email",
        "source_commit": "query-test",
        "requested_by": "query-test",
    }
    if operation is ChangeOperation.RENAME:
        values["new_field"] = "customer_email"
    elif operation is ChangeOperation.TYPE_CHANGE:
        values.update({"old_type": old_type, "new_type": new_type})
    return ChangeRequest.model_validate(values)


def golden_context(
    field: str = "cust_email",
    *,
    field_type: str = "TEXT",
    schema_type: str | None = None,
    extra_fields: tuple[SchemaField, ...] = (),
) -> ContextBundle:
    return ContextBundle(
        target_urn=TARGET,
        target_name="order_details",
        target_domain="Analytics",
        field=field,
        field_type=field_type,
        schema_fields=[
            SchemaField(
                name="cust_email",
                data_type=schema_type or field_type,
                nullable=True,
            ),
            SchemaField(name="order_id", data_type="NUMBER", nullable=False),
            *extra_fields,
        ],
        provenance=ContextProvenance(
            mode=ContextMode.LIVE,
            retrieved_at=datetime(2026, 8, 9, tzinfo=UTC),
            adapter_version="query-test/1",
        ),
    )


@pytest.mark.parametrize("operation", list(ChangeOperation))
def test_plan_contains_only_single_read_only_statements(
    operation: ChangeOperation,
) -> None:
    change = request_for(operation)
    plan = build_validation_plan(change, golden_context(change.field), RELATION)

    assert plan.queries
    for query in plan.queries:
        allowed = {change.field}
        if change.new_field is not None:
            allowed.add(change.new_field)
        validate_read_only_query(query, RELATION, allowed)
        assert ";" not in query.sql
        assert "--" not in query.sql
        assert "/*" not in query.sql


@pytest.mark.parametrize(
    "sql",
    [
        "select * from SAFE_DB.SAFE_SCHEMA.ORDER_DETAILS; drop table x",
        "delete from SAFE_DB.SAFE_SCHEMA.ORDER_DETAILS",
        "select cust_email from OTHER_DB.X.Y",
        "select secret_column from SAFE_DB.SAFE_SCHEMA.ORDER_DETAILS",
        "call system$wait(10)",
        "select cust_email from SAFE_DB.SAFE_SCHEMA.ORDER_DETAILS -- trusted",
        "select * from SAFE_DB.SAFE_SCHEMA.ORDER_DETAILS",
        "select current_user() from SAFE_DB.SAFE_SCHEMA.ORDER_DETAILS",
        (
            "select cust_email from SAFE_DB.SAFE_SCHEMA.ORDER_DETAILS "
            "where cust_email in "
            "(select cust_email from SAFE_DB.SAFE_SCHEMA.ORDER_DETAILS)"
        ),
        (
            "select cust_email from SAFE_DB.SAFE_SCHEMA.ORDER_DETAILS a "
            "join SAFE_DB.SAFE_SCHEMA.ORDER_DETAILS b "
            "on a.cust_email = b.cust_email"
        ),
    ],
)
def test_query_guard_rejects_unsafe_or_unallowlisted_sql(sql: str) -> None:
    with pytest.raises(UnsafeWarehouseQuery):
        validate_read_only_query(
            WarehouseQuery(code="probe", sql=sql, expected_columns=()),
            RELATION,
            {"cust_email"},
        )


def test_rename_plan_has_exact_projection_and_result_aliases() -> None:
    change = request_for(ChangeOperation.RENAME)

    plan = build_validation_plan(change, golden_context(), RELATION)

    assert plan.queries == (
        WarehouseQuery(
            code="schema_probe",
            sql=(
                'SELECT "CUST_EMAIL"\n'
                'FROM "SAFE_DB"."SAFE_SCHEMA"."ORDER_DETAILS"\n'
                "WHERE 1 = 0"
            ),
            expected_columns=("CUST_EMAIL",),
        ),
        WarehouseQuery(
            code="rename_projection",
            sql=(
                "WITH projected AS (\n"
                '  SELECT "CUST_EMAIL" AS "CUSTOMER_EMAIL"\n'
                '  FROM "SAFE_DB"."SAFE_SCHEMA"."ORDER_DETAILS"\n'
                ")\n"
                "SELECT COUNT(*) AS rows_evaluated,\n"
                '       COUNT("CUSTOMER_EMAIL") AS populated_row_count\n'
                "FROM projected"
            ),
            expected_columns=("ROWS_EVALUATED", "POPULATED_ROW_COUNT"),
        ),
    )


def test_remove_plan_uses_zero_row_safe_count_aggregates() -> None:
    plan = build_validation_plan(
        request_for(ChangeOperation.REMOVE), golden_context(), RELATION
    )
    evidence = plan.queries[1]

    assert evidence.code == "remove_impact"
    assert evidence.sql == (
        "SELECT COUNT(*) AS rows_evaluated,\n"
        '       COUNT("CUST_EMAIL") AS populated_row_count\n'
        'FROM "SAFE_DB"."SAFE_SCHEMA"."ORDER_DETAILS"'
    )
    assert evidence.expected_columns == ("ROWS_EVALUATED", "POPULATED_ROW_COUNT")
    assert "/" not in evidence.sql


@pytest.mark.parametrize(
    ("old_type", "new_type", "rendered_old", "rendered_new"),
    [
        ("NUMBER(18,2)", "NUMBER(10,1)", "NUMBER(18, 2)", "NUMBER(10, 1)"),
        ("TEXT", "VARCHAR(16)", "VARCHAR(16777216)", "VARCHAR(16)"),
    ],
)
def test_type_change_plan_uses_exact_canonical_narrowing_types(
    old_type: str, new_type: str, rendered_old: str, rendered_new: str
) -> None:
    change = request_for(
        ChangeOperation.TYPE_CHANGE, old_type=old_type, new_type=new_type
    )
    plan = build_validation_plan(
        change,
        golden_context(field_type=old_type, schema_type=old_type),
        RELATION,
    )
    evidence = plan.queries[1]

    assert evidence.code == "type_conversion"
    assert evidence.expected_columns == (
        "ROWS_EVALUATED",
        "POPULATED_ROW_COUNT",
        "UNSAFE_ROW_COUNT",
    )
    parsed = parse_one(evidence.sql, read="snowflake")
    rendered_types = {
        node.args["to"].sql(dialect="snowflake")
        for node in parsed.find_all(exp.TryCast)
    }
    # sqlglot's Snowflake AST canonicalizes NUMBER to its DECIMAL synonym.
    expected_types = {
        parse_one(f"SELECT TRY_CAST(1 AS {value})", read="snowflake")
        .find(exp.DataType)
        .sql(dialect="snowflake")
        for value in (rendered_old, rendered_new)
    }
    assert rendered_types == expected_types
    assert "COUNT_IF" in evidence.sql
    assert "/" not in evidence.sql


def test_type_change_plan_renders_exact_round_trip_predicate() -> None:
    change = request_for(
        ChangeOperation.TYPE_CHANGE,
        old_type="NUMBER(18,2)",
        new_type="NUMBER(10,1)",
    )

    evidence = build_validation_plan(
        change,
        golden_context(field_type="NUMBER(18,2)"),
        RELATION,
    ).queries[1]

    assert evidence.sql == (
        "SELECT COUNT(*) AS rows_evaluated,\n"
        '       COUNT("CUST_EMAIL") AS populated_row_count,\n'
        "       COUNT_IF(\n"
        '         "CUST_EMAIL" IS NOT NULL AND (\n'
        '           TRY_CAST(TO_VARCHAR("CUST_EMAIL") AS NUMBER(10, 1)) '
        "IS NULL OR\n"
        "           TRY_CAST(\n"
        '             TO_VARCHAR(TRY_CAST(TO_VARCHAR("CUST_EMAIL") '
        "AS NUMBER(10, 1))) AS NUMBER(18, 2)\n"
        '           ) IS DISTINCT FROM "CUST_EMAIL"\n'
        "         )\n"
        "       ) AS unsafe_row_count\n"
        'FROM "SAFE_DB"."SAFE_SCHEMA"."ORDER_DETAILS"'
    )


def test_number_conversion_wraps_numeric_sources_for_try_cast() -> None:
    change = request_for(
        ChangeOperation.TYPE_CHANGE,
        old_type="NUMBER(18,2)",
        new_type="NUMBER(10,1)",
    )

    sql = (
        build_validation_plan(
            change,
            golden_context(field_type="NUMBER(18,2)"),
            RELATION,
        )
        .queries[1]
        .sql
    )

    assert 'TRY_CAST(TO_VARCHAR("CUST_EMAIL") AS NUMBER(10, 1))' in sql
    assert (
        'TO_VARCHAR(TRY_CAST(TO_VARCHAR("CUST_EMAIL") AS NUMBER(10, 1))) '
        "AS NUMBER(18, 2)"
    ) in sql


@pytest.mark.parametrize(
    ("old_type", "new_type"),
    [
        ("BINARY", "BINARY(8)"),
        ("VARIANT", "VARCHAR(16)"),
        ("VARCHAR(16)", "VARIANT"),
        ("GEOGRAPHY", "VARCHAR(16)"),
        ("VARCHAR(16)", "GEOMETRY"),
        ("UUID", "VARCHAR(16)"),
        ("VARCHAR(16)", "DECFLOAT"),
    ],
)
def test_type_change_rejects_undocumented_try_cast_families(
    old_type: str, new_type: str
) -> None:
    change = request_for(
        ChangeOperation.TYPE_CHANGE,
        old_type=old_type,
        new_type=new_type,
    )

    with pytest.raises(UnsupportedWarehouseConversion):
        build_validation_plan(
            change,
            golden_context(field_type=old_type),
            RELATION,
        )


@pytest.mark.parametrize(
    ("old_type", "new_type"),
    [
        ("BOOLEAN", "VARCHAR(16)"),
        ("DATE", "TIMESTAMP_NTZ(9)"),
        ("TIME(9)", "VARCHAR(16)"),
        ("TIMESTAMP_LTZ(9)", "TIMESTAMP_TZ(9)"),
        ("FLOAT", "NUMBER(10,2)"),
    ],
)
def test_type_change_accepts_documented_try_cast_families(
    old_type: str, new_type: str
) -> None:
    change = request_for(
        ChangeOperation.TYPE_CHANGE,
        old_type=old_type,
        new_type=new_type,
    )

    plan = build_validation_plan(
        change,
        golden_context(field_type=old_type),
        RELATION,
    )

    assert plan.queries[1].code == "type_conversion"


def test_plan_models_are_immutable_and_relation_is_normalized() -> None:
    plan = build_validation_plan(
        request_for(ChangeOperation.REMOVE),
        golden_context(),
        "safe_db.safe_schema.order_details",
    )

    assert plan.relation == RELATION
    assert plan.relation_fingerprint == sha256(RELATION.encode()).hexdigest()
    assert fingerprint_relation("safe_db.safe_schema.order_details") == (
        fingerprint_relation(RELATION)
    )
    with pytest.raises(FrozenInstanceError):
        plan.relation = "OTHER_DB.X.Y"
    with pytest.raises(FrozenInstanceError):
        plan.queries[0].sql = "SELECT 1"


@pytest.mark.parametrize(
    "relation",
    [
        "SAFE_DB.SAFE_SCHEMA",
        "SAFE_DB.SAFE_SCHEMA.ORDER_DETAILS.EXTRA",
        "SAFE_DB.SAFE_SCHEMA.ORDER_DETAILS;DROP_TABLE_X",
        'SAFE_DB.SAFE_SCHEMA."ORDER_DETAILS"',
        "SAFE_DB.SAFE-SCHEMA.ORDER_DETAILS",
        "SAFE_DB..ORDER_DETAILS",
    ],
)
def test_relation_map_injection_is_rejected(relation: str) -> None:
    with pytest.raises(UnsafeWarehouseQuery):
        fingerprint_relation(relation)
    with pytest.raises(UnsafeWarehouseQuery):
        build_validation_plan(
            request_for(ChangeOperation.REMOVE), golden_context(), relation
        )


def test_rename_rejects_case_insensitive_destination_collision() -> None:
    change = request_for(ChangeOperation.RENAME)
    context = golden_context(
        extra_fields=(
            SchemaField(name="CUSTOMER_EMAIL", data_type="TEXT", nullable=True),
        )
    )

    with pytest.raises(UnsafeWarehouseQuery, match="destination"):
        build_validation_plan(change, context, RELATION)


def test_rename_rejects_destination_that_only_differs_by_case() -> None:
    change = request_for(ChangeOperation.RENAME).model_copy(
        update={"new_field": "CUST_EMAIL"}
    )

    with pytest.raises(UnsafeWarehouseQuery, match="differ"):
        build_validation_plan(change, golden_context(), RELATION)


@pytest.mark.parametrize(
    "context",
    [
        golden_context(field="other_field"),
        golden_context().model_copy(update={"target_urn": "urn:li:dataset:other"}),
    ],
)
def test_plan_rejects_mismatched_request_context_identity(
    context: ContextBundle,
) -> None:
    with pytest.raises(UnsafeWarehouseQuery, match="context"):
        build_validation_plan(request_for(ChangeOperation.REMOVE), context, RELATION)


def test_plan_rejects_missing_or_ambiguous_source_schema_field() -> None:
    context = golden_context().model_copy(
        update={
            "schema_fields": [
                SchemaField(name="order_id", data_type="NUMBER", nullable=False)
            ]
        }
    )

    with pytest.raises(UnsafeWarehouseQuery, match="schema"):
        build_validation_plan(request_for(ChangeOperation.REMOVE), context, RELATION)


def test_plan_rejects_context_and_schema_type_mismatch() -> None:
    with pytest.raises(UnsafeWarehouseQuery, match="schema type"):
        build_validation_plan(
            request_for(ChangeOperation.REMOVE),
            golden_context(field_type="TEXT", schema_type="NUMBER"),
            RELATION,
        )


def test_type_change_rejects_request_old_type_that_differs_from_context() -> None:
    change = request_for(
        ChangeOperation.TYPE_CHANGE,
        old_type="NUMBER(12,2)",
        new_type="NUMBER(10,1)",
    )

    with pytest.raises(UnsafeWarehouseQuery, match="current type"):
        build_validation_plan(change, golden_context(), RELATION)


def test_guard_rejects_mutations_of_a_generated_query() -> None:
    query = build_validation_plan(
        request_for(ChangeOperation.REMOVE), golden_context(), RELATION
    ).queries[1]
    mutations = [
        query.sql.replace("ORDER_DETAILS", "CUSTOMERS"),
        query.sql.replace("CUST_EMAIL", "SECRET_COLUMN"),
        f"{query.sql}; SELECT 1",
        f"{query.sql} -- trusted",
        query.sql.replace('COUNT("CUST_EMAIL")', 'MAX("CUST_EMAIL")'),
        query.sql.replace('COUNT("CUST_EMAIL")', "COUNT(*)"),
        query.sql.replace(
            'FROM "SAFE_DB"."SAFE_SCHEMA"."ORDER_DETAILS"',
            'FROM (SELECT "CUST_EMAIL" FROM "SAFE_DB"."SAFE_SCHEMA"."ORDER_DETAILS")',
        ),
        query.sql.replace(
            'FROM "SAFE_DB"."SAFE_SCHEMA"."ORDER_DETAILS"',
            'FROM "SAFE_DB"."SAFE_SCHEMA"."ORDER_DETAILS" a '
            'JOIN "SAFE_DB"."SAFE_SCHEMA"."ORDER_DETAILS" b '
            'ON a."CUST_EMAIL" = b."CUST_EMAIL"',
        ),
    ]

    for mutated_sql in mutations:
        with pytest.raises(UnsafeWarehouseQuery):
            validate_read_only_query(
                WarehouseQuery(
                    code=query.code,
                    sql=mutated_sql,
                    expected_columns=query.expected_columns,
                ),
                RELATION,
                {"cust_email"},
            )


def test_guard_rejects_noncanonical_type_token_mutation() -> None:
    query = build_validation_plan(
        request_for(ChangeOperation.TYPE_CHANGE), golden_context(), RELATION
    ).queries[1]
    mutated = query.sql.replace("VARCHAR(16)", "STRING")

    mutated_query = WarehouseQuery(
        code=query.code,
        sql=mutated,
        expected_columns=query.expected_columns,
    )
    with pytest.raises(UnsafeWarehouseQuery):
        validate_read_only_query(mutated_query, RELATION, {"cust_email"})
    assert mutated_query.sql != query.sql


def test_guard_rejects_canonical_type_parameter_mutation() -> None:
    query = build_validation_plan(
        request_for(ChangeOperation.TYPE_CHANGE), golden_context(), RELATION
    ).queries[1]
    mutated = query.sql.replace("VARCHAR(16)", "VARCHAR(8)")

    with pytest.raises(UnsafeWarehouseQuery):
        validate_read_only_query(
            WarehouseQuery(
                code=query.code,
                sql=mutated,
                expected_columns=query.expected_columns,
            ),
            RELATION,
            {"cust_email"},
        )


def test_guard_rejects_swapped_rename_source_and_destination() -> None:
    query = build_validation_plan(
        request_for(ChangeOperation.RENAME), golden_context(), RELATION
    ).queries[1]
    mutated = (
        query.sql.replace("CUST_EMAIL", "TEMP_FIELD")
        .replace("CUSTOMER_EMAIL", "CUST_EMAIL")
        .replace("TEMP_FIELD", "CUSTOMER_EMAIL")
    )

    with pytest.raises(UnsafeWarehouseQuery):
        validate_read_only_query(
            WarehouseQuery(
                code=query.code,
                sql=mutated,
                expected_columns=query.expected_columns,
            ),
            RELATION,
            {"cust_email", "customer_email"},
        )


def test_guard_binds_query_result_aliases() -> None:
    query = build_validation_plan(
        request_for(ChangeOperation.REMOVE), golden_context(), RELATION
    ).queries[1]
    mutated = query.sql.replace("rows_evaluated", "rows_seen")

    with pytest.raises(UnsafeWarehouseQuery, match="columns"):
        validate_read_only_query(
            WarehouseQuery(
                code=query.code,
                sql=mutated,
                expected_columns=query.expected_columns,
            ),
            RELATION,
            {"cust_email"},
        )


def test_rename_ast_contains_source_and_destination_identifiers() -> None:
    query = build_validation_plan(
        request_for(ChangeOperation.RENAME), golden_context(), RELATION
    ).queries[1]

    identifiers = {
        identifier.name.upper()
        for identifier in parse_one(query.sql, read="snowflake").find_all(
            exp.Identifier
        )
    }
    assert {"CUST_EMAIL", "CUSTOMER_EMAIL"} <= identifiers
