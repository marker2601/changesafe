import hashlib
import json
from pathlib import Path

from scripts.capture_snapshot import write_snapshot
from scripts.seed_datahub import build_seed_spec


def test_snapshot_capture_writes_canonical_redacted_bytes(tmp_path: Path) -> None:
    snapshot = tmp_path / "context.json"
    checksum = tmp_path / "context.sha256"
    write_snapshot(
        {
            "z": 2,
            "authorization": "Bearer private",
            "a": {"token": "secret", "urn": "urn:li:dataset:demo"},
        },
        snapshot,
        checksum,
    )

    raw = snapshot.read_bytes()
    parsed = json.loads(raw)

    assert parsed["authorization"] == "[REDACTED]"
    assert parsed["a"]["token"] == "[REDACTED]"
    assert raw.startswith(b'{\n  "a"')
    assert (
        checksum.read_text(encoding="ascii").split()[0]
        == hashlib.sha256(raw).hexdigest()
    )


def test_seed_spec_contains_required_graph_and_governance_definitions() -> None:
    seed = build_seed_spec()

    assert len(seed["assets"]) == 7
    assert len(seed["downstream_from_target"]) == 4
    assert seed["tag"] == "urn:li:tag:ChangeSafe:Deprecating"
    assert set(seed["structured_properties"]) == {
        "urn:li:structuredProperty:changesafe.riskLevel",
        "urn:li:structuredProperty:changesafe.changeStatus",
        "urn:li:structuredProperty:changesafe.lastRunId",
    }
