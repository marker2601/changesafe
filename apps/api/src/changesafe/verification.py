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
    ROLLBACK,
    expected_artifact_paths,
)
from changesafe.sql_types import canonical_sql_type, type_change_kind

REF_PATTERN = re.compile(r"\{\{\s*ref\(['\"]([^'\"]+)['\"]\)\s*\}\}")
CONFIG_PATTERN = re.compile(r"^\s*\{\{\s*config\(.*?\)\s*\}\}\s*$", re.MULTILINE)


def _check(code: str, label: str, passed: bool, detail: str) -> ValidationCheck:
    return ValidationCheck(code=code, label=label, passed=passed, detail=detail)


def _normalized_sql(content: str) -> str:
    without_config = CONFIG_PATTERN.sub("", content)
    return REF_PATTERN.sub(lambda match: match.group(1), without_config)


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


def _manifest_matches(bundle: ArtifactBundle) -> bool:
    try:
        manifest = json.loads(bundle.files[MANIFEST].content)
    except (KeyError, json.JSONDecodeError):
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
    return hashes_match and bundle.manifest_hash == bundle.files[MANIFEST].sha256


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
    old_present = bool(
        re.search(rf"\b{re.escape(change.field)}\b", model_text, re.IGNORECASE)
    )
    compatible = old_present and (
        new_field is None
        or bool(
            re.search(
                rf"\bas\s+{re.escape(new_field)}\b", model_text, re.IGNORECASE
            )
        )
    )
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

    model_expressions = parsed.get(model_sql, [])
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
        for name in REF_PATTERN.findall(artifact.content)
    }
    known = {
        context.target_name,
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
    sources_valid = not unsafe_statement and not unknown_relations
    checks.append(
        _check(
            "source_relations",
            "Referenced relations exist in context",
            sources_valid,
            "Every relation is backed by DataHub context and expressions are scalar."
            if sources_valid
            else (
                "Generated SQL contains a subquery, unsafe function, or non-select "
                "statement."
                if unsafe_statement
                else f"Unknown relations: {sorted(unknown_relations)}"
            ),
        )
    )

    compatibility = bundle.files.get(compatibility_test)
    compatibility_text = compatibility.content.lower() if compatibility else ""
    comparison_valid = change.field.lower() in compatibility_text and (
        "where false" in compatibility_text
        if change.operation is ChangeOperation.REMOVE
        else new_field is not None
        and new_field.lower() in compatibility_text
        and "is distinct from" in compatibility_text
    )
    if change.operation is ChangeOperation.REMOVE:
        compatibility_label = "Phase-one field remains available"
        compatibility_detail = (
            f"The singular guard compiles only while {change.field} exists."
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
    downstream_named = all(
        asset.name.lower() in migration_text for asset in context.downstream_assets
    )
    migration_valid = (
        "owner:" in migration_text
        and "deprecation window:" in migration_text
        and downstream_named
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
    rollback_valid = model_sql in rollback_text and model_yaml in rollback_text
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

    manifest_valid = _manifest_matches(bundle)
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
