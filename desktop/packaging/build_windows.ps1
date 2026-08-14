<#
    Build AlikhandeScanner.exe on Windows.

    Run from the repository's `desktop` directory:

        powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1

    The script refuses to package a build whose own tests do not pass. That is
    the point: an executable is the artefact people actually run, and shipping
    one from a red suite is how an untested build reaches a live terminal.
#>

[CmdletBinding()]
param(
    [switch]$SkipTests,
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

Write-Host "== Alikhande Scanner — Windows build ==" -ForegroundColor Cyan
Write-Host "working directory: $root"

# ---------------------------------------------------------------- environment
$version = & $Python -c "import sys; print('.'.join(map(str, sys.version_info[:3])))"
Write-Host "python: $version"

if ([version]($version) -lt [version]"3.10.0") {
    throw "Python 3.10 or newer is required (found $version)."
}

Write-Host "`n-- installing dependencies" -ForegroundColor Cyan
& $Python -m pip install --upgrade pip
& $Python -m pip install -r requirements.txt
& $Python -m pip install pyinstaller

# --------------------------------------------------------------------- tests
if (-not $SkipTests) {
    Write-Host "`n-- running the test suite" -ForegroundColor Cyan
    & $Python -m unittest discover -s tests -t .
    if ($LASTEXITCODE -ne 0) {
        throw "tests failed — refusing to package. Fix them, or pass -SkipTests if you accept the risk."
    }
    Write-Host "tests passed" -ForegroundColor Green
}

# ------------------------------------------------------------------- doctor
Write-Host "`n-- environment check" -ForegroundColor Cyan
& $Python -m alikhande doctor

# -------------------------------------------------------------------- build
Write-Host "`n-- building" -ForegroundColor Cyan
Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue
& $Python -m PyInstaller packaging\alikhande.spec --noconfirm

$exe = Join-Path $root "dist\AlikhandeScanner\AlikhandeScanner.exe"
if (-not (Test-Path $exe)) {
    throw "build finished but $exe is missing."
}

$size = [math]::Round((Get-ChildItem -Recurse "dist\AlikhandeScanner" |
    Measure-Object -Property Length -Sum).Sum / 1MB, 1)

Write-Host "`n== build complete ==" -ForegroundColor Green
Write-Host "executable: $exe"
Write-Host "bundle size: $size MB"
Write-Host @"

Before running it against a broker:
  1. Start MetaTrader 5 and log in to a DEMO account.
  2. Tools -> Options -> Expert Advisors -> enable Algo Trading.
  3. Add every symbol you want scanned to Market Watch.

This build refuses to trade a non-demo account. That refusal is structural,
not a setting.
"@ -ForegroundColor Yellow
