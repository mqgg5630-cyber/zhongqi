@echo off
rem where.cmd - double-click friendly wrapper for where.ps1 (ASCII only).
rem Which folder is which: repo path, branch, config branch, latest commit,
rem download folder. Prints this folder and (always) every sibling clone,
rem so you can see which one belongs to your session branch.
setlocal
set "PS1=%~dp0where.ps1"
if not exist "%PS1%" (
  echo [ERROR] where.ps1 not found next to this file.
  echo         Run this from inside the cloned repo folder.
  pause
  exit /b 1
)
if "%*"=="" (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%PS1%" -All
) else (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%PS1%" %*
)
set RC=%ERRORLEVEL%
echo.
echo [exit code %RC%]
echo %cmdcmdline% | find /i "%~nx0" >nul && pause
exit /b %RC%
