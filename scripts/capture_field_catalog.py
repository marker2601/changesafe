"""Capture a checksummed field-scoped catalog from a live DataHub adapter."""

# ruff: noqa: E402 -- direct execution must prefer this worktree over shared venvs.

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "apps" / "api" / "src"), str(ROOT)]

from changesafe.config import Mode, Settings
from changesafe.context.base import ContextLoadError, DataHubContextPort
from changesafe.context.factory import build_context_port
from changesafe.context.replay import RecordedDataHubCatalog, RecordedFieldContext
from changesafe.domain import (
    ChangeOperation,
    ChangeRequest,
    ContextBundle,
    ContextMode,
)
from scripts.capture_snapshot import write_snapshot_atomic


async def build_recorded_catalog(
    port: DataHubContextPort, target_urn: str
) -> RecordedDataHubCatalog:
    schema = await port.discover_schema(target_urn)
    contexts: dict[str, RecordedFieldContext] = {}
    shared: ContextBundle | None = None
    total = len(schema.schema_fields)
    for index, schema_field in enumerate(schema.schema_fields, start=1):
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
            query_count=context.query_count,
            evidence=context.evidence,
            tool_evidence=context.tool_evidence,
        )
        print(f"Captured field {index}/{total}")
    if shared is None:
        raise ContextLoadError("DataHub schema did not contain supported fields")
    return RecordedDataHubCatalog(
        snapshot_version=3,
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


async def capture_recorded_catalog(
    port: DataHubContextPort,
    target_urn: str,
    snapshot: Path,
    checksum: Path,
) -> str:
    catalog = await build_recorded_catalog(port, target_urn)
    return write_recorded_catalog(catalog, snapshot, checksum)


def write_recorded_catalog(
    catalog: RecordedDataHubCatalog, snapshot: Path, checksum: Path
) -> str:
    payload = catalog.model_dump(
        mode="json", exclude={"provenance": {"snapshot_hash"}}
    )
    return write_snapshot_atomic(payload, snapshot, checksum)


async def capture_from_settings(
    target_urn: str, snapshot: Path, checksum: Path
) -> int:
    try:
        settings = Settings()
        if settings.mode is not Mode.LIVE or not settings.live_context_enabled:
            print(
                "Capture requires live DataHub credentials; snapshot was not changed.",
                file=sys.stderr,
            )
            return 2

        port = build_context_port(settings)
        try:
            catalog = await build_recorded_catalog(port, target_urn)
        finally:
            close = getattr(port, "close", None)
            if callable(close):
                close()
        digest = write_recorded_catalog(catalog, snapshot, checksum)
    except Exception:
        print("Capture failed; snapshot was not changed.", file=sys.stderr)
        return 1

    print(f"Captured catalog ({digest})")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Capture a field-scoped catalog from live DataHub."
    )
    parser.add_argument("--target-urn", required=True)
    parser.add_argument("--snapshot", required=True, type=Path)
    parser.add_argument("--checksum", required=True, type=Path)
    args = parser.parse_args(argv)
    return asyncio.run(
        capture_from_settings(args.target_urn, args.snapshot, args.checksum)
    )


if __name__ == "__main__":
    raise SystemExit(main())
