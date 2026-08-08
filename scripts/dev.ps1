param(
    [string]$EnvFile = "C:\Users\harik\ChangeSafe\private\changesafe.env"
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$python = Get-Command python -ErrorAction SilentlyContinue
$pnpm = Get-Command pnpm -ErrorAction SilentlyContinue

if (-not $python) {
    $pythonPath = "C:\Users\harik\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
} else {
    $pythonPath = $python.Source
}

if (-not $pnpm) {
    $pnpmPath = "C:\Users\harik\.cache\codex-runtimes\codex-primary-runtime\dependencies\bin\fallback\pnpm.cmd"
} else {
    $pnpmPath = $pnpm.Source
}

if (Test-Path -LiteralPath $EnvFile) {
    $env:CHANGESAFE_ENV_FILE = $EnvFile
}

$backend = Start-Process -FilePath $pythonPath -ArgumentList @(
    "-m", "uvicorn", "changesafe.main:app", "--reload", "--port", "8000",
    "--app-dir", "apps/api/src"
) -WorkingDirectory $repoRoot -WindowStyle Hidden -PassThru

try {
    & $pnpmPath --dir $repoRoot dev
} finally {
    if (-not $backend.HasExited) {
        Stop-Process -Id $backend.Id
    }
}
