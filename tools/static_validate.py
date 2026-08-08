#!/usr/bin/env python3
from pathlib import Path
import re,sys
ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'MQL5'
INC=SRC/'Include'/'AlikhandeScanner'
EA=SRC/'Experts'/'AlikhandeScanner'/'AlikhandeScanner.mq5'
errors=[]
files=list(SRC.rglob('*.mq5'))+list(SRC.rglob('*.mqh'))
texts={f:f.read_text(encoding='utf-8',errors='replace') for f in files}

for f,t in texts.items():
    for inc in re.findall(r'#include\s+[<"]AlikhandeScanner/([^>"]+)[>"]',t):
        target=INC/inc
        if not target.exists(): errors.append(f'BROKEN_INCLUDE {f.relative_to(ROOT)} -> {inc}')
    x=re.sub(r'//.*','',t)
    x=re.sub(r'/\*.*?\*/','',x,flags=re.S)
    x=re.sub(r'"(?:\\.|[^"\\])*"','""',x)
    if x.count('{')!=x.count('}'): errors.append(f'BRACE_MISMATCH {f.relative_to(ROOT)}')

all_src='\n'.join(texts.values())
required={
    'event_reconciliation':'OnTradeTransaction',
    'sqlite':'DatabaseOpen',
    'preflight':'OrderCheck',
    'real_hard_block':'REAL_ACCOUNT_BLOCKED',
    'demo_guard':'ACCOUNT_TRADE_MODE_DEMO',
    'persistent_dedup':'SignalExists',
    'shadow_mode':'AS_MODE_SHADOW',
    'regime':'AS_RegimeEngine',
    'news_gate':'CalendarValueHistory',
    'spec_drift':'SPEC_DRIFT',
}
for name,needle in required.items():
    if needle not in all_src: errors.append(f'MISSING_REQUIRED {name}: {needle}')

for forbidden in ['OrderSendAsync(','WebRequest(','martingale','averaging down']:
    if forbidden.lower() in all_src.lower(): errors.append(f'FORBIDDEN_OR_DEFERRED_SOURCE {forbidden}')

submit=[str(f.relative_to(ROOT)) for f,t in texts.items() if 'OrderSend(' in t]
if submit!=['MQL5/Include/AlikhandeScanner/Execution/ExecutionEngine.mqh']:
    errors.append('ORDER_SEND_BOUNDARY '+repr(submit))

sig=(INC/'Signals'/'SignalEngine.mqh').read_text()
if 'has_historical_estimate=false' not in sig: errors.append('PROBABILITY_GUARD_MISSING')
if 'LiveValidatorV13.mqh' not in sig or 'ZoneSemanticsV13.mqh' not in sig or 'ExplainableScoringV13.mqh' not in sig:
    errors.append('PRODUCTION_SIGNAL_V13_NOT_WIRED')

for rel in [
    'MQL5/Include/AlikhandeScanner/Core/SignalRegistry.mqh',
    'MQL5/Include/AlikhandeScanner/Storage/SignalLogger.mqh',
    'MQL5/Include/AlikhandeScanner/Trading/DemoExecution.mqh']:
    if (ROOT/rel).exists(): errors.append('LEGACY_ACTIVE '+rel)

# Detect missing Alikhande compile-time constants/enums before MetaEditor.
defs=set(re.findall(r'^\s*#define\s+(AS_[A-Z0-9_]+)',all_src,re.M))
for enum_body in re.findall(r'enum\s+ENUM_AS_[A-Z0-9_]+\s*\{([^}]*)\}',all_src,re.S):
    defs.update(re.findall(r'\b(AS_[A-Z0-9_]+)\b',enum_body))
uses=set(re.findall(r'\b(AS_[A-Z0-9_]+)\b',all_src))
missing=sorted(x for x in uses-defs if not x.startswith('AS_PRODUCT_') and x not in {'AS_VERSION','AS_RULE_VERSION','AS_SCORING_VERSION','AS_SCHEMA_VERSION','AS_MANAGED_CHART_MARKER'})
if missing: errors.append('UNRESOLVED_AS_CONSTANTS '+','.join(missing))

# Production reachability gate. Follow the real include graph from the EA;
# compiling a module in a synthetic test is not evidence that production uses it.
include_re=re.compile(r'#include\s+[<"]([^>"]+)[>"]')
def resolve_include(source:Path, token:str):
    if token.startswith('AlikhandeScanner/'):
        return INC/token[len('AlikhandeScanner/'):]
    if token.startswith('..') or token.startswith('.'):
        return (source.parent/token).resolve()
    return None

reachable=set()
stack=[EA.resolve()]
while stack:
    current=stack.pop()
    if current in reachable or not current.exists():
        continue
    reachable.add(current)
    text=current.read_text(encoding='utf-8',errors='replace')
    for token in include_re.findall(text):
        target=resolve_include(current,token)
        if target is not None and target.exists() and (target.suffix.lower() in {'.mqh','.mq5'}):
            stack.append(target.resolve())

all_modules={p.resolve() for p in INC.rglob('*.mqh')}
unreachable=sorted(str(p.relative_to(ROOT)) for p in all_modules-reachable)
if unreachable:
    errors.append('UNREACHABLE_MODULES '+','.join(unreachable))

# Critical scheduler arrays must be initialised after resizing; relying on
# unspecified resized-array contents can corrupt cooldown/new-bar state.
ea_text=EA.read_text(encoding='utf-8',errors='replace')
for name in ['g_last_alert','g_bar_h4','g_bar_h1','g_bar_m15','g_bar_m5']:
    if f'ArrayResize({name},' in ea_text and f'ArrayInitialize({name},' not in ea_text:
        errors.append(f'UNINITIALIZED_RUNTIME_ARRAY {name}')

# Stale-signal regression guard: signal evaluation must not be gated by a
# closed-bar-change disjunction. Closed bars update structural inputs; the live
# validator must still run every scan pass.
compact=re.sub(r'\s+','',ea_text)
if 'c4||c1||c15||c5' in compact and 'g_signal_engine.Evaluate' in compact:
    errors.append('STALE_SIGNAL_BAR_GATED_EVALUATION')
if 'g_cached_signal[i]=s;' not in compact:
    errors.append('LIVE_SIGNAL_CACHE_NOT_REFRESHED')

# Indicator handles used by production analysis must be retained in a cache;
# repeated create/release cycles are forbidden in the scanner hot path.
for rel in ['Analysis/TrendEngine.mqh','Analysis/ZoneEngine.mqh']:
    p=INC/rel;t=p.read_text(encoding='utf-8',errors='replace')
    if any(fn in t for fn in ['iMA(','iADX(','iATR(']) and 'm_handles' not in t:
        errors.append('UNCACHED_INDICATOR_HANDLE '+rel)

print('STATIC GATE')
print('INFO files=',len(files))
print('INFO lines=',sum(len(t.splitlines()) for t in texts.values()))
print('INFO reachable_modules=',len(all_modules & reachable),'/',len(all_modules))
if errors:
    for e in errors: print('FAIL',e)
    sys.exit(1)
print('PASS include graph / reachability / live-signal path / indicator cache / constants / architecture boundaries / safety policy')
