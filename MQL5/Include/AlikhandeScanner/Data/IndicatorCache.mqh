#pragma once
#include "../Core/Log.mqh"

// Indicator handle cache.
//
// v1.1.0 called iMA/iADX/iATR and IndicatorRelease on *every* Analyze() — four
// handles per timeframe per symbol, created and destroyed on each closed bar.
// Two problems with that:
//
//   1. BarsCalculated() is unreliable immediately after handle creation, so the
//      very first Analyze() for a symbol routinely bailed out with "IND DATA"
//      even though the data was fine. It only recovered on the next bar.
//   2. Repeated create/release churns MT5's internal indicator cache.
//
// Handles are cheap to hold and expensive to churn, so they are created once
// per (symbol, timeframe, kind, period) and kept for the life of the EA.

enum ENUM_AS_INDICATOR
  {
   AS_IND_EMA,
   AS_IND_ADX,
   AS_IND_ATR
  };

#define AS_INDICATOR_CACHE_CAPACITY 256

class AS_IndicatorCache
  {
private:
   string m_keys[AS_INDICATOR_CACHE_CAPACITY];
   int    m_handles[AS_INDICATOR_CACHE_CAPACITY];
   int    m_count;
   AS_Log *m_log;

   string Key(const string symbol, const ENUM_TIMEFRAMES tf,
              const ENUM_AS_INDICATOR kind, const int period) const
     {
      return StringFormat("%s|%d|%d|%d", symbol, (int)tf, (int)kind, period);
     }

   int Create(const string symbol, const ENUM_TIMEFRAMES tf,
              const ENUM_AS_INDICATOR kind, const int period)
     {
      switch(kind)
        {
         case AS_IND_EMA: return iMA(symbol, tf, period, 0, MODE_EMA, PRICE_CLOSE);
         case AS_IND_ADX: return iADX(symbol, tf, period);
         case AS_IND_ATR: return iATR(symbol, tf, period);
        }
      return INVALID_HANDLE;
     }

public:
   AS_IndicatorCache(void) { m_count = 0; m_log = NULL; ArrayInitialize(m_handles, INVALID_HANDLE); }

   void Attach(AS_Log &log) { m_log = GetPointer(log); }

   void Release(void)
     {
      for(int i = 0; i < m_count; i++)
         if(m_handles[i] != INVALID_HANDLE)
            IndicatorRelease(m_handles[i]);
      m_count = 0;
     }

   int Count(void) const { return m_count; }

   // Returns a cached handle, creating it on first request. INVALID_HANDLE
   // means the terminal refused to create it — the caller must not proceed.
   int Handle(const string symbol, const ENUM_TIMEFRAMES tf,
              const ENUM_AS_INDICATOR kind, const int period)
     {
      const string key = Key(symbol, tf, kind, period);

      for(int i = 0; i < m_count; i++)
         if(m_keys[i] == key)
            return m_handles[i];

      if(m_count >= AS_INDICATOR_CACHE_CAPACITY)
        {
         if(m_log != NULL)
            m_log.Error("INDICATOR_CACHE_FULL", symbol,
                        StringFormat("capacity %d exhausted; reduce the symbol list",
                                     AS_INDICATOR_CACHE_CAPACITY));
         return INVALID_HANDLE;
        }

      const int handle = Create(symbol, tf, kind, period);
      if(handle == INVALID_HANDLE)
        {
         if(m_log != NULL)
            m_log.Error("INDICATOR_CREATE_FAILED", symbol,
                        StringFormat("kind=%d tf=%d period=%d err=%d",
                                     (int)kind, (int)tf, period, GetLastError()));
         return INVALID_HANDLE;
        }

      m_keys[m_count] = key;
      m_handles[m_count] = handle;
      m_count++;
      return handle;
     }

   // Copy `count` values ending at the most recent CLOSED bar (shift 1).
   //
   // The returned array is in chronological order: index 0 is oldest, index
   // count-1 is the most recent closed bar. That is CopyBuffer's native layout
   // for a non-series destination, and stating it here once stops every call
   // site from having to re-derive it.
   bool CopyClosed(const int handle, const int buffer_index,
                   const int count, double &out[])
     {
      if(handle == INVALID_HANDLE || count <= 0)
         return false;
      if(BarsCalculated(handle) < count + 1)
         return false;
      if(ArrayResize(out, count) != count)
         return false;
      ArraySetAsSeries(out, false);
      return CopyBuffer(handle, buffer_index, 1, count, out) == count;
     }
  };
