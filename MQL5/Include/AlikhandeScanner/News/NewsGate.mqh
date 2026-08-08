#pragma once
#include "../Core/Config.mqh"
#include "../Core/RuntimeContext.mqh"
#include "CalendarProviderV13.mqh"

class AS_NewsGate {
private:
   AS_RuntimeContextReader m_runtime_reader;
   AS_CalendarProviderV13 m_provider;
public:
   void Evaluate(const string symbol,const int before_min,const int after_min,AS_NewsStateV13 &state){
      AS_RuntimeContext ctx;m_runtime_reader.Read(ctx);m_provider.Evaluate(ctx,symbol,before_min,after_min,state);
   }

   bool BlockedNow(const string symbol,const int before_min,const int after_min,string &reason){
      AS_NewsStateV13 state;Evaluate(symbol,before_min,after_min,state);
      reason=state.reason;
      if(!state.available)return false;
      return state.blocked;
   }
};