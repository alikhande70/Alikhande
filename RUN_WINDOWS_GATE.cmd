@echo off
setlocal
cd /d "%~dp0"
echo Alikhande Scanner v1.3 - Windows MetaEditor Gate
echo This step compiles only. It does NOT place trades.
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\run_windows_gate.ps1"
if errorlevel 1 (
  echo.
  echo GATE FAILED. Please send a screenshot of this window to GPT.
  pause
  exit /b 1
)
endlocal
