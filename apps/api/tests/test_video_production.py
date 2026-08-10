from itertools import pairwise
from pathlib import Path
from subprocess import CompletedProcess

import pytest
from scripts.video.narration import (
    DEFAULT_ELEVENLABS_VOICE_ID,
    CaptionCue,
    SceneMedia,
    VideoProductionError,
    build_edge_tts_command,
    build_elevenlabs_request,
    build_timing_manifest,
    load_private_video_env,
    parse_available_voices,
    parse_elevenlabs_response,
    parse_vtt,
    resolve_elevenlabs_voice_id,
    select_voice,
    split_caption_cue,
)
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


def test_voice_selection_prefers_ava_then_jenny() -> None:
    assert (
        select_voice(
            {"en-US-AvaMultilingualNeural", "en-US-JennyNeural"}
        )
        == "en-US-AvaMultilingualNeural"
    )
    assert select_voice({"en-US-JennyNeural"}) == "en-US-JennyNeural"
    with pytest.raises(VideoProductionError, match="approved generated voice"):
        select_voice({"en-US-DavidNeural"})


def test_available_voice_parser_uses_only_voice_names() -> None:
    output = (
        "Name Gender Locale\n"
        "en-US-AvaMultilingualNeural Female en-US\n"
        "en-US-JennyNeural Female en-US\n"
    )
    assert parse_available_voices(output) == {
        "en-US-AvaMultilingualNeural",
        "en-US-JennyNeural",
    }


def test_edge_tts_command_uses_argument_array_and_pinned_options(
    tmp_path: Path,
) -> None:
    command = build_edge_tts_command(
        text="Safe narration",
        voice="en-US-AvaMultilingualNeural",
        media_path=tmp_path / "scene.mp3",
        subtitles_path=tmp_path / "scene.vtt",
    )
    assert command[1:3] == ["-m", "edge_tts"]
    assert "--voice" in command
    assert "en-US-AvaMultilingualNeural" in command
    assert "--rate=-2%" in command
    assert "--write-media" in command
    assert "--write-subtitles" in command
    assert "Safe narration" in command


def test_private_video_env_ignores_comments_and_blank_values(
    tmp_path: Path,
) -> None:
    env_path = tmp_path / "video.env"
    env_path.write_text(
        "# local only\n"
        "ELEVENLABS_API_KEY=secret-value\n"
        "ELEVENLABS_VOICE_ID=\n"
        "IGNORED_LINE\n",
        encoding="utf-8",
    )
    assert load_private_video_env(env_path) == {
        "ELEVENLABS_API_KEY": "secret-value"
    }


def test_elevenlabs_key_id_is_not_mistaken_for_voice_id() -> None:
    assert (
        resolve_elevenlabs_voice_id("a" * 64)
        == DEFAULT_ELEVENLABS_VOICE_ID
    )
    assert (
        resolve_elevenlabs_voice_id("JBFqnCBsd6RMkjVDRZzb")
        == "JBFqnCBsd6RMkjVDRZzb"
    )


def test_elevenlabs_request_contains_key_only_in_header() -> None:
    api_key = "private-elevenlabs-key"
    request = build_elevenlabs_request(
        text="ChangeSafe checks the evidence.",
        api_key=api_key,
        voice_id="JBFqnCBsd6RMkjVDRZzb",
    )
    assert request.full_url.endswith(
        "/JBFqnCBsd6RMkjVDRZzb/with-timestamps"
        "?output_format=mp3_44100_128"
    )
    assert request.get_header("Xi-api-key") == api_key
    assert api_key.encode() not in request.data
    assert b"eleven_multilingual_v2" in request.data


def test_elevenlabs_response_yields_audio_and_synchronized_caption() -> None:
    payload = (
        b'{"audio_base64":"c2FmZS1hdWRpbw==","alignment":{'
        b'"characters":["S","a","f","e"],'
        b'"character_start_times_seconds":[0.0,0.1,0.2,0.3],'
        b'"character_end_times_seconds":[0.1,0.2,0.3,0.4]}}'
    )
    audio, cues = parse_elevenlabs_response(payload, "Safe")
    assert audio == b"safe-audio"
    assert cues == (CaptionCue(0, 400, "Safe"),)


def test_vtt_parser_returns_millisecond_cues() -> None:
    cues = parse_vtt(
        "WEBVTT\n\n"
        "00:00:00.500 --> 00:00:02.000\n"
        "DataHub evidence is checked.\n\n"
        "00:00:02.100 --> 00:00:03.900\n"
        "Production rows were not queried.\n"
    )
    assert cues == (
        CaptionCue(500, 2_000, "DataHub evidence is checked."),
        CaptionCue(2_100, 3_900, "Production rows were not queried."),
    )


def test_caption_split_preserves_text_and_timing() -> None:
    cue = CaptionCue(
        start_ms=1_000,
        end_ms=5_000,
        text=(
            "ChangeSafe traces every returned dependency and states when "
            "DataHub did not provide an intermediate mapping."
        ),
    )
    parts = split_caption_cue(cue, max_chars=56)
    assert " ".join(part.text for part in parts) == cue.text
    assert parts[0].start_ms == cue.start_ms
    assert parts[-1].end_ms == cue.end_ms
    assert all(len(part.text) <= 56 for part in parts)
    assert all(left.end_ms == right.start_ms for left, right in pairwise(parts))


def test_timing_manifest_uses_scene_order_and_safe_paths(
    tmp_path: Path,
) -> None:
    audio_dir = tmp_path / "audio"
    audio_dir.mkdir()
    media = tuple(
        SceneMedia(
            scene_id=scene.scene_id,
            audio_path=audio_dir / f"{scene.scene_id}.mp3",
            vtt_path=audio_dir / f"{scene.scene_id}.vtt",
            audio_end_ms=scene.min_duration_ms - 800,
            captions=(CaptionCue(0, 900, scene.captions[0]),),
        )
        for scene in SCENES
    )
    manifest = build_timing_manifest(media, tmp_path)
    assert [item["scene_id"] for item in manifest["scenes"]] == [
        scene.scene_id for scene in SCENES
    ]
    assert manifest["total_duration_ms"] <= 175_000
    assert all(
        not Path(str(item["audio_path"])).is_absolute()
        for item in manifest["scenes"]
    )
    assert manifest["captions"][0]["start_ms"] == 0


def test_timing_manifest_rejects_media_outside_work_dir(
    tmp_path: Path,
) -> None:
    outside = tmp_path.parent / "outside.mp3"
    media = (
        SceneMedia(
            scene_id=SCENES[0].scene_id,
            audio_path=outside,
            vtt_path=tmp_path / "problem.vtt",
            audio_end_ms=1_000,
            captions=(CaptionCue(0, 900, "safe"),),
        ),
    )
    with pytest.raises(VideoProductionError, match="video work directory"):
        build_timing_manifest(media, tmp_path)


def test_command_result_type_matches_safe_runner_contract() -> None:
    result = CompletedProcess(["python", "-m", "edge_tts"], 0, "ok", "")
    assert result.returncode == 0
