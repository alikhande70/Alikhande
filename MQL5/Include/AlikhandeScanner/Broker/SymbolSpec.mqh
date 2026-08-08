#pragma once
#include "../Domain/Models.mqh"
#include "SpecDrift.mqh"

class AS_SymbolSpecReader {
private: AS_SpecDrift m_drift;
public:
   bool Read(const string symbol,AS_SymbolSpec &s){
      ZeroMemory(s);s.symbol=symbol;
      s.digits=(int)SymbolInfoInteger(symbol,SYMBOL_DIGITS);
      s.point=SymbolInfoDouble(symbol,SYMBOL_POINT);
      s.tick_size=SymbolInfoDouble(symbol,SYMBOL_TRADE_TICK_SIZE);
      s.tick_value=SymbolInfoDouble(symbol,SYMBOL_TRADE_TICK_VALUE);
      s.contract_size=SymbolInfoDouble(symbol,SYMBOL_TRADE_CONTRACT_SIZE);
      s.volume_min=SymbolInfoDouble(symbol,SYMBOL_VOLUME_MIN);
      s.volume_max=SymbolInfoDouble(symbol,SYMBOL_VOLUME_MAX);
      s.volume_step=SymbolInfoDouble(symbol,SYMBOL_VOLUME_STEP);
      s.trade_mode=SymbolInfoInteger(symbol,SYMBOL_TRADE_MODE);
      s.stops_level=(int)SymbolInfoInteger(symbol,SYMBOL_TRADE_STOPS_LEVEL);
      s.freeze_level=(int)SymbolInfoInteger(symbol,SYMBOL_TRADE_FREEZE_LEVEL);
      s.filling_mode=SymbolInfoInteger(symbol,SYMBOL_FILLING_MODE);
      s.ready=(s.point>0&&s.tick_size>0&&s.volume_min>0&&s.volume_max>=s.volume_min&&s.volume_step>0&&s.contract_size>0);
      if(s.ready)s.spec_hash=m_drift.Hash(s);
      return s.ready;
   }
};
