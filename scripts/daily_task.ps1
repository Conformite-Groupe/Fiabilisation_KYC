<#
  COMPLIANCE BOA GROUP - Fiabilisation KYC
  Traitements quotidiens (tache planifiee).

  Enchaine :
    1. redemarrage cible du serveur Django (processus detache, sans console)
    2. manage.py run_daily_jobs  -> Script_V3.r, imports, taux de qualite,
       caches, appreciations, rappels DATEREV + rapport email

  Garanties :
    - aucune fenetre cmd creee (donc plus d'empilement de fenetres)
    - un seul processus python tue : celui du serveur, via django.pid
    - verrou anti-chevauchement
    - code de retour reel remonte a l'Ordonnanceur de taches
    - log unique horodate + rotation
#>
[CmdletBinding()]
param(
    [string]$ProjectRoot = "C:\Fiabilisation KYC\Python\Fiabilisation_kyc",
    [string]$BindAddress = "10.170.82.20:8080",
    [string[]]$JobArgs   = @(),
    [switch]$SkipWeb
)

$ErrorActionPreference = "Stop"
$exitCode = 0

$Python  = Join-Path $ProjectRoot "venv\Scripts\python.exe"
$LogDir  = Join-Path $ProjectRoot "logs"
$LogFile = Join-Path $LogDir "daily_task.log"
$LockFile = Join-Path $ProjectRoot "daily_task.lock"

function Write-Log {
    param([string]$Message)
    $line = "{0}  {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    Write-Output $line
    Add-Content -Path $LogFile -Value $line -Encoding utf8
}

# --- Controles prealables ----------------------------------------------------
if (-not (Test-Path (Join-Path $ProjectRoot "manage.py"))) {
    Write-Error "Projet introuvable : $ProjectRoot"; exit 2
}
if (-not (Test-Path $Python)) {
    Write-Error "Interpreteur introuvable : $Python"; exit 2
}
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
if ((Test-Path $LogFile) -and ((Get-Item $LogFile).Length -gt 20MB)) {
    Move-Item $LogFile "$LogFile.1" -Force
}

# --- Verrou anti-chevauchement ----------------------------------------------
$lock = $null
try {
    $lock = [System.IO.File]::Open($LockFile, 'OpenOrCreate', 'ReadWrite', 'None')
} catch {
    Write-Log "[ABANDON] Une execution est deja en cours (verrou $LockFile)."
    exit 3
}

try {
    Write-Log "===================================================================="
    Write-Log "Demarrage des traitements quotidiens"

    # --- 1. Serveur Django ---------------------------------------------------
    if (-not $SkipWeb) {
        Write-Log "[START] Redemarrage du serveur Django"
        try {
            & (Join-Path $PSScriptRoot "restart_django.ps1") -ProjectRoot $ProjectRoot -BindAddress $BindAddress |
                ForEach-Object { Write-Log "        $_" }
            Write-Log "[OK] Serveur Django en ligne sur $BindAddress"
        } catch {
            Write-Log "[ECHEC] Redemarrage Django : $($_.Exception.Message)"
            $exitCode = 4
        }
    }

    # --- 2. Traitements metier ----------------------------------------------
    # run_daily_jobs ecrit son propre log detaille (logs\run_daily_jobs_*.log)
    # et envoie le rapport de supervision par email.
    Write-Log "[START] manage.py run_daily_jobs $($JobArgs -join ' ')"
    Push-Location $ProjectRoot
    try {
        $args = @("-X", "utf8", "manage.py", "run_daily_jobs") + $JobArgs
        & $Python @args 2>&1 | ForEach-Object { Add-Content -Path $LogFile -Value $_ -Encoding utf8 }
        $rc = $LASTEXITCODE
    } finally {
        Pop-Location
    }

    if ($rc -eq 0) {
        Write-Log "[OK] Traitements quotidiens termines"
    } else {
        Write-Log "[ECHEC] run_daily_jobs - code de retour $rc"
        $exitCode = $rc
    }
}
finally {
    Write-Log "Fin des traitements (code $exitCode)"
    if ($lock) { $lock.Close(); $lock.Dispose() }
    Remove-Item $LockFile -Force -ErrorAction SilentlyContinue
}

exit $exitCode
