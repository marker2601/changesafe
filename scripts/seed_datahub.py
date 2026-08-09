"""Apply and verify the minimal ChangeSafe overlay for DataHub's demo datapack.

Load the organizer-provided base graph first with:

    datahub datapack load showcase-ecommerce

This script deliberately does not replace the official schema, ownership, domains,
tags, or lineage. It adds only namespaced ChangeSafe audit definitions and two
sanitized query-usage records needed for a deterministic judge demonstration.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Protocol

from changesafe.demo import DEMO_FIELD, DEMO_TARGET_URN, golden_change

DATAPACK = "showcase-ecommerce"
DEPRECATING_TAG = "urn:li:tag:ChangeSafe:Deprecating"
PII_TAG = "urn:li:tag:b2fd91.PII_Data"
PROPERTY_DEFINITIONS: dict[str, dict[str, str | list[str]]] = {
    "urn:li:structuredProperty:changesafe.riskLevel": {
        "type": "string",
        "allowed_values": ["LOW", "MEDIUM", "HIGH", "CRITICAL"],
    },
    "urn:li:structuredProperty:changesafe.changeStatus": {
        "type": "string",
        "allowed_values": ["PROPOSED", "DEPRECATING", "COMPLETED"],
    },
    "urn:li:structuredProperty:changesafe.lastRunId": {"type": "string"},
}


class ProposalEmitter(Protocol):
    def emit(self, proposal: Any) -> None: ...


def build_seed_spec() -> dict[str, Any]:
    return {
        "base_datapack": DATAPACK,
        "load_command": f"datahub datapack load {DATAPACK}",
        "target": DEMO_TARGET_URN,
        "field": DEMO_FIELD,
        "required_official_context": {
            "governance_tags": [PII_TAG],
            "owners": "at least one accountable owner",
            "downstream": "at least one field-evidenced dependency",
        },
        "overlay": {
            "namespace": "changesafe",
            "tag": DEPRECATING_TAG,
            "query_records": 2,
            "structured_properties": PROPERTY_DEFINITIONS,
        },
    }


def build_seed_proposals() -> list[Any]:
    """Return stable UPSERTs that never overwrite the official asset graph."""

    try:
        from datahub.emitter.mce_builder import make_schema_field_urn
        from datahub.emitter.mcp import MetadataChangeProposalWrapper
        from datahub.metadata import schema_classes as m
    except ImportError as exc:  # pragma: no cover - packaging check
        raise RuntimeError(
            "Install ChangeSafe with the 'live' extra to seed DataHub"
        ) from exc

    actor = "urn:li:corpuser:changesafe"
    audit = m.AuditStampClass(time=0, actor=actor)
    proposals: list[Any] = []

    def add(entity_urn: str, aspect: Any) -> None:
        proposals.append(
            MetadataChangeProposalWrapper(entityUrn=entity_urn, aspect=aspect)
        )

    add(
        DEPRECATING_TAG,
        m.TagPropertiesClass(
            name="ChangeSafe:Deprecating",
            description="A field in an approved ChangeSafe deprecation window.",
        ),
    )

    for urn, definition in PROPERTY_DEFINITIONS.items():
        allowed = definition.get("allowed_values")
        add(
            urn,
            m.StructuredPropertyDefinitionClass(
                qualifiedName=urn.removeprefix("urn:li:structuredProperty:"),
                displayName=urn.rsplit(".", 1)[-1],
                description="ChangeSafe publication audit metadata.",
                valueType="urn:li:dataType:datahub.string",
                entityTypes=["urn:li:entityType:datahub.dataset"],
                cardinality="SINGLE",
                allowedValues=(
                    [m.PropertyValueClass(value=value) for value in allowed]
                    if isinstance(allowed, list)
                    else None
                ),
                created=audit,
                lastModified=audit,
            ),
        )
        add(
            urn,
            m.StructuredPropertySettingsClass(
                showInAssetSummary=True,
                showInSearchFilters=True,
                lastModified=audit,
            ),
        )

    statements = (
        "select cust_email from order_entry_db.analytics.order_details",
        "select count(distinct cust_email) "
        "from order_entry_db.analytics.order_details",
    )
    for index, statement in enumerate(statements, start=1):
        query_urn = f"urn:li:query:changesafe-order-details-cust-email-{index}"
        add(
            query_urn,
            m.QueryPropertiesClass(
                statement=m.QueryStatementClass(value=statement, language="SQL"),
                source="SYSTEM",
                created=audit,
                lastModified=audit,
                name=f"ChangeSafe order-details usage {index}",
            ),
        )
        add(
            query_urn,
            m.QuerySubjectsClass(
                subjects=[
                    m.QuerySubjectClass(
                        entity=make_schema_field_urn(DEMO_TARGET_URN, DEMO_FIELD)
                    )
                ]
            ),
        )

    return proposals


def apply_seed(emitter: ProposalEmitter, proposals: Sequence[Any]) -> None:
    for proposal in proposals:
        emitter.emit(proposal)


async def verify_seed(gms_url: str, token: str) -> None:
    from changesafe.context.live import AgentContextToolRunner, LiveDataHubContext
    from changesafe.domain import ContextMode

    runner = AgentContextToolRunner.connect(gms_url.rstrip("/"), token)
    port = LiveDataHubContext(
        runner=runner,
        allowlist={DEMO_TARGET_URN},
        timeout_seconds=8,
        retry_count=1,
    )
    try:
        context = await port.load(golden_change())
    finally:
        runner.close()

    if context.provenance.mode is not ContextMode.LIVE:
        raise RuntimeError("Seed verification did not use live DataHub context")
    if context.target_urn != DEMO_TARGET_URN or context.field != DEMO_FIELD:
        raise RuntimeError("Official Order Entry target or field is unavailable")
    if not context.downstream_assets:
        raise RuntimeError("Official field dependency evidence is unavailable")
    platforms = {asset.urn.lower() for asset in context.downstream_assets}
    if not any("powerbi" in urn or "looker" in urn for urn in platforms):
        raise RuntimeError("Expected a BI dependency from the official datapack")
    if not context.upstream_assets or not context.queries:
        raise RuntimeError("Lineage or sanitized query evidence is unavailable")
    if PII_TAG not in context.field_tags:
        raise RuntimeError("Official PII governance metadata is unavailable")
    if not context.owners:
        raise RuntimeError("Official accountable ownership is unavailable")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Print, apply, and verify the ChangeSafe overlay for the official "
            "showcase-ecommerce datapack."
        )
    )
    parser.add_argument(
        "--compact", action="store_true", help="Emit compact JSON for automation."
    )
    parser.add_argument(
        "--apply", action="store_true", help="Apply stable overlay UPSERTs."
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Verify the loaded official datapack and ChangeSafe overlay.",
    )
    parser.add_argument(
        "--no-verify",
        action="store_true",
        help="Skip post-apply verification (not recommended).",
    )
    parser.add_argument("--gms-url", default=os.getenv("DATAHUB_GMS_URL"))
    parser.add_argument("--token", default=os.getenv("DATAHUB_GMS_TOKEN"))
    parser.add_argument("--env-file", type=Path, help="Private environment file.")
    args = parser.parse_args()

    if not args.apply and not args.verify_only:
        print(
            json.dumps(
                build_seed_spec(),
                indent=None if args.compact else 2,
                sort_keys=True,
            )
        )
        return

    if args.env_file is not None:
        if not args.env_file.is_file():
            parser.error(f"Environment file does not exist: {args.env_file}")
        os.environ["CHANGESAFE_ENV_FILE"] = str(args.env_file.resolve())

    from changesafe.config import Settings

    settings = Settings()
    gms_url = args.gms_url or (
        str(settings.datahub_gms_url) if settings.datahub_gms_url else None
    )
    token = args.token or (
        settings.datahub_gms_token.get_secret_value()
        if settings.datahub_gms_token
        else None
    )
    if not gms_url or not token:
        parser.error(
            "--gms-url and --token (or DataHub environment values) are required"
        )

    if args.apply:
        from datahub.emitter.rest_emitter import DatahubRestEmitter

        emitter = DatahubRestEmitter(
            gms_server=gms_url.rstrip("/"),
            token=token,
            timeout_sec=10,
            retry_max_times=1,
        )
        try:
            emitter.test_connection()
            proposals = build_seed_proposals()
            apply_seed(emitter, proposals)
        finally:
            emitter.close()
        print(f"Applied {len(proposals)} namespaced overlay aspect upserts.")

    if args.verify_only or not args.no_verify:
        asyncio.run(verify_seed(gms_url, token))
        print("Verified the official DataHub demo and ChangeSafe overlay.")


if __name__ == "__main__":
    main()
