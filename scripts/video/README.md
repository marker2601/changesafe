# ChangeSafe competition video production

This directory creates the public ChangeSafe demo from the permanent hosted application. The workflow is asserted, captioned, and fail-closed: it refuses an unexpected host, live/mutation configuration, schema count, browser error, artifact count, validation result, media codec, duration, or resolution.

## One command

From the repository root on the configured Windows workstation:

```powershell
& '.\scripts\video\run_demo_video.ps1'
```

The command creates these untracked deliverables in `%USERPROFILE%\Videos\ChangeSafe Submission`:

- `changesafe-competition-demo.mp4`
- `changesafe-competition-demo.srt`
- `changesafe-video-script.md`
- `changesafe-video-poster.png`
- `changesafe-video-verification.json`

The MP4 contract is 145–175 seconds, H.264/AAC, 1920×1080, 30 fps, and below 250 MB. The current approved render is 173.93 seconds and approximately 19 MB.

## Narration provider

Credential-free generation uses the pinned Edge TTS dependency. For the higher-quality ElevenLabs render, create this private file outside the checkout:

```text
C:\Users\harik\.changesafe-private\video.env
```

```dotenv
ELEVENLABS_API_KEY=
ELEVENLABS_VOICE_ID=
```

Grant the key only the ElevenLabs **Text to Speech** permission and use a low character quota. A voice ID is about 20 characters; the ElevenLabs key ID is not a voice ID. If the supplied voice value is absent or invalid, the renderer uses the documented stock George voice. If ElevenLabs is unavailable, narration falls back safely without exposing provider errors or the key.

Never place credentials in the repository, output directory, command line, capture report, or verification JSON.

## Reusing narration

To keep an already approved voice render while recapturing the hosted browser flow:

```powershell
& '.\scripts\video\run_demo_video.ps1' -ReuseNarration
```

The runner can clear only `<output>\.video-work`; it never deletes the output directory or tracked files. The final files are outside Git, while the pure contracts and production scripts remain reviewable in this repository.

## What the recorder proves

- the permanent origin responds at `/healthz`, `/api/public-config`, and `/api/schema-fields`;
- replay provenance is `snapshot`, the schema contains exactly 55 fields, and all mutation/warehouse flags are off;
- `cust_email` rename, `order_status` removal, and `order_total` type change use real keyboard-driven field selection;
- the primary run produces six impact classifications, seven artifact files, and 12 / 12 blocking checks;
- exact lineage evidence opens in the accessible drawer and returns focus on Escape;
- approval produces a non-mutating receipt and non-empty patch;
- browser console and page error lists stay empty.

The final video truthfully says **Recorded DataHub evidence**, **Preview only**, and **Production rows not queried**.
