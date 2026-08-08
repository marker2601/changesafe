"""Sanitize and persist a canonical DataHub context snapshot."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from changesafe.redaction import redact


def canonical_bytes(payload: Any) -> bytes:
    return (
        json.dumps(redact(payload), indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def write_snapshot(payload: Any, snapshot: Path, checksum: Path) -> str:
    raw = canonical_bytes(payload)
    digest = hashlib.sha256(raw).hexdigest()
    snapshot.parent.mkdir(parents=True, exist_ok=True)
    checksum.parent.mkdir(parents=True, exist_ok=True)
    snapshot.write_bytes(raw)
    checksum.write_text(f"{digest}  {snapshot.name}\n", encoding="ascii")
    return digest


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sanitize a captured DataHub context JSON document."
    )
    parser.add_argument("input", type=Path)
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("checksum", type=Path)
    args = parser.parse_args()
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    digest = write_snapshot(payload, args.snapshot, args.checksum)
    print(f"Captured {args.snapshot} ({digest})")


if __name__ == "__main__":
    main()
