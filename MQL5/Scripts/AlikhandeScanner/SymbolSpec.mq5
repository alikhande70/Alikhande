#property strict
#property version "1.10"
#property script_show_inputs
input string InpSymbols="XAUUSD_o,EURUSD_o,GBPUSD_o";
void OnStart(){string a[];int n=StringSplit(InpSymbols,',',a);for(int i=0;i<n;i++){string s=a[i];StringTrimLeft(s);StringTrimRight(s);if(!SymbolSelect(s,true)){PrintFormat("%s: unavailable",s);continue;}PrintFormat("%s digits=%d point=%g tick_size=%g tick_value=%g vol_min=%g vol_max=%g vol_step=%g stops=%d freeze=%d trade_mode=%d",s,(int)SymbolInfoInteger(s,SYMBOL_DIGITS),SymbolInfoDouble(s,SYMBOL_POINT),SymbolInfoDouble(s,SYMBOL_TRADE_TICK_SIZE),SymbolInfoDouble(s,SYMBOL_TRADE_TICK_VALUE),SymbolInfoDouble(s,SYMBOL_VOLUME_MIN),SymbolInfoDouble(s,SYMBOL_VOLUME_MAX),SymbolInfoDouble(s,SYMBOL_VOLUME_STEP),(int)SymbolInfoInteger(s,SYMBOL_TRADE_STOPS_LEVEL),(int)SymbolInfoInteger(s,SYMBOL_TRADE_FREEZE_LEVEL),(int)SymbolInfoInteger(s,SYMBOL_TRADE_MODE));}}
