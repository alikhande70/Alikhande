//+------------------------------------------------------------------+
//| Database.mqh                                                      |
//| SQLite persistence layer — the source of truth for signals,       |
//| trade lifecycle, outcomes and system health. CSV (SignalLogger)   |
//| becomes a read-only export of this data, not the primary store.  |
//|                                                                    |
//| Uses MQL5's native Database* functions (DatabaseOpen/Execute/     |
//| Bind/TransactionBegin/Commit) — see:                              |
//| https://www.mql5.com/en/docs/database                            |
//+------------------------------------------------------------------+
#property strict

#define ALIKHANDE_DB_FILENAME "AlikhandeScanner\\alikhande.sqlite"

int g_AlikhandeDbHandle = INVALID_HANDLE;

bool AlikhandeDbIsOpen() { return g_AlikhandeDbHandle != INVALID_HANDLE; }

//+------------------------------------------------------------------+
//| Schema. Every bulk write elsewhere in the codebase MUST be        |
//| wrapped in DatabaseTransactionBegin/Commit — unwrapped inserts    |
//| on disk-backed SQLite are orders of magnitude slower.             |
//+------------------------------------------------------------------+
bool AlikhandeDbCreateSchema()
  {
   if(!AlikhandeDbIsOpen())
      return false;

   string statements[] =
     {
      "CREATE TABLE IF NOT EXISTS schema_meta ("
      " key TEXT PRIMARY KEY, value TEXT NOT NULL)",

      "CREATE TABLE IF NOT EXISTS signals ("
      " signal_id TEXT PRIMARY KEY,"
      " ts INTEGER NOT NULL,"
      " symbol TEXT NOT NULL,"
      " direction TEXT NOT NULL,"
      " setup TEXT NOT NULL,"
      " h4_state TEXT, h1_state TEXT, m15_state TEXT, m5_state TEXT,"
      " spread REAL, atr REAL,"
      " support REAL, resistance REAL,"
      " entry REAL, sl REAL, tp REAL,"
      " long_score REAL, short_score REAL,"
      " rule_version INTEGER NOT NULL,"
      " parameter_hash TEXT NOT NULL,"
      " broker_spec_hash TEXT NOT NULL,"
      " state TEXT NOT NULL,"
      " created_at INTEGER NOT NULL)",

      "CREATE TABLE IF NOT EXISTS signal_features ("
      " signal_id TEXT NOT NULL,"
      " feature_name TEXT NOT NULL,"
      " feature_value REAL,"
      " PRIMARY KEY(signal_id, feature_name),"
      " FOREIGN KEY(signal_id) REFERENCES signals(signal_id))",

      "CREATE TABLE IF NOT EXISTS trade_plans ("
      " plan_id TEXT PRIMARY KEY,"
      " signal_id TEXT NOT NULL,"
      " risk_pct REAL NOT NULL,"
      " lot REAL NOT NULL,"
      " sl_price REAL, tp_price REAL,"
      " created_at INTEGER NOT NULL,"
      " FOREIGN KEY(signal_id) REFERENCES signals(signal_id))",

      "CREATE TABLE IF NOT EXISTS trade_requests ("
      " request_id TEXT PRIMARY KEY,"
      " plan_id TEXT NOT NULL,"
      " submitted_at INTEGER NOT NULL,"
      " state TEXT NOT NULL,"
      " retcode INTEGER,"
      " FOREIGN KEY(plan_id) REFERENCES trade_plans(plan_id))",

      "CREATE TABLE IF NOT EXISTS deals ("
      " deal_id INTEGER PRIMARY KEY,"
      " request_id TEXT NOT NULL,"
      " position_id INTEGER,"
      " volume REAL, price REAL,"
      " ts INTEGER NOT NULL,"
      " FOREIGN KEY(request_id) REFERENCES trade_requests(request_id))",

      "CREATE TABLE IF NOT EXISTS outcomes ("
      " signal_id TEXT PRIMARY KEY,"
      " result TEXT NOT NULL," // TP / SL / EXPIRED / INVALIDATED / AMBIGUOUS / NOT_FILLED
      " mfe REAL, mae REAL,"
      " closed_at INTEGER,"
      " FOREIGN KEY(signal_id) REFERENCES signals(signal_id))",

      "CREATE TABLE IF NOT EXISTS symbol_specs ("
      " symbol TEXT PRIMARY KEY,"
      " digits INTEGER, contract_size REAL,"
      " stops_level INTEGER, freeze_level INTEGER,"
      " spec_hash TEXT NOT NULL,"
      " updated_at INTEGER NOT NULL)",

      "CREATE TABLE IF NOT EXISTS sessions ("
      " id INTEGER PRIMARY KEY AUTOINCREMENT,"
      " symbol TEXT NOT NULL, session_name TEXT NOT NULL,"
      " start_ts INTEGER NOT NULL, end_ts INTEGER NOT NULL)",

      "CREATE TABLE IF NOT EXISTS news_events ("
      " id INTEGER PRIMARY KEY AUTOINCREMENT,"
      " currency TEXT NOT NULL, importance TEXT NOT NULL,"
      " event_time INTEGER NOT NULL, title TEXT)",

      "CREATE TABLE IF NOT EXISTS parameter_sets ("
      " hash TEXT PRIMARY KEY, json_blob TEXT NOT NULL,"
      " created_at INTEGER NOT NULL)",

      "CREATE TABLE IF NOT EXISTS runtime_events ("
      " id INTEGER PRIMARY KEY AUTOINCREMENT,"
      " ts INTEGER NOT NULL, level TEXT NOT NULL,"
      " code TEXT NOT NULL, message TEXT)",

      "CREATE TABLE IF NOT EXISTS system_health ("
      " id INTEGER PRIMARY KEY AUTOINCREMENT,"
      " ts INTEGER NOT NULL,"
      " cpu_budget_used_ms REAL,"
      " restart_marker INTEGER,"
      " last_ontimer_ts INTEGER)",

      "CREATE INDEX IF NOT EXISTS idx_signals_symbol_ts ON signals(symbol, ts)",
      "CREATE INDEX IF NOT EXISTS idx_trade_requests_state ON trade_requests(state)"
     };

   if(!DatabaseTransactionBegin(g_AlikhandeDbHandle))
      return false;

   for(int i = 0; i < ArraySize(statements); i++)
     {
      if(!DatabaseExecute(g_AlikhandeDbHandle, statements[i]))
        {
         DatabaseTransactionRollback(g_AlikhandeDbHandle);
         PrintFormat("Alikhande DB: schema statement %d failed: %s", i, DatabaseErrorText());
         return false;
        }
     }

   DatabaseExecute(g_AlikhandeDbHandle,
      StringFormat("INSERT OR REPLACE INTO schema_meta(key,value) VALUES('schema_version','%d')",
                   ALIKHANDE_DB_SCHEMA_VERSION));

   return DatabaseTransactionCommit(g_AlikhandeDbHandle);
  }

//+------------------------------------------------------------------+
//| Open (or create) the database and ensure the schema exists.       |
//| Call once from OnInit. Never call from OnTimer/OnTick.            |
//+------------------------------------------------------------------+
bool AlikhandeDbInit()
  {
   if(AlikhandeDbIsOpen())
      return true;

   g_AlikhandeDbHandle = DatabaseOpen(ALIKHANDE_DB_FILENAME,
                                       DATABASE_OPEN_READWRITE | DATABASE_OPEN_CREATE);
   if(g_AlikhandeDbHandle == INVALID_HANDLE)
     {
      PrintFormat("Alikhande DB: open failed: %s", DatabaseErrorText());
      return false;
     }

   if(!AlikhandeDbCreateSchema())
     {
      DatabaseClose(g_AlikhandeDbHandle);
      g_AlikhandeDbHandle = INVALID_HANDLE;
      return false;
     }

   return true;
  }

void AlikhandeDbShutdown()
  {
   if(AlikhandeDbIsOpen())
     {
      DatabaseClose(g_AlikhandeDbHandle);
      g_AlikhandeDbHandle = INVALID_HANDLE;
     }
  }

//+------------------------------------------------------------------+
//| Runtime event log — every non-trivial state transition, DB write  |
//| failure, or guard trip should go through here so Health tab and   |
//| post-mortems have a single append-only trail.                     |
//+------------------------------------------------------------------+
void AlikhandeDbLogEvent(const string level, const string code, const string message)
  {
   if(!AlikhandeDbIsOpen())
      return;

   int stmt = DatabasePrepare(g_AlikhandeDbHandle,
      "INSERT INTO runtime_events(ts, level, code, message) VALUES(?,?,?,?)");
   if(stmt == INVALID_HANDLE)
      return;

   DatabaseBind(stmt, 0, (long)TimeCurrent());
   DatabaseBind(stmt, 1, level);
   DatabaseBind(stmt, 2, code);
   DatabaseBind(stmt, 3, message);
   DatabaseRead(stmt);
   DatabaseFinalize(stmt);
  }
