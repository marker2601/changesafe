"""Fail CI when tracked source contains a credential-shaped value."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

SIGNATURES = {
    "OpenAI API key": re.compile(rb"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b"),
    "GitHub token": re.compile(rb"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    "Slack token": re.compile(rb"\bxox[baprs]-[A-Za-z0-9-]{20,}\b"),
    "private key": re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
}

SKIP_SUFFIXES = {
    ".gif",
    ".ico",
    ".jpeg",
    ".jpg",
    ".lock",
    ".pdf",
    ".png",
    ".webm",
    ".zip",
}


def tracked_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        check=True,
        capture_output=True,
    )
    return [Path(raw.decode()) for raw in result.stdout.split(b"\0") if raw]


def main() -> int:
    findings: list[str] = []
    for path in tracked_files():
        if path.suffix.lower() in SKIP_SUFFIXES or not path.is_file():
            continue
        content = path.read_bytes()
        for label, signature in SIGNATURES.items():
            if signature.search(content):
                findings.append(f"{path}: credential-shaped {label}")

    if findings:
        print("Secret scan failed:")
        print("\n".join(f"- {finding}" for finding in findings))
        return 1

    print("Secret scan passed: no credential signatures in tracked text files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
