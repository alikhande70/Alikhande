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

defs=set(re.findall(r'^\s*#define\s+(AS_[A-Z0-9_]+)',all_src,re.M))
for enum_body in re.findall(r'enum\s+ENUM_AS_[A-Z0-9_]+\s*\{([^}]*)\}',all_src,re.S):
    defs.update(re.findall(r'\b(AS_[A-Z0-9_]+)\b',enum_body))
uses=set(re.findall(r'\b(AS_[A-Z0-9_]+)\b',all_src))
missing=sorted(x for x in uses-defs if not x.startswith('AS_PRODUCT_') and x not in {'AS_VERSION','AS_RULE_VERSION','AS_SCORING_VERSION','AS_SCHEMA_VERSION','AS_MANAGED_CHART_MARKER'})
if missing: errors.append('UNRESOLVED_AS_CONSTANTS '+','.join(missing))

include_re=re.compile(r'#include\s+[<"]([^>"]+)[>"]')
def resolve_include(source:Path, token:str):
    if token.startswith('AlikhandeScanner/'):
        return (INC/token[len('AlikhandeScanner/'):]).resolve()
    return (source.parent/token).resolve()

reachable=set();stack=[EA.resolve()]
while stack:
    current=stack.pop()
    if current in reachable or not current.exists(): continue
    reachable.add(current)
    text=current.read_text(encoding='utf-8',errors='replace')
    for token in include_re.findall(text):
        target=resolve_include(current,token)
        if target.exists() and target.suffix.lower() in {'.mqh','.mq5'}: stack.append(target)

all_modules={p.resolve() for p in INC.rglob('*.mqh')}
unreachable=sorted(str(p.relative_to(ROOT)) for p in all_modules-reachable)
if unreachable: errors.append('UNREACHABLE_MODULES '+','.join(unreachable))

ea_text=EA.read_text(encoding='utf-8',errors='replace')
for name in ['g_last_alert','g_bar_h4','g_bar_h1','g_bar_m15','g_bar_m5']:
    if f'ArrayResize({name},' in ea_text and f'ArrayInitialize({name},' not in ea_text: errors.append(f'UNINITIALIZED_RUNTIME_ARRAY {name}')

compact=re.sub(r'\s+','',ea_text)
if 'c4||c1||c15||c5' in compact and 'g_signal_engine.Evaluate' in compact: errors.append('STALE_SIGNAL_BAR_GATED_EVALUATION')
if 'g_cached_signal[i]=s;' not in compact: errors.append('LIVE_SIGNAL_CACHE_NOT_REFRESHED')

for rel in ['Analysis/TrendEngine.mqh','Analysis/ZoneEngine.mqh']:
    t=(INC/rel).read_text(encoding='utf-8',errors='replace')
    if any(fn in t for fn in ['iMA(','iADX(','iATR(']) and 'm_handles' not in t: errors.append('UNCACHED_INDICATOR_HANDLE '+rel)

execution=(INC/'Execution'/'ExecutionEngine.mqh').read_text(encoding='utf-8',errors='replace')
execution_compact=re.sub(r'\s+','',execution)
if 'm_current.state=AS_EXEC_UNKNOWN;m_current.terminal=false' not in execution_compact: errors.append('UNKNOWN_EXECUTION_MAY_UNBLOCK_SEND')
if 'm_current.created_at=now' not in execution_compact: errors.append('EXECUTION_CREATED_AT_NOT_PERSISTED')
reconciler=(INC/'Execution'/'ReconcilerV13.mqh').read_text(encoding='utf-8',errors='replace')
for needle in ['PositionsTotal()','OrdersTotal()','HistoryDealsTotal()','HistoryOrdersTotal()','ORDER_POSITION_ID','DEAL_ORDER','current.created_at']:
    if needle not in reconciler: errors.append('RECONCILIATION_SOURCE_MISSING '+needle)

outcome=(INC/'Signals'/'OutcomeEngine.mqh').read_text(encoding='utf-8',errors='replace')
for needle in ['UpdateShadow','SyncDemoExecution','RecoverTerminalWithoutOutcome','AS_OUTCOME_SOURCE_SHADOW','AS_OUTCOME_SOURCE_DEMO','DEAL_POSITION_ID','DEAL_REASON_TP','DEAL_REASON_SL','x.created_at']:
    if needle not in outcome: errors.append('OUTCOME_EVIDENCE_PATH_MISSING '+needle)
repo=(INC/'Persistence'/'Repositories.mqh').read_text(encoding='utf-8',errors='replace')
for needle in ['evidence_source','rule_version','scoring_version','parameter_hash','broker_spec_hash','execution_id','created_at','LoadLatestExecutionWithoutOutcome']:
    if needle not in repo: errors.append('OUTCOME_PROVENANCE_MISSING '+needle)
read_models=(INC/'Persistence'/'ReadModels.mqh').read_text(encoding='utf-8',errors='replace')
for needle in ['evidence_source=?3','rule_version=?4','scoring_version=?5','parameter_hash=?6']:
    if needle not in read_models: errors.append('OUTCOME_STATS_SCOPE_MISSING '+needle)
if 'g_outcomes.UpdateShadow' not in ea_text or 'g_outcomes.SyncDemoExecution' not in ea_text: errors.append('OUTCOME_ENGINE_NOT_WIRED_TO_EA')
if 's.signal_id=AS_Fnv1a(s.signal_id+"|"+g_parameter_hash+"|"+s.broker_spec_hash)' not in compact: errors.append('SIGNAL_EVIDENCE_IDENTITY_NOT_SCOPED')
version=(INC/'Core'/'VersionInfo.mqh').read_text(encoding='utf-8',errors='replace')
if '#define AS_SCHEMA_VERSION 7' not in version: errors.append('SCHEMA_V7_NOT_ACTIVE')

database=(INC/'Persistence'/'Database.mqh').read_text(encoding='utf-8',errors='replace')
if 'Migrate5To6' not in database or 'ix_outcomes_scope' not in database: errors.append('OUTCOME_SCHEMA_MIGRATION_MISSING')
if 'Migrate6To7' not in database or 'ALTER TABLE executions ADD COLUMN created_at' not in database: errors.append('EXECUTION_TIMESTAMP_MIGRATION_MISSING')

print('STATIC GATE')
print('INFO files=',len(files))
print('INFO lines=',sum(len(t.splitlines()) for t in texts.values()))
print('INFO reachable_modules=',len(all_modules & reachable),'/',len(all_modules))
if errors:
    for e in errors: print('FAIL',e)
    sys.exit(1)
print('PASS include graph / reachability / live-signal path / indicator cache / execution recovery / evidence integrity / migrations / constants / safety policy')
