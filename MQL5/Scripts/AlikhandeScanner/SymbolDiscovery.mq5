//+------------------------------------------------------------------+
//| SymbolDiscovery.mq5                                                |
//| Diagnostic: resolves each configured symbol and prints how it was |
//| matched (exact / _o suffix / # prefix / normalized fallback /     |
//| UNRESOLVED). Run after CompileAllModules, before the EA.          |
//+------------------------------------------------------------------+
#property copyright "Alikhande"
#property version   "1.20"
#property script_show_inputs

#include <AlikhandeScanner/Broker/SymbolResolver.mqh>

input string InpSymbolsCsv = "EURUSD,GBPUSD,XAUUSD";

string ResolutionStatusLabel(const ENUM_SYMBOL_RESOLUTION status)
  {
   switch(status)
     {
      case SYMBOL_RESOLVED_EXACT:      return "EXACT";
      case SYMBOL_RESOLVED_SUFFIX:     return "SUFFIX(_o)";
      case SYMBOL_RESOLVED_PREFIX:     return "PREFIX(#)";
      case SYMBOL_RESOLVED_NORMALIZED: return "NORMALIZED";
      case SYMBOL_UNRESOLVED:          return "UNRESOLVED";
     }
   return "?";
  }

void OnStart()
  {
   string symbols[];
   int n = StringSplit(InpSymbolsCsv, ',', symbols);

   PrintFormat("=== Alikhande Symbol Discovery — %d symbol(s) ===", n);
   for(int i = 0; i < n; i++)
     {
      string baseName = symbols[i];
      StringTrimLeft(baseName);
      StringTrimRight(baseName);
      if(baseName == "")
         continue;

      SymbolResolution res = ResolveSymbol(baseName);
      PrintFormat("%-12s -> %-12s [%s]", baseName,
                  res.resolvedName == "" ? "UNRESOLVED" : res.resolvedName,
                  ResolutionStatusLabel(res.status));
     }
  }
