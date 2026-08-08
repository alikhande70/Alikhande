#!/usr/bin/env python3
from pathlib import Path
import re,sys
ROOT=Path(__file__).resolve().parents[1];SRC=ROOT/'MQL5';errors=[];files=list(SRC.rglob('*.mq5'))+list(SRC.rglob('*.mqh'))
for f in files:
 t=f.read_text(encoding='utf-8',errors='replace')
 for inc in re.findall(r'#include\s+[<"]AlikhandeScanner/([^>"]+)[>"]',t):
  target=ROOT/'MQL5'/'Include'/'AlikhandeScanner'/inc
  if not target.exists():errors.append(f'BROKEN_INCLUDE {f.relative_to(ROOT)} -> {inc}')
 x=re.sub(r'//.*','',t);x=re.sub(r'/\*.*?\*/','',x,flags=re.S);x=re.sub(r'"(?:\\.|[^"\\])*"','""',x)
 if x.count('{')!=x.count('}'):errors.append(f'BRACE_MISMATCH {f.relative_to(ROOT)}')
all_src='\n'.join(f.read_text(encoding='utf-8',errors='replace') for f in files)
for name,needle in {'event_reconciliation':'OnTradeTransaction','sqlite':'DatabaseOpen','preflight':'OrderCheck','real_hard_block':'REAL_ACCOUNT_BLOCKED','demo_guard':'ACCOUNT_TRADE_MODE_DEMO','persistent_dedup':'SignalExists','shadow_mode':'AS_MODE_SHADOW','regime':'AS_RegimeEngine','news_gate':'CalendarValueHistory','spec_drift':'SPEC_DRIFT'}.items():
 if needle not in all_src:errors.append(f'MISSING_REQUIRED {name}: {needle}')
for forbidden in ['OrderSendAsync(','WebRequest(','martingale','averaging down']:
 if forbidden.lower() in all_src.lower():errors.append(f'FORBIDDEN_OR_DEFERRED_SOURCE {forbidden}')
submit=[str(f.relative_to(ROOT)) for f in files if 'OrderSend(' in f.read_text(encoding='utf-8',errors='replace')]
if submit!=['MQL5/Include/AlikhandeScanner/Execution/ExecutionEngine.mqh']:errors.append('ORDER_SEND_BOUNDARY '+repr(submit))
sig=(ROOT/'MQL5/Include/AlikhandeScanner/Signals/SignalEngine.mqh').read_text()
if 'has_historical_estimate=false' not in sig:errors.append('PROBABILITY_GUARD_MISSING')
for rel in ['MQL5/Include/AlikhandeScanner/Core/SignalRegistry.mqh','MQL5/Include/AlikhandeScanner/Storage/SignalLogger.mqh','MQL5/Include/AlikhandeScanner/Trading/DemoExecution.mqh']:
 if (ROOT/rel).exists():errors.append('LEGACY_ACTIVE '+rel)
print('STATIC GATE');print('INFO files=',len(files));print('INFO lines=',sum(len(f.read_text(encoding='utf-8',errors='replace').splitlines()) for f in files))
if errors:
 [print('FAIL',e) for e in errors];sys.exit(1)
print('PASS include graph / brace balance / architecture boundaries / safety policy')
