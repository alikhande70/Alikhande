#pragma once
#include "../Domain/Models.mqh"
#include "RuntimeSnapshots.mqh"

class AS_MarketData {
private:
   AS_RuntimeSnapshots m_runtime;
public:
   bool EnsureReady(const string symbol,const ENUM_TIMEFRAMES tf,const int min_bars,ENUM_AS_DATA_STATE &state) {
      if(!SymbolSelect(symbol,true)) { state=AS_DATA_ERROR; return false; }
      if(!SymbolIsSynchronized(symbol)) { state=AS_DATA_SYNCHRONIZING; return false; }
      long synced=0; ResetLastError();
      if(!SeriesInfoInteger(symbol,tf,SERIES_SYNCHRONIZED,synced) || synced==0) { state=AS_DATA_DOWNLOADING; return false; }
      if(Bars(symbol,tf)<min_bars) { state=AS_DATA_DOWNLOADING; return false; }
      state=AS_DATA_READY; return true;
   }
   bool EnsureAllReady(const string symbol,const int min_bars,ENUM_AS_DATA_STATE &state){ ENUM_TIMEFRAMES tfs[4]={PERIOD_H4,PERIOD_H1,PERIOD_M15,PERIOD_M5}; for(int i=0;i<4;i++)if(!EnsureReady(symbol,tfs[i],min_bars,state))return false; state=AS_DATA_READY;return true; }
   bool Snapshot(const string requested,const string symbol,const int max_tick_age_seconds,AS_SymbolSnapshot &s) {
      ZeroMemory(s);s.requested_symbol=requested;s.symbol=symbol;
      AS_QuoteState q;if(!m_runtime.Quote(symbol,max_tick_age_seconds,q)){s.spread_state=AS_SPREAD_NO_TICK;s.data_state=q.data_state;return false;}
      s.bid=q.bid;s.ask=q.ask;s.point=q.point;s.digits=q.digits;s.spread_points=q.spread_points;s.tick_time=q.tick_time;s.data_state=q.data_state;
      s.spread_state=(q.fresh?AS_SPREAD_WARMING_UP:AS_SPREAD_STALE);
      return true;
   }
   bool ClosedBar(const string symbol,const ENUM_TIMEFRAMES tf,const int shift,AS_ClosedBarSnapshot &bar){return m_runtime.ClosedBar(symbol,tf,shift,bar);}
   bool Rates(const string symbol,const ENUM_TIMEFRAMES tf,const int start_shift,const int count,MqlRates &rates[]) { ArraySetAsSeries(rates,true); int copied=CopyRates(symbol,tf,start_shift,count,rates); return copied==count; }
};