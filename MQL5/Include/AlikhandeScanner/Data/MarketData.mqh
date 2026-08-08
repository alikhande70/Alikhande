#pragma once
#include "../Domain/Models.mqh"
#include "../Core/Log.mqh"

// Quote and history availability.
//
// The contract that matters here: a stale quote is a *failure*, not a value.
// v1.1.0 returned `true` from Snapshot() on a stale tick and relied on one
// downstream check in the signal engine to catch it. That works until someone
// adds a second consumer. Snapshot() now returns false whenever the data is not
// safe to act on, and the state field says why.

class AS_MarketData
  {
private:
   AS_Log *m_log;

public:
   AS_MarketData(void) { m_log = NULL; }

   void Attach(AS_Log &log) { m_log = GetPointer(log); }

   bool EnsureReady(const string symbol, const ENUM_TIMEFRAMES tf,
                    const int min_bars, ENUM_AS_DATA_STATE &state)
     {
      if(!SymbolSelect(symbol, true))
        {
         state = AS_DATA_ERROR;
         return false;
        }
      if(!SymbolIsSynchronized(symbol))
        {
         state = AS_DATA_SYNCHRONIZING;
         return false;
        }

      long synchronized = 0;
      ResetLastError();
      if(!SeriesInfoInteger(symbol, tf, SERIES_SYNCHRONIZED, synchronized) || synchronized == 0)
        {
         state = AS_DATA_DOWNLOADING;
         return false;
        }
      if(Bars(symbol, tf) < min_bars)
        {
         state = AS_DATA_DOWNLOADING;
         return false;
        }

      state = AS_DATA_READY;
      return true;
     }

   bool EnsureAllReady(const string symbol, const int min_bars, ENUM_AS_DATA_STATE &state)
     {
      ENUM_TIMEFRAMES timeframes[4] = {PERIOD_H4, PERIOD_H1, PERIOD_M15, PERIOD_M5};
      for(int i = 0; i < 4; i++)
         if(!EnsureReady(symbol, timeframes[i], min_bars, state))
            return false;
      state = AS_DATA_READY;
      return true;
     }

   // Returns false whenever the snapshot must not be acted upon. `s.data_state`
   // and `s.spread_state` always carry the reason, so the UI can render an
   // accurate status even on failure.
   bool Snapshot(const string requested, const string symbol,
                 const int max_tick_age_seconds, AS_SymbolSnapshot &s)
     {
      ZeroMemory(s);
      s.requested_symbol = requested;
      s.symbol = symbol;

      MqlTick tick;
      if(!SymbolInfoTick(symbol, tick))
        {
         s.spread_state = AS_SPREAD_NO_TICK;
         s.data_state = AS_DATA_ERROR;
         return false;
        }

      s.bid = tick.bid;
      s.ask = tick.ask;
      s.tick_time = (datetime)tick.time;
      s.point = SymbolInfoDouble(symbol, SYMBOL_POINT);
      s.digits = (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS);

      if(s.point <= 0.0 || s.ask <= 0.0 || s.bid <= 0.0 || s.ask < s.bid)
        {
         s.spread_state = AS_SPREAD_NO_TICK;
         s.data_state = AS_DATA_ERROR;
         return false;
        }

      s.spread_points = (s.ask - s.bid) / s.point;

      if(max_tick_age_seconds > 0 && (TimeCurrent() - s.tick_time) > max_tick_age_seconds)
        {
         s.spread_state = AS_SPREAD_STALE;
         s.data_state = AS_DATA_STALE;
         if(m_log != NULL)
            m_log.Warn("QUOTE_STALE", symbol,
                       StringFormat("last tick %d s old (limit %d s)",
                                    (int)(TimeCurrent() - s.tick_time), max_tick_age_seconds));
         return false;
        }

      s.data_state = AS_DATA_READY;
      return true;
     }
  };
