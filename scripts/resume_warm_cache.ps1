param(
    [int]$InitialDelayMinutes = 20,
    [int]$Passes = 3,
    [int]$BetweenPassMinutes = 30,
    [double]$RequestDelaySeconds = 5.0
)

$ErrorActionPreference = "Continue"
$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
$logPath = Join-Path $projectRoot "data\warm-cache-resume.log"

if (-not (Test-Path -LiteralPath $python)) {
    throw "Project Python environment not found: $python"
}

Set-Location -LiteralPath $projectRoot
New-Item -ItemType Directory -Path (Split-Path -Parent $logPath) -Force | Out-Null

"[$(Get-Date -Format o)] Waiting $InitialDelayMinutes minute(s) before retrying." |
    Tee-Object -FilePath $logPath -Append
Start-Sleep -Seconds ($InitialDelayMinutes * 60)

for ($pass = 1; $pass -le $Passes; $pass++) {
    "[$(Get-Date -Format o)] Starting cache pass $pass of $Passes." |
        Tee-Object -FilePath $logPath -Append

    & $python -m onenote_indexer warm-cache `
        --max-pages 1000 `
        --max-mb 10000 `
        --delay $RequestDelaySeconds 2>&1 |
        Tee-Object -FilePath $logPath -Append

    "[$(Get-Date -Format o)] Finished cache pass $pass of $Passes (exit code $LASTEXITCODE)." |
        Tee-Object -FilePath $logPath -Append

    if ($pass -lt $Passes) {
        Start-Sleep -Seconds ($BetweenPassMinutes * 60)
    }
}
