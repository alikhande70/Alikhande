param(
  [Parameter(Mandatory=$true)][string]$MetaEditor,
  [Parameter(Mandatory=$true)][string]$TerminalDataPath,
  [string]$Configuration = "Release"
)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$mql = Join-Path $repo "MQL5"
$targetMql = Join-Path $TerminalDataPath "MQL5"
$artifact = Join-Path $repo "artifacts\metaeditor"
New-Item -ItemType Directory -Force -Path $artifact | Out-Null

if (!(Test-Path $MetaEditor)) { throw "MetaEditor not found: $MetaEditor" }
if (!(Test-Path $targetMql)) { throw "MT5 data path is invalid: $TerminalDataPath" }

$copies = @(
  @{src=(Join-Path $mql "Experts\AlikhandeScanner"); dst=(Join-Path $targetMql "Experts\AlikhandeScanner")},
  @{src=(Join-Path $mql "Include\AlikhandeScanner"); dst=(Join-Path $targetMql "Include\AlikhandeScanner")},
  @{src=(Join-Path $mql "Scripts\AlikhandeScanner"); dst=(Join-Path $targetMql "Scripts\AlikhandeScanner")}
)
foreach ($c in $copies) {
  if (Test-Path $c.dst) { Remove-Item -Recurse -Force $c.dst }
  New-Item -ItemType Directory -Force -Path (Split-Path -Parent $c.dst) | Out-Null
  Copy-Item -Recurse -Force $c.src $c.dst
}

$targets = @(
  "Scripts\AlikhandeScanner\CompileAllModules.mq5",
  "Scripts\AlikhandeScanner\DatabaseSmoke.mq5",
  "Scripts\AlikhandeScanner\PersistenceSmoke.mq5",
  "Scripts\AlikhandeScanner\SmokeDomain.mq5",
  "Scripts\AlikhandeScanner\SymbolDiscovery.mq5",
  "Scripts\AlikhandeScanner\SymbolSpec.mq5",
  "Scripts\AlikhandeScanner\Tests\Phase1RuntimeSelfTests.mq5",
  "Scripts\AlikhandeScanner\Tests\Phase2ZoneSignalSelfTests.mq5",
  "Scripts\AlikhandeScanner\Tests\Phase3ScoringLifecycleSelfTests.mq5",
  "Scripts\AlikhandeScanner\Tests\Phase4PersistenceSelfTests.mq5",
  "Scripts\AlikhandeScanner\Tests\Phase5RiskSelfTests.mq5",
  "Scripts\AlikhandeScanner\Tests\Phase6ExecutionSelfTests.mq5",
  "Scripts\AlikhandeScanner\Tests\Phase7CalendarUiSelfTests.mq5",
  "Experts\AlikhandeScanner\AlikhandeScanner.mq5"
)

$failed = $false
foreach ($relative in $targets) {
  $source = Join-Path $targetMql $relative
  $safe = ($relative -replace '[\\/:*?"<>|]', '_')
  $log = Join-Path $artifact ($safe + ".log")
  if (!(Test-Path $source)) { throw "Compile target missing: $source" }
  & $MetaEditor /compile:"$source" /log:"$log" | Out-Null
  if (!(Test-Path $log)) { throw "MetaEditor did not produce log: $log" }
  $text = Get-Content $log -Raw
  Write-Host "==== $relative ===="
  Write-Host $text
  if ($text -notmatch '0 errors, 0 warnings') { $failed = $true }
}

if ($failed) { throw "MetaEditor compile gate failed. Inspect artifacts/metaeditor/*.log" }
Write-Host "PASS: all Alikhande v1.3 MetaEditor targets compiled with 0 errors, 0 warnings"
