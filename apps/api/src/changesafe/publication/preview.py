"""Deterministic unified patches for credential-free approval previews."""

from __future__ import annotations

from pathlib import PurePosixPath

from changesafe.domain import ArtifactBundle
from changesafe.generation.templates import EXPECTED_GOLDEN_PATHS


class UnsafeArtifactPath(ValueError):
    """Raised when a patch path is outside the verified artifact allowlist."""


def _safe_path(path: str) -> bool:
    parsed = PurePosixPath(path)
    return (
        path in EXPECTED_GOLDEN_PATHS
        and not parsed.is_absolute()
        and ".." not in parsed.parts
        and "\\" not in path
    )


def build_unified_patch(artifacts: ArtifactBundle) -> str:
    if set(artifacts.files) != set(EXPECTED_GOLDEN_PATHS) or not all(
        _safe_path(path) for path in artifacts.files
    ):
        raise UnsafeArtifactPath("artifact bundle contains a non-allowlisted path")

    sections: list[str] = []
    for path in sorted(artifacts.files):
        artifact = artifacts.files[path]
        content = artifact.content.replace("\r\n", "\n").replace("\r", "\n")
        lines = content.splitlines()
        header = [
            f"diff --git a/{path} b/{path}",
            "new file mode 100644",
            f"index 0000000..{artifact.sha256[:7]}",
            "--- /dev/null",
            f"+++ b/{path}",
            f"@@ -0,0 +1,{len(lines)} @@",
        ]
        body = [f"+{line}" for line in lines]
        sections.append("\n".join([*header, *body]) + "\n")
    return "".join(sections)
