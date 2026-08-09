"""Fail-closed validation of generated migration artifacts."""

from __future__ import annotations

import json
import re
from pathlib import PurePosixPath
from typing import Any, cast

import sqlglot
import yaml
from sqlglot import exp

from changesafe.domain import (
    ArtifactBundle,
    ChangeOperation,
    ChangeRequest,
    ContextBundle,
    ValidationCheck,
    ValidationReport,
)
from changesafe.generation.templates import (
    MANIFEST,
    PR_BODY,
    ROLLBACK,
    expected_artifact_paths,
    generate_artifacts,
)
from changesafe.risk import score_change
from changesafe.sql_types import canonical_sql_type, type_change_kind

REF_PATTERN = re.compile(r"\{\{\s*ref\(['\"]([^'\"]+)['\"]\)\s*\}\}")
CONFIG_PATTERN = re.compile(r"^\s*\{\{\s*config\(.*?\)\s*\}\}\s*$", re.MULTILINE)
SQL_COMMENT_PATTERN = re.compile(r"--[^\r\n]*|/\*.*?\*/", re.DOTALL)
NUMBERED_STEP_PATTERN = re.compile(r"(?m)^(\d+)\.\s+(.+)$")
SAFE_MODEL_CONFIG = "{{ config(materialized='table', contract={'enforced': true}) }}"


def _check(code: str, label: str, passed: bool, detail: str) -> ValidationCheck:
    return ValidationCheck(code=code, label=label, passed=passed, detail=detail)


def _sql_without_comments(content: str) -> str:
    return SQL_COMMENT_PATTERN.sub("", content)


def _dbt_refs(content: str) -> set[str]:
    normalized, refs = _replace_dbt_refs_with_sentinels(content)
    del normalized
    return set(refs.values())


def _live_jinja_directives(content: str) -> list[str]:
    """Return interpolation directives that execute outside SQL comments/strings."""
    source = _sql_without_comments(content)
    directives: list[str] = []
    cursor = 0
    while cursor < len(source):
        character = source[cursor]
        if character in {"'", '"'}:
            quote = character
            cursor += 1
            while cursor < len(source):
                if source[cursor] == quote:
                    if cursor + 1 < len(source) and source[cursor + 1] == quote:
                        cursor += 2
                        continue
                    cursor += 1
                    break
                cursor += 1
            continue
        if source.startswith("{{", cursor):
            end = source.find("}}", cursor + 2)
            if end < 0:
                return ["<unterminated-jinja>"]
            directives.append(source[cursor : end + 2].strip())
            cursor = end + 2
            continue
        cursor += 1
    return directives


def _replace_dbt_refs_with_sentinels(content: str) -> tuple[str, dict[str, str]]:
    source = CONFIG_PATTERN.sub("", _sql_without_comments(content))
    chunks: list[str] = []
    refs: dict[str, str] = {}
    index = 0
    cursor = 0
    while cursor < len(source):
        character = source[cursor]
        if character in {"'", '"'}:
            quote = character
            end = cursor + 1
            while end < len(source):
                if source[end] == quote:
                    if end + 1 < len(source) and source[end + 1] == quote:
                        end += 2
                        continue
                    end += 1
                    break
                end += 1
            chunks.append(source[cursor:end])
            cursor = end
            continue
        match = REF_PATTERN.match(source, cursor)
        if match is None:
            chunks.append(character)
            cursor += 1
            continue
        sentinel = f"changesafe_ref_{index}"
        refs[sentinel] = match.group(1)
        chunks.append(sentinel)
        index += 1
        cursor = match.end()
    return "".join(chunks), refs


def _normalized_sql(content: str) -> str:
    without_config = CONFIG_PATTERN.sub("", _sql_without_comments(content))
    return REF_PATTERN.sub(lambda match: match.group(1), without_config)


def _sentinel_ref_tables(content: str) -> tuple[list[exp.Table], dict[str, str]]:
    normalized, refs = _replace_dbt_refs_with_sentinels(content)
    try:
        expressions = cast(
            list[exp.Expression], sqlglot.parse(normalized, read="snowflake")
        )
    except sqlglot.errors.ParseError:
        return [], refs
    tables = [
        table
        for expression in expressions
        for table in expression.find_all(exp.Table)
        if table.name
    ]
    return tables, refs


def _parsed_sql(
    bundle: ArtifactBundle,
) -> tuple[dict[str, list[exp.Expression]], list[str]]:
    parsed: dict[str, list[exp.Expression]] = {}
    errors: list[str] = []
    for path, artifact in bundle.files.items():
        if not path.endswith(".sql"):
            continue
        try:
            parsed[path] = cast(
                list[exp.Expression],
                sqlglot.parse(_normalized_sql(artifact.content), read="snowflake"),
            )
        except sqlglot.errors.ParseError as exc:
            errors.append(f"{path}: {exc.errors[0].get('description', 'parse error')}")
    return parsed, errors


def _yaml_columns(
    content: str, model_name: str
) -> tuple[list[str], dict[str, set[str]], dict[str, str], bool]:
    try:
        document = yaml.safe_load(content)
    except yaml.YAMLError:
        return [], {}, {}, False
    if not isinstance(document, dict) or document.get("version") != 2:
        return [], {}, {}, False
    models = document.get("models")
    if not isinstance(models, list):
        return [], {}, {}, False
    model = next(
        (
            item
            for item in models
            if isinstance(item, dict) and item.get("name") == model_name
        ),
        None,
    )
    if not isinstance(model, dict):
        return [], {}, {}, False
    columns = model.get("columns")
    if not isinstance(columns, list):
        return [], {}, {}, False
    names: list[str] = []
    tests: dict[str, set[str]] = {}
    data_types: dict[str, str] = {}
    for column in columns:
        if not isinstance(column, dict) or not column.get("name"):
            continue
        name = str(column["name"])
        key = name.casefold()
        names.append(name)
        raw_tests = column.get("tests", [])
        if not isinstance(raw_tests, list):
            raw_tests = []
        tests[key] = {
            str(item) if isinstance(item, str) else str(next(iter(item), ""))
            for item in raw_tests
            if isinstance(item, (str, dict))
        }
        if column.get("data_type") is not None:
            data_types[key] = str(column["data_type"])
    return names, tests, data_types, True


def _preferred_field(change: ChangeRequest) -> str | None:
    if change.operation is ChangeOperation.RENAME:
        return change.new_field
    if change.operation is ChangeOperation.TYPE_CHANGE:
        return f"{change.field}__new_type"
    return None


def _types_match(left: str, right: str) -> bool:
    try:
        return canonical_sql_type(left) == canonical_sql_type(right)
    except ValueError:
        return False


def _context_alignment(
    change: ChangeRequest, context: ContextBundle
) -> tuple[bool, str, Any | None]:
    matches = [
        field
        for field in context.schema_fields
        if field.name.casefold() == change.field.casefold()
    ]
    if len(matches) != 1:
        return (
            False,
            "The changed field is absent or ambiguous in DataHub schema.",
            None,
        )
    changed = matches[0]
    try:
        if canonical_sql_type(changed.data_type) != canonical_sql_type(
            context.field_type
        ):
            return (
                False,
                "DataHub field type conflicts with the complete schema.",
                changed,
            )

        preferred = _preferred_field(change)
        existing = {field.name.casefold() for field in context.schema_fields}
        if preferred is not None and preferred.casefold() in existing:
            return (
                False,
                "The preferred output name already exists in DataHub.",
                changed,
            )

        if change.operation is ChangeOperation.TYPE_CHANGE:
            assert change.new_type is not None
            if (
                change.old_type is not None
                and canonical_sql_type(change.old_type)
                != canonical_sql_type(context.field_type)
            ):
                return False, "old_type disagrees with DataHub metadata.", changed
            if type_change_kind(context.field_type, change.new_type) == "no_op":
                return False, "new_type is a no-op for DataHub metadata.", changed
    except ValueError as exc:
        return False, f"Invalid or unsupported Snowflake type: {exc}.", changed
    return True, "The request agrees with complete DataHub schema metadata.", changed


def _select_output_names(expressions: list[exp.Expression]) -> list[str]:
    select = next(
        (
            expression
            for expression in expressions
            if isinstance(expression, exp.Select)
        ),
        None,
    )
    if select is None:
        return []
    return [projection.alias_or_name for projection in select.expressions]


def _manifest_matches(
    bundle: ArtifactBundle, change: ChangeRequest, context: ContextBundle
) -> bool:
    try:
        manifest = json.loads(bundle.files[MANIFEST].content)
    except (KeyError, json.JSONDecodeError):
        return False
    try:
        expected_risk = score_change(change, context).model_dump(mode="json")
    except ValueError:
        return False
    expected_context = {
        "mode": context.provenance.mode.value,
        "snapshot_hash": context.provenance.snapshot_hash,
        "target_urn": context.target_urn,
    }
    if (
        set(manifest)
        != {"version", "change", "context", "risk", "deprecation_status", "files"}
        or manifest.get("version") != 1
        or manifest.get("change") != change.model_dump(mode="json")
        or manifest.get("context") != expected_context
        or manifest.get("risk") != expected_risk
        or manifest.get("deprecation_status") != "phase_one"
    ):
        return False
    declared = manifest.get("files")
    if not isinstance(declared, dict):
        return False
    expected_paths = set(bundle.files) - {MANIFEST}
    if set(declared) != expected_paths:
        return False
    hashes_match = all(
        bundle.files[path].sha256 == digest for path, digest in declared.items()
    )
    try:
        expected_bundle = generate_artifacts(
            change, context, score_change(change, context)
        )
    except ValueError:
        return False
    expected_hashes = {
        path: artifact.sha256 for path, artifact in expected_bundle.files.items()
    }
    actual_hashes = {path: artifact.sha256 for path, artifact in bundle.files.items()}
    return (
        hashes_match
        and bundle.manifest_hash == bundle.files[MANIFEST].sha256
        and actual_hashes == expected_hashes
        and bundle.manifest_hash == expected_bundle.manifest_hash
    )


def _column_is(expression: exp.Expression, name: str) -> bool:
    return (
        isinstance(expression, exp.Column)
        and expression.name.casefold() == name.casefold()
    )


def _unqualified_column_is(expression: exp.Expression, name: str) -> bool:
    return (
        isinstance(expression, exp.Column)
        and expression.name.casefold() == name.casefold()
        and not expression.table
    )


def _model_select_contract_valid(
    expressions: list[exp.Expression],
    change: ChangeRequest,
    context: ContextBundle,
) -> bool:
    if len(expressions) != 1 or not isinstance(expressions[0], exp.Select):
        return False
    select = expressions[0]
    if any(
        value is not None
        for name, value in select.args.items()
        if name not in {"expressions", "from_"}
    ):
        return False
    projections = list(select.expressions)
    preferred = _preferred_field(change)
    expected_count = len(context.schema_fields) + (1 if preferred else 0)
    if len(projections) != expected_count:
        return False
    position = 0
    for schema_field in context.schema_fields:
        projection = projections[position]
        if not _unqualified_column_is(projection, schema_field.name):
            return False
        position += 1
        if schema_field.name.casefold() != change.field.casefold() or preferred is None:
            continue
        preferred_projection = projections[position]
        if (
            not isinstance(preferred_projection, exp.Alias)
            or preferred_projection.alias_or_name.casefold() != preferred.casefold()
        ):
            return False
        if change.operation is ChangeOperation.RENAME:
            if not _unqualified_column_is(preferred_projection.this, change.field):
                return False
        else:
            if not isinstance(preferred_projection.this, exp.Cast):
                return False
            if not _unqualified_column_is(
                preferred_projection.this.this, change.field
            ):
                return False
            assert change.new_type is not None
            try:
                if canonical_sql_type(
                    preferred_projection.this.to.sql(dialect="snowflake")
                ) != canonical_sql_type(change.new_type):
                    return False
            except ValueError:
                return False
        position += 1
    return True


def _phase_one_projection_valid(
    expressions: list[exp.Expression], change: ChangeRequest, context: ContextBundle
) -> bool:
    return _model_select_contract_valid(expressions, change, context)


def _compatibility_test_valid(
    expressions: list[exp.Expression],
    change: ChangeRequest,
    shim_model: str,
    content: str,
) -> bool:
    if _live_jinja_directives(content) != [f"{{{{ ref('{shim_model}') }}}}"]:
        return False
    if len(expressions) != 1 or not isinstance(expressions[0], exp.Select):
        return False
    select = expressions[0]
    if any(
        value is not None
        for name, value in select.args.items()
        if name not in {"expressions", "from_", "where"}
    ):
        return False
    if len(list(select.find_all(exp.Select))) != 1:
        return False
    if len(select.expressions) != 1 or not _column_is(
        select.expressions[0], change.field
    ):
        return False
    tables = list(select.find_all(exp.Table))
    if len(tables) != 1 or tables[0].name.casefold() != shim_model.casefold():
        return False
    if tables[0].args.get("alias") is not None or any(
        column.table for column in select.find_all(exp.Column)
    ):
        return False
    where = select.args.get("where")
    if not isinstance(where, exp.Where):
        return False
    if change.operation is ChangeOperation.REMOVE:
        return isinstance(where.this, exp.Boolean) and where.this.this is False

    preferred = _preferred_field(change)
    if preferred is None or not isinstance(where.this, exp.NullSafeNEQ):
        return False
    if not _column_is(where.this.expression, preferred):
        return False
    if change.operation is ChangeOperation.RENAME:
        return _column_is(where.this.this, change.field)
    if not isinstance(where.this.this, exp.Cast):
        return False
    if not _column_is(where.this.this.this, change.field):
        return False
    assert change.new_type is not None
    try:
        return canonical_sql_type(
            where.this.this.to.sql(dialect="snowflake")
        ) == canonical_sql_type(change.new_type)
    except ValueError:
        return False


def _yaml_structure_matches(
    content: str, model_name: str, change: ChangeRequest, context: ContextBundle
) -> bool:
    try:
        document = yaml.safe_load(content)
    except yaml.YAMLError:
        return False
    if not isinstance(document, dict) or set(document) != {"version", "models"}:
        return False
    models = document.get("models")
    if document.get("version") != 2 or not isinstance(models, list) or len(models) != 1:
        return False
    model = models[0]
    if not isinstance(model, dict) or set(model) != {
        "name",
        "description",
        "config",
        "columns",
    }:
        return False
    if (
        model.get("name") != model_name
        or model.get("description")
        != "Phase-one compatibility layer over the governed model."
        or model.get("config") != {"contract": {"enforced": True}}
    ):
        return False
    columns = model.get("columns")
    if not isinstance(columns, list):
        return False
    preferred = _preferred_field(change)
    expected_fields = [
        {
            "name": field.name,
            "data_type": field.data_type,
            "nullable": field.nullable,
        }
        for field in context.schema_fields
    ]
    changed = next(
        (
            field
            for field in expected_fields
            if str(field["name"]).casefold() == change.field.casefold()
        ),
        None,
    )
    if changed is None:
        return False
    if preferred is not None:
        preferred_type = (
            change.new_type
            if change.operation is ChangeOperation.TYPE_CHANGE
            else str(changed["data_type"])
        )
        assert preferred_type is not None
        preferred_field = {
            "name": preferred,
            "data_type": preferred_type,
            "nullable": changed["nullable"],
        }
        index = next(
            index
            for index, field in enumerate(expected_fields)
            if str(field["name"]).casefold() == change.field.casefold()
        )
        expected_fields = [
            *expected_fields[: index + 1],
            preferred_field,
            *expected_fields[index + 1 :],
        ]
    if len(columns) != len(expected_fields):
        return False
    for column, expected in zip(columns, expected_fields, strict=True):
        if not isinstance(column, dict):
            return False
        name = str(expected["name"])
        data_type = str(expected["data_type"])
        nullable = bool(expected["nullable"])
        allowed_keys = {"name", "data_type", "description"}
        if not nullable:
            allowed_keys.add("tests")
        if (
            set(column) - allowed_keys
            or column.get("name") != name
            or column.get("data_type") != data_type
        ):
            return False
        expected_description: str | None = None
        if str(name).casefold() == change.field.casefold():
            expected_description = (
                "Deprecated compatibility field retained during phase one."
            )
        elif preferred is not None and str(name).casefold() == preferred.casefold():
            expected_description = "Preferred field for migrated consumers."
        if expected_description is None:
            if "description" in column:
                return False
        elif column.get("description") != expected_description:
            return False
        if nullable:
            if "tests" in column:
                return False
        elif column.get("tests") != ["not_null"]:
            return False
    return True


def _transition_guidance_valid(
    content: str,
    change: ChangeRequest,
    governed_model: str,
    shim_model: str,
    downstream_count: int,
) -> bool:
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    required = [
        f"The governed base model remains unchanged in phase one: `{governed_model}`.",
        f"ChangeSafe adds compatibility relation `{shim_model}`.",
    ]
    if change.operation is ChangeOperation.REMOVE:
        owner_transition = (
            f"Downstream owners must switch to `{shim_model}` while retaining "
            f"`{change.field}` until phase two."
        )
    else:
        preferred = _preferred_field(change)
        assert preferred is not None
        owner_transition = (
            f"Downstream owners must switch to `{shim_model}` and migrate to "
            f"`{preferred}`."
        )
    required.extend(
        [
            owner_transition,
            (
                f"All {downstream_count} recorded consumers must complete migration "
                f"through `{shim_model}`, the operation-specific compatibility test "
                "must remain green, and the accountable owner must approve phase two."
            ),
        ]
    )
    operational_phrases = ("switch to", "migrate to", "retaining", "phase two")
    has_conflicting_action = any(
        line not in required
        and any(phrase in line.casefold() for phrase in operational_phrases)
        for line in lines
    )
    return not has_conflicting_action and all(
        lines.count(item) == 1 for item in required
    )


def _rollback_instructions_valid(
    content: str,
    change: ChangeRequest,
    governed_model: str,
    shim_model: str,
    model_sql: str,
    model_yaml: str,
    test_path: str,
) -> bool:
    steps = [
        (int(number), action.strip())
        for number, action in NUMBERED_STEP_PATTERN.findall(content)
    ]
    return steps == [
        (1, (
            f"Move downstream consumers from `{shim_model}` back to "
            f"`{governed_model}` before removing generated artifacts."
        )),
        (
            2,
            f"Confirm `{change.field}` remains available to every downstream consumer.",
        ),
        (3, f"Revert `{model_sql}`."),
        (4, f"Revert `{model_yaml}`."),
        (5, f"Remove `{test_path}`."),
        (6, "Run `dbt parse` and the project test suite before republishing."),
    ]


def verify_artifacts(
    bundle: ArtifactBundle,
    change: ChangeRequest,
    context: ContextBundle,
) -> ValidationReport:
    checks: list[ValidationCheck] = []
    expected_paths = expected_artifact_paths(change, context)
    allowed = set(expected_paths)
    paths_safe = set(bundle.files) == allowed and all(
        path == artifact.path
        and not PurePosixPath(path).is_absolute()
        and ".." not in PurePosixPath(path).parts
        for path, artifact in bundle.files.items()
    )
    checks.append(
        _check(
            "paths_confined",
            "Generated paths are confined",
            paths_safe,
            "All paths match the seven-file allowlist."
            if paths_safe
            else "A generated path is outside the seven-file allowlist.",
        )
    )

    parsed, parse_errors = _parsed_sql(bundle)
    checks.append(
        _check(
            "sql_parses",
            "SQL parses with the Snowflake dialect",
            not parse_errors,
            "Every SQL artifact parsed successfully."
            if not parse_errors
            else "; ".join(parse_errors),
        )
    )

    model_sql = next(
        path
        for path in expected_paths
        if path.startswith("models/marts/") and path.endswith(".sql")
    )
    model_yaml = next(
        path
        for path in expected_paths
        if path.startswith("models/marts/") and path.endswith((".yml", ".yaml"))
    )
    compatibility_test = next(
        path for path in expected_paths if path.startswith("tests/")
    )
    migration_notes = next(
        path for path in expected_paths if path.startswith("migrations/")
    )
    model_name = PurePosixPath(model_sql).stem
    model_content = bundle.files.get(model_sql)
    model_text = model_content.content if model_content else ""
    model_expressions = parsed.get(model_sql, [])
    new_field = _preferred_field(change)
    context_aligned, alignment_detail, changed_schema_field = _context_alignment(
        change, context
    )
    checks.append(
        _check(
            "request_context_alignment",
            "Requested change agrees with DataHub metadata",
            context_aligned,
            alignment_detail,
        )
    )
    compatible = _phase_one_projection_valid(model_expressions, change, context)
    checks.append(
        _check(
            "phase_one_compatibility",
            "Phase-one compatibility invariant holds",
            compatible,
            "The phase-one model preserves the old contract and required alias."
            if compatible
            else "The model does not expose both phase-one field names.",
        )
    )

    yaml_artifact = bundle.files.get(model_yaml)
    required_fields = {change.field.casefold()}
    if new_field is not None:
        required_fields.add(new_field.casefold())
    columns, column_tests, column_types, yaml_structure_valid = _yaml_columns(
        yaml_artifact.content if yaml_artifact else "",
        model_name,
    )
    column_keys = {name.casefold() for name in columns}
    required_not_null: set[str] = set()
    expected_types: dict[str, str] = {}
    if changed_schema_field is not None:
        source_key = change.field.casefold()
        expected_types[source_key] = changed_schema_field.data_type
        if not changed_schema_field.nullable:
            required_not_null.add(source_key)
        if new_field is not None:
            preferred_key = new_field.casefold()
            expected_types[preferred_key] = (
                change.new_type
                if change.operation is ChangeOperation.TYPE_CHANGE
                and change.new_type is not None
                else changed_schema_field.data_type
            )
            if not changed_schema_field.nullable:
                required_not_null.add(preferred_key)
    tests_valid = all(
        "not_null" in column_tests.get(name, set()) for name in required_not_null
    )
    types_valid = all(
        name in column_types and _types_match(column_types[name], data_type)
        for name, data_type in expected_types.items()
    )
    yaml_valid = (
        yaml_structure_valid
        and _yaml_structure_matches(
            yaml_artifact.content if yaml_artifact else "", model_name, change, context
        )
        and required_fields.issubset(column_keys)
        and tests_valid
        and types_valid
    )
    checks.append(
        _check(
            "yaml_contract",
            "dbt YAML matches the DataHub-backed contract",
            yaml_valid,
            "Changed fields, types, and evidence-backed tests are contracted."
            if yaml_valid
            else "The dbt contract has a missing field, type, or required test.",
        )
    )

    model_output_names = _select_output_names(model_expressions)
    normalized_model_names = [name.casefold() for name in model_output_names if name]
    normalized_yaml_names = [name.casefold() for name in columns]
    output_names_unique = bool(normalized_model_names) and (
        len(normalized_model_names) == len(set(normalized_model_names))
        and len(normalized_yaml_names) == len(set(normalized_yaml_names))
        and set(normalized_model_names) == set(normalized_yaml_names)
    )
    checks.append(
        _check(
            "unique_output_names",
            "Model and YAML output names are unique",
            output_names_unique,
            "SQL and YAML expose the same case-insensitively unique columns."
            if output_names_unique
            else "SQL or YAML contains duplicate or mismatched output columns.",
        )
    )

    no_star = bool(model_expressions) and not any(
        expression.find(exp.Star) for expression in model_expressions
    )
    checks.append(
        _check(
            "no_select_star",
            "Generated model avoids SELECT star",
            no_star,
            "The model selects explicit columns."
            if no_star
            else "The generated model contains an unqualified SELECT star.",
        )
    )

    referenced = {
        name
        for artifact in bundle.files.values()
        if artifact.path.endswith(".sql")
        for name in _dbt_refs(artifact.content)
    }
    governed_model = model_name.removesuffix("__changesafe")
    known = {
        context.target_name,
        governed_model,
        model_name,
        *(asset.name for asset in context.upstream_assets),
        *(asset.name for asset in context.downstream_assets),
    }
    parsed_relations = {
        table.name
        for expressions in parsed.values()
        for expression in expressions
        for table in expression.find_all(exp.Table)
        if table.name
    }
    unsafe_statement = any(
        not isinstance(expression, exp.Select)
        or bool(list(expression.find_all(exp.Subquery)))
        or len(list(expression.find_all(exp.Select))) != 1
        or bool(list(expression.find_all(exp.Anonymous)))
        for expressions in parsed.values()
        for expression in expressions
    )
    all_relations = referenced | parsed_relations
    unknown_relations = all_relations - known
    model_refs = _dbt_refs(model_text)
    model_tables = [
        table
        for expression in model_expressions
        for table in expression.find_all(exp.Table)
        if table.name
    ]
    sentinel_tables, sentinel_refs = _sentinel_ref_tables(model_text)
    source_valid = (
        model_refs == {governed_model}
        and _live_jinja_directives(model_text)
        == [SAFE_MODEL_CONFIG, f"{{{{ ref('{governed_model}') }}}}"]
        and _model_select_contract_valid(model_expressions, change, context)
        and len(model_tables) == 1
        and model_tables[0].name.casefold() == governed_model.casefold()
        and model_tables[0].args.get("alias") is None
        and model_tables[0].args.get("db") is None
        and model_tables[0].args.get("catalog") is None
        and len(sentinel_refs) == 1
        and len(sentinel_tables) == 1
        and sentinel_tables[0].name.casefold() in sentinel_refs
        and sentinel_refs[sentinel_tables[0].name.casefold()].casefold()
        == governed_model.casefold()
        and sentinel_tables[0].args.get("alias") is None
        and sentinel_tables[0].args.get("db") is None
        and sentinel_tables[0].args.get("catalog") is None
        and model_name != governed_model
    )
    sources_valid = not unsafe_statement and not unknown_relations and source_valid
    checks.append(
        _check(
            "source_relations",
            "Referenced relations exist in context",
            sources_valid,
            "The compatibility layer reads only the governed model and expressions "
            "are scalar."
            if sources_valid
            else (
                "Generated SQL contains a subquery, unsafe function, or non-select "
                "statement."
                if unsafe_statement
                else (
                    f"Unknown relations: {sorted(unknown_relations)}"
                    if unknown_relations
                    else (
                        "Compatibility layer must read the governed model without "
                        "a self-cycle."
                    )
                )
            ),
        )
    )

    comparison_valid = _compatibility_test_valid(
        parsed.get(compatibility_test, []),
        change,
        model_name,
        (
            bundle.files[compatibility_test].content
            if compatibility_test in bundle.files
            else ""
        ),
    )
    if change.operation is ChangeOperation.REMOVE:
        compatibility_label = "Phase-one removal guard references the field"
        compatibility_detail = (
            f"The generated singular test references {change.field}; when dbt "
            "executes it in the target warehouse, premature removal causes a "
            "missing-column error. ChangeSafe does not execute this query."
            if comparison_valid
            else "The singular guard does not prove the phase-one field exists."
        )
    else:
        compatibility_label = "Compatibility test compares old and new values"
        compatibility_detail = (
            "The singular test fails on divergent values."
            if comparison_valid
            else "The compatibility test does not compare both field values."
        )
    checks.append(
        _check(
            "compatibility_test",
            compatibility_label,
            comparison_valid,
            compatibility_detail,
        )
    )

    migration = bundle.files.get(migration_notes)
    migration_text = migration.content.lower() if migration else ""
    pr = bundle.files.get(PR_BODY)
    pr_text = pr.content if pr else ""
    downstream_named = all(
        asset.name.lower() in migration_text for asset in context.downstream_assets
    )
    migration_valid = (
        "owner:" in migration_text
        and "deprecation window:" in migration_text
        and downstream_named
        and _transition_guidance_valid(
            migration.content if migration else "",
            change,
            governed_model,
            model_name,
            len(context.downstream_assets),
        )
        and _transition_guidance_valid(
            pr_text,
            change,
            governed_model,
            model_name,
            len(context.downstream_assets),
        )
    )
    checks.append(
        _check(
            "migration_notes",
            "Migration notes include owner, window, and evidence",
            migration_valid,
            "Migration governance and downstream evidence are complete."
            if migration_valid
            else "Migration notes omit required governance or downstream evidence.",
        )
    )

    rollback = bundle.files.get(ROLLBACK)
    rollback_text = rollback.content if rollback else ""
    rollback_valid = _rollback_instructions_valid(
        rollback_text,
        change,
        governed_model,
        model_name,
        model_sql,
        model_yaml,
        compatibility_test,
    )
    checks.append(
        _check(
            "rollback_instructions",
            "Rollback references generated model files",
            rollback_valid,
            "Rollback instructions identify the generated model and contract."
            if rollback_valid
            else "Rollback instructions do not reference both model files.",
        )
    )

    manifest_valid = _manifest_matches(bundle, change, context)
    checks.append(
        _check(
            "manifest_hashes",
            "Manifest hashes match generated bytes",
            manifest_valid,
            "All artifact digests match exact UTF-8 bytes."
            if manifest_valid
            else "One or more artifact or manifest hashes do not match.",
        )
    )

    return ValidationReport(
        passed=all(check.passed for check in checks if check.blocking), checks=checks
    )
