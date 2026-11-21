param(
    [string]$Message = "Codex checkpoint",
    [switch]$NoPush
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $ProjectRoot

$GitCommand = Get-Command git -ErrorAction SilentlyContinue
if ($GitCommand) {
    $Git = $GitCommand.Source
} elseif (Test-Path "C:\Program Files\Git\cmd\git.exe") {
    $Git = "C:\Program Files\Git\cmd\git.exe"
} elseif (Test-Path "C:\Program Files\Git\bin\git.exe") {
    $Git = "C:\Program Files\Git\bin\git.exe"
} else {
    Write-Host "Git is not installed or is not on PATH. Install Git for Windows, then rerun this script."
    exit 2
}

if (-not (Test-Path ".git")) {
    & $Git init | Out-Host
}

$Name = & $Git config user.name
$Email = & $Git config user.email
if (-not $Name) {
    & $Git config user.name "Codex"
}
if (-not $Email) {
    & $Git config user.email "codex@local"
}

& $Git add -A | Out-Host

$Status = & $Git status --porcelain
if (-not $Status) {
    Write-Host "No project changes to commit."
} else {
    & $Git commit -m $Message | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "Git commit failed with exit code $LASTEXITCODE."
    }
}

if ($NoPush) {
    Write-Host "Skipping push because -NoPush was specified."
    exit 0
}

$Origin = & $Git remote get-url origin 2>$null
if (-not $Origin) {
    throw "No origin remote is configured; cannot push the checkpoint."
}

$Branch = & $Git branch --show-current
if (-not $Branch) {
    throw "The repository is in detached HEAD state; cannot choose a branch to push."
}

& $Git push --set-upstream origin $Branch | Out-Host
if ($LASTEXITCODE -ne 0) {
    throw "Git push failed with exit code $LASTEXITCODE."
}

Write-Host "Checkpoint pushed to origin/$Branch."
