"""Reviewed operation-specific templates; LLM output can supply prose only."""

from __future__ import annotations

import json
import re
from datetime import timedelta

from pydantic import Field

from changesafe.domain import (
    ArtifactBundle,
    ArtifactFile,
    ChangeOperation,
    ChangeRequest,
    ContextBundle,
    RiskResult,
    SchemaField,
    StrictModel,
)
from changesafe.sql_types import canonical_sql_type, type_change_kind

MODEL_SQL = "models/marts/order_details__changesafe.sql"
MODEL_YAML = "models/marts/order_details__changesafe.yml"
COMPATIBILITY_TEST = "tests/assert_cust_email_compatibility.sql"
MIGRATION_NOTES = "migrations/2026-08-08-cust-email-rename.md"
ROLLBACK = "ROLLBACK.md"
PR_BODY = "PR_BODY.md"
MANIFEST = "changesafe-manifest.json"
EXPECTED_GOLDEN_PATHS = (
    MODEL_SQL,
    MODEL_YAML,
    COMPATIBILITY_TEST,
    MIGRATION_NOTES,
    ROLLBACK,
    PR_BODY,
    MANIFEST,
)


class GenerationNarrative(StrictModel):
    transformation_expression: str = Field(min_length=1, max_length=500)
    explanation: str = Field(min_length=1, max_length=2000)
    deprecation_language: str = Field(min_length=1, max_length=2000)
    migration_summary: str = Field(min_length=1, max_length=3000)
    rollback_summary: str = Field(min_length=1, max_length=2000)
    pr_prose: str = Field(min_length=1, max_length=4000)


def _slug(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-").lower()
    return normalized or "change"


def _identifier(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_]", "_", value).strip("_").lower()
    if not normalized:
        return "model"
    return f"model_{normalized}" if normalized[0].isdigit() else normalized


def _target_model_name(context: ContextBundle) -> str:
    return _identifier(context.target_name)


def _model_name(context: ContextBundle) -> str:
    return f"{_target_model_name(context)}__changesafe"


def _model_paths(context: ContextBundle) -> tuple[str, str]:
    model = _model_name(context)
    return f"models/marts/{model}.sql", f"models/marts/{model}.yml"


def _test_path(change: ChangeRequest) -> str:
    field = _identifier(change.field)
    suffix = {
        ChangeOperation.RENAME: "compatibility",
        ChangeOperation.REMOVE: "retained",
        ChangeOperation.TYPE_CHANGE: "type_compatibility",
    }[change.operation]
    return f"tests/assert_{field}_{suffix}.sql"


def _migration_path(change: ChangeRequest, context: ContextBundle) -> str:
    date = context.provenance.retrieved_at.date().isoformat()
    return f"migrations/{date}-{_slug(change.field)}-{change.operation.value}.md"


def expected_artifact_paths(
    change: ChangeRequest, context: ContextBundle
) -> tuple[str, ...]:
    model_sql, model_yaml = _model_paths(context)
    return (
        model_sql,
        model_yaml,
        _test_path(change),
        _migration_path(change, context),
        ROLLBACK,
        PR_BODY,
        MANIFEST,
    )


def _owner(context: ContextBundle) -> str:
    accountable = next(
        (
            owner
            for owner in context.owners
            if owner.ownership_type.upper()
            in {"DATA_OWNER", "BUSINESS_OWNER", "OWNER"}
        ),
        None,
    )
    if accountable is not None:
        return accountable.name
    if context.owners:
        return context.owners[0].name
    return "Data Platform"


def _preferred_field(change: ChangeRequest) -> str | None:
    if change.operation is ChangeOperation.RENAME:
        return change.new_field
    if change.operation is ChangeOperation.TYPE_CHANGE:
        return f"{change.field}__new_type"
    return None


def _schema(context: ContextBundle) -> list[SchemaField]:
    if not context.schema_fields:
        raise ValueError("Complete schema context is required for artifact generation")
    return context.schema_fields


def _changed_schema_field(
    change: ChangeRequest, context: ContextBundle
) -> SchemaField:
    matches = [
        field
        for field in _schema(context)
        if field.name.casefold() == change.field.casefold()
    ]
    if len(matches) != 1:
        raise ValueError(
            "Changed field is absent or ambiguous in DataHub schema context"
        )
    return matches[0]


def _validate_generation_context(
    change: ChangeRequest, context: ContextBundle
) -> SchemaField:
    changed = _changed_schema_field(change, context)
    if canonical_sql_type(changed.data_type) != canonical_sql_type(
        context.field_type
    ):
        raise ValueError("DataHub field type disagrees with complete schema context")

    preferred = _preferred_field(change)
    existing_names = {field.name.casefold() for field in _schema(context)}
    if preferred is not None and preferred.casefold() in existing_names:
        raise ValueError(
            f"Preferred field '{preferred}' already exists in the DataHub schema"
        )

    if change.operation is ChangeOperation.TYPE_CHANGE:
        assert change.new_type is not None
        if (
            change.old_type is not None
            and canonical_sql_type(change.old_type)
            != canonical_sql_type(context.field_type)
        ):
            raise ValueError("old_type does not match DataHub metadata")
        if type_change_kind(context.field_type, change.new_type) == "no_op":
            raise ValueError("new_type is a no-op for DataHub metadata")
    return changed


def default_narrative(
    change: ChangeRequest, context: ContextBundle
) -> GenerationNarrative:
    preferred = _preferred_field(change)
    if change.operation is ChangeOperation.REMOVE:
        action = (
            f"Retain `{change.field}` during phase one while every recorded consumer "
            "moves away from it."
        )
    elif change.operation is ChangeOperation.TYPE_CHANGE:
        action = (
            f"Keep `{change.field}` and introduce `{preferred}` with type "
            f"`{change.new_type}` during phase one."
        )
    else:
        action = (
            f"Keep `{change.field}` and introduce `{preferred}` during phase one."
        )
    return GenerationNarrative(
        transformation_expression=change.field,
        explanation=action,
        deprecation_language=(
            f"`{change.field}` remains available for a 30-day deprecation window "
            "and is removed only after every recorded downstream consumer migrates."
        ),
        migration_summary=(
            f"{action} Update the dbt contract and enforce the operation-specific "
            "compatibility invariant."
        ),
        rollback_summary=(
            "Revert the generated compatibility layer, schema, and test together, "
            "then run dbt parse before reopening downstream traffic."
        ),
        pr_prose=(
            "This phase-one compatibility layer preserves the existing interface "
            "and includes "
            "deterministic validation, deprecation evidence, and rollback steps."
        ),
    )


def _model_sql(change: ChangeRequest, context: ContextBundle) -> str:
    preferred = _preferred_field(change)
    projections: list[str] = []
    for schema_field in _schema(context):
        projections.append(schema_field.name)
        if schema_field.name != change.field or preferred is None:
            continue
        if change.operation is ChangeOperation.TYPE_CHANGE:
            assert change.new_type is not None
            projections.append(
                f"cast({change.field} as {change.new_type}) as {preferred}"
            )
        else:
            projections.append(f"{change.field} as {preferred}")
    if change.field not in {field.name for field in _schema(context)}:
        raise ValueError("Changed field is absent from complete schema context")
    rendered = ",\n".join(f"    {projection}" for projection in projections)
    return (
        "{{ config(materialized='table', contract={'enforced': true}) }}\n\n"
        f"select\n{rendered}\n"
        f"from {{{{ ref('{_target_model_name(context)}') }}}}\n"
    )


def _yaml_tests(field: SchemaField) -> str | None:
    return "[not_null]" if not field.nullable else None


def _model_yaml(change: ChangeRequest, context: ContextBundle) -> str:
    preferred = _preferred_field(change)
    changed_field = _changed_schema_field(change, context)
    fields = list(_schema(context))
    if preferred is not None:
        fields.insert(
            next(
                i
                for i, field in enumerate(fields)
                if field.name.casefold() == change.field.casefold()
            )
            + 1,
            SchemaField(
                name=preferred,
                data_type=(
                    change.new_type
                    if change.operation is ChangeOperation.TYPE_CHANGE
                    else changed_field.data_type
                ),
                nullable=changed_field.nullable,
            ),
        )
    lines = [
        "version: 2",
        "",
        "models:",
        f"  - name: {_model_name(context)}",
        "    description: Phase-one compatibility layer over the governed model.",
        "    config:",
        "      contract:",
        "        enforced: true",
        "    columns:",
    ]
    for field in fields:
        lines.extend(
            [
                f"      - name: {field.name}",
                f"        data_type: {json.dumps(field.data_type)}",
            ]
        )
        if field.name == change.field:
            lines.append(
                "        description: Deprecated compatibility field retained "
                "during phase one."
            )
        elif field.name == preferred:
            lines.append(
                "        description: Preferred field for migrated consumers."
            )
        tests = _yaml_tests(field)
        if tests:
            lines.append(f"        tests: {tests}")
    return "\n".join(lines) + "\n"


def _compatibility_test(change: ChangeRequest, context: ContextBundle) -> str:
    model = _model_name(context)
    preferred = _preferred_field(change)
    if change.operation is ChangeOperation.REMOVE:
        return (
            "-- Phase-one safety guard: dbt returns zero rows while this field "
            "exists.\n"
            f"-- If {change.field} is removed too early, warehouse execution fails "
            "on the missing column.\n"
            f"select {change.field}\n"
            f"from {{{{ ref('{model}') }}}}\n"
            "where false\n"
        )
    assert preferred is not None
    expected = change.field
    if change.operation is ChangeOperation.TYPE_CHANGE:
        assert change.new_type is not None
        expected = f"cast({change.field} as {change.new_type})"
    return (
        "-- Passing result: zero rows where phase-one values diverge.\n"
        "select\n"
        f"    {change.field}\n"
        f"from {{{{ ref('{model}') }}}}\n"
        f"where {expected} is distinct from {preferred}\n"
    )


def _change_title(change: ChangeRequest) -> str:
    if change.operation is ChangeOperation.RENAME:
        return f"rename `{change.field}` to `{change.new_field}`"
    if change.operation is ChangeOperation.TYPE_CHANGE:
        return f"change `{change.field}` to `{change.new_type}`"
    return f"defer removal of `{change.field}`"


def _migration_notes(
    change: ChangeRequest,
    context: ContextBundle,
    risk: RiskResult,
    narrative: GenerationNarrative,
) -> str:
    owner = _owner(context)
    governed_model = _target_model_name(context)
    shim_model = _model_name(context)
    preferred = _preferred_field(change)
    owner_transition = f"switch to `{shim_model}`"
    if preferred is not None:
        owner_transition += f" and migrate to `{preferred}`"
    else:
        owner_transition += f" while retaining `{change.field}` until phase two"
    ends = context.provenance.retrieved_at.date() + timedelta(days=30)
    downstream = "\n".join(
        f"- `{asset.name}` — {asset.domain or 'Unassigned'} — `{asset.urn}`"
        for asset in context.downstream_assets
    ) or "- No downstream assets were returned by the complete lineage query."
    return (
        f"# Migration: {_change_title(change)}\n\n"
        f"**Owner:** {owner}  \n"
        f"**Risk:** {risk.score}/100 — {risk.band.value.title()}  \n"
        f"**Deprecation window:** through {ends.isoformat()}\n\n"
        "## Phase one\n\n"
        f"The governed base model remains unchanged in phase one: `{governed_model}`. "
        f"ChangeSafe adds compatibility relation `{shim_model}`. "
        "Downstream owners must "
        f"{owner_transition}.\n\n"
        f"{narrative.migration_summary}\n\n"
        f"{narrative.deprecation_language}\n\n"
        "## Downstream evidence\n\n"
        f"{downstream}\n\n"
        "## Exit criteria\n\n"
        f"All {len(context.downstream_assets)} recorded consumers must complete "
        f"migration through `{shim_model}`, the operation-specific compatibility "
        "test must remain "
        "green, and the accountable owner must approve phase two.\n"
    )


def _rollback(
    change: ChangeRequest,
    context: ContextBundle,
    narrative: GenerationNarrative,
) -> str:
    model_sql, model_yaml = _model_paths(context)
    test_path = _test_path(change)
    governed_model = _target_model_name(context)
    shim_model = _model_name(context)
    return (
        "# ChangeSafe rollback\n\n"
        f"{narrative.rollback_summary}\n\n"
        f"1. Move downstream consumers from `{shim_model}` back to `{governed_model}` "
        "before removing generated artifacts.\n"
        f"2. Confirm `{change.field}` remains available to every downstream consumer.\n"
        f"3. Revert `{model_sql}`.\n"
        f"4. Revert `{model_yaml}`.\n"
        f"5. Remove `{test_path}`.\n"
        "6. Run `dbt parse` and the project test suite before republishing.\n"
    )


def _pr_body(
    change: ChangeRequest,
    context: ContextBundle,
    risk: RiskResult,
    narrative: GenerationNarrative,
) -> str:
    factor_lines = "\n".join(
        f"- **+{factor.points}** {factor.label}" for factor in risk.factors
    )
    domains = {asset.domain for asset in context.downstream_assets if asset.domain}
    governed_model = _target_model_name(context)
    shim_model = _model_name(context)
    preferred = _preferred_field(change)
    owner_transition = f"switch to `{shim_model}`"
    if preferred is not None:
        owner_transition += f" and migrate to `{preferred}`"
    else:
        owner_transition += f" while retaining `{change.field}` until phase two"
    return (
        f"# ChangeSafe: {_change_title(change)}\n\n"
        f"{narrative.pr_prose}\n\n"
        "## Phase-one compatibility relation\n\n"
        f"The governed base model remains unchanged in phase one: `{governed_model}`. "
        f"This package adds compatibility relation `{shim_model}`. "
        "Downstream owners must "
        f"{owner_transition}.\n\n"
        f"## Deterministic risk: {risk.score}/100 — {risk.band.value.title()}\n\n"
        f"{factor_lines}\n\n"
        f"## Impact\n\n{len(context.downstream_assets)} downstream assets across "
        f"{len(domains)} domains were found in DataHub.\n\n"
        "## Validation\n\n"
        "Publication remains blocked until SQL, YAML, compatibility, path, "
        "rollback, and manifest checks pass.\n\n"
        "## Exit criteria\n\n"
        f"All {len(context.downstream_assets)} recorded consumers must complete "
        f"migration through `{shim_model}`, the operation-specific compatibility "
        "test must remain "
        "green, and the accountable owner must approve phase two.\n"
    )


def generate_artifacts(
    change: ChangeRequest,
    context: ContextBundle,
    risk: RiskResult,
    narrative: GenerationNarrative | None = None,
) -> ArtifactBundle:
    _validate_generation_context(change, context)
    narrative = narrative or default_narrative(change, context)
    model_sql, model_yaml = _model_paths(context)
    contents = {
        model_sql: _model_sql(change, context),
        model_yaml: _model_yaml(change, context),
        _test_path(change): _compatibility_test(change, context),
        _migration_path(change, context): _migration_notes(
            change, context, risk, narrative
        ),
        ROLLBACK: _rollback(change, context, narrative),
        PR_BODY: _pr_body(change, context, risk, narrative),
    }
    files = {
        path: ArtifactFile(path=path, content=content)
        for path, content in contents.items()
    }
    manifest = {
        "version": 1,
        "change": change.model_dump(mode="json"),
        "context": {
            "mode": context.provenance.mode.value,
            "snapshot_hash": context.provenance.snapshot_hash,
            "target_urn": context.target_urn,
        },
        "risk": risk.model_dump(mode="json"),
        "deprecation_status": "phase_one",
        "files": {path: artifact.sha256 for path, artifact in files.items()},
    }
    manifest_content = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    files[MANIFEST] = ArtifactFile(path=MANIFEST, content=manifest_content)
    return ArtifactBundle(files=files, manifest_hash=files[MANIFEST].sha256)
