"""Regenerate the checked-in golden migration from reviewed templates."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from changesafe.context.replay import ReplayDataHubContext
from changesafe.domain import ChangeRequest
from changesafe.generation.templates import generate_artifacts
from changesafe.risk import score_change

ROOT = Path(__file__).resolve().parents[1]
def _sync_file(path: Path, content: str, *, check: bool) -> bool:
    if check:
        return not path.is_file() or path.read_text(encoding="utf-8") != content
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")
    return False


async def regenerate(*, check: bool = False) -> None:
    change = ChangeRequest.model_validate_json(
        (ROOT / "examples" / "unsafe-change" / "change.json").read_text(
            encoding="utf-8"
        )
    )
    context = await ReplayDataHubContext.from_default().load(change)
    bundle = generate_artifacts(change, context, score_change(change, context))
    dbt_fixture_paths = tuple(
        path
        for path in bundle.files
        if path.startswith("models/marts/") or path.startswith("tests/")
    )
    destination = ROOT / "examples" / "generated-safe-change"
    mismatches: list[str] = []
    if check:
        existing = {
            path.relative_to(destination).as_posix()
            for path in destination.rglob("*")
            if path.is_file()
        }
        mismatches.extend(sorted(existing - set(bundle.files)))
    for artifact in bundle.files.values():
        path = destination / artifact.path
        if _sync_file(path, artifact.content, check=check):
            mismatches.append(artifact.path)
    fixture = ROOT / "fixtures" / "dbt_project"
    for artifact_path in dbt_fixture_paths:
        artifact = bundle.files[artifact_path]
        if _sync_file(fixture / artifact_path, artifact.content, check=check):
            mismatches.append(f"fixtures/dbt_project/{artifact_path}")
    if mismatches:
        raise SystemExit(
            "Checked-in examples differ from deterministic generation: "
            + ", ".join(sorted(mismatches))
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Regenerate or verify the checked-in golden migration."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail when checked-in files differ instead of writing them.",
    )
    args = parser.parse_args()
    asyncio.run(regenerate(check=args.check))


if __name__ == "__main__":
    main()
