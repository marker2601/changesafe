"""Fail-closed validation of generated migration artifacts."""

from __future__ import annotations

import json
import re
from pathlib import PurePosixPath
from typing import cast

import sqlglot
import yaml
from sqlglot import exp

from changesafe.domain import (
    ArtifactBundle,
    ChangeRequest,
    ContextBundle,
    ValidationCheck,
    ValidationReport,
)
from changesafe.generation.templates import (
    COMPATIBILITY_TEST,
    EXPECTED_GOLDEN_PATHS,
    MANIFEST,
    MIGRATION_NOTES,
    MODEL_SQL,
    MODEL_YAML,
    ROLLBACK,
)

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


def _yaml_column_names(content: str) -> tuple[set[str], bool]:
    try:
        document = yaml.safe_load(content)
    except yaml.YAMLError:
        return set(), False
    if not isinstance(document, dict) or document.get("version") != 2:
        return set(), False
    models = document.get("models")
    if not isinstance(models, list):
        return set(), False
    model = next(
        (
            item
            for item in models
            if isinstance(item, dict) and item.get("name") == "dim_customers"
        ),
        None,
    )
    if not isinstance(model, dict):
        return set(), False
    columns = model.get("columns")
    if not isinstance(columns, list):
        return set(), False
    names = {
        str(column.get("name"))
        for column in columns
        if isinstance(column, dict) and column.get("name")
    }
    has_tests = all(
        isinstance(column, dict) and column.get("tests")
        for column in columns
        if isinstance(column, dict)
        and column.get("name") in {"customer_email", "primary_email"}
    )
    return names, has_tests


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
    allowed = set(EXPECTED_GOLDEN_PATHS)
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

    model_content = bundle.files.get(MODEL_SQL)
    model_text = model_content.content if model_content else ""
    new_field = change.new_field or f"{change.field}__new_type"
    compatible = bool(
        re.search(rf"\b{re.escape(change.field)}\b", model_text, re.IGNORECASE)
        and re.search(rf"\bas\s+{re.escape(new_field)}\b", model_text, re.IGNORECASE)
    )
    checks.append(
        _check(
            "phase_one_compatibility",
            "Old and new fields coexist",
            compatible,
            "The phase-one model exposes both field contracts."
            if compatible
            else "The model does not expose both phase-one field names.",
        )
    )

    yaml_artifact = bundle.files.get(MODEL_YAML)
    columns, has_tests = _yaml_column_names(
        yaml_artifact.content if yaml_artifact else ""
    )
    yaml_valid = {change.field, new_field}.issubset(columns) and has_tests
    checks.append(
        _check(
            "yaml_contract",
            "dbt YAML declares changed fields and tests",
            yaml_valid,
            "Both fields are contracted and tested."
            if yaml_valid
            else "The dbt contract is missing a changed field or required tests.",
        )
    )

    model_expressions = parsed.get(MODEL_SQL, [])
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
    sources_valid = referenced.issubset(known)
    checks.append(
        _check(
            "source_relations",
            "Referenced relations exist in context",
            sources_valid,
            "Every dbt ref is backed by DataHub context."
            if sources_valid
            else f"Unknown relations: {sorted(referenced - known)}",
        )
    )

    compatibility = bundle.files.get(COMPATIBILITY_TEST)
    compatibility_text = compatibility.content.lower() if compatibility else ""
    comparison_valid = (
        change.field.lower() in compatibility_text
        and new_field.lower() in compatibility_text
        and "is distinct from" in compatibility_text
    )
    checks.append(
        _check(
            "compatibility_test",
            "Compatibility test compares old and new values",
            comparison_valid,
            "The singular test fails on divergent values."
            if comparison_valid
            else "The compatibility test does not compare both field values.",
        )
    )

    migration = bundle.files.get(MIGRATION_NOTES)
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
    rollback_valid = MODEL_SQL in rollback_text and MODEL_YAML in rollback_text
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
