"""Live DataHub Agent Context Kit adapter and response normalization."""

from __future__ import annotations

import asyncio
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from time import perf_counter
from typing import Any, cast

from changesafe.context.base import (
    ContextAuthorizationError,
    ContextLoadError,
    ContextTimeoutError,
    ContextTransportError,
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
    SchemaField,
    ToolEvidence,
)
from changesafe.redaction import redact

GOLDEN_TARGET = (
    "urn:li:dataset:(urn:li:dataPlatform:dbt,analytics.dim_customers,PROD)"
)
GOLDEN_FIELD = "customer_email"
GOLDEN_DOWNSTREAM_URNS = {
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
}


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
    return next(
        (mapping[key] for key in keys if mapping.get(key) is not None),
        default,
    )


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


def _is_authorization_error(error: BaseException) -> bool:
    """Recognize SDK-wrapped HTTP auth failures without matching secret text."""

    pending: list[BaseException] = [error]
    seen: set[int] = set()
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        response = getattr(current, "response", None)
        for value in (current, response):
            status_code = getattr(value, "status_code", None)
            if status_code in {401, 403}:
                return True
        for nested in (current.__cause__, current.__context__):
            if nested is not None:
                pending.append(nested)
    return False


def _domain_name(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    if not isinstance(value, dict):
        return None
    nested = value.get("domain")
    if nested is not None:
        return _domain_name(nested)
    return _display_name(value)


def _ownership_type(value: Any) -> str:
    raw = str(value).rsplit(":", 1)[-1].upper()
    raw = raw.removeprefix("__SYSTEM__")
    normalized = "_".join(filter(None, re.split(r"[^A-Z0-9]+", raw)))
    return {
        "DATAOWNER": "DATA_OWNER",
        "BUSINESSOWNER": "BUSINESS_OWNER",
    }.get(normalized, normalized or "UNKNOWN")


class AgentContextToolRunner:
    """Invoke synchronous Agent Context Kit functions off the event loop."""

    def __init__(self, client: Any, tools: dict[str, Any]) -> None:
        self.client = client
        self.tools = tools
        self._executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="changesafe-datahub"
        )

    @classmethod
    def connect(
        cls, server: str, token: str, *, timeout_seconds: float = 8.0
    ) -> AgentContextToolRunner:
        try:
            from datahub.ingestion.graph.config import DatahubClientConfig
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
            DataHubClient(
                config=DatahubClientConfig(
                    server=server,
                    token=token,
                    timeout_sec=timeout_seconds,
                    retry_max_times=0,
                    pool_connections=1,
                    pool_maxsize=1,
                )
            ),
            {name: getattr(mcp_tools, name) for name in names},
        )

    async def call(self, tool: str, **parameters: Any) -> Any:
        if tool not in self.tools:
            raise ContextLoadError(f"Unsupported DataHub tool: {tool}")

        def invoke() -> Any:
            from datahub_agent_context.context import DataHubContext

            with DataHubContext(self.client):
                return self.tools[tool](**parameters)

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._executor, invoke)

    def close(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)


class LiveDataHubContext:
    def __init__(
        self,
        runner: ToolRunner,
        allowlist: set[str],
        *,
        timeout_seconds: float = 8.0,
        retry_count: int = 1,
    ) -> None:
        self.runner = runner
        self.allowlist = allowlist
        self.timeout_seconds = timeout_seconds
        self.retry_count = retry_count

    def close(self) -> None:
        close = getattr(self.runner, "close", None)
        if callable(close):
            close()

    async def _call(
        self,
        tool: str,
        evidence: list[ToolEvidence],
        **parameters: Any,
    ) -> Any:
        started = perf_counter()
        result: Any = None
        for attempt in range(self.retry_count + 1):
            try:
                result = await asyncio.wait_for(
                    self.runner.call(tool, **parameters),
                    timeout=self.timeout_seconds,
                )
                break
            except PermissionError as exc:
                raise ContextAuthorizationError(
                    f"DataHub authorization failed for tool '{tool}'"
                ) from exc
            except TimeoutError as exc:
                if attempt >= self.retry_count:
                    raise ContextTimeoutError(
                        f"DataHub tool '{tool}' timed out"
                    ) from exc
            except Exception as exc:
                if _is_authorization_error(exc):
                    raise ContextAuthorizationError(
                        f"DataHub authorization failed for tool '{tool}'"
                    ) from exc
                if attempt >= self.retry_count:
                    raise ContextTransportError(
                        f"DataHub tool '{tool}' was unavailable"
                    ) from exc
            await asyncio.sleep(0)
        duration_ms = max(0, round((perf_counter() - started) * 1000))
        referenced = _collect_urns(result)
        evidence.append(
            ToolEvidence(
                tool=tool,
                parameters=redact(parameters),
                duration_ms=duration_ms,
                result_count=_result_count(tool, result),
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
            keywords=None,
            limit=200,
            offset=0,
        )
        upstream_lineage = await self._call(
            "get_lineage",
            calls,
            urn=change.asset_urn,
            column=change.field,
            upstream=True,
            max_hops=3,
            max_results=30,
            offset=0,
        )
        downstream_lineage = await self._call(
            "get_lineage",
            calls,
            urn=change.asset_urn,
            column=change.field,
            upstream=False,
            max_hops=3,
            max_results=30,
            offset=0,
        )
        downstream_asset_lineage = await self._call(
            "get_lineage",
            calls,
            urn=change.asset_urn,
            column=None,
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
        try:
            return _normalize_context(
                change,
                entities,
                schema,
                upstream_lineage,
                downstream_lineage,
                downstream_asset_lineage,
                queries,
                calls,
            )
        except ContextLoadError:
            raise
        except (KeyError, TypeError, ValueError) as exc:
            raise ContextLoadError(
                "DataHub response did not satisfy the ChangeSafe context contract"
            ) from exc

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
            assert isinstance(document, dict)
            returned_urn = _first_present(document, ("urn", "documentUrn"))
            if returned_urn != document_urn:
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
                column_paths=[None],
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


def _result_count(tool: str, result: Any) -> int:
    if tool == "get_entities":
        return len(_extract_entities(result))
    if tool == "list_schema_fields":
        if isinstance(result, dict) and isinstance(result.get("returned"), int):
            return int(result["returned"])
        return len(_extract_fields(result))
    if tool == "get_lineage" and isinstance(result, dict):
        for direction_name in ("upstreams", "downstreams"):
            direction = result.get(direction_name)
            if not isinstance(direction, dict):
                continue
            if isinstance(direction.get("returned"), int):
                return int(direction["returned"])
            results = direction.get("searchResults")
            if isinstance(results, list):
                return len(results)
        relationships, _ = _lineage_relationships(result, "downstreams")
        if not relationships:
            relationships, _ = _lineage_relationships(result, "upstreams")
        return len(relationships)
    if tool == "get_dataset_queries" and isinstance(result, dict):
        queries = result.get("queries")
        return len(queries) if isinstance(queries, list) else 0
    return len(_as_list(result))


def _require_mutation_success(tool: str, result: Any) -> None:
    if not isinstance(result, dict) or result.get("success") is not True:
        raise ContextLoadError(
            f"DataHub tool '{tool}' did not return a positive success acknowledgement"
        )


def _field_type(field: dict[str, Any]) -> str:
    value = _first_present(field, ("nativeDataType", "nativeType", "type"))
    if isinstance(value, dict):
        value = _first_present(value, ("nativeDataType", "type", "name"))
    return str(value) if isinstance(value, str) and value else "UNKNOWN"


def _is_nested_schema_field(field: dict[str, Any], field_path: str) -> bool:
    json_path = field.get("jsonPath")
    return bool(
        isinstance(json_path, str)
        and "." in field_path
        and json_path == f"$.{field_path}"
    )


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


def _lineage_relationships(
    raw: Any, direction_name: str
) -> tuple[list[dict[str, Any]], bool]:
    if not isinstance(raw, dict):
        return [], False
    direction = raw.get(direction_name)
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


def _normalize_lineage_assets(
    change: ChangeRequest, raw: Any, direction_name: str
) -> list[AffectedAsset]:
    relationships, partial_lineage = _lineage_relationships(raw, direction_name)
    if partial_lineage:
        raise ContextLoadError("DataHub returned a partial lineage page")
    normalized: list[AffectedAsset] = []
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
        if not lineage_path and urn and item.get("degree") == 1:
            lineage_path = (
                [urn, change.asset_urn]
                if direction_name == "upstreams"
                else [change.asset_urn, urn]
            )
        normalized.append(
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
    return normalized


def _query_text(item: dict[str, Any]) -> str:
    direct = _first_present(item, ("query", "sql", "text"))
    if isinstance(direct, str):
        return direct
    statement = _nested(item, "properties", "statement", "value")
    return statement if isinstance(statement, str) else ""


def _structured_properties(raw: Any) -> dict[str, list[str | int | float]]:
    if not isinstance(raw, dict):
        return {}
    entries = raw.get("properties")
    if isinstance(entries, list):
        normalized: dict[str, list[str | int | float]] = {}
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            definition = entry.get("structuredProperty")
            urn = (
                _first_present(definition, ("urn", "structuredPropertyUrn"))
                if isinstance(definition, dict)
                else definition
            )
            if not isinstance(urn, str) or not urn:
                continue
            values: list[str | int | float] = []
            for item in _as_list(entry.get("values")):
                if isinstance(item, (str, int, float)) and not isinstance(item, bool):
                    values.append(item)
                elif isinstance(item, dict):
                    value = _first_present(item, ("stringValue", "numberValue"))
                    if isinstance(value, (str, int, float)) and not isinstance(
                        value, bool
                    ):
                        values.append(value)
            if values:
                normalized[urn] = values
        return normalized

    normalized = {}
    for urn, raw_values in raw.items():
        values = [
            value
            for value in _as_list(raw_values)
            if isinstance(value, (str, int, float)) and not isinstance(value, bool)
        ]
        if values:
            normalized[str(urn)] = values
    return normalized


def _normalize_context(
    change: ChangeRequest,
    entities_raw: Any,
    schema_raw: Any,
    upstream_lineage_raw: Any,
    downstream_lineage_raw: Any,
    downstream_asset_lineage_raw: Any,
    queries_raw: Any,
    calls: list[ToolEvidence],
) -> ContextBundle:
    entities = _extract_entities(entities_raw)
    if not entities:
        raise ContextLoadError("Target asset was not returned by DataHub")
    entity = entities[0]
    fields = _extract_fields(schema_raw)
    if isinstance(schema_raw, dict):
        remaining = schema_raw.get("remainingCount", 0)
        total = schema_raw.get("totalFields")
        returned = schema_raw.get("returned", len(fields))
        if (
            (isinstance(remaining, int) and remaining > 0)
            or (
                isinstance(total, int)
                and isinstance(returned, int)
                and returned < total
            )
        ):
            raise ContextLoadError("DataHub returned a partial schema field page")
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
    schema_fields: list[SchemaField] = []
    for item in fields:
        raw_name = _first_present(item, ("fieldPath", "name", "field"))
        if not isinstance(raw_name, str) or not raw_name:
            continue
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", raw_name):
            if _is_nested_schema_field(item, raw_name):
                continue
            raise ContextLoadError(
                "DataHub schema contains an unsupported top-level field identifier"
            )
        data_type = _field_type(item)
        if data_type == "UNKNOWN":
            raise ContextLoadError(
                "DataHub schema field is missing a concrete native type"
            )
        schema_fields.append(
            SchemaField(
                name=raw_name,
                data_type=data_type,
                nullable=bool(item.get("nullable", True)),
            )
        )

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
                ownership_value, ("urn", "type"), "UNKNOWN"
            )
        owners.append(
            Owner(
                urn=_first_present(
                    owner, ("urn", "ownerUrn"), "urn:li:corpuser:unknown"
                ),
                name=_display_name(owner, "Unknown owner") or "Unknown owner",
                ownership_type=_ownership_type(ownership_value),
            )
        )

    field_tags = list(
        dict.fromkeys([*_urns(entity.get("tags")), *_urns(field.get("tags"))])
    )
    terms = _urns(entity.get("glossaryTerms")) + _urns(field.get("glossaryTerms"))

    upstream = _normalize_lineage_assets(
        change, upstream_lineage_raw, "upstreams"
    )
    downstream = _normalize_lineage_assets(
        change, downstream_lineage_raw, "downstreams"
    )
    asset_downstream = _normalize_lineage_assets(
        change, downstream_asset_lineage_raw, "downstreams"
    )
    seen_downstream = {asset.urn for asset in downstream}
    for asset in asset_downstream:
        if asset.entity_type.lower() == "dataset" or asset.urn in seen_downstream:
            continue
        downstream.append(asset)
        seen_downstream.add(asset.urn)

    if (
        change.asset_urn == GOLDEN_TARGET
        and change.field == GOLDEN_FIELD
        and {asset.urn for asset in downstream} != GOLDEN_DOWNSTREAM_URNS
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

    normalized_field_type = _field_type(field)
    evidence = [
        EvidenceRef(
            urn=change.asset_urn,
            kind="schema",
            label=f"{change.field} {normalized_field_type}",
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
        field_type=normalized_field_type,
        schema_fields=schema_fields,
        upstream_assets=upstream,
        downstream_assets=downstream,
        owners=owners,
        field_tags=field_tags,
        glossary_terms=list(dict.fromkeys(terms)),
        structured_properties=_structured_properties(
            entity.get("structuredProperties", {})
        ),
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
    factors = "\n".join(
        f"- +{factor.points} {factor.label}: "
        f"{', '.join(factor.evidence_urns)}"
        for factor in decision.risk_factors
    ) or "- No additional risk factors."
    validation = "\n".join(
        f"- {'PASS' if check.passed else 'FAIL'} `{check.code}`: {check.detail}"
        for check in decision.validation_checks
    ) or "- No validation checks were recorded."
    evidence = "\n".join(
        f"- `{item.kind}` {item.label}: `{item.urn}`"
        + (f" via {' -> '.join(item.path)}" if item.path else "")
        for item in decision.evidence
    ) or "- No evidence references were recorded."
    return (
        f"# ChangeSafe decision {decision.run_id}\n\n"
        f"- Source commit: `{decision.change.source_commit}`\n"
        f"- Asset: `{decision.change.asset_urn}`\n"
        f"- Change: `{decision.change.operation.value}` "
        f"`{decision.change.field}`\n"
        f"- Risk: {decision.risk_score}/{decision.risk_band.value.title()}\n"
        f"- Artifact manifest: `{decision.artifact_hash}`\n"
        f"- Approved: {decision.approved_at.isoformat()}\n"
        f"{pr_line}\n"
        f"## Risk factors\n\n{factors}\n\n"
        f"## Evidence\n\n{evidence}\n\n"
        f"## Validation\n\n{validation}\n\n"
        f"## Migration\n\n{decision.migration_summary}\n\n"
        f"## Rollback\n\n{decision.rollback_summary}\n"
    )
