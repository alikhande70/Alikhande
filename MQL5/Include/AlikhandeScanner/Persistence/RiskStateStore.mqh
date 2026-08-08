#pragma once
#include "Database.mqh"

struct AS_RiskStateSnapshot {
   int day_key;
   double day_start_equity;
   double peak_equity;
   int consecutive_losses;
   datetime updated_at;
};

class AS_RiskStateStore {
private:
   AS_Database *m_db;
public:
   AS_RiskStateStore(void){m_db=NULL;}
   void Attach(AS_Database &db){m_db=&db;}

   bool Load(AS_RiskStateSnapshot &s){
      ZeroMemory(s);
      if(m_db==NULL||!m_db.Ready())return false;
      int q=DatabasePrepare(m_db.Handle(),"SELECT day_key,day_start_equity,peak_equity,consecutive_losses,updated_at FROM risk_state WHERE id=1");
      if(q==INVALID_HANDLE)return false;
      if(!DatabaseRead(q)){DatabaseFinalize(q);return false;}
      long day=0,losses=0,updated=0;
      DatabaseColumnLong(q,0,day);DatabaseColumnDouble(q,1,s.day_start_equity);DatabaseColumnDouble(q,2,s.peak_equity);DatabaseColumnLong(q,3,losses);DatabaseColumnLong(q,4,updated);
      DatabaseFinalize(q);
      s.day_key=(int)day;s.consecutive_losses=(int)losses;s.updated_at=(datetime)updated;
      return true;
   }

   bool Save(const AS_RiskStateSnapshot &s){
      if(m_db==NULL||!m_db.Ready())return false;
      int q=DatabasePrepare(m_db.Handle(),"INSERT OR REPLACE INTO risk_state(id,day_key,day_start_equity,peak_equity,consecutive_losses,updated_at) VALUES(1,?1,?2,?3,?4,?5)");
      if(q==INVALID_HANDLE)return false;
      bool ok=DatabaseBind(q,0,s.day_key)&&DatabaseBind(q,1,s.day_start_equity)&&DatabaseBind(q,2,s.peak_equity)&&DatabaseBind(q,3,s.consecutive_losses)&&DatabaseBind(q,4,(long)s.updated_at);
      if(ok)ok=DatabaseRead(q);
      int e=GetLastError();DatabaseFinalize(q);return ok||e==ERR_DATABASE_NO_MORE_DATA;
   }
};
