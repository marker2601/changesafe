"""Live DataHub Agent Context Kit adapter and response normalization."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from time import perf_counter
from typing import Any, cast

from changesafe.context.base import (
    ContextLoadError,
    DecisionWriteback,
    ToolRunner,
)
from changesafe.domain import (
    AffectedAsset,
    ChangeRequest,
    ContextBundle,
    ContextMode,
    ContextProvenance,
    DataHubReceipt,
    EvidenceRef,
    Owner,
    ToolEvidence,
)
from changesafe.redaction import redact


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _nested(value: Any, *keys: str) -> Any:
    current = value
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _first_present(
    mapping: dict[str, Any], keys: tuple[str, ...], default: Any = None
) -> Any:
    return next((mapping[key] for key in keys if key in mapping), default)


class AgentContextToolRunner:
    """Invoke synchronous Agent Context Kit functions off the event loop."""

    def __init__(self, client: Any, tools: dict[str, Any]) -> None:
        self.client = client
        self.tools = tools

    @classmethod
    def connect(cls, server: str, token: str) -> AgentContextToolRunner:
        try:
            from datahub.sdk.main_client import DataHubClient
            from datahub_agent_context import mcp_tools
        except ImportError as exc:
            raise ContextLoadError(
                "Live DataHub support is not installed; install the 'live' extra"
            ) from exc

        names = (
            "get_entities",
            "list_schema_fields",
            "get_lineage",
            "get_dataset_queries",
            "save_document",
            "add_structured_properties",
            "add_tags",
        )
        return cls(
            DataHubClient(server=server, token=token),
            {name: getattr(mcp_tools, name) for name in names},
        )

    async def call(self, tool: str, **parameters: Any) -> Any:
        if tool not in self.tools:
            raise ContextLoadError(f"Unsupported DataHub tool: {tool}")

        def invoke() -> Any:
            from datahub_agent_context.context import DataHubContext

            with DataHubContext(self.client):
                return self.tools[tool](**parameters)

        return await asyncio.to_thread(invoke)


class LiveDataHubContext:
    def __init__(self, runner: ToolRunner, allowlist: set[str]) -> None:
        self.runner = runner
        self.allowlist = allowlist

    async def _call(
        self,
        tool: str,
        evidence: list[ToolEvidence],
        **parameters: Any,
    ) -> Any:
        started = perf_counter()
        try:
            result = await self.runner.call(tool, **parameters)
        except PermissionError:
            raise
        except Exception as exc:
            raise ContextLoadError(f"DataHub tool '{tool}' failed") from exc
        duration_ms = max(0, round((perf_counter() - started) * 1000))
        result_items = _as_list(result)
        referenced = _collect_urns(result)
        evidence.append(
            ToolEvidence(
                tool=tool,
                parameters=redact(parameters),
                duration_ms=duration_ms,
                result_count=len(result_items),
                referenced_urns=referenced,
            )
        )
        return result

    async def load(self, change: ChangeRequest) -> ContextBundle:
        if change.asset_urn not in self.allowlist:
            raise PermissionError("Asset is outside the configured DataHub allowlist")

        calls: list[ToolEvidence] = []
        entities = await self._call("get_entities", calls, urns=[change.asset_urn])
        schema = await self._call(
            "list_schema_fields",
            calls,
            urn=change.asset_urn,
            keywords=[change.field],
            limit=100,
            offset=0,
        )
        lineage = await self._call(
            "get_lineage",
            calls,
            urn=change.asset_urn,
            column=change.field,
            upstream=False,
            max_hops=3,
            max_results=30,
            offset=0,
        )
        queries = await self._call(
            "get_dataset_queries",
            calls,
            urn=change.asset_urn,
            column=change.field,
            start=0,
            count=10,
        )
        return _normalize_context(change, entities, schema, lineage, queries, calls)

    async def writeback(self, decision: DecisionWriteback) -> DataHubReceipt:
        target = decision.change.asset_urn
        if target not in self.allowlist:
            raise PermissionError("Asset is outside the configured DataHub allowlist")

        evidence: list[ToolEvidence] = []
        title = f"ChangeSafe decision {decision.run_id}"
        content = _decision_markdown(decision)
        document = await self._call(
            "save_document",
            evidence,
            document_type="Decision",
            title=title,
            content=content,
            related_assets=[target],
        )
        await self._call(
            "add_structured_properties",
            evidence,
            property_values={
                "urn:li:structuredProperty:changesafe.riskLevel": [
                    decision.risk_band.value.upper()
                ],
                "urn:li:structuredProperty:changesafe.changeStatus": ["DEPRECATING"],
                "urn:li:structuredProperty:changesafe.lastRunId": [decision.run_id],
            },
            entity_urns=[target],
        )
        await self._call(
            "add_tags",
            evidence,
            tag_urns=["urn:li:tag:ChangeSafe:Deprecating"],
            entity_urns=[target],
            column_paths=[decision.change.field],
        )
        document_urn = None
        if isinstance(document, dict):
            document_urn = _first_present(document, ("urn", "documentUrn"))
        return DataHubReceipt(
            mode="live",
            label="WRITTEN TO DATAHUB",
            document_urn=document_urn,
            updated_urns=[target],
            mutations=["save_document", "add_structured_properties", "add_tags"],
        )


def _collect_urns(value: Any) -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if key.lower().endswith("urn") and isinstance(item, str):
                found.append(item)
            else:
                found.extend(_collect_urns(item))
    elif isinstance(value, list):
        for item in value:
            found.extend(_collect_urns(item))
    return list(dict.fromkeys(found))


def _extract_entities(raw: Any) -> list[dict[str, Any]]:
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]
    if isinstance(raw, dict):
        for key in ("entities", "results", "data"):
            value = raw.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


def _extract_fields(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, dict):
        return []
    for key in ("fields", "schemaFields", "results"):
        value = raw.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _urns(items: Any) -> list[str]:
    result: list[str] = []
    for item in _as_list(items):
        if isinstance(item, str):
            result.append(item)
        elif isinstance(item, dict):
            urn = _first_present(item, ("urn", "tagUrn", "termUrn"))
            if isinstance(urn, str):
                result.append(urn)
    return result


def _normalize_context(
    change: ChangeRequest,
    entities_raw: Any,
    schema_raw: Any,
    lineage_raw: Any,
    queries_raw: Any,
    calls: list[ToolEvidence],
) -> ContextBundle:
    entities = _extract_entities(entities_raw)
    if not entities:
        raise ContextLoadError("Target asset was not returned by DataHub")
    entity = entities[0]
    fields = _extract_fields(schema_raw)
    field = next(
        (
            item
            for item in fields
            if _first_present(item, ("fieldPath", "name", "field")) == change.field
        ),
        None,
    )
    if field is None:
        raise ContextLoadError("Target field is absent from the DataHub schema")

    domain_value = entity.get("domain")
    target_domain = (
        _first_present(domain_value, ("name", "displayName"))
        if isinstance(domain_value, dict)
        else domain_value
    )
    owner_items = entity.get("owners") or _nested(entity, "ownership", "owners") or []
    owners: list[Owner] = []
    for item in _as_list(owner_items):
        if not isinstance(item, dict):
            continue
        nested_owner = item.get("owner")
        owner = cast(
            dict[str, Any], nested_owner if isinstance(nested_owner, dict) else item
        )
        owners.append(
            Owner(
                urn=_first_present(
                    owner, ("urn", "ownerUrn"), "urn:li:corpuser:unknown"
                ),
                name=_first_present(owner, ("name", "displayName"), "Unknown owner"),
                ownership_type=_first_present(
                    item, ("type", "ownershipType"), "UNKNOWN"
                ),
            )
        )

    field_tags = list(
        dict.fromkeys([*_urns(entity.get("tags")), *_urns(field.get("tags"))])
    )
    terms = _urns(entity.get("glossaryTerms")) + _urns(field.get("glossaryTerms"))

    relationships: list[dict[str, Any]] = []
    if isinstance(lineage_raw, dict):
        for key in ("relationships", "entities", "results"):
            value = lineage_raw.get(key)
            if isinstance(value, list):
                relationships = [item for item in value if isinstance(item, dict)]
                break
    downstream = []
    for item in relationships:
        domain = item.get("domain")
        domain_name = (
            _first_present(domain, ("name", "displayName"))
            if isinstance(domain, dict)
            else domain
        )
        entity_type = str(
            _first_present(item, ("entityType", "entity_type", "type"), "dataset")
        )
        downstream.append(
            AffectedAsset(
                urn=str(_first_present(item, ("urn", "entityUrn"), "")),
                name=str(_first_present(item, ("name", "displayName"), "unnamed")),
                entity_type=entity_type,
                domain=domain_name,
                field=_first_present(item, ("field", "column", "fieldPath")),
                is_executive=bool(item.get("isExecutive"))
                or (
                    entity_type.lower() == "dashboard"
                    and "executive" in str(domain_name).lower()
                ),
                is_production_ml=bool(item.get("isProductionMl")),
                lineage_path=[str(value) for value in item.get("lineagePath", [])],
            )
        )

    query_items = (
        queries_raw.get("queries", []) if isinstance(queries_raw, dict) else []
    )
    query_texts = [
        str(_first_present(item, ("query", "sql", "text"), ""))
        for item in query_items
        if isinstance(item, dict)
    ]
    usage_tier = (
        str(queries_raw.get("usageTier", "none")).lower()
        if isinstance(queries_raw, dict)
        else "none"
    )
    if usage_tier not in {"none", "low", "medium", "high"}:
        usage_tier = "high" if query_texts else "none"

    evidence = [
        EvidenceRef(
            urn=change.asset_urn,
            kind="schema",
            label=f"{change.field} {field.get('type', 'UNKNOWN')}",
        ),
        *[
            EvidenceRef(urn=urn, kind="governance", label=urn.rsplit(":", 1)[-1])
            for urn in [*field_tags, *terms]
        ],
        *[
            EvidenceRef(
                urn=str(_first_present(item, ("urn", "queryUrn"), change.asset_urn)),
                kind="usage",
                label="Query usage",
            )
            for item in query_items
            if isinstance(item, dict)
        ],
        *[
            EvidenceRef(
                urn=asset.urn,
                kind="lineage",
                label=asset.name,
                path=asset.lineage_path,
            )
            for asset in downstream
        ],
    ]
    return ContextBundle(
        target_urn=change.asset_urn,
        target_name=str(_first_present(entity, ("name", "displayName"), "unknown")),
        target_domain=target_domain,
        field=change.field,
        field_type=str(_first_present(field, ("type", "nativeType"), "UNKNOWN")),
        downstream_assets=downstream,
        owners=owners,
        field_tags=field_tags,
        glossary_terms=list(dict.fromkeys(terms)),
        structured_properties=entity.get("structuredProperties", {}),
        usage_tier=usage_tier,
        queries=query_texts,
        evidence=evidence,
        tool_evidence=calls,
        provenance=ContextProvenance(
            mode=ContextMode.LIVE,
            retrieved_at=datetime.now(UTC),
            adapter_version="datahub-agent-context/1.7.0",
        ),
    )


def _decision_markdown(decision: DecisionWriteback) -> str:
    pr_line = (
        f"- Pull request: {decision.pull_request_url}\n"
        if decision.pull_request_url
        else "- Pull request: not yet published\n"
    )
    return (
        f"# ChangeSafe decision {decision.run_id}\n\n"
        f"- Asset: `{decision.change.asset_urn}`\n"
        f"- Change: `{decision.change.operation.value}` "
        f"`{decision.change.field}`\n"
        f"- Risk: {decision.risk_score}/{decision.risk_band.value.title()}\n"
        f"- Artifact manifest: `{decision.artifact_hash}`\n"
        f"- Approved: {decision.approved_at.isoformat()}\n"
        f"{pr_line}\n"
        "The verified phase-one migration preserves compatibility and includes "
        "rollback instructions.\n"
    )
