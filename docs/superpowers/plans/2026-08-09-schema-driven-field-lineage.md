# ChangeSafe Schema-Driven Field Analysis and Exact Lineage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a user select any supported field from an allowlisted DataHub dataset, analyze only that field's evidence, and show truthful source-column to destination-column routes with reproducible multi-field proof.

**Architecture:** Add a read-only schema-discovery contract to the existing DataHub context port, implement it for both live and checksummed recorded evidence, and expose it through one bounded FastAPI endpoint. Convert the recorded fixture into a dataset catalog with one field-scoped context per schema field, then add a React schema hook, accessible field combobox, and route formatter that derives directional endpoints without inventing missing column mappings.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, DataHub Agent Context 1.7.0, pytest, React 19, TypeScript 6, Vitest, Testing Library, Lucide React, CSS, Vite, Playwright, dbt Core with DuckDB, Docker, and the existing in-app Browser workflow.

## Global Constraints

- `cust_email -> primary_email` remains an example, not a product restriction.
- Dataset discovery and analysis use the same configured URN allowlist.
- The browser never receives a DataHub token or any other server credential.
- The current field must come from the active live or checksummed recorded schema; there is no free-text fallback.
- Recorded mode supports every valid field in the official 55-field `order_details` schema with field-scoped evidence, including a truthful empty result where DataHub returned none.
- Governance, lineage, usage, or query evidence recorded for `cust_email` must not be copied to a different field.
- Exact field endpoints are shown only when DataHub returned them.
- Multi-hop routes without intermediate column mappings say `intermediate column mapping not returned by DataHub`.
- Asset-only dependencies say `dataset-level relationship` and identify the missing endpoint field.
- No field name is inferred merely because source and destination names look similar.
- Rename destinations remain explicit user input; ChangeSafe does not automatically prefix every field with `primary_`.
- Type-change current type is read-only schema evidence; new types still pass the shared Snowflake type validator.
- Submitted requests remain immutable and bound to their saved context, artifacts, validation, and provenance.
- All run progress continues to come from persisted server events; no presentation delay or random result is added.
- Existing owner gating, publication destination binding, mutation allowlists, idempotency, and crash recovery remain unchanged.
- Motion remains evidence-bearing, has a `prefers-reduced-motion` equivalent, and never implies unknown path detail.
- Final visual verification uses the user's selected in-app Browser; existing Playwright coverage remains an automated repository gate.

---

## File structure and responsibilities

### Backend contracts and adapters

- Modify `apps/api/src/changesafe/domain.py`: public `SchemaCatalog`, `LineagePrecision`, and the required precision on `AffectedAsset`.
- Modify `apps/api/src/changesafe/context/base.py`: add `discover_schema(asset_urn)` to `DataHubContextPort`.
- Modify `apps/api/src/changesafe/context/live.py`: reuse complete schema pagination for discovery and analysis; normalize schema once; attach truthful lineage precision.
- Modify `apps/api/src/changesafe/context/replay.py`: validate the versioned recorded catalog, return schema discovery, and reconstruct a `ContextBundle` for the selected field only.
- Modify `apps/api/src/changesafe/api.py`: expose bounded `GET /api/schema-fields` with active/recorded source selection and stable safe failures.

### Evidence capture

- Create `scripts/capture_field_catalog.py`: read all supported fields from live DataHub, capture one context per field, and atomically write the checksummed recorded catalog only after all fields succeed.
- Modify `scripts/capture_snapshot.py`: keep canonical redaction and add an atomic bytes/checksum helper used by the catalog capture.
- Replace `fixtures/datahub/golden-context.json`: versioned catalog containing common dataset metadata plus 55 field contexts.
- Update `fixtures/datahub/golden-context.sha256` and deterministic files under `examples/generated-safe-change/`.

### Web discovery and selection

- Modify `apps/web/src/types.ts`: add schema catalog and lineage precision types.
- Modify `apps/web/src/api.ts`: add `getSchemaCatalog(assetUrn, source)`.
- Create `apps/web/src/hooks/useSchemaCatalog.ts`: load/caches schema, ignores stale responses, retries, and explicitly requests recorded fallback.
- Create `apps/web/src/components/FieldCombobox.tsx`: accessible searchable field selection with type/nullability details.
- Modify `apps/web/src/components/ChangeForm.tsx`: replace current-field free text, bind current type to schema, and expose loading/error/provenance states.
- Modify `apps/web/src/App.tsx`: own schema loading, clear stale operation values on field change, and distinguish the official dataset from the single default request.
- Modify `apps/web/src/changeDraft.ts`: add `isOfficialDataset` while retaining `isOfficialScenario` for the exact default request.

### Exact route presentation

- Create `apps/web/src/lineageRoute.ts`: one pure route builder and formatters shared by visual and accessible views.
- Modify `apps/web/src/components/ImpactGraph.tsx`: render source endpoint, destination endpoint, precision, hop count, and empty-evidence states.
- Modify `apps/web/src/components/EvidenceDrawer.tsx`: show raw endpoint fields, ordered URNs, provenance limitation, and DataHub link.
- Modify `apps/web/src/lineageEvidence.ts`: delegate kind/degree language to the route contract without losing existing API compatibility.
- Modify `apps/web/src/styles.css`: combobox, route line, empty state, mobile wrapping, focus, and reduced-motion rules.

### Proof and public documentation

- Modify focused Python and web tests listed in the tasks below.
- Modify `tests/e2e/golden-flow.spec.ts`: prove two selected fields create different requests/routes/artifacts.
- Modify `tests/e2e/capture-screenshots.spec.ts`: capture the final dropdown and exact route proof.
- Modify `docs/architecture.md`, `docs/demo-script.md`, `docs/devpost-submission.md`, and `design-qa.md`: describe and record multi-field proof without overclaiming missing lineage.

---

### Task 1: Define schema discovery and lineage precision contracts

**Files:**
- Modify: `apps/api/src/changesafe/domain.py`
- Modify: `apps/api/src/changesafe/context/base.py`
- Modify: `apps/api/tests/test_domain.py`
- Modify: `apps/api/tests/publication/helpers.py`
- Modify: test doubles implementing `DataHubContextPort` under `apps/api/tests/`
- Modify: `fixtures/datahub/golden-context.json`
- Modify: `fixtures/datahub/golden-context.sha256`
- Modify: `examples/generated-safe-change/changesafe-manifest.json`

**Interfaces:**
- Produces: `LineagePrecision`, `SchemaCatalog`, and `DataHubContextPort.discover_schema(asset_urn: str) -> SchemaCatalog`.
- Preserves: existing `load(change)` and `writeback(decision, ...)` behavior.

- [ ] **Step 1: Add failing strict-domain tests**

Add imports and these assertions to `apps/api/tests/test_domain.py`:

```python
from pydantic import ValidationError

from changesafe.domain import (
    ContextMode,
    ContextProvenance,
    LineagePrecision,
    SchemaCatalog,
    SchemaField,
)


def test_schema_catalog_requires_a_nonempty_unique_schema() -> None:
    provenance = ContextProvenance(
        mode=ContextMode.SNAPSHOT,
        retrieved_at="2026-08-08T20:00:00Z",
        adapter_version="recorded-catalog/2",
        snapshot_hash="a" * 64,
    )
    with pytest.raises(ValidationError, match="schema_fields"):
        SchemaCatalog(
            target_urn="urn:li:dataset:demo",
            target_name="demo",
            schema_fields=[],
            provenance=provenance,
        )
    with pytest.raises(ValidationError, match="duplicate"):
        SchemaCatalog(
            target_urn="urn:li:dataset:demo",
            target_name="demo",
            schema_fields=[
                SchemaField(name="order_id", data_type="NUMBER", nullable=False),
                SchemaField(name="ORDER_ID", data_type="NUMBER", nullable=False),
            ],
            provenance=provenance,
        )


def test_affected_asset_requires_explicit_lineage_precision() -> None:
    asset = AffectedAsset(
        urn="urn:li:dataset:upstream",
        name="upstream",
        entity_type="dataset",
        field="order_id",
        lineage_degree=1,
        lineage_precision=LineagePrecision.EXACT_FIELD,
    )
    assert asset.lineage_precision is LineagePrecision.EXACT_FIELD
```

- [ ] **Step 2: Run the focused tests and confirm failure**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest apps/api/tests/test_domain.py -q
```

Expected: import failures for `SchemaCatalog` and `LineagePrecision`.

- [ ] **Step 3: Add strict public models**

Add to `apps/api/src/changesafe/domain.py`:

```python
class LineagePrecision(StrEnum):
    EXACT_FIELD = "exact_field"
    ENDPOINT_FIELD = "endpoint_field"
    DATASET_LEVEL = "dataset_level"


class SchemaCatalog(StrictModel):
    target_urn: str = Field(min_length=8, pattern=r"^urn:li:")
    target_name: str = Field(min_length=1)
    schema_fields: list[SchemaField] = Field(min_length=1)
    provenance: ContextProvenance

    @model_validator(mode="after")
    def require_unique_fields(self) -> SchemaCatalog:
        names = [field.name.casefold() for field in self.schema_fields]
        if len(names) != len(set(names)):
            raise ValueError("schema_fields contains duplicate field names")
        return self
```

Add `lineage_precision: LineagePrecision` to `AffectedAsset` without a permissive default. Place `SchemaCatalog` after `ContextProvenance` so every referenced type is defined.

- [ ] **Step 4: Extend the context port and test doubles**

Add to `DataHubContextPort`:

```python
async def discover_schema(self, asset_urn: str) -> SchemaCatalog: ...
```

Update every concrete fake port to delegate or return a minimal valid catalog. Use this shared test implementation where appropriate:

```python
async def discover_schema(self, asset_urn: str) -> SchemaCatalog:
    context = await self.delegate.load(golden_change())
    if context.target_urn != asset_urn:
        raise ContextLoadError("Snapshot does not contain the requested asset")
    return SchemaCatalog(
        target_urn=context.target_urn,
        target_name=context.target_name,
        schema_fields=context.schema_fields,
        provenance=context.provenance,
    )
```

- [ ] **Step 5: Update existing affected-asset fixtures explicitly**

For every test-created `AffectedAsset`, set one of:

```python
lineage_precision=LineagePrecision.EXACT_FIELD
lineage_precision=LineagePrecision.ENDPOINT_FIELD
lineage_precision=LineagePrecision.DATASET_LEVEL
```

Use `EXACT_FIELD` only for degree-one field evidence, `ENDPOINT_FIELD` for a known endpoint on a multi-hop result, and `DATASET_LEVEL` when `field is None`.

Update every asset in the current checked-in snapshot with the same explicit
classification, recalculate `golden-context.sha256`, and run
`scripts/regenerate_examples.py`. This keeps the repository green before Task 3
replaces the single-field snapshot with the versioned catalog; do not introduce a
temporary default that silently classifies old evidence.

- [ ] **Step 6: Re-run domain and context tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest apps/api/tests/test_domain.py apps/api/tests/context/test_contract.py apps/api/tests/test_risk.py -q
```

Expected: all pass; failures about missing `lineage_precision` indicate an unsafe fixture that still needs an explicit classification.

- [ ] **Step 7: Commit the contract**

```powershell
git add apps/api/src/changesafe/domain.py apps/api/src/changesafe/context/base.py apps/api/tests
git add fixtures/datahub/golden-context.json fixtures/datahub/golden-context.sha256 examples/generated-safe-change/changesafe-manifest.json
git commit -m "feat: define schema and lineage evidence contracts"
```

---

### Task 2: Implement live schema discovery and truthful route precision

**Files:**
- Modify: `apps/api/src/changesafe/context/live.py`
- Modify: `apps/api/tests/context/test_live_mapping.py`

**Interfaces:**
- Consumes: `SchemaCatalog`, `LineagePrecision`, existing DataHub `get_entities` and `list_schema_fields` tools.
- Produces: `LiveDataHubContext.discover_schema(asset_urn)` and explicit precision on every normalized lineage asset.

- [ ] **Step 1: Write failing live-discovery contract tests**

Add a realistic paginated runner test to `test_live_mapping.py`:

```python
@pytest.mark.asyncio
async def test_live_schema_discovery_returns_complete_allowlisted_schema() -> None:
    runner = FakeRunner(
        {
            "get_entities": {"entities": [{"urn": TARGET, "name": "order_details"}]},
            "list_schema_fields": {
                "fields": [
                    {"fieldPath": "order_id", "nativeDataType": "NUMBER", "nullable": False},
                    {"fieldPath": "cust_email", "nativeDataType": "TEXT", "nullable": True},
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
    assert [(item.name, item.data_type, item.nullable) for item in catalog.schema_fields] == [
        ("order_id", "NUMBER", False),
        ("cust_email", "TEXT", True),
    ]
    assert catalog.provenance.mode is ContextMode.LIVE
    assert [call[0] for call in runner.calls] == ["get_entities", "list_schema_fields"]
```

Add tests that discovery rejects an out-of-allowlist URN before a tool call, rejects duplicate case-insensitive fields, rejects an unsupported quoted top-level field, ignores positively identified nested paths, rejects missing native types, and preserves complete pagination.

Add a field-governance isolation case where the dataset entity has a PII tag but
the selected schema field has only a quality tag. Assert `context.field_tags`
contains the field's quality tag and not the dataset-level PII tag. The same rule
applies to `glossary_terms`; field-scoped risk evidence must not be populated from
an unrelated asset-level label.

- [ ] **Step 2: Write failing precision tests**

Extend current direct, degree-two-without-path, and dataset-only fixtures:

```python
assert direct.lineage_precision is LineagePrecision.EXACT_FIELD
assert multi_hop.lineage_precision is LineagePrecision.ENDPOINT_FIELD
assert asset_only.lineage_precision is LineagePrecision.DATASET_LEVEL
```

Also assert a degree-two result with a two-URN endpoint path remains `ENDPOINT_FIELD`; the short path does not turn it into a direct edge.

- [ ] **Step 3: Run live mapping tests and confirm failure**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest apps/api/tests/context/test_live_mapping.py -q
```

Expected: missing `discover_schema` and `lineage_precision` failures.

- [ ] **Step 4: Refactor schema pagination to accept an asset URN**

Change the private method signature and both call sites:

```python
async def _load_schema_fields(
    self, asset_urn: str, calls: list[ToolEvidence]
) -> Any:
    return await self._call(
        "list_schema_fields",
        calls,
        urn=asset_urn,
        keywords=None,
        limit=200,
        offset=0,
    )
```

Keep the existing forward-progress, total, offset, and completeness checks unchanged for subsequent pages.

- [ ] **Step 5: Extract one strict schema normalizer**

Add a helper used by discovery and `_normalize_context`:

```python
def _normalize_schema_fields(schema_raw: Any) -> list[SchemaField]:
    fields = _extract_fields(schema_raw)
    normalized: list[SchemaField] = []
    seen: set[str] = set()
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
        key = raw_name.casefold()
        if key in seen:
            raise ContextLoadError("DataHub schema contains duplicate field identifiers")
        seen.add(key)
        data_type = _field_type(item)
        if data_type == "UNKNOWN":
            raise ContextLoadError(
                "DataHub schema field is missing a concrete native type"
            )
        normalized.append(
            SchemaField(
                name=raw_name,
                data_type=data_type,
                nullable=bool(item.get("nullable", True)),
            )
        )
    if not normalized:
        raise ContextLoadError("DataHub returned an empty supported schema")
    return normalized
```

Preserve the existing page-completeness check before calling this helper.

- [ ] **Step 6: Implement `discover_schema`**

Add:

```python
async def discover_schema(self, asset_urn: str) -> SchemaCatalog:
    if asset_urn not in self.allowlist:
        raise PermissionError("Asset is outside the configured DataHub allowlist")
    calls: list[ToolEvidence] = []
    entities_raw = await self._call("get_entities", calls, urns=[asset_urn])
    schema_raw = await self._load_schema_fields(asset_urn, calls)
    entities = _extract_entities(entities_raw)
    if not entities:
        raise ContextLoadError("Target asset was not returned by DataHub")
    return SchemaCatalog(
        target_urn=asset_urn,
        target_name=_display_name(entities[0], "unknown") or "unknown",
        schema_fields=_normalize_schema_fields(schema_raw),
        provenance=ContextProvenance(
            mode=ContextMode.LIVE,
            retrieved_at=datetime.now(UTC),
            adapter_version="datahub-agent-context/1.7.0",
        ),
    )
```

Update `load()` to call `_load_schema_fields(change.asset_urn, calls)` and reuse `_normalize_schema_fields` when constructing `ContextBundle`.

Normalize `field_tags` and `glossary_terms` from the matched schema field only:

```python
field_tags = list(dict.fromkeys(_urns(field.get("tags"))))
terms = list(dict.fromkeys(_urns(field.get("glossaryTerms"))))
```

Dataset ownership and structured properties remain dataset-level context, but
they are not relabeled as field governance.

- [ ] **Step 7: Attach explicit lineage precision**

In `_normalize_lineage_assets`, compute:

```python
if field_path is None:
    precision = LineagePrecision.DATASET_LEVEL
elif lineage_degree == 1:
    precision = LineagePrecision.EXACT_FIELD
else:
    precision = LineagePrecision.ENDPOINT_FIELD
```

Pass `lineage_precision=precision`. Never reduce `lineage_degree` based on a shorter returned path.

- [ ] **Step 8: Re-run focused live and strict static checks**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest apps/api/tests/context/test_live_mapping.py -q
.\.venv\Scripts\python.exe -m ruff check apps/api/src/changesafe/context/live.py apps/api/tests/context/test_live_mapping.py
.\.venv\Scripts\python.exe -m mypy apps/api/src
```

Expected: all pass.

- [ ] **Step 9: Commit live discovery**

```powershell
git add apps/api/src/changesafe/context/live.py apps/api/tests/context/test_live_mapping.py
git commit -m "feat: discover live schemas safely"
```

---

### Task 3: Build the checksummed multi-field recorded catalog

**Files:**
- Modify: `apps/api/src/changesafe/context/replay.py`
- Modify: `scripts/capture_snapshot.py`
- Create: `scripts/capture_field_catalog.py`
- Modify: `fixtures/datahub/golden-context.json`
- Modify: `fixtures/datahub/golden-context.sha256`
- Modify: `apps/api/tests/context/test_contract.py`
- Modify: `apps/api/tests/context/test_scripts.py`
- Modify: `apps/api/tests/test_config.py`
- Modify: `apps/api/tests/publication/test_idempotency.py`
- Modify: `examples/generated-safe-change/*`

**Interfaces:**
- Consumes: live `discover_schema` and `load` results.
- Produces: versioned recorded catalog `snapshot_version == 2`, `ReplayDataHubContext.discover_schema`, and selected-field `ContextBundle` reconstruction.

- [ ] **Step 1: Add failing recorded-catalog tests**

Change `test_replay_uses_the_official_order_entry_scenario` into parametrized field coverage:

```python
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "expected_type"),
    [("cust_email", "TEXT"), ("order_total", "FLOAT"), ("order_status", "NUMBER")],
)
async def test_replay_builds_a_field_scoped_context(
    field: str, expected_type: str
) -> None:
    change = golden_change().model_copy(
        update={"field": field, "new_field": f"preferred_{field}"}
    )
    context = await ReplayDataHubContext.from_default().load(change)

    assert context.field == field
    assert context.field_type == expected_type
    assert all(
        asset.field is None or field.casefold() in asset.field.casefold()
        for asset in [*context.upstream_assets, *context.downstream_assets]
    )
    if field != "cust_email":
        scoped_text = json.dumps(
            {
                "field_tags": context.field_tags,
                "glossary_terms": context.glossary_terms,
                "queries": context.queries,
                "evidence": [item.model_dump(mode="json") for item in context.evidence],
                "upstream": [item.model_dump(mode="json") for item in context.upstream_assets],
                "downstream": [item.model_dump(mode="json") for item in context.downstream_assets],
            }
        )
        assert "cust_email" not in scoped_text
```

Add:

```python
catalog = await ReplayDataHubContext.from_default().discover_schema(TARGET)
assert len(catalog.schema_fields) == 55
assert catalog.provenance.mode is ContextMode.SNAPSHOT
assert len(catalog.provenance.snapshot_hash or "") == 64
```

Add temporary-catalog tests that reject a missing field context, an extra field context, checksum drift, duplicate schema names, and an unknown selected field.

- [ ] **Step 2: Run replay tests and confirm failure**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest apps/api/tests/context/test_contract.py -q
```

Expected: non-email loads fail with `Snapshot does not contain the requested field`.

- [ ] **Step 3: Define private versioned snapshot models**

In `context/replay.py`, add strict internal models:

```python
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
        expected = {item.name for item in self.schema_fields}
        if set(self.fields) != expected:
            raise ValueError("recorded field contexts must exactly match schema_fields")
        return self
```

The serialized provenance omits `snapshot_hash`; `ReplayDataHubContext` injects the verified digest after reading bytes.

- [ ] **Step 4: Reconstruct only the selected field**

Refactor `_load_payload()` to return `RecordedDataHubCatalog, digest`. Implement:

```python
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
```

In `load(change)`, look up `catalog.fields[change.field]` exactly and construct `ContextBundle` from common dataset metadata plus only that record. Reject an absent field with `Snapshot does not contain the requested field`.

- [ ] **Step 5: Make snapshot writes atomic**

Add to `scripts/capture_snapshot.py`:

```python
def write_snapshot_atomic(payload: Any, snapshot: Path, checksum: Path) -> str:
    raw = canonical_bytes(payload)
    digest = hashlib.sha256(raw).hexdigest()
    snapshot.parent.mkdir(parents=True, exist_ok=True)
    checksum.parent.mkdir(parents=True, exist_ok=True)
    snapshot_tmp = snapshot.with_suffix(snapshot.suffix + ".tmp")
    checksum_tmp = checksum.with_suffix(checksum.suffix + ".tmp")
    snapshot_tmp.write_bytes(raw)
    checksum_tmp.write_text(f"{digest}  {snapshot.name}\n", encoding="ascii")
    snapshot_tmp.replace(snapshot)
    checksum_tmp.replace(checksum)
    return digest
```

Make the existing `write_snapshot` delegate to this helper so no caller can leave a catalog/checksum pair half-written.

- [ ] **Step 6: Add a read-only catalog capture script with fake-port tests**

Create `scripts/capture_field_catalog.py` with these boundaries:

```python
async def build_recorded_catalog(
    port: DataHubContextPort, target_urn: str
) -> RecordedDataHubCatalog:
    schema = await port.discover_schema(target_urn)
    contexts: dict[str, RecordedFieldContext] = {}
    shared: ContextBundle | None = None
    for schema_field in schema.schema_fields:
        change = ChangeRequest(
            asset_urn=target_urn,
            operation=ChangeOperation.RENAME,
            field=schema_field.name,
            new_field=f"changesafe_candidate_{schema_field.name}",
            source_commit="recorded-field-catalog-v2",
            requested_by="changesafe-capture",
        )
        context = await port.load(change)
        shared = shared or context
        contexts[schema_field.name] = RecordedFieldContext(
            field_type=context.field_type,
            upstream_assets=context.upstream_assets,
            downstream_assets=context.downstream_assets,
            field_tags=context.field_tags,
            glossary_terms=context.glossary_terms,
            usage_tier=context.usage_tier,
            queries=context.queries,
            evidence=context.evidence,
            tool_evidence=context.tool_evidence,
        )
    if shared is None:
        raise ContextLoadError("DataHub schema did not contain supported fields")
    return RecordedDataHubCatalog(
        snapshot_version=2,
        target_urn=shared.target_urn,
        target_name=shared.target_name,
        target_domain=shared.target_domain,
        schema_fields=schema.schema_fields,
        owners=shared.owners,
        structured_properties=shared.structured_properties,
        fields=contexts,
        provenance=schema.provenance.model_copy(
            update={"mode": ContextMode.SNAPSHOT, "snapshot_hash": None}
        ),
    )
```

The CLI uses `Settings()` and `build_context_port(settings)` only when live credentials are configured, performs reads sequentially, prints progress as `Captured field N/55`, redacts exception text, closes the adapter in `finally`, and calls `write_snapshot_atomic` only after all field loads succeed. Add fake-port tests proving no output is replaced after a later-field failure.

- [ ] **Step 7: Run capture-script tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest apps/api/tests/context/test_scripts.py -q
```

Expected: all fake capture, redaction, atomicity, close, and partial-failure tests pass.

- [ ] **Step 8: Capture the official 55-field catalog from local live DataHub**

With the existing private env file selected through `CHANGESAFE_ENV_FILE`, run:

```powershell
$env:CHANGESAFE_ENV_FILE='C:\Users\harik\ChangeSafe\private\changesafe.env'
$env:CHANGESAFE_MODE='live'
.\.venv\Scripts\python.exe scripts/capture_field_catalog.py `
  --target-urn 'urn:li:dataset:(urn:li:dataPlatform:dbt,b2fd91.ORDER_ENTRY_DB.analytics.order_details,PROD)' `
  --snapshot fixtures/datahub/golden-context.json `
  --checksum fixtures/datahub/golden-context.sha256
```

Expected: exactly 55 successful field messages followed by one digest; no token or raw exception is printed. If any field fails, stop and fix the adapter/capture contract rather than synthesizing its context.

- [ ] **Step 9: Regenerate deterministic examples and verify field isolation**

Run:

```powershell
.\.venv\Scripts\python.exe scripts/regenerate_examples.py
.\.venv\Scripts\python.exe scripts/regenerate_examples.py --check
.\.venv\Scripts\python.exe -m pytest apps/api/tests/context apps/api/tests/test_generation.py apps/api/tests/test_risk.py apps/api/tests/test_impact.py -q
```

Expected: all pass. Inspect `order_total` and `order_status` contexts to confirm they contain no field evidence mentioning `cust_email`; common dataset-level metadata may remain only when it was captured for those fields.

- [ ] **Step 10: Commit the recorded catalog**

```powershell
git add apps/api/src/changesafe/context/replay.py scripts/capture_snapshot.py scripts/capture_field_catalog.py fixtures/datahub apps/api/tests/context apps/api/tests/test_config.py apps/api/tests/publication/test_idempotency.py examples/generated-safe-change
git commit -m "feat: record field-scoped DataHub contexts"
```

---

### Task 4: Expose bounded schema discovery to the browser

**Files:**
- Modify: `apps/api/src/changesafe/api.py`
- Modify: `apps/api/tests/test_api.py`
- Modify: `apps/web/src/types.ts`
- Modify: `apps/web/src/api.ts`
- Modify: `apps/web/tests/api.test.ts`
- Modify: `apps/web/tests/fixtures.ts`
- Modify: inline `ChangeSafeApi` mocks in `apps/web/tests/App.test.tsx`

**Interfaces:**
- Produces: `GET /api/schema-fields?asset_urn=<urn>&source=active|recorded` and `ChangeSafeApi.getSchemaCatalog`.
- Consumes: active context adapter and the existing AUTO-mode snapshot adapter.

- [ ] **Step 1: Add failing FastAPI endpoint tests**

Add to `apps/api/tests/test_api.py`:

```python
@pytest.mark.asyncio
async def test_schema_endpoint_returns_recorded_fields_without_credentials(
    tmp_path: Path,
) -> None:
    app = create_app(
        settings=Settings(
            _env_file=None,
            mode=Mode.REPLAY,
            changesafe_data_path=tmp_path / "runs.db",
        ),
        context_port=ReplayDataHubContext.from_default(),
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/api/schema-fields",
            params={"asset_urn": DEMO_TARGET_URN, "source": "active"},
        )
    assert response.status_code == 200
    assert len(response.json()["schema_fields"]) == 55
    assert response.json()["provenance"]["mode"] == "snapshot"
    assert "token" not in response.text.casefold()
```

Add cases for malformed URN (422), out-of-allowlist (403), transport failure (502 with stable public copy), `source=recorded` in AUTO mode, recorded fallback unavailable in LIVE mode (409), and per-client schema rate limiting without consuming the run-creation quota.

- [ ] **Step 2: Run the API test and confirm failure**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest apps/api/tests/test_api.py -q
```

Expected: `/api/schema-fields` returns 404.

- [ ] **Step 3: Implement the bounded endpoint**

Use typed query validation:

```python
@app.get("/api/schema-fields", response_model=SchemaCatalog)
async def schema_fields(
    request: Request,
    asset_urn: Annotated[str, Query(min_length=8, pattern=r"^urn:li:")],
    source: Literal["active", "recorded"] = "active",
) -> SchemaCatalog:
    client = request.client.host if request.client is not None else "unknown"
    if not await schema_rate_limiter.allow(f"schema:{client}"):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Schema lookup rate limit exceeded; retry in one minute.",
            headers={"Retry-After": "60"},
        )
    selected = active_context
    if source == "recorded":
        if isinstance(active_context, ReplayDataHubContext):
            selected = active_context
        elif snapshot_context is not None:
            selected = snapshot_context
        else:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Recorded DataHub evidence is not configured.",
            )
    try:
        return await selected.discover_schema(asset_urn)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail="Asset is outside the configured allowlist") from exc
    except ContextAuthorizationError as exc:
        raise HTTPException(status_code=503, detail="DataHub authorization is unavailable") from exc
    except ContextLoadError as exc:
        raise HTTPException(status_code=502, detail="DataHub schema could not be loaded") from exc
```

Create a separate `RunRateLimiter` instance for schema lookups so dropdown loading cannot consume Analyze capacity.

- [ ] **Step 4: Add failing browser-client tests**

In `apps/web/tests/api.test.ts`, mock `fetch` and assert:

```ts
await api.getSchemaCatalog(OFFICIAL_TARGET, "recorded");
expect(fetch).toHaveBeenCalledWith(
  `/api/schema-fields?${new URLSearchParams({
    asset_urn: OFFICIAL_TARGET,
    source: "recorded",
  })}`,
);
```

Also assert safe API detail messages flow through `ApiError` and no header contains a DataHub token.

- [ ] **Step 5: Add TypeScript contracts and client method**

In `types.ts`:

```ts
export interface SchemaField {
  name: string;
  data_type: string;
  nullable: boolean;
}

export interface SchemaCatalog {
  target_urn: string;
  target_name: string;
  schema_fields: SchemaField[];
  provenance: ContextBundle["provenance"];
}

export type SchemaEvidenceSource = "active" | "recorded";
```

Use `SchemaField[]` inside `ContextBundle` and add to `ChangeSafeApi`:

```ts
getSchemaCatalog(
  assetUrn: string,
  source?: SchemaEvidenceSource,
): Promise<SchemaCatalog>;
```

Implement it with `URLSearchParams` and `responseJson` in `api.ts`.

Add `lineage_precision: "exact_field" | "endpoint_field" | "dataset_level"`
to the TypeScript `AffectedAsset` contract. Update `createGoldenApi()` and every
inline `ChangeSafeApi` mock with `getSchemaCatalog`, and classify every web
lineage fixture explicitly so `pnpm typecheck` remains green at this commit.

- [ ] **Step 6: Re-run API and client tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest apps/api/tests/test_api.py -q
pnpm --filter @changesafe/web test --run tests/api.test.ts
pnpm --filter @changesafe/web typecheck
```

Expected: all pass.

- [ ] **Step 7: Commit the API boundary**

```powershell
git add apps/api/src/changesafe/api.py apps/api/tests/test_api.py apps/web/src/types.ts apps/web/src/api.ts apps/web/tests/api.test.ts apps/web/tests/fixtures.ts apps/web/tests/App.test.tsx
git commit -m "feat: expose safe schema discovery"
```

---

### Task 5: Add the schema hook and accessible field dropdown

**Files:**
- Create: `apps/web/src/hooks/useSchemaCatalog.ts`
- Create: `apps/web/src/components/FieldCombobox.tsx`
- Modify: `apps/web/src/components/ChangeForm.tsx`
- Modify: `apps/web/src/App.tsx`
- Modify: `apps/web/src/changeDraft.ts`
- Modify: `apps/web/src/styles.css`
- Create: `apps/web/tests/useSchemaCatalog.test.tsx`
- Create: `apps/web/tests/FieldCombobox.test.tsx`
- Modify: `apps/web/tests/ChangeForm.test.tsx`
- Modify: `apps/web/tests/changeDraft.test.ts`
- Modify: `apps/web/tests/App.test.tsx`
- Modify: `apps/web/tests/fixtures.ts`

**Interfaces:**
- Consumes: `ChangeSafeApi.getSchemaCatalog`, `SchemaCatalog`, `SchemaField`.
- Produces: exact returned-field selection, recorded fallback action, and schema-bound draft type.

- [ ] **Step 1: Add failing hook tests for loading, stale responses, and fallback**

Use `renderHook` with deferred promises:

```tsx
it("keeps the latest asset schema when an older request resolves late", async () => {
  const first = deferred<SchemaCatalog>();
  const second = deferred<SchemaCatalog>();
  const api = mockApi({
    getSchemaCatalog: vi
      .fn()
      .mockReturnValueOnce(first.promise)
      .mockReturnValueOnce(second.promise),
  });
  const { result, rerender } = renderHook(
    ({ urn }) => useSchemaCatalog(api, urn),
    { initialProps: { urn: "urn:li:dataset:first" } },
  );
  rerender({ urn: "urn:li:dataset:second" });
  second.resolve(secondCatalog);
  await waitFor(() => expect(result.current.catalog).toBe(secondCatalog));
  first.resolve(firstCatalog);
  await act(async () => undefined);
  expect(result.current.catalog).toBe(secondCatalog);
});
```

Add tests for session-local cache reuse, retry after error, invalid URN without a request, and `loadRecorded()` calling source `recorded` explicitly.

- [ ] **Step 2: Implement `useSchemaCatalog` minimally**

Return this stable shape:

```ts
interface SchemaCatalogState {
  catalog: SchemaCatalog | null;
  loading: boolean;
  error: string | null;
  source: SchemaEvidenceSource;
  retry(): void;
  loadRecorded(): void;
}
```

Use a module-local `Map<string, SchemaCatalog>` cache keyed by
`${source}:${assetUrn}` so it survives component resets without persisting stale
live metadata across a page reload. Use a monotonically increasing request ID and
an effect cleanup boolean. Do not set old catalog data for a new URN.

- [ ] **Step 3: Add failing combobox interaction tests**

Test visible option detail and keyboard behavior:

```tsx
render(
  <FieldCombobox
    disabled={false}
    fields={schemaFields}
    onChange={onChange}
    value="cust_email"
  />,
);
const input = screen.getByRole("combobox", { name: "Current field" });
await user.click(input);
await user.clear(input);
await user.type(input, "order");
expect(screen.getByRole("option", { name: /order_total.*FLOAT.*required/i })).toBeVisible();
await user.keyboard("{ArrowDown}{Enter}");
expect(onChange).toHaveBeenCalledWith(
  expect.objectContaining({ name: "order_total", data_type: "FLOAT" }),
);
```

Add Escape, no-results, exact selected value, disabled/loading, and blur-without-valid-selection tests. Assert every option has `aria-selected` and the input exposes `aria-controls`, `aria-expanded`, and `aria-activedescendant` while open.

- [ ] **Step 4: Implement the accessible `FieldCombobox`**

Use an `<input role="combobox" aria-autocomplete="list">` controlling a `<ul role="listbox">`. Filter case-insensitively by name and type, keep a local query separate from the selected field, and commit only an option supplied in `fields`. Render option text as:

```tsx
<span>{field.name}</span>
<small>{field.data_type} · {field.nullable ? "nullable" : "required"}</small>
```

Do not expose an arbitrary typed query as a valid `ChangeRequest.field`.

- [ ] **Step 5: Add failing form and App tests**

Update fixtures with a 55-field `schemaCatalog`. Assert:

```tsx
expect(screen.getByRole("combobox", { name: "Current field" })).toHaveValue("cust_email");
await selectField(user, "order_total");
expect(screen.getByLabelText("Current type")).toHaveValue("FLOAT");
expect(screen.getByLabelText("New field")).toHaveValue("");
expect(screen.getByRole("button", { name: "Analyze change" })).toBeDisabled();
await user.type(screen.getByLabelText("New field"), "preferred_order_total");
expect(screen.getByRole("button", { name: "Analyze change" })).toBeEnabled();
```

Add states for `Loading fields…`, safe discovery error, Retry, explicit `Use recorded fields` in AUTO mode, and no recorded fallback action in LIVE mode. Add a test proving a selected field invalidates and removes the previous analyzed workspace only after the user chooses `New analysis`; an existing run remains immutable.

- [ ] **Step 6: Wire schema state into the form**

In `App.tsx` call:

```ts
const schema = useSchemaCatalog(api, draft.asset_urn);
```

Pass schema state to `ChangeForm`. When a field is selected:

```ts
const selectCurrentField = (selected: SchemaField) => {
  setDraft((current) => ({
    ...current,
    field: selected.name,
    old_type: selected.data_type,
    new_field: current.field === selected.name ? current.new_field : "",
  }));
};
```

Do not change `run.request` or `run.analysis` after submission.

- [ ] **Step 7: Replace current field input and bind current type**

In `ChangeForm.tsx`:

- render `FieldCombobox` only before submission;
- show `Reading schema from Live DataHub` or `Reading checksum-verified recorded schema` from catalog provenance;
- render current type as a read-only value for type change;
- disable Analyze when busy, schema is loading/failed, no exact selected schema field exists, or required operation fields are blank; and
- keep the advanced Dataset URN control, but clear old options as soon as its value changes.

Add `isOfficialDataset(change)` in `changeDraft.ts`:

```ts
export function isOfficialDataset(
  change: Pick<ChangeDraft, "asset_urn">,
): boolean {
  return change.asset_urn === OFFICIAL_TARGET;
}
```

Use it for dataset-level hero/scenario labels; retain `isOfficialScenario` only for the exact default request.

- [ ] **Step 8: Add combobox and schema-state styling**

Add existing-token-based styles for `.field-combobox`, `.field-combobox-list`, `.field-option`, `.schema-source`, `.schema-error`, focus-visible, selected/active option, and mobile wrapping. The list is bounded with `max-height` and scroll; it must remain within 430 px without page-level horizontal overflow.

- [ ] **Step 9: Run focused frontend tests and static gates**

Run:

```powershell
pnpm --filter @changesafe/web test --run tests/useSchemaCatalog.test.tsx tests/FieldCombobox.test.tsx tests/ChangeForm.test.tsx tests/changeDraft.test.ts tests/App.test.tsx
pnpm --filter @changesafe/web lint
pnpm --filter @changesafe/web typecheck
pnpm --filter @changesafe/web build
```

Expected: all pass.

- [ ] **Step 10: Commit field selection**

```powershell
git add apps/web/src/hooks/useSchemaCatalog.ts apps/web/src/components/FieldCombobox.tsx apps/web/src/components/ChangeForm.tsx apps/web/src/App.tsx apps/web/src/changeDraft.ts apps/web/src/styles.css apps/web/tests
git commit -m "feat: select fields from DataHub schema"
```

---

### Task 6: Render exact directional field routes without fabricated columns

**Files:**
- Create: `apps/web/src/lineageRoute.ts`
- Modify: `apps/web/src/lineageEvidence.ts`
- Modify: `apps/web/src/components/ImpactGraph.tsx`
- Modify: `apps/web/src/components/EvidenceDrawer.tsx`
- Modify: `apps/web/src/styles.css`
- Create: `apps/web/tests/lineageRoute.test.ts`
- Modify: `apps/web/tests/ImpactGraph.test.tsx`

**Interfaces:**
- Consumes: `ContextBundle`, `AffectedAsset`, `LineagePrecision`.
- Produces: one `buildLineageRoute(context, asset, direction)` representation shared by cards, drawer, and accessible list.

- [ ] **Step 1: Add failing pure route tests**

Create `apps/web/tests/lineageRoute.test.ts`:

```ts
it("builds exact upstream and downstream endpoint order", () => {
  const upstream = buildLineageRoute(context, upstreamAsset, "upstream");
  expect(upstream.source).toEqual({
    urn: upstreamAsset.urn,
    name: upstreamAsset.name,
    field: "cust_email",
  });
  expect(upstream.destination).toEqual({
    urn: context.target_urn,
    name: context.target_name,
    field: context.field,
  });

  const downstream = buildLineageRoute(context, downstreamAsset, "downstream");
  expect(downstream.source.urn).toBe(context.target_urn);
  expect(downstream.destination.urn).toBe(downstreamAsset.urn);
});
```

Add exact assertions for:

- `order_details.cust_email -> ORDER_DETAILS.cust_email`;
- degree two plus endpoint field: `2 hops; intermediate column mapping not returned by DataHub`;
- downstream dataset-only: `Dataset-level relationship; destination field not returned by DataHub`;
- upstream dataset-only: `Dataset-level relationship; source field not returned by DataHub`;
- recorded degree two with a two-URN path remains multi-hop; and
- a concrete path derives hop degree only when authoritative degree is absent.

- [ ] **Step 2: Run the route test and confirm failure**

Run:

```powershell
pnpm --filter @changesafe/web test --run tests/lineageRoute.test.ts
```

Expected: module-not-found failure.

- [ ] **Step 3: Implement the pure route contract**

Create:

```ts
export type RouteDirection = "upstream" | "downstream";

export interface FieldEndpoint {
  urn: string;
  name: string;
  field: string | null;
}

export interface LineageRoute {
  direction: RouteDirection;
  source: FieldEndpoint;
  destination: FieldEndpoint;
  degree: number | null;
  precision: LineagePrecision;
  orderedAssetPath: string[];
  limitation: string | null;
}

export function lineageDegree(asset: AffectedAsset): number | null {
  const pathDegree =
    asset.lineage_path.length >= 2 ? asset.lineage_path.length - 1 : null;
  if (asset.lineage_degree === null) return pathDegree;
  if (pathDegree === null) return asset.lineage_degree;
  return Math.max(asset.lineage_degree, pathDegree);
}

export function buildLineageRoute(
  context: ContextBundle,
  asset: AffectedAsset,
  direction: RouteDirection,
): LineageRoute {
  const target = {
    urn: context.target_urn,
    name: context.target_name,
    field: context.field,
  };
  const endpoint = { urn: asset.urn, name: asset.name, field: asset.field };
  const degree = lineageDegree(asset);
  const source = direction === "upstream" ? endpoint : target;
  const destination = direction === "upstream" ? target : endpoint;
  const limitation =
    asset.lineage_precision === "dataset_level"
      ? `Dataset-level relationship; ${
          direction === "upstream" ? "source" : "destination"
        } field not returned by DataHub`
      : asset.lineage_precision === "endpoint_field" && degree !== null && degree > 1
        ? `${degree} hops; intermediate column mapping not returned by DataHub`
        : null;
  return {
    direction,
    source,
    destination,
    degree,
    precision: asset.lineage_precision,
    orderedAssetPath: asset.lineage_path,
    limitation,
  };
}
```

Add `formatEndpoint(endpoint)` and `formatRoute(route)` pure helpers. Preserve the exact raw `field` string in the drawer; route display may visually separate asset and field but must not change the value.

`lineageRoute.ts` owns `lineageDegree`. `lineageEvidence.ts` imports and
re-exports or wraps that function; `lineageRoute.ts` must not import
`lineageEvidence.ts`, preventing a circular module dependency.

- [ ] **Step 4: Add failing graph and drawer assertions**

In `ImpactGraph.test.tsx`, assert visible and accessible routes:

```tsx
expect(
  screen.getByText("stg_order_details.cust_email → order_details.cust_email"),
).toBeVisible();
expect(
  screen.getByText("order_details.cust_email → ORDER_DETAILS.cust_email"),
).toBeVisible();
```

For an endpoint-only multi-hop asset assert the limitation text appears on the card and in the drawer. For a dataset-level dashboard assert no invented `.cust_email` suffix appears after the dashboard name. Open the accessible list and assert it contains the same formatted routes and limitations for both directions.

Add an empty upstream/downstream case that renders `No field-level upstream evidence returned` and `No recorded downstream field route` rather than a blank column.

- [ ] **Step 5: Render the shared route in every view**

In `ImpactGraph.tsx`, map assets with their direction, call `buildLineageRoute`, and render:

```tsx
<span className="field-route">{formatRoute(route)}</span>
<small>{route.degree ? `${route.degree} ${route.degree === 1 ? "hop" : "hops"}` : "Degree not returned"}</small>
{route.limitation ? <em>{route.limitation}</em> : null}
```

Pass `context` and `direction` into `EvidenceDrawer`, or pass the already-built `LineageRoute`. The drawer shows source/destination names, URNs, exact raw fields, ordered path URNs, precision, limitation, and the existing safe DataHub link.

Make the accessible list consume the same `LineageRoute`; do not maintain a second string-building path.

- [ ] **Step 6: Keep compatibility lineage labels delegated**

Update `compactLineageLabel(asset)` to use `lineageDegree` plus `lineage_precision` so old labels remain truthful:

```ts
if (asset.lineage_precision === "dataset_level") return "dataset-level relationship";
if (degree === null) return "field endpoint; degree unavailable";
return degree === 1 ? "direct field route (1 hop)" : `multi-hop field route (${degree} hops)`;
```

Do not label endpoint-only degree-two evidence as direct even if `lineage_path` contains only source and endpoint URNs.

- [ ] **Step 7: Style exact routes and responsive states**

Use existing colors and type tokens. Permit route fields to wrap at dots/underscores without truncating essential endpoint text. On 430 px, stack source, arrow, and destination vertically while preserving reading order. Under `prefers-reduced-motion`, remove the travelling light and retain static directional arrows and route text.

- [ ] **Step 8: Run focused route, graph, accessibility, and build checks**

Run:

```powershell
pnpm --filter @changesafe/web test --run tests/lineageRoute.test.ts tests/ImpactGraph.test.tsx
pnpm --filter @changesafe/web lint
pnpm --filter @changesafe/web typecheck
pnpm --filter @changesafe/web build
```

Expected: all pass with no duplicate route-text logic.

- [ ] **Step 9: Commit exact route presentation**

```powershell
git add apps/web/src/lineageRoute.ts apps/web/src/lineageEvidence.ts apps/web/src/components/ImpactGraph.tsx apps/web/src/components/EvidenceDrawer.tsx apps/web/src/styles.css apps/web/tests/lineageRoute.test.ts apps/web/tests/ImpactGraph.test.tsx
git commit -m "feat: show exact field lineage routes"
```

---

### Task 7: Prove multi-field behavior end to end

**Files:**
- Modify: `apps/api/tests/test_api.py`
- Modify: `apps/api/tests/test_orchestrator.py`
- Modify: `apps/api/tests/test_generation.py`
- Modify: `apps/api/tests/test_verification.py`
- Modify: `apps/web/tests/App.test.tsx`
- Modify: `tests/e2e/golden-flow.spec.ts`
- Modify: `fixtures/dbt_project/` only if a representative generated package requires a fixture input adjustment

**Interfaces:**
- Consumes: recorded 55-field catalog, schema dropdown, exact route UI.
- Produces: repeatable proof that selected fields control context, impacts, generated bytes, and validation.

- [ ] **Step 1: Add a backend three-field proof matrix**

Parametrize `cust_email`, `order_total`, and `order_status` (or `customer_id` if the captured evidence is stronger) with valid operation payloads. Assert for every run:

```python
assert run.analysis is not None
assert run.analysis.context.field == change.field
assert run.analysis.context.field_type == expected_type
assert run.analysis.publication_eligible is True
assert run.analysis.validation.passed is True
assert all(check.passed for check in run.analysis.validation.checks if check.blocking)
assert change.field in run.analysis.artifacts.files[model_path].content
assert run.analysis.artifacts.manifest_hash is not None
```

For non-email contexts, assert no evidence label, query, or field endpoint contains `cust_email`. Do not assert that two numeric risk scores must differ when the captured evidence legitimately produces equal scores; instead assert each risk factor's evidence URNs belong to that saved context.

- [ ] **Step 2: Run the matrix and confirm any remaining leaks**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest apps/api/tests/test_orchestrator.py apps/api/tests/test_generation.py apps/api/tests/test_verification.py -q
```

Expected before final fixes: any remaining default-field assumptions fail by naming `cust_email`.

- [ ] **Step 3: Remove only proven hardcoded field assumptions**

Trace each failing assertion to generation, impact, or verification code. Replace a hardcoded demo field with `change.field`, `context.field`, or the matched `SchemaField`; do not loosen a validation check. Re-run the focused test immediately after each minimal fix.

- [ ] **Step 4: Add an API-level two-run comparison**

Create two replay runs against the same asset and operation, one for `cust_email` and one for `order_total`, wait for `awaiting_approval`, and assert:

```python
assert email_run["request"]["field"] == "cust_email"
assert total_run["request"]["field"] == "order_total"
assert email_run["analysis"]["context"] != total_run["analysis"]["context"]
assert (
    email_run["analysis"]["artifacts"]["manifest_hash"]
    != total_run["analysis"]["artifacts"]["manifest_hash"]
)
total_context = total_run["analysis"]["context"]
field_scoped = {
    "field_tags": total_context["field_tags"],
    "glossary_terms": total_context["glossary_terms"],
    "queries": total_context["queries"],
    "evidence": total_context["evidence"],
    "upstream_assets": total_context["upstream_assets"],
    "downstream_assets": total_context["downstream_assets"],
}
assert "cust_email" not in json.dumps(field_scoped)
```

The complete schema is intentionally excluded from this negative assertion
because `cust_email` remains a valid neighboring column in the same 55-field
dataset contract.

The second request's rename destination must be `preferred_order_total`, avoiding an irrelevant comparison with `primary_email`.

- [ ] **Step 5: Add a browser-level field-change flow**

Extend `golden-flow.spec.ts` after the default proof:

```ts
await page.getByRole("button", { name: "New analysis" }).click();
await page.getByRole("combobox", { name: "Current field" }).fill("order_total");
await page.getByRole("option", { name: /order_total.*FLOAT.*required/i }).click();
await page.getByLabel("New field").fill("preferred_order_total");
await page.getByRole("button", { name: "Analyze change" }).click();
await expect(page.getByText(/order_details\.order_total/).first()).toBeVisible();
await expect(page.getByText(/preferred_order_total/).first()).toBeVisible();
await expect(page.getByText(/cust_email as primary_email/i)).not.toBeVisible();
await expect(page.getByText("12 / 12", { exact: true })).toBeVisible();
```

Open one dependency card and assert the exact source and destination fields or the explicit DataHub limitation, depending on the captured result. Capture console errors and require an empty array.

- [ ] **Step 6: Prove phone containment and keyboard selection**

At 430x932, select another field by keyboard, analyze, open the accessible dependency list, and assert `document.documentElement.scrollWidth === clientWidth`. Verify the combobox, route, and evidence drawer remain reachable by role/name.

- [ ] **Step 7: Run focused E2E and dbt proof**

Run:

```powershell
pnpm test:e2e -- --grep "field|golden workflow|phone"
.\.venv\Scripts\dbt.exe parse --project-dir fixtures/dbt_project --profiles-dir fixtures/dbt_project
.\.venv\Scripts\dbt.exe build --project-dir fixtures/dbt_project --profiles-dir fixtures/dbt_project
```

Expected: all selected-field flows pass; dbt reports PASS for every checked-in model/test.

- [ ] **Step 8: Commit multi-field proof**

```powershell
git add apps/api/tests apps/web/tests/App.test.tsx tests/e2e/golden-flow.spec.ts fixtures/dbt_project
git commit -m "test: prove field-specific analysis end to end"
```

---

### Task 8: Update public proof, screenshots, and complete every gate

**Files:**
- Modify: `docs/architecture.md`
- Modify: `docs/demo-script.md`
- Modify: `docs/devpost-submission.md`
- Modify: `design-qa.md`
- Modify: `tests/e2e/capture-screenshots.spec.ts`
- Modify: `docs/screenshots/changesafe-desktop-replay.png`
- Modify: `docs/screenshots/changesafe-desktop-proof.png`
- Modify: `docs/screenshots/changesafe-mobile-replay.png`
- Modify: `docs/screenshots/changesafe-mobile-proof.png`
- Modify: `README.md` only where current usage/proof wording becomes stale

**Interfaces:**
- Consumes: final schema discovery, multi-field fixture, route UI, and repository gates.
- Produces: accurate public explanation and current visual proof.

- [ ] **Step 1: Update documentation without overclaiming**

Document:

- the dropdown reads the active evidence source's allowlisted schema;
- recorded mode contains a checksummed field-scoped context for all 55 supported fields;
- live mode refreshes field context at analysis time;
- exact endpoints, endpoint-only multi-hop evidence, and dataset-only relationships are visually distinct;
- a missing column mapping is an explicit limitation, not a product failure or an inferred route; and
- representative field results follow captured evidence, so equal risk scores are possible when metadata justifies them.

Update the demo script to select `cust_email`, then `order_total` or the strongest captured non-email field, and point out the changed context, route, artifact bytes, and verifier evidence.

- [ ] **Step 2: Update screenshot assertions before capture**

In `capture-screenshots.spec.ts`, wait for schema options before Analyze, assert a visible exact route or limitation, verify horizontal containment for the combobox and dependency map, and capture one desktop overview plus lower proof and equivalent mobile states. Keep `fullPage: false` and anchor the lower proof deliberately.

- [ ] **Step 3: Inspect the final feature in the in-app Browser**

Using the existing verified local replay app, inspect:

- initial schema loading and loaded dropdown;
- keyboard and pointer field selection;
- `cust_email` and one non-email run;
- exact direct route;
- endpoint-only multi-hop limitation;
- dataset-only relationship limitation;
- evidence drawer and DataHub link origin;
- recorded fallback if available;
- 1440 px, 1280 px, and 430 px layouts;
- reduced-motion rendering; and
- browser console/network errors.

Record measurements and findings in `design-qa.md`; do not mark passed until defects are fixed and rechecked.

- [ ] **Step 4: Regenerate the four checked-in screenshots**

Run the existing explicit capture flow after source changes are final:

```powershell
$env:CHANGESAFE_CAPTURE_SCREENSHOTS='1'
pnpm exec playwright test tests/e2e/capture-screenshots.spec.ts
Remove-Item Env:CHANGESAFE_CAPTURE_SCREENSHOTS
```

Open all four PNGs and confirm they depict the final dropdown/route labels, contain no cropped panels, and match the documented viewport/state.

- [ ] **Step 5: Run complete Python and deterministic-evidence gates**

Run:

```powershell
.\.venv\Scripts\python.exe -m ruff check --no-cache .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m mypy apps/api/src scripts
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts/regenerate_examples.py --check
.\.venv\Scripts\python.exe scripts/check_secrets.py
```

Expected: zero failures; only the already-understood upstream SDK warning may remain.

- [ ] **Step 6: Run complete frontend, browser, and dbt gates**

Run:

```powershell
pnpm --filter @changesafe/web lint
pnpm --filter @changesafe/web typecheck
pnpm --filter @changesafe/web test --run
pnpm --filter @changesafe/web build
pnpm test:e2e
.\.venv\Scripts\dbt.exe parse --project-dir fixtures/dbt_project --profiles-dir fixtures/dbt_project
.\.venv\Scripts\dbt.exe build --project-dir fixtures/dbt_project --profiles-dir fixtures/dbt_project
```

Expected: all pass with no console errors or overflow assertions.

- [ ] **Step 7: Run container and repository-integrity gates**

Build the production image, start it with replay-only settings and mutation flags false, verify `/healthz`, schema discovery, two field analyses, and preview approval. Then run:

```powershell
git diff --check
git status --short
```

Expected: the image serves the final UI/API; schema discovery contains 55 fields; both analyses reach approval; no secret is committed; only intentional files are modified.

- [ ] **Step 8: Perform final spec coverage self-review**

Read `docs/superpowers/specs/2026-08-09-schema-driven-field-lineage-design.md` from top to bottom and map every acceptance criterion to a passing automated test, browser observation, fixture property, or documentation statement. Fix any uncovered requirement before committing.

- [ ] **Step 9: Commit final proof and documentation**

```powershell
git add README.md docs design-qa.md tests/e2e/capture-screenshots.spec.ts
git commit -m "docs: prove schema-driven field analysis"
```

- [ ] **Step 10: Request final code review before merge**

Use `superpowers:requesting-code-review` against the complete implementation diff. Address every Critical or Important correctness, evidence, security, recovery, and accessibility finding; repeat the full affected gates after any fix.

---

## Completion evidence checklist

- [ ] The schema endpoint returns exactly 55 supported official fields in recorded mode.
- [ ] The dropdown exposes field name, native type, and nullability and accepts keyboard selection.
- [ ] A stale schema request cannot replace the current asset's options.
- [ ] `cust_email`, `order_total`, and a third operational/integrity field complete analysis with their own contexts.
- [ ] No non-email field context contains copied `cust_email` field evidence.
- [ ] Every direct field route shows source asset/field and destination asset/field.
- [ ] Multi-hop routes disclose unavailable intermediate column mappings.
- [ ] Dataset-only dependencies never receive an invented field suffix.
- [ ] Graph, drawer, and accessible list use the same route object and wording.
- [ ] Generated model/YAML/tests/notes/rollback/PR/manifest use the selected field.
- [ ] All twelve blocking checks pass for representative field/operation combinations.
- [ ] Recorded evidence is checksum-valid and deterministic.
- [ ] Live DataHub smoke proof retrieves the same schema and field-scoped context contract.
- [ ] Desktop, medium desktop, and phone layouts have no clipping or horizontal overflow.
- [ ] Full Python, TypeScript, Vitest, Playwright, dbt, Docker, secret, and diff gates pass.
