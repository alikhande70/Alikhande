//+------------------------------------------------------------------+
//| SymbolResolver.mqh                                                 |
//| Broker-aware symbol resolution: exact name, "_o" suffix, "#"      |
//| prefix, and a full-tree normalized fallback (strip all non-alpha  |
//| characters and match against Market Watch + full symbol tree).    |
//| Unresolved symbols must show UNRESOLVED and never generate        |
//| signals — see docs/v1.1.0_ACCEPTANCE_TESTS.md "Broker Gate".      |
//+------------------------------------------------------------------+
#property strict
#include "../Domain/Enums.mqh"

string NormalizeSymbolName(const string s)
  {
   string result = "";
   int len = StringLen(s);
   for(int i = 0; i < len; i++)
     {
      ushort c = StringGetCharacter(s, i);
      bool isAlpha = (c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z');
      if(isAlpha)
         result += StringSubstr(s, i, 1);
     }
   return result;
  }

struct SymbolResolution
  {
   ENUM_SYMBOL_RESOLUTION status;
   string                 resolvedName; // "" if UNRESOLVED
  };

bool TrySelectSymbol(const string candidate)
  {
   if(SymbolSelect(candidate, true))
      return true;
   // SymbolSelect can succeed for names present in the full tree but not yet
   // shown in Market Watch; SymbolInfoInteger below confirms it truly exists.
   return (long)SymbolInfoInteger(candidate, SYMBOL_SELECT) != 0 ||
          SymbolInfoDouble(candidate, SYMBOL_POINT) > 0.0;
  }

//+------------------------------------------------------------------+
//| Resolution order: exact -> "_o" suffix -> "#" prefix -> full-tree |
//| normalized scan. First match wins.                                |
//+------------------------------------------------------------------+
SymbolResolution ResolveSymbol(const string baseName)
  {
   SymbolResolution res;
   res.status = SYMBOL_UNRESOLVED;
   res.resolvedName = "";

   if(TrySelectSymbol(baseName))
     {
      res.status = SYMBOL_RESOLVED_EXACT;
      res.resolvedName = baseName;
      return res;
     }

   string withSuffix = baseName + "_o";
   if(TrySelectSymbol(withSuffix))
     {
      res.status = SYMBOL_RESOLVED_SUFFIX;
      res.resolvedName = withSuffix;
      return res;
     }

   string withPrefix = "#" + baseName;
   if(TrySelectSymbol(withPrefix))
     {
      res.status = SYMBOL_RESOLVED_PREFIX;
      res.resolvedName = withPrefix;
      return res;
     }

   // Full-tree normalized fallback: strip non-alpha characters from every
   // symbol in the broker's tree and compare against the normalized target.
   string target = NormalizeSymbolName(baseName);
   int total = SymbolsTotal(false); // false = full tree, not just Market Watch
   for(int i = 0; i < total; i++)
     {
      string name = SymbolName(i, false);
      if(NormalizeSymbolName(name) == target)
        {
         if(TrySelectSymbol(name))
           {
            res.status = SYMBOL_RESOLVED_NORMALIZED;
            res.resolvedName = name;
            return res;
           }
        }
     }

   return res; // UNRESOLVED
  }
