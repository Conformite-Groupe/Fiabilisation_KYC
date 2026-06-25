param(
    [int]$Users = 20,
    [int]$Rules = 20,
    [string]$Python = "python",
    [string]$ExtraArgs = ""
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$LogDir = Join-Path $ProjectRoot "logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$LogFile = Join-Path $LogDir ("warm_ui_caches_{0}.log" -f (Get-Date -Format "yyyyMMdd"))

Set-Location $ProjectRoot
$startedAt = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
"[$startedAt] Demarrage warm_ui_caches --users $Users --rules $Rules $ExtraArgs" | Tee-Object -FilePath $LogFile -Append

$commandArgs = @("manage.py", "warm_ui_caches", "--users", "$Users", "--rules", "$Rules")
if ($ExtraArgs.Trim()) {
    $commandArgs += ($ExtraArgs -split "\s+")
}

& $Python @commandArgs 2>&1 | Tee-Object -FilePath $LogFile -Append
$exitCode = $LASTEXITCODE

$endedAt = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
"[$endedAt] Fin warm_ui_caches exit=$exitCode" | Tee-Object -FilePath $LogFile -Append
exit $exitCode
