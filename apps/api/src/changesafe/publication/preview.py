"""Deterministic unified patches for credential-free approval previews."""

from __future__ import annotations

import re
from pathlib import PurePosixPath

from changesafe.domain import ArtifactBundle


class UnsafeArtifactPath(ValueError):
    """Raised when a patch path is outside the verified artifact allowlist."""


PATH_PATTERNS = {
    "model_sql": re.compile(r"^models/marts/[a-z_][a-z0-9_]*\.sql$"),
    "model_yaml": re.compile(r"^models/marts/[a-z_][a-z0-9_]*\.yml$"),
    "test": re.compile(r"^tests/assert_[a-z_][a-z0-9_]*\.sql$"),
    "migration": re.compile(
        r"^migrations/\d{4}-\d{2}-\d{2}-[a-z0-9-]+"
        r"-(?:rename|remove|type_change)\.md$"
    ),
    "rollback": re.compile(r"^ROLLBACK\.md$"),
    "pr": re.compile(r"^PR_BODY\.md$"),
    "manifest": re.compile(r"^changesafe-manifest\.json$"),
}


def _path_kind(path: str) -> str | None:
    parsed = PurePosixPath(path)
    if parsed.is_absolute() or ".." in parsed.parts or "\\" in path:
        return None
    return next(
        (kind for kind, pattern in PATH_PATTERNS.items() if pattern.fullmatch(path)),
        None,
    )


def build_unified_patch(artifacts: ArtifactBundle) -> str:
    kinds = [_path_kind(path) for path in artifacts.files]
    if len(artifacts.files) != len(PATH_PATTERNS) or set(kinds) != set(PATH_PATTERNS):
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
