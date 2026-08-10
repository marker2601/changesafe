from __future__ import annotations

import argparse
import base64
import binascii
import json
import re
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from html import unescape
from pathlib import Path
from subprocess import CompletedProcess
from typing import Any
from urllib.request import Request, urlopen

from scripts.video.storyboard import SCENES, Scene, default_output_dir


class VideoProductionError(RuntimeError):
    """A stable, public-safe video production failure."""


@dataclass(frozen=True)
class CaptionCue:
    start_ms: int
    end_ms: int
    text: str


@dataclass(frozen=True)
class SceneMedia:
    scene_id: str
    audio_path: Path
    vtt_path: Path
    audio_end_ms: int
    captions: tuple[CaptionCue, ...]


CommandRunner = Callable[[list[str]], CompletedProcess[str]]

_APPROVED_VOICES = (
    "en-US-AvaMultilingualNeural",
    "en-US-JennyNeural",
)
DEFAULT_ELEVENLABS_VOICE_ID = "JBFqnCBsd6RMkjVDRZzb"
_ELEVENLABS_VOICE_ID = re.compile(r"^[A-Za-z0-9_-]{20}$")
_PRIVATE_VIDEO_ENV = Path("C:/Users/harik/.changesafe-private/video.env")
_VOICE_NAME = re.compile(r"^[a-z]{2}-[A-Z]{2}-[A-Za-z]+(?:Multilingual)?Neural$")
_TIMESTAMP = re.compile(
    r"^(?P<hours>\d{2}):(?P<minutes>\d{2}):(?P<seconds>\d{2})"
    r"[.,](?P<milliseconds>\d{3})$"
)


def run_checked(command: list[str]) -> CompletedProcess[str]:
    return subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        shell=False,
    )


def load_private_video_env(path: Path = _PRIVATE_VIDEO_ENV) -> dict[str, str]:
    if not path.is_file():
        return {}
    values: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as error:
        raise VideoProductionError(
            "Private video configuration is unreadable."
        ) from error
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        if value.strip():
            values[key.strip()] = value.strip()
    return values


def resolve_elevenlabs_voice_id(candidate: str | None) -> str:
    if candidate and _ELEVENLABS_VOICE_ID.fullmatch(candidate):
        return candidate
    return DEFAULT_ELEVENLABS_VOICE_ID


def build_elevenlabs_request(
    *,
    text: str,
    api_key: str,
    voice_id: str,
) -> Request:
    resolved_voice = resolve_elevenlabs_voice_id(voice_id)
    url = (
        "https://api.elevenlabs.io/v1/text-to-speech/"
        f"{resolved_voice}/with-timestamps?output_format=mp3_44100_128"
    )
    body = json.dumps(
        {
            "text": text,
            "model_id": "eleven_multilingual_v2",
            "voice_settings": {
                "stability": 0.55,
                "similarity_boost": 0.75,
                "style": 0.12,
                "use_speaker_boost": True,
            },
        },
        separators=(",", ":"),
    ).encode("utf-8")
    return Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "xi-api-key": api_key,
        },
        method="POST",
    )


def parse_elevenlabs_response(
    payload: bytes,
    expected_text: str,
) -> tuple[bytes, tuple[CaptionCue, ...]]:
    try:
        response = json.loads(payload)
        encoded_audio = response["audio_base64"]
        alignment = response.get("alignment") or response["normalized_alignment"]
        characters = alignment["characters"]
        end_times = alignment["character_end_times_seconds"]
        audio = base64.b64decode(encoded_audio, validate=True)
    except (
        binascii.Error,
        KeyError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
    ) as error:
        raise VideoProductionError(
            "ElevenLabs returned invalid narration media."
        ) from error
    if not audio or not characters or len(characters) != len(end_times):
        raise VideoProductionError("ElevenLabs returned incomplete narration media.")
    if "".join(str(character) for character in characters) != expected_text:
        raise VideoProductionError(
            "ElevenLabs narration alignment did not match the script."
        )
    end_ms = round(float(end_times[-1]) * 1_000)
    if end_ms <= 0:
        raise VideoProductionError("ElevenLabs returned invalid narration timing.")
    cue = CaptionCue(0, end_ms, expected_text)
    return audio, split_caption_cue(cue, max_chars=96)


def parse_available_voices(output: str) -> set[str]:
    voices: set[str] = set()
    for line in output.splitlines():
        fields = line.strip().split()
        if fields and _VOICE_NAME.fullmatch(fields[0]):
            voices.add(fields[0])
    return voices


def select_voice(available: set[str]) -> str:
    for candidate in _APPROVED_VOICES:
        if candidate in available:
            return candidate
    raise VideoProductionError("No approved generated voice is available.")


def build_edge_tts_command(
    *,
    text: str,
    voice: str,
    media_path: Path,
    subtitles_path: Path,
) -> list[str]:
    if voice not in _APPROVED_VOICES:
        raise VideoProductionError("The generated voice is not approved.")
    return [
        sys.executable,
        "-m",
        "edge_tts",
        "--voice",
        voice,
        "--rate=-2%",
        "--text",
        text,
        "--write-media",
        str(media_path),
        "--write-subtitles",
        str(subtitles_path),
    ]


def _timestamp_ms(value: str) -> int:
    match = _TIMESTAMP.fullmatch(value.strip())
    if match is None:
        raise VideoProductionError("Narration subtitles contain an invalid timestamp.")
    return (
        int(match.group("hours")) * 3_600_000
        + int(match.group("minutes")) * 60_000
        + int(match.group("seconds")) * 1_000
        + int(match.group("milliseconds"))
    )


def _clean_caption(value: str) -> str:
    without_tags = re.sub(r"<[^>]+>", "", value)
    return " ".join(unescape(without_tags).split())


def parse_vtt(value: str) -> tuple[CaptionCue, ...]:
    lines = value.lstrip("\ufeff").splitlines()
    cues: list[CaptionCue] = []
    index = 0
    while index < len(lines):
        line = lines[index].strip()
        if "-->" not in line:
            index += 1
            continue
        start_raw, end_with_settings = (part.strip() for part in line.split("-->", 1))
        end_raw = end_with_settings.split()[0]
        start_ms = _timestamp_ms(start_raw)
        end_ms = _timestamp_ms(end_raw)
        index += 1
        text_lines: list[str] = []
        while index < len(lines) and lines[index].strip():
            if "-->" in lines[index]:
                break
            text_lines.append(lines[index].strip())
            index += 1
        text = _clean_caption(" ".join(text_lines))
        if not text or end_ms <= start_ms:
            raise VideoProductionError("Narration subtitles contain an invalid cue.")
        cues.append(CaptionCue(start_ms, end_ms, text))
    if not cues:
        raise VideoProductionError("Narration subtitles contain no cues.")
    return tuple(cues)


def split_caption_cue(
    cue: CaptionCue,
    *,
    max_chars: int = 96,
) -> tuple[CaptionCue, ...]:
    normalized = " ".join(cue.text.split())
    if len(normalized) <= max_chars:
        return (CaptionCue(cue.start_ms, cue.end_ms, normalized),)
    words = normalized.split()
    if any(len(word) > max_chars for word in words):
        raise VideoProductionError("Narration contains an unsplittable caption word.")
    chunks: list[str] = []
    current: list[str] = []
    for word in words:
        candidate = " ".join([*current, word])
        if current and len(candidate) > max_chars:
            chunks.append(" ".join(current))
            current = [word]
        else:
            current.append(word)
    if current:
        chunks.append(" ".join(current))

    duration = cue.end_ms - cue.start_ms
    weights = [len(chunk) for chunk in chunks]
    total_weight = sum(weights)
    result: list[CaptionCue] = []
    cursor = cue.start_ms
    consumed_weight = 0
    for index, (chunk, weight) in enumerate(zip(chunks, weights, strict=True)):
        consumed_weight += weight
        end_ms = (
            cue.end_ms
            if index == len(chunks) - 1
            else cue.start_ms + round(duration * consumed_weight / total_weight)
        )
        result.append(CaptionCue(cursor, end_ms, chunk))
        cursor = end_ms
    return tuple(result)


def _inside(root: Path, candidate: Path) -> Path:
    try:
        return candidate.resolve().relative_to(root.resolve())
    except ValueError as error:
        raise VideoProductionError(
            "Narration media must remain inside the video work directory."
        ) from error


def build_timing_manifest(
    media: Sequence[SceneMedia],
    work_dir: Path,
) -> dict[str, Any]:
    for item in media:
        _inside(work_dir, item.audio_path)
        _inside(work_dir, item.vtt_path)

    expected_ids = [scene.scene_id for scene in SCENES]
    actual_ids = [item.scene_id for item in media]
    if actual_ids != expected_ids:
        raise VideoProductionError("Narration media scene order is invalid.")

    scene_by_id = {scene.scene_id: scene for scene in SCENES}
    cursor = 0
    scenes: list[dict[str, Any]] = []
    global_captions: list[dict[str, Any]] = []
    for item in media:
        scene = scene_by_id[item.scene_id]
        audio_relative = _inside(work_dir, item.audio_path)
        vtt_relative = _inside(work_dir, item.vtt_path)
        duration_ms = max(scene.min_duration_ms, item.audio_end_ms + 800)
        for cue_index, cue in enumerate(item.captions):
            if cue.start_ms < 0 or cue.end_ms <= cue.start_ms:
                raise VideoProductionError("Narration caption timing is invalid.")
            global_captions.append(
                {
                    "cue_id": f"{scene.scene_id}-{cue_index + 1}",
                    "scene_id": scene.scene_id,
                    "start_ms": cursor + cue.start_ms,
                    "end_ms": cursor + cue.end_ms,
                    "text": cue.text,
                }
            )
        scenes.append(
            {
                "scene_id": scene.scene_id,
                "start_ms": cursor,
                "duration_ms": duration_ms,
                "audio_path": audio_relative.as_posix(),
                "vtt_path": vtt_relative.as_posix(),
                "callouts": list(scene.captions),
            }
        )
        cursor += duration_ms
    if cursor > 175_000:
        raise VideoProductionError("Narration timeline exceeds 175000 ms.")
    return {
        "version": 1,
        "total_duration_ms": cursor,
        "scenes": scenes,
        "captions": global_captions,
    }


def _srt_timestamp(milliseconds: int) -> str:
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, milliseconds = divmod(remainder, 1_000)
    return f"{hours:02}:{minutes:02}:{seconds:02},{milliseconds:03}"


def _write_srt(captions: Sequence[dict[str, Any]], path: Path) -> None:
    blocks = [
        (
            f"{index}\n"
            f"{_srt_timestamp(int(cue['start_ms']))} --> "
            f"{_srt_timestamp(int(cue['end_ms']))}\n"
            f"{cue['text']}"
        )
        for index, cue in enumerate(captions, start=1)
    ]
    path.write_text("\n\n".join(blocks) + "\n", encoding="utf-8")


def _write_script(
    scenes: Sequence[dict[str, Any]],
    path: Path,
) -> None:
    narration_by_id: dict[str, Scene] = {
        scene.scene_id: scene for scene in SCENES
    }
    sections = ["# ChangeSafe competition video narration", ""]
    for item in scenes:
        start_seconds = int(item["start_ms"]) // 1_000
        minutes, seconds = divmod(start_seconds, 60)
        scene = narration_by_id[str(item["scene_id"])]
        sections.extend(
            [
                f"## {minutes}:{seconds:02} — {scene.scene_id}",
                "",
                scene.narration,
                "",
            ]
        )
    path.write_text("\n".join(sections), encoding="utf-8")


def _write_vtt(cues: Sequence[CaptionCue], path: Path) -> None:
    blocks = ["WEBVTT", ""]
    for cue in cues:
        start = _srt_timestamp(cue.start_ms).replace(",", ".")
        end = _srt_timestamp(cue.end_ms).replace(",", ".")
        blocks.extend([f"{start} --> {end}", cue.text, ""])
    path.write_text("\n".join(blocks), encoding="utf-8")


def _elevenlabs_media(
    audio_dir: Path,
    *,
    api_key: str,
    voice_id: str,
) -> tuple[SceneMedia, ...]:
    media: list[SceneMedia] = []
    for scene in SCENES:
        request = build_elevenlabs_request(
            text=scene.narration,
            api_key=api_key,
            voice_id=voice_id,
        )
        try:
            response = urlopen(request, timeout=60)
            try:
                payload = response.read()
            finally:
                response.close()
            audio, cues = parse_elevenlabs_response(payload, scene.narration)
        except VideoProductionError:
            raise
        except (OSError, TimeoutError) as error:
            raise VideoProductionError(
                "ElevenLabs narration request failed."
            ) from error
        audio_path = audio_dir / f"{scene.scene_id}.mp3"
        vtt_path = audio_dir / f"{scene.scene_id}.vtt"
        audio_path.write_bytes(audio)
        _write_vtt(cues, vtt_path)
        media.append(
            SceneMedia(
                scene_id=scene.scene_id,
                audio_path=audio_path,
                vtt_path=vtt_path,
                audio_end_ms=max(cue.end_ms for cue in cues),
                captions=cues,
            )
        )
    return tuple(media)


def _edge_media(
    audio_dir: Path,
    runner: CommandRunner,
) -> tuple[tuple[SceneMedia, ...], str]:
    try:
        listed = runner([sys.executable, "-m", "edge_tts", "--list-voices"])
    except (OSError, subprocess.CalledProcessError) as error:
        raise VideoProductionError("Generated voice discovery failed.") from error
    voice = select_voice(parse_available_voices(listed.stdout))

    media: list[SceneMedia] = []
    for scene in SCENES:
        audio_path = audio_dir / f"{scene.scene_id}.mp3"
        vtt_path = audio_dir / f"{scene.scene_id}.vtt"
        command = build_edge_tts_command(
            text=scene.narration,
            voice=voice,
            media_path=audio_path,
            subtitles_path=vtt_path,
        )
        try:
            runner(command)
            if not audio_path.is_file() or audio_path.stat().st_size == 0:
                raise OSError("empty narration media")
            cues = parse_vtt(vtt_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, subprocess.CalledProcessError) as error:
            raise VideoProductionError(
                f"Narration generation failed for scene {scene.scene_id}."
            ) from error
        split_cues = tuple(
            part
            for cue in cues
            for part in split_caption_cue(cue, max_chars=96)
        )
        media.append(
            SceneMedia(
                scene_id=scene.scene_id,
                audio_path=audio_path,
                vtt_path=vtt_path,
                audio_end_ms=max(cue.end_ms for cue in split_cues),
                captions=split_cues,
            )
        )
    return tuple(media), voice


def prepare_narration(
    output_dir: Path,
    runner: CommandRunner = run_checked,
) -> Path:
    output_root = output_dir.expanduser().resolve()
    work_dir = output_root / ".video-work"
    audio_dir = work_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)

    private_env = load_private_video_env()
    api_key = private_env.get("ELEVENLABS_API_KEY")
    configured_voice = private_env.get("ELEVENLABS_VOICE_ID")
    provider = "edge-tts"
    voice = ""
    if api_key:
        try:
            voice = resolve_elevenlabs_voice_id(configured_voice)
            media = _elevenlabs_media(
                audio_dir,
                api_key=api_key,
                voice_id=voice,
            )
            provider = "elevenlabs"
        except VideoProductionError:
            print(
                "ElevenLabs narration was unavailable; using the safe fallback.",
                file=sys.stderr,
            )
            media, voice = _edge_media(audio_dir, runner)
    else:
        media, voice = _edge_media(audio_dir, runner)

    manifest = build_timing_manifest(media, work_dir)
    manifest["provider"] = provider
    manifest["voice"] = voice
    timing_path = work_dir / "timing.json"
    timing_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    _write_srt(
        manifest["captions"],
        output_root / "changesafe-competition-demo.srt",
    )
    _write_script(
        manifest["scenes"],
        output_root / "changesafe-video-script.md",
    )
    return timing_path


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate safe ChangeSafe competition narration."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=default_output_dir(),
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    timing = prepare_narration(args.output_dir)
    print(timing)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
