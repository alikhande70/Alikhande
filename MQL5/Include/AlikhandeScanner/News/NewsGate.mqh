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

   bool BlocksTrading(const AS_NewsStateV13 &state){
      if(state.available)return state.blocked;
      AS_RuntimeContext ctx;m_runtime_reader.Read(ctx);
      // Real terminal is fail-closed: if the configured news gate cannot see,
      // no demo order is allowed. Tester/optimization may continue so strategy
      // logic can still be measured, but the run remains explicitly NEWS-BLIND.
      return ctx.kind==AS_RUNTIME_TERMINAL;
   }

   bool NewsBlind(const AS_NewsStateV13 &state){
      if(state.available)return false;
      AS_RuntimeContext ctx;m_runtime_reader.Read(ctx);
      return ctx.kind==AS_RUNTIME_TESTER || ctx.kind==AS_RUNTIME_OPTIMIZATION;
   }

   bool BlockedNow(const string symbol,const int before_min,const int after_min,string &reason){
      AS_NewsStateV13 state;Evaluate(symbol,before_min,after_min,state);reason=state.reason;return BlocksTrading(state);
   }
};