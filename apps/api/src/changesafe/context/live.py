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
    WritebackProgress,
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

GOLDEN_TARGET = (
    "urn:li:dataset:(urn:li:dataPlatform:dbt,analytics.dim_customers,PROD)"
)
GOLDEN_FIELD = "customer_email"
GOLDEN_DOWNSTREAM_COUNT = 4


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


def _display_name(value: Any, default: str | None = None) -> str | None:
    if isinstance(value, str):
        return value
    if not isinstance(value, dict):
        return default
    direct = _first_present(value, ("name", "displayName", "label"))
    if isinstance(direct, str) and direct:
        return direct
    for key in ("properties", "editableProperties", "info"):
        nested = value.get(key)
        candidate = _display_name(nested)
        if candidate:
            return candidate
    return default


def _domain_name(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    if not isinstance(value, dict):
        return None
    nested = value.get("domain")
    if nested is not None:
        return _domain_name(nested)
    return _display_name(value)


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

    async def writeback(
        self,
        decision: DecisionWriteback,
        *,
        progress: DataHubReceipt | None = None,
        on_progress: WritebackProgress | None = None,
    ) -> DataHubReceipt:
        target = decision.change.asset_urn
        if target not in self.allowlist:
            raise PermissionError("Asset is outside the configured DataHub allowlist")

        evidence: list[ToolEvidence] = []
        title = f"ChangeSafe decision {decision.run_id}"
        content = _decision_markdown(decision)
        document_urn = (
            progress.document_urn
            if progress is not None and progress.document_urn
            else f"urn:li:document:changesafe-{decision.idempotency_key[:32]}"
        )
        receipt = progress or DataHubReceipt(
            mode="live",
            label="WRITEBACK IN PROGRESS",
            document_urn=document_urn,
            updated_urns=[target],
        )

        async def record(mutation: str) -> None:
            nonlocal receipt
            receipt = receipt.model_copy(
                update={
                    "label": "WRITEBACK IN PROGRESS",
                    "document_urn": document_urn,
                    "updated_urns": [target],
                    "mutations": list(
                        dict.fromkeys([*receipt.mutations, mutation])
                    ),
                }
            )
            if on_progress is not None:
                await on_progress(receipt)

        if "save_document" not in receipt.mutations:
            document = await self._call(
                "save_document",
                evidence,
                urn=document_urn,
                document_type="Decision",
                title=title,
                content=content,
                related_assets=[target],
            )
            _require_mutation_success("save_document", document)
            if isinstance(document, dict):
                returned_urn = _first_present(document, ("urn", "documentUrn"))
                if isinstance(returned_urn, str) and returned_urn != document_urn:
                    raise ContextLoadError(
                        "DataHub returned an unexpected decision document URN"
                    )
            await record("save_document")

        if "add_structured_properties" not in receipt.mutations:
            properties = await self._call(
                "add_structured_properties",
                evidence,
                property_values={
                    "urn:li:structuredProperty:changesafe.riskLevel": [
                        decision.risk_band.value.upper()
                    ],
                    "urn:li:structuredProperty:changesafe.changeStatus": [
                        "DEPRECATING"
                    ],
                    "urn:li:structuredProperty:changesafe.lastRunId": [
                        decision.run_id
                    ],
                },
                entity_urns=[target],
            )
            _require_mutation_success("add_structured_properties", properties)
            await record("add_structured_properties")

        if "add_tags" not in receipt.mutations:
            tags = await self._call(
                "add_tags",
                evidence,
                tag_urns=["urn:li:tag:ChangeSafe:Deprecating"],
                entity_urns=[target],
                column_paths=[decision.change.field],
            )
            _require_mutation_success("add_tags", tags)
            await record("add_tags")

        receipt = receipt.model_copy(update={"label": "WRITTEN TO DATAHUB"})
        if on_progress is not None:
            await on_progress(receipt)
        return receipt


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


def _require_mutation_success(tool: str, result: Any) -> None:
    if isinstance(result, dict) and result.get("success") is False:
        raise ContextLoadError(f"DataHub tool '{tool}' did not report success")


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
            else:
                for key in ("tags", "terms", "tag", "term"):
                    if key in item:
                        result.extend(_urns(item[key]))
    return result


def _lineage_relationships(raw: Any) -> tuple[list[dict[str, Any]], bool]:
    if not isinstance(raw, dict):
        return [], False
    direction = raw.get("downstreams")
    if isinstance(direction, dict):
        results = direction.get("searchResults")
        relationships = (
            [item for item in results if isinstance(item, dict)]
            if isinstance(results, list)
            else []
        )
        total = direction.get("total")
        returned = direction.get("returned", len(relationships))
        partial = bool(direction.get("hasMore"))
        if isinstance(total, int) and isinstance(returned, int):
            partial = partial or returned < total
        return relationships, partial
    for key in ("relationships", "entities", "results"):
        value = raw.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)], False
    return [], False


def _query_text(item: dict[str, Any]) -> str:
    direct = _first_present(item, ("query", "sql", "text"))
    if isinstance(direct, str):
        return direct
    statement = _nested(item, "properties", "statement", "value")
    return statement if isinstance(statement, str) else ""


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

    target_domain = _domain_name(entity.get("domain"))
    owner_items = entity.get("owners") or _nested(entity, "ownership", "owners") or []
    owners: list[Owner] = []
    for item in _as_list(owner_items):
        if not isinstance(item, dict):
            continue
        nested_owner = item.get("owner")
        owner = cast(
            dict[str, Any], nested_owner if isinstance(nested_owner, dict) else item
        )
        ownership_value = _first_present(item, ("ownershipType", "type"), "UNKNOWN")
        if isinstance(ownership_value, dict):
            ownership_value = _first_present(
                ownership_value, ("type", "urn"), "UNKNOWN"
            )
        owners.append(
            Owner(
                urn=_first_present(
                    owner, ("urn", "ownerUrn"), "urn:li:corpuser:unknown"
                ),
                name=_display_name(owner, "Unknown owner") or "Unknown owner",
                ownership_type=str(ownership_value),
            )
        )

    field_tags = list(
        dict.fromkeys([*_urns(entity.get("tags")), *_urns(field.get("tags"))])
    )
    terms = _urns(entity.get("glossaryTerms")) + _urns(field.get("glossaryTerms"))

    relationships, partial_lineage = _lineage_relationships(lineage_raw)
    if partial_lineage:
        raise ContextLoadError("DataHub returned a partial lineage page")
    downstream = []
    for item in relationships:
        nested_entity = item.get("entity")
        asset = cast(
            dict[str, Any], nested_entity if isinstance(nested_entity, dict) else item
        )
        domain_name = _domain_name(asset.get("domain"))
        entity_type = str(
            _first_present(asset, ("entityType", "entity_type", "type"), "dataset")
        )
        urn = str(_first_present(asset, ("urn", "entityUrn"), ""))
        lineage_columns = item.get("lineageColumns")
        field_path = _first_present(asset, ("field", "column", "fieldPath"))
        if field_path is None and isinstance(lineage_columns, list):
            field_path = next(
                (value for value in lineage_columns if isinstance(value, str)), None
            )
        raw_path = item.get("lineagePath") or item.get("paths")
        lineage_path = _collect_urns(raw_path)
        if not lineage_path and urn:
            lineage_path = [change.asset_urn, urn]
        downstream.append(
            AffectedAsset(
                urn=urn,
                name=_display_name(asset, "unnamed") or "unnamed",
                entity_type=entity_type,
                domain=domain_name,
                field=field_path,
                is_executive=bool(asset.get("isExecutive"))
                or (
                    entity_type.lower() == "dashboard"
                    and "executive" in str(domain_name).lower()
                ),
                is_production_ml=bool(asset.get("isProductionMl")),
                lineage_path=lineage_path,
            )
        )

    if (
        change.asset_urn == GOLDEN_TARGET
        and change.field == GOLDEN_FIELD
        and len(downstream) != GOLDEN_DOWNSTREAM_COUNT
    ):
        raise ContextLoadError(
            "Seeded DataHub lineage contract requires exactly four downstream assets"
        )

    query_items = (
        queries_raw.get("queries", []) if isinstance(queries_raw, dict) else []
    )
    query_texts = [
        _query_text(item)
        for item in query_items
        if isinstance(item, dict)
    ]
    query_texts = [text for text in query_texts if text]
    usage_tier = (
        str(queries_raw.get("usageTier", "none")).lower()
        if isinstance(queries_raw, dict)
        else "none"
    )
    if usage_tier not in {"none", "low", "medium", "high"}:
        usage_tier = "high" if query_texts else "none"
    elif usage_tier == "none" and query_texts:
        usage_tier = "high"

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
        target_name=_display_name(entity, "unknown") or "unknown",
        target_domain=target_domain,
        field=change.field,
        field_type=str(
            _first_present(
                field, ("type", "nativeType", "nativeDataType"), "UNKNOWN"
            )
        ),
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
