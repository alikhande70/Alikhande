#pragma once
#include "../Domain/Models.mqh"
class AS_TradeGuards {
public:
   bool HasExposure(const string symbol){for(int i=PositionsTotal()-1;i>=0;i--){ulong t=PositionGetTicket(i);if(t>0&&PositionGetString(POSITION_SYMBOL)==symbol)return true;}for(int i=OrdersTotal()-1;i>=0;i--){ulong t=OrderGetTicket(i);if(t>0&&OrderGetString(ORDER_SYMBOL)==symbol)return true;}return false;}
   bool TradePermissions(const string symbol,string &codes){bool ok=true;if(!TerminalInfoInteger(TERMINAL_TRADE_ALLOWED)){ok=false;codes+="TERMINAL_TRADE_DISABLED;";}if(!MQLInfoInteger(MQL_TRADE_ALLOWED)){ok=false;codes+="MQL_TRADE_DISABLED;";}if(!AccountInfoInteger(ACCOUNT_TRADE_ALLOWED)){ok=false;codes+="ACCOUNT_TRADE_DISABLED;";}long mode=SymbolInfoInteger(symbol,SYMBOL_TRADE_MODE);if(mode==SYMBOL_TRADE_MODE_DISABLED||mode==SYMBOL_TRADE_MODE_CLOSEONLY){ok=false;codes+="SYMBOL_TRADE_DISABLED;";}return ok;}
   bool StopsValid(const AS_TradePlan &p,string &codes){double point=SymbolInfoDouble(p.symbol,SYMBOL_POINT);int stop_level=(int)SymbolInfoInteger(p.symbol,SYMBOL_TRADE_STOPS_LEVEL);if(point<=0)return false;double min_dist=stop_level*point;if(MathAbs(p.entry-p.stop_loss)<min_dist||MathAbs(p.take_profit-p.entry)<min_dist){codes+="BROKER_STOP_LEVEL;";return false;}return true;}
};
