#pragma once
#include "../Core/Config.mqh"
#include "../Core/VersionInfo.mqh"
class AS_Database {
private:
   int m_db;
   bool Exec(const string sql){if(m_db==INVALID_HANDLE)return false;ResetLastError();if(!DatabaseExecute(m_db,sql)){PrintFormat("Alikhande DB error=%d sql=%s",GetLastError(),sql);return false;}return true;}
public:
   AS_Database(void){m_db=INVALID_HANDLE;}
   ~AS_Database(void){Close();}
   bool Open(){if(m_db!=INVALID_HANDLE)return true;m_db=DatabaseOpen(AS_DATABASE_FILE,DATABASE_OPEN_READWRITE|DATABASE_OPEN_CREATE);if(m_db==INVALID_HANDLE){PrintFormat("Alikhande DB open failed error=%d",GetLastError());return false;}if(!Exec("PRAGMA journal_mode=WAL"))Print("Alikhande DB: WAL unavailable, continuing with SQLite default journal mode");return Migrate();}
   void Close(){if(m_db!=INVALID_HANDLE){DatabaseClose(m_db);m_db=INVALID_HANDLE;}}
   bool Ready()const{return m_db!=INVALID_HANDLE;}
   int Handle()const{return m_db;}
   bool Migrate(){if(!Ready())return false;if(!Exec("CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT NOT NULL)"))return false;if(!Exec("CREATE TABLE IF NOT EXISTS signals(signal_id TEXT PRIMARY KEY,symbol TEXT NOT NULL,direction INTEGER,setup INTEGER,state INTEGER,created_at INTEGER,confirmation_time INTEGER,expires_at INTEGER,entry REAL,sl REAL,tp REAL,long_score REAL,short_score REAL,rule_version TEXT,scoring_version TEXT,parameter_hash TEXT,broker_spec_hash TEXT,regime INTEGER,regime_confidence REAL,reasons TEXT,validation_codes TEXT)"))return false;if(!Exec("CREATE TABLE IF NOT EXISTS trade_plans(plan_id TEXT PRIMARY KEY,signal_id TEXT,symbol TEXT,direction INTEGER,entry REAL,sl REAL,tp REAL,risk_pct REAL,risk_amount REAL,actual_risk REAL,lot REAL,margin REAL,created_at INTEGER,expires_at INTEGER,broker_spec_hash TEXT,validation_codes TEXT)"))return false;if(!Exec("CREATE TABLE IF NOT EXISTS executions(execution_id TEXT PRIMARY KEY,plan_id TEXT,signal_id TEXT,symbol TEXT,state INTEGER,request_id INTEGER,order_ticket INTEGER,deal_ticket INTEGER,position_id INTEGER,retcode INTEGER,requested_volume REAL,filled_volume REAL,updated_at INTEGER,message TEXT)"))return false;if(!Exec("CREATE TABLE IF NOT EXISTS outcomes(signal_id TEXT PRIMARY KEY,state INTEGER,resolved_at INTEGER,exit_price REAL,r_multiple REAL,mfe_r REAL,mae_r REAL,notes TEXT)"))return false;if(!Exec("CREATE TABLE IF NOT EXISTS symbol_specs(symbol TEXT,spec_hash TEXT,captured_at INTEGER,digits INTEGER,point REAL,tick_size REAL,tick_value REAL,contract_size REAL,volume_min REAL,volume_max REAL,volume_step REAL,stops_level INTEGER,freeze_level INTEGER,filling_mode INTEGER,PRIMARY KEY(symbol,captured_at))"))return false;if(!Exec("CREATE TABLE IF NOT EXISTS runtime_events(id INTEGER PRIMARY KEY AUTOINCREMENT,event_time INTEGER,severity TEXT,component TEXT,code TEXT,message TEXT)"))return false;string q=StringFormat("INSERT OR REPLACE INTO meta(key,value) VALUES('schema_version','%d')",AS_SCHEMA_VERSION);return Exec(q);}
   bool Begin(){return Ready()&&DatabaseTransactionBegin(m_db);}
   bool Commit(){return Ready()&&DatabaseTransactionCommit(m_db);}
   bool Rollback(){return Ready()&&DatabaseTransactionRollback(m_db);}
};
