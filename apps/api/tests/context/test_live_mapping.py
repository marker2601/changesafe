from collections.abc import Mapping
from typing import Any

import pytest

from changesafe.context.base import ContextLoadError
from changesafe.context.live import LiveDataHubContext
from changesafe.domain import ChangeOperation, ChangeRequest, ContextMode

TARGET = "urn:li:dataset:(urn:li:dataPlatform:dbt,analytics.dim_customers,PROD)"


class FakeRunner:
    def __init__(self, results: Mapping[str, Any]) -> None:
        self.results = results
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def call(self, tool: str, **parameters: Any) -> Any:
        self.calls.append((tool, parameters))
        return self.results[tool]


def golden_change() -> ChangeRequest:
    return ChangeRequest(
        asset_urn=TARGET,
        operation=ChangeOperation.RENAME,
        field="customer_email",
        new_field="primary_email",
        old_type="STRING",
        new_type="STRING",
        source_commit="demo-unsafe-change",
        requested_by="demo-user",
    )


@pytest.mark.asyncio
async def test_live_adapter_maps_agent_context_tool_envelopes() -> None:
    downstream = [
        {
            "urn": f"urn:li:dataset:asset-{index}",
            "name": name,
            "entityType": "dashboard" if index == 4 else "dataset",
            "domain": domain,
            "field": "customer_email",
            "lineagePath": [TARGET, f"urn:li:dataset:asset-{index}"],
        }
        for index, (name, domain) in enumerate(
            [
                ("customer_360", "Analytics"),
                ("campaign_audiences", "Marketing"),
                ("customer_contact_queue", "Support"),
                ("customer_retention_dashboard", "Executive Reporting"),
            ],
            start=1,
        )
    ]
    downstream[-1]["isExecutive"] = True
    runner = FakeRunner(
        {
            "get_entities": [
                {
                    "urn": TARGET,
                    "name": "dim_customers",
                    "domain": {"name": "Analytics"},
                    "owners": [
                        {
                            "urn": "urn:li:corpuser:customer-analytics",
                            "name": "Customer Analytics",
                            "type": "DATA_OWNER",
                        }
                    ],
                    "tags": [{"urn": "urn:li:tag:PII"}],
                    "glossaryTerms": [{"urn": "urn:li:glossaryTerm:CustomerEmail"}],
                }
            ],
            "list_schema_fields": {
                "fields": [
                    {
                        "fieldPath": "customer_email",
                        "type": "STRING",
                        "tags": [{"urn": "urn:li:tag:PII"}],
                    }
                ]
            },
            "get_lineage": {"relationships": downstream},
            "get_dataset_queries": {
                "usageTier": "high",
                "queries": [
                    {
                        "urn": "urn:li:query:customer-email-usage",
                        "query": "select customer_email from analytics.dim_customers",
                    }
                ],
            },
        }
    )
    port = LiveDataHubContext(runner=runner, allowlist={TARGET})

    context = await port.load(golden_change())

    assert context.provenance.mode is ContextMode.LIVE
    assert context.target_name == "dim_customers"
    assert context.field_type == "STRING"
    assert len(context.downstream_assets) == 4
    assert context.owners[0].ownership_type == "DATA_OWNER"
    assert context.usage_tier == "high"
    assert [call[0] for call in runner.calls] == [
        "get_entities",
        "list_schema_fields",
        "get_lineage",
        "get_dataset_queries",
    ]


@pytest.mark.asyncio
async def test_live_adapter_maps_installed_agent_context_1_7_envelopes() -> None:
    downstream = [
        {
            "entity": {
                "urn": f"urn:li:dataset:asset-{index}",
                "name": name,
                "type": "DASHBOARD" if index == 4 else "DATASET",
                "domain": {
                    "domain": {
                        "urn": f"urn:li:domain:{domain.lower().replace(' ', '-')}",
                        "properties": {"name": domain},
                    }
                },
            },
            "degree": 1,
            "lineageColumns": ["customer_email"],
        }
        for index, (name, domain) in enumerate(
            [
                ("customer_360", "Analytics"),
                ("campaign_audiences", "Marketing"),
                ("customer_contact_queue", "Support"),
                ("customer_retention_dashboard", "Executive Reporting"),
            ],
            start=1,
        )
    ]
    runner = FakeRunner(
        {
            "get_entities": [
                {
                    "urn": TARGET,
                    "name": "dim_customers",
                    "domain": {
                        "domain": {
                            "urn": "urn:li:domain:analytics",
                            "properties": {"name": "Analytics"},
                        }
                    },
                    "ownership": {
                        "owners": [
                            {
                                "owner": {
                                    "urn": "urn:li:corpuser:customer-analytics",
                                    "properties": {
                                        "displayName": "Customer Analytics"
                                    },
                                },
                                "ownershipType": {
                                    "urn": (
                                        "urn:li:ownershipType:"
                                        "__system__business_owner"
                                    ),
                                    "type": "BUSINESS_OWNER",
                                    "info": {"name": "Business Owner"},
                                },
                            }
                        ]
                    },
                    "tags": {
                        "tags": [
                            {
                                "tag": {
                                    "urn": "urn:li:tag:PII",
                                    "properties": {"name": "PII"},
                                }
                            }
                        ]
                    },
                }
            ],
            "list_schema_fields": {
                "urn": TARGET,
                "fields": [
                    {
                        "fieldPath": "customer_email",
                        "nativeDataType": "STRING",
                        "tags": {
                            "tags": [
                                {"tag": {"urn": "urn:li:tag:PII"}}
                            ]
                        },
                        "glossaryTerms": {
                            "terms": [
                                {
                                    "term": {
                                        "urn": (
                                            "urn:li:glossaryTerm:CustomerEmail"
                                        )
                                    }
                                }
                            ]
                        },
                    }
                ],
                "totalFields": 1,
                "returned": 1,
                "remainingCount": 0,
                "offset": 0,
            },
            "get_lineage": {
                "downstreams": {
                    "searchResults": downstream,
                    "total": 4,
                    "returned": 4,
                    "hasMore": False,
                },
                "metadata": {"queryType": "column-level-lineage"},
            },
            "get_dataset_queries": {
                "total": 1,
                "start": 0,
                "count": 1,
                "queries": [
                    {
                        "urn": "urn:li:query:q1",
                        "properties": {
                            "statement": {
                                "value": (
                                    "select customer_email from "
                                    "analytics.dim_customers"
                                ),
                                "language": "SQL",
                            },
                            "source": "SYSTEM",
                        },
                    }
                ],
            },
        }
    )

    context = await LiveDataHubContext(
        runner=runner, allowlist={TARGET}
    ).load(golden_change())

    assert context.target_domain == "Analytics"
    assert context.owners[0].name == "Customer Analytics"
    assert context.owners[0].ownership_type == "BUSINESS_OWNER"
    assert context.field_tags == ["urn:li:tag:PII"]
    assert context.glossary_terms == ["urn:li:glossaryTerm:CustomerEmail"]
    assert len(context.downstream_assets) == 4
    assert context.downstream_assets[0].field == "customer_email"
    assert context.queries == [
        "select customer_email from analytics.dim_customers"
    ]
    assert context.usage_tier == "high"


@pytest.mark.asyncio
async def test_seeded_live_lineage_fails_closed_when_page_is_partial() -> None:
    runner = FakeRunner(
        {
            "get_entities": [{"urn": TARGET, "name": "dim_customers"}],
            "list_schema_fields": {
                "fields": [
                    {"fieldPath": "customer_email", "nativeDataType": "STRING"}
                ],
                "totalFields": 1,
                "returned": 1,
                "remainingCount": 0,
            },
            "get_lineage": {
                "downstreams": {
                    "searchResults": [],
                    "total": 4,
                    "returned": 0,
                    "hasMore": True,
                }
            },
            "get_dataset_queries": {"total": 0, "queries": []},
        }
    )

    with pytest.raises(ContextLoadError, match="partial"):
        await LiveDataHubContext(runner=runner, allowlist={TARGET}).load(
            golden_change()
        )


@pytest.mark.asyncio
async def test_live_adapter_rejects_non_allowlisted_asset_before_tool_calls() -> None:
    runner = FakeRunner({})
    port = LiveDataHubContext(runner=runner, allowlist={TARGET})
    change = golden_change().model_copy(update={"asset_urn": "urn:li:dataset:other"})

    with pytest.raises(PermissionError, match="allowlist"):
        await port.load(change)

    assert runner.calls == []
