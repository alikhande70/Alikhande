#pragma once
#include "../Core/Config.mqh"

class AS_AccountRiskGuard {
private:
   int m_day_key;double m_day_start_equity;double m_peak_equity;int m_consecutive_losses;
   int DayKey(){MqlDateTime dt;TimeToStruct(TimeCurrent(),dt);return dt.year*1000+dt.day_of_year;}
   void RollDay(){int k=DayKey();if(k!=m_day_key){m_day_key=k;m_day_start_equity=AccountInfoDouble(ACCOUNT_EQUITY);m_consecutive_losses=0;}}
public:
   AS_AccountRiskGuard(void){m_day_key=0;m_day_start_equity=0;m_peak_equity=0;m_consecutive_losses=0;}
   void Initialize(){m_day_key=DayKey();m_day_start_equity=AccountInfoDouble(ACCOUNT_EQUITY);m_peak_equity=m_day_start_equity;m_consecutive_losses=0;}
   void RegisterClosedProfit(const double net_profit){if(net_profit<0)m_consecutive_losses++;else if(net_profit>0)m_consecutive_losses=0;}
   bool Check(const bool enabled,string &codes){if(!enabled)return true;RollDay();double eq=AccountInfoDouble(ACCOUNT_EQUITY);if(eq>m_peak_equity)m_peak_equity=eq;bool ok=true;
      if(m_day_start_equity>0&&(m_day_start_equity-eq)/m_day_start_equity*100.0>=AS_DEFAULT_DAILY_LOSS_LIMIT_PCT){ok=false;codes+="DAILY_LOSS_HALT;";}
      if(m_peak_equity>0&&(m_peak_equity-eq)/m_peak_equity*100.0>=AS_DEFAULT_TOTAL_DRAWDOWN_LIMIT_PCT){ok=false;codes+="TOTAL_DRAWDOWN_HALT;";}
      if(m_consecutive_losses>=AS_DEFAULT_MAX_CONSECUTIVE_LOSSES){ok=false;codes+="CONSECUTIVE_LOSS_HALT;";}return ok;}
};
