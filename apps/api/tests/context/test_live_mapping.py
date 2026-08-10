import asyncio
import threading
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any

import pytest

from changesafe.context.base import (
    ContextAuthorizationError,
    ContextLoadError,
    ContextTimeoutError,
    ContextTransportError,
    DecisionWriteback,
)
from changesafe.context.live import AgentContextToolRunner, LiveDataHubContext
from changesafe.domain import (
    ChangeOperation,
    ChangeRequest,
    ContextMode,
    LineagePrecision,
    RiskBand,
)
from changesafe.risk import score_change

TARGET = "urn:li:dataset:(urn:li:dataPlatform:dbt,analytics.dim_customers,PROD)"
DOWNSTREAM_URNS = [
    "urn:li:dataset:(urn:li:dataPlatform:snowflake,analytics.customer_360,PROD)",
    (
        "urn:li:dataset:(urn:li:dataPlatform:snowflake,"
        "marketing.campaign_audiences,PROD)"
    ),
    (
        "urn:li:dataset:(urn:li:dataPlatform:snowflake,"
        "support.customer_contact_queue,PROD)"
    ),
    "urn:li:dashboard:(looker,customer_retention_dashboard)",
]


class FakeRunner:
    def __init__(
        self,
        results: Mapping[
            str, Any | Callable[[dict[str, Any]], Any]
        ],
    ) -> None:
        self.results = results
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def call(self, tool: str, **parameters: Any) -> Any:
        self.calls.append((tool, parameters))
        result = self.results[tool]
        return result(parameters) if callable(result) else result


class FailureRunner:
    def __init__(self, failure: Exception) -> None:
        self.failure = failure
        self.calls = 0

    async def call(self, tool: str, **parameters: Any) -> Any:
        del tool, parameters
        self.calls += 1
        raise self.failure


class HangingRunner:
    def __init__(self) -> None:
        self.calls = 0

    async def call(self, tool: str, **parameters: Any) -> Any:
        del tool, parameters
        self.calls += 1
        await asyncio.Event().wait()


class HttpStatusFailure(Exception):
    def __init__(self, status_code: int) -> None:
        super().__init__("private upstream response")
        self.response = type("Response", (), {"status_code": status_code})()


def golden_change() -> ChangeRequest:
    return ChangeRequest(
        asset_urn=TARGET,
        operation=ChangeOperation.RENAME,
        field="customer_email",
        new_field="primary_email",
        source_commit="demo-unsafe-change",
        requested_by="demo-user",
    )


@pytest.mark.asyncio
async def test_live_schema_discovery_returns_complete_allowlisted_schema() -> None:
    runner = FakeRunner(
        {
            "get_entities": {"entities": [{"urn": TARGET, "name": "order_details"}]},
            "list_schema_fields": {
                "urn": TARGET,
                "fields": [
                    {
                        "fieldPath": "order_id",
                        "nativeDataType": "NUMBER",
                        "nullable": False,
                    },
                    {
                        "fieldPath": "customer_email",
                        "nativeDataType": "TEXT",
                        "nullable": True,
                    },
                ],
                "totalFields": 2,
                "returned": 2,
                "remainingCount": 0,
                "offset": 0,
            },
        }
    )
    port = LiveDataHubContext(runner, {TARGET})

    catalog = await port.discover_schema(TARGET)

    assert catalog.target_urn == TARGET
    assert catalog.target_name == "order_details"
    assert [
        (item.name, item.data_type, item.nullable) for item in catalog.schema_fields
    ] == [
        ("order_id", "NUMBER", False),
        ("customer_email", "TEXT", True),
    ]
    assert catalog.provenance.mode is ContextMode.LIVE
    assert [call[0] for call in runner.calls] == [
        "get_entities",
        "list_schema_fields",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["discover", "load"])
async def test_live_adapter_rejects_entity_for_a_different_target(
    operation: str,
) -> None:
    wrong_urn = "urn:li:dataset:(urn:li:dataPlatform:dbt,finance.wrong,PROD)"
    runner = FakeRunner(
        {"get_entities": [{"urn": wrong_urn, "name": "wrong"}]}
    )
    port = LiveDataHubContext(runner, {TARGET})

    with pytest.raises(ContextLoadError, match="requested target"):
        if operation == "discover":
            await port.discover_schema(TARGET)
        else:
            await port.load(golden_change())

    assert [tool for tool, _ in runner.calls] == ["get_entities"]


@pytest.mark.asyncio
async def test_live_discovery_rejects_multiple_entities_for_one_requested_target(
) -> None:
    runner = FakeRunner(
        {
            "get_entities": [
                {"urn": TARGET, "name": "order_details"},
                {"urn": TARGET, "name": "duplicate_order_details"},
            ]
        }
    )

    with pytest.raises(ContextLoadError, match="exactly one"):
        await LiveDataHubContext(runner, {TARGET}).discover_schema(TARGET)

    assert [tool for tool, _ in runner.calls] == ["get_entities"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "identity_fields",
    [
        {},
        {"urn": TARGET, "datasetUrn": TARGET},
    ],
)
async def test_schema_page_requires_one_explicit_exact_root_identity(
    identity_fields: dict[str, str],
) -> None:
    runner = FakeRunner(
        {
            "get_entities": [{"urn": TARGET, "name": "dim_customers"}],
            "list_schema_fields": {
                **identity_fields,
                "fields": [
                    {"fieldPath": "customer_email", "nativeDataType": "STRING"}
                ],
                "totalFields": 1,
                "returned": 1,
                "remainingCount": 0,
                "offset": 0,
            },
        }
    )

    with pytest.raises(ContextLoadError, match=r"schema.*root identity"):
        await LiveDataHubContext(runner, {TARGET}).discover_schema(TARGET)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bound_entity_response",
    [
        [{"name": "identity-missing"}],
        [{"urn": "urn:li:dataset:wrong", "name": "wrong"}],
        [
            {"urn": TARGET, "name": "first"},
            {"urn": TARGET, "name": "second"},
        ],
    ],
)
async def test_each_lineage_page_requires_exact_entity_scoped_root_binding(
    bound_entity_response: list[dict[str, str]],
) -> None:
    entity_calls = 0

    def entities(_parameters: dict[str, Any]) -> list[dict[str, str]]:
        nonlocal entity_calls
        entity_calls += 1
        if entity_calls == 1:
            return [{"urn": TARGET, "name": "dim_customers"}]
        return bound_entity_response

    runner = FakeRunner(
        {
            "get_entities": entities,
            "list_schema_fields": {
                "urn": TARGET,
                "fields": [
                    {"fieldPath": "customer_email", "nativeDataType": "STRING"}
                ],
                "totalFields": 1,
                "returned": 1,
                "remainingCount": 0,
                "offset": 0,
            },
            "get_lineage": {
                "upstreams": {
                    "searchResults": [],
                    "total": 0,
                    "returned": 0,
                    "hasMore": False,
                    "offset": 0,
                }
            },
            "get_dataset_queries": {"total": 0, "queries": []},
        }
    )

    with pytest.raises(ContextLoadError, match=r"lineage.*root identity"):
        await LiveDataHubContext(runner, {TARGET}).load(golden_change())

    assert all(tool != "get_dataset_queries" for tool, _ in runner.calls)


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["discover", "load"])
async def test_live_adapter_rejects_schema_for_a_different_target(
    operation: str,
) -> None:
    wrong_urn = "urn:li:dataset:(urn:li:dataPlatform:dbt,finance.wrong,PROD)"
    runner = FakeRunner(
        {
            "get_entities": [{"urn": TARGET, "name": "order_details"}],
            "list_schema_fields": {
                "urn": wrong_urn,
                "fields": [
                    {"fieldPath": "customer_email", "nativeDataType": "STRING"}
                ],
                "totalFields": 1,
                "returned": 1,
                "remainingCount": 0,
            },
        }
    )
    port = LiveDataHubContext(runner, {TARGET})

    with pytest.raises(ContextLoadError, match=r"schema.*requested target"):
        if operation == "discover":
            await port.discover_schema(TARGET)
        else:
            await port.load(golden_change())

    assert [tool for tool, _ in runner.calls] == [
        "get_entities",
        "list_schema_fields",
    ]


@pytest.mark.asyncio
async def test_live_schema_discovery_rejects_non_allowlisted_asset_before_tool_calls(
) -> None:
    runner = FakeRunner({})
    port = LiveDataHubContext(runner, {TARGET})

    with pytest.raises(PermissionError, match="allowlist"):
        await port.discover_schema("urn:li:dataset:outside-allowlist")

    assert runner.calls == []


@pytest.mark.asyncio
async def test_live_schema_discovery_rejects_duplicate_case_insensitive_fields(
) -> None:
    runner = FakeRunner(
        {
            "get_entities": [{"urn": TARGET, "name": "orders"}],
            "list_schema_fields": {
                "urn": TARGET,
                "fields": [
                    {"fieldPath": "order_id", "nativeDataType": "NUMBER"},
                    {"fieldPath": "ORDER_ID", "nativeDataType": "NUMBER"},
                ],
                "totalFields": 2,
                "returned": 2,
                "remainingCount": 0,
            },
        }
    )

    with pytest.raises(ContextLoadError, match="duplicate field identifiers"):
        await LiveDataHubContext(runner, {TARGET}).discover_schema(TARGET)


@pytest.mark.asyncio
async def test_live_schema_discovery_rejects_quoted_top_level_field() -> None:
    runner = FakeRunner(
        {
            "get_entities": [{"urn": TARGET, "name": "orders"}],
            "list_schema_fields": {
                "urn": TARGET,
                "fields": [
                    {"fieldPath": '"order id"', "nativeDataType": "NUMBER"}
                ],
                "totalFields": 1,
                "returned": 1,
                "remainingCount": 0,
            },
        }
    )

    with pytest.raises(ContextLoadError, match="unsupported top-level"):
        await LiveDataHubContext(runner, {TARGET}).discover_schema(TARGET)


@pytest.mark.asyncio
async def test_live_schema_discovery_ignores_identified_nested_paths() -> None:
    runner = FakeRunner(
        {
            "get_entities": [{"urn": TARGET, "name": "orders"}],
            "list_schema_fields": {
                "urn": TARGET,
                "fields": [
                    {"fieldPath": "order_id", "nativeDataType": "NUMBER"},
                    {
                        "fieldPath": "shipping.address",
                        "nativeDataType": "STRUCT",
                        "jsonPath": "$.shipping.address",
                    },
                ],
                "totalFields": 2,
                "returned": 2,
                "remainingCount": 0,
            },
        }
    )

    catalog = await LiveDataHubContext(runner, {TARGET}).discover_schema(TARGET)

    assert [field.name for field in catalog.schema_fields] == ["order_id"]


@pytest.mark.asyncio
async def test_live_schema_discovery_rejects_missing_native_type() -> None:
    runner = FakeRunner(
        {
            "get_entities": [{"urn": TARGET, "name": "orders"}],
            "list_schema_fields": {
                "urn": TARGET,
                "fields": [{"fieldPath": "order_id", "nativeDataType": None}],
                "totalFields": 1,
                "returned": 1,
                "remainingCount": 0,
            },
        }
    )

    with pytest.raises(ContextLoadError, match="concrete native type"):
        await LiveDataHubContext(runner, {TARGET}).discover_schema(TARGET)


@pytest.mark.asyncio
async def test_live_schema_discovery_fetches_every_schema_page() -> None:
    def schema_page(parameters: dict[str, Any]) -> dict[str, Any]:
        offset = parameters["offset"]
        if offset == 0:
            return {
                "urn": TARGET,
                "fields": [{"fieldPath": "order_id", "nativeDataType": "NUMBER"}],
                "totalFields": 2,
                "returned": 1,
                "remainingCount": 1,
                "offset": 0,
            }
        if offset == 1:
            return {
                "urn": TARGET,
                "fields": [
                    {"fieldPath": "customer_email", "nativeDataType": "TEXT"}
                ],
                "totalFields": 2,
                "returned": 1,
                "remainingCount": 0,
                "offset": 1,
            }
        raise AssertionError(f"unexpected schema offset {offset}")

    runner = FakeRunner(
        {
            "get_entities": [{"urn": TARGET, "name": "orders"}],
            "list_schema_fields": schema_page,
        }
    )

    catalog = await LiveDataHubContext(runner, {TARGET}).discover_schema(TARGET)

    assert [field.name for field in catalog.schema_fields] == [
        "order_id",
        "customer_email",
    ]
    schema_calls = [
        parameters for tool, parameters in runner.calls if tool == "list_schema_fields"
    ]
    assert [call["offset"] for call in schema_calls] == [0, 1]


@pytest.mark.asyncio
async def test_live_schema_discovery_rejects_complete_page_with_missing_fields(
) -> None:
    runner = FakeRunner(
        {
            "get_entities": [{"urn": TARGET, "name": "orders"}],
            "list_schema_fields": {
                "urn": TARGET,
                "fields": [{"fieldPath": "order_id", "nativeDataType": "NUMBER"}],
                "totalFields": 2,
                "returned": 2,
                "remainingCount": 0,
                "offset": 0,
            },
        }
    )

    with pytest.raises(ContextLoadError, match="schema field page was inconsistent"):
        await LiveDataHubContext(runner, {TARGET}).discover_schema(TARGET)


@pytest.mark.asyncio
async def test_live_adapter_classifies_lineage_evidence_precision() -> None:
    direct_urn = "urn:li:dataset:(urn:li:dataPlatform:dbt,analytics.stg_orders,PROD)"
    endpoint_urn = "urn:li:dashboard:(looker,customer_health)"
    dataset_urn = "urn:li:dashboard:(tableau,customer_growth)"

    def lineage_result(parameters: dict[str, Any]) -> dict[str, Any]:
        direction = "upstreams" if parameters["upstream"] else "downstreams"
        if parameters["upstream"]:
            results = [
                {
                    "entity": {
                        "urn": direct_urn,
                        "name": "stg_orders",
                        "type": "DATASET",
                        "field": "customer_email",
                    },
                    "degree": 1,
                }
            ]
        elif parameters["column"] is not None:
            results = [
                {
                    "entity": {
                        "urn": endpoint_urn,
                        "name": "customer_health",
                        "type": "DASHBOARD",
                        "field": "customer_email",
                    },
                    "degree": 2,
                    "lineagePath": [TARGET, endpoint_urn],
                }
            ]
        else:
            results = [
                {
                    "entity": {
                        "urn": dataset_urn,
                        "name": "customer_growth",
                        "type": "DASHBOARD",
                    },
                    "degree": 1,
                }
            ]
        return {
            direction: {
                "searchResults": results,
                "total": len(results),
                "returned": len(results),
                "hasMore": False,
            }
        }

    runner = FakeRunner(
        {
            "get_entities": [{"urn": TARGET, "name": "dim_customers"}],
            "list_schema_fields": {
                "urn": TARGET,
                "fields": [
                    {"fieldPath": "customer_email", "nativeDataType": "STRING"}
                ],
                "totalFields": 1,
                "returned": 1,
                "remainingCount": 0,
            },
            "get_lineage": lineage_result,
            "get_dataset_queries": {"queries": []},
        }
    )

    context = await LiveDataHubContext(runner, {TARGET}).load(golden_change())

    assert context.upstream_assets[0].lineage_precision is LineagePrecision.EXACT_FIELD
    assert context.downstream_assets[0].lineage_precision is (
        LineagePrecision.ENDPOINT_FIELD
    )
    assert context.downstream_assets[1].lineage_precision is (
        LineagePrecision.DATASET_LEVEL
    )


@pytest.mark.asyncio
async def test_live_adapter_treats_blank_lineage_field_as_dataset_level() -> None:
    upstream_urn = "urn:li:dataset:(urn:li:dataPlatform:dbt,analytics.stg_orders,PROD)"

    def lineage_result(parameters: dict[str, Any]) -> dict[str, Any]:
        direction = "upstreams" if parameters["upstream"] else "downstreams"
        results = (
            [
                {
                    "entity": {
                        "urn": upstream_urn,
                        "name": "stg_orders",
                        "type": "DATASET",
                        "field": "",
                    },
                    "degree": 1,
                }
            ]
            if parameters["upstream"]
            else []
        )
        return {
            direction: {
                "searchResults": results,
                "total": len(results),
                "returned": len(results),
                "hasMore": False,
            }
        }

    runner = FakeRunner(
        {
            "get_entities": [{"urn": TARGET, "name": "dim_customers"}],
            "list_schema_fields": {
                "urn": TARGET,
                "fields": [
                    {"fieldPath": "customer_email", "nativeDataType": "STRING"}
                ],
                "totalFields": 1,
                "returned": 1,
                "remainingCount": 0,
            },
            "get_lineage": lineage_result,
            "get_dataset_queries": {"queries": []},
        }
    )

    context = await LiveDataHubContext(runner, {TARGET}).load(golden_change())

    assert context.upstream_assets[0].field is None
    assert context.upstream_assets[0].lineage_precision is (
        LineagePrecision.DATASET_LEVEL
    )


@pytest.mark.asyncio
async def test_live_adapter_uses_only_selected_field_governance() -> None:
    runner = FakeRunner(
        {
            "get_entities": [
                {
                    "urn": TARGET,
                    "name": "dim_customers",
                    "tags": {"tags": [{"tag": {"urn": "urn:li:tag:PII"}}]},
                    "glossaryTerms": {
                        "terms": [
                            {"term": {"urn": "urn:li:glossaryTerm:Customer"}}
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
                                {"tag": {"urn": "urn:li:tag:DataQuality"}}
                            ]
                        },
                        "glossaryTerms": {
                            "terms": [
                                {
                                    "term": {
                                        "urn": "urn:li:glossaryTerm:EmailQuality"
                                    }
                                }
                            ]
                        },
                    }
                ],
                "totalFields": 1,
                "returned": 1,
                "remainingCount": 0,
            },
            "get_lineage": {"relationships": []},
            "get_dataset_queries": {"queries": []},
        }
    )

    context = await LiveDataHubContext(runner, {TARGET}).load(golden_change())

    assert context.field_tags == ["urn:li:tag:DataQuality"]
    assert context.glossary_terms == ["urn:li:glossaryTerm:EmailQuality"]
    governance_urns = [
        evidence.urn for evidence in context.evidence if evidence.kind == "governance"
    ]
    assert governance_urns == [
        "urn:li:tag:DataQuality",
        "urn:li:glossaryTerm:EmailQuality",
    ]


@pytest.mark.asyncio
async def test_live_adapter_maps_agent_context_tool_envelopes() -> None:
    downstream = [
        {
            "urn": urn,
            "name": name,
            "entityType": (
                "dashboard"
                if urn.startswith("urn:li:dashboard:")
                else "dataset"
            ),
            "domain": domain,
            "field": "customer_email",
            "lineagePath": [TARGET, urn],
        }
        for urn, (name, domain) in zip(
            DOWNSTREAM_URNS,
            [
                ("customer_360", "Analytics"),
                ("campaign_audiences", "Marketing"),
                ("customer_contact_queue", "Support"),
                ("customer_retention_dashboard", "Executive Reporting"),
            ],
            strict=True,
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
                            "type": "DATAOWNER",
                        }
                    ],
                    "tags": [{"urn": "urn:li:tag:PII"}],
                    "glossaryTerms": [{"urn": "urn:li:glossaryTerm:CustomerEmail"}],
                }
            ],
            "list_schema_fields": {
                "urn": TARGET,
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
    assert context.downstream_assets[0].lineage_path == [
        TARGET,
        DOWNSTREAM_URNS[0],
    ]
    assert context.owners[0].ownership_type == "DATA_OWNER"
    assert context.usage_tier == "high"
    assert [call[0] for call in runner.calls] == [
        "get_entities",
        "list_schema_fields",
        "get_lineage",
        "get_entities",
        "get_lineage",
        "get_entities",
        "get_lineage",
        "get_entities",
        "get_dataset_queries",
    ]

    lineage = runner.results["get_lineage"]
    assert isinstance(lineage, dict)
    relationships = lineage["relationships"]
    assert isinstance(relationships, list)
    relationships[0]["urn"] = "urn:li:dataset:unexpected"

    changed_context = await port.load(golden_change())

    assert {asset.urn for asset in changed_context.downstream_assets} != set(
        DOWNSTREAM_URNS
    )


@pytest.mark.asyncio
async def test_live_adapter_fetches_every_schema_page_before_analysis() -> None:
    def schema_page(parameters: dict[str, Any]) -> dict[str, Any]:
        offset = parameters["offset"]
        if offset == 0:
            return {
                "urn": TARGET,
                "fields": [
                    {
                        "fieldPath": "customer_email",
                        "nativeDataType": "STRING",
                    }
                ],
                "totalFields": 2,
                "returned": 1,
                "remainingCount": 1,
                "offset": 0,
            }
        if offset == 1:
            return {
                "urn": TARGET,
                "fields": [
                    {"fieldPath": "customer_id", "nativeDataType": "BIGINT"}
                ],
                "totalFields": 2,
                "returned": 1,
                "remainingCount": 0,
                "offset": 1,
            }
        raise AssertionError(f"unexpected schema offset {offset}")

    runner = FakeRunner(
        {
            "get_entities": [{"urn": TARGET, "name": "dim_customers"}],
            "list_schema_fields": schema_page,
            "get_lineage": {"relationships": []},
            "get_dataset_queries": {"queries": []},
        }
    )

    context = await LiveDataHubContext(
        runner=runner, allowlist={TARGET}
    ).load(golden_change())

    assert [field.name for field in context.schema_fields] == [
        "customer_email",
        "customer_id",
    ]
    assert [
        parameters["offset"]
        for tool, parameters in runner.calls
        if tool == "list_schema_fields"
    ] == [0, 1]
    assert [
        item.result_count
        for item in context.tool_evidence
        if item.tool == "list_schema_fields"
    ] == [1, 1]


@pytest.mark.asyncio
async def test_live_adapter_maps_installed_agent_context_1_7_envelopes() -> None:
    downstream = [
        {
            "entity": {
                "urn": urn,
                "name": name,
                "type": (
                    "DASHBOARD"
                    if urn.startswith("urn:li:dashboard:")
                    else "DATASET"
                ),
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
        for urn, (name, domain) in zip(
            DOWNSTREAM_URNS,
            [
                ("customer_360", "Analytics"),
                ("campaign_audiences", "Marketing"),
                ("customer_contact_queue", "Support"),
                ("customer_retention_dashboard", "Executive Reporting"),
            ],
            strict=True,
        )
        ]
    downstream[0]["degree"] = 2

    def lineage_result(parameters: dict[str, Any]) -> dict[str, Any]:
        if parameters["upstream"]:
            return {
                "upstreams": {
                    "searchResults": [
                        {
                            "entity": {
                                "urn": (
                                    "urn:li:dataset:(urn:li:dataPlatform:dbt,"
                                    "analytics.stg_customers,PROD)"
                                ),
                                "name": "stg_customers",
                                "type": "DATASET",
                            },
                            "degree": 1,
                            "lineageColumns": ["customer_email"],
                        }
                    ],
                    "total": 1,
                    "returned": 1,
                    "hasMore": False,
                }
            }
        results = downstream if parameters["column"] is None else downstream[:-1]
        return {
            "downstreams": {
                "searchResults": results,
                "total": len(results),
                "returned": len(results),
                "hasMore": False,
            },
            "metadata": {
                "queryType": (
                    "dataset-level-lineage"
                    if parameters["column"] is None
                    else "column-level-lineage"
                )
            },
        }

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
                                    "type": "OWNERSHIP_TYPE",
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
                    "structuredProperties": {
                        "properties": [
                            {
                                "structuredProperty": {
                                    "urn": (
                                        "urn:li:structuredProperty:"
                                        "changesafe.riskLevel"
                                    )
                                },
                                "values": [{"stringValue": "CRITICAL"}],
                            },
                            {
                                "structuredProperty": {
                                    "urn": "urn:li:structuredProperty:qualityScore"
                                },
                                "values": [{"numberValue": 98.5}],
                            },
                        ]
                    },
                }
            ],
            "list_schema_fields": {
                "urn": TARGET,
                "fields": [
                        {
                            "fieldPath": "customer_email",
                            "nativeDataType": None,
                            "type": "STRING",
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
                    },
                    {
                        "fieldPath": "address.city",
                        "nativeDataType": "STRING",
                        "jsonPath": "$.address.city",
                    },
                ],
                "totalFields": 2,
                "returned": 2,
                "remainingCount": 0,
                "offset": 0,
            },
            "get_lineage": lineage_result,
            "get_dataset_queries": {
                "total": 1,
                "start": 0,
                "count": 1,
                "queries": [
                    {
                        "urn": "urn:li:query:q1",
                        "properties": {
                            "statement": {
                                "value": "SENSITIVE_QUERY_TEXT_SENTINEL",
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
    assert [field.name for field in context.schema_fields] == ["customer_email"]
    assert len(context.downstream_assets) == 4
    assert context.upstream_assets[0].name == "stg_customers"
    assert context.upstream_assets[0].lineage_degree == 1
    assert context.upstream_assets[0].lineage_path == []
    assert context.downstream_assets[0].field == "customer_email"
    assert context.downstream_assets[0].lineage_degree == 2
    assert context.downstream_assets[0].lineage_path == []
    assert context.model_dump()["downstream_assets"][0]["lineage_degree"] == 2
    serialized_context = context.model_dump_json()
    assert "queries" not in context.model_dump()
    assert "SENSITIVE_QUERY_TEXT_SENTINEL" not in serialized_context
    assert context.query_count == 1
    assert context.usage_tier == "high"
    assert context.structured_properties == {
        "urn:li:structuredProperty:changesafe.riskLevel": ["CRITICAL"],
        "urn:li:structuredProperty:qualityScore": [98.5],
    }
    assert context.evidence[0].label == "customer_email STRING"
    assert [item.result_count for item in context.tool_evidence] == [
        1,
        2,
        1,
        1,
        3,
        1,
        4,
        1,
        1,
    ]
    assert score_change(golden_change(), context).score == 90


@pytest.mark.asyncio
async def test_live_adapter_fails_closed_for_unsupported_top_level_identifier() -> None:
    runner = FakeRunner(
        {
            "get_entities": [{"urn": TARGET, "name": "dim_customers"}],
            "list_schema_fields": {
                "urn": TARGET,
                "fields": [
                    {"fieldPath": "customer_email", "nativeDataType": "STRING"},
                    {"fieldPath": "Order Date", "nativeDataType": "DATE"},
                ],
                "totalFields": 2,
                "returned": 2,
                "remainingCount": 0,
            },
            "get_lineage": {"relationships": []},
            "get_dataset_queries": {"queries": []},
        }
    )

    with pytest.raises(ContextLoadError, match="unsupported top-level"):
        await LiveDataHubContext(runner=runner, allowlist={TARGET}).load(
            golden_change()
        )


@pytest.mark.asyncio
async def test_live_adapter_fails_closed_when_native_type_is_missing() -> None:
    runner = FakeRunner(
        {
            "get_entities": [{"urn": TARGET, "name": "dim_customers"}],
            "list_schema_fields": {
                "urn": TARGET,
                "fields": [{"fieldPath": "customer_email", "nativeDataType": None}],
                "totalFields": 1,
                "returned": 1,
                "remainingCount": 0,
            },
            "get_lineage": {"relationships": []},
            "get_dataset_queries": {"queries": []},
        }
    )

    with pytest.raises(ContextLoadError, match="concrete native type"):
        await LiveDataHubContext(runner=runner, allowlist={TARGET}).load(
            golden_change()
        )


@pytest.mark.asyncio
async def test_live_adapter_fetches_every_lineage_page_before_analysis() -> None:
    dashboard_urns = [
        "urn:li:dashboard:(looker,customer_health)",
        "urn:li:dashboard:(tableau,customer_growth)",
    ]

    def lineage_page(parameters: dict[str, Any]) -> dict[str, Any]:
        direction = "upstreams" if parameters["upstream"] else "downstreams"
        if parameters["column"] is not None or parameters["upstream"]:
            return {
                direction: {
                    "searchResults": [],
                    "total": 0,
                    "returned": 0,
                    "hasMore": False,
                    "offset": parameters["offset"],
                }
            }

        offset = parameters["offset"]
        if offset not in (0, 1):
            raise AssertionError(f"unexpected lineage offset {offset}")
        urn = dashboard_urns[offset]
        return {
            "downstreams": {
                "searchResults": [
                    {
                        "entity": {
                            "urn": urn,
                            "name": urn.rsplit(",", 1)[-1].rstrip(")"),
                            "type": "DASHBOARD",
                        },
                        "degree": offset + 1,
                    }
                ],
                "total": 2,
                "returned": 1,
                "hasMore": offset == 0,
                "offset": offset,
            }
        }

    runner = FakeRunner(
        {
            "get_entities": [{"urn": TARGET, "name": "dim_customers"}],
            "list_schema_fields": {
                "urn": TARGET,
                "fields": [
                    {
                        "fieldPath": "customer_email",
                        "nativeDataType": "STRING",
                    }
                ],
                "totalFields": 1,
                "returned": 1,
                "remainingCount": 0,
            },
            "get_lineage": lineage_page,
            "get_dataset_queries": {"queries": []},
        }
    )

    context = await LiveDataHubContext(
        runner=runner, allowlist={TARGET}
    ).load(golden_change())

    assert [asset.urn for asset in context.downstream_assets] == dashboard_urns
    asset_lineage_calls = [
        parameters
        for tool, parameters in runner.calls
        if tool == "get_lineage" and parameters["column"] is None
    ]
    assert [call["offset"] for call in asset_lineage_calls] == [0, 1]
    assert asset_lineage_calls[1]["max_results"] == 2


@pytest.mark.asyncio
async def test_seeded_live_lineage_fails_closed_when_page_is_partial() -> None:
    runner = FakeRunner(
        {
            "get_entities": [{"urn": TARGET, "name": "dim_customers"}],
            "list_schema_fields": {
                "urn": TARGET,
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
@pytest.mark.parametrize("page_fault", ["empty", "repeated", "changed_total"])
async def test_live_adapter_fails_closed_on_empty_repeated_or_inconsistent_pages(
    page_fault: str,
) -> None:
    endpoint = "urn:li:dashboard:(looker,customer_health)"

    def lineage_page(parameters: dict[str, Any]) -> dict[str, Any]:
        direction = "upstreams" if parameters["upstream"] else "downstreams"
        if parameters["upstream"] or parameters["column"] is not None:
            return {
                direction: {
                    "searchResults": [],
                    "total": 0,
                    "returned": 0,
                    "hasMore": False,
                    "offset": 0,
                }
            }
        if parameters["offset"] == 0:
            return {
                direction: {
                    "searchResults": [
                        {
                            "entity": {
                                "urn": endpoint,
                                "name": "customer_health",
                                "type": "DASHBOARD",
                            },
                            "degree": 1,
                        }
                    ],
                    "total": 2,
                    "returned": 1,
                    "hasMore": True,
                    "offset": 0,
                }
            }
        results = [] if page_fault == "empty" else [
            {
                "entity": {
                    "urn": endpoint,
                    "name": "customer_health",
                    "type": "DASHBOARD",
                },
                "degree": 1,
            }
        ]
        return {
            direction: {
                "searchResults": results,
                "total": 3 if page_fault == "changed_total" else 2,
                "returned": len(results),
                "hasMore": False,
                "offset": 1,
            }
        }

    runner = FakeRunner(
        {
            "get_entities": [{"urn": TARGET, "name": "dim_customers"}],
            "list_schema_fields": {
                "urn": TARGET,
                "fields": [
                    {"fieldPath": "customer_email", "nativeDataType": "STRING"}
                ],
                "totalFields": 1,
                "returned": 1,
                "remainingCount": 0,
            },
            "get_lineage": lineage_page,
            "get_dataset_queries": {"queries": []},
        }
    )

    with pytest.raises(ContextLoadError, match="lineage"):
        await LiveDataHubContext(runner, {TARGET}).load(golden_change())


@pytest.mark.asyncio
async def test_live_adapter_allows_distinct_relationships_to_one_endpoint() -> None:
    endpoint = "urn:li:dashboard:(looker,customer_health)"

    def lineage_result(parameters: dict[str, Any]) -> dict[str, Any]:
        direction = "upstreams" if parameters["upstream"] else "downstreams"
        relationships = []
        if not parameters["upstream"] and parameters["column"] is not None:
            relationships = [
                {
                    "entity": {
                        "urn": endpoint,
                        "name": "customer_health",
                        "type": "DASHBOARD",
                        "field": "customer_email",
                    },
                    "degree": 1,
                    "lineagePath": [TARGET, endpoint],
                },
                {
                    "entity": {
                        "urn": endpoint,
                        "name": "customer_health",
                        "type": "DASHBOARD",
                        "field": "backup_email",
                    },
                    "degree": 2,
                    "lineagePath": [TARGET, "urn:li:dataset:bridge", endpoint],
                },
            ]
        return {
            direction: {
                "searchResults": relationships,
                "total": len(relationships),
                "returned": len(relationships),
                "hasMore": False,
            }
        }

    runner = FakeRunner(
        {
            "get_entities": [{"urn": TARGET, "name": "dim_customers"}],
            "list_schema_fields": {
                "urn": TARGET,
                "fields": [
                    {"fieldPath": "customer_email", "nativeDataType": "STRING"}
                ],
                "totalFields": 1,
                "returned": 1,
                "remainingCount": 0,
            },
            "get_lineage": lineage_result,
            "get_dataset_queries": {"queries": []},
        }
    )

    context = await LiveDataHubContext(runner, {TARGET}).load(golden_change())

    assert [asset.urn for asset in context.downstream_assets] == [
        endpoint,
        endpoint,
    ]
    assert [asset.field for asset in context.downstream_assets] == [
        "customer_email",
        "backup_email",
    ]
    assert [asset.lineage_degree for asset in context.downstream_assets] == [1, 2]


@pytest.mark.asyncio
async def test_live_adapter_rejects_lineage_endpoint_without_an_urn() -> None:
    def lineage_result(parameters: dict[str, Any]) -> dict[str, Any]:
        direction = "upstreams" if parameters["upstream"] else "downstreams"
        results = []
        if not parameters["upstream"] and parameters["column"] is not None:
            results = [{"entity": {"name": "missing_urn"}, "degree": 1}]
        return {
            direction: {
                "searchResults": results,
                "total": len(results),
                "returned": len(results),
                "hasMore": False,
            }
        }

    runner = FakeRunner(
        {
            "get_entities": [{"urn": TARGET, "name": "dim_customers"}],
            "list_schema_fields": {
                "urn": TARGET,
                "fields": [
                    {"fieldPath": "customer_email", "nativeDataType": "STRING"}
                ],
                "totalFields": 1,
                "returned": 1,
                "remainingCount": 0,
            },
            "get_lineage": lineage_result,
            "get_dataset_queries": {"queries": []},
        }
    )

    with pytest.raises(ContextLoadError, match="missing its URN"):
        await LiveDataHubContext(runner, {TARGET}).load(golden_change())


@pytest.mark.asyncio
async def test_missing_optional_live_evidence_remains_explicit_and_conservative(
) -> None:
    runner = FakeRunner(
        {
            "get_entities": [{"urn": TARGET, "name": "dim_customers"}],
            "list_schema_fields": {
                "urn": TARGET,
                "fields": [
                    {"fieldPath": "customer_email", "nativeDataType": "STRING"}
                ],
                "totalFields": 1,
                "returned": 1,
                "remainingCount": 0,
            },
            "get_lineage": {"relationships": []},
            "get_dataset_queries": {"queries": []},
        }
    )

    context = await LiveDataHubContext(runner, {TARGET}).load(golden_change())
    risk = score_change(golden_change(), context)

    assert context.owners == []
    assert context.field_tags == []
    assert context.glossary_terms == []
    assert context.query_count == 0
    assert context.usage_tier == "none"
    assert [factor.code for factor in risk.factors] == [
        "base_rename",
        "missing_accountable_owner",
    ]


@pytest.mark.asyncio
async def test_live_adapter_rejects_non_allowlisted_asset_before_tool_calls() -> None:
    runner = FakeRunner({})
    port = LiveDataHubContext(runner=runner, allowlist={TARGET})
    change = golden_change().model_copy(update={"asset_urn": "urn:li:dataset:other"})

    with pytest.raises(PermissionError, match="allowlist"):
        await port.load(change)

    assert runner.calls == []


@pytest.mark.asyncio
async def test_live_adapter_rejects_unknown_field_before_lineage_or_query_calls(
) -> None:
    runner = FakeRunner(
        {
            "get_entities": [{"urn": TARGET, "name": "dim_customers"}],
            "list_schema_fields": {
                "urn": TARGET,
                "fields": [
                    {"fieldPath": "customer_email", "nativeDataType": "STRING"}
                ],
                "totalFields": 1,
                "returned": 1,
                "remainingCount": 0,
            },
        }
    )
    change = golden_change().model_copy(
        update={"field": "unknown_field", "new_field": "preferred_field"}
    )

    with pytest.raises(ContextLoadError, match="Target field is absent"):
        await LiveDataHubContext(runner=runner, allowlist={TARGET}).load(change)

    assert [tool for tool, _ in runner.calls] == [
        "get_entities",
        "list_schema_fields",
    ]


@pytest.mark.asyncio
async def test_live_adapter_bounds_timeout_and_performs_one_retry() -> None:
    runner = HangingRunner()
    port = LiveDataHubContext(
        runner=runner,
        allowlist={TARGET},
        timeout_seconds=0.01,
        retry_count=1,
    )

    with pytest.raises(ContextTimeoutError):
        await port.load(golden_change())

    assert runner.calls == 2


@pytest.mark.asyncio
async def test_live_adapter_does_not_retry_authorization_failure() -> None:
    runner = FailureRunner(PermissionError("private detail"))
    port = LiveDataHubContext(
        runner=runner,
        allowlist={TARGET},
        timeout_seconds=1,
        retry_count=1,
    )

    with pytest.raises(ContextAuthorizationError):
        await port.load(golden_change())

    assert runner.calls == 1


@pytest.mark.asyncio
async def test_live_adapter_detects_wrapped_http_authorization_failure() -> None:
    runner = FailureRunner(HttpStatusFailure(401))
    port = LiveDataHubContext(
        runner=runner,
        allowlist={TARGET},
        timeout_seconds=1,
        retry_count=1,
    )

    with pytest.raises(ContextAuthorizationError):
        await port.load(golden_change())

    assert runner.calls == 1


@pytest.mark.asyncio
async def test_live_adapter_types_transport_failure_after_retry() -> None:
    runner = FailureRunner(ConnectionError("private endpoint"))
    port = LiveDataHubContext(
        runner=runner,
        allowlist={TARGET},
        timeout_seconds=1,
        retry_count=1,
    )

    with pytest.raises(ContextTransportError):
        await port.load(golden_change())

    assert runner.calls == 2


@pytest.mark.asyncio
async def test_agent_runner_does_not_overlap_timed_out_sdk_threads() -> None:
    from datahub_agent_context.context import DataHubContext

    assert DataHubContext is not None
    entered = threading.Event()
    release = threading.Event()
    state_lock = threading.Lock()
    active = 0
    max_active = 0
    calls = 0

    def blocking_tool(**_parameters: Any) -> dict[str, bool]:
        nonlocal active, calls, max_active
        with state_lock:
            calls += 1
            active += 1
            max_active = max(max_active, active)
        entered.set()
        release.wait(timeout=1)
        with state_lock:
            active -= 1
        return {"success": True}

    runner = AgentContextToolRunner(
        client=object(), tools={"blocking_tool": blocking_tool}
    )
    try:
        first = asyncio.create_task(runner.call("blocking_tool"))
        assert await asyncio.to_thread(entered.wait, 0.5)
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(first, timeout=0.01)

        second = asyncio.create_task(runner.call("blocking_tool"))
        await asyncio.sleep(0.02)
        assert calls == 1
        assert max_active == 1
        release.set()
        await second

        assert calls == 2
        assert max_active == 1
    finally:
        release.set()
        runner.close()


def test_agent_runner_configures_sdk_timeout_and_disables_inner_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import datahub.sdk.main_client

    captured: dict[str, Any] = {}

    class FakeClient:
        def __init__(self, **kwargs: Any) -> None:
            captured.update(kwargs)

    monkeypatch.setattr(datahub.sdk.main_client, "DataHubClient", FakeClient)

    runner = AgentContextToolRunner.connect(
        "https://datahub.example.test",
        "private-token",
        timeout_seconds=3.5,
    )
    try:
        config = captured["config"]
        assert config.server == "https://datahub.example.test"
        assert config.timeout_sec == 3.5
        assert config.retry_max_times == 0
        assert config.pool_connections == 1
        assert config.pool_maxsize == 1
    finally:
        runner.close()


def decision() -> DecisionWriteback:
    return DecisionWriteback(
        run_id="0198f2b8-a68d-7af3-8958-cb18c7337e91",
        change=golden_change(),
        risk_score=90,
        risk_band=RiskBand.CRITICAL,
        artifact_hash="b" * 64,
        approved_at=datetime(2026, 8, 8, tzinfo=UTC),
        idempotency_key="f" * 64,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("bad_tool", "bad_response"),
    [
        ("save_document", None),
        ("save_document", {}),
        ("save_document", {"status": "ok"}),
        ("add_structured_properties", None),
        ("add_tags", None),
    ],
)
async def test_writeback_requires_explicit_positive_tool_acknowledgement(
    bad_tool: str, bad_response: Any
) -> None:
    document_urn = f"urn:li:document:changesafe-{'f' * 32}"
    results: dict[str, Any] = {
        "save_document": {"success": True, "urn": document_urn},
        "add_structured_properties": {"success": True},
        "add_tags": {"success": True},
    }
    results[bad_tool] = bad_response
    runner = FakeRunner(results)
    port = LiveDataHubContext(runner=runner, allowlist={TARGET}, retry_count=0)

    with pytest.raises(ContextLoadError, match="positive success acknowledgement"):
        await port.writeback(decision())


@pytest.mark.asyncio
async def test_writeback_applies_status_tag_to_the_readable_asset_entity() -> None:
    document_urn = f"urn:li:document:changesafe-{'f' * 32}"
    runner = FakeRunner(
        {
            "save_document": {"success": True, "urn": document_urn},
            "add_structured_properties": {"success": True},
            "add_tags": {"success": True},
        }
    )
    port = LiveDataHubContext(runner=runner, allowlist={TARGET}, retry_count=0)

    await port.writeback(decision())

    tag_parameters = next(
        parameters for tool, parameters in runner.calls if tool == "add_tags"
    )
    assert tag_parameters == {
        "tag_urns": ["urn:li:tag:ChangeSafe:Deprecating"],
        "entity_urns": [TARGET],
        "column_paths": [None],
    }
