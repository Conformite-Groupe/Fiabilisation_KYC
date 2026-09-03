@echo off
REM =====================================================================
REM  COMPLIANCE BOA GROUP - Fiabilisation KYC
REM  Point d'entree UNIQUE de la tache planifiee quotidienne.
REM  Ne fait que deleguer a daily_task.ps1 : aucune fenetre residuelle.
REM =====================================================================
powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "%~dp0daily_task.ps1" %*
exit /b %ERRORLEVEL%
