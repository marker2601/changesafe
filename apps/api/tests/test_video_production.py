from pathlib import Path

from scripts.video.storyboard import (
    SCENES,
    TOTAL_VISUAL_MS,
    default_output_dir,
    narration_word_count,
    validate_storyboard,
)


def test_storyboard_is_under_three_minutes_and_complete() -> None:
    assert [scene.scene_id for scene in SCENES] == [
        "problem",
        "truth-boundary",
        "schema-request",
        "lineage",
        "impact",
        "artifacts",
        "multi-field",
        "approval",
        "closing",
    ]
    assert 145_000 <= TOTAL_VISUAL_MS <= 175_000
    assert 300 <= narration_word_count() <= 340
    assert validate_storyboard() == []


def test_storyboard_contains_binding_competition_proof() -> None:
    all_text = " ".join(scene.narration for scene in SCENES)
    assert "DataHub" in all_text
    assert "fifty-five" in all_text
    assert "seven reviewable files" in all_text
    assert "Twelve blocking checks" in all_text
    assert "production rows were not queried" in all_text
    assert "non-mutating receipt" in all_text


def test_storyboard_excludes_private_or_false_claims() -> None:
    all_text = " ".join(scene.narration for scene in SCENES).casefold()
    for forbidden in (
        "judge-prepared",
        "production rows passed",
        "live warehouse passed",
        "temporary tunnel",
        "api token",
        "private key",
    ):
        assert forbidden not in all_text


def test_default_output_is_outside_the_checkout() -> None:
    output = default_output_dir()
    assert output == Path.home() / "Videos" / "ChangeSafe Submission"
    assert not output.is_relative_to(Path.cwd())
