#pragma once
#include "Database.mqh"
#include "../Domain/Models.mqh"

// Data access. Every statement is prepared and bound — no string-concatenated
// SQL anywhere, so a symbol name containing a quote can never corrupt a query.

class AS_Repositories
  {
private:
   AS_Database *m_db;
   AS_Log      *m_log;

   bool Ready(void) const { return m_db != NULL && m_db.IsOpen(); }

   // Runs a prepared statement that returns no rows.
   bool Step(const int request, const string what)
     {
      if(request == INVALID_HANDLE)
        {
         if(m_log != NULL)
            m_log.Error("DB_PREPARE_FAILED", what, DatabaseErrorText());
         return false;
        }
      const bool ok = DatabaseRead(request) || DatabaseColumnsCount(request) == 0;
      DatabaseFinalize(request);
      return ok;
     }

public:
   AS_Repositories(void) { m_db = NULL; m_log = NULL; }

   void Attach(AS_Database &db, AS_Log &log)
     {
      m_db = GetPointer(db);
      m_log = GetPointer(log);
     }

   // ------------------------------------------------------------- signals

   // Persistent de-duplication. v1.1.0 kept seen ids in a RAM array only, so a
   // restart re-logged every signal it had already recorded.
   bool SignalExists(const string signal_id)
     {
      if(!Ready() || signal_id == "")
         return false;
      int request = DatabasePrepare(m_db.Handle(),
                                    "SELECT 1 FROM signals WHERE signal_id=?");
      if(request == INVALID_HANDLE)
         return false;
      DatabaseBind(request, 0, signal_id);
      const bool found = DatabaseRead(request);
      DatabaseFinalize(request);
      return found;
     }

   bool SaveSignal(const AS_SignalCandidate &s, const string state_name)
     {
      if(!Ready() || s.signal_id == "")
         return false;

      int request = DatabasePrepare(m_db.Handle(),
         "INSERT OR REPLACE INTO signals("
         " signal_id,symbol,direction,setup,state,"
         " preferred_entry,stop_loss,take_profit,nearest_support,nearest_resistance,"
         " long_score,short_score,reasons,validation_codes,"
         " confirmation_bar_time,created_at,expires_at,"
         " rule_version,scoring_version,parameter_hash,broker_spec_hash)"
         " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)");
      if(request == INVALID_HANDLE)
        {
         if(m_log != NULL)
            m_log.Error("DB_PREPARE_FAILED", "SaveSignal", DatabaseErrorText());
         return false;
        }

      int i = 0;
      DatabaseBind(request, i++, s.signal_id);
      DatabaseBind(request, i++, s.symbol);
      DatabaseBind(request, i++, (int)s.direction);
      DatabaseBind(request, i++, (int)s.setup);
      DatabaseBind(request, i++, state_name);
      DatabaseBind(request, i++, s.preferred_entry);
      DatabaseBind(request, i++, s.stop_loss);
      DatabaseBind(request, i++, s.take_profit);
      DatabaseBind(request, i++, s.nearest_support);
      DatabaseBind(request, i++, s.nearest_resistance);
      DatabaseBind(request, i++, s.long_score);
      DatabaseBind(request, i++, s.short_score);
      DatabaseBind(request, i++, s.reasons);
      DatabaseBind(request, i++, s.validation_codes);
      DatabaseBind(request, i++, (long)s.confirmation_bar_time);
      DatabaseBind(request, i++, (long)s.creation_time);
      DatabaseBind(request, i++, (long)s.expires_at);
      DatabaseBind(request, i++, s.rule_version);
      DatabaseBind(request, i++, s.scoring_version);
      DatabaseBind(request, i++, s.parameter_hash);
      DatabaseBind(request, i++, s.broker_spec_hash);

      return Step(request, "SaveSignal");
     }

   bool UpdateSignalState(const string signal_id, const string state_name)
     {
      if(!Ready())
         return false;
      int request = DatabasePrepare(m_db.Handle(),
                                    "UPDATE signals SET state=? WHERE signal_id=?");
      if(request == INVALID_HANDLE)
         return false;
      DatabaseBind(request, 0, state_name);
      DatabaseBind(request, 1, signal_id);
      return Step(request, "UpdateSignalState");
     }

   bool SaveFeature(const string signal_id, const string name, const double value)
     {
      if(!Ready())
         return false;
      int request = DatabasePrepare(m_db.Handle(),
         "INSERT OR REPLACE INTO signal_features(signal_id,name,value) VALUES(?,?,?)");
      if(request == INVALID_HANDLE)
         return false;
      DatabaseBind(request, 0, signal_id);
      DatabaseBind(request, 1, name);
      DatabaseBind(request, 2, value);
      return Step(request, "SaveFeature");
     }

   // ---------------------------------------------------------------- plans

   bool SavePlan(const AS_TradePlan &p)
     {
      if(!Ready() || p.plan_id == "")
         return false;
      int request = DatabasePrepare(m_db.Handle(),
         "INSERT OR REPLACE INTO trade_plans("
         " plan_id,signal_id,symbol,direction,entry,stop_loss,take_profit,"
         " risk_percent,risk_amount,actual_risk_amount,lot_size,margin_required,"
         " created_at,expires_at,validation_codes)"
         " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)");
      if(request == INVALID_HANDLE)
         return false;

      int i = 0;
      DatabaseBind(request, i++, p.plan_id);
      DatabaseBind(request, i++, p.signal_id);
      DatabaseBind(request, i++, p.symbol);
      DatabaseBind(request, i++, (int)p.direction);
      DatabaseBind(request, i++, p.entry);
      DatabaseBind(request, i++, p.stop_loss);
      DatabaseBind(request, i++, p.take_profit);
      DatabaseBind(request, i++, p.risk_percent);
      DatabaseBind(request, i++, p.risk_amount);
      DatabaseBind(request, i++, p.actual_risk_amount);
      DatabaseBind(request, i++, p.lot_size);
      DatabaseBind(request, i++, p.margin_required);
      DatabaseBind(request, i++, (long)p.created_at);
      DatabaseBind(request, i++, (long)p.expires_at);
      DatabaseBind(request, i++, p.validation_codes);
      return Step(request, "SavePlan");
     }

   // ----------------------------------------------------------- executions

   bool SaveExecution(const AS_ExecutionRecord &e, const string state_name)
     {
      if(!Ready() || e.execution_id == "")
         return false;
      int request = DatabasePrepare(m_db.Handle(),
         "INSERT OR REPLACE INTO executions("
         " execution_id,plan_id,signal_id,symbol,state,"
         " request_id,order_ticket,deal_ticket,position_id,"
         " requested_volume,filled_volume,retcode,message,"
         " created_at,updated_at,terminal)"
         " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)");
      if(request == INVALID_HANDLE)
         return false;

      int i = 0;
      DatabaseBind(request, i++, e.execution_id);
      DatabaseBind(request, i++, e.plan_id);
      DatabaseBind(request, i++, e.signal_id);
      DatabaseBind(request, i++, e.symbol);
      DatabaseBind(request, i++, state_name);
      DatabaseBind(request, i++, (long)e.request_id);
      DatabaseBind(request, i++, (long)e.order_ticket);
      DatabaseBind(request, i++, (long)e.deal_ticket);
      DatabaseBind(request, i++, (long)e.position_id);
      DatabaseBind(request, i++, e.requested_volume);
      DatabaseBind(request, i++, e.filled_volume);
      DatabaseBind(request, i++, (int)e.retcode);
      DatabaseBind(request, i++, e.message);
      DatabaseBind(request, i++, (long)e.created_at);
      DatabaseBind(request, i++, (long)e.updated_at);
      DatabaseBind(request, i++, e.terminal ? 1 : 0);
      return Step(request, "SaveExecution");
     }

   // Loads the most recent non-terminal execution so a restart resumes
   // reconciliation instead of forgetting an in-flight order.
   bool LoadUnresolvedExecution(AS_ExecutionRecord &e)
     {
      ZeroMemory(e);
      if(!Ready())
         return false;
      int request = DatabasePrepare(m_db.Handle(),
         "SELECT execution_id,plan_id,signal_id,symbol,request_id,order_ticket,"
         " deal_ticket,position_id,requested_volume,filled_volume,retcode,message,"
         " created_at,updated_at"
         " FROM executions WHERE terminal=0 ORDER BY updated_at DESC LIMIT 1");
      if(request == INVALID_HANDLE)
         return false;

      bool found = false;
      if(DatabaseRead(request))
        {
         long v = 0;
         DatabaseColumnText(request, 0, e.execution_id);
         DatabaseColumnText(request, 1, e.plan_id);
         DatabaseColumnText(request, 2, e.signal_id);
         DatabaseColumnText(request, 3, e.symbol);
         DatabaseColumnLong(request, 4, v); e.request_id = (ulong)v;
         DatabaseColumnLong(request, 5, v); e.order_ticket = (ulong)v;
         DatabaseColumnLong(request, 6, v); e.deal_ticket = (ulong)v;
         DatabaseColumnLong(request, 7, v); e.position_id = (ulong)v;
         DatabaseColumnDouble(request, 8, e.requested_volume);
         DatabaseColumnDouble(request, 9, e.filled_volume);
         int retcode = 0;
         DatabaseColumnInteger(request, 10, retcode); e.retcode = (uint)retcode;
         DatabaseColumnText(request, 11, e.message);
         DatabaseColumnLong(request, 12, v); e.created_at = (datetime)v;
         DatabaseColumnLong(request, 13, v); e.updated_at = (datetime)v;
         e.terminal = false;
         found = true;
        }
      DatabaseFinalize(request);
      return found;
     }

   // Deal ledger keyed by ticket. Returns false when the ticket was already
   // recorded, which is what makes OnTradeTransaction handling idempotent
   // under MetaQuotes' explicitly unordered, potentially-repeated delivery.
   bool RecordDealOnce(const ulong deal_ticket, const string execution_id,
                       const string symbol, const int entry_type,
                       const double volume, const double price, const double net_profit)
     {
      if(!Ready() || deal_ticket == 0)
         return false;

      int probe = DatabasePrepare(m_db.Handle(),
                                  "SELECT 1 FROM deals WHERE deal_ticket=?");
      if(probe == INVALID_HANDLE)
         return false;
      DatabaseBind(probe, 0, (long)deal_ticket);
      const bool already = DatabaseRead(probe);
      DatabaseFinalize(probe);
      if(already)
         return false;

      int request = DatabasePrepare(m_db.Handle(),
         "INSERT INTO deals(deal_ticket,execution_id,symbol,entry_type,"
         " volume,price,net_profit,recorded_at) VALUES(?,?,?,?,?,?,?,?)");
      if(request == INVALID_HANDLE)
         return false;

      int i = 0;
      DatabaseBind(request, i++, (long)deal_ticket);
      DatabaseBind(request, i++, execution_id);
      DatabaseBind(request, i++, symbol);
      DatabaseBind(request, i++, entry_type);
      DatabaseBind(request, i++, volume);
      DatabaseBind(request, i++, price);
      DatabaseBind(request, i++, net_profit);
      DatabaseBind(request, i++, (long)TimeCurrent());
      return Step(request, "RecordDeal");
     }

   // ------------------------------------------------------------- outcomes

   bool SaveOutcome(const AS_Outcome &o)
     {
      if(!Ready() || o.signal_id == "")
         return false;
      int request = DatabasePrepare(m_db.Handle(),
         "INSERT OR REPLACE INTO outcomes(signal_id,result,realized_r,mfe_r,mae_r,closed_at)"
         " VALUES(?,?,?,?,?,?)");
      if(request == INVALID_HANDLE)
         return false;
      DatabaseBind(request, 0, o.signal_id);
      DatabaseBind(request, 1, o.result);
      DatabaseBind(request, 2, o.realized_r);
      DatabaseBind(request, 3, o.mfe_r);
      DatabaseBind(request, 4, o.mae_r);
      DatabaseBind(request, 5, (long)o.closed_at);
      return Step(request, "SaveOutcome");
     }

   // Counts TP/SL outcomes for one symbol+setup under a specific rule version.
   // Version scoping is deliberate: pooling outcomes across rule changes would
   // produce a win rate that describes no system that ever actually ran.
   bool OutcomeCounts(const string symbol, const int setup, const string rule_version,
                      int &wins, int &total)
     {
      wins = 0;
      total = 0;
      if(!Ready())
         return false;
      int request = DatabasePrepare(m_db.Handle(),
         "SELECT o.result FROM outcomes o JOIN signals s ON s.signal_id=o.signal_id"
         " WHERE s.symbol=? AND s.setup=? AND s.rule_version=?"
         " AND o.result IN ('TP','SL')");
      if(request == INVALID_HANDLE)
         return false;

      DatabaseBind(request, 0, symbol);
      DatabaseBind(request, 1, setup);
      DatabaseBind(request, 2, rule_version);
      while(DatabaseRead(request))
        {
         string result = "";
         DatabaseColumnText(request, 0, result);
         total++;
         if(result == "TP")
            wins++;
        }
      DatabaseFinalize(request);
      return true;
     }

   // ----------------------------------------------------------- risk state

   bool SaveRiskState(const AS_RiskState &r)
     {
      if(!Ready())
         return false;
      int request = DatabasePrepare(m_db.Handle(),
         "INSERT OR REPLACE INTO risk_state(id,day_key,day_start_equity,peak_equity,"
         " consecutive_losses,daily_risk_used_pct,updated_at) VALUES(1,?,?,?,?,?,?)");
      if(request == INVALID_HANDLE)
         return false;
      DatabaseBind(request, 0, r.day_key);
      DatabaseBind(request, 1, r.day_start_equity);
      DatabaseBind(request, 2, r.peak_equity);
      DatabaseBind(request, 3, r.consecutive_losses);
      DatabaseBind(request, 4, r.daily_risk_used_pct);
      DatabaseBind(request, 5, (long)TimeCurrent());
      return Step(request, "SaveRiskState");
     }

   bool LoadRiskState(AS_RiskState &r)
     {
      ZeroMemory(r);
      if(!Ready())
         return false;
      int request = DatabasePrepare(m_db.Handle(),
         "SELECT day_key,day_start_equity,peak_equity,consecutive_losses,"
         " daily_risk_used_pct,updated_at FROM risk_state WHERE id=1");
      if(request == INVALID_HANDLE)
         return false;

      bool found = false;
      if(DatabaseRead(request))
        {
         long v = 0;
         DatabaseColumnInteger(request, 0, r.day_key);
         DatabaseColumnDouble(request, 1, r.day_start_equity);
         DatabaseColumnDouble(request, 2, r.peak_equity);
         DatabaseColumnInteger(request, 3, r.consecutive_losses);
         DatabaseColumnDouble(request, 4, r.daily_risk_used_pct);
         DatabaseColumnLong(request, 5, v); r.updated_at = (datetime)v;
         found = true;
        }
      DatabaseFinalize(request);
      return found;
     }

   // --------------------------------------------------------- symbol specs

   bool SaveSpec(const AS_SymbolSpec &s)
     {
      if(!Ready() || !s.ready)
         return false;
      int request = DatabasePrepare(m_db.Handle(),
         "INSERT OR REPLACE INTO symbol_specs(symbol,fingerprint,digits,point,tick_size,"
         " tick_value,contract_size,volume_min,volume_step,stops_level,freeze_level,updated_at)"
         " VALUES(?,?,?,?,?,?,?,?,?,?,?,?)");
      if(request == INVALID_HANDLE)
         return false;

      int i = 0;
      DatabaseBind(request, i++, s.symbol);
      DatabaseBind(request, i++, s.fingerprint);
      DatabaseBind(request, i++, s.digits);
      DatabaseBind(request, i++, s.point);
      DatabaseBind(request, i++, s.tick_size);
      DatabaseBind(request, i++, s.tick_value);
      DatabaseBind(request, i++, s.contract_size);
      DatabaseBind(request, i++, s.volume_min);
      DatabaseBind(request, i++, s.volume_step);
      DatabaseBind(request, i++, s.stops_level);
      DatabaseBind(request, i++, s.freeze_level);
      DatabaseBind(request, i++, (long)TimeCurrent());
      return Step(request, "SaveSpec");
     }

   bool LoadSpecFingerprint(const string symbol, string &fingerprint)
     {
      fingerprint = "";
      if(!Ready())
         return false;
      int request = DatabasePrepare(m_db.Handle(),
                                    "SELECT fingerprint FROM symbol_specs WHERE symbol=?");
      if(request == INVALID_HANDLE)
         return false;
      DatabaseBind(request, 0, symbol);
      bool found = false;
      if(DatabaseRead(request))
        {
         DatabaseColumnText(request, 0, fingerprint);
         found = true;
        }
      DatabaseFinalize(request);
      return found;
     }

   // -------------------------------------------------------------- events

   bool LogEvent(const string level, const string code,
                 const string context, const string message)
     {
      if(!Ready())
         return false;
      int request = DatabasePrepare(m_db.Handle(),
         "INSERT INTO runtime_events(ts,level,code,context,message) VALUES(?,?,?,?,?)");
      if(request == INVALID_HANDLE)
         return false;
      DatabaseBind(request, 0, (long)TimeCurrent());
      DatabaseBind(request, 1, level);
      DatabaseBind(request, 2, code);
      DatabaseBind(request, 3, context);
      DatabaseBind(request, 4, message);
      return Step(request, "LogEvent");
     }
  };
