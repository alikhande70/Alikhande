#pragma once
#include "../Domain/Models.mqh"

class AS_MarketData {
public:
   bool EnsureReady(const string symbol,const ENUM_TIMEFRAMES tf,const int min_bars,ENUM_AS_DATA_STATE &state) {
      if(!SymbolSelect(symbol,true)) { state=AS_DATA_ERROR; return false; }
      if(!SymbolIsSynchronized(symbol)) { state=AS_DATA_SYNCHRONIZING; return false; }
      long synced=0; ResetLastError();
      if(!SeriesInfoInteger(symbol,tf,SERIES_SYNCHRONIZED,synced) || synced==0) { state=AS_DATA_DOWNLOADING; return false; }
      if(Bars(symbol,tf)<min_bars) { state=AS_DATA_DOWNLOADING; return false; }
      state=AS_DATA_READY; return true;
   }

   bool EnsureAllReady(const string symbol,const int min_bars,ENUM_AS_DATA_STATE &state){
      ENUM_TIMEFRAMES tfs[4]={PERIOD_H4,PERIOD_H1,PERIOD_M15,PERIOD_M5};
      for(int i=0;i<4;i++)if(!EnsureReady(symbol,tfs[i],min_bars,state))return false;
      state=AS_DATA_READY;return true;
   }

   bool Snapshot(const string requested,const string symbol,const int max_tick_age_seconds,AS_SymbolSnapshot &s) {
      ZeroMemory(s); MqlTick tick; s.requested_symbol=requested; s.symbol=symbol;
      if(!SymbolInfoTick(symbol,tick)) { s.spread_state=AS_SPREAD_NO_TICK; s.data_state=AS_DATA_ERROR; return false; }
      s.bid=tick.bid; s.ask=tick.ask; s.tick_time=(datetime)tick.time;
      s.point=SymbolInfoDouble(symbol,SYMBOL_POINT); s.digits=(int)SymbolInfoInteger(symbol,SYMBOL_DIGITS);
      if(s.point<=0 || s.ask<=0 || s.bid<=0) { s.data_state=AS_DATA_ERROR; return false; }
      s.spread_points=(s.ask-s.bid)/s.point;
      if(max_tick_age_seconds>0 && TimeCurrent()-s.tick_time>max_tick_age_seconds){s.spread_state=AS_SPREAD_STALE;s.data_state=AS_DATA_STALE;return true;}
      s.data_state=AS_DATA_READY; return true;
   }

   bool Rates(const string symbol,const ENUM_TIMEFRAMES tf,const int start_shift,const int count,MqlRates &rates[]) {
      ArraySetAsSeries(rates,true); int copied=CopyRates(symbol,tf,start_shift,count,rates); return copied==count;
   }
};
