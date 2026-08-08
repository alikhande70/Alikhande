//+------------------------------------------------------------------+
//| SymbolSpec.mqh                                                     |
//| Symbol specification snapshot + warm-up: specs become ready       |
//| without blocking OnInit indefinitely (Broker Gate, acceptance     |
//| tests). A symbol is considered "ready" once digits/point/contract |
//| size are non-zero — brokers can take a few ticks to populate a    |
//| freshly-selected symbol's spec.                                   |
//+------------------------------------------------------------------+
#property strict

struct SymbolSpecSnapshot
  {
   string symbol;
   bool   ready;
   int    digits;
   double point;
   double contractSize;
   double volumeMin, volumeMax, volumeStep;
   int    stopsLevel, freezeLevel;
   double tickValue, tickSize;
  };

SymbolSpecSnapshot FetchSymbolSpec(const string symbol)
  {
   SymbolSpecSnapshot s;
   s.symbol = symbol;
   s.digits = (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS);
   s.point  = SymbolInfoDouble(symbol, SYMBOL_POINT);
   s.contractSize = SymbolInfoDouble(symbol, SYMBOL_TRADE_CONTRACT_SIZE);
   s.volumeMin  = SymbolInfoDouble(symbol, SYMBOL_VOLUME_MIN);
   s.volumeMax  = SymbolInfoDouble(symbol, SYMBOL_VOLUME_MAX);
   s.volumeStep = SymbolInfoDouble(symbol, SYMBOL_VOLUME_STEP);
   s.stopsLevel  = (int)SymbolInfoInteger(symbol, SYMBOL_TRADE_STOPS_LEVEL);
   s.freezeLevel = (int)SymbolInfoInteger(symbol, SYMBOL_TRADE_FREEZE_LEVEL);
   s.tickValue = SymbolInfoDouble(symbol, SYMBOL_TRADE_TICK_VALUE);
   s.tickSize  = SymbolInfoDouble(symbol, SYMBOL_TRADE_TICK_SIZE);

   s.ready = (s.digits > 0) && (s.point > 0.0) && (s.contractSize > 0.0) &&
             (s.volumeMin > 0.0) && (s.tickSize > 0.0);
   return s;
  }

//+------------------------------------------------------------------+
//| Non-blocking warm-up: call once per OnTimer tick during OnInit's  |
//| grace period. Returns true once every symbol in the list is ready |
//| or the deadline passes (in which case unready symbols are logged  |
//| and excluded, not retried forever).                                |
//+------------------------------------------------------------------+
bool WarmUpSymbolSpecs(const string &symbols[], string &unreadySymbols[])
  {
   ArrayResize(unreadySymbols, 0);
   bool allReady = true;

   for(int i = 0; i < ArraySize(symbols); i++)
     {
      SymbolSpecSnapshot spec = FetchSymbolSpec(symbols[i]);
      if(!spec.ready)
        {
         allReady = false;
         int n = ArraySize(unreadySymbols);
         ArrayResize(unreadySymbols, n + 1);
         unreadySymbols[n] = symbols[i];
        }
     }

   return allReady;
  }
