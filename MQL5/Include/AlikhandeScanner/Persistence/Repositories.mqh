#pragma once
#include "Database.mqh"
#include "../Domain/Models.mqh"

class AS_Repositories {
private:
   AS_Database *m_db;
   bool WriteDone(const bool ok,const int q){int e=GetLastError();DatabaseFinalize(q);return ok||e==ERR_DATABASE_NO_MORE_DATA;}
public:
   AS_Repositories(void){m_db=NULL;}
   void Attach(AS_Database &db){m_db=&db;}

   bool SignalExists(const string signal_id){
      if(m_db==NULL||!m_db.Ready())return false;
      int q=DatabasePrepare(m_db.Handle(),"SELECT signal_id FROM signals WHERE signal_id=?1 LIMIT 1");if(q==INVALID_HANDLE)return false;
      DatabaseBind(q,0,signal_id);bool exists=DatabaseRead(q);DatabaseFinalize(q);return exists;
   }

   bool SaveSignal(const AS_SignalCandidate &s){
      if(m_db==NULL||!m_db.Ready())return false;
      int q=DatabasePrepare(m_db.Handle(),"INSERT OR REPLACE INTO signals(signal_id,symbol,direction,setup,state,created_at,confirmation_time,expires_at,entry,sl,tp,long_score,short_score,rule_version,scoring_version,parameter_hash,broker_spec_hash,regime,regime_confidence,reasons,validation_codes) VALUES(?1,?2,?3,?4,?5,?6,?7,?8,?9,?10,?11,?12,?13,?14,?15,?16,?17,?18,?19,?20,?21)");if(q==INVALID_HANDLE)return false;
      bool ok=true;int n=0;
      ok&=DatabaseBind(q,n++,s.signal_id);ok&=DatabaseBind(q,n++,s.symbol);ok&=DatabaseBind(q,n++,(int)s.direction);ok&=DatabaseBind(q,n++,(int)s.setup);ok&=DatabaseBind(q,n++,(int)s.state);
      ok&=DatabaseBind(q,n++,(long)s.creation_time);ok&=DatabaseBind(q,n++,(long)s.confirmation_bar_time);ok&=DatabaseBind(q,n++,(long)s.expires_at);
      ok&=DatabaseBind(q,n++,s.preferred_entry);ok&=DatabaseBind(q,n++,s.stop_loss);ok&=DatabaseBind(q,n++,s.take_profit);ok&=DatabaseBind(q,n++,s.long_score);ok&=DatabaseBind(q,n++,s.short_score);
      ok&=DatabaseBind(q,n++,s.rule_version);ok&=DatabaseBind(q,n++,s.scoring_version);ok&=DatabaseBind(q,n++,s.parameter_hash);ok&=DatabaseBind(q,n++,s.broker_spec_hash);
      ok&=DatabaseBind(q,n++,(int)s.regime);ok&=DatabaseBind(q,n++,s.regime_confidence);ok&=DatabaseBind(q,n++,s.reasons);ok&=DatabaseBind(q,n++,s.validation_codes);
      if(ok)ok=DatabaseRead(q);return WriteDone(ok,q);
   }

   bool UpdateSignalState(const string signal_id,const ENUM_AS_SIGNAL_STATE state){
      if(m_db==NULL||!m_db.Ready())return false;int q=DatabasePrepare(m_db.Handle(),"UPDATE signals SET state=?1 WHERE signal_id=?2");if(q==INVALID_HANDLE)return false;
      bool ok=DatabaseBind(q,0,(int)state)&&DatabaseBind(q,1,signal_id);if(ok)ok=DatabaseRead(q);return WriteDone(ok,q);
   }

   bool SavePlan(const AS_TradePlan &p){
      if(m_db==NULL||!m_db.Ready())return false;
      int q=DatabasePrepare(m_db.Handle(),"INSERT OR REPLACE INTO trade_plans(plan_id,signal_id,symbol,direction,entry,sl,tp,risk_pct,risk_amount,actual_risk,lot,margin,created_at,expires_at,broker_spec_hash,validation_codes) VALUES(?1,?2,?3,?4,?5,?6,?7,?8,?9,?10,?11,?12,?13,?14,?15,?16)");if(q==INVALID_HANDLE)return false;bool ok=true;int n=0;
      ok&=DatabaseBind(q,n++,p.plan_id);ok&=DatabaseBind(q,n++,p.signal_id);ok&=DatabaseBind(q,n++,p.symbol);ok&=DatabaseBind(q,n++,(int)p.direction);ok&=DatabaseBind(q,n++,p.entry);ok&=DatabaseBind(q,n++,p.stop_loss);ok&=DatabaseBind(q,n++,p.take_profit);ok&=DatabaseBind(q,n++,p.risk_percent);ok&=DatabaseBind(q,n++,p.risk_amount);ok&=DatabaseBind(q,n++,p.actual_risk_amount);ok&=DatabaseBind(q,n++,p.lot_size);ok&=DatabaseBind(q,n++,p.margin_required);ok&=DatabaseBind(q,n++,(long)p.created_at);ok&=DatabaseBind(q,n++,(long)p.expires_at);ok&=DatabaseBind(q,n++,p.broker_spec_hash);ok&=DatabaseBind(q,n++,p.validation_codes);if(ok)ok=DatabaseRead(q);return WriteDone(ok,q);
   }

   bool SaveExecution(const AS_ExecutionRecord &x){
      if(m_db==NULL||!m_db.Ready())return false;
      int q=DatabasePrepare(m_db.Handle(),"INSERT OR REPLACE INTO executions(execution_id,plan_id,signal_id,symbol,state,request_id,order_ticket,deal_ticket,position_id,retcode,requested_volume,filled_volume,updated_at,message) VALUES(?1,?2,?3,?4,?5,?6,?7,?8,?9,?10,?11,?12,?13,?14)");if(q==INVALID_HANDLE)return false;bool ok=true;int n=0;
      ok&=DatabaseBind(q,n++,x.execution_id);ok&=DatabaseBind(q,n++,x.plan_id);ok&=DatabaseBind(q,n++,x.signal_id);ok&=DatabaseBind(q,n++,x.symbol);ok&=DatabaseBind(q,n++,(int)x.state);
      ok&=DatabaseBind(q,n++,(long)x.request_id);ok&=DatabaseBind(q,n++,(long)x.order_ticket);ok&=DatabaseBind(q,n++,(long)x.deal_ticket);ok&=DatabaseBind(q,n++,(long)x.position_id);ok&=DatabaseBind(q,n++,(long)x.retcode);
      ok&=DatabaseBind(q,n++,x.requested_volume);ok&=DatabaseBind(q,n++,x.filled_volume);ok&=DatabaseBind(q,n++,(long)x.updated_at);ok&=DatabaseBind(q,n++,x.message);if(ok)ok=DatabaseRead(q);return WriteDone(ok,q);
   }

   bool SaveOutcome(const string signal_id,const ENUM_AS_SIGNAL_STATE state,const double exit_price,const double r_multiple,const string notes){
      if(m_db==NULL||!m_db.Ready())return false;int q=DatabasePrepare(m_db.Handle(),"INSERT OR REPLACE INTO outcomes(signal_id,state,resolved_at,exit_price,r_multiple,mfe_r,mae_r,notes) VALUES(?1,?2,?3,?4,?5,0,0,?6)");if(q==INVALID_HANDLE)return false;
      bool ok=DatabaseBind(q,0,signal_id)&&DatabaseBind(q,1,(int)state)&&DatabaseBind(q,2,(long)TimeCurrent())&&DatabaseBind(q,3,exit_price)&&DatabaseBind(q,4,r_multiple)&&DatabaseBind(q,5,notes);if(ok)ok=DatabaseRead(q);return WriteDone(ok,q);
   }

   int CountTable(const string table_name){if(m_db==NULL||!m_db.Ready())return 0;if(table_name!="signals"&&table_name!="outcomes"&&table_name!="executions")return 0;int q=DatabasePrepare(m_db.Handle(),"SELECT COUNT(*) FROM "+table_name);if(q==INVALID_HANDLE)return 0;int count=0;if(DatabaseRead(q))DatabaseColumnInteger(q,0,count);DatabaseFinalize(q);return count;}

   string LatestSpecHash(const string symbol){if(m_db==NULL||!m_db.Ready())return "";int q=DatabasePrepare(m_db.Handle(),"SELECT spec_hash FROM symbol_specs WHERE symbol=?1 ORDER BY captured_at DESC LIMIT 1");if(q==INVALID_HANDLE)return "";DatabaseBind(q,0,symbol);string hash="";if(DatabaseRead(q))DatabaseColumnText(q,0,hash);DatabaseFinalize(q);return hash;}

   bool SaveSpec(const AS_SymbolSpec &s){
      if(m_db==NULL||!m_db.Ready()||!s.ready)return false;int q=DatabasePrepare(m_db.Handle(),"INSERT INTO symbol_specs(symbol,spec_hash,captured_at,digits,point,tick_size,tick_value,contract_size,volume_min,volume_max,volume_step,stops_level,freeze_level,filling_mode) VALUES(?1,?2,?3,?4,?5,?6,?7,?8,?9,?10,?11,?12,?13,?14)");if(q==INVALID_HANDLE)return false;bool ok=true;int n=0;
      ok&=DatabaseBind(q,n++,s.symbol);ok&=DatabaseBind(q,n++,s.spec_hash);ok&=DatabaseBind(q,n++,(long)TimeCurrent());ok&=DatabaseBind(q,n++,s.digits);ok&=DatabaseBind(q,n++,s.point);ok&=DatabaseBind(q,n++,s.tick_size);ok&=DatabaseBind(q,n++,s.tick_value);ok&=DatabaseBind(q,n++,s.contract_size);ok&=DatabaseBind(q,n++,s.volume_min);ok&=DatabaseBind(q,n++,s.volume_max);ok&=DatabaseBind(q,n++,s.volume_step);ok&=DatabaseBind(q,n++,s.stops_level);ok&=DatabaseBind(q,n++,s.freeze_level);ok&=DatabaseBind(q,n++,(long)s.filling_mode);if(ok)ok=DatabaseRead(q);return WriteDone(ok,q);
   }

   bool LoadLatestUnresolvedExecution(AS_ExecutionRecord &x){
      ZeroMemory(x);if(m_db==NULL||!m_db.Ready())return false;
      // enum states: SUBMITTING=4, ACCEPTED=5, PARTIAL=6, FILLED=7, POSITION_ACTIVE=8, UNKNOWN=11, RECONCILING=12
      int q=DatabasePrepare(m_db.Handle(),"SELECT execution_id,plan_id,signal_id,symbol,state,request_id,order_ticket,deal_ticket,position_id,retcode,requested_volume,filled_volume,updated_at,message FROM executions WHERE state IN (4,5,6,7,8,11,12) ORDER BY updated_at DESC LIMIT 1");if(q==INVALID_HANDLE)return false;
      if(!DatabaseRead(q)){DatabaseFinalize(q);return false;}
      string a,b,c,d,msg;long st=0,req=0,ord=0,deal=0,pos=0,ret=0,upd=0;double rv=0,fv=0;
      DatabaseColumnText(q,0,a);DatabaseColumnText(q,1,b);DatabaseColumnText(q,2,c);DatabaseColumnText(q,3,d);DatabaseColumnLong(q,4,st);DatabaseColumnLong(q,5,req);DatabaseColumnLong(q,6,ord);DatabaseColumnLong(q,7,deal);DatabaseColumnLong(q,8,pos);DatabaseColumnLong(q,9,ret);DatabaseColumnDouble(q,10,rv);DatabaseColumnDouble(q,11,fv);DatabaseColumnLong(q,12,upd);DatabaseColumnText(q,13,msg);DatabaseFinalize(q);
      x.execution_id=a;x.plan_id=b;x.signal_id=c;x.symbol=d;x.state=(ENUM_AS_EXEC_STATE)st;x.request_id=(ulong)req;x.order_ticket=(ulong)ord;x.deal_ticket=(ulong)deal;x.position_id=(ulong)pos;x.retcode=(uint)ret;x.requested_volume=rv;x.filled_volume=fv;x.updated_at=(datetime)upd;x.message=msg;x.terminal=false;return true;
   }

   void RuntimeEvent(const string severity,const string component,const string code,const string message){if(m_db==NULL||!m_db.Ready())return;int q=DatabasePrepare(m_db.Handle(),"INSERT INTO runtime_events(event_time,severity,component,code,message) VALUES(?1,?2,?3,?4,?5)");if(q==INVALID_HANDLE)return;bool ok=DatabaseBind(q,0,(long)TimeCurrent())&&DatabaseBind(q,1,severity)&&DatabaseBind(q,2,component)&&DatabaseBind(q,3,code)&&DatabaseBind(q,4,message);if(ok)DatabaseRead(q);DatabaseFinalize(q);}
};
