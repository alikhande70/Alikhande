//+------------------------------------------------------------------+
//| SystemHealth.mqh                                                  |
//| Restart-recovery marker, runtime telemetry (CPU budget usage,     |
//| tick staleness), and the broker-spec drift check described in     |
//| docs/ARCHITECTURE_V1.2.md section 8.                              |
//+------------------------------------------------------------------+
#property strict
#include "../Storage/Database.mqh"
#include "../Core/Hash.mqh"

datetime g_LastOnTimerTs = 0;
double   g_LastCpuBudgetUsedMs = 0.0;

void HealthRecordRestartMarker()
  {
   AlikhandeDbLogEvent("INFO", "RESTART", TimeToString(TimeCurrent(), TIME_DATE|TIME_SECONDS));

   int stmt = DatabasePrepare(g_AlikhandeDbHandle,
      "INSERT INTO system_health(ts, cpu_budget_used_ms, restart_marker, last_ontimer_ts) "
      "VALUES(?,?,1,?)");
   if(stmt == INVALID_HANDLE)
      return;
   DatabaseBind(stmt, 0, (long)TimeCurrent());
   DatabaseBind(stmt, 1, 0.0);
   DatabaseBind(stmt, 2, (long)0);
   DatabaseRead(stmt);
   DatabaseFinalize(stmt);
  }

// Call at the top and bottom of each OnTimer slice; logs a WARN if the slice
// exceeded its budget so silent throttling never goes unnoticed.
void HealthTrackTimerSlice(const ulong startMicroseconds, const double budgetMs)
  {
   double usedMs = (double)(GetMicrosecondCount() - startMicroseconds) / 1000.0;
   g_LastCpuBudgetUsedMs = usedMs;
   g_LastOnTimerTs = TimeCurrent();

   if(usedMs > budgetMs)
      AlikhandeDbLogEvent("WARN", "TIMER_BUDGET_EXCEEDED",
         StringFormat("used=%.2fms budget=%.2fms", usedMs, budgetMs));
  }

// A tick older than staleSeconds means quotes are not live — candidates must
// be blocked regardless of what the scoring pipeline computed upstream.
bool HealthIsTickStale(const string symbol, const int staleSeconds)
  {
   MqlTick tick;
   if(!SymbolInfoTick(symbol, tick))
      return true;
   return (TimeCurrent() - tick.time) > staleSeconds;
  }

//+------------------------------------------------------------------+
//| Broker/symbol spec drift detection (blueprint section 8). Hashes  |
//| the fields that matter for risk math; if the live hash differs    |
//| from the last stored one, the broker changed the symbol spec      |
//| mid-session — every risk calc using the old value is now stale.   |
//+------------------------------------------------------------------+
string ComputeSymbolSpecHash(const string symbol)
  {
   int digits          = (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS);
   double contractSize = SymbolInfoDouble(symbol, SYMBOL_TRADE_CONTRACT_SIZE);
   int stopsLevel      = (int)SymbolInfoInteger(symbol, SYMBOL_TRADE_STOPS_LEVEL);
   int freezeLevel     = (int)SymbolInfoInteger(symbol, SYMBOL_TRADE_FREEZE_LEVEL);
   double tickValue     = SymbolInfoDouble(symbol, SYMBOL_TRADE_TICK_VALUE);

   string blob = StringFormat("%s|%d|%.4f|%d|%d|%.6f", symbol, digits, contractSize,
                               stopsLevel, freezeLevel, tickValue);
   return AlikhandeHashString(blob);
  }

bool HealthCheckSymbolSpecDrift(const string symbol)
  {
   string liveHash = ComputeSymbolSpecHash(symbol);

   int stmt = DatabasePrepare(g_AlikhandeDbHandle,
      "SELECT spec_hash FROM symbol_specs WHERE symbol=?");
   if(stmt == INVALID_HANDLE)
      return false;

   DatabaseBind(stmt, 0, symbol);
   bool hasPrev = DatabaseRead(stmt);
   string prevHash = "";
   if(hasPrev)
      DatabaseColumnText(stmt, 0, prevHash);
   DatabaseFinalize(stmt);

   bool drifted = hasPrev && (prevHash != liveHash);
   if(drifted)
      AlikhandeDbLogEvent("WARN", "SYMBOL_SPEC_DRIFT",
         StringFormat("%s spec hash changed: %s -> %s", symbol, prevHash, liveHash));

   int upsert = DatabasePrepare(g_AlikhandeDbHandle,
      "INSERT INTO symbol_specs(symbol, digits, contract_size, stops_level, freeze_level, "
      "spec_hash, updated_at) VALUES(?,?,?,?,?,?,?) "
      "ON CONFLICT(symbol) DO UPDATE SET digits=excluded.digits, "
      "contract_size=excluded.contract_size, stops_level=excluded.stops_level, "
      "freeze_level=excluded.freeze_level, spec_hash=excluded.spec_hash, "
      "updated_at=excluded.updated_at");
   if(upsert != INVALID_HANDLE)
     {
      DatabaseBind(upsert, 0, symbol);
      DatabaseBind(upsert, 1, (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS));
      DatabaseBind(upsert, 2, SymbolInfoDouble(symbol, SYMBOL_TRADE_CONTRACT_SIZE));
      DatabaseBind(upsert, 3, (int)SymbolInfoInteger(symbol, SYMBOL_TRADE_STOPS_LEVEL));
      DatabaseBind(upsert, 4, (int)SymbolInfoInteger(symbol, SYMBOL_TRADE_FREEZE_LEVEL));
      DatabaseBind(upsert, 5, liveHash);
      DatabaseBind(upsert, 6, (long)TimeCurrent());
      DatabaseRead(upsert);
      DatabaseFinalize(upsert);
     }

   return drifted;
  }
