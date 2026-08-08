#pragma once
#include "../Domain/Models.mqh"
#include "../Persistence/Repositories.mqh"

class AS_OutcomeEngine {
private:
   AS_Repositories *m_repo;

   bool Persist(AS_SignalCandidate &s,const ENUM_AS_SIGNAL_STATE state,const ENUM_AS_OUTCOME_SOURCE source,const string execution_id,const double exit_price,const double r_multiple,const string notes){
      if(m_repo==NULL||s.signal_id==""||m_repo.OutcomeExists(s.signal_id))return false;
      s.state=state;
      m_repo.UpdateSignalState(s.signal_id,state);
      return m_repo.SaveOutcome(s,state,source,execution_id,exit_price,r_multiple,notes);
   }
public:
   AS_OutcomeEngine(void){m_repo=NULL;}
   void Attach(AS_Repositories &repo){m_repo=&repo;}

   // Shadow evidence is explicitly observational: no broker execution exists.
   bool UpdateShadow(AS_SignalCandidate &s){
      if(s.signal_id==""||s.state!=AS_SIGNAL_ACTIVE)return false;
      MqlTick tick;if(!SymbolInfoTick(s.symbol,tick))return false;
      double px=(s.direction==AS_DIR_LONG?tick.bid:tick.ask);
      ENUM_AS_SIGNAL_STATE next=AS_SIGNAL_ACTIVE;
      if(s.direction==AS_DIR_LONG){if(px<=s.stop_loss)next=AS_SIGNAL_SL;else if(px>=s.take_profit)next=AS_SIGNAL_TP;}
      else if(s.direction==AS_DIR_SHORT){if(px>=s.stop_loss)next=AS_SIGNAL_SL;else if(px<=s.take_profit)next=AS_SIGNAL_TP;}
      if(next==AS_SIGNAL_ACTIVE&&TimeCurrent()>s.expires_at)next=AS_SIGNAL_EXPIRED;
      if(next==AS_SIGNAL_ACTIVE)return false;
      double risk=MathAbs(s.preferred_entry-s.stop_loss);
      double r=(risk>0?(s.direction==AS_DIR_LONG?(px-s.preferred_entry):(s.preferred_entry-px))/risk:0.0);
      return Persist(s,next,AS_OUTCOME_SOURCE_SHADOW,"",px,r,"SHADOW_OBSERVED_QUOTE");
   }

   // Demo evidence is derived only from broker deals belonging to the resolved
   // execution. A quote crossing TP/SL is not accepted as proof of execution.
   bool SyncDemoExecution(const AS_ExecutionRecord &x,AS_SignalCandidate &s,const ulong magic){
      if(m_repo==NULL||x.execution_id==""||x.signal_id==""||s.signal_id!=x.signal_id)return false;
      if(m_repo.OutcomeExists(s.signal_id))return false;

      if(x.state==AS_EXEC_REJECTED||x.state==AS_EXEC_CANCELLED){
         return Persist(s,AS_SIGNAL_NOT_FILLED,AS_OUTCOME_SOURCE_DEMO,x.execution_id,0.0,0.0,"DEMO_ORDER_NOT_FILLED");
      }
      if(x.state!=AS_EXEC_COMPLETED)return false;
      if(x.position_id==0)return false;

      AS_TradePlan plan;if(!m_repo.LoadPlan(x.plan_id,plan))return false;
      if(!HistorySelect(TimeCurrent()-86400*30,TimeCurrent()+60))return false;

      double entry_value=0.0,entry_volume=0.0,exit_value=0.0,exit_volume=0.0;
      long last_exit_reason=-1;int matched=0;
      for(int i=0;i<HistoryDealsTotal();i++){
         ulong deal=HistoryDealGetTicket(i);if(deal==0)continue;
         if((ulong)HistoryDealGetInteger(deal,DEAL_MAGIC)!=magic)continue;
         if(HistoryDealGetString(deal,DEAL_SYMBOL)!=x.symbol)continue;
         if((ulong)HistoryDealGetInteger(deal,DEAL_POSITION_ID)!=x.position_id)continue;
         long entry=HistoryDealGetInteger(deal,DEAL_ENTRY);double volume=HistoryDealGetDouble(deal,DEAL_VOLUME);double price=HistoryDealGetDouble(deal,DEAL_PRICE);
         if(entry==DEAL_ENTRY_IN){entry_value+=price*volume;entry_volume+=volume;matched++;}
         else if(entry==DEAL_ENTRY_OUT||entry==DEAL_ENTRY_OUT_BY){exit_value+=price*volume;exit_volume+=volume;last_exit_reason=HistoryDealGetInteger(deal,DEAL_REASON);matched++;}
      }
      if(matched==0||entry_volume<=0.0||exit_volume<=0.0)return false;

      double avg_entry=entry_value/entry_volume,avg_exit=exit_value/exit_volume;
      double risk=MathAbs(avg_entry-plan.stop_loss);double r=0.0;
      if(risk>0.0)r=(plan.direction==AS_DIR_LONG?(avg_exit-avg_entry):(avg_entry-avg_exit))/risk;

      ENUM_AS_SIGNAL_STATE result_state=AS_SIGNAL_INVALIDATED;
      string note="DEMO_EXIT_OTHER";
      if(last_exit_reason==DEAL_REASON_TP){result_state=AS_SIGNAL_TP;note="DEMO_BROKER_TP";}
      else if(last_exit_reason==DEAL_REASON_SL){result_state=AS_SIGNAL_SL;note="DEMO_BROKER_SL";}
      return Persist(s,result_state,AS_OUTCOME_SOURCE_DEMO,x.execution_id,avg_exit,r,note);
   }
};