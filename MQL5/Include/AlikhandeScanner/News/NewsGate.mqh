#pragma once
#include "../Core/Config.mqh"
#include "../Core/RuntimeContext.mqh"
#include "CalendarProviderV13.mqh"

class AS_NewsGate {
private:
   AS_RuntimeContextReader m_runtime_reader;
   AS_CalendarProviderV13 m_provider;
public:
   bool BlockedNow(const string symbol,const int before_min,const int after_min,string &reason){
      reason="";
      AS_RuntimeContext ctx;m_runtime_reader.Read(ctx);
      AS_NewsStateV13 state;m_provider.Evaluate(ctx,symbol,before_min,after_min,state);
      if(!state.available){reason=state.reason;return false;}
      reason=state.reason;
      return state.blocked;
   }
};