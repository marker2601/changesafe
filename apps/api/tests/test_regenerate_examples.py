import os
import subprocess
import sys
from pathlib import Path


def test_regenerate_examples_prefers_the_checkout_source_over_pythonpath(
    tmp_path: Path,
) -> None:
    repo_root = Path(__file__).resolve().parents[3]
    foreign_package = tmp_path / "foreign-package" / "changesafe"
    foreign_package.mkdir(parents=True)
    (foreign_package / "__init__.py").write_text(
        'raise RuntimeError("foreign editable checkout imported")\n',
        encoding="utf-8",
    )
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(foreign_package.parent)

    result = subprocess.run(
        [sys.executable, "scripts/regenerate_examples.py", "--check"],
        cwd=repo_root,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
