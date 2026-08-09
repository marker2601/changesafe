"""Credential-free replay adapter backed by a checksummed canonical snapshot."""

from __future__ import annotations

import json
import os
from hashlib import sha256
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from changesafe.context.base import (
    ContextLoadError,
    DecisionWriteback,
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
    SchemaCatalog,
    SchemaField,
    StrictModel,
    ToolEvidence,
)
from changesafe.sql_types import canonical_sql_type

REPO_ROOT = Path(__file__).resolve().parents[5]
DEFAULT_SNAPSHOT = REPO_ROOT / "fixtures" / "datahub" / "golden-context.json"
DEFAULT_CHECKSUM = REPO_ROOT / "fixtures" / "datahub" / "golden-context.sha256"


class RecordedFieldContext(StrictModel):
    field_type: str
    upstream_assets: list[AffectedAsset]
    downstream_assets: list[AffectedAsset]
    field_tags: list[str]
    glossary_terms: list[str]
    usage_tier: Literal["none", "low", "medium", "high"]
    queries: list[str]
    evidence: list[EvidenceRef]
    tool_evidence: list[ToolEvidence]


class RecordedDataHubCatalog(StrictModel):
    snapshot_version: Literal[2]
    target_urn: str
    target_name: str
    target_domain: str | None
    schema_fields: list[SchemaField] = Field(min_length=1)
    owners: list[Owner]
    structured_properties: dict[str, list[str | int | float]]
    fields: dict[str, RecordedFieldContext]
    provenance: ContextProvenance

    @model_validator(mode="after")
    def fields_match_schema(self) -> RecordedDataHubCatalog:
        names = [item.name.casefold() for item in self.schema_fields]
        if len(names) != len(set(names)):
            raise ValueError("schema_fields contains duplicate field names")
        expected = {item.name for item in self.schema_fields}
        if set(self.fields) != expected:
            raise ValueError("recorded field contexts must exactly match schema_fields")
        schema_by_name = {item.name: item for item in self.schema_fields}
        for name, recorded in self.fields.items():
            try:
                if canonical_sql_type(recorded.field_type) != canonical_sql_type(
                    schema_by_name[name].data_type
                ):
                    raise ValueError(
                        "recorded field context type must match its schema field"
                    )
            except ValueError as exc:
                raise ValueError(
                    "recorded field context type must match its schema field"
                ) from exc
        return self


class ReplayDataHubContext:
    def __init__(self, snapshot_path: Path, checksum_path: Path) -> None:
        self.snapshot_path = snapshot_path
        self.checksum_path = checksum_path

    @classmethod
    def from_default(cls) -> ReplayDataHubContext:
        snapshot = Path(os.getenv("CHANGESAFE_SNAPSHOT_PATH", DEFAULT_SNAPSHOT))
        checksum = Path(
            os.getenv("CHANGESAFE_SNAPSHOT_CHECKSUM_PATH", DEFAULT_CHECKSUM)
        )
        return cls(snapshot, checksum)

    def _load_payload(self) -> tuple[RecordedDataHubCatalog, str]:
        try:
            raw = self.snapshot_path.read_bytes()
            expected = self.checksum_path.read_text(encoding="ascii").split()[0]
        except OSError as exc:
            raise ContextLoadError("DataHub snapshot is unavailable") from exc

        actual = sha256(raw).hexdigest()
        if actual != expected:
            raise ContextLoadError("DataHub snapshot checksum mismatch")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ContextLoadError("DataHub snapshot is not valid JSON") from exc
        try:
            return RecordedDataHubCatalog.model_validate(payload), actual
        except ValueError as exc:
            raise ContextLoadError(
                "DataHub snapshot failed contract validation"
            ) from exc

    async def load(self, change: ChangeRequest) -> ContextBundle:
        catalog, digest = self._load_payload()
        if catalog.target_urn != change.asset_urn:
            raise ContextLoadError("Snapshot does not contain the requested asset")
        try:
            recorded = catalog.fields[change.field]
        except KeyError as exc:
            raise ContextLoadError(
                "Snapshot does not contain the requested field"
            ) from exc
        provenance = catalog.provenance.model_copy(
            update={"mode": ContextMode.SNAPSHOT, "snapshot_hash": digest}
        )
        return ContextBundle(
            target_urn=catalog.target_urn,
            target_name=catalog.target_name,
            target_domain=catalog.target_domain,
            field=change.field,
            field_type=recorded.field_type,
            schema_fields=catalog.schema_fields,
            upstream_assets=recorded.upstream_assets,
            downstream_assets=recorded.downstream_assets,
            owners=catalog.owners,
            field_tags=recorded.field_tags,
            glossary_terms=recorded.glossary_terms,
            structured_properties=catalog.structured_properties,
            usage_tier=recorded.usage_tier,
            queries=recorded.queries,
            evidence=recorded.evidence,
            tool_evidence=recorded.tool_evidence,
            provenance=provenance,
        )

    async def discover_schema(self, asset_urn: str) -> SchemaCatalog:
        catalog, digest = self._load_payload()
        if catalog.target_urn != asset_urn:
            raise ContextLoadError("Snapshot does not contain the requested asset")
        return SchemaCatalog(
            target_urn=catalog.target_urn,
            target_name=catalog.target_name,
            schema_fields=catalog.schema_fields,
            provenance=catalog.provenance.model_copy(
                update={"mode": ContextMode.SNAPSHOT, "snapshot_hash": digest}
            ),
        )

    async def writeback(
        self,
        decision: DecisionWriteback,
        *,
        progress: DataHubReceipt | None = None,
        on_progress: WritebackProgress | None = None,
    ) -> DataHubReceipt:
        del progress
        receipt = DataHubReceipt(
            mode="preview",
            label="NOT WRITTEN — SNAPSHOT MODE",
            updated_urns=[decision.change.asset_urn],
            mutations=[],
        )
        if on_progress is not None:
            await on_progress(receipt)
        return receipt
