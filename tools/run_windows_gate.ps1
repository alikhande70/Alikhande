param(
  [string]$MetaEditor = "",
  [string]$TerminalDataPath = ""
)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$compile = Join-Path $PSScriptRoot "compile_mt5.ps1"

function Find-MetaEditors {
  $roots = @($env:ProgramFiles, ${env:ProgramFiles(x86)}, $env:LOCALAPPDATA) | Where-Object { $_ -and (Test-Path $_) }
  $found = New-Object System.Collections.Generic.List[string]
  foreach ($root in $roots) {
    $direct = @(
      (Join-Path $root "MetaTrader 5\metaeditor64.exe"),
      (Join-Path $root "LiteFinance MT5\metaeditor64.exe"),
      (Join-Path $root "LiteFinance-MT5-Demo\metaeditor64.exe")
    )
    foreach ($p in $direct) { if (Test-Path $p) { $found.Add((Resolve-Path $p).Path) } }
    Get-ChildItem -Path $root -Directory -ErrorAction SilentlyContinue |
      Where-Object { $_.Name -match 'MetaTrader|LiteFinance|MT5' } |
      ForEach-Object {
        $p = Join-Path $_.FullName "metaeditor64.exe"
        if (Test-Path $p) { $found.Add((Resolve-Path $p).Path) }
      }
  }
  return @($found | Select-Object -Unique)
}

function Find-TerminalDataPaths([string]$EditorPath) {
  $base = Join-Path $env:APPDATA "MetaQuotes\Terminal"
  if (!(Test-Path $base)) { return @() }
  $editorDir = Split-Path -Parent $EditorPath
  $all = Get-ChildItem -Path $base -Directory -ErrorAction SilentlyContinue |
    Where-Object { Test-Path (Join-Path $_.FullName "MQL5") }

  $matched = @()
  foreach ($d in $all) {
    $origin = Join-Path $d.FullName "origin.txt"
    if (Test-Path $origin) {
      $text = (Get-Content $origin -Raw -ErrorAction SilentlyContinue).Trim()
      if ($text -and ($editorDir -like "$text*" -or $text -like "$editorDir*")) { $matched += $d.FullName }
    }
  }
  if ($matched.Count -gt 0) { return @($matched) }
  return @($all | Sort-Object LastWriteTime -Descending | ForEach-Object { $_.FullName })
}

function Choose-One([string]$title, [string[]]$items) {
  if ($items.Count -eq 0) { throw "No $title found automatically." }
  if ($items.Count -eq 1) { return $items[0] }
  Write-Host ""
  Write-Host "Multiple $title candidates found:" -ForegroundColor Yellow
  for ($i=0; $i -lt $items.Count; $i++) { Write-Host "[$($i+1)] $($items[$i])" }
  do { $choice = Read-Host "Enter number (1-$($items.Count))" } while (($choice -as [int]) -lt 1 -or ($choice -as [int]) -gt $items.Count)
  return $items[[int]$choice-1]
}

Write-Host "=== Alikhande Scanner v1.3 Windows Qualification Gate ===" -ForegroundColor Cyan
Write-Host "This launcher only copies source files and compiles them. It does NOT place any trade." -ForegroundColor Green

if (!$MetaEditor) { $MetaEditor = Choose-One "MetaEditor" (Find-MetaEditors) }
if (!(Test-Path $MetaEditor)) { throw "MetaEditor not found: $MetaEditor" }

if (!$TerminalDataPath) { $TerminalDataPath = Choose-One "MT5 data folder" (Find-TerminalDataPaths $MetaEditor) }
if (!(Test-Path (Join-Path $TerminalDataPath "MQL5"))) { throw "Invalid MT5 data folder: $TerminalDataPath" }

Write-Host "MetaEditor: $MetaEditor"
Write-Host "MT5 data:   $TerminalDataPath"
Write-Host ""

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $compile -MetaEditor $MetaEditor -TerminalDataPath $TerminalDataPath
if ($LASTEXITCODE -ne 0) { throw "Compile gate failed. Please send the files under artifacts\metaeditor to GPT." }

Write-Host ""
Write-Host "PASS: MetaEditor compile gate completed." -ForegroundColor Green
Write-Host "Next: send the console output or artifacts\metaeditor logs to GPT before running any demo execution." -ForegroundColor Cyan
Read-Host "Press Enter to close"
