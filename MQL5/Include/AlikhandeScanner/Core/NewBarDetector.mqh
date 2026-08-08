//+------------------------------------------------------------------+
//| NewBarDetector.mqh                                                 |
//| Per-symbol, per-timeframe new-closed-bar detection. Heavy analysis|
//| (TrendEngine/ZoneEngine) must only re-run when this returns true  |
//| for the relevant timeframe — never on every timer tick.           |
//+------------------------------------------------------------------+
#property strict

#define NEW_BAR_MAX_TRACKED 64

string   g_NewBarKeys[NEW_BAR_MAX_TRACKED];
datetime g_NewBarTimes[NEW_BAR_MAX_TRACKED];
int      g_NewBarCount = 0;

string BuildBarKey(const string symbol, const ENUM_TIMEFRAMES tf)
  {
   return symbol + "_" + EnumToString(tf);
  }

bool IsNewClosedBar(const string symbol, const ENUM_TIMEFRAMES tf)
  {
   datetime currentBarTime = iTime(symbol, tf, 0);
   if(currentBarTime == 0)
      return false; // no data yet

   string key = BuildBarKey(symbol, tf);

   for(int i = 0; i < g_NewBarCount; i++)
     {
      if(g_NewBarKeys[i] == key)
        {
         if(g_NewBarTimes[i] == currentBarTime)
            return false;
         g_NewBarTimes[i] = currentBarTime;
         return true;
        }
     }

   // First time we've seen this symbol/timeframe — record it but do not
   // treat the initial observation as "new" (it's not a fresh close, it's
   // just startup).
   if(g_NewBarCount < NEW_BAR_MAX_TRACKED)
     {
      g_NewBarKeys[g_NewBarCount] = key;
      g_NewBarTimes[g_NewBarCount] = currentBarTime;
      g_NewBarCount++;
     }
   return false;
  }
