param(
    # Nombre d'utilisateurs representatifs (scopes) a prechauffer.
    [int]$Users = 20,
    # Nombre de workers paralleles. 6 = bon compromis sur 8 coeurs.
    [int]$Workers = 6,
    # Modales /non_anom par regle : 0 = aucune (poste le plus lourd, desactive
    # par defaut pour la vitesse). Mettre >0 seulement si vous en avez besoin.
    [int]$Rules = 0,
    # Python du venv du projet par defaut.
    [string]$Python = ".\venv\Scripts\python.exe"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

$LogDir = Join-Path $ProjectRoot "logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"

$startedAt = Get-Date
Write-Host "[$($startedAt.ToString('HH:mm:ss'))] Prechauffage RAPIDE : $Workers workers paralleles (par utilisateur), --users $Users --rules $Rules"

# Chaque worker traite un slice i/N des utilisateurs sur TOUS les blocs.
# Le travail lourd (dashboards, quality par scope) se repartit sur les coeurs.
$jobs = 1..$Workers | ForEach-Object {
    $i = $_
    $log = Join-Path $LogDir ("warm_w{0}of{1}_{2}.log" -f $i, $Workers, $stamp)
    Start-Job -Name "w$i" -ScriptBlock {
        param($root, $py, $users, $rules, $slice, $log)
        Set-Location $root
        & $py "manage.py" "warm_ui_caches" "--users" "$users" "--rules" "$rules" "--slice" $slice *>&1 |
            Tee-Object -FilePath $log
        exit $LASTEXITCODE
    } -ArgumentList $ProjectRoot, $Python, $Users, $Rules, "$i/$Workers", $log
}

Write-Host "Workers lances : $($jobs.Name -join ', '). Attente..."
$jobs | Wait-Job | Out-Null

$allOk = $true
foreach ($j in $jobs) {
    Receive-Job $j | Out-Null
    $ok = if ($j.State -eq 'Completed') { "OK" } else { $allOk = $false; "ECHEC ($($j.State))" }
    Write-Host "  - $($j.Name) : $ok"
}
$jobs | Remove-Job

$elapsed = (Get-Date) - $startedAt
$status = if ($allOk) { "SUCCES" } else { "AVEC ERREURS" }
Write-Host ("[{0}] Termine ({1}) en {2:N1} s ({3:N1} min)" -f (Get-Date -Format 'HH:mm:ss'), $status, $elapsed.TotalSeconds, $elapsed.TotalMinutes)
