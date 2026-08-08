#property strict
#property version   "1.30"
#property description "Alikhande Scanner MT5 v1.3.0 - Evidence Integrity edition"
#property description "Alert-only by default. Real accounts are blocked unconditionally."

#include <AlikhandeScanner/Core/Config.mqh>
#include <AlikhandeScanner/Core/VersionInfo.mqh>
#include <AlikhandeScanner/Core/Log.mqh>
#include <AlikhandeScanner/Core/RuntimeContext.mqh>
#include <AlikhandeScanner/Domain/Models.mqh>
#include <AlikhandeScanner/Persistence/PersistencePolicy.mqh>
#include <AlikhandeScanner/Persistence/Database.mqh>
#include <AlikhandeScanner/Persistence/Repositories.mqh>
#include <AlikhandeScanner/Broker/SymbolResolver.mqh>
#include <AlikhandeScanner/Broker/SymbolSpec.mqh>
#include <AlikhandeScanner/Data/IndicatorCache.mqh>
#include <AlikhandeScanner/Data/MarketData.mqh>
#include <AlikhandeScanner/Data/SpreadTracker.mqh>
#include <AlikhandeScanner/Analysis/TrendEngine.mqh>
#include <AlikhandeScanner/Analysis/ZoneEngine.mqh>
#include <AlikhandeScanner/Analysis/RegimeEngine.mqh>
#include <AlikhandeScanner/Signals/SignalEngine.mqh>
#include <AlikhandeScanner/Signals/SignalLifecycle.mqh>
#include <AlikhandeScanner/Statistics/Statistics.mqh>
#include <AlikhandeScanner/Risk/RiskPlanner.mqh>
#include <AlikhandeScanner/Risk/PortfolioRisk.mqh>
#include <AlikhandeScanner/Risk/TradeGuards.mqh>
#include <AlikhandeScanner/Risk/AccountRiskGuard.mqh>
#include <AlikhandeScanner/News/CalendarGate.mqh>
#include <AlikhandeScanner/Execution/ArmedIntent.mqh>
#include <AlikhandeScanner/Execution/ExecutionEngine.mqh>
#include <AlikhandeScanner/UI/Dashboard.mqh>

//--- inputs -----------------------------------------------------------------
input string           InpSymbols                = AS_DEFAULT_SYMBOLS;
input ENUM_AS_RUN_MODE InpRunMode                = AS_MODE_ALERT_ONLY;
input int              InpScanTimerMs            = AS_DEFAULT_SCAN_TIMER_MS;
input int              InpScanBudgetMicroseconds = AS_DEFAULT_SCAN_BUDGET_US;
input int              InpSymbolsPerSlice        = AS_DEFAULT_SYMBOLS_PER_SLICE;
input int              InpMinimumBars            = AS_DEFAULT_MINIMUM_BARS;
input int              InpSpreadWarmupSamples    = AS_DEFAULT_SPREAD_WARMUP_SAMPLES;
input int              InpMaximumTickAgeSeconds  = AS_DEFAULT_MAX_TICK_AGE_SECONDS;
input double           InpRiskPercent            = AS_DEFAULT_RISK_PERCENT;
input double           InpMaxOpenRiskPercent     = AS_DEFAULT_MAX_OPEN_RISK_PCT;
input double           InpMaxCurrencyRiskPercent = AS_DEFAULT_MAX_CURRENCY_RISK_PCT;
input double           InpMaxAssetClassRiskPct   = AS_DEFAULT_MAX_ASSET_CLASS_RISK_PCT;
input bool             InpEnableAccountGuards    = false;
input bool             InpEnableAlerts           = true;
input int              InpAlertCooldownMinutes   = 30;
input ENUM_AS_CHART_REUSE InpChartReuseMode      = AS_CHART_MANAGED_ONLY;
input bool             InpEnableNewsGate         = true;
input int              InpNewsPreMinutes         = AS_NEWS_PRE_MINUTES;
input int              InpNewsPostMinutes        = AS_NEWS_POST_MINUTES;
input bool             InpNewsIncludeMedium      = false;

//--- collaborators -----------------------------------------------------------
AS_Log              g_log;
AS_RuntimeProbe     g_runtime_probe;
AS_RuntimeContext   g_runtime;
AS_PersistencePolicy g_persistence_policy;
AS_PersistencePlan  g_persistence;
AS_Database         g_database;
AS_Repositories     g_repo;
AS_SymbolResolver   g_resolver;
AS_SymbolSpecReader g_spec_reader;
AS_IndicatorCache   g_indicators;
AS_MarketData       g_market;
AS_TrendEngine      g_trend;
AS_ZoneEngine       g_zones;
AS_RegimeEngine     g_regime;
AS_SignalEngine     g_signal;
AS_Statistics       g_statistics;
AS_RiskPlanner      g_risk_planner;
AS_TradeGuards      g_trade_guards;
AS_AccountRiskGuard g_account_guard;
AS_CalendarGate     g_calendar;
AS_IntentArming     g_arming;
AS_ExecutionEngine  g_execution;
AS_Dashboard        g_ui;

//--- per-symbol state --------------------------------------------------------
string               g_requested[];
string               g_symbols[];
AS_SpreadTracker    *g_spreads[];
AS_StructuralContext g_context[];
AS_SignalCandidate   g_signal_cache[];
AS_NewsVerdict       g_news_cache[];
AS_NewsVerdict       g_news_disabled;
AS_TradePlan         g_plan_cache[];
datetime             g_last_alert[];
datetime             g_bar_h4[], g_bar_h1[], g_bar_m15[], g_bar_m5[];

int      g_cursor = 0;
int      g_unresolved = 0;
double   g_last_slice_ms = 0.0;
datetime g_last_reconcile = 0;

//+------------------------------------------------------------------+
string TrendText(const ENUM_AS_TREND_CLASS trend)
  {
   switch(trend)
     {
      case AS_STRONG_BULLISH: return "STR BULL";
      case AS_BULLISH:        return "BULL";
      case AS_WEAK_BULLISH:   return "WK BULL";
      case AS_STRONG_BEARISH: return "STR BEAR";
      case AS_BEARISH:        return "BEAR";
      case AS_WEAK_BEARISH:   return "WK BEAR";
     }
   return "NEUTRAL";
  }

string SetupText(const ENUM_AS_SETUP_TYPE setup)
  {
   switch(setup)
     {
      case AS_TREND_PULLBACK:       return "Pullback";
      case AS_SUPPORT_REJECTION:    return "S.Reject";
      case AS_RESISTANCE_REJECTION: return "R.Reject";
      case AS_BREAKOUT_RETEST:      return "Retest";
     }
   return "-";
  }

string RunModeText(const ENUM_AS_RUN_MODE mode)
  {
   switch(mode)
     {
      case AS_MODE_ALERT_ONLY: return "ALERT-ONLY";
      case AS_MODE_SHADOW:     return "SHADOW";
      case AS_MODE_DEMO_CONFIRM: return "DEMO-CONFIRM";
     }
   return "?";
  }

//+------------------------------------------------------------------+
//| Managed chart handling. The marker object lets the EA recognise a |
//| chart it opened, so repeated clicks reuse it instead of stacking  |
//| duplicate windows.                                                 |
//+------------------------------------------------------------------+
bool IsManagedChart(const long chart_id)
  {
   return ObjectFind(chart_id, AS_MANAGED_CHART_MARKER) >= 0;
  }

long FindExistingChart(const string symbol, const ENUM_TIMEFRAMES tf, const bool managed_only)
  {
   for(long chart_id = ChartFirst(); chart_id >= 0; chart_id = ChartNext(chart_id))
     {
      if(ChartSymbol(chart_id) != symbol || ChartPeriod(chart_id) != tf)
         continue;
      if(!managed_only || IsManagedChart(chart_id))
         return chart_id;
     }
   return -1;
  }

void OpenManagedChart(const string symbol, const ENUM_TIMEFRAMES tf)
  {
   long chart_id = -1;
   if(InpChartReuseMode == AS_CHART_MANAGED_ONLY)
      chart_id = FindExistingChart(symbol, tf, true);
   else if(InpChartReuseMode == AS_CHART_REUSE_ANY_MATCHING)
      chart_id = FindExistingChart(symbol, tf, false);

   if(chart_id < 0)
      chart_id = ChartOpen(symbol, tf);
   if(chart_id <= 0)
      return;

   ChartSetInteger(chart_id, CHART_BRING_TO_TOP, true);
   if(ObjectFind(chart_id, AS_MANAGED_CHART_MARKER) < 0)
     {
      ObjectCreate(chart_id, AS_MANAGED_CHART_MARKER, OBJ_LABEL, 0, 0, 0);
      ObjectSetString(chart_id, AS_MANAGED_CHART_MARKER, OBJPROP_TEXT, "");
      ObjectSetInteger(chart_id, AS_MANAGED_CHART_MARKER, OBJPROP_COLOR, clrNONE);
      ObjectSetInteger(chart_id, AS_MANAGED_CHART_MARKER, OBJPROP_HIDDEN, true);
     }
  }

//+------------------------------------------------------------------+
//| Structure is rebuilt only when a closed bar changed on one of the  |
//| analysed timeframes. Everything else runs every pass.              |
//+------------------------------------------------------------------+
bool ClosedBarChanged(const string symbol, const ENUM_TIMEFRAMES tf, datetime &last_seen)
  {
   const datetime closed = iTime(symbol, tf, 1);
   if(closed <= 0)
      return false;
   if(closed == last_seen)
      return false;
   last_seen = closed;
   return true;
  }

//+------------------------------------------------------------------+
int OnInit()
  {
   g_log.SetMinimumLevel(AS_LOG_INFO);
   g_indicators.Attach(g_log);
   g_resolver.Attach(g_log);
   g_spec_reader.Attach(g_log);
   g_market.Attach(g_log);
   g_database.Attach(g_log);
   g_trend.Attach(g_indicators);
   g_zones.Attach(g_indicators);

   // Classify the runtime BEFORE touching persistence. A backtest and an
   // optimization sweep produce records indistinguishable from live ones; if
   // they share a database file, every statistic computed later is measuring a
   // mixture of live scanning and whatever sweep happened to run that day.
   g_runtime = g_runtime_probe.Detect();
   g_persistence = g_persistence_policy.Plan(g_runtime);

   g_log.Info("RUNTIME", "",
              StringFormat("%s (%s) persistence=%s [%s]",
                           AS_RuntimeKindName(g_runtime.kind), g_runtime.description,
                           g_persistence.enabled ? g_persistence.filename : "disabled",
                           g_persistence.rationale));

   if(g_persistence.enabled && !g_database.Open(g_persistence.filename))
     {
      if(g_persistence.required)
        {
         // Production only. Without persistence there is no de-duplication
         // across restarts, no risk-state continuity and no outcome history,
         // so running anyway would produce data that cannot be trusted.
         Print("Alikhande: FATAL - production database unavailable, refusing to start");
         return INIT_FAILED;
        }
      g_log.Warn("DB_UNAVAILABLE", "",
                 "continuing without persistence; this run leaves no record");
     }
   g_repo.Attach(g_database, g_log);

   // Stamp the runtime into the event log too. The filename already separates
   // contexts, but a database that gets copied or renamed should still be able
   // to say what produced it.
   g_repo.LogEvent("INFO", "RUNTIME", AS_RuntimeKindName(g_runtime.kind),
                   StringFormat("production=%s %s",
                                g_runtime.is_production ? "yes" : "no",
                                g_runtime.description));
   g_statistics.Attach(g_repo);
   ZeroMemory(g_news_disabled);
   g_news_disabled.state = AS_NEWS_CLEAR;
   g_news_disabled.source = AS_NEWS_SOURCE_UNAVAILABLE;
   g_news_disabled.reason = "news gate disabled by input";
   g_arming.Attach(g_log);
   g_calendar.Attach(g_log);
   g_calendar.ApplyRuntimePolicy(g_runtime);
   g_account_guard.Attach(g_repo, g_log);
   g_execution.Attach(g_repo, g_log, AS_MAGIC);

   string raw[];
   const int requested_count = StringSplit(InpSymbols, ',', raw);
   if(requested_count <= 0)
      return INIT_PARAMETERS_INCORRECT;

   ArrayResize(g_requested, requested_count);
   ArrayResize(g_symbols, requested_count);
   ArrayResize(g_spreads, requested_count);
   ArrayResize(g_context, requested_count);
   ArrayResize(g_signal_cache, requested_count);
   ArrayResize(g_news_cache, requested_count);
   ArrayResize(g_plan_cache, requested_count);
   ArrayResize(g_last_alert, requested_count);
   ArrayResize(g_bar_h4, requested_count);
   ArrayResize(g_bar_h1, requested_count);
   ArrayResize(g_bar_m15, requested_count);
   ArrayResize(g_bar_m5, requested_count);

   // MQL5 does not guarantee zero-initialisation of resized arrays. v1.1.0
   // omitted this, leaving the alert cooldown comparing against garbage.
   ArrayInitialize(g_last_alert, 0);
   ArrayInitialize(g_bar_h4, 0);
   ArrayInitialize(g_bar_h1, 0);
   ArrayInitialize(g_bar_m15, 0);
   ArrayInitialize(g_bar_m5, 0);

   g_unresolved = 0;
   for(int i = 0; i < requested_count; i++)
     {
      g_requested[i] = raw[i];
      StringTrimLeft(g_requested[i]);
      StringTrimRight(g_requested[i]);

      string resolved = "";
      if(!g_resolver.Resolve(g_requested[i], resolved))
         g_unresolved++;
      g_symbols[i] = resolved;

      g_spreads[i] = new AS_SpreadTracker();
      ZeroMemory(g_context[i]);
      ZeroMemory(g_signal_cache[i]);
      ZeroMemory(g_news_cache[i]);
      ZeroMemory(g_plan_cache[i]);

      // Seed the drift baseline from persisted state so a specification
      // change across a restart is still detected.
      if(resolved != "")
        {
         string stored = "";
         if(g_repo.LoadSpecFingerprint(resolved, stored))
            g_spec_reader.SeedFingerprint(resolved, stored);
        }
     }

   g_account_guard.Initialize();
   g_execution.RecoverAfterRestart();

   g_ui.Create(requested_count);
   g_ui.SetMode(RunModeText(InpRunMode), InpRunMode != AS_MODE_ALERT_ONLY);

   EventSetMillisecondTimer((int)MathMax(100, InpScanTimerMs));

   g_log.Info("STARTED", "",
              StringFormat("v%s mode=%s symbols=%d unresolved=%d",
                           AS_VERSION, RunModeText(InpRunMode),
                           requested_count, g_unresolved));
   return INIT_SUCCEEDED;
  }

//+------------------------------------------------------------------+
void OnDeinit(const int reason)
  {
   EventKillTimer();

   for(int i = 0; i < ArraySize(g_spreads); i++)
      if(CheckPointer(g_spreads[i]) == POINTER_DYNAMIC)
         delete g_spreads[i];

   g_indicators.Release();
   g_ui.Destroy();
   g_database.Close();
  }

//+------------------------------------------------------------------+
void ProcessSymbol(const int index)
  {
   const string symbol = g_symbols[index];

   if(symbol == "")
     {
      g_ui.Row(index, g_requested[index], AS_REGIME_UNKNOWN, AS_DIR_NONE,
               "-", 0, 0, 0, "UNRESOLVED");
      return;
     }

   AS_SymbolSpec spec;
   if(!g_spec_reader.Read(symbol, spec))
     {
      g_ui.Row(index, symbol, AS_REGIME_UNKNOWN, AS_DIR_NONE, "-", 0, 0, 0, "SPEC WARMUP");
      return;
     }
   // Persist on first sight as well as on drift, otherwise the baseline never
   // reaches the database and cross-restart drift cannot be detected.
   if(g_spec_reader.DetectDrift(spec) != AS_SPEC_UNCHANGED)
      g_repo.SaveSpec(spec);

   AS_SymbolSnapshot snapshot;
   if(!g_market.Snapshot(g_requested[index], symbol, InpMaximumTickAgeSeconds, snapshot))
     {
      const string status = (snapshot.data_state == AS_DATA_STALE ? "STALE QUOTE" : "NO TICK");
      g_ui.Row(index, symbol, AS_REGIME_UNKNOWN, AS_DIR_NONE, "-", 0, 0,
               snapshot.spread_points, status);
      return;
     }

   g_spreads[index].Add(snapshot.spread_points);
   snapshot.spread_state = g_spreads[index].Classify(snapshot.spread_points,
                                                     InpSpreadWarmupSamples,
                                                     snapshot.spread_ratio,
                                                     snapshot.spread_percentile);

   ENUM_AS_DATA_STATE data_state;
   if(!g_market.EnsureAllReady(symbol, InpMinimumBars, data_state))
     {
      g_ui.Row(index, symbol, AS_REGIME_UNKNOWN, AS_DIR_NONE, "-", 0, 0,
               snapshot.spread_points, "LOADING");
      return;
     }

   // --- structural half: only on a new closed bar ------------------------
   // Bitwise OR, not logical: every timeframe must be evaluated so each one
   // records its own last-seen bar. Short-circuiting would leave the later
   // timeframes permanently stale once an earlier one returned true.
   const bool bar_changed = ClosedBarChanged(symbol, PERIOD_H4,  g_bar_h4[index])
                            | ClosedBarChanged(symbol, PERIOD_H1,  g_bar_h1[index])
                            | ClosedBarChanged(symbol, PERIOD_M15, g_bar_m15[index])
                            | ClosedBarChanged(symbol, PERIOD_M5,  g_bar_m5[index]);

   if(bar_changed || !g_context[index].valid)
     {
      if(!g_signal.BuildContext(symbol, g_trend, g_zones, g_regime,
                                snapshot, g_context[index]))
        {
         g_ui.Row(index, symbol, AS_REGIME_UNKNOWN, AS_DIR_NONE, "-", 0, 0,
                  snapshot.spread_points, "IND DATA");
         return;
        }
     }

   // --- live half: every pass, against the current quote ------------------
   AS_SignalCandidate candidate;
   if(!g_signal.Evaluate(g_context[index], snapshot, candidate))
      return;

   candidate.broker_spec_hash = spec.fingerprint;
   g_statistics.Enrich(candidate);

   // The calendar answers with a state AND a source. UNKNOWN is a distinct
   // third answer, never folded into CLEAR: a gate that goes quiet exactly
   // when it cannot see is worse than no gate, because it looks like one.
   const AS_NewsVerdict news = InpEnableNewsGate
                               ? g_calendar.Evaluate(symbol, g_runtime,
                                                     InpNewsPreMinutes, InpNewsPostMinutes,
                                                     InpNewsIncludeMedium)
                               : g_news_disabled;
   g_news_cache[index] = news;
   const bool news_blocks = InpEnableNewsGate && g_calendar.BlocksTrading(news);
   if(news_blocks)
     {
      candidate.hard_blocked = true;
      candidate.direction = AS_DIR_NONE;
      candidate.setup = AS_SETUP_NONE;
      candidate.validation_codes += StringFormat("NEWS_%s(%s);",
                                                 AS_NewsStateName(news.state), news.reason);
     }

   g_signal_cache[index] = candidate;

   // --- guards ------------------------------------------------------------
   string guard_codes = "";
   const bool guards_ok = g_account_guard.Check(InpEnableAccountGuards, guard_codes);

   string status;
   if(!guards_ok)
      status = "RISK HALT";
   else if(candidate.direction != AS_DIR_NONE)
      status = (candidate.direction == AS_DIR_LONG ? "LONG" : "SHORT");
   else if(candidate.hard_blocked)
      status = "BLOCKED";
   else
      status = "NO TRADE";

   g_ui.Row(index, symbol, g_context[index].regime.regime, candidate.direction,
            SetupText(candidate.setup), candidate.long_score, candidate.short_score,
            snapshot.spread_points, status);

   // --- persistence and alerting ------------------------------------------
   if(candidate.direction == AS_DIR_NONE || !guards_ok)
      return;

   // Persistent de-duplication: the same structural signal is stored once,
   // even across a restart.
   if(!g_repo.SignalExists(candidate.signal_id))
     {
      g_repo.SaveSignal(candidate, AS_SignalStateName(AS_SIGNAL_CONFIRMED));
      g_repo.SaveFeature(candidate.signal_id, "h1_direction", g_context[index].h1.direction_score);
      g_repo.SaveFeature(candidate.signal_id, "h1_adx", g_context[index].h1.adx);
      g_repo.SaveFeature(candidate.signal_id, "h1_atr_ratio", g_context[index].h1.atr_ratio);
      g_repo.SaveFeature(candidate.signal_id, "spread_ratio", snapshot.spread_ratio);
      g_repo.SaveFeature(candidate.signal_id, "spread_percentile", snapshot.spread_percentile);
      g_repo.SaveFeature(candidate.signal_id, "regime", (double)g_context[index].regime.regime);

      if(InpEnableAlerts
         && TimeCurrent() - g_last_alert[index] >= InpAlertCooldownMinutes * 60)
        {
         Alert(StringFormat("%s %s %s  score %.0f", symbol, status,
                            SetupText(candidate.setup),
                            candidate.direction == AS_DIR_LONG
                            ? candidate.long_score : candidate.short_score));
         g_last_alert[index] = TimeCurrent();
        }
     }

   // In alert-only mode nothing further happens; the plan is not even built.
   if(InpRunMode == AS_MODE_ALERT_ONLY)
      return;

   AS_TradePlan plan;
   if(!g_risk_planner.Build(candidate, InpRiskPercent, AS_DEFAULT_PREVIEW_TTL_SECONDS,
                            AS_DEFAULT_MAX_DRIFT_POINTS, InpMaxOpenRiskPercent,
                            InpMaxCurrencyRiskPercent, InpMaxAssetClassRiskPct,
                            AS_MAGIC, plan))
     {
      g_log.Info("PLAN_REJECTED", symbol, plan.validation_codes);
      return;
     }

   if(g_trade_guards.HasExposure(symbol, AS_MAGIC))
      return;

   g_repo.SavePlan(plan);
   g_plan_cache[index] = plan;

   // SHADOW exercises the whole path without sending, so it can run
   // unattended. DEMO_CONFIRM never sends from here: the plan is now
   // previewed and waits for the operator to arm and then confirm it.
   if(InpRunMode == AS_MODE_SHADOW)
     {
      string reason = "";
      if(!g_execution.Submit(plan, InpRunMode, reason))
         g_log.Info("EXECUTION_NOT_SENT", symbol, reason);
     }
  }

//+------------------------------------------------------------------+
//| Confirmation path. Reached only from a deliberate second click on |
//| an already-armed plan; nothing here runs on the timer.            |
//+------------------------------------------------------------------+
void ConfirmArmedPlan(const int index)
  {
   if(InpRunMode != AS_MODE_DEMO_CONFIRM)
      return;
   if(index < 0 || index >= ArraySize(g_plan_cache))
      return;

   AS_TradePlan plan = g_plan_cache[index];
   string reason = "";

   if(!g_arming.Confirm(plan, reason))
     {
      g_log.Warn("CONFIRM_REJECTED", plan.symbol, reason);
      return;
     }

   // Re-validated inside Submit against the live quote: arming is permission,
   // not a snapshot the market is obliged to honour.
   if(!g_execution.Submit(plan, InpRunMode, reason))
      g_log.Warn("EXECUTION_NOT_SENT", plan.symbol, reason);
   else
      g_log.Info("EXECUTION_SENT", plan.symbol,
                 StringFormat("plan %s confirmed and submitted", plan.plan_id));
  }

//+------------------------------------------------------------------+
void RefreshActiveTab()
  {
   g_ui.SetAcknowledgeAvailable(g_execution.RequiresManualReview());

   const AS_ArmedIntent intent = g_arming.Current();
   g_ui.SetArmState(g_arming.IsArmed(),
                    g_arming.IsArmed() ? (int)(intent.expires_at - TimeCurrent()) : 0,
                    intent.symbol);

   const ENUM_AS_TAB tab = g_ui.ActiveTab();
   if(tab == AS_TAB_OVERVIEW)
      return;

   if(tab == AS_TAB_DETAIL)
     {
      const string selected = g_ui.SelectedSymbol();
      for(int i = 0; i < ArraySize(g_symbols); i++)
        {
         if(g_symbols[i] != selected || selected == "")
            continue;
         g_ui.RenderDetail(g_signal_cache[i], g_context[i].regime,
                           TrendText(g_context[i].h4.trend_class),
                           TrendText(g_context[i].h1.trend_class),
                           TrendText(g_context[i].m15.trend_class),
                           TrendText(g_context[i].m5.trend_class),
                           g_news_cache[i]);
         return;
        }
      AS_SignalCandidate empty;
      ZeroMemory(empty);
      AS_RegimeResult no_regime;
      ZeroMemory(no_regime);
      AS_NewsVerdict no_news;
      ZeroMemory(no_news);
      g_ui.RenderDetail(empty, no_regime, "-", "-", "-", "-", no_news);
      return;
     }

   if(tab == AS_TAB_RISK)
     {
      const string symbol = (g_ui.SelectedSymbol() != "" ? g_ui.SelectedSymbol() : _Symbol);
      string guard_codes = "";
      g_account_guard.Check(InpEnableAccountGuards, guard_codes);
      g_ui.RenderRisk(g_risk_planner.Exposure(symbol, AS_MAGIC),
                      g_account_guard.State(), InpRiskPercent, guard_codes);
      return;
     }

   if(tab == AS_TAB_HEALTH)
     {
      const AS_ExecutionRecord execution = g_execution.Current();
      g_ui.RenderHealth(ArraySize(g_symbols), g_unresolved,
                        g_last_slice_ms, InpScanBudgetMicroseconds / 1000.0,
                        g_indicators.Count(), g_database.IsOpen(),
                        AS_ExecStateName(execution.state), g_log.SuppressedCount(),
                        AS_RuntimeKindName(g_runtime.kind), g_runtime.is_production,
                        g_persistence.enabled ? g_persistence.filename : "disabled",
                        g_execution.RequiresManualReview());
     }
  }

//+------------------------------------------------------------------+
void OnTimer()
  {
   const int total = ArraySize(g_symbols);
   if(total == 0)
      return;

   const ulong started = GetMicrosecondCount();
   const int limit = (int)MathMin(InpSymbolsPerSlice, total);
   int processed = 0;

   while(processed < limit)
     {
      // The budget is checked after the first symbol so at least one always
      // makes progress, however slow the terminal is.
      if(processed > 0
         && GetMicrosecondCount() - started >= (ulong)MathMax(1000, InpScanBudgetMicroseconds))
         break;

      ProcessSymbol((g_cursor + processed) % total);
      processed++;
     }

   if(processed > 0)
      g_cursor = (g_cursor + processed) % total;

   // Reconciliation is time-based, not event-based: transaction events can be
   // dropped when the terminal queue overflows, so nothing may depend on one.
   g_arming.Sweep();

   if(TimeCurrent() - g_last_reconcile >= AS_RECONCILE_GRACE_SECONDS)
     {
      g_execution.Reconcile();
      g_last_reconcile = TimeCurrent();
     }

   g_last_slice_ms = (double)(GetMicrosecondCount() - started) / 1000.0;
   RefreshActiveTab();
   ChartRedraw();
  }

//+------------------------------------------------------------------+
int SelectedIndex()
  {
   const string selected = g_ui.SelectedSymbol();
   if(selected == "")
      return -1;
   for(int i = 0; i < ArraySize(g_symbols); i++)
      if(g_symbols[i] == selected)
         return i;
   return -1;
  }

//+------------------------------------------------------------------+
void ArmSelectedPlan()
  {
   if(InpRunMode != AS_MODE_DEMO_CONFIRM)
     {
      g_log.Info("ARM_IGNORED", "", "arming only applies in DEMO-CONFIRM mode");
      return;
     }

   const int index = SelectedIndex();
   if(index < 0)
      return;

   if(g_execution.RequiresManualReview())
     {
      g_log.Warn("ARM_REJECTED", g_symbols[index],
                 "an earlier execution is unresolved; verify the account and "
                 "acknowledge before arming anything new");
      return;
     }
   if(!g_plan_cache[index].valid)
     {
      g_log.Info("ARM_REJECTED", g_symbols[index], "no valid plan to arm");
      return;
     }
   g_arming.Arm(g_plan_cache[index]);
  }

//+------------------------------------------------------------------+
void OnChartEvent(const int id, const long &lparam, const double &dparam, const string &sparam)
  {
   if(id != CHARTEVENT_OBJECT_CLICK)
      return;

   // Arm and Confirm are handled before tab/row routing so a click on either
   // can never also be interpreted as a navigation action.
   if(g_ui.IsAcknowledgeClick(sparam))
     {
      // Deliberate operator act: they are asserting the account was checked.
      // Recorded with that wording so the log says who decided, not just what
      // changed.
      if(g_execution.AcknowledgeUnresolved("operator confirmed account verified via dashboard"))
         g_log.Warn("SUBMISSION_UNBLOCKED", "", "unresolved execution acknowledged");
      RefreshActiveTab();
      ChartRedraw();
      return;
     }
   if(g_ui.IsArmClick(sparam))
     {
      ArmSelectedPlan();
      RefreshActiveTab();
      ChartRedraw();
      return;
     }
   if(g_ui.IsConfirmClick(sparam))
     {
      ConfirmArmedPlan(SelectedIndex());
      RefreshActiveTab();
      ChartRedraw();
      return;
     }

   int row = -1;
   if(!g_ui.HandleClick(sparam, row))
      return;

   if(row >= 0 && row < ArraySize(g_symbols) && g_symbols[row] != "")
     {
      g_ui.SetSelectedSymbol(g_symbols[row]);
      OpenManagedChart(g_symbols[row], PERIOD_M15);
     }

   RefreshActiveTab();
   ChartRedraw();
  }

//+------------------------------------------------------------------+
void OnTradeTransaction(const MqlTradeTransaction &trans,
                        const MqlTradeRequest &request,
                        const MqlTradeResult &result)
  {
   g_execution.OnTransaction(trans, request, result);

   // Account guards only ever see this EA's own closed deals. v1.1.0 counted
   // every closing deal on the account, so a manual trade could trip the
   // consecutive-loss halt for something the scanner never did.
   if(trans.type != TRADE_TRANSACTION_DEAL_ADD || trans.deal == 0)
      return;
   if(!HistoryDealSelect(trans.deal))
      return;
   if((ulong)HistoryDealGetInteger(trans.deal, DEAL_MAGIC) != AS_MAGIC)
      return;

   const long entry = HistoryDealGetInteger(trans.deal, DEAL_ENTRY);
   if(entry != DEAL_ENTRY_OUT && entry != DEAL_ENTRY_OUT_BY)
      return;

   const double net = HistoryDealGetDouble(trans.deal, DEAL_PROFIT)
                      + HistoryDealGetDouble(trans.deal, DEAL_COMMISSION)
                      + HistoryDealGetDouble(trans.deal, DEAL_SWAP);
   g_account_guard.RegisterClosedProfit(net);
  }
