"""Define and optionally emit the reproducible synthetic ChangeSafe graph."""

from __future__ import annotations

import argparse
import json
from typing import Any

TARGET = "urn:li:dataset:(urn:li:dataPlatform:dbt,analytics.dim_customers,PROD)"


def build_seed_spec() -> dict[str, Any]:
    assets = [
        {
            "urn": (
                "urn:li:dataset:(urn:li:dataPlatform:postgres,sales.customers_raw,PROD)"
            ),
            "name": "customers_raw",
            "domain": "Sales",
        },
        {
            "urn": (
                "urn:li:dataset:(urn:li:dataPlatform:dbt,analytics.stg_customers,PROD)"
            ),
            "name": "stg_customers",
            "domain": "Analytics",
        },
        {"urn": TARGET, "name": "dim_customers", "domain": "Analytics"},
        {
            "urn": (
                "urn:li:dataset:(urn:li:dataPlatform:snowflake,"
                "analytics.customer_360,PROD)"
            ),
            "name": "customer_360",
            "domain": "Analytics",
        },
        {
            "urn": (
                "urn:li:dataset:(urn:li:dataPlatform:snowflake,"
                "marketing.campaign_audiences,PROD)"
            ),
            "name": "campaign_audiences",
            "domain": "Marketing",
        },
        {
            "urn": (
                "urn:li:dataset:(urn:li:dataPlatform:snowflake,"
                "support.customer_contact_queue,PROD)"
            ),
            "name": "customer_contact_queue",
            "domain": "Support",
        },
        {
            "urn": "urn:li:dashboard:(looker,customer_retention_dashboard)",
            "name": "customer_retention_dashboard",
            "domain": "Executive Reporting",
        },
    ]
    return {
        "assets": assets,
        "target": TARGET,
        "downstream_from_target": [item["urn"] for item in assets[3:]],
        "field": "customer_email",
        "field_type": "STRING",
        "tag": "urn:li:tag:ChangeSafe:Deprecating",
        "governance_tags": ["urn:li:tag:PII"],
        "glossary_terms": ["urn:li:glossaryTerm:CustomerEmail"],
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


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Print the deterministic DataHub seed specification."
    )
    parser.add_argument(
        "--compact", action="store_true", help="Emit compact JSON for automation."
    )
    args = parser.parse_args()
    print(
        json.dumps(
            build_seed_spec(),
            indent=None if args.compact else 2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
