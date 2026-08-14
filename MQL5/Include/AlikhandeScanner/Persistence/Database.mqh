#pragma once
#include "../Core/Config.mqh"
#include "../Core/VersionInfo.mqh"
#include "../Core/Log.mqh"

// SQLite connection and schema management.
//
// MQL5 ships SQLite natively (DatabaseOpen/Execute/Prepare/Bind/Read), so there
// is no reason for a scanner that wants to prove anything about its own history
// to persist through appended CSV. CSV remains as an *export* for Excel/Python;
// this is the source of truth.
//
// Migration policy: `schema_meta.schema_version` is the single authority.
// Migrate() walks from the stored version to AS_DB_SCHEMA_VERSION one step at a
// time. Adding a schema change without adding its migration step is a release
// blocker — the version check will refuse to open the database rather than
// operate against a shape it does not understand.

class AS_Database
  {
private:
   int     m_handle;
   AS_Log *m_log;

   bool Exec(const string sql)
     {
      if(m_handle == INVALID_HANDLE)
         return false;
      if(DatabaseExecute(m_handle, sql))
         return true;
      if(m_log != NULL)
         m_log.Error("DB_EXEC_FAILED", "", StringFormat("%s | %s", DatabaseErrorText(), sql));
      return false;
     }

   int ReadSchemaVersion(void)
     {
      int request = DatabasePrepare(m_handle,
                                    "SELECT value FROM schema_meta WHERE key='schema_version'");
      if(request == INVALID_HANDLE)
         return 0;
      int version = 0;
      if(DatabaseRead(request))
        {
         string raw = "";
         DatabaseColumnText(request, 0, raw);
         version = (int)StringToInteger(raw);
        }
      DatabaseFinalize(request);
      return version;
     }

   bool WriteSchemaVersion(const int version)
     {
      return Exec(StringFormat(
                     "INSERT OR REPLACE INTO schema_meta(key,value) VALUES('schema_version','%d')",
                     version));
     }

   // Version 1 — the initial shape.
   bool MigrateToV1(void)
     {
      string statements[] =
        {
         "CREATE TABLE IF NOT EXISTS signals("
         " signal_id TEXT PRIMARY KEY,"
         " symbol TEXT NOT NULL,"
         " direction INTEGER NOT NULL,"
         " setup INTEGER NOT NULL,"
         " state TEXT NOT NULL,"
         " preferred_entry REAL, stop_loss REAL, take_profit REAL,"
         " nearest_support REAL, nearest_resistance REAL,"
         " long_score REAL, short_score REAL,"
         " reasons TEXT, validation_codes TEXT,"
         " confirmation_bar_time INTEGER,"
         " created_at INTEGER NOT NULL,"
         " expires_at INTEGER,"
         " rule_version TEXT NOT NULL,"
         " scoring_version TEXT NOT NULL,"
         " parameter_hash TEXT NOT NULL,"
         " broker_spec_hash TEXT NOT NULL)",

         // Feature snapshot per signal. This is what a future meta-model would
         // train on; capturing it now is why the model becomes possible later.
         "CREATE TABLE IF NOT EXISTS signal_features("
         " signal_id TEXT NOT NULL,"
         " name TEXT NOT NULL,"
         " value REAL,"
         " PRIMARY KEY(signal_id,name))",

         "CREATE TABLE IF NOT EXISTS trade_plans("
         " plan_id TEXT PRIMARY KEY,"
         " signal_id TEXT NOT NULL,"
         " symbol TEXT NOT NULL,"
         " direction INTEGER NOT NULL,"
         " entry REAL, stop_loss REAL, take_profit REAL,"
         " risk_percent REAL, risk_amount REAL, actual_risk_amount REAL,"
         " lot_size REAL, margin_required REAL,"
         " created_at INTEGER NOT NULL, expires_at INTEGER,"
         " validation_codes TEXT)",

         "CREATE TABLE IF NOT EXISTS executions("
         " execution_id TEXT PRIMARY KEY,"
         " plan_id TEXT NOT NULL,"
         " signal_id TEXT NOT NULL,"
         " symbol TEXT NOT NULL,"
         " state TEXT NOT NULL,"
         " request_id INTEGER, order_ticket INTEGER,"
         " deal_ticket INTEGER, position_id INTEGER,"
         " requested_volume REAL, filled_volume REAL,"
         " retcode INTEGER, message TEXT,"
         " created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL,"
         " terminal INTEGER NOT NULL)",

         // Deals are recorded by ticket so replayed or duplicated
         // OnTradeTransaction events cannot double-count a fill.
         "CREATE TABLE IF NOT EXISTS deals("
         " deal_ticket INTEGER PRIMARY KEY,"
         " execution_id TEXT,"
         " symbol TEXT NOT NULL,"
         " entry_type INTEGER,"
         " volume REAL, price REAL, net_profit REAL,"
         " recorded_at INTEGER NOT NULL)",

         "CREATE TABLE IF NOT EXISTS outcomes("
         " signal_id TEXT PRIMARY KEY,"
         " result TEXT NOT NULL,"
         " realized_r REAL, mfe_r REAL, mae_r REAL,"
         " closed_at INTEGER)",

         "CREATE TABLE IF NOT EXISTS symbol_specs("
         " symbol TEXT PRIMARY KEY,"
         " fingerprint TEXT NOT NULL,"
         " digits INTEGER, point REAL, tick_size REAL, tick_value REAL,"
         " contract_size REAL, volume_min REAL, volume_step REAL,"
         " stops_level INTEGER, freeze_level INTEGER,"
         " updated_at INTEGER NOT NULL)",

         // Single-row table (id=1) holding guard state across restarts.
         "CREATE TABLE IF NOT EXISTS risk_state("
         " id INTEGER PRIMARY KEY CHECK(id=1),"
         " day_key INTEGER, day_start_equity REAL, peak_equity REAL,"
         " consecutive_losses INTEGER, daily_risk_used_pct REAL,"
         " updated_at INTEGER NOT NULL)",

         "CREATE TABLE IF NOT EXISTS runtime_events("
         " id INTEGER PRIMARY KEY AUTOINCREMENT,"
         " ts INTEGER NOT NULL, level TEXT NOT NULL,"
         " code TEXT NOT NULL, context TEXT, message TEXT)",

         "CREATE INDEX IF NOT EXISTS ix_signals_symbol_time ON signals(symbol,created_at)",
         "CREATE INDEX IF NOT EXISTS ix_signals_state ON signals(state)",
         "CREATE INDEX IF NOT EXISTS ix_executions_terminal ON executions(terminal)",
         "CREATE INDEX IF NOT EXISTS ix_events_ts ON runtime_events(ts)"
        };

      for(int i = 0; i < ArraySize(statements); i++)
         if(!Exec(statements[i]))
            return false;
      return true;
     }

   bool Migrate(void)
     {
      if(!Exec("CREATE TABLE IF NOT EXISTS schema_meta("
               " key TEXT PRIMARY KEY, value TEXT NOT NULL)"))
         return false;

      int current = ReadSchemaVersion();

      if(current > AS_DB_SCHEMA_VERSION)
        {
         if(m_log != NULL)
            m_log.Error("DB_SCHEMA_TOO_NEW", "",
                        StringFormat("database is at v%d, this build understands v%d; "
                                     "refusing to operate against an unknown shape",
                                     current, AS_DB_SCHEMA_VERSION));
         return false;
        }

      // Each step is applied inside its own transaction so a failure leaves the
      // stored version pointing at the last shape that fully succeeded.
      while(current < AS_DB_SCHEMA_VERSION)
        {
         const int target = current + 1;
         if(!DatabaseTransactionBegin(m_handle))
            return false;

         bool ok = false;
         switch(target)
           {
            case 1: ok = MigrateToV1(); break;
            default:
               if(m_log != NULL)
                  m_log.Error("DB_MIGRATION_MISSING", "",
                              StringFormat("no migration step defined for v%d", target));
               ok = false;
           }

         if(!ok || !WriteSchemaVersion(target))
           {
            DatabaseTransactionRollback(m_handle);
            return false;
           }
         if(!DatabaseTransactionCommit(m_handle))
            return false;

         current = target;
         if(m_log != NULL)
            m_log.Info("DB_MIGRATED", "", StringFormat("schema now at v%d", target));
        }

      return true;
     }

public:
   AS_Database(void) { m_handle = INVALID_HANDLE; m_log = NULL; }

   void Attach(AS_Log &log) { m_log = GetPointer(log); }

   bool IsOpen(void) const { return m_handle != INVALID_HANDLE; }
   int  Handle(void) const { return m_handle; }

   bool Open(const string filename)
     {
      if(m_handle != INVALID_HANDLE)
         return true;

      m_handle = DatabaseOpen(filename, DATABASE_OPEN_READWRITE | DATABASE_OPEN_CREATE);
      if(m_handle == INVALID_HANDLE)
        {
         if(m_log != NULL)
            m_log.Error("DB_OPEN_FAILED", filename, DatabaseErrorText());
         return false;
        }

      // WAL keeps a reader (an external inspection tool) from blocking the
      // scanner's writes mid-session.
      Exec("PRAGMA journal_mode=WAL");
      Exec("PRAGMA foreign_keys=ON");

      if(!Migrate())
        {
         Close();
         return false;
        }
      return true;
     }

   void Close(void)
     {
      if(m_handle == INVALID_HANDLE)
         return;
      DatabaseClose(m_handle);
      m_handle = INVALID_HANDLE;
     }

   bool Begin(void)    { return m_handle != INVALID_HANDLE && DatabaseTransactionBegin(m_handle); }
   bool Commit(void)   { return m_handle != INVALID_HANDLE && DatabaseTransactionCommit(m_handle); }
   bool Rollback(void) { return m_handle != INVALID_HANDLE && DatabaseTransactionRollback(m_handle); }

   bool Execute(const string sql) { return Exec(sql); }
  };
