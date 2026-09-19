@echo off
rem push.cmd - double-click friendly wrapper for push.ps1 (ASCII only).
rem Commit local changes and push them to the working branch.
rem Put this file in the repo root next to the .ps1 scripts and double-click it.
setlocal
set "PS1=%~dp0push.ps1"
if not exist "%PS1%" (
  echo [ERROR] push.ps1 not found next to this file.
  echo         Run this from the cloned repo folder, e.g. E:\0zhongqi\zhongqi-arena
  pause
  exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%PS1%" %*
set RC=%ERRORLEVEL%
echo.
echo [exit code %RC%]
echo %cmdcmdline% | find /i "%~nx0" >nul && pause
exit /b %RC%
