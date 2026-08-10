import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from changesafe.context.replay import ReplayDataHubContext
from changesafe.demo import DEMO_TARGET_URN
from changesafe.domain import ChangeOperation, ChangeRequest, SchemaField
from changesafe.generation.service import ArtifactGenerationService
from changesafe.risk import score_change
from changesafe.sql_types import canonical_sql_type
from changesafe.verification import verify_artifacts

SNAPSHOT = Path("fixtures/datahub/golden-context.json")
RECORDED_FIELDS = [
    SchemaField.model_validate(item)
    for item in json.loads(SNAPSHOT.read_text(encoding="utf-8"))["schema_fields"]
]


def alternate_type(current: str) -> str:
    base, _ = canonical_sql_type(current)
    return "NUMBER(38,0)" if base == "VARCHAR" else "VARCHAR(320)"


def valid_change_for(
    field: SchemaField, operation: ChangeOperation
) -> ChangeRequest:
    common = {
        "asset_urn": DEMO_TARGET_URN,
        "operation": operation,
        "field": field.name,
        "source_commit": f"matrix-{field.name}-{operation.value}",
        "requested_by": "competition-matrix",
    }
    if operation is ChangeOperation.RENAME:
        new_field = f"changesafe_{field.name}"
        recorded_names = {item.name.casefold() for item in RECORDED_FIELDS}
        assert new_field.casefold() not in recorded_names
        return ChangeRequest(**common, new_field=new_field)
    if operation is ChangeOperation.TYPE_CHANGE:
        return ChangeRequest(
            **common,
            old_type=field.data_type,
            new_type=alternate_type(field.data_type),
        )
    return ChangeRequest(**common)


@pytest.mark.parametrize("field", RECORDED_FIELDS, ids=lambda field: field.name)
@pytest.mark.parametrize("operation", list(ChangeOperation))
@pytest.mark.asyncio
async def test_every_recorded_field_operation_is_deterministic(
    field: SchemaField, operation: ChangeOperation
) -> None:
    change = valid_change_for(field, operation)
    context = await ReplayDataHubContext.from_default().load(change)
    risk = score_change(change, context)
    generator = ArtifactGenerationService()
    first = await generator.generate(change, context, risk)
    second = await generator.generate(change, context, risk)
    validation = verify_artifacts(first, change, context)
    manifest = json.loads(first.files["changesafe-manifest.json"].content)

    assert first == second
    assert validation.passed
    assert manifest["change"] == change.model_dump(mode="json")
    assert manifest["context"]["field"] == field.name
    assert manifest["context"]["field_type"] == field.data_type


@pytest.mark.parametrize(
    ("identifier", "valid"),
    [
        ("", False),
        ("a", True),
        ("a" * 128, True),
        ("a" * 129, False),
        ("1field", False),
        ("-field", False),
        ("field name", False),
        ('field"name', False),
        ("café", False),
        ("field\nname", False),
        ("_field", True),
    ],
)
def test_change_request_identifier_boundaries(
    identifier: str, valid: bool
) -> None:
    values = {
        "asset_urn": DEMO_TARGET_URN,
        "operation": ChangeOperation.REMOVE,
        "field": identifier,
        "source_commit": "request-boundary",
        "requested_by": "competition-matrix",
    }

    if valid:
        assert ChangeRequest.model_validate(values).field == identifier
    else:
        with pytest.raises(ValidationError):
            ChangeRequest.model_validate(values)


@pytest.mark.parametrize(
    ("operation", "irrelevant"),
    [
        (ChangeOperation.RENAME, {"old_type": "TEXT"}),
        (ChangeOperation.RENAME, {"new_type": "NUMBER"}),
        (ChangeOperation.REMOVE, {"new_field": "preferred_email"}),
        (ChangeOperation.REMOVE, {"old_type": "TEXT"}),
        (ChangeOperation.REMOVE, {"new_type": "NUMBER"}),
        (ChangeOperation.TYPE_CHANGE, {"new_field": "preferred_email"}),
    ],
)
def test_change_request_rejects_every_irrelevant_operation_field(
    operation: ChangeOperation, irrelevant: dict[str, str]
) -> None:
    values: dict[str, object] = {
        "asset_urn": DEMO_TARGET_URN,
        "operation": operation,
        "field": "cust_email",
        "source_commit": "request-boundary",
        "requested_by": "competition-matrix",
    }
    if operation is ChangeOperation.RENAME:
        values["new_field"] = "preferred_email"
    elif operation is ChangeOperation.TYPE_CHANGE:
        values.update({"old_type": "TEXT", "new_type": "NUMBER"})
    values.update(irrelevant)

    with pytest.raises(ValidationError, match="only valid"):
        ChangeRequest.model_validate(values)


@pytest.mark.parametrize(
    "missing",
    [
        "asset_urn",
        "operation",
        "field",
        "new_field",
        "source_commit",
        "requested_by",
    ],
)
def test_change_request_rejects_each_missing_required_rename_field(
    missing: str,
) -> None:
    values = {
        "asset_urn": DEMO_TARGET_URN,
        "operation": ChangeOperation.RENAME,
        "field": "cust_email",
        "new_field": "preferred_email",
        "source_commit": "request-boundary",
        "requested_by": "competition-matrix",
    }
    values.pop(missing)

    with pytest.raises(ValidationError):
        ChangeRequest.model_validate(values)


def test_change_request_rejects_extra_properties() -> None:
    with pytest.raises(ValidationError, match="extra_forbidden"):
        ChangeRequest.model_validate(
            {
                "asset_urn": DEMO_TARGET_URN,
                "operation": ChangeOperation.REMOVE,
                "field": "cust_email",
                "source_commit": "request-boundary",
                "requested_by": "competition-matrix",
                "connector_dsn": "must-not-cross-the-boundary",
            }
        )


@pytest.mark.parametrize(
    "new_field", ["cust_email", "CUST_EMAIL", "CUSTOMER_ID"]
)
@pytest.mark.asyncio
async def test_rename_equality_or_case_insensitive_collision_never_generates(
    new_field: str,
) -> None:
    values = {
        "asset_urn": DEMO_TARGET_URN,
        "operation": ChangeOperation.RENAME,
        "field": "cust_email",
        "new_field": new_field,
        "source_commit": "rename-collision-boundary",
        "requested_by": "competition-matrix",
    }
    with pytest.raises((ValidationError, ValueError)):
        change = ChangeRequest.model_validate(values)
        context = await ReplayDataHubContext.from_default().load(change)
        await ArtifactGenerationService().generate(
            change, context, score_change(change, context)
        )
