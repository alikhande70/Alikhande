#pragma once
#include "../Persistence/Database.mqh"

// Persistent admission gate for trade deals. A deal must pass this ledger
// before it is allowed to mutate in-memory execution state.
class AS_DealLedgerV13
  {
private:
   AS_Database *m_db;
public:
   AS_DealLedgerV13(void){m_db=NULL;}
   void Attach(AS_Database &db){m_db=&db;}

   bool AlreadyRecorded(const ulong deal_ticket) const
     {
      if(m_db==NULL || !m_db.Ready() || deal_ticket==0)return false;
      int q=DatabasePrepare(m_db.Handle(),"SELECT deal_ticket FROM execution_deals WHERE deal_ticket=?1 LIMIT 1");
      if(q==INVALID_HANDLE)return false;
      DatabaseBind(q,0,(long)deal_ticket);
      const bool exists=DatabaseRead(q);
      DatabaseFinalize(q);
      return exists;
     }

   bool Admit(const ulong deal_ticket,const string execution_id,const string symbol,const int entry_type,
              const double volume,const double price,const double net_profit)
     {
      if(m_db==NULL || !m_db.Ready() || deal_ticket==0)return false;
      if(AlreadyRecorded(deal_ticket))return false;
      int q=DatabasePrepare(m_db.Handle(),"INSERT INTO execution_deals(deal_ticket,execution_id,symbol,entry_type,volume,price,net_profit,recorded_at) VALUES(?1,?2,?3,?4,?5,?6,?7,?8)");
      if(q==INVALID_HANDLE)return false;
      bool ok=true;int n=0;
      ok&=DatabaseBind(q,n++,(long)deal_ticket);
      ok&=DatabaseBind(q,n++,execution_id);
      ok&=DatabaseBind(q,n++,symbol);
      ok&=DatabaseBind(q,n++,entry_type);
      ok&=DatabaseBind(q,n++,volume);
      ok&=DatabaseBind(q,n++,price);
      ok&=DatabaseBind(q,n++,net_profit);
      ok&=DatabaseBind(q,n++,(long)TimeCurrent());
      if(ok)ok=DatabaseRead(q);
      const int err=GetLastError();
      DatabaseFinalize(q);
      return ok || err==ERR_DATABASE_NO_MORE_DATA;
     }
  };
