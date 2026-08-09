import subprocess
from pathlib import Path

import pytest

from changesafe.config import Mode, Settings
from changesafe.domain import ArtifactFile, ChangeOperation, RunState
from changesafe.generation.templates import generate_artifacts
from changesafe.publication.preview import UnsafeArtifactPath, build_unified_patch
from changesafe.publication.service import PublicationService

from .helpers import analyzed_run


@pytest.mark.asyncio
async def test_replay_approval_creates_truthful_downloadable_preview(
    tmp_path: Path,
) -> None:
    store, context, run = await analyzed_run(tmp_path)
    settings = Settings(
        _env_file=None,
        mode=Mode.REPLAY,
        changesafe_data_path=tmp_path / "runs.db",
    )
    service = PublicationService(
        store=store,
        settings=settings,
        context_port=context,
    )

    receipt = await service.approve(run.run_id, supplied_admin_token=None)
    persisted = await store.get(run.run_id)

    assert receipt.mode == "preview"
    assert receipt.writeback.label == "NOT WRITTEN — SNAPSHOT MODE"
    assert receipt.patch is not None
    assert "--- /dev/null\n+++ b/PR_BODY.md\n" in receipt.patch
    assert "diff --git a/models/marts/order_details.sql" in receipt.patch
    assert "\r" not in receipt.patch
    assert persisted is not None
    assert persisted.state is RunState.COMPLETED
    assert persisted.publication == receipt


@pytest.mark.asyncio
async def test_duplicate_preview_approval_reuses_exact_receipt(tmp_path: Path) -> None:
    store, context, run = await analyzed_run(tmp_path)
    service = PublicationService(
        store=store,
        settings=Settings(
            _env_file=None,
            mode=Mode.REPLAY,
            changesafe_data_path=tmp_path / "runs.db",
        ),
        context_port=context,
    )

    first = await service.approve(run.run_id, supplied_admin_token=None)
    second = await service.approve(run.run_id, supplied_admin_token=None)

    assert second == first


@pytest.mark.asyncio
async def test_patch_confines_paths_and_uses_dev_null(tmp_path: Path) -> None:
    _, _, run = await analyzed_run(tmp_path)
    assert run.analysis is not None
    patch = build_unified_patch(run.analysis.artifacts)

    assert patch.count("--- /dev/null\n") == 7
    assert "../" not in patch
    checked = subprocess.run(
        ["git", "apply", "--check", "-"],
        cwd=tmp_path,
        input=patch,
        text=True,
        capture_output=True,
        check=False,
    )
    assert checked.returncode == 0, checked.stderr


@pytest.mark.asyncio
async def test_patch_rejects_path_outside_allowlist(tmp_path: Path) -> None:
    _, _, run = await analyzed_run(tmp_path)
    assert run.analysis is not None
    artifacts = run.analysis.artifacts
    unsafe = artifacts.model_copy(
        update={
            "files": {
                **artifacts.files,
                "../escape.sql": ArtifactFile(
                    path="../escape.sql", content="select 1\n"
                ),
            }
        }
    )

    with pytest.raises(UnsafeArtifactPath):
        build_unified_patch(unsafe)


@pytest.mark.asyncio
async def test_patch_accepts_verified_operation_specific_paths(tmp_path: Path) -> None:
    _, _, run = await analyzed_run(tmp_path)
    assert run.analysis is not None
    change = run.request.model_copy(
        update={
            "operation": ChangeOperation.REMOVE,
            "new_field": None,
            "new_type": None,
        }
    )
    artifacts = generate_artifacts(
        change, run.analysis.context, run.analysis.risk
    )

    patch = build_unified_patch(artifacts)

    assert "tests/assert_cust_email_retained.sql" in patch


@pytest.mark.asyncio
async def test_live_read_only_run_is_not_mislabeled_as_snapshot(tmp_path: Path) -> None:
    from .test_idempotency import FlakyWritebackContext

    context = FlakyWritebackContext()
    store, _, run = await analyzed_run(tmp_path, context_port=context)
    service = PublicationService(
        store=store,
        settings=Settings(
            _env_file=None,
            mode=Mode.LIVE,
            changesafe_data_path=tmp_path / "runs.db",
            datahub_gms_url="https://datahub.example.test",
            datahub_gms_token="private-token",
        ),
        context_port=context,
    )

    receipt = await service.approve(run.run_id, supplied_admin_token=None)

    assert receipt.mode == "preview"
    assert receipt.writeback.label == "NOT WRITTEN — PUBLICATION DISABLED"
