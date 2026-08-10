param(
    [string]$BaseUrl = 'https://changesafe-competition.onrender.com',
    [string]$OutputDir = (Join-Path $HOME 'Videos\ChangeSafe Submission'),
    [switch]$ReuseNarration
)

$ErrorActionPreference = 'Stop'
$RepoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$Python = Join-Path $RepoRoot '.venv\Scripts\python.exe'
$Node = 'C:\Users\harik\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe'
$Pnpm = 'C:\Users\harik\.cache\codex-runtimes\codex-primary-runtime\dependencies\bin\fallback\pnpm.cmd'
$OutputDir = [System.IO.Path]::GetFullPath($OutputDir)
$WorkDir = [System.IO.Path]::GetFullPath((Join-Path $OutputDir '.video-work'))
$OutputPrefix = $OutputDir.TrimEnd('\', '/') + [System.IO.Path]::DirectorySeparatorChar

if (-not $WorkDir.StartsWith($OutputPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw 'The video work directory must remain inside the output directory.'
}
foreach ($required in @($Python, $Node, $Pnpm)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "Required bundled runtime is unavailable: $required"
    }
}

New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
if (-not $ReuseNarration -and (Test-Path -LiteralPath $WorkDir)) {
    Remove-Item -LiteralPath $WorkDir -Recurse -Force
}
New-Item -ItemType Directory -Path $WorkDir -Force | Out-Null

$Timing = Join-Path $WorkDir 'timing.json'
$CaptureDir = Join-Path $WorkDir 'capture'
$Capture = Join-Path $CaptureDir 'changesafe-demo.webm'
$Closing = Join-Path $CaptureDir 'closing.png'
$CaptureReport = Join-Path $CaptureDir 'capture-report.json'
$Video = Join-Path $OutputDir 'changesafe-competition-demo.mp4'
$Poster = Join-Path $OutputDir 'changesafe-video-poster.png'
$Verification = Join-Path $OutputDir 'changesafe-video-verification.json'

Push-Location $RepoRoot
try {
    & $Python -m pip install -r scripts/video/requirements.txt
    if (-not $ReuseNarration -or -not (Test-Path -LiteralPath $Timing)) {
        & $Python -m scripts.video.narration --output-dir $OutputDir
    }
    & $Node --test scripts/video/capture_contract.test.mjs
    & $Node scripts/video/capture_demo.mjs --base-url $BaseUrl --timing $Timing --work-dir $WorkDir
    & $Python -m scripts.video.compose_demo --capture $Capture --timing $Timing --work-dir $WorkDir --closing-frame $Closing --capture-report $CaptureReport --output $Video --poster $Poster --verification $Verification
    & $Python -m pytest -q apps/api/tests/test_video_production.py
    & $Python -m ruff check scripts/video apps/api/tests/test_video_production.py
    & $Python scripts/check_secrets.py
}
finally {
    Pop-Location
}

$Summary = Get-Content -LiteralPath $Verification -Raw | ConvertFrom-Json
Write-Host 'ChangeSafe competition video bundle:'
Write-Host "  $Video"
Write-Host "  $(Join-Path $OutputDir 'changesafe-competition-demo.srt')"
Write-Host "  $(Join-Path $OutputDir 'changesafe-video-script.md')"
Write-Host "  $Poster"
Write-Host "  $Verification"
Write-Host ("Verified: {0:N2}s, {1}x{2}, {3} fps, {4}/{5}" -f `
    $Summary.media.duration_seconds,
    $Summary.media.width,
    $Summary.media.height,
    $Summary.media.frame_rate,
    $Summary.media.video_codec,
    $Summary.media.audio_codec)
