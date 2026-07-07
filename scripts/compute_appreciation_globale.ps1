param(
    [string]$Python = "python",
    [string]$ExtraArgs = ""
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$LogDir = Join-Path $ProjectRoot "logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$LogFile = Join-Path $LogDir ("appreciation_globale_{0}.log" -f (Get-Date -Format "yyyyMMdd"))

Set-Location $ProjectRoot
$startedAt = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
"[$startedAt] Demarrage compute_appreciation_globale $ExtraArgs" | Tee-Object -FilePath $LogFile -Append

$commandArgs = @("manage.py", "compute_appreciation_globale")
if ($ExtraArgs.Trim()) {
    $commandArgs += ($ExtraArgs -split "\s+")
}

& $Python @commandArgs 2>&1 | Tee-Object -FilePath $LogFile -Append
$exitCode = $LASTEXITCODE

$endedAt = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
"[$endedAt] Fin compute_appreciation_globale exit=$exitCode" | Tee-Object -FilePath $LogFile -Append
exit $exitCode
