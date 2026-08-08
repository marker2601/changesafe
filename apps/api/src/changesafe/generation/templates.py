"""Reviewed deterministic templates that remain authoritative over LLM prose."""

from __future__ import annotations

import json
from datetime import timedelta

from pydantic import Field

from changesafe.domain import (
    ArtifactBundle,
    ArtifactFile,
    ChangeOperation,
    ChangeRequest,
    ContextBundle,
    RiskResult,
    StrictModel,
)

MODEL_SQL = "models/marts/dim_customers.sql"
MODEL_YAML = "models/marts/dim_customers.yml"
COMPATIBILITY_TEST = "tests/assert_customer_email_compatibility.sql"
MIGRATION_NOTES = "migrations/2026-08-06-customer-email-rename.md"
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


def _owner(context: ContextBundle) -> str:
    accountable = next(
        (
            owner
            for owner in context.owners
            if owner.ownership_type.upper() in {"DATA_OWNER", "BUSINESS_OWNER", "OWNER"}
        ),
        None,
    )
    if accountable is not None:
        return accountable.name
    if context.owners:
        return context.owners[0].name
    return "Data Platform"


def default_narrative(
    change: ChangeRequest, context: ContextBundle
) -> GenerationNarrative:
    expression = change.field
    if change.operation is ChangeOperation.TYPE_CHANGE and change.new_type:
        expression = f"cast({change.field} as {change.new_type})"
    return GenerationNarrative(
        transformation_expression=expression,
        explanation=(
            "Keep the source value available under the existing contract while "
            "consumers move to the new field name."
        ),
        deprecation_language=(
            f"`{change.field}` remains available for a 30-day deprecation window "
            "and is removed only after every recorded downstream consumer migrates."
        ),
        migration_summary=(
            f"Introduce `{change.new_field or change.field}` without removing "
            f"`{change.field}`, update the dbt contract, and enforce value "
            "compatibility."
        ),
        rollback_summary=(
            "Revert the generated model, schema, and compatibility test together, then "
            "run dbt parse before reopening downstream traffic."
        ),
        pr_prose=(
            "This phase-one migration preserves the existing interface, adds the new "
            "contracted field, and includes deterministic validation and rollback "
            "evidence."
        ),
    )


def _model_sql(change: ChangeRequest, narrative: GenerationNarrative) -> str:
    new_field = change.new_field or f"{change.field}__new_type"
    new_expression = narrative.transformation_expression
    return (
        "{{ config(materialized='table', contract={'enforced': true}) }}\n\n"
        "select\n"
        "    customer_id,\n"
        "    customer_name,\n"
        f"    {change.field},\n"
        f"    {new_expression} as {new_field},\n"
        "    customer_status,\n"
        "    created_at\n"
        "from {{ ref('stg_customers') }}\n"
    )


def _model_yaml(change: ChangeRequest, context: ContextBundle) -> str:
    new_field = change.new_field or f"{change.field}__new_type"
    new_type = change.new_type or context.field_type
    return (
        "version: 2\n\n"
        "models:\n"
        "  - name: dim_customers\n"
        "    description: Governed customer dimension with a phase-one "
        "compatibility alias.\n"
        "    config:\n"
        "      contract:\n"
        "        enforced: true\n"
        "    columns:\n"
        "      - name: customer_id\n"
        "        data_type: STRING\n"
        "        tests: [not_null, unique]\n"
        f"      - name: {change.field}\n"
        f"        data_type: {context.field_type}\n"
        "        description: Deprecated compatibility field retained during "
        "phase one.\n"
        "        tests: [not_null]\n"
        f"      - name: {new_field}\n"
        f"        data_type: {new_type}\n"
        "        description: Preferred field for migrated consumers.\n"
        "        tests: [not_null]\n"
        "      - name: customer_name\n"
        "        data_type: STRING\n"
        "      - name: customer_status\n"
        "        data_type: STRING\n"
        "      - name: created_at\n"
        "        data_type: TIMESTAMP\n"
    )


def _compatibility_test(change: ChangeRequest) -> str:
    new_field = change.new_field or f"{change.field}__new_type"
    return (
        "-- Passing result: zero rows where phase-one values diverge.\n"
        "select\n"
        "    customer_id\n"
        "from {{ ref('dim_customers') }}\n"
        f"where {change.field} is distinct from {new_field}\n"
    )


def _migration_notes(
    change: ChangeRequest,
    context: ContextBundle,
    risk: RiskResult,
    narrative: GenerationNarrative,
) -> str:
    owner = _owner(context)
    ends = context.provenance.retrieved_at.date() + timedelta(days=30)
    downstream = "\n".join(
        f"- `{asset.name}` — {asset.domain or 'Unassigned'} — `{asset.urn}`"
        for asset in context.downstream_assets
    )
    return (
        f"# Migration: `{change.field}` to `{change.new_field}`\n\n"
        f"**Owner:** {owner}  \n"
        f"**Risk:** {risk.score}/100 — {risk.band.value.title()}  \n"
        f"**Deprecation window:** through {ends.isoformat()}\n\n"
        "## Phase one\n\n"
        f"{narrative.migration_summary}\n\n"
        f"{narrative.deprecation_language}\n\n"
        "## Downstream evidence\n\n"
        f"{downstream}\n\n"
        "## Exit criteria\n\n"
        "All four recorded consumers must use the preferred field, the "
        "compatibility test must remain green, and the accountable owner must "
        "approve phase two.\n"
    )


def _rollback(change: ChangeRequest, narrative: GenerationNarrative) -> str:
    return (
        "# ChangeSafe rollback\n\n"
        f"{narrative.rollback_summary}\n\n"
        "1. Revert `models/marts/dim_customers.sql`.\n"
        "2. Revert `models/marts/dim_customers.yml`.\n"
        "3. Remove `tests/assert_customer_email_compatibility.sql`.\n"
        f"4. Confirm `{change.field}` remains available to every downstream consumer.\n"
        "5. Run `dbt parse` and the project test suite before republishing.\n"
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
    return (
        f"# ChangeSafe: migrate `{change.field}` to `{change.new_field}`\n\n"
        f"{narrative.pr_prose}\n\n"
        f"## Deterministic risk: {risk.score}/100 — {risk.band.value.title()}\n\n"
        f"{factor_lines}\n\n"
        f"## Impact\n\n{len(context.downstream_assets)} downstream assets across "
        f"{len({asset.domain for asset in context.downstream_assets if asset.domain})} "
        "domains were found in DataHub.\n\n"
        "## Validation\n\n"
        "Publication remains blocked until SQL, YAML, compatibility, path, "
        "rollback, and manifest checks pass.\n"
    )


def generate_artifacts(
    change: ChangeRequest,
    context: ContextBundle,
    risk: RiskResult,
    narrative: GenerationNarrative | None = None,
) -> ArtifactBundle:
    narrative = narrative or default_narrative(change, context)
    contents = {
        MODEL_SQL: _model_sql(change, narrative),
        MODEL_YAML: _model_yaml(change, context),
        COMPATIBILITY_TEST: _compatibility_test(change),
        MIGRATION_NOTES: _migration_notes(change, context, risk, narrative),
        ROLLBACK: _rollback(change, narrative),
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
