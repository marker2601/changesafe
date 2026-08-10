from __future__ import annotations

import argparse
import json
import re
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import imageio_ffmpeg

from scripts.video.narration import VideoProductionError
from scripts.video.storyboard import default_output_dir


@dataclass(frozen=True)
class ComposeInputs:
    capture: Path
    work_dir: Path
    timing: dict[str, Any]
    output: Path
    closing_frame: Path | None = None


@dataclass(frozen=True)
class MediaProbe:
    duration_seconds: float
    width: int
    height: int
    frame_rate: float
    video_codec: str
    audio_codec: str
    file_size: int


def _inside(root: Path, relative_value: object) -> Path:
    if not isinstance(relative_value, str) or not relative_value:
        raise VideoProductionError("Narration audio path is missing.")
    relative = Path(relative_value)
    candidate = (root / relative).resolve()
    if relative.is_absolute() or not candidate.is_relative_to(root.resolve()):
        raise VideoProductionError(
            "Narration audio must remain inside the video work directory."
        )
    return candidate


def build_compose_command(
    ffmpeg: Path,
    inputs: ComposeInputs,
) -> list[str]:
    scenes = inputs.timing.get("scenes")
    total_ms = inputs.timing.get("total_duration_ms")
    if not isinstance(scenes, list) or len(scenes) != 9:
        raise VideoProductionError("Exactly nine timed scenes are required.")
    if not isinstance(total_ms, int) or not 145_000 <= total_ms <= 175_000:
        raise VideoProductionError("Video timing must be between 145000 and 175000 ms.")

    command = [str(ffmpeg), "-hide_banner", "-y", "-i", str(inputs.capture)]
    next_input = 1
    if inputs.closing_frame is not None:
        command.extend(
            [
                "-loop",
                "1",
                "-framerate",
                "30",
                "-i",
                str(inputs.closing_frame),
            ]
        )
        closing_input = next_input
        next_input += 1
    else:
        closing_input = None

    audio_indexes: list[int] = []
    for scene in scenes:
        audio_path = _inside(inputs.work_dir, scene.get("audio_path"))
        command.extend(["-i", str(audio_path)])
        audio_indexes.append(next_input)
        next_input += 1

    total_seconds = total_ms / 1_000
    video_filters = [
        (
            f"[0:v]trim=duration={total_seconds:.3f},setpts=PTS-STARTPTS,"
            "scale=1920:1080:force_original_aspect_ratio=decrease,"
            "pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=#00141d,"
            "setsar=1,fps=30,format=yuv420p[vbase]"
        )
    ]
    video_output = "vbase"
    if closing_input is not None:
        closing_start = scenes[-1].get("start_ms")
        if not isinstance(closing_start, int) or closing_start < 0:
            raise VideoProductionError("Closing scene timing is invalid.")
        video_filters.extend(
            [
                (
                    f"[{closing_input}:v]scale=1920:1080,setsar=1,"
                    "format=rgba[vclosing]"
                ),
                (
                    "[vbase][vclosing]overlay=enable="
                    f"'gte(t,{closing_start / 1_000:.3f})':"
                    "eof_action=repeat[vout]"
                ),
            ]
        )
        video_output = "vout"

    audio_filters: list[str] = []
    audio_labels: list[str] = []
    for index, (scene, input_index) in enumerate(
        zip(scenes, audio_indexes, strict=True)
    ):
        start_ms = scene.get("start_ms")
        if not isinstance(start_ms, int) or start_ms < 0:
            raise VideoProductionError("Narration scene timing is invalid.")
        label = f"a{index}"
        audio_filters.append(
            f"[{input_index}:a]aresample=48000,adelay={start_ms}|{start_ms}[{label}]"
        )
        audio_labels.append(f"[{label}]")
    audio_filters.append(
        "".join(audio_labels)
        + "amix=inputs=9:duration=longest:normalize=0,"
        + "alimiter=limit=0.95[aout]"
    )
    filter_graph = ";".join([*video_filters, *audio_filters])

    command.extend(
        [
            "-filter_complex",
            filter_graph,
            "-map",
            f"[{video_output}]",
            "-map",
            "[aout]",
            "-t",
            f"{total_seconds:.3f}",
            "-r",
            "30",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-movflags",
            "+faststart",
            "-map_metadata",
            "-1",
            "-metadata",
            "title=ChangeSafe — Data contract change intelligence",
            "-metadata",
            "artist=ChangeSafe",
            "-metadata",
            "comment=Recorded DataHub evidence; production rows not queried.",
            str(inputs.output),
        ]
    )
    return command


def verify_media(probe: MediaProbe) -> list[str]:
    errors: list[str] = []
    if probe.duration_seconds < 145:
        errors.append("duration must be at least 145 seconds")
    elif probe.duration_seconds > 175:
        errors.append("duration must not exceed 175 seconds")
    if probe.video_codec != "h264":
        errors.append("video codec must be h264")
    if probe.audio_codec != "aac":
        errors.append("audio codec must be aac")
    if (probe.width, probe.height) != (1920, 1080):
        errors.append("video dimensions must be 1920x1080")
    if abs(probe.frame_rate - 30) > 0.05:
        errors.append("video frame rate must be 30 fps")
    if not 1_000_000 <= probe.file_size <= 250_000_000:
        errors.append("video file size must be between 1 MB and 250 MB")
    return errors


def probe_media(ffmpeg: Path, media: Path) -> MediaProbe:
    result = subprocess.run(
        [str(ffmpeg), "-hide_banner", "-i", str(media), "-f", "null", "NUL"],
        check=False,
        capture_output=True,
        text=True,
        shell=False,
    )
    output = result.stderr
    if result.returncode != 0:
        raise VideoProductionError("Final video could not be decoded.")
    duration_match = re.search(
        r"Duration:\s*(\d{2}):(\d{2}):(\d{2}\.\d+)", output
    )
    video_match = re.search(
        r"Video:\s*([a-zA-Z0-9_]+).*?(\d{3,5})x(\d{3,5}).*?([\d.]+) fps",
        output,
    )
    audio_match = re.search(r"Audio:\s*([a-zA-Z0-9_]+)", output)
    if duration_match is None or video_match is None or audio_match is None:
        raise VideoProductionError("Final video stream metadata is incomplete.")
    hours, minutes, seconds = duration_match.groups()
    duration = int(hours) * 3_600 + int(minutes) * 60 + float(seconds)
    codec, width, height, frame_rate = video_match.groups()
    return MediaProbe(
        duration_seconds=duration,
        width=int(width),
        height=int(height),
        frame_rate=float(frame_rate),
        video_codec=codec,
        audio_codec=audio_match.group(1),
        file_size=media.stat().st_size,
    )


def _run_checked(command: list[str], message: str) -> None:
    try:
        subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            shell=False,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise VideoProductionError(message) from error


def compose_and_verify(
    inputs: ComposeInputs,
    *,
    poster: Path,
    capture_report: Path,
    verification: Path,
) -> MediaProbe:
    ffmpeg = Path(imageio_ffmpeg.get_ffmpeg_exe()).resolve()
    encoder_result = subprocess.run(
        [str(ffmpeg), "-hide_banner", "-encoders"],
        check=True,
        capture_output=True,
        text=True,
        shell=False,
    )
    if "libx264" not in encoder_result.stdout or " aac " not in encoder_result.stdout:
        raise VideoProductionError("Required H.264 and AAC encoders are unavailable.")

    inputs.output.parent.mkdir(parents=True, exist_ok=True)
    try:
        _run_checked(
            build_compose_command(ffmpeg, inputs),
            "Final video composition failed.",
        )
        probe = probe_media(ffmpeg, inputs.output)
        errors = verify_media(probe)
        if errors:
            raise VideoProductionError("; ".join(errors))
        _run_checked(
            [
                str(ffmpeg),
                "-hide_banner",
                "-y",
                "-ss",
                "14",
                "-i",
                str(inputs.output),
                "-frames:v",
                "1",
                str(poster),
            ],
            "Video poster extraction failed.",
        )
        capture = json.loads(capture_report.read_text(encoding="utf-8"))
        public_report = {
            "version": 1,
            "media": asdict(probe),
            "capture": capture,
            "claims": {
                "context": "Recorded DataHub evidence",
                "warehouse": "Production rows not queried",
                "publication": "Preview only; no external systems changed",
            },
        }
        verification.write_text(
            json.dumps(public_report, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return probe
    except Exception:
        inputs.output.unlink(missing_ok=True)
        raise


def _parser() -> argparse.ArgumentParser:
    output = default_output_dir()
    work = output / ".video-work"
    parser = argparse.ArgumentParser(description="Compose the ChangeSafe demo video.")
    parser.add_argument(
        "--capture", type=Path, default=work / "capture" / "changesafe-demo.webm"
    )
    parser.add_argument("--timing", type=Path, default=work / "timing.json")
    parser.add_argument("--work-dir", type=Path, default=work)
    parser.add_argument(
        "--closing-frame", type=Path, default=work / "capture" / "closing.png"
    )
    parser.add_argument(
        "--capture-report",
        type=Path,
        default=work / "capture" / "capture-report.json",
    )
    parser.add_argument(
        "--output", type=Path, default=output / "changesafe-competition-demo.mp4"
    )
    parser.add_argument(
        "--poster", type=Path, default=output / "changesafe-video-poster.png"
    )
    parser.add_argument(
        "--verification",
        type=Path,
        default=output / "changesafe-video-verification.json",
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    timing = json.loads(args.timing.read_text(encoding="utf-8"))
    inputs = ComposeInputs(
        capture=args.capture.resolve(),
        work_dir=args.work_dir.resolve(),
        timing=timing,
        output=args.output.resolve(),
        closing_frame=args.closing_frame.resolve(),
    )
    probe = compose_and_verify(
        inputs,
        poster=args.poster.resolve(),
        capture_report=args.capture_report.resolve(),
        verification=args.verification.resolve(),
    )
    print(json.dumps(asdict(probe), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
