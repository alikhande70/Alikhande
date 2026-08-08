#pragma once
#include "../Core/VersionInfo.mqh"
#include "../Core/RuntimeContext.mqh"
#include "DatabasePolicyV13.mqh"

class AS_Database {
private:
   int m_db;
   string m_filename;
   AS_RuntimeContext m_context;

   bool Exec(const string sql){
      if(m_db==INVALID_HANDLE)return false;
      ResetLastError();
      if(!DatabaseExecute(m_db,sql)){
         PrintFormat("Alikhande DB error=%d sql=%s",GetLastError(),sql);
         return false;
      }
      return true;
   }

   int ReadVersion(){
      if(!Ready())return -1;
      int stmt=DatabasePrepare(m_db,"SELECT value FROM meta WHERE key='schema_version'");
      if(stmt==INVALID_HANDLE)return 0;
      int version=0;
      if(DatabaseRead(stmt)){
         string raw="";
         DatabaseColumnText(stmt,0,raw);
         version=(int)StringToInteger(raw);
      }
      DatabaseFinalize(stmt);
      return version;
   }

   bool WriteVersion(const int version){return Exec(StringFormat("INSERT OR REPLACE INTO meta(key,value) VALUES('schema_version','%d')",version));}

   bool BootstrapV4(){
      if(!Exec("CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT NOT NULL)"))return false;
      if(!Exec("CREATE TABLE IF NOT EXISTS signals(signal_id TEXT PRIMARY KEY,symbol TEXT NOT NULL,direction INTEGER,setup INTEGER,state INTEGER,created_at INTEGER,confirmation_time INTEGER,expires_at INTEGER,entry REAL,sl REAL,tp REAL,long_score REAL,short_score REAL,rule_version TEXT,scoring_version TEXT,parameter_hash TEXT,broker_spec_hash TEXT,regime INTEGER,regime_confidence REAL,reasons TEXT,validation_codes TEXT)"))return false;
      if(!Exec("CREATE TABLE IF NOT EXISTS trade_plans(plan_id TEXT PRIMARY KEY,signal_id TEXT,symbol TEXT,direction INTEGER,entry REAL,sl REAL,tp REAL,risk_pct REAL,risk_amount REAL,actual_risk REAL,lot REAL,margin REAL,created_at INTEGER,expires_at INTEGER,broker_spec_hash TEXT,validation_codes TEXT)"))return false;
      if(!Exec("CREATE TABLE IF NOT EXISTS executions(execution_id TEXT PRIMARY KEY,plan_id TEXT,signal_id TEXT,symbol TEXT,state INTEGER,request_id INTEGER,order_ticket INTEGER,deal_ticket INTEGER,position_id INTEGER,retcode INTEGER,requested_volume REAL,filled_volume REAL,updated_at INTEGER,message TEXT)"))return false;
      if(!Exec("CREATE TABLE IF NOT EXISTS outcomes(signal_id TEXT PRIMARY KEY,state INTEGER,resolved_at INTEGER,exit_price REAL,r_multiple REAL,mfe_r REAL,mae_r REAL,notes TEXT)"))return false;
      if(!Exec("CREATE TABLE IF NOT EXISTS symbol_specs(symbol TEXT,spec_hash TEXT,captured_at INTEGER,digits INTEGER,point REAL,tick_size REAL,tick_value REAL,contract_size REAL,volume_min REAL,volume_max REAL,volume_step REAL,stops_level INTEGER,freeze_level INTEGER,filling_mode INTEGER,PRIMARY KEY(symbol,captured_at))"))return false;
      if(!Exec("CREATE TABLE IF NOT EXISTS runtime_events(id INTEGER PRIMARY KEY AUTOINCREMENT,event_time INTEGER,severity TEXT,component TEXT,code TEXT,message TEXT)"))return false;
      if(!Exec("CREATE TABLE IF NOT EXISTS risk_state(id INTEGER PRIMARY KEY CHECK(id=1),day_key INTEGER,day_start_equity REAL,peak_equity REAL,consecutive_losses INTEGER,updated_at INTEGER)"))return false;
      return true;
   }

   bool Migrate4To5(){
      if(!Exec("CREATE TABLE IF NOT EXISTS signal_features(signal_id TEXT NOT NULL,name TEXT NOT NULL,value REAL,PRIMARY KEY(signal_id,name))"))return false;
      if(!Exec("CREATE TABLE IF NOT EXISTS execution_deals(deal_ticket INTEGER PRIMARY KEY,execution_id TEXT,symbol TEXT,entry_type INTEGER,volume REAL,price REAL,net_profit REAL,recorded_at INTEGER)"))return false;
      if(!Exec("CREATE TABLE IF NOT EXISTS runtime_identity(id INTEGER PRIMARY KEY CHECK(id=1),context_kind INTEGER NOT NULL,identity TEXT NOT NULL,db_file TEXT NOT NULL,updated_at INTEGER NOT NULL)"))return false;
      if(!Exec("CREATE INDEX IF NOT EXISTS ix_signals_symbol_time ON signals(symbol,created_at)"))return false;
      if(!Exec("CREATE INDEX IF NOT EXISTS ix_executions_state ON executions(state)"))return false;
      return true;
   }

   bool Migrate5To6(){
      if(!Exec("ALTER TABLE outcomes ADD COLUMN evidence_source INTEGER NOT NULL DEFAULT 0"))return false;
      if(!Exec("ALTER TABLE outcomes ADD COLUMN rule_version TEXT"))return false;
      if(!Exec("ALTER TABLE outcomes ADD COLUMN scoring_version TEXT"))return false;
      if(!Exec("ALTER TABLE outcomes ADD COLUMN parameter_hash TEXT"))return false;
      if(!Exec("ALTER TABLE outcomes ADD COLUMN broker_spec_hash TEXT"))return false;
      if(!Exec("ALTER TABLE outcomes ADD COLUMN execution_id TEXT"))return false;
      if(!Exec("ALTER TABLE executions ADD COLUMN created_at INTEGER NOT NULL DEFAULT 0"))return false;
      if(!Exec("CREATE INDEX IF NOT EXISTS ix_outcomes_scope ON outcomes(evidence_source,rule_version,scoring_version,parameter_hash,state)"))return false;
      if(!Exec("CREATE INDEX IF NOT EXISTS ix_executions_created ON executions(created_at)"))return false;
      return true;
   }

public:
   AS_Database(void){m_db=INVALID_HANDLE;m_filename="";ZeroMemory(m_context);}
   ~AS_Database(void){Close();}

   bool Open(){
      if(m_db!=INVALID_HANDLE)return true;
      AS_RuntimeContextReader reader;reader.Read(m_context);
      AS_DatabasePolicyV13 policy;m_filename=policy.FileName(m_context);
      m_db=DatabaseOpen(m_filename,DATABASE_OPEN_READWRITE|DATABASE_OPEN_CREATE);
      if(m_db==INVALID_HANDLE){PrintFormat("Alikhande DB open failed file=%s error=%d",m_filename,GetLastError());return false;}
      if(!Exec("PRAGMA journal_mode=WAL"))Print("Alikhande DB: WAL unavailable, continuing with SQLite default journal mode");
      if(!Exec("PRAGMA foreign_keys=ON"))Print("Alikhande DB: foreign_keys pragma unavailable");
      if(!Migrate()){Close();return false;}
      Exec(StringFormat("INSERT OR REPLACE INTO runtime_identity(id,context_kind,identity,db_file,updated_at) VALUES(1,%d,'%s','%s',%I64d)",(int)m_context.kind,m_context.identity,m_filename,(long)TimeCurrent()));
      return true;
   }

   void Close(){if(m_db!=INVALID_HANDLE){DatabaseClose(m_db);m_db=INVALID_HANDLE;}}
   bool Ready()const{return m_db!=INVALID_HANDLE;}
   int Handle()const{return m_db;}
   string FileName()const{return m_filename;}
   AS_RuntimeContext Context()const{return m_context;}

   bool Migrate(){
      if(!Ready())return false;
      if(!DatabaseTransactionBegin(m_db))return false;
      bool ok=BootstrapV4();
      if(!ok){DatabaseTransactionRollback(m_db);return false;}
      int version=ReadVersion();
      if(version==0){version=4;ok=WriteVersion(version);}
      if(version>AS_SCHEMA_VERSION){PrintFormat("Alikhande DB schema too new current=%d supported=%d",version,AS_SCHEMA_VERSION);DatabaseTransactionRollback(m_db);return false;}
      if(ok && version==4 && AS_SCHEMA_VERSION>=5){ok=Migrate4To5();if(ok){version=5;ok=WriteVersion(version);}}
      if(ok && version==5 && AS_SCHEMA_VERSION>=6){ok=Migrate5To6();if(ok){version=6;ok=WriteVersion(version);}}
      if(!ok || version!=AS_SCHEMA_VERSION){DatabaseTransactionRollback(m_db);return false;}
      if(!DatabaseTransactionCommit(m_db))return false;
      return true;
   }

   bool Begin(){return Ready()&&DatabaseTransactionBegin(m_db);}
   bool Commit(){return Ready()&&DatabaseTransactionCommit(m_db);}
   bool Rollback(){return Ready()&&DatabaseTransactionRollback(m_db);}
};