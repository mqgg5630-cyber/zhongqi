@echo off
rem reclone.cmd - double-click friendly wrapper for reclone.ps1 (ASCII only).
rem Double-click: clones the repo into a NEW sibling folder (..\<repo>-arena)
rem and leaves the folder you double-clicked in completely untouched.
rem Pass a target with:  reclone.cmd -Path E:\0zhongqi\zhongqi-arena
setlocal
set "PS1=%~dp0reclone.ps1"
if not exist "%PS1%" (
  echo [ERROR] reclone.ps1 not found next to this file.
  echo         Run this from inside the cloned repo folder.
  pause
  exit /b 1
)
if "%*"=="" (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%PS1%"
) else (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%PS1%" %*
)
set RC=%ERRORLEVEL%
echo.
echo [exit code %RC%]
echo %cmdcmdline% | find /i "%~nx0" >nul && pause
exit /b %RC%
