//+------------------------------------------------------------------+
//| SignalRegistry.mqh                                                 |
//| In-memory mirror of "signals seen this session" — prevents        |
//| duplicate SignalID logging across repeated timer events, and owns |
//| the managed-chart reuse policy (repeated "Open" clicks reuse an   |
//| Alikhande-managed chart rather than opening a new one each time). |
//+------------------------------------------------------------------+
#property strict

#define SIGNAL_REGISTRY_MAX 256

string g_SeenSignalIds[SIGNAL_REGISTRY_MAX];
int    g_SeenSignalCount = 0;

bool SignalRegistryContains(const string signalId)
  {
   for(int i = 0; i < g_SeenSignalCount; i++)
      if(g_SeenSignalIds[i] == signalId)
         return true;
   return false;
  }

// Returns false (and does not register) if already seen — callers must
// treat that as "do not persist/log this signal again".
bool SignalRegistryTryAdd(const string signalId)
  {
   if(SignalRegistryContains(signalId))
      return false;

   if(g_SeenSignalCount >= SIGNAL_REGISTRY_MAX)
     {
      // Oldest-first eviction — this is a dedup cache, not the source of
      // truth (SQLite `signals` table is), so bounded memory is fine.
      for(int i = 1; i < SIGNAL_REGISTRY_MAX; i++)
         g_SeenSignalIds[i - 1] = g_SeenSignalIds[i];
      g_SeenSignalCount = SIGNAL_REGISTRY_MAX - 1;
     }

   g_SeenSignalIds[g_SeenSignalCount] = signalId;
   g_SeenSignalCount++;
   return true;
  }

//+------------------------------------------------------------------+
//| Managed-chart reuse: symbol+timeframe maps to a chart ID this EA  |
//| opened. A repeated "Open" click brings that chart to front instead|
//| of spawning a new one.                                             |
//+------------------------------------------------------------------+
#define MANAGED_CHART_MAX 64

string g_ManagedChartKeys[MANAGED_CHART_MAX];
long   g_ManagedChartIds[MANAGED_CHART_MAX];
int    g_ManagedChartCount = 0;

string BuildManagedChartKey(const string symbol, const ENUM_TIMEFRAMES tf)
  {
   return symbol + "_" + EnumToString(tf);
  }

long FindManagedChart(const string symbol, const ENUM_TIMEFRAMES tf)
  {
   string key = BuildManagedChartKey(symbol, tf);
   for(int i = 0; i < g_ManagedChartCount; i++)
      if(g_ManagedChartKeys[i] == key)
        {
         // Confirm the chart still exists — the user may have closed it.
         if(ChartSymbol(g_ManagedChartIds[i]) != "")
            return g_ManagedChartIds[i];
         // Stale entry — drop it by shifting the rest down.
         for(int j = i; j < g_ManagedChartCount - 1; j++)
           {
            g_ManagedChartKeys[j] = g_ManagedChartKeys[j + 1];
            g_ManagedChartIds[j] = g_ManagedChartIds[j + 1];
           }
         g_ManagedChartCount--;
         return 0;
        }
   return 0;
  }

long OpenOrReuseManagedChart(const string symbol, const ENUM_TIMEFRAMES tf)
  {
   long existing = FindManagedChart(symbol, tf);
   if(existing != 0)
     {
      ChartSetInteger(existing, CHART_BRING_TO_TOP, true);
      return existing;
     }

   long newChart = ChartOpen(symbol, tf);
   if(newChart != 0 && g_ManagedChartCount < MANAGED_CHART_MAX)
     {
      g_ManagedChartKeys[g_ManagedChartCount] = BuildManagedChartKey(symbol, tf);
      g_ManagedChartIds[g_ManagedChartCount] = newChart;
      g_ManagedChartCount++;
     }
   return newChart;
  }
