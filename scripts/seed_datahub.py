"""Build, apply, and verify the reproducible ChangeSafe DataHub graph."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Protocol

TARGET = "urn:li:dataset:(urn:li:dataPlatform:dbt,analytics.dim_customers,PROD)"
CUSTOMERS_RAW = (
    "urn:li:dataset:(urn:li:dataPlatform:postgres,sales.customers_raw,PROD)"
)
STG_CUSTOMERS = (
    "urn:li:dataset:(urn:li:dataPlatform:dbt,analytics.stg_customers,PROD)"
)
CUSTOMER_360 = (
    "urn:li:dataset:(urn:li:dataPlatform:snowflake,"
    "analytics.customer_360,PROD)"
)
CAMPAIGN_AUDIENCES = (
    "urn:li:dataset:(urn:li:dataPlatform:snowflake,"
    "marketing.campaign_audiences,PROD)"
)
CONTACT_QUEUE = (
    "urn:li:dataset:(urn:li:dataPlatform:snowflake,"
    "support.customer_contact_queue,PROD)"
)
DASHBOARD = "urn:li:dashboard:(looker,customer_retention_dashboard)"
OWNER = "urn:li:corpuser:customer-analytics"
TECHNICAL_OWNER = "urn:li:corpuser:data-platform"
PII_TAG = "urn:li:tag:PII"
DEPRECATING_TAG = "urn:li:tag:ChangeSafe:Deprecating"
EMAIL_TERM = "urn:li:glossaryTerm:CustomerEmail"

DATASETS = (
    (CUSTOMERS_RAW, "postgres", "customers_raw", "Sales", "email"),
    (STG_CUSTOMERS, "dbt", "stg_customers", "Analytics", "customer_email"),
    (TARGET, "dbt", "dim_customers", "Analytics", "customer_email"),
    (CUSTOMER_360, "snowflake", "customer_360", "Analytics", "customer_email"),
    (
        CAMPAIGN_AUDIENCES,
        "snowflake",
        "campaign_audiences",
        "Marketing",
        "customer_email",
    ),
    (
        CONTACT_QUEUE,
        "snowflake",
        "customer_contact_queue",
        "Support",
        "customer_email",
    ),
)


class ProposalEmitter(Protocol):
    def emit(self, proposal: Any) -> None: ...


def build_seed_spec() -> dict[str, Any]:
    assets = [
        {"urn": urn, "name": name, "domain": domain}
        for urn, _, name, domain, _ in DATASETS
    ]
    assets.append(
        {
            "urn": DASHBOARD,
            "name": "customer_retention_dashboard",
            "domain": "Executive Reporting",
        }
    )
    return {
        "assets": assets,
        "target": TARGET,
        "downstream_from_target": [
            CUSTOMER_360,
            CAMPAIGN_AUDIENCES,
            CONTACT_QUEUE,
            DASHBOARD,
        ],
        "field": "customer_email",
        "field_type": "STRING",
        "owners": [
            {"urn": TECHNICAL_OWNER, "type": "TECHNICAL_OWNER"},
            {"urn": OWNER, "type": "DATA_OWNER"},
        ],
        "tag": DEPRECATING_TAG,
        "governance_tags": [PII_TAG],
        "glossary_terms": [EMAIL_TERM],
        "structured_properties": {
            "urn:li:structuredProperty:changesafe.riskLevel": {
                "type": "string",
                "allowed_values": ["LOW", "MEDIUM", "HIGH", "CRITICAL"],
            },
            "urn:li:structuredProperty:changesafe.changeStatus": {
                "type": "string",
                "allowed_values": ["PROPOSED", "DEPRECATING", "COMPLETED"],
            },
            "urn:li:structuredProperty:changesafe.lastRunId": {"type": "string"},
        },
    }


def build_seed_proposals() -> list[Any]:
    """Return stable UPSERT proposals; rerunning them is idempotent."""

    try:
        from datahub.emitter.mce_builder import make_schema_field_urn
        from datahub.emitter.mcp import MetadataChangeProposalWrapper
        from datahub.metadata import schema_classes as m
    except ImportError as exc:  # pragma: no cover - exercised by packaging checks
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

    domains = {
        "Sales",
        "Analytics",
        "Marketing",
        "Support",
        "Executive Reporting",
    }
    domain_urns = {
        name: f"urn:li:domain:changesafe-{name.lower().replace(' ', '-')}"
        for name in domains
    }
    for name in sorted(domains):
        add(
            domain_urns[name],
            m.DomainPropertiesClass(
                name=name,
                description=f"Synthetic ChangeSafe {name} domain.",
            ),
        )

    add(PII_TAG, m.TagPropertiesClass(name="PII", description="Personal data"))
    add(
        DEPRECATING_TAG,
        m.TagPropertiesClass(
            name="ChangeSafe:Deprecating",
            description="A field in a governed ChangeSafe deprecation window.",
        ),
    )
    add(
        EMAIL_TERM,
        m.GlossaryTermInfoClass(
            definition="Customer contact email used by governed analytics products.",
            termSource="INTERNAL",
            name="Customer Email",
        ),
    )
    add(
        OWNER,
        m.CorpUserInfoClass(
            active=True,
            displayName="Customer Analytics",
            email="customer-analytics@example.invalid",
            title="Data Owner",
        ),
    )
    add(
        TECHNICAL_OWNER,
        m.CorpUserInfoClass(
            active=True,
            displayName="Data Platform",
            email="data-platform@example.invalid",
            title="Technical Owner",
        ),
    )

    property_specs = build_seed_spec()["structured_properties"]
    for urn, definition in property_specs.items():
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

    target_fields = [
        ("customer_id", "STRING", False),
        ("customer_name", "STRING", True),
        ("customer_email", "STRING", False),
        ("customer_status", "STRING", True),
        ("created_at", "TIMESTAMP", True),
    ]
    for urn, platform, name, domain, lineage_field in DATASETS:
        fields = target_fields if urn in {STG_CUSTOMERS, TARGET} else [
            (lineage_field, "STRING", True)
        ]
        schema_fields = []
        for field_name, native_type, nullable in fields:
            governed = urn == TARGET and field_name == "customer_email"
            schema_fields.append(
                m.SchemaFieldClass(
                    fieldPath=field_name,
                    type=m.SchemaFieldDataTypeClass(type=m.StringTypeClass()),
                    nativeDataType=native_type,
                    nullable=nullable,
                    globalTags=(
                        m.GlobalTagsClass(tags=[m.TagAssociationClass(tag=PII_TAG)])
                        if governed
                        else None
                    ),
                    glossaryTerms=(
                        m.GlossaryTermsClass(
                            terms=[m.GlossaryTermAssociationClass(urn=EMAIL_TERM)],
                            auditStamp=audit,
                        )
                        if governed
                        else None
                    ),
                )
            )
        add(
            urn,
            m.DatasetPropertiesClass(
                name=name,
                qualifiedName=name,
                description=f"Synthetic ChangeSafe dataset {name}.",
            ),
        )
        add(urn, m.DomainsClass(domains=[domain_urns[domain]]))
        add(
            urn,
            m.SchemaMetadataClass(
                schemaName=name,
                platform=f"urn:li:dataPlatform:{platform}",
                version=0,
                hash="changesafe-v1",
                platformSchema=m.OtherSchemaClass(rawSchema=""),
                fields=schema_fields,
                created=audit,
                lastModified=audit,
            ),
        )

    add(
        TARGET,
        m.OwnershipClass(
            owners=[
                m.OwnerClass(owner=TECHNICAL_OWNER, type="TECHNICAL_OWNER"),
                m.OwnerClass(owner=OWNER, type="DATAOWNER"),
            ],
            lastModified=audit,
        ),
    )
    add(TARGET, m.GlobalTagsClass(tags=[m.TagAssociationClass(tag=PII_TAG)]))

    lineage = {
        STG_CUSTOMERS: (CUSTOMERS_RAW, "email", "customer_email"),
        TARGET: (STG_CUSTOMERS, "customer_email", "customer_email"),
        CUSTOMER_360: (TARGET, "customer_email", "customer_email"),
        CAMPAIGN_AUDIENCES: (TARGET, "customer_email", "customer_email"),
        CONTACT_QUEUE: (TARGET, "customer_email", "customer_email"),
    }
    for downstream, (upstream, upstream_field, downstream_field) in lineage.items():
        add(
            downstream,
            m.UpstreamLineageClass(
                upstreams=[
                    m.UpstreamClass(
                        dataset=upstream,
                        type="TRANSFORMED",
                        auditStamp=audit,
                    )
                ],
                fineGrainedLineages=[
                    m.FineGrainedLineageClass(
                        upstreamType="FIELD_SET",
                        downstreamType="FIELD",
                        upstreams=[make_schema_field_urn(upstream, upstream_field)],
                        downstreams=[
                            make_schema_field_urn(downstream, downstream_field)
                        ],
                        confidenceScore=1.0,
                    )
                ],
            ),
        )

    add(
        DASHBOARD,
        m.DashboardInfoClass(
            title="customer_retention_dashboard",
            description="Executive customer-retention dashboard.",
            lastModified=m.ChangeAuditStampsClass(
                created=audit,
                lastModified=audit,
            ),
            datasets=[TARGET],
        ),
    )
    add(DASHBOARD, m.DomainsClass(domains=[domain_urns["Executive Reporting"]]))

    query_statements = [
        "select customer_email from analytics.dim_customers "
        "where customer_status = 'active'",
        "select count(distinct customer_email) from analytics.dim_customers",
    ]
    for index, statement in enumerate(query_statements, start=1):
        query_urn = f"urn:li:query:changesafe-customer-email-{index}"
        add(
            query_urn,
            m.QueryPropertiesClass(
                statement=m.QueryStatementClass(value=statement, language="SQL"),
                source="SYSTEM",
                created=audit,
                lastModified=audit,
                name=f"ChangeSafe customer email usage {index}",
            ),
        )
        add(
            query_urn,
            m.QuerySubjectsClass(
                subjects=[
                    m.QuerySubjectClass(
                        entity=make_schema_field_urn(TARGET, "customer_email")
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
    from changesafe.domain import ChangeOperation, ChangeRequest, ContextMode
    from changesafe.risk import score_change

    change = ChangeRequest(
        asset_urn=TARGET,
        operation=ChangeOperation.RENAME,
        field="customer_email",
        new_field="primary_email",
        old_type="STRING",
        new_type="STRING",
        source_commit="seed-contract-check",
        requested_by="changesafe-seed",
    )
    port = LiveDataHubContext(
        runner=AgentContextToolRunner.connect(gms_url.rstrip("/"), token),
        allowlist={TARGET},
        timeout_seconds=8,
        retry_count=1,
    )
    context = await port.load(change)
    if context.provenance.mode is not ContextMode.LIVE:
        raise RuntimeError("Seed verification did not use live DataHub context")
    expected_downstream = {
        CUSTOMER_360,
        CAMPAIGN_AUDIENCES,
        CONTACT_QUEUE,
        DASHBOARD,
    }
    if {asset.urn for asset in context.downstream_assets} != expected_downstream:
        raise RuntimeError("Seed verification requires the exact downstream graph")
    if not context.upstream_assets or not context.queries:
        raise RuntimeError("Seed verification did not return lineage and query usage")
    if PII_TAG not in context.field_tags:
        raise RuntimeError("Seed verification did not return field governance")
    expected_owners = {
        (TECHNICAL_OWNER, "TECHNICAL_OWNER"),
        (OWNER, "DATA_OWNER"),
    }
    actual_owners = {
        (owner.urn, owner.ownership_type) for owner in context.owners
    }
    if actual_owners != expected_owners:
        raise RuntimeError("Seed verification requires both documented owners")
    risk = score_change(change, context)
    if risk.score != 90:
        raise RuntimeError(f"Seed verification expected risk 90, received {risk.score}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Print, apply, and verify the deterministic DataHub seed graph."
    )
    parser.add_argument(
        "--compact", action="store_true", help="Emit compact JSON for automation."
    )
    parser.add_argument(
        "--apply", action="store_true", help="Apply stable UPSERT proposals."
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Run the post-seed live contract check without applying proposals.",
    )
    parser.add_argument(
        "--no-verify",
        action="store_true",
        help="Skip the post-apply contract check (not recommended).",
    )
    parser.add_argument("--gms-url", default=os.getenv("DATAHUB_GMS_URL"))
    parser.add_argument("--token", default=os.getenv("DATAHUB_GMS_TOKEN"))
    parser.add_argument(
        "--env-file",
        type=Path,
        help=(
            "Private env file. Defaults to CHANGESAFE_ENV_FILE or the prepared "
            "laptop path."
        ),
    )
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
        print(f"Applied {len(proposals)} idempotent DataHub aspect upserts.")

    if args.verify_only or not args.no_verify:
        asyncio.run(verify_seed(gms_url, token))
        print("Verified the live ChangeSafe DataHub seed contract.")


if __name__ == "__main__":
    main()
