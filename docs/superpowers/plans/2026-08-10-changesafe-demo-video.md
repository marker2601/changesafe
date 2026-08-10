# ChangeSafe Competition Demo Video Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a verified, professional 1080p ChangeSafe competition video with generated narration, synchronized captions, real hosted interactions, and a runtime below three minutes.

**Architecture:** A typed Python storyboard is the single source of narration and scene requirements. A pinned credential-free TTS preparation step emits per-scene audio and timing data; a Playwright recorder consumes that timing data to capture asserted states from the permanent hosted application with burned-in HTML captions; a separate FFmpeg composer creates the H.264/AAC MP4, poster, SRT, and verification report. Binary output stays outside Git history under the user's Videos folder.

**Tech Stack:** Python 3.12, `edge-tts==7.2.8`, `imageio-ffmpeg==0.6.0`, Node.js 24, Playwright, pytest, Node test runner, FFmpeg, PowerShell.

## Global Constraints

- Final runtime target is 2:35–2:45 with a hard maximum of 2:55.
- Final video is 1920×1080, 16:9, 30 fps, H.264 video with AAC audio.
- Generated narration uses `en-US-AvaMultilingualNeural` at `-2%` rate unless the voice list does not contain that exact name; the only fallback is `en-US-JennyNeural`.
- The permanent source is `https://changesafe-competition.onrender.com` on public replay configuration.
- Every product frame comes from an asserted hosted application state.
- Captions are burned into the video and also delivered as an SRT file.
- The video must state recorded DataHub evidence, preview only, and production rows not queried.
- No raw query, credential, token, private endpoint, relation fingerprint, raw warehouse value, or private operator detail may enter source text, output metadata, or a frame.
- Binary media output is written to `Path.home() / "Videos" / "ChangeSafe Submission"`; this machine has no `D:` drive.
- No MP4, WebM, MP3, WAV, or generated poster is committed to Git.
- The first cut has no background music. Generated voice and product visuals carry the story.

## File structure

- Create `scripts/video/__init__.py`: marks the production helpers as an importable package.
- Create `scripts/video/storyboard.py`: owns immutable scenes, narration, caption chunks, visual minimums, and story validation.
- Create `scripts/video/narration.py`: selects a supported voice, invokes pinned Edge TTS, parses VTT timing, and writes the capture timing manifest plus SRT.
- Create `scripts/video/requirements.txt`: pins the two non-production media dependencies.
- Create `scripts/video/capture_contract.mjs`: pure timing, URL, overlay, and safety helpers shared by recorder tests and implementation.
- Create `scripts/video/capture_contract.test.mjs`: Node unit tests for capture safety and timing.
- Create `scripts/video/capture_demo.mjs`: records the real hosted scene sequence with Playwright assertions and HTML captions.
- Create `scripts/video/compose_demo.py`: muxes captured video and delayed scene audio, emits H.264/AAC MP4, poster, and verification report.
- Create `scripts/video/run_demo_video.ps1`: one-command, fail-closed production pipeline.
- Create `scripts/video/README.md`: exact local generation and upload-review instructions.
- Create `apps/api/tests/test_video_production.py`: unit and contract tests for storyboard, narration manifest, composition command, and output confinement.
- Modify `.gitignore`: ignore only `.video-work/` and `video-output/` if those names are created inside the checkout accidentally.
- Modify `docs/demo-script.md`: replace the obsolete three-full-flow script and temporary tunnel statement with the approved concise script and permanent URL.
- Modify `docs/devpost-submission.md`: replace the stale hosted-app line and mark the generated MP4 as ready for public upload.

---

### Task 1: Storyboard contract and safety tests

**Files:**
- Create: `scripts/video/__init__.py`
- Create: `scripts/video/storyboard.py`
- Create: `apps/api/tests/test_video_production.py`

**Interfaces:**
- Produces: `Scene`, `SCENES`, `TOTAL_VISUAL_MS`, `narration_word_count()`, `validate_storyboard()`, and `default_output_dir()`.
- Consumes: no production code; it copies the approved narration from `docs/superpowers/specs/2026-08-10-changesafe-demo-video-design.md`.

- [ ] **Step 1: Write failing storyboard contract tests**

Add tests that import the absent module and define the binding requirements:

```python
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
```

- [ ] **Step 2: Run the storyboard tests and observe RED**

Run:

```powershell
& '.\.venv\Scripts\python.exe' -m pytest -q apps/api/tests/test_video_production.py
```

Expected: collection fails because `scripts.video.storyboard` does not exist.

- [ ] **Step 3: Implement the immutable storyboard**

Define this public shape and the nine approved scenes:

```python
from dataclasses import dataclass
from pathlib import Path
import re


@dataclass(frozen=True)
class Scene:
    scene_id: str
    min_duration_ms: int
    narration: str
    captions: tuple[str, ...]
    required_dom_text: tuple[str, ...] = ()


SCENES = (
    Scene(
        "problem",
        12_000,
        "A column rename looks simple. But in analytics, one field can feed "
        "models, metrics, dashboards, and the teams making decisions from "
        "them. Change it without context, and the failure appears far downstream.",
        ("A column rename looks simple.", "One field can feed decisions far downstream."),
    ),
    Scene(
        "truth-boundary",
        15_000,
        "ChangeSafe turns DataHub context into a verified migration decision "
        "before anything is published. This hosted demonstration uses "
        "checksum-pinned recorded DataHub evidence, exercises the real "
        "application pipeline, and clearly states that production rows were "
        "not queried.",
        ("DataHub context before publication.", "Recorded evidence · Production rows not queried"),
        ("Recorded DataHub schema", "Production rows not queried"),
    ),
    Scene(
        "schema-request",
        18_000,
        "We start from the allowlisted order_details schema. DataHub returns "
        "fifty-five concrete fields with their native types and nullability. "
        "We select cust_email, propose primary_email, and analyze the change.",
        ("55 schema fields", "cust_email → primary_email"),
        ("Current field", "Analyze change"),
    ),
    Scene(
        "lineage",
        27_000,
        "Persisted events show each real phase. ChangeSafe retrieves "
        "field-scoped metadata, traces upstream and downstream dependencies, "
        "and labels the precision of every relationship. Exact routes name "
        "both returned fields. Multi-hop and dataset-level evidence disclose "
        "what DataHub did not return instead of inventing a connection. For "
        "this field, six upstream and twenty-five downstream relationships "
        "show how widely one contract change can travel.",
        ("Field-scoped dependency evidence", "Exact routes stay exact", "Unknown mappings stay unknown"),
        ("Recorded dependents", "25 downstream assets"),
    ),
    Scene(
        "impact",
        22_000,
        "The same evidence drives six impact classifications and a "
        "deterministic factor score, with every point traceable to the factor "
        "ledger. Then ChangeSafe creates a conservative phase-one migration: "
        "the governed model stays intact while a compatibility shim exposes "
        "the old and new contract together.",
        ("Six evidence-led impact areas", "Every score factor is traceable"),
        ("Impact classification", "Critical technical risk"),
    ),
    Scene(
        "artifacts",
        24_000,
        "The result is seven reviewable files with exact hashes, rollback "
        "guidance, and an operation-specific compatibility test. Twelve "
        "blocking checks verify the request, metadata, SQL, YAML, output "
        "contract, paths, rollback, and manifest.",
        ("7 verified files", "12 / 12 blocking checks"),
        ("Generated artifacts", "12 / 12"),
    ),
    Scene(
        "multi-field",
        16_000,
        "This is not an email-only workflow. Selecting order_status rebuilds "
        "the evidence for removal. Selecting order_total rebuilds it for a "
        "type change. The chosen field and operation bind the assessment and "
        "every generated byte. Unknown fields and destination collisions are "
        "blocked before a run can start.",
        ("Not email-only", "Field + operation bind every result"),
    ),
    Scene(
        "approval",
        19_000,
        "Finally, ChangeSafe pauses for the accountable owner. In this "
        "competition-safe mode, approval creates a non-mutating receipt and a "
        "downloadable patch. Nothing is silently written.",
        ("Human approval required", "NOT WRITTEN — SNAPSHOT MODE"),
        ("Approve preview", "Preview ready", "Download patch"),
    ),
    Scene(
        "closing",
        9_000,
        "ChangeSafe makes schema change review evidence-bound, fail-closed, "
        "and human approved—using DataHub to keep every dependency in view.",
        ("Evidence-bound. Fail-closed. Human-approved.",),
    ),
)

TOTAL_VISUAL_MS = sum(scene.min_duration_ms for scene in SCENES)


def narration_word_count() -> int:
    return len(re.findall(r"[A-Za-z0-9]+(?:[-'][A-Za-z0-9]+)*", " ".join(s.narration for s in SCENES)))


def default_output_dir() -> Path:
    return Path.home() / "Videos" / "ChangeSafe Submission"
```

Implement `validate_storyboard()` to return stable error strings for duplicate scene IDs, captions longer than 96 characters, missing narration, out-of-range total duration, and any of the forbidden claim fragments from the tests.

```python
FORBIDDEN_CLAIMS = (
    "judge-prepared",
    "production rows passed",
    "live warehouse passed",
    "temporary tunnel",
    "api token",
    "private key",
)


def validate_storyboard() -> list[str]:
    errors: list[str] = []
    ids = [scene.scene_id for scene in SCENES]
    if len(ids) != len(set(ids)):
        errors.append("scene ids must be unique")
    if not 145_000 <= TOTAL_VISUAL_MS <= 175_000:
        errors.append("visual runtime must be between 145000 and 175000 ms")
    for scene in SCENES:
        if not scene.narration.strip():
            errors.append(f"{scene.scene_id}: narration is required")
        if any(len(caption) > 96 for caption in scene.captions):
            errors.append(f"{scene.scene_id}: caption exceeds 96 characters")
    combined = " ".join(scene.narration for scene in SCENES).casefold()
    for fragment in FORBIDDEN_CLAIMS:
        if fragment in combined:
            errors.append(f"forbidden claim: {fragment}")
    return errors
```

- [ ] **Step 4: Run focused tests and static checks**

Run:

```powershell
& '.\.venv\Scripts\python.exe' -m pytest -q apps/api/tests/test_video_production.py
& '.\.venv\Scripts\ruff.exe' check scripts/video apps/api/tests/test_video_production.py
```

Expected: all tests and Ruff pass.

- [ ] **Step 5: Commit Task 1**

```powershell
git add scripts/video/__init__.py scripts/video/storyboard.py apps/api/tests/test_video_production.py
git commit -m "test: define competition video storyboard"
```

---

### Task 2: Credential-free narration and timing manifest

**Files:**
- Create: `scripts/video/requirements.txt`
- Create: `scripts/video/narration.py`
- Modify: `apps/api/tests/test_video_production.py`

**Interfaces:**
- Consumes: `SCENES` and `default_output_dir()` from Task 1.
- Produces: `CaptionCue`, `SceneMedia`, `select_voice()`, `build_timing_manifest()`, `prepare_narration(output_dir: Path, runner: CommandRunner) -> Path`, `timing.json`, per-scene MP3/VTT files, `changesafe-competition-demo.srt`, and `changesafe-video-script.md`.

- [ ] **Step 1: Pin non-production media dependencies**

Create `scripts/video/requirements.txt` exactly:

```text
edge-tts==7.2.8
imageio-ffmpeg==0.6.0
```

- [ ] **Step 2: Add RED tests for voice selection, command safety, and timing output**

Use a fake command runner so CI never calls the external TTS service. Assert:

```python
def test_voice_selection_prefers_ava_then_jenny() -> None:
    assert select_voice({"en-US-AvaMultilingualNeural", "en-US-JennyNeural"}) == "en-US-AvaMultilingualNeural"
    assert select_voice({"en-US-JennyNeural"}) == "en-US-JennyNeural"
    with pytest.raises(VideoProductionError, match="approved generated voice"):
        select_voice({"en-US-DavidNeural"})


def test_timing_manifest_uses_scene_order_and_safe_paths(tmp_path: Path) -> None:
    media = tuple(
        SceneMedia(
            scene_id=scene.scene_id,
            audio_path=tmp_path / f"{scene.scene_id}.mp3",
            vtt_path=tmp_path / f"{scene.scene_id}.vtt",
            audio_end_ms=scene.min_duration_ms - 800,
            captions=(CaptionCue(0, 900, scene.captions[0]),),
        )
        for scene in SCENES
    )
    manifest = build_timing_manifest(media, tmp_path)
    assert [item["scene_id"] for item in manifest["scenes"]] == [s.scene_id for s in SCENES]
    assert manifest["total_duration_ms"] <= 175_000
    assert all(Path(item["audio_path"]).is_relative_to(tmp_path) for item in manifest["scenes"])
```

Also assert that narration commands use `sys.executable -m edge_tts`, the chosen allowlisted voice, `--rate=-2%`, `--write-media`, and `--write-subtitles`, and never use `shell=True`.

- [ ] **Step 3: Run RED narration tests**

Run:

```powershell
& '.\.venv\Scripts\python.exe' -m pytest -q apps/api/tests/test_video_production.py -k "voice or timing or narration"
```

Expected: import or attribute failures for the absent narration module.

- [ ] **Step 4: Implement narration preparation**

Implement these exact public contracts:

```python
class VideoProductionError(RuntimeError):
    pass


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


CommandRunner = Callable[[list[str]], subprocess.CompletedProcess[str]]


def select_voice(available: set[str]) -> str:
    for candidate in ("en-US-AvaMultilingualNeural", "en-US-JennyNeural"):
        if candidate in available:
            return candidate
    raise VideoProductionError("No approved generated voice is available.")


def prepare_narration(
    output_dir: Path,
    runner: CommandRunner = run_checked,
) -> Path:
    """Write per-scene media, global SRT/script, and return timing.json."""
```

The implementation must:

1. Create `output_dir / ".video-work" / "audio"`.
2. Call `python -m edge_tts --list-voices` and select only the two approved voices.
3. Generate one MP3 and VTT per scene using argument arrays.
4. Parse each VTT cue, rebase it to the scene's global start, and split caption text only at whitespace.
5. Set each scene duration to `max(scene.min_duration_ms, audio_end_ms + 800)` and fail if total duration exceeds 175,000 ms.
6. Write UTF-8 JSON with version `1`, voice, total duration, scene start/duration/audio paths, and global caption cues.
7. Write a standard numbered SRT with `HH:MM:SS,mmm` timestamps.
8. Write the approved narration and timestamps to `changesafe-video-script.md`.
9. Mask command failures with `Narration generation failed for scene <scene_id>.` and never echo response bodies or environment values.

- [ ] **Step 5: Run narration tests and full focused gate**

```powershell
& '.\.venv\Scripts\python.exe' -m pytest -q apps/api/tests/test_video_production.py
& '.\.venv\Scripts\ruff.exe' check scripts/video apps/api/tests/test_video_production.py
```

Expected: all pass without a network call.

- [ ] **Step 6: Commit Task 2**

```powershell
git add scripts/video/requirements.txt scripts/video/narration.py apps/api/tests/test_video_production.py
git commit -m "feat: prepare generated demo narration"
```

---

### Task 3: Asserted hosted browser capture

**Files:**
- Create: `scripts/video/capture_contract.mjs`
- Create: `scripts/video/capture_contract.test.mjs`
- Create: `scripts/video/capture_demo.mjs`

**Interfaces:**
- Consumes: `timing.json` from Task 2 and the permanent hosted base URL.
- Produces: `.video-work/capture/changesafe-demo.webm` and one 1920×1080 PNG review frame per scene.

- [ ] **Step 1: Write RED Node tests for the capture boundary**

Create tests using `node:test` and `node:assert/strict`:

```javascript
test("accepts only the permanent HTTPS application origin", () => {
  assert.equal(
    assertSafeBaseUrl("https://changesafe-competition.onrender.com"),
    "https://changesafe-competition.onrender.com",
  );
  for (const value of [
    "http://changesafe-competition.onrender.com",
    "https://example.invalid",
    "https://user:pass@changesafe-competition.onrender.com",
  ]) {
    assert.throws(() => assertSafeBaseUrl(value), /approved hosted origin/);
  }
});

test("rejects timing manifests that reorder or exceed scenes", () => {
  assert.throws(() => validateTimingManifest(reorderedManifest, "C:/video-work"), /scene order/);
  assert.throws(() => validateTimingManifest(overlongManifest, "C:/video-work"), /175000/);
});

test("overlay text is inserted with textContent and never HTML", () => {
  const model = overlayModel("<img src=x onerror=alert(1)>", "55 fields");
  assert.equal(model.caption, "<img src=x onerror=alert(1)>");
  assert.equal(model.callout, "55 fields");
  assert.equal(Object.hasOwn(model, "html"), false);
});
```

- [ ] **Step 2: Run RED Node tests**

```powershell
$env:PATH='C:\Users\harik\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin;' + $env:PATH
node --test scripts/video/capture_contract.test.mjs
```

Expected: module-not-found failure for `capture_contract.mjs`.

- [ ] **Step 3: Implement pure capture contracts**

Export:

```javascript
import path from "node:path";

export const SCENE_IDS = [
  "problem", "truth-boundary", "schema-request", "lineage", "impact",
  "artifacts", "multi-field", "approval", "closing",
];

const APPROVED_ORIGIN = "https://changesafe-competition.onrender.com";

export function assertSafeBaseUrl(value) {
  const parsed = new URL(value);
  if (
    parsed.origin !== APPROVED_ORIGIN ||
    parsed.username !== "" ||
    parsed.password !== "" ||
    (parsed.pathname !== "/" && parsed.pathname !== "") ||
    parsed.search !== "" ||
    parsed.hash !== ""
  ) {
    throw new Error("Base URL must use the approved hosted origin.");
  }
  return parsed.origin;
}

export function validateTimingManifest(value, workDir) {
  if (value?.version !== 1 || !Array.isArray(value.scenes)) {
    throw new Error("Timing manifest version 1 is required.");
  }
  const ids = value.scenes.map((scene) => scene.scene_id);
  if (JSON.stringify(ids) !== JSON.stringify(SCENE_IDS)) {
    throw new Error("Timing manifest scene order is invalid.");
  }
  if (!Number.isInteger(value.total_duration_ms) || value.total_duration_ms > 175000) {
    throw new Error("Timing manifest must not exceed 175000 ms.");
  }
  const root = path.resolve(workDir);
  for (const scene of value.scenes) {
    const audio = path.resolve(root, scene.audio_path);
    if (path.relative(root, audio).startsWith("..")) {
      throw new Error("Scene audio must remain inside the video work directory.");
    }
  }
  return value;
}
export function overlayModel(caption, callout = "") {
  return { caption: String(caption), callout: String(callout) };
}
export function sceneDeadline(scene) { return scene.start_ms + scene.duration_ms; }
```

Reject absolute media paths outside the supplied work directory, duplicate cue IDs, non-monotonic cues, captions over 96 characters, and totals above 175,000 ms.

- [ ] **Step 4: Run GREEN pure tests**

```powershell
node --test scripts/video/capture_contract.test.mjs
```

Expected: all pass.

- [ ] **Step 5: Implement the browser recorder**

The CLI is:

```text
node scripts/video/capture_demo.mjs --base-url https://changesafe-competition.onrender.com --timing <timing.json> --work-dir <.video-work>
```

Implement these fail-closed phases:

1. Preflight `/healthz`, `/api/public-config`, and `/api/schema-fields`; require health `ok`, mode `replay`, all mutation and warehouse flags false, provenance `snapshot`, and exactly 55 fields.
2. Launch Chromium headless with viewport/video size 1920×1080, device scale factor 1, and `recordVideo` to the supplied work directory.
3. Fail on any page error or console error.
4. Add a fixed brand-safe caption/callout layer using DOM nodes and `textContent`. Use cream captions on a 92% opaque navy panel with teal top border and lime callout chip.
5. Record the title scene with `page.setContent()` and the ChangeSafe mark rendered as CSS geometry/text; do not depend on an external image.
6. Navigate to the hosted app only after preflight. Assert `Recorded DataHub schema`, `Preview only`, and `Production rows not queried`.
7. Select `cust_email` with keyboard interaction, enter `primary_email`, analyze, and wait for `awaiting approval`, seven artifact buttons, and `12 / 12`.
8. Scroll and pause on the persisted process, exact direct route, limited multi-hop route, six impact cards, factor ledger, generated shim bytes, and validation summary. Open the evidence drawer, close with Escape, and assert focus returns.
9. Use real New analysis flows to show `order_status` Remove and `order_total` Change type to `VARCHAR(320)`. Capture only the field/operation-bound summary and evidence count for each.
10. Recreate the passing rename run, approve preview, assert `Preview ready`, `NOT WRITTEN — SNAPSHOT MODE`, and a `Download patch` link whose response is 200 and non-empty.
11. Render the closing card with hosted URL, repository URL, DataHub attribution, and `Evidence-bound. Fail-closed. Human-approved.`
12. For each scene, schedule timing-manifest captions and wait only until the exact scene deadline. Save a review PNG at the strongest frame.
13. Close the page/context before calling `video.saveAs()` and write a sanitized `capture-report.json` containing scene IDs, public URLs, assertion counts, video path, and empty browser-error arrays.

- [ ] **Step 6: Run capture tests and lint**

```powershell
node --test scripts/video/capture_contract.test.mjs
& 'C:\Users\harik\.cache\codex-runtimes\codex-primary-runtime\dependencies\bin\fallback\pnpm.cmd' --filter @changesafe/web lint
```

Expected: pass.

- [ ] **Step 7: Commit Task 3**

```powershell
git add scripts/video/capture_contract.mjs scripts/video/capture_contract.test.mjs scripts/video/capture_demo.mjs
git commit -m "feat: record asserted hosted demo scenes"
```

---

### Task 4: H.264/AAC composition and media verification

**Files:**
- Create: `scripts/video/compose_demo.py`
- Modify: `apps/api/tests/test_video_production.py`

**Interfaces:**
- Consumes: capture WebM, `timing.json`, scene MP3s, SRT, and `capture-report.json`.
- Produces: `changesafe-competition-demo.mp4`, `changesafe-video-poster.png`, and `changesafe-video-verification.json`.

- [ ] **Step 1: Add RED composition command tests**

Test the pure command builder:

```python
from dataclasses import replace


def test_compose_command_is_public_safe_and_submission_compatible(tmp_path: Path) -> None:
    timing = {
        "total_duration_ms": 162_000,
        "scenes": [
            {
                "scene_id": scene.scene_id,
                "start_ms": index * 18_000,
                "audio_path": str(tmp_path / f"{scene.scene_id}.mp3"),
            }
            for index, scene in enumerate(SCENES)
        ],
    }
    inputs = ComposeInputs(
        capture=tmp_path / "capture.webm",
        timing=timing,
        output=tmp_path / "changesafe-competition-demo.mp4",
    )
    command = build_compose_command(Path("ffmpeg"), inputs)
    joined = " ".join(command)
    assert "libx264" in command
    assert "-pix_fmt yuv420p" in joined
    assert "-r 30" in joined
    assert "-c:a aac" in joined
    assert "-b:a 192k" in joined
    assert "-metadata title=ChangeSafe — Data contract change intelligence" in joined
    assert "token" not in joined.casefold()
    assert "private" not in joined.casefold()


def test_media_verification_rejects_wrong_codec_or_runtime() -> None:
    good = MediaProbe(
        duration_seconds=160.0,
        width=1920,
        height=1080,
        frame_rate=30.0,
        video_codec="h264",
        audio_codec="aac",
        file_size=20_000_000,
    )
    assert verify_media(replace(good, video_codec="vp8")) == ["video codec must be h264"]
    assert verify_media(replace(good, duration_seconds=176.0)) == ["duration must not exceed 175 seconds"]
```

- [ ] **Step 2: Run RED composition tests**

```powershell
& '.\.venv\Scripts\python.exe' -m pytest -q apps/api/tests/test_video_production.py -k "compose or media"
```

Expected: missing compose module or functions.

- [ ] **Step 3: Implement the composer**

Use `imageio_ffmpeg.get_ffmpeg_exe()` and first require encoder output to contain `libx264` and `aac`. Build an argument list, never a shell string.

Define the composition boundary explicitly:

```python
@dataclass(frozen=True)
class ComposeInputs:
    capture: Path
    timing: dict[str, object]
    output: Path


@dataclass(frozen=True)
class MediaProbe:
    duration_seconds: float
    width: int
    height: int
    frame_rate: float
    video_codec: str
    audio_codec: str
    file_size: int
```

For nine audio inputs, build one deterministic delay per scene:

```python
audio_filters = [
    f"[{index + 1}:a]adelay={scene['start_ms']}|{scene['start_ms']}[a{index}]"
    for index, scene in enumerate(inputs.timing["scenes"])
]
mix_inputs = "".join(f"[a{index}]" for index in range(len(audio_filters)))
filter_graph = ";".join(
    [
        *audio_filters,
        f"{mix_inputs}amix=inputs=9:duration=longest:normalize=0,"
        "alimiter=limit=0.95[aout]",
    ]
)
```

Map the WebM video and `[aout]`; scale/pad to 1920×1080, force 30 fps, encode `libx264` CRF 18 preset `medium`, `yuv420p`, AAC 192 kbps, and trim to `total_duration_ms`. Set only public metadata: title, artist `ChangeSafe`, comment `Recorded DataHub evidence; production rows not queried.`

After composition:

1. Run FFmpeg inspection and parse duration, video codec, audio codec, dimensions, frame rate, and stream presence.
2. Require duration 145–175 seconds, H.264, AAC, 1920×1080, 30 fps, and both streams.
3. Require file size between 1 MB and 250 MB.
4. Extract the poster at 14 seconds with a single 1920×1080 PNG frame.
5. Copy the SRT and script from the narration stage into the submission directory.
6. Merge the sanitized capture report and media facts into `changesafe-video-verification.json`.
7. Delete a partial MP4 if any validation fails.

- [ ] **Step 4: Run composition tests and Ruff**

```powershell
& '.\.venv\Scripts\python.exe' -m pytest -q apps/api/tests/test_video_production.py
& '.\.venv\Scripts\ruff.exe' check scripts/video apps/api/tests/test_video_production.py
```

Expected: all pass.

- [ ] **Step 5: Commit Task 4**

```powershell
git add scripts/video/compose_demo.py apps/api/tests/test_video_production.py
git commit -m "feat: compose and verify competition video"
```

---

### Task 5: One-command production runner and documentation

**Files:**
- Create: `scripts/video/run_demo_video.ps1`
- Create: `scripts/video/README.md`
- Modify: `.gitignore`
- Modify: `docs/demo-script.md`
- Modify: `docs/devpost-submission.md`

**Interfaces:**
- Consumes: all Task 1–4 CLIs.
- Produces: a single documented command that creates the complete local submission bundle without committing binaries.

- [ ] **Step 1: Add RED runner-contract tests**

Extend `test_video_production.py` to assert that the PowerShell source:

- sets `$ErrorActionPreference = 'Stop'`;
- uses the repository `.venv` Python and bundled Node/pnpm paths;
- installs only `scripts/video/requirements.txt`;
- runs narration, pure Node tests, browser capture, composition, Python tests, Ruff, and secret scan in that order;
- defaults output to `$HOME\Videos\ChangeSafe Submission`;
- never deletes outside `<output>\.video-work`;
- does not print environment variables.

- [ ] **Step 2: Run RED runner test**

```powershell
& '.\.venv\Scripts\python.exe' -m pytest -q apps/api/tests/test_video_production.py -k runner
```

Expected: failure because `run_demo_video.ps1` is absent.

- [ ] **Step 3: Implement the guarded runner**

Expose parameters:

```powershell
param(
  [string]$BaseUrl = 'https://changesafe-competition.onrender.com',
  [string]$OutputDir = (Join-Path $HOME 'Videos\ChangeSafe Submission'),
  [switch]$ReuseNarration
)
```

Resolve and verify that `.video-work` is a child of `OutputDir` before clearing only that directory. Create the output directory. Install pinned requirements into the existing project venv, run tests before production, run narration/capture/composition, rerun focused tests and secret scan, then print only the five public deliverable paths and verification summary.

- [ ] **Step 4: Update runbook and public copy**

Document the exact command:

```powershell
& '.\scripts\video\run_demo_video.ps1'
```

Update the old demo script to the approved 2:42 storyboard and permanent Render URL. Update Devpost submission links to:

```text
- Hosted app: https://changesafe-competition.onrender.com
- Source repository: https://github.com/marker2601/changesafe
- Demo video: generated locally as changesafe-competition-demo.mp4; upload publicly before submission
```

Add only these ignore entries:

```gitignore
.video-work/
video-output/
```

- [ ] **Step 5: Run focused and repository gates**

```powershell
& '.\.venv\Scripts\python.exe' -m pytest -q apps/api/tests/test_video_production.py
node --test scripts/video/capture_contract.test.mjs
& '.\.venv\Scripts\ruff.exe' check scripts/video apps/api/tests/test_video_production.py
& '.\.venv\Scripts\python.exe' scripts/check_secrets.py
git diff --check
```

Expected: all pass.

- [ ] **Step 6: Commit Task 5**

```powershell
git add .gitignore scripts/video/run_demo_video.ps1 scripts/video/README.md docs/demo-script.md docs/devpost-submission.md apps/api/tests/test_video_production.py
git commit -m "docs: add repeatable competition video production"
```

---

### Task 6: Produce, inspect, and package the actual video

**Files:**
- Generate outside Git: `%USERPROFILE%\Videos\ChangeSafe Submission\changesafe-competition-demo.mp4`
- Generate outside Git: `%USERPROFILE%\Videos\ChangeSafe Submission\changesafe-competition-demo.srt`
- Generate outside Git: `%USERPROFILE%\Videos\ChangeSafe Submission\changesafe-video-script.md`
- Generate outside Git: `%USERPROFILE%\Videos\ChangeSafe Submission\changesafe-video-poster.png`
- Generate outside Git: `%USERPROFILE%\Videos\ChangeSafe Submission\changesafe-video-verification.json`

**Interfaces:**
- Consumes: the guarded production runner and permanent hosted app.
- Produces: the final user-reviewable media bundle.

- [ ] **Step 1: Run the full production pipeline**

```powershell
& '.\scripts\video\run_demo_video.ps1'
```

Expected: five public deliverables are created; no tracked binary appears in `git status`.

- [ ] **Step 2: Inspect every scene visually**

Open all nine `.video-work/review/<scene-id>.png` frames and the final poster. Check title-safe captions, cursor/callout placement, readable generated SQL, absence of browser/account chrome, correct evidence labels, no secret or private detail, and brand consistency. Any failed frame requires recapture; do not conceal it in composition.

- [ ] **Step 3: Review audio and synchronization**

Listen to the complete MP4 at normal laptop volume. Confirm the generated voice is intelligible, not clipped, and aligned with each scene. Confirm captions convey the same meaning as the spoken line and do not remain on screen after the corresponding narration.

- [ ] **Step 4: Verify the actual media contract**

Read `changesafe-video-verification.json` and independently run the composer `--verify-only` mode. Require:

```text
duration_seconds: 145–175
width: 1920
height: 1080
frame_rate: 30
video_codec: h264
audio_codec: aac
browser_console_errors: []
browser_page_errors: []
schema_field_count: 55
artifact_count: 7
blocking_checks: 12
patch_status: 200
```

- [ ] **Step 5: Run the final source release gate**

```powershell
& '.\.venv\Scripts\python.exe' -m pytest -q
& '.\.venv\Scripts\ruff.exe' check .
& '.\.venv\Scripts\mypy.exe' apps/api/src/changesafe
& '.\.venv\Scripts\python.exe' scripts/regenerate_examples.py --check
& '.\.venv\Scripts\python.exe' scripts/check_secrets.py
git diff --check
git status --short --branch
```

Expected: all project gates pass and the worktree contains no untracked binary media.

- [ ] **Step 6: Commit any final script-only correction and push master**

If visual/audio review required source-script adjustments, commit only those text/tooling changes after rerunning their focused tests:

```powershell
git add scripts/video apps/api/tests/test_video_production.py docs/demo-script.md docs/devpost-submission.md .gitignore
git commit -m "fix: polish competition demo video"
git push origin master
```

If no correction was needed, push the existing Task 1–5 commits:

```powershell
git push origin master
```

- [ ] **Step 7: Hand off public upload instructions**

Provide the user the absolute MP4, SRT, script, poster, and verification-report paths. Recommend uploading the MP4 to YouTube as **Public** (not Private), applying the generated poster, adding the SRT captions, testing the link in a signed-out window, and then placing that public URL into Devpost before final submission.
