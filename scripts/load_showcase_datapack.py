"""Guarded loader for DataHub's official ``showcase-ecommerce`` data pack.

The command is deliberately a no-I/O preview unless ``--apply`` is supplied.
Apply mode reuses the installed DataHub CLI's registry, verified download,
schema compatibility filter, referential-integrity check, time shifting, and
load-record format. It replaces the CLI's asynchronous sink with ordered
RESTLI synchronous writes so a completed record can only follow full success.
"""

from __future__ import annotations

import argparse
import inspect
import sys
from collections.abc import Callable, Sequence
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

OFFICIAL_PACK_NAME = "showcase-ecommerce"


class RuntimeCompatibilityError(RuntimeError):
    """Raised when the installed DataHub CLI lacks the guarded loader hooks."""


@dataclass(frozen=True)
class LoadOptions:
    apply: bool = False
    no_cache: bool = False
    no_time_shift: bool = False
    as_of: datetime | None = None


@dataclass(frozen=True)
class LoadResult:
    pack_name: str
    applied: bool
    file_count: int
    run_id: str | None = None


@dataclass(frozen=True)
class OfficialRuntime:
    """Narrow adapter around the installed DataHub datapack implementation."""

    get_pack: Callable[..., Any]
    check_trust: Callable[..., Any]
    check_version_compatibility: Callable[..., Any]
    download_pack: Callable[..., Sequence[Any]]
    load_client_config: Callable[..., Any]
    apply_schema_filter: Callable[..., Path]
    check_referential_integrity: Callable[..., Any]
    time_shift_file: Callable[..., Path]
    generate_run_id: Callable[..., str]
    pipeline_create: Callable[..., Any]
    save_load_record: Callable[..., Any]


def _require_parameters(
    function: Callable[..., Any],
    label: str,
    required: set[str],
) -> None:
    try:
        available = set(inspect.signature(function).parameters)
    except (TypeError, ValueError) as exc:
        raise RuntimeCompatibilityError(
            f"Cannot verify the installed DataHub {label} interface."
        ) from exc

    missing = required - available
    if missing:
        names = ", ".join(sorted(missing))
        raise RuntimeCompatibilityError(
            f"The installed DataHub {label} interface is incompatible "
            f"(missing: {names})."
        )


def load_official_runtime() -> OfficialRuntime:
    """Load and validate the exact official helpers this guard delegates to."""
    try:
        from datahub.cli.datapack import loader, registry
        from datahub.cli.datapack.time_shift import time_shift_file
        from datahub.ingestion.run.pipeline import Pipeline
    except ImportError as exc:
        raise RuntimeCompatibilityError(
            "The DataHub CLI datapack runtime is not installed. Install the "
            "project's live dependencies before using --apply."
        ) from exc

    private_helpers = {
        "schema filter": (
            getattr(loader, "_apply_schema_filter", None),
            {"pack_path", "client_config"},
        ),
        "referential-integrity check": (
            getattr(loader, "_check_referential_integrity", None),
            {"pack_path", "client_config"},
        ),
        "run-id generator": (
            getattr(loader, "_generate_run_id", None),
            {"pack_name"},
        ),
    }
    for label, (helper, parameters) in private_helpers.items():
        if not callable(helper):
            raise RuntimeCompatibilityError(
                f"The installed DataHub {label} helper is unavailable."
            )
        _require_parameters(helper, label, parameters)

    public_helpers = {
        "registry": (registry.get_pack, {"name", "no_cache"}),
        "download": (loader.download_pack, {"pack", "no_cache"}),
        "trust check": (loader.check_trust, {"pack"}),
        "version check": (loader.check_version_compatibility, {"pack"}),
        "time shift": (
            time_shift_file,
            {"input_path", "reference_timestamp", "target_timestamp"},
        ),
        "load record": (loader.save_load_record, {"pack", "run_id"}),
    }
    for label, (helper, parameters) in public_helpers.items():
        _require_parameters(helper, label, parameters)

    return OfficialRuntime(
        get_pack=registry.get_pack,
        check_trust=loader.check_trust,
        check_version_compatibility=loader.check_version_compatibility,
        download_pack=loader.download_pack,
        load_client_config=loader.load_client_config,
        apply_schema_filter=private_helpers["schema filter"][0],
        check_referential_integrity=private_helpers["referential-integrity check"][0],
        time_shift_file=time_shift_file,
        generate_run_id=private_helpers["run-id generator"][0],
        pipeline_create=Pipeline.create,
        save_load_record=loader.save_load_record,
    )


def _client_value(client_config: Any, name: str) -> Any:
    value = getattr(client_config, name, None)
    if value is not None:
        return value
    if hasattr(client_config, "model_dump"):
        return client_config.model_dump(mode="json", exclude_none=True).get(name)
    return None


def _synchronous_sink_config(client_config: Any) -> dict[str, Any]:
    server = _client_value(client_config, "server")
    if not server:
        raise RuntimeCompatibilityError(
            "The DataHub client configuration does not contain a server URL."
        )

    config: dict[str, Any] = {
        "server": str(server),
        "endpoint": "restli",
        "mode": "sync",
    }
    token = _client_value(client_config, "token")
    if token:
        config["token"] = token
    return config


def _remove_generated_files(paths: set[Path]) -> None:
    # DataHub's helpers close NamedTemporaryFile before returning. A best-effort
    # cleanup avoids turning a transient Windows file lock into a false load
    # failure after the pipeline has already reported its real status.
    for path in paths:
        with suppress(OSError):
            path.unlink(missing_ok=True)


def load_showcase_datapack(
    options: LoadOptions,
    *,
    runtime: OfficialRuntime | None = None,
) -> LoadResult:
    """Preview or synchronously apply DataHub's official showcase datapack."""
    if not options.apply:
        print(f"Official DataHub data pack: {OFFICIAL_PACK_NAME}")
        print("PREVIEW ONLY — no network or cache access; no DataHub writes.")
        print("Run again with --apply to resolve and load the verified pack.")
        return LoadResult(
            pack_name=OFFICIAL_PACK_NAME,
            applied=False,
            file_count=0,
        )

    runtime = runtime or load_official_runtime()
    pack = runtime.get_pack(OFFICIAL_PACK_NAME, no_cache=options.no_cache)
    runtime.check_trust(pack)
    runtime.check_version_compatibility(pack)
    entries = list(runtime.download_pack(pack, no_cache=options.no_cache))
    if not entries:
        raise RuntimeError("The official DataHub datapack contained no files.")

    client_config = runtime.load_client_config()
    sink_config = _synchronous_sink_config(client_config)
    run_id = runtime.generate_run_id(pack.name)

    for index, entry in enumerate(entries):
        original_path = Path(entry.path)
        generated_paths: set[Path] = set()
        effective_path = original_path
        try:
            filtered_path = Path(
                runtime.apply_schema_filter(effective_path, client_config=client_config)
            )
            if filtered_path != original_path:
                generated_paths.add(filtered_path)
            effective_path = filtered_path

            if index == len(entries) - 1:
                runtime.check_referential_integrity(
                    effective_path, client_config=client_config
                )

            if not options.no_time_shift and pack.reference_timestamp:
                target_timestamp = (
                    int(options.as_of.timestamp() * 1000) if options.as_of else None
                )
                shifted_path = Path(
                    runtime.time_shift_file(
                        input_path=effective_path,
                        reference_timestamp=pack.reference_timestamp,
                        target_timestamp=target_timestamp,
                    )
                )
                if shifted_path != original_path:
                    generated_paths.add(shifted_path)
                effective_path = shifted_path

            print(
                f"Loading ordered part {index + 1}/{len(entries)}: {original_path.name}"
            )
            pipeline = runtime.pipeline_create(
                {
                    "run_id": run_id,
                    "source": {
                        "type": "file",
                        "config": {"path": str(effective_path)},
                    },
                    "sink": {
                        "type": "datahub-rest",
                        "config": dict(sink_config),
                    },
                }
            )
            pipeline.run()
            pipeline.raise_from_status()
        finally:
            _remove_generated_files(generated_paths)

    runtime.save_load_record(pack, run_id)
    print(
        f"Loaded {len(entries)} ordered parts synchronously. "
        "The completed load record was saved."
    )
    return LoadResult(
        pack_name=pack.name,
        applied=True,
        file_count=len(entries),
        run_id=run_id,
    )


def _parse_as_of(raw: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "--as-of must be an ISO-8601 timestamp"
        ) from exc
    if parsed.tzinfo is None:
        raise argparse.ArgumentTypeError(
            "--as-of must include a timezone, for example 2026-08-09T12:00:00Z"
        )
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Preview or safely load DataHub's official showcase-ecommerce "
            "datapack in strict synchronous order."
        )
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="perform the DataHub writes (default is a no-I/O preview)",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="make the official registry and downloader bypass their cache",
    )
    parser.add_argument(
        "--no-time-shift",
        action="store_true",
        help="preserve timestamps from the official datapack",
    )
    parser.add_argument(
        "--as-of",
        type=_parse_as_of,
        help="time-shift the datapack to this timezone-aware ISO timestamp",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        load_showcase_datapack(
            LoadOptions(
                apply=args.apply,
                no_cache=args.no_cache,
                no_time_shift=args.no_time_shift,
                as_of=args.as_of,
            )
        )
    except RuntimeCompatibilityError as exc:
        print(f"Cannot run guarded loader: {exc}", file=sys.stderr)
        print("No completed load record was written.", file=sys.stderr)
        return 2
    except Exception as exc:
        # Deliberately omit exception text: third-party configuration errors can
        # embed authentication material. The exception type is enough to route
        # operators to logs without echoing a token into a demo terminal.
        print(
            f"Load failed safely ({type(exc).__name__}). "
            "No completed load record was written.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
