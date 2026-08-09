import hashlib
import json
from pathlib import Path

from scripts.capture_snapshot import write_snapshot
from scripts.check_secrets import SIGNATURES
from scripts.seed_datahub import apply_seed, build_seed_proposals, build_seed_spec


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

    assert seed["base_datapack"] == "showcase-ecommerce"
    assert seed["load_command"] == "datahub datapack load showcase-ecommerce"
    assert seed["field"] == "cust_email"
    assert seed["required_official_context"]["governance_tags"] == [
        "urn:li:tag:b2fd91.PII_Data"
    ]
    assert seed["overlay"]["tag"] == "urn:li:tag:ChangeSafe:Deprecating"
    assert set(seed["overlay"]["structured_properties"]) == {
        "urn:li:structuredProperty:changesafe.riskLevel",
        "urn:li:structuredProperty:changesafe.changeStatus",
        "urn:li:structuredProperty:changesafe.lastRunId",
    }


def test_seed_builds_stable_idempotent_metadata_upserts() -> None:
    proposals = build_seed_proposals()
    identities = [
        (proposal.entityUrn, proposal.aspectName) for proposal in proposals
    ]

    assert len(identities) == len(set(identities))
    assert (
        "urn:li:structuredProperty:changesafe.riskLevel",
        "propertyDefinition",
    ) in identities
    assert any(aspect == "queryProperties" for _, aspect in identities)
    assert not any(aspect == "schemaMetadata" for _, aspect in identities)
    assert not any(aspect == "upstreamLineage" for _, aspect in identities)
    assert not any(aspect == "ownership" for _, aspect in identities)

    class FakeEmitter:
        def __init__(self) -> None:
            self.emitted = []

        def emit(self, proposal) -> None:
            self.emitted.append((proposal.entityUrn, proposal.aspectName))

    emitter = FakeEmitter()
    apply_seed(emitter, proposals)
    apply_seed(emitter, proposals)

    assert emitter.emitted[: len(identities)] == identities
    assert emitter.emitted[len(identities) :] == identities


def test_secret_signatures_detect_fine_grained_github_tokens() -> None:
    token = b"github_" + b"pat_" + (b"A" * 40)

    assert SIGNATURES["GitHub fine-grained token"].search(token)
