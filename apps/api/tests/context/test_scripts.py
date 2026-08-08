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

    assert len(seed["assets"]) == 7
    assert len(seed["downstream_from_target"]) == 4
    assert seed["tag"] == "urn:li:tag:ChangeSafe:Deprecating"
    assert seed["owners"] == [
        {
            "urn": "urn:li:corpuser:data-platform",
            "type": "TECHNICAL_OWNER",
        },
        {
            "urn": "urn:li:corpuser:customer-analytics",
            "type": "DATA_OWNER",
        },
    ]
    assert set(seed["structured_properties"]) == {
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
    assert any(aspect == "schemaMetadata" for _, aspect in identities)
    assert any(aspect == "upstreamLineage" for _, aspect in identities)
    assert any(aspect == "queryProperties" for _, aspect in identities)
    assert (
        "urn:li:corpuser:data-platform",
        "corpUserInfo",
    ) in identities
    ownership = next(
        proposal for proposal in proposals if proposal.aspectName == "ownership"
    )
    assert {
        (owner.owner, owner.type) for owner in ownership.aspect.owners
    } == {
        ("urn:li:corpuser:data-platform", "TECHNICAL_OWNER"),
        ("urn:li:corpuser:customer-analytics", "DATAOWNER"),
    }

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
