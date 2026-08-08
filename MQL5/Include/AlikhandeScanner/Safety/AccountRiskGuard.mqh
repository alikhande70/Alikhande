#pragma once
#include "../Core/Config.mqh"
#include "../Persistence/RiskStateStore.mqh"

class AS_AccountRiskGuard {
private:
   int m_day_key;
   double m_day_start_equity;
   double m_peak_equity;
   int m_consecutive_losses;
   AS_RiskStateStore *m_store;

   int DayKey(){MqlDateTime dt;TimeToStruct(TimeCurrent(),dt);return dt.year*1000+dt.day_of_year;}
   void Persist(){if(m_store==NULL)return;AS_RiskStateSnapshot s;s.day_key=m_day_key;s.day_start_equity=m_day_start_equity;s.peak_equity=m_peak_equity;s.consecutive_losses=m_consecutive_losses;s.updated_at=TimeCurrent();m_store.Save(s);}
   void RollDay(){int k=DayKey();if(k!=m_day_key){m_day_key=k;m_day_start_equity=AccountInfoDouble(ACCOUNT_EQUITY);m_consecutive_losses=0;if(m_day_start_equity>m_peak_equity)m_peak_equity=m_day_start_equity;Persist();}}
public:
   AS_AccountRiskGuard(void){m_day_key=0;m_day_start_equity=0;m_peak_equity=0;m_consecutive_losses=0;m_store=NULL;}
   void Attach(AS_RiskStateStore &store){m_store=&store;}
   void Initialize(){
      AS_RiskStateSnapshot saved;
      if(m_store!=NULL&&m_store.Load(saved)&&saved.day_key==DayKey()&&saved.day_start_equity>0){m_day_key=saved.day_key;m_day_start_equity=saved.day_start_equity;m_peak_equity=MathMax(saved.peak_equity,AccountInfoDouble(ACCOUNT_EQUITY));m_consecutive_losses=saved.consecutive_losses;Persist();return;}
      m_day_key=DayKey();m_day_start_equity=AccountInfoDouble(ACCOUNT_EQUITY);m_peak_equity=m_day_start_equity;m_consecutive_losses=0;Persist();
   }
   void RegisterClosedProfit(const double net_profit){if(net_profit<0)m_consecutive_losses++;else if(net_profit>0)m_consecutive_losses=0;Persist();}
   bool Check(const bool enabled,string &codes){
      if(!enabled)return true;RollDay();double eq=AccountInfoDouble(ACCOUNT_EQUITY);if(eq>m_peak_equity){m_peak_equity=eq;Persist();}
      bool ok=true;
      if(m_day_start_equity>0&&(m_day_start_equity-eq)/m_day_start_equity*100.0>=AS_DEFAULT_DAILY_LOSS_LIMIT_PCT){ok=false;codes+="DAILY_LOSS_HALT;";}
      if(m_peak_equity>0&&(m_peak_equity-eq)/m_peak_equity*100.0>=AS_DEFAULT_TOTAL_DRAWDOWN_LIMIT_PCT){ok=false;codes+="TOTAL_DRAWDOWN_HALT;";}
      if(m_consecutive_losses>=AS_DEFAULT_MAX_CONSECUTIVE_LOSSES){ok=false;codes+="CONSECUTIVE_LOSS_HALT;";}
      return ok;
   }
};
