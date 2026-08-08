#property strict
#property version   "1.10"
#property description "Alikhande Scanner MT5 v1.1.0 - ScannerPanel hardening edition, alert-only by default"

#include <AlikhandeScanner/Core/Config.mqh>
#include <AlikhandeScanner/Core/VersionInfo.mqh>
#include <AlikhandeScanner/Domain/Models.mqh>
#include <AlikhandeScanner/Broker/SymbolResolver.mqh>
#include <AlikhandeScanner/Broker/SymbolSpec.mqh>
#include <AlikhandeScanner/Data/MarketData.mqh>
#include <AlikhandeScanner/Data/SpreadTracker.mqh>
#include <AlikhandeScanner/Analysis/TrendEngine.mqh>
#include <AlikhandeScanner/Analysis/ZoneEngine.mqh>
#include <AlikhandeScanner/Signals/SignalEngine.mqh>
#include <AlikhandeScanner/UI/Dashboard.mqh>
#include <AlikhandeScanner/Storage/SignalLogger.mqh>
#include <AlikhandeScanner/Trading/RiskPlanner.mqh>
#include <AlikhandeScanner/Trading/DemoExecution.mqh>
#include <AlikhandeScanner/Safety/AccountRiskGuard.mqh>

input string InpSymbols=AS_DEFAULT_SYMBOLS;
input int InpScanTimerMs=AS_DEFAULT_SCAN_TIMER_MS;
input int InpScanBudgetMicroseconds=AS_DEFAULT_SCAN_BUDGET_US;
input int InpSymbolsPerSlice=AS_DEFAULT_SYMBOLS_PER_SLICE;
input int InpMinimumBars=AS_DEFAULT_MINIMUM_BARS;
input int InpSpreadWarmupSamples=AS_DEFAULT_SPREAD_WARMUP_SAMPLES;
input int InpMaximumTickAgeSeconds=AS_DEFAULT_MAX_TICK_AGE_SECONDS;
input ENUM_AS_CHART_REUSE InpChartReuseMode=AS_ATLAS_MANAGED_ONLY;
input bool InpEnableAlerts=true;
input int InpAlertCooldownMinutes=30;
input bool InpAlertOnlyMode=true;
input bool InpEnableAccountRiskGuards=false;

AS_MarketData g_data;AS_TrendEngine g_trend;AS_ZoneEngine g_zones;AS_SignalEngine g_signal;AS_Dashboard g_ui;AS_SignalLogger g_log;
AS_SymbolResolver g_resolver;AS_SymbolSpecReader g_spec_reader;AS_AccountRiskGuard g_account_guard;
string g_requested[],g_symbols[];int g_cursor=0;datetime g_last_alert[];AS_SpreadTracker *g_spreads[];
datetime g_bar_h4[],g_bar_h1[],g_bar_m15[],g_bar_m5[];AS_TrendResult g_h4[],g_h1[],g_m15[],g_m5[];AS_SignalCandidate g_cached_signal[];

string TrendText(ENUM_AS_TREND_CLASS t){if(t==AS_STRONG_BULLISH)return "STR BULL";if(t==AS_BULLISH)return "BULL";if(t==AS_WEAK_BULLISH)return "WK BULL";if(t==AS_STRONG_BEARISH)return "STR BEAR";if(t==AS_BEARISH)return "BEAR";if(t==AS_WEAK_BEARISH)return "WK BEAR";return "NEUTRAL";}

bool RefreshTrend(const string symbol,const ENUM_TIMEFRAMES tf,datetime &last_bar,AS_TrendResult &out,bool &changed){changed=false;datetime closed=iTime(symbol,tf,1);if(closed<=0)return false;if(closed==last_bar&&out.valid)return true;AS_TrendResult temp;ZeroMemory(temp);if(!g_trend.Analyze(symbol,tf,temp))return false;out=temp;last_bar=closed;changed=true;return true;}

bool IsManagedChart(const long cid){return ObjectFind(cid,AS_MANAGED_CHART_MARKER)>=0;}
long FindExistingChart(const string symbol,const ENUM_TIMEFRAMES tf,const bool managed_only){for(long cid=ChartFirst();cid>=0;cid=ChartNext(cid)){if(ChartSymbol(cid)==symbol&&ChartPeriod(cid)==tf){if(!managed_only||IsManagedChart(cid))return cid;}}return -1;}
void OpenManagedChart(const string symbol,const ENUM_TIMEFRAMES tf){long cid=-1;if(InpChartReuseMode==AS_ATLAS_MANAGED_ONLY)cid=FindExistingChart(symbol,tf,true);else if(InpChartReuseMode==AS_REUSE_ANY_MATCHING)cid=FindExistingChart(symbol,tf,false);if(cid<0)cid=ChartOpen(symbol,tf);if(cid>0){ChartSetInteger(cid,CHART_BRING_TO_TOP,true);if(ObjectFind(cid,AS_MANAGED_CHART_MARKER)<0){ObjectCreate(cid,AS_MANAGED_CHART_MARKER,OBJ_LABEL,0,0,0);ObjectSetString(cid,AS_MANAGED_CHART_MARKER,OBJPROP_TEXT,"");ObjectSetInteger(cid,AS_MANAGED_CHART_MARKER,OBJPROP_COLOR,clrNONE);ObjectSetInteger(cid,AS_MANAGED_CHART_MARKER,OBJPROP_HIDDEN,true);}}}

int OnInit(){
   string raw[];int n=StringSplit(InpSymbols,',',raw);if(n<=0)return INIT_PARAMETERS_INCORRECT;
   ArrayResize(g_requested,n);ArrayResize(g_symbols,n);ArrayResize(g_last_alert,n);ArrayResize(g_spreads,n);ArrayResize(g_bar_h4,n);ArrayResize(g_bar_h1,n);ArrayResize(g_bar_m15,n);ArrayResize(g_bar_m5,n);ArrayResize(g_h4,n);ArrayResize(g_h1,n);ArrayResize(g_m15,n);ArrayResize(g_m5,n);ArrayResize(g_cached_signal,n);
   for(int i=0;i<n;i++){g_requested[i]=raw[i];StringTrimLeft(g_requested[i]);StringTrimRight(g_requested[i]);string resolved="";if(!g_resolver.Resolve(g_requested[i],resolved))PrintFormat("Alikhande: unresolved symbol '%s'",g_requested[i]);g_symbols[i]=resolved;g_spreads[i]=new AS_SpreadTracker();}
   g_account_guard.Initialize();g_ui.Header();EventSetMillisecondTimer((int)MathMax(100,InpScanTimerMs));PrintFormat("Alikhande Scanner v%s initialized. AlertOnly=%s",AS_VERSION,(InpAlertOnlyMode?"true":"false"));return INIT_SUCCEEDED;
}

void OnDeinit(const int reason){EventKillTimer();for(int i=0;i<ArraySize(g_spreads);i++)if(CheckPointer(g_spreads[i])==POINTER_DYNAMIC)delete g_spreads[i];g_ui.Clear();}

void OnTimer(){
   int total=ArraySize(g_symbols);if(total==0)return;ulong started=GetMicrosecondCount();int processed=0,limit=(int)MathMin(InpSymbolsPerSlice,total);
   while(processed<limit){if(processed>0&&GetMicrosecondCount()-started>=(ulong)MathMax(1000,InpScanBudgetMicroseconds))break;int i=(g_cursor+processed)%total;processed++;string sym=g_symbols[i];
      if(sym==""){g_ui.Row(i,g_requested[i],0,"DATA","DATA",0,0,"UNRESOLVED");continue;}
      AS_SymbolSpec spec;if(!g_spec_reader.Read(sym,spec)){g_ui.Row(i,sym,0,"SPEC","SPEC",0,0,"SPEC WARMUP");continue;}
      AS_SymbolSnapshot snap;if(!g_data.Snapshot(g_requested[i],sym,InpMaximumTickAgeSeconds,snap)){g_ui.Row(i,sym,0,"DATA","DATA",0,0,"NO TICK");continue;}
      if(snap.spread_state!=AS_SPREAD_STALE){g_spreads[i].Add(snap.spread_points);snap.spread_state=g_spreads[i].Classify(snap.spread_points,InpSpreadWarmupSamples,snap.spread_ratio);}
      ENUM_AS_DATA_STATE ds;if(!g_data.EnsureAllReady(sym,InpMinimumBars,ds)){g_ui.Row(i,sym,snap.spread_points,"SYNC","SYNC",0,0,"LOADING");continue;}
      bool c4=false,c1=false,c15=false,c5=false;
      if(!RefreshTrend(sym,PERIOD_H4,g_bar_h4[i],g_h4[i],c4)||!RefreshTrend(sym,PERIOD_H1,g_bar_h1[i],g_h1[i],c1)||!RefreshTrend(sym,PERIOD_M15,g_bar_m15[i],g_m15[i],c15)||!RefreshTrend(sym,PERIOD_M5,g_bar_m5[i],g_m5[i],c5)){g_ui.Row(i,sym,snap.spread_points,"WAIT","WAIT",0,0,"IND DATA");continue;}
      if(c4||c1||c15||c5||g_cached_signal[i].confirmation_bar_time==0){AS_Zone z[];g_zones.Build(sym,PERIOD_H1,300,3,3,0.20,z);AS_SignalCandidate candidate;ZeroMemory(candidate);if(g_signal.Evaluate(sym,g_h4[i],g_h1[i],g_m15[i],g_m5[i],snap,z,candidate))g_cached_signal[i]=candidate;}
      AS_SignalCandidate s;s=g_cached_signal[i];string status=(s.direction==AS_DIR_LONG?"LONG":(s.direction==AS_DIR_SHORT?"SHORT":(s.hard_blocked?"BLOCKED":"NO TRADE")));
      string risk_codes="";if(!g_account_guard.Check(InpEnableAccountRiskGuards,risk_codes))status="RISK HALT";
      g_ui.Row(i,sym,snap.spread_points,TrendText(g_h1[i].trend_class),TrendText(g_m15[i].trend_class),s.long_score,s.short_score,status);
      if((s.direction==AS_DIR_LONG||s.direction==AS_DIR_SHORT)&&status!="RISK HALT"&&g_log.AppendUnique(s)){if(InpEnableAlerts&&TimeCurrent()-g_last_alert[i]>=InpAlertCooldownMinutes*60){Alert(StringFormat("%s %s score L%.0f/S%.0f",sym,status,s.long_score,s.short_score));g_last_alert[i]=TimeCurrent();}}
   }
   if(processed>0)g_cursor=(g_cursor+processed)%total;ChartRedraw();
}

void OnChartEvent(const int id,const long &lparam,const double &dparam,const string &sparam){if(id!=CHARTEVENT_OBJECT_CLICK)return;string symbol;if(g_ui.ParseOpen(sparam,symbol))OpenManagedChart(symbol,PERIOD_M15);}

void OnTradeTransaction(const MqlTradeTransaction &trans,const MqlTradeRequest &request,const MqlTradeResult &result){
   if(trans.type==TRADE_TRANSACTION_DEAL_ADD&&trans.deal>0&&HistoryDealSelect(trans.deal)){long entry=HistoryDealGetInteger(trans.deal,DEAL_ENTRY);if(entry==DEAL_ENTRY_OUT||entry==DEAL_ENTRY_OUT_BY){double net=HistoryDealGetDouble(trans.deal,DEAL_PROFIT)+HistoryDealGetDouble(trans.deal,DEAL_COMMISSION)+HistoryDealGetDouble(trans.deal,DEAL_SWAP);g_account_guard.RegisterClosedProfit(net);}}
   PrintFormat("Alikhande trade transaction type=%d order=%I64u deal=%I64u retcode=%u",trans.type,trans.order,trans.deal,result.retcode);
}
