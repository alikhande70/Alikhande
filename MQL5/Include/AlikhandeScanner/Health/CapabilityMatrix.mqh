#pragma once
#include "../Domain/Models.mqh"
class AS_CapabilityMatrix {
public:
   AS_HealthSnapshot Inspect(const bool db_ready,const bool data_ready,const bool unresolved_execution){ AS_HealthSnapshot h;ZeroMemory(h);h.demo_account=AccountInfoInteger(ACCOUNT_TRADE_MODE)==ACCOUNT_TRADE_MODE_DEMO;h.trade_allowed=(bool)AccountInfoInteger(ACCOUNT_TRADE_ALLOWED)&&(bool)MQLInfoInteger(MQL_TRADE_ALLOWED);h.db_ready=db_ready;h.data_ready=data_ready;h.history_ready=true;h.execution_blocked=!h.demo_account||!h.trade_allowed||!db_ready||unresolved_execution;h.state=(h.execution_blocked?AS_HEALTH_BLOCKED:(data_ready?AS_HEALTH_OK:AS_HEALTH_DEGRADED));h.reasons="";if(!h.demo_account)h.reasons+="REAL_ACCOUNT;";if(!h.trade_allowed)h.reasons+="TRADE_NOT_ALLOWED;";if(!db_ready)h.reasons+="DB_NOT_READY;";if(!data_ready)h.reasons+="DATA_NOT_READY;";if(unresolved_execution)h.reasons+="UNRESOLVED_EXECUTION;";return h; }
};
