param(
    [string]$Python = "python",
    [string]$ExtraArgs = ""
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$LogDir = Join-Path $ProjectRoot "logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$LogFile = Join-Path $LogDir ("daily_jobs_{0}.log" -f (Get-Date -Format "yyyyMMdd"))

Set-Location $ProjectRoot
$startedAt = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
"[$startedAt] Demarrage run_daily_jobs $ExtraArgs" | Tee-Object -FilePath $LogFile -Append

$commandArgs = @("manage.py", "run_daily_jobs")
if ($ExtraArgs.Trim()) {
    $commandArgs += ($ExtraArgs -split "\s+")
}

& $Python @commandArgs 2>&1 | Tee-Object -FilePath $LogFile -Append
$exitCode = $LASTEXITCODE

$endedAt = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
"[$endedAt] Fin run_daily_jobs exit=$exitCode" | Tee-Object -FilePath $LogFile -Append
exit $exitCode
