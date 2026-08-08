#pragma once
#include "../Domain/Models.mqh"

class AS_SymbolSpecReader {
public:
   bool Read(const string symbol,AS_SymbolSpec &s){
      ZeroMemory(s); s.symbol=symbol;
      s.digits=(int)SymbolInfoInteger(symbol,SYMBOL_DIGITS);
      s.point=SymbolInfoDouble(symbol,SYMBOL_POINT);
      s.tick_size=SymbolInfoDouble(symbol,SYMBOL_TRADE_TICK_SIZE);
      s.tick_value=SymbolInfoDouble(symbol,SYMBOL_TRADE_TICK_VALUE);
      s.volume_min=SymbolInfoDouble(symbol,SYMBOL_VOLUME_MIN);
      s.volume_max=SymbolInfoDouble(symbol,SYMBOL_VOLUME_MAX);
      s.volume_step=SymbolInfoDouble(symbol,SYMBOL_VOLUME_STEP);
      s.trade_mode=SymbolInfoInteger(symbol,SYMBOL_TRADE_MODE);
      s.stops_level=(int)SymbolInfoInteger(symbol,SYMBOL_TRADE_STOPS_LEVEL);
      s.freeze_level=(int)SymbolInfoInteger(symbol,SYMBOL_TRADE_FREEZE_LEVEL);
      s.ready=(s.point>0 && s.tick_size>0 && s.volume_min>0 && s.volume_max>=s.volume_min && s.volume_step>0);
      return s.ready;
   }
};
