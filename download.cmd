@echo off
rem download.cmd - double-click friendly wrapper for download.ps1 (ASCII only).
rem Put this file in the repo root next to the .ps1 scripts and double-click it.
rem Bypasses the PowerShell execution policy, so it works on a fresh Windows.
setlocal
set "PS1=%~dp0download.ps1"
if not exist "%PS1%" (
  echo [ERROR] download.ps1 not found next to this file.
  echo         Run this from the cloned repo folder, e.g. E:\0zhongqi\zhongqi
  pause
  exit /b 1
)
set "ARGS=%*"
if "%ARGS%"=="" set "ARGS=-Set final"
powershell -NoProfile -ExecutionPolicy Bypass -File "%PS1%" %ARGS%
set RC=%ERRORLEVEL%
echo.
echo [exit code %RC%]
rem pause only when double-clicked from Explorer, not when called from a terminal
echo %cmdcmdline% | find /i "%~nx0" >nul && pause
exit /b %RC%
