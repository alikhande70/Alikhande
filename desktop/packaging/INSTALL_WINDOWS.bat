@echo off
setlocal

rem  Alikhande Scanner - one-click Windows install.
rem
rem  Double-click this file, or run it from a Command Prompt. It exists because
rem  build_windows.ps1 assumes you already know to open PowerShell, cd to the
rem  right directory, and pass -ExecutionPolicy Bypass. Getting any of those
rem  three wrong produces an error message that says nothing about the actual
rem  problem, so this wrapper does them for you and checks the one prerequisite
rem  it cannot install on your behalf.

title Alikhande Scanner - Windows install

rem  %~dp0 is this script's own folder (packaging\, with a trailing backslash);
rem  the project root is its parent. Resolving it this way means the script
rem  works no matter which directory it is launched from.
set "PACKAGING=%~dp0"
for %%I in ("%PACKAGING%..") do set "ROOT=%%~fI"

echo ==========================================================
echo   Alikhande Scanner - Windows install
echo ==========================================================
echo   project: %ROOT%
echo.

rem ---------------------------------------------------------------- Python
rem  Two launchers are worth trying. `py` is the version launcher that ships
rem  with the python.org installer and works even when PATH was never set up;
rem  `python` is the fallback. Neither is trusted on the strength of `where`
rem  alone, because the Microsoft Store plants a stub python.exe on PATH that
rem  does nothing but open the Store page. Running the version probe is what
rem  actually proves a usable interpreter is there.
set "PY="

call :probe py -3
if not errorlevel 1 set "PY=py -3"

if not defined PY (
    call :probe python
    if not errorlevel 1 set "PY=python"
)

if not defined PY goto :nopython

echo   python:  found via "%PY%"
echo.

rem ------------------------------------------------------------------ build
rem  -ExecutionPolicy Bypass applies to this one PowerShell process only. It
rem  does not change the machine's policy, which is why it is safe here.
rem  %* forwards any switches you passed, so -SkipTests still reaches the
rem  build script.
powershell -NoProfile -ExecutionPolicy Bypass -File "%PACKAGING%build_windows.ps1" %*
if errorlevel 1 goto :failed

echo.
echo ==========================================================
echo   Done. The application is at:
echo   %ROOT%\dist\AlikhandeScanner\AlikhandeScanner.exe
echo ==========================================================
echo.
echo   Make a Desktop shortcut to that .exe if you want one.
echo   Live trading additionally needs MetaTrader 5 running and
echo   logged in to a DEMO account, with Algo Trading enabled.
echo.
pause
exit /b 0

rem ------------------------------------------------------------- subroutine
rem  Exits 0 when %* is an interpreter of at least 3.10, non-zero otherwise -
rem  including when the command does not exist at all, which cmd reports as
rem  errorlevel 9009.
:probe
%* -c "import sys; sys.exit(0 if sys.version_info[:2] >= (3, 10) else 1)" >nul 2>&1
exit /b %errorlevel%

:nopython
echo   [X] Python 3.10 or newer was not found.
echo.
echo   Install it from https://www.python.org/downloads/windows/
echo   and tick "Add python.exe to PATH" on the first screen of the
echo   installer. That checkbox is off by default and is the single
echo   most common reason this step fails.
echo.
echo   Then run this file again.
echo.
pause
exit /b 1

:failed
echo.
echo   [X] The build did not finish. The error above is the real one -
echo       this line is only telling you where to look.
echo.
echo   Two failures are common and neither is a bug in the project:
echo     - the test suite failed, so packaging was refused on purpose;
echo     - pip could not reach the network to fetch PySide6.
echo.
pause
exit /b 1
