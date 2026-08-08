#pragma once
#include "../Domain/Enums.mqh"
#include "../Core/Hash.mqh"

// Live quote truth. This object is intentionally disposable and must never be
// used as the stable identity of a structural setup.
struct AS_QuoteState
  {
   string symbol;
   double bid;
   double ask;
   double point;
   int digits;
   double spread_points;
   datetime tick_time;
   ENUM_AS_DATA_STATE data_state;
   bool fresh;
  };

// Closed-bar truth. The identity is derived only from symbol/timeframe/bar
// close information; live bid/ask cannot change it.
struct AS_ClosedBarSnapshot
  {
   string symbol;
   ENUM_TIMEFRAMES timeframe;
   datetime bar_time;
   double open;
   double high;
   double low;
   double close;
   long tick_volume;
   long real_volume;
   int spread;
   string structural_id;
   bool valid;
  };

class AS_RuntimeSnapshots
  {
public:
   bool Quote(const string symbol,const int max_tick_age_seconds,AS_QuoteState &out) const
     {
      ZeroMemory(out);
      out.symbol = symbol;
      MqlTick tick;
      if(!SymbolInfoTick(symbol,tick))
        {
         out.data_state = AS_DATA_ERROR;
         return false;
        }
      out.bid = tick.bid;
      out.ask = tick.ask;
      out.point = SymbolInfoDouble(symbol,SYMBOL_POINT);
      out.digits = (int)SymbolInfoInteger(symbol,SYMBOL_DIGITS);
      out.tick_time = (datetime)tick.time;
      if(out.bid <= 0.0 || out.ask <= 0.0 || out.point <= 0.0)
        {
         out.data_state = AS_DATA_ERROR;
         return false;
        }
      out.spread_points = (out.ask-out.bid)/out.point;
      out.fresh = (max_tick_age_seconds <= 0 || TimeCurrent()-out.tick_time <= max_tick_age_seconds);
      out.data_state = (out.fresh ? AS_DATA_READY : AS_DATA_STALE);
      return true;
     }

   bool ClosedBar(const string symbol,const ENUM_TIMEFRAMES tf,const int shift,AS_ClosedBarSnapshot &out) const
     {
      ZeroMemory(out);
      if(shift < 1)
         return false; // structural snapshots may never read the forming bar

      MqlRates rates[1];
      ArraySetAsSeries(rates,true);
      if(CopyRates(symbol,tf,shift,1,rates) != 1)
         return false;

      out.symbol = symbol;
      out.timeframe = tf;
      out.bar_time = rates[0].time;
      out.open = rates[0].open;
      out.high = rates[0].high;
      out.low = rates[0].low;
      out.close = rates[0].close;
      out.tick_volume = (long)rates[0].tick_volume;
      out.real_volume = (long)rates[0].real_volume;
      out.spread = rates[0].spread;
      out.structural_id = AS_Fnv1a(StringFormat("%s|%d|%I64d|%.10f|%.10f|%.10f|%.10f",
                                                symbol,(int)tf,(long)out.bar_time,
                                                out.open,out.high,out.low,out.close));
      out.valid = true;
      return true;
     }
  };
