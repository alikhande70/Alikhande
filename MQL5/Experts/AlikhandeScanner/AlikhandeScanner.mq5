#property strict
#property version "1.20"
#property description "Alikhande Scanner MT5 v1.2.0-rc1 - reliability and evidence edition"

#include <AlikhandeScanner/Core/Config.mqh>
#include <AlikhandeScanner/Core/VersionInfo.mqh>
#include <AlikhandeScanner/Core/Hash.mqh>
#include <AlikhandeScanner/Domain/Models.mqh>
#include <AlikhandeScanner/Broker/SymbolResolver.mqh>
#include <AlikhandeScanner/Broker/SymbolSpec.mqh>
#include <AlikhandeScanner/Data/MarketData.mqh>
#include <AlikhandeScanner/Data/SpreadTracker.mqh>
#include <AlikhandeScanner/Analysis/TrendEngine.mqh>
#include <AlikhandeScanner/Analysis/ZoneEngine.mqh>
#include <AlikhandeScanner/Analysis/RegimeEngine.mqh>
#include <AlikhandeScanner/Signals/SignalEngine.mqh>
#include <AlikhandeScanner/Signals/SignalLifecycle.mqh>
#include <AlikhandeScanner/Signals/OutcomeEngine.mqh>
#include <AlikhandeScanner/Persistence/Database.mqh>
#include <AlikhandeScanner/Persistence/Repositories.mqh>
#include <AlikhandeScanner/Trading/RiskPlanner.mqh>
#include <AlikhandeScanner/Risk/PortfolioRisk.mqh>
#include <AlikhandeScanner/News/NewsGate.mqh>
#include <AlikhandeScanner/Execution/ExecutionEngine.mqh>
#include <AlikhandeScanner/Safety/AccountRiskGuard.mqh>
#include <AlikhandeScanner/Health/CircuitBreaker.mqh>
#include <AlikhandeScanner/Health/CapabilityMatrix.mqh>
#include <AlikhandeScanner/UI/Dashboard.mqh>
#include <AlikhandeScanner/UI/ChartOverlay.mqh>

input string InpSymbols=AS_DEFAULT_SYMBOLS;
input int InpScanTimerMs=AS_DEFAULT_SCAN_TIMER_MS;
input int InpScanBudgetMicroseconds=AS_DEFAULT_SCAN_BUDGET_US;
input int InpSymbolsPerSlice=AS_DEFAULT_SYMBOLS_PER_SLICE;
input int InpMinimumBars=AS_DEFAULT_MINIMUM_BARS;
input int InpSpreadWarmupSamples=AS_DEFAULT_SPREAD_WARMUP_SAMPLES;
input int InpMaximumTickAgeSeconds=AS_DEFAULT_MAX_TICK_AGE_SECONDS;
input ENUM_AS_CHART_REUSE InpChartReuseMode=AS_MANAGED_ONLY;
input ENUM_AS_RUN_MODE InpRunMode=AS_MODE_ALERT_ONLY;
input double InpRiskPercent=AS_DEFAULT_RISK_PERCENT;
input double InpMaxTotalOpenRiskPct=AS_DEFAULT_TOTAL_OPEN_RISK_PCT;
input bool InpEnableAlerts=true;
input int InpAlertCooldownMinutes=30;
input bool InpEnableAccountRiskGuards=true;
input bool InpEnableNewsGate=true;
input int InpNewsBlockBeforeMinutes=AS_DEFAULT_NEWS_BLOCK_BEFORE_MIN;
input int InpNewsBlockAfterMinutes=AS_DEFAULT_NEWS_BLOCK_AFTER_MIN;

AS_MarketData g_data;
AS_TrendEngine g_trend;
AS_ZoneEngine g_zones;
AS_RegimeEngine g_regime_engine;
AS_SignalEngine g_signal_engine;
AS_Dashboard g_ui;
AS_SymbolResolver g_resolver;
AS_SymbolSpecReader g_spec_reader;
AS_AccountRiskGuard g_account_guard;
AS_RiskPlanner g_risk_planner;
AS_PortfolioRisk g_portfolio;
AS_NewsGate g_news;
AS_Database g_db;
AS_Repositories g_repo;
AS_SignalLifecycle g_lifecycle;
AS_OutcomeEngine g_outcomes;
AS_ExecutionEngine g_execution;
AS_CircuitBreaker g_breaker;
AS_CapabilityMatrix g_capabilities;
AS_ChartOverlay g_overlay;

string g_requested[],g_symbols[];
int g_cursor=0,g_selected=-1;
datetime g_last_alert[];
AS_SpreadTracker *g_spreads[];
datetime g_bar_h4[],g_bar_h1[],g_bar_m15[],g_bar_m5[];
AS_TrendResult g_h4[],g_h1[],g_m15[],g_m5[];
AS_SignalCandidate g_cached_signal[];
AS_RegimeResult g_cached_regime[];
AS_SymbolSpec g_cached_spec[];
bool g_data_ready[];
AS_TradePlan g_current_plan;
string g_parameter_hash="";

string CurrentParameterHash(){
   string raw=StringFormat("%s|%d|%d|%d|%d|%d|%d|%d|%d|%.4f|%.4f|%d|%d|%d|%d|%d",
      InpSymbols,InpScanTimerMs,InpScanBudgetMicroseconds,InpSymbolsPerSlice,InpMinimumBars,
      InpSpreadWarmupSamples,InpMaximumTickAgeSeconds,(int)InpChartReuseMode,(int)InpRunMode,
      InpRiskPercent,InpMaxTotalOpenRiskPct,(int)InpEnableAccountRiskGuards,(int)InpEnableNewsGate,
      InpNewsBlockBeforeMinutes,InpNewsBlockAfterMinutes,InpAlertCooldownMinutes);
   return AS_Fnv1a(raw);
}

bool SignalTerminal(const AS_SignalCandidate &s){
   return s.state==AS_SIGNAL_TP || s.state==AS_SIGNAL_SL || s.state==AS_SIGNAL_EXPIRED ||
          s.state==AS_SIGNAL_INVALIDATED || s.state==AS_SIGNAL_AMBIGUOUS || s.state==AS_SIGNAL_NOT_FILLED;
}

bool RefreshTrend(const string symbol,const ENUM_TIMEFRAMES tf,datetime &last_bar,AS_TrendResult &out,bool &changed){
   changed=false;
   datetime closed=iTime(symbol,tf,1);
   if(closed<=0)return false;
   if(closed==last_bar&&out.valid)return true;
   AS_TrendResult temp;ZeroMemory(temp);
   if(!g_trend.Analyze(symbol,tf,temp))return false;
   out=temp;last_bar=closed;changed=true;return true;
}

bool IsManagedChart(const long cid){return ObjectFind(cid,AS_MANAGED_CHART_MARKER)>=0;}

long FindExistingChart(const string symbol,const ENUM_TIMEFRAMES tf,const bool managed_only){
   for(long cid=ChartFirst();cid>=0;cid=ChartNext(cid)){
      if(ChartSymbol(cid)==symbol&&ChartPeriod(cid)==tf){if(!managed_only||IsManagedChart(cid))return cid;}
   }
   return -1;
}

void OpenManagedChart(const string symbol,const ENUM_TIMEFRAMES tf){
   long cid=-1;
   if(InpChartReuseMode==AS_MANAGED_ONLY)cid=FindExistingChart(symbol,tf,true);
   else if(InpChartReuseMode==AS_REUSE_MATCHING)cid=FindExistingChart(symbol,tf,false);
   if(cid<0)cid=ChartOpen(symbol,tf);
   if(cid>0){
      ChartSetInteger(cid,CHART_BRING_TO_TOP,true);
      if(ObjectFind(cid,AS_MANAGED_CHART_MARKER)<0){
         ObjectCreate(cid,AS_MANAGED_CHART_MARKER,OBJ_LABEL,0,0,0);
         ObjectSetString(cid,AS_MANAGED_CHART_MARKER,OBJPROP_TEXT,"");
         ObjectSetInteger(cid,AS_MANAGED_CHART_MARKER,OBJPROP_HIDDEN,true);
      }
   }
}

int IndexOfSymbol(const string symbol){for(int i=0;i<ArraySize(g_symbols);i++)if(g_symbols[i]==symbol)return i;return -1;}

bool AllDataReady(){
   if(ArraySize(g_symbols)==0)return false;
   for(int i=0;i<ArraySize(g_symbols);i++)if(g_symbols[i]==""||!g_data_ready[i])return false;
   return true;
}

void RenderSelected(){
   if(g_selected<0||g_selected>=ArraySize(g_symbols))return;
   if(g_ui.Tab()==AS_TAB_SIGNAL)g_ui.SignalDetail(g_cached_signal[g_selected]);
   if(g_ui.Tab()==AS_TAB_RISK)g_ui.RiskDetail(g_current_plan,(g_current_plan.valid?"Preview valid. DEMO confirmation required.":"No valid preview."),g_current_plan.valid&&InpRunMode==AS_MODE_DEMO_CONFIRM);
}

int OnInit(){
   if(InpRiskPercent<=0||InpRiskPercent>AS_MAXIMUM_RISK_PERCENT)return INIT_PARAMETERS_INCORRECT;
   string raw[];int n=StringSplit(InpSymbols,',',raw);if(n<=0)return INIT_PARAMETERS_INCORRECT;
   ArrayResize(g_requested,n);ArrayResize(g_symbols,n);ArrayResize(g_last_alert,n);ArrayResize(g_spreads,n);
   ArrayResize(g_bar_h4,n);ArrayResize(g_bar_h1,n);ArrayResize(g_bar_m15,n);ArrayResize(g_bar_m5,n);
   ArrayResize(g_h4,n);ArrayResize(g_h1,n);ArrayResize(g_m15,n);ArrayResize(g_m5,n);
   ArrayResize(g_cached_signal,n);ArrayResize(g_cached_regime,n);ArrayResize(g_cached_spec,n);ArrayResize(g_data_ready,n);
   for(int i=0;i<n;i++){
      g_requested[i]=raw[i];StringTrimLeft(g_requested[i]);StringTrimRight(g_requested[i]);
      string resolved="";if(!g_resolver.Resolve(g_requested[i],resolved))PrintFormat("Alikhande unresolved symbol '%s'",g_requested[i]);
      g_symbols[i]=resolved;g_spreads[i]=new AS_SpreadTracker();g_data_ready[i]=false;
   }
   g_parameter_hash=CurrentParameterHash();
   bool db_ok=g_db.Open();if(!db_ok)g_breaker.Trip("DB_NOT_READY");
   g_repo.Attach(g_db);g_lifecycle.Attach(g_repo);g_outcomes.Attach(g_repo);g_execution.Attach(g_repo);
   g_account_guard.Initialize();g_ui.Build();
   EventSetMillisecondTimer((int)MathMax(100,InpScanTimerMs));
   PrintFormat("%s %s initialized mode=%s parameter_hash=%s",AS_PRODUCT_NAME,AS_VERSION,EnumToString(InpRunMode),g_parameter_hash);
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason){
   EventKillTimer();
   for(int i=0;i<ArraySize(g_spreads);i++)if(CheckPointer(g_spreads[i])==POINTER_DYNAMIC)delete g_spreads[i];
   g_db.Close();g_ui.Clear();
}

void ScanOne(const int i){
   g_data_ready[i]=false;
   string sym=g_symbols[i];if(sym=="")return;

   AS_SymbolSpec spec;if(!g_spec_reader.Read(sym,spec))return;
   string previous_spec=g_repo.LatestSpecHash(sym);
   if(previous_spec=="")g_repo.SaveSpec(spec);
   else if(previous_spec!=spec.spec_hash){g_repo.SaveSpec(spec);g_repo.RuntimeEvent("WARN","Broker","SPEC_DRIFT",sym+" broker specification changed");}
   g_cached_spec[i]=spec;

   AS_SymbolSnapshot snap;if(!g_data.Snapshot(g_requested[i],sym,InpMaximumTickAgeSeconds,snap))return;
   if(snap.spread_state!=AS_SPREAD_STALE){g_spreads[i].Add(snap.spread_points);snap.spread_state=g_spreads[i].Classify(snap.spread_points,InpSpreadWarmupSamples,snap.spread_ratio);}
   ENUM_AS_DATA_STATE ds;if(!g_data.EnsureAllReady(sym,InpMinimumBars,ds))return;
   g_data_ready[i]=true;

   bool c4=false,c1=false,c15=false,c5=false;
   if(!RefreshTrend(sym,PERIOD_H4,g_bar_h4[i],g_h4[i],c4)||!RefreshTrend(sym,PERIOD_H1,g_bar_h1[i],g_h1[i],c1)||
      !RefreshTrend(sym,PERIOD_M15,g_bar_m15[i],g_m15[i],c15)||!RefreshTrend(sym,PERIOD_M5,g_bar_m5[i],g_m5[i],c5))return;

   AS_RegimeResult regime;g_regime_engine.Evaluate(g_h4[i],g_h1[i],g_m15[i],snap,regime);
   string news_reason="";
   bool calendar_block=false;
   if(InpEnableNewsGate)calendar_block=g_news.BlockedNow(sym,InpNewsBlockBeforeMinutes,InpNewsBlockAfterMinutes,news_reason);
   bool news_unavailable=InpEnableNewsGate && !calendar_block && news_reason!="";
   bool news_block=calendar_block||news_unavailable;
   if(news_block){regime.regime=AS_REGIME_NEWS_RISK;regime.tradable=false;regime.reasons+=(news_reason==""?"NEWS_BLOCK":news_reason)+";";}
   g_cached_regime[i]=regime;

   bool tracking_active=(g_cached_signal[i].state==AS_SIGNAL_ACTIVE && !SignalTerminal(g_cached_signal[i]));
   if(tracking_active){
      g_outcomes.Update(g_cached_signal[i]);
      tracking_active=(g_cached_signal[i].state==AS_SIGNAL_ACTIVE && !SignalTerminal(g_cached_signal[i]));
   }

   if(!tracking_active && (c4||c1||c15||c5||g_cached_signal[i].confirmation_bar_time==0)){
      AS_Zone zones[];g_zones.Build(sym,PERIOD_H1,300,3,3,0.20,zones);
      AS_SignalCandidate s;ZeroMemory(s);
      if(g_signal_engine.Evaluate(sym,g_h4[i],g_h1[i],g_m15[i],g_m5[i],snap,zones,regime,spec,s)){
         s.parameter_hash=g_parameter_hash;
         bool fresh=g_lifecycle.Register(s);
         if(fresh||g_cached_signal[i].signal_id=="")g_cached_signal[i]=s;
         if(fresh&&(s.direction==AS_DIR_LONG||s.direction==AS_DIR_SHORT)){
            if(InpRunMode==AS_MODE_SHADOW)g_lifecycle.Activate(g_cached_signal[i]);
            if(InpEnableAlerts&&TimeCurrent()-g_last_alert[i]>=InpAlertCooldownMinutes*60){
               Alert(StringFormat("%s %s L%.0f/S%.0f %s",sym,EnumToString(s.direction),s.long_score,s.short_score,EnumToString(regime.regime)));
               g_last_alert[i]=TimeCurrent();
            }
         }
      }
   }

   if(g_cached_signal[i].state==AS_SIGNAL_ACTIVE)g_outcomes.Update(g_cached_signal[i]);
   string status=(g_cached_signal[i].direction==AS_DIR_NONE?"WATCH":"READY");
   if(g_cached_signal[i].hard_blocked||news_block)status="BLOCKED";
   string news_label=(calendar_block?"HIGH":(news_unavailable?"N/A":"CLEAR"));
   g_ui.Row(i,sym,snap.spread_points,regime,g_cached_signal[i],news_label,status);
}

void OnTimer(){
   int total=ArraySize(g_symbols);if(total==0)return;
   g_execution.Reconcile();
   ulong started=GetMicrosecondCount();int processed=0,limit=(int)MathMin(InpSymbolsPerSlice,total);
   while(processed<limit){
      if(processed>0&&GetMicrosecondCount()-started>=(ulong)MathMax(1000,InpScanBudgetMicroseconds))break;
      int i=(g_cursor+processed)%total;processed++;ScanOne(i);
   }
   if(processed>0)g_cursor=(g_cursor+processed)%total;
   string risk_codes="";if(!g_account_guard.Check(InpEnableAccountRiskGuards,risk_codes))g_breaker.Trip("ACCOUNT_RISK_GUARD");
   AS_HealthSnapshot h=g_capabilities.Inspect(g_db.Ready(),AllDataReady(),g_execution.HasUnresolved());
   if(g_ui.Tab()==AS_TAB_SYSTEM)g_ui.System(h,StringFormat("Open risk %.2f%% | Breaker %s %s",g_portfolio.ScannerOpenRiskPct(AS_MAGIC),g_breaker.Blocked()?"ON":"OFF",g_breaker.Reasons()));
   RenderSelected();ChartRedraw();
}

void OnChartEvent(const int id,const long &lparam,const double &dparam,const string &sparam){
   if(id!=CHARTEVENT_OBJECT_CLICK)return;
   ENUM_AS_TAB tab;if(g_ui.ParseTab(sparam,tab)){g_ui.SetTab(tab);RenderSelected();return;}
   string symbol;
   if(g_ui.ParseOpen(sparam,symbol)){
      int oi=IndexOfSymbol(symbol);OpenManagedChart(symbol,PERIOD_M15);
      long cid=FindExistingChart(symbol,PERIOD_M15,InpChartReuseMode==AS_MANAGED_ONLY);
      if(cid>0&&oi>=0)g_overlay.Draw(cid,g_cached_signal[oi]);return;
   }
   if(g_ui.ParseDetail(sparam,symbol)){g_selected=IndexOfSymbol(symbol);g_ui.SetTab(AS_TAB_SIGNAL);RenderSelected();return;}
   if(g_ui.ParsePreview(sparam,symbol)){
      int i=IndexOfSymbol(symbol);if(i<0)return;g_selected=i;ZeroMemory(g_current_plan);string reason="";
      bool ok=g_risk_planner.Build(g_cached_signal[i],g_cached_spec[i],InpRiskPercent,AS_DEFAULT_PREVIEW_TTL_SECONDS,AS_DEFAULT_MAX_DRIFT_POINTS,g_current_plan);
      if(ok)ok=g_portfolio.AllowNewRisk(g_current_plan.risk_percent,InpMaxTotalOpenRiskPct,AS_MAGIC,reason);
      if(ok)g_repo.SavePlan(g_current_plan);else g_current_plan.valid=false;
      g_ui.SetTab(AS_TAB_RISK);g_ui.RiskDetail(g_current_plan,ok?"Preview valid. DEMO confirmation required.":reason,false);return;
   }
   if(g_ui.ParseExecute(sparam,symbol)){
      if(InpRunMode!=AS_MODE_DEMO_CONFIRM||!g_current_plan.valid||g_current_plan.symbol!=symbol||g_breaker.Blocked())return;
      string reason="";g_execution.SubmitDemo(g_current_plan,reason);g_ui.SetTab(AS_TAB_SYSTEM);return;
   }
}

void OnTradeTransaction(const MqlTradeTransaction &trans,const MqlTradeRequest &request,const MqlTradeResult &result){
   g_execution.OnTransaction(trans,request,result);
   if(trans.type==TRADE_TRANSACTION_DEAL_ADD&&trans.deal>0&&HistoryDealSelect(trans.deal)){
      if((ulong)HistoryDealGetInteger(trans.deal,DEAL_MAGIC)!=AS_MAGIC)return;
      long entry=HistoryDealGetInteger(trans.deal,DEAL_ENTRY);
      if(entry==DEAL_ENTRY_OUT||entry==DEAL_ENTRY_OUT_BY){
         double net=HistoryDealGetDouble(trans.deal,DEAL_PROFIT)+HistoryDealGetDouble(trans.deal,DEAL_COMMISSION)+HistoryDealGetDouble(trans.deal,DEAL_SWAP);
         g_account_guard.RegisterClosedProfit(net);
      }
   }
}
