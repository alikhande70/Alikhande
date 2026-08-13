@echo off
setlocal

rem  Alikhande Scanner - verify this machine can run it, and prove it.
rem
rem  Double-click this file. It changes nothing and installs nothing except the
rem  Python packages the application needs. It runs every check, writes the
rem  whole transcript to VERIFY-REPORT.txt beside itself, and prints it.
rem
rem  It exists because "it does not work" is not a report anybody can act on.
rem  The file it produces is.

title Alikhande Scanner - verification

set "PACKAGING=%~dp0"
for %%I in ("%PACKAGING%..") do set "ROOT=%%~fI"
set "REPORT=%ROOT%\VERIFY-REPORT.txt"

echo.
echo   Running checks. This takes a few minutes - the test suite is real.
echo   Everything is being written to:
echo     %REPORT%
echo.

rem  The whole body runs redirected, then the file is printed. cmd has no tee,
rem  and a `call :label > file` is the one construction that captures a block
rem  without repeating a redirect on every line.
call :body > "%REPORT%" 2>&1
type "%REPORT%"

echo.
echo ==========================================================
echo   Done. Send this file back if anything failed:
echo   %REPORT%
echo ==========================================================
echo.
pause
exit /b 0


:body
echo ==========================================================
echo   ALIKHANDE SCANNER - VERIFICATION REPORT
echo ==========================================================
echo   generated : %DATE% %TIME%
echo   folder    : %ROOT%
echo   computer  : %COMPUTERNAME%
echo   user      : %USERNAME%
echo.

echo -- [1/6] Windows version ---------------------------------
ver
echo.
wmic os get Caption,Version,OSArchitecture /value 2>nul | findstr /r "[a-zA-Z]"
echo.

echo -- [2/6] Python ------------------------------------------
rem  `where` alone is not enough: the Microsoft Store plants a stub python.exe
rem  on PATH that only opens the Store page. Running the interpreter is what
rem  actually proves one is there.
set "PY="
call :probe py -3
if not errorlevel 1 set "PY=py -3"
if not defined PY (
    call :probe python
    if not errorlevel 1 set "PY=python"
)

if not defined PY (
    echo   [X] FAIL - no Python 3.10+ found.
    echo.
    echo       Install from https://www.python.org/downloads/windows/
    echo       and tick "Add python.exe to PATH" on the first screen.
    echo       That checkbox is off by default and is the single most
    echo       common reason this step fails.
    echo.
    echo   VERDICT: cannot run. Fix Python first, then run this file again.
    exit /b 1
)

echo   launcher : %PY%
%PY% -c "import sys, platform; print('   version  :', sys.version.split()[0]); print('   build    :', platform.machine()); print('   exe      :', sys.executable)"
echo   [OK] Python is usable.
echo.

echo -- [3/6] Dependencies ------------------------------------
pushd "%ROOT%"
%PY% -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 (
    echo   [X] FAIL - pip could not install the dependencies.
    echo       Usually a network or proxy problem, not a bug in the project.
    popd
    exit /b 1
)
echo   [OK] Dependencies installed.
echo.

echo -- [4/6] Environment check (doctor) ----------------------
%PY% -m alikhande doctor
echo.

echo -- [5/6] Test suite --------------------------------------
rem  The real suite, not a subset. A green suite here is the strongest
rem  evidence available that this machine runs the application correctly.
%PY% -m unittest discover -s tests -t .
if errorlevel 1 (
    echo   [X] FAIL - tests did not pass on this machine.
    popd
    exit /b 1
)
echo   [OK] Test suite passed.
echo.

echo -- [6/6] Backtest smoke run ------------------------------
rem  Small on purpose. The point is that the pipeline runs end to end here,
rem  not to produce a result worth reading - the data is synthetic.
%PY% -m alikhande backtest --symbols EURUSD --h4-bars 400 --warmup 9900 --steps 300
if errorlevel 1 (
    echo   [X] FAIL - the backtest did not complete.
    popd
    exit /b 1
)
echo   [OK] Backtest completed.
popd
echo.

echo ==========================================================
echo   VERDICT: this computer can run Alikhande Scanner.
echo ==========================================================
echo.
echo   To start it:
echo     cd desktop
echo     %PY% -m alikhande
echo.
echo   To build the standalone .exe:
echo     double-click packaging\INSTALL_WINDOWS.bat
echo.
echo   MetaTrader 5 is NOT required for any of the above. It is needed
echo   only for live broker data, and even then the application refuses
echo   to trade a non-demo account.
exit /b 0

:probe
rem  Exits 0 when %* is an interpreter of at least 3.10. A missing command
rem  gives errorlevel 9009, which is also non-zero, so both cases are covered.
%* -c "import sys; sys.exit(0 if sys.version_info[:2] >= (3, 10) else 1)" >nul 2>&1
exit /b %errorlevel%
