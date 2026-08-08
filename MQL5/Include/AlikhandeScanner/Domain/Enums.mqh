//+------------------------------------------------------------------+
//| Enums.mqh                                                          |
//| Core domain enums shared across the scoring pipeline.             |
//+------------------------------------------------------------------+
#property strict

enum ENUM_TREND_DIRECTION
  {
   TREND_BULLISH,
   TREND_BEARISH,
   TREND_NEUTRAL
  };

string TrendDirectionToString(const ENUM_TREND_DIRECTION d)
  {
   switch(d)
     {
      case TREND_BULLISH: return "Bullish";
      case TREND_BEARISH: return "Bearish";
      case TREND_NEUTRAL:  return "Neutral";
     }
   return "?";
  }

enum ENUM_SETUP_TYPE
  {
   SETUP_NONE,
   SETUP_PULLBACK,
   SETUP_REJECTION,
   SETUP_BREAKOUT_RETEST // reserved, not active — see docs/v1.1.0_README.md limitations
  };

string SetupTypeToString(const ENUM_SETUP_TYPE s)
  {
   switch(s)
     {
      case SETUP_NONE:            return "-";
      case SETUP_PULLBACK:        return "Pullback";
      case SETUP_REJECTION:       return "Rejection";
      case SETUP_BREAKOUT_RETEST: return "Breakout-Retest";
     }
   return "?";
  }

enum ENUM_ZONE_TYPE
  {
   ZONE_SUPPORT,
   ZONE_RESISTANCE
  };

// Symbol resolution outcome — SymbolResolver.mqh tries these in order:
// exact name, "_o" suffix, "#" prefix, normalized fallback.
enum ENUM_SYMBOL_RESOLUTION
  {
   SYMBOL_RESOLVED_EXACT,
   SYMBOL_RESOLVED_SUFFIX,
   SYMBOL_RESOLVED_PREFIX,
   SYMBOL_RESOLVED_NORMALIZED,
   SYMBOL_UNRESOLVED
  };
