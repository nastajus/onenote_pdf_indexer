param(
    [string]$Message = "Codex checkpoint"
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
    exit 0
}

& $Git commit -m $Message | Out-Host
