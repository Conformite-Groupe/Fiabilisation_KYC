@echo off
setlocal EnableExtensions
chcp 65001 >nul
title COMPLIANCE BOA GROUP - Fiabilisation KYC
color 0A

REM ==================================================================
REM  COMPLIANCE BOA GROUP - Fiabilisation KYC
REM  Traitements quotidiens - concu pour le Planificateur de taches.
REM  Aucune fenetre laissee ouverte. Tout est journalise.
REM ==================================================================

set "DJANGO_DIR=C:\Fiabilisation KYC\Python\Fiabilisation_kyc"
set "DJANGO_HOST=10.170.82.20:8080"
set "R_DIR=C:\Fiabilisation KYC\R"
set "R_SCRIPT=script_V3.R"
set "RETENTION_DAYS=30"
set "BOOT_WAIT=20"

set "PY=%DJANGO_DIR%\venv\Scripts\python.exe"
set "LOGDIR=%DJANGO_DIR%\logs"

for /f %%I in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd"') do set "DAY=%%I"
if not exist "%LOGDIR%" mkdir "%LOGDIR%" >nul 2>&1
set "LOG=%LOGDIR%\daily_%DAY%.log"
set "LOCKDIR=%LOGDIR%\daily.lock.d"
set "STALE_HOURS=8"

REM  Le log du jour peut etre verrouille par un processus d'un run precedent.
REM  On teste l'acces AVANT d'ecrire : cmd ne renvoie pas d'errorlevel sur un
REM  echec d'ouverture de redirection, la sonde doit donc etre externe.
for /f %%R in ('powershell -NoProfile -Command "Get-Date -Format HHmmss"') do set "RUNID=%%R"
set "LOGOK="
for /f %%A in ('powershell -NoProfile -Command "try { $f=[IO.File]::Open(\"%LOG%\",'Append','Write','ReadWrite'); $f.Close(); 'ok' } catch { 'ko' }"') do set "LOGOK=%%A"
if /i "%LOGOK%"=="ok" goto :log_pret
set "LOG=%LOGDIR%\daily_%DAY%_%RUNID%.log"
echo.
echo  [INFO] Le log du jour est verrouille par un autre processus.
echo         Journalisation basculee vers : %LOG%
echo.
:log_pret

set "RC_R=0"
set "RC_PY=0"
set "RC_FINAL=0"

REM --- Banniere (console uniquement, jamais dans le log) ---------------
call :banner

REM --- Controle prealable : le dossier de logs doit etre accessible ----
if not exist "%LOGDIR%" (
    echo [ECHEC] Dossier de logs introuvable et impossible a creer :
    echo         %LOGDIR%
    echo         Verifiez la variable DJANGO_DIR en tete de ce fichier.
    echo.
    if defined UI pause
    exit /b 3
)

REM --- Verrou : empeche deux executions simultanees -------------------
REM  On utilise un DOSSIER, pas un fichier ouvert : mkdir est atomique et
REM  ne cree aucun descripteur. Un descripteur (9>fichier) serait herite
REM  par le processus Django lance a l'etape 0, qui garderait le verrou
REM  ouvert toute la journee et bloquerait tous les lancements suivants.
mkdir "%LOCKDIR%" 2>nul
if not errorlevel 1 goto :verrou_pris

REM  Verrou deja present : est-il perime (run precedent interrompu) ?
set "PERIME="
for /f %%S in ('powershell -NoProfile -Command "if ((Get-Date) - (Get-Item '%LOCKDIR%').CreationTime -gt [TimeSpan]::FromHours(%STALE_HOURS%)) { 'oui' } else { 'non' }"') do set "PERIME=%%S"
if /i "%PERIME%"=="oui" (
    echo  [INFO] Verrou datant de plus de %STALE_HOURS%h - run precedent interrompu.
    echo         Reprise du verrou.
    rmdir /s /q "%LOCKDIR%" 2>nul
    mkdir "%LOCKDIR%" 2>nul
    if not errorlevel 1 goto :verrou_pris
)

echo.
echo  [ABANDON] Une execution est deja en cours - rien n'a ete lance.
echo            Verrou : %LOCKDIR%
echo            S'il ne reste aucun traitement actif, supprimez ce dossier.
echo.
>>"%LOGDIR%\daily_abandons.log" echo [%DAY% %TIME%] [ABANDON] Une execution est deja en cours.
if defined UI pause
exit /b 2

:verrou_pris
call :main
rmdir /s /q "%LOCKDIR%" 2>nul
exit /b %RC_FINAL%


REM ====================== CORPS PRINCIPAL ============================
:main
call :log "=================================================================="
call :log "[START] Traitements quotidiens KYC"

REM --- Etape 0 : redemarrage du serveur Django ------------------------
call :log "[0] Arret du serveur Django (processus runserver uniquement)..."
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -like '*manage.py*runserver*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }" >>"%LOG%" 2>&1

if not exist "%PY%" call :log "[ECHEC] Python introuvable : %PY%" & set "RC_FINAL=1" & goto :skip_django_start
call :log "[0] Lancement du serveur Django sur %DJANGO_HOST%..."
REM  IMPORTANT : ne JAMAIS rediriger cette ligne vers %LOG%. Le processus
REM  Django fils heriterait du handle et garderait le log verrouille toute
REM  la journee. Les sorties du serveur vont dans django_out/err.log.
powershell -NoProfile -Command "Start-Process -FilePath '%PY%' -ArgumentList 'manage.py','runserver','%DJANGO_HOST%','--noreload' -WorkingDirectory '%DJANGO_DIR%' -WindowStyle Hidden -RedirectStandardOutput '%LOGDIR%\django_out.log' -RedirectStandardError '%LOGDIR%\django_err.log'" >nul 2>&1
if errorlevel 1 call :log "[ECHEC] Le serveur Django n'a pas pu demarrer." & set "RC_FINAL=1" & goto :skip_django_start
call :log "[OK] Serveur Django lance. Attente de %BOOT_WAIT%s."
powershell -NoProfile -Command "Start-Sleep -Seconds %BOOT_WAIT%"
:skip_django_start

REM --- Etape 1 : production des etats R --------------------------------
call :log "[1] Production des etats R (%R_SCRIPT%)..."
call :find_rscript
if not defined RSCRIPT call :log "[ECHEC] Rscript.exe introuvable - etape 1 ignoree." & set "RC_R=9" & goto :after_r
pushd "%R_DIR%"
"%RSCRIPT%" "%R_SCRIPT%" >>"%LOG%" 2>&1
call :setrc RC_R
popd
:after_r
if "%RC_R%"=="0" call :log "[OK] Etats R produits." & goto :step_django
call :log "[ECHEC] %R_SCRIPT% - code retour %RC_R%"
set "RC_FINAL=1"

REM --- Etapes 2 a 8 : traitements Django -------------------------------
:step_django
call :log "[2-8] Traitements Django (run_daily_jobs)..."
pushd "%DJANGO_DIR%"
"%PY%" manage.py run_daily_jobs >>"%LOG%" 2>&1
call :setrc RC_PY
popd
if "%RC_PY%"=="0" call :log "[OK] Traitements Django termines." & goto :cleanup
call :log "[ECHEC] run_daily_jobs - code retour %RC_PY%"
set "RC_FINAL=1"

REM --- Purge des logs de plus de RETENTION_DAYS jours -------------------
:cleanup
powershell -NoProfile -Command "Get-ChildItem -Path '%LOGDIR%' -Filter 'daily_*.log' -ErrorAction SilentlyContinue | Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-%RETENTION_DAYS%) } | Remove-Item -Force -ErrorAction SilentlyContinue" >nul 2>&1

if not "%RC_FINAL%"=="0" goto :fin_erreur
call :log "[FIN] TOUS LES TRAITEMENTS TERMINES AVEC SUCCES"
if defined UI echo  ✔  TOUS LES TRAITEMENTS TERMINES AVEC SUCCES
exit /b 0
:fin_erreur
call :log "[FIN] DES ERREURS SONT SURVENUES - voir %LOG%"
if defined UI color 0C
if defined UI echo  ✖  DES ERREURS SONT SURVENUES
if defined UI if not "%RC_R%"=="0"  echo     - Etats R et traitements : voir "%LOG%"
if defined UI if not "%RC_PY%"=="0" echo     - Traitements Django    : voir "%LOG%"
exit /b 0


REM ====================== SOUS-ROUTINES ==============================
REM  UI n'est definie que s'il y a une vraie console (lancement manuel).
REM  En session 0 (tache planifiee sans ouverture de session) elle reste
REM  vide : ni banniere, ni couleurs, ni caracteres non-ASCII.
:banner
set "UI="
if not defined SESSIONNAME goto :eof
if /i "%SESSIONNAME%"=="Services" goto :eof
set "UI=1"
echo.
echo  ╔══════════════════════════════════════════════════════════════╗
echo  ║                                                              ║
echo  ║                  COMPLIANCE  BOA  GROUP                      ║
echo  ║                                                              ║
echo  ║             FIABILISATION DES DONNEES  KYC                   ║
echo  ║                                                              ║
echo  ╠══════════════════════════════════════════════════════════════╣
echo  ║   Traitements quotidiens :                                   ║
echo  ║     [0] Redemarrage du serveur Django                        ║
echo  ║     [1] Production des etats R     (script_V3.R)             ║
echo  ║     [2] Importation KYC            (import_kyc.py)           ║
echo  ║     [3] Importation evolutions     (import_premier.py)       ║
echo  ║     [4] Importation taux agents    (import_taux_agent.py)    ║
echo  ║     [5] Calcul des taux de qualite                           ║
echo  ║     [6] Prechauffe des caches                                ║
echo  ║     [7] Appreciations globales                               ║
echo  ║     [8] Rappels DATEREV + rapport email                      ║
echo  ╚══════════════════════════════════════════════════════════════╝
echo.
echo  Demarrage : %DAY% %TIME%
echo  ────────────────────────────────────────────────────────────────
echo.
goto :eof

:setrc
set "%~1=%ERRORLEVEL%"
exit /b 0

:find_rscript
set "RSCRIPT="
for /f "delims=" %%D in ('dir /b /o-n "C:\Program Files\R\R-*" 2^>nul') do (
    if not defined RSCRIPT if exist "C:\Program Files\R\%%D\bin\x64\Rscript.exe" set "RSCRIPT=C:\Program Files\R\%%D\bin\x64\Rscript.exe"
)
if defined RSCRIPT exit /b 0
for /f "delims=" %%P in ('where Rscript.exe 2^>nul') do if not defined RSCRIPT set "RSCRIPT=%%P"
exit /b 0

:log
REM  Le bloc parenthese est indispensable : un « 2>nul » nu ne masque pas
REM  l'echec d'ouverture de la redirection, cmd l'ecrit sur SA propre stderr.
( >>"%LOG%" echo [%DAY% %TIME%] %~1 ) 2>nul
echo [%DAY% %TIME%] %~1
exit /b 0
