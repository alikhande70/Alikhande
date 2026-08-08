//+------------------------------------------------------------------+
//| SymbolSpec.mq5                                                     |
//| Diagnostic: resolves each configured symbol then prints its full  |
//| spec snapshot and whether it warmed up (became ready) within the  |
//| grace period. Run after SymbolDiscovery, before the EA.           |
//+------------------------------------------------------------------+
#property copyright "Alikhande"
#property version   "1.20"
#property script_show_inputs

#include <AlikhandeScanner/Broker/SymbolResolver.mqh>
#include <AlikhandeScanner/Broker/SymbolSpec.mqh>

input string InpSymbolsCsv = "EURUSD,GBPUSD,XAUUSD";
input int    InpWarmupAttempts = 20;
input int    InpWarmupDelayMs  = 200;

void OnStart()
  {
   string rawSymbols[];
   int n = StringSplit(InpSymbolsCsv, ',', rawSymbols);

   string resolved[];
   ArrayResize(resolved, 0);

   for(int i = 0; i < n; i++)
     {
      string baseName = rawSymbols[i];
      StringTrimLeft(baseName);
      StringTrimRight(baseName);
      if(baseName == "")
         continue;

      SymbolResolution res = ResolveSymbol(baseName);
      if(res.status == SYMBOL_UNRESOLVED)
        {
         PrintFormat("%-12s UNRESOLVED — skipped", baseName);
         continue;
        }

      int k = ArraySize(resolved);
      ArrayResize(resolved, k + 1);
      resolved[k] = res.resolvedName;
     }

   string unready[];
   bool allReady = false;
   for(int attempt = 0; attempt < InpWarmupAttempts && !allReady; attempt++)
     {
      allReady = WarmUpSymbolSpecs(resolved, unready);
      if(!allReady)
         Sleep(InpWarmupDelayMs);
     }

   PrintFormat("=== Alikhande Symbol Spec — warm-up %s after %d attempt(s) ===",
               allReady ? "COMPLETE" : "TIMED OUT", InpWarmupAttempts);

   for(int i = 0; i < ArraySize(resolved); i++)
     {
      SymbolSpecSnapshot spec = FetchSymbolSpec(resolved[i]);
      PrintFormat("%-12s ready=%s digits=%d point=%.5f contract=%.2f volMin=%.2f volStep=%.2f "
                  "stopsLevel=%d freezeLevel=%d tickValue=%.4f",
                  resolved[i], spec.ready ? "yes" : "NO", spec.digits, spec.point,
                  spec.contractSize, spec.volumeMin, spec.volumeStep, spec.stopsLevel,
                  spec.freezeLevel, spec.tickValue);
     }
  }
