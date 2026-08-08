#pragma once
#include "../Domain/Models.mqh"
#include "../Core/Hash.mqh"
#include "Preflight.mqh"
#include "DealLedgerV13.mqh"
#include "ReconcilerV13.mqh"
#include "../Persistence/Repositories.mqh"

class AS_ExecutionEngine {
private:
   AS_Preflight m_preflight;
   AS_Repositories *m_repo;
   AS_Database *m_db;
   AS_DealLedgerV13 m_deals;
   AS_ReconcilerV13 m_reconciler;
   AS_ExecutionRecord m_current;

   bool ScannerDeal(const ulong deal_ticket){
      if(deal_ticket==0 || !HistoryDealSelect(deal_ticket)) return false;
      if((ulong)HistoryDealGetInteger(deal_ticket,DEAL_MAGIC)!=AS_MAGIC) return false;
      return m_current.symbol=="" || HistoryDealGetString(deal_ticket,DEAL_SYMBOL)==m_current.symbol;
   }

   void Save(){if(m_repo!=NULL)m_repo.SaveExecution(m_current);}
public:
   AS_ExecutionEngine(void){m_repo=NULL;m_db=NULL;ZeroMemory(m_current);m_current.state=AS_EXEC_IDLE;}

   void Attach(AS_Repositories &repo,AS_Database &db){
      m_repo=&repo;m_db=&db;m_deals.Attach(db);
      if(m_repo.LoadLatestUnresolvedExecution(m_current))Reconcile();
   }

   // Legacy attachment deliberately does not enable execution: durable deal
   // idempotency is a required dependency in v1.3.
   void Attach(AS_Repositories &repo){m_repo=&repo;m_db=NULL;m_repo.LoadLatestUnresolvedExecution(m_current);}

   bool HasUnresolved()const{
      return m_current.state==AS_EXEC_SUBMITTING || m_current.state==AS_EXEC_ACCEPTED ||
             m_current.state==AS_EXEC_PARTIALLY_FILLED || m_current.state==AS_EXEC_FILLED ||
             m_current.state==AS_EXEC_POSITION_ACTIVE || m_current.state==AS_EXEC_UNKNOWN ||
             m_current.state==AS_EXEC_RECONCILING;
   }
   AS_ExecutionRecord Current()const{return m_current;}

   bool SubmitDemo(const AS_TradePlan &p,string &reason){
      reason="";
      if(AccountInfoInteger(ACCOUNT_TRADE_MODE)!=ACCOUNT_TRADE_MODE_DEMO){reason="REAL_ACCOUNT_BLOCKED";return false;}
      if(m_db==NULL || !m_db.Ready()){reason="PERSISTENCE_REQUIRED_FOR_EXECUTION";return false;}
      if(HasUnresolved()){reason="EXECUTION_ALREADY_UNRESOLVED";return false;}
      MqlTradeRequest req;MqlTradeCheckResult chk;
      if(!m_preflight.Validate(p,req,chk,reason))return false;
      ZeroMemory(m_current);
      m_current.execution_id=AS_Fnv1a(p.plan_id+"|"+IntegerToString((int)TimeCurrent())+"|"+p.symbol);
      m_current.plan_id=p.plan_id;m_current.signal_id=p.signal_id;m_current.symbol=p.symbol;
      m_current.state=AS_EXEC_SUBMITTING;m_current.requested_volume=p.lot_size;m_current.updated_at=TimeCurrent();m_current.terminal=false;

      // Intent must exist durably before OrderSend. If persistence fails, no order leaves.
      if(m_repo==NULL || !m_repo.SaveExecution(m_current)){reason="INTENT_PERSIST_FAILED";m_current.state=AS_EXEC_REJECTED;m_current.terminal=true;return false;}

      MqlTradeResult result;ZeroMemory(result);
      bool sent=OrderSend(req,result);
      m_current.request_id=result.request_id;m_current.order_ticket=result.order;m_current.deal_ticket=result.deal;
      m_current.retcode=result.retcode;m_current.message=result.comment;m_current.updated_at=TimeCurrent();
      if(!sent){m_current.state=AS_EXEC_REJECTED;m_current.terminal=true;reason=StringFormat("ORDERSEND_%u_%s",result.retcode,result.comment);}
      else if(result.retcode==TRADE_RETCODE_DONE){m_current.state=AS_EXEC_FILLED;}
      else if(result.retcode==TRADE_RETCODE_DONE_PARTIAL){m_current.state=AS_EXEC_PARTIALLY_FILLED;}
      else if(result.retcode==TRADE_RETCODE_PLACED){m_current.state=AS_EXEC_ACCEPTED;}
      else{m_current.state=AS_EXEC_UNKNOWN;reason=StringFormat("UNKNOWN_SUBMIT_%u_%s",result.retcode,result.comment);}
      Save();
      return sent;
   }

   void OnTransaction(const MqlTradeTransaction &trans,const MqlTradeRequest &request,const MqlTradeResult &result){
      if(m_current.execution_id=="")return;
      bool related=false;
      if(m_current.request_id>0 && result.request_id==m_current.request_id)related=true;
      if(m_current.order_ticket>0 && trans.order==m_current.order_ticket)related=true;
      if(m_current.deal_ticket>0 && trans.deal==m_current.deal_ticket)related=true;
      if(!related && trans.type==TRADE_TRANSACTION_DEAL_ADD && ScannerDeal(trans.deal))related=true;
      if(!related)return;

      if(trans.order>0)m_current.order_ticket=trans.order;
      if(trans.position>0)m_current.position_id=trans.position;
      if(result.retcode>0)m_current.retcode=result.retcode;

      if(trans.type==TRADE_TRANSACTION_DEAL_ADD && trans.deal>0 && HistoryDealSelect(trans.deal)){
         if(!ScannerDeal(trans.deal))return;
         const long entry=HistoryDealGetInteger(trans.deal,DEAL_ENTRY);
         const double volume=HistoryDealGetDouble(trans.deal,DEAL_VOLUME);
         const double price=HistoryDealGetDouble(trans.deal,DEAL_PRICE);
         const double net=HistoryDealGetDouble(trans.deal,DEAL_PROFIT)+HistoryDealGetDouble(trans.deal,DEAL_COMMISSION)+HistoryDealGetDouble(trans.deal,DEAL_SWAP);

         // The persistent ledger is the admission gate. A replay exits here
         // before deal_ticket or filled_volume can mutate again.
         if(!m_deals.Admit(trans.deal,m_current.execution_id,m_current.symbol,(int)entry,volume,price,net))return;

         m_current.deal_ticket=trans.deal;
         if(entry==DEAL_ENTRY_OUT || entry==DEAL_ENTRY_OUT_BY){m_current.state=AS_EXEC_RECONCILING;}
         else{
            m_current.filled_volume+=volume;
            const double step=SymbolInfoDouble(m_current.symbol,SYMBOL_VOLUME_STEP);
            const double tolerance=(step>0.0?step*0.5:1e-8);
            m_current.state=(m_current.filled_volume+tolerance>=m_current.requested_volume?AS_EXEC_FILLED:AS_EXEC_PARTIALLY_FILLED);
         }
      } else if(trans.type==TRADE_TRANSACTION_POSITION){
         m_current.state=AS_EXEC_POSITION_ACTIVE;
      } else if(trans.type==TRADE_TRANSACTION_ORDER_DELETE){
         m_current.state=AS_EXEC_RECONCILING;
      }
      m_current.updated_at=TimeCurrent();Save();
   }

   void Reconcile(){
      if(!HasUnresolved())return;
      AS_ReconcileResultV13 rebuilt;
      if(!m_reconciler.Rebuild(m_current,AS_MAGIC,rebuilt)){
         m_current.state=AS_EXEC_UNKNOWN;m_current.message=rebuilt.reason;m_current.updated_at=TimeCurrent();Save();return;
      }
      m_current.state=rebuilt.state;
      if(rebuilt.position_id>0)m_current.position_id=rebuilt.position_id;
      m_current.terminal=rebuilt.terminal;
      m_current.message=rebuilt.reason;
      m_current.updated_at=TimeCurrent();Save();
   }
};
