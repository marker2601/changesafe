param(
    [string]$EnvFile = "C:\Users\harik\ChangeSafe\private\changesafe.env",
    [int]$ApiPort = 8000,
    [int]$WebPort = 5173
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"
$python = Get-Command python -ErrorAction SilentlyContinue
$pnpm = Get-Command pnpm -ErrorAction SilentlyContinue

if (Test-Path -LiteralPath $venvPython) {
    $pythonPath = $venvPython
} elseif (-not $python) {
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
$env:CHANGESAFE_API_TARGET = "http://127.0.0.1:$ApiPort"

$backend = Start-Process -FilePath $pythonPath -ArgumentList @(
    "-m", "uvicorn", "changesafe.main:app", "--reload", "--port", "$ApiPort",
    "--app-dir", "apps/api/src"
) -WorkingDirectory $repoRoot -WindowStyle Hidden -PassThru

try {
    & $pnpmPath --dir $repoRoot --filter "@changesafe/web" dev -- --host 127.0.0.1 --port $WebPort
} finally {
    if (-not $backend.HasExited) {
        Stop-Process -Id $backend.Id
    }
}
