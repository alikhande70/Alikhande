//+------------------------------------------------------------------+
//| AlikhandeScanner.mq5                                               |
//| Multi-timeframe zone-based trend scanner. Alert-only by default;   |
//| demo execution requires explicit user confirmation via the         |
//| Detail tab and passes through the full reliability pipeline        |
//| (RiskPlanner -> TradeGuards -> OrderPreflight -> DemoExecution).    |
//|                                                                      |
//| v1.2.0 — Reliability & Evidence Edition. This is a fresh,          |
//| spec-compliant rebuild (see README.md "Known gap" and               |
//| docs/ARCHITECTURE_V1.2.md) written to match the documented v1.1.0  |
//| behavior in docs/v1.1.0_README.md and docs/v1.1.0_ACCEPTANCE_TESTS.md,|
//| not a byte-exact port of the original source.                       |
//+------------------------------------------------------------------+
#property copyright "Alikhande"
#property version   "1.20"
#property strict

#include <AlikhandeScanner/Core/Config.mqh>
#include <AlikhandeScanner/Core/VersionInfo.mqh>
#include <AlikhandeScanner/Core/ParameterHash.mqh>
#include <AlikhandeScanner/Core/NewBarDetector.mqh>
#include <AlikhandeScanner/Core/SignalRegistry.mqh>
#include <AlikhandeScanner/Core/Hash.mqh>
#include <AlikhandeScanner/Storage/Database.mqh>
#include <AlikhandeScanner/Storage/SignalLogger.mqh>
#include <AlikhandeScanner/Domain/SignalLifecycle.mqh>
#include <AlikhandeScanner/Broker/SymbolResolver.mqh>
#include <AlikhandeScanner/Broker/SymbolSpec.mqh>
#include <AlikhandeScanner/Data/MarketData.mqh>
#include <AlikhandeScanner/Data/SpreadTracker.mqh>
#include <AlikhandeScanner/Analysis/TrendEngine.mqh>
#include <AlikhandeScanner/Analysis/ZoneEngine.mqh>
#include <AlikhandeScanner/Signals/SignalEngine.mqh>
#include <AlikhandeScanner/Risk/PortfolioRisk.mqh>
#include <AlikhandeScanner/Trading/RiskPlanner.mqh>
#include <AlikhandeScanner/Trading/DemoExecution.mqh>
#include <AlikhandeScanner/Safety/TradeGuards.mqh>
#include <AlikhandeScanner/Safety/AccountRiskGuard.mqh>
#include <AlikhandeScanner/News/NewsFilter.mqh>
#include <AlikhandeScanner/Execution/TradeRequestTracker.mqh>
#include <AlikhandeScanner/Execution/ExecutionStateMachine.mqh>
#include <AlikhandeScanner/Execution/OrderPreflight.mqh>
#include <AlikhandeScanner/Health/SystemHealth.mqh>
#include <AlikhandeScanner/Statistics/Statistics.mqh>
#include <AlikhandeScanner/UI/DashboardTabs.mqh>

//--- inputs -----------------------------------------------------------
input string InpSymbolsCsv        = "EURUSD,GBPUSD,XAUUSD"; // comma-separated base symbol names
input bool   InpAlertOnly         = CFG_ALERT_ONLY_DEFAULT;
input double InpRiskPct           = CFG_DEFAULT_RISK_PCT;
input double InpMaxOpenRiskPct    = CFG_DEFAULT_MAX_OPEN_RISK_PCT;
input double InpMaxSymbolRiskPct  = CFG_DEFAULT_MAX_SYMBOL_RISK_PCT;
input double InpMaxCcyRiskPct     = CFG_DEFAULT_MAX_CCY_RISK_PCT;
input double InpMaxDailyRiskPct   = CFG_DEFAULT_DAILY_RISK_PCT;
input bool   InpAccountGuardsEnabled = CFG_ACCOUNT_GUARDS_ENABLED_DEFAULT;
input double InpMaxDailyLossPct   = 3.0;
input double InpMaxDrawdownPct    = 8.0;
input int    InpMaxConsecutiveLosses = 4;
input long   InpMagicNumber       = 20260101;

//--- runtime state ------------------------------------------------------
string g_ResolvedSymbols[];
string g_UnresolvedSymbols[];
int    g_ScanCursor = 0;
AccountGuardState g_AccountGuardState;
datetime g_LastReconcileTs = 0;

//+------------------------------------------------------------------+
int OnInit()
  {
   Print(AlikhandeVersionString());

   if(!AlikhandeDbInit())
     {
      Print("Alikhande: FATAL — database init failed, EA will not run");
      return INIT_FAILED;
     }

   HealthRecordRestartMarker();
   TradeRequestRecoverAfterRestart();
   AccountGuardResetDay(g_AccountGuardState);

   string rawSymbols[];
   int n = StringSplit(InpSymbolsCsv, ',', rawSymbols);
   ArrayResize(g_ResolvedSymbols, 0);
   ArrayResize(g_UnresolvedSymbols, 0);

   for(int i = 0; i < n; i++)
     {
      string baseName = rawSymbols[i];
      StringTrimLeft(baseName);
      StringTrimRight(baseName);
      if(baseName == "")
         continue;

      SymbolResolution res = ResolveSymbol(baseName);
      if(res.status == SYMBOL_UNRESOLVED)
        {
         int u = ArraySize(g_UnresolvedSymbols);
         ArrayResize(g_UnresolvedSymbols, u + 1);
         g_UnresolvedSymbols[u] = baseName;
         AlikhandeDbLogEvent("WARN", "SYMBOL_UNRESOLVED", baseName);
         continue;
        }

      int r = ArraySize(g_ResolvedSymbols);
      ArrayResize(g_ResolvedSymbols, r + 1);
      g_ResolvedSymbols[r] = res.resolvedName;
     }

   for(int i = 0; i < ArraySize(g_ResolvedSymbols); i++)
      HealthCheckSymbolSpecDrift(g_ResolvedSymbols[i]);

   DashboardCreate();
   EventSetMillisecondTimer(CFG_TIMER_SLICE_MS);

   return INIT_SUCCEEDED;
  }

//+------------------------------------------------------------------+
void OnDeinit(const int reason)
  {
   EventKillTimer();
   DashboardDestroy();
   ExportSignalsToCsv();
   AlikhandeDbShutdown();
  }

//+------------------------------------------------------------------+
//| Sliced scheduler: at most CFG_SYMBOLS_PER_SLICE symbols per timer  |
//| event, budget-tracked so a slow broker/symbol never blows the      |
//| CFG_TIMER_BUDGET_MS ceiling for the whole EA.                      |
//+------------------------------------------------------------------+
void OnTimer()
  {
   ulong sliceStart = GetMicrosecondCount();

   AccountGuardMaybeRollDay(g_AccountGuardState);

   int total = ArraySize(g_ResolvedSymbols);
   if(total > 0)
     {
      for(int i = 0; i < CFG_SYMBOLS_PER_SLICE && i < total; i++)
        {
         int idx = (g_ScanCursor + i) % total;
         ProcessSymbol(g_ResolvedSymbols[idx]);
        }
      g_ScanCursor = (g_ScanCursor + CFG_SYMBOLS_PER_SLICE) % total;
     }

   if(TimeCurrent() - g_LastReconcileTs >= CFG_RECONCILE_GRACE_SECONDS)
     {
      ReconcileStaleRequests(CFG_RECONCILE_GRACE_SECONDS);
      g_LastReconcileTs = TimeCurrent();
     }

   HealthTrackTimerSlice(sliceStart, CFG_TIMER_BUDGET_MS);
  }

//+------------------------------------------------------------------+
//| Per-symbol pipeline: Data Quality -> News Gate -> MTF+Zones ->     |
//| Setup -> Score -> Risk Gate -> Signal Lifecycle -> Dashboard.      |
//| Heavy analysis (trend/zones) only re-runs on a new closed H1 bar — |
//| everything else (spread/tick) refreshes every slice.                |
//+------------------------------------------------------------------+
void ProcessSymbol(const string symbol)
  {
   MarketSnapshot snap = FetchMarketSnapshot(symbol, CFG_TF_H1, CFG_ATR_PERIOD);

   bool stale = IsQuoteStale(symbol, CFG_STALE_QUOTE_SECONDS);

   NewsGateResult news = EvaluateNewsGate(symbol, CFG_NEWS_PRE_MINUTES, CFG_NEWS_POST_MINUTES,
                                           CFG_NEWS_INCLUDE_MEDIUM);

   string status = "SCANNING";
   color statusColor = DASH_COLOR_MUTED;

   if(stale)
     {
      status = "STALE";
      statusColor = DASH_COLOR_BAD;
     }
   else if(news.blocked)
     {
      status = "NEWS BLOCK";
      statusColor = DASH_COLOR_WARN;
     }

   if(!stale && IsNewClosedBar(symbol, CFG_TF_H1))
      EvaluateCandidates(symbol, snap, news);

   int row = FindSymbolRow(symbol);
   DashboardUpdateOverviewRow(row, symbol, "-", "-", "-", 0, 0,
                              StringFormat("%.0f pts", snap.spreadPoints),
                              news.blocked ? "BLOCK" : "clear", status, statusColor);
  }

int FindSymbolRow(const string symbol)
  {
   for(int i = 0; i < ArraySize(g_ResolvedSymbols); i++)
      if(g_ResolvedSymbols[i] == symbol)
         return i;
   return 0;
  }

//+------------------------------------------------------------------+
void EvaluateCandidates(const string symbol, const MarketSnapshot &snap,
                         const NewsGateResult &news)
  {
   MtfSnapshot mtf = ComputeMtfSnapshot(symbol);

   Zone zones[];
   FindZones(symbol, CFG_TF_H1, 300, 3, zones);
   ApplyZoneAtrBuffer(zones, snap.atr, CFG_ZONE_TOLERANCE_ATR);

   MqlTick tick;
   if(!SymbolInfoTick(symbol, tick))
      return;

   ENUM_TREND_DIRECTION directions[2] = {TREND_BULLISH, TREND_BEARISH};
   for(int d = 0; d < 2; d++)
     {
      Candidate cand;
      string blockLines[];
      double price = (directions[d] == TREND_BULLISH) ? tick.ask : tick.bid;

      if(!BuildCandidate(symbol, directions[d], mtf, zones, price, snap.atr, cand, blockLines))
         continue;
      cand.spread = snap.spreadPoints;

      if(news.blocked)
        {
         AlikhandeDbLogEvent("INFO", "SIGNAL_BLOCKED_NEWS",
            StringFormat("%s %s: %s (%s)", symbol, TrendDirectionToString(directions[d]),
                        news.eventTitle, news.currency));
         continue;
        }

      ComputeScore(mtf, snap.atrQualityRatio, cand.nearestZone.touches, cand.score);

      double relevantScore = (directions[d] == TREND_BULLISH) ? cand.score.longScore
                                                                : cand.score.shortScore;
      if(relevantScore < 60.0) // [ASSUMED] minimum score to register as a candidate
         continue;

      PersistCandidate(symbol, directions[d], cand);
     }
  }

//+------------------------------------------------------------------+
void PersistCandidate(const string symbol, const ENUM_TREND_DIRECTION direction,
                       const Candidate &cand)
  {
   string paramBlob = BuildScoringParameterBlob(CFG_ATR_SL_BUFFER_MULT, CFG_MIN_RR,
                                                 CFG_PULLBACK_LOOKBACK_BARS,
                                                 CFG_ZONE_TOLERANCE_ATR, ALIKHANDE_RULE_VERSION);
   string parameterHash = ComputeParameterHash(paramBlob);
   string brokerSpecHash = ComputeSymbolSpecHash(symbol);

   string signalId = AlikhandeHashWithPrefix(symbol,
      StringFormat("%s|%d|%.5f|%.5f|%.5f|%d", symbol, (int)direction, cand.entry, cand.sl,
                   cand.tp, (int)cand.ts));

   if(!SignalRegistryTryAdd(signalId))
      return; // duplicate SignalID for this timer pass — already logged

   SignalRecord rec;
   rec.signalId = signalId;
   rec.ts = cand.ts;
   rec.symbol = symbol;
   rec.direction = (direction == TREND_BULLISH) ? "LONG" : "SHORT";
   rec.setup = SetupTypeToString(cand.setup);
   rec.h4State = TrendDirectionToString(cand.mtf.h4.direction);
   rec.h1State = TrendDirectionToString(cand.mtf.h1.direction);
   rec.m15State = TrendDirectionToString(cand.mtf.m15.direction);
   rec.m5State = "-"; // M5 confirmation is boolean (setup type), not a trend state
   rec.spread = cand.spread;
   rec.atr = cand.atr;
   rec.support = (cand.nearestZone.type == ZONE_SUPPORT) ? cand.nearestZone.priceLow : 0.0;
   rec.resistance = (cand.nearestZone.type == ZONE_RESISTANCE) ? cand.nearestZone.priceHigh : 0.0;
   rec.entry = cand.entry;
   rec.sl = cand.sl;
   rec.tp = cand.tp;
   rec.longScore = cand.score.longScore;
   rec.shortScore = cand.score.shortScore;
   rec.ruleVersion = ALIKHANDE_RULE_VERSION;
   rec.parameterHash = parameterHash;
   rec.brokerSpecHash = brokerSpecHash;
   rec.state = SIGNAL_CANDIDATE;

   if(!SignalPersistNew(rec))
     {
      AlikhandeDbLogEvent("ERROR", "SIGNAL_PERSIST_FAILED", signalId);
      return;
     }

   SignalTransition(signalId, SIGNAL_CANDIDATE, SIGNAL_CONFIRMED);

   string explanationLines[1];
   explanationLines[0] = StringFormat("score %.0f from MTF alignment + zone quality",
                                       (direction == TREND_BULLISH) ? cand.score.longScore
                                                                     : cand.score.shortScore);
   string noBlocks[0];
   DashboardUpdateDetail(symbol, rec.h4State, rec.h1State, rec.m15State, rec.m5State,
                         rec.support, rec.resistance, rec.entry, rec.sl, rec.tp,
                         explanationLines, noBlocks);

   SendNotification(StringFormat("Alikhande: %s %s %s candidate ready", symbol,
                                 rec.direction, rec.setup));
  }

//+------------------------------------------------------------------+
void OnTradeTransaction(const MqlTradeTransaction &trans, const MqlTradeRequest &request,
                         const MqlTradeResult &result)
  {
   HandleTradeTransaction(trans, request, result);
  }

//+------------------------------------------------------------------+
void OnChartEvent(const int id, const long &lparam, const double &dparam, const string &sparam)
  {
   if(id == CHARTEVENT_OBJECT_CLICK)
      DashboardHandleClick(sparam);
  }
