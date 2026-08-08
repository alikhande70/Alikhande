#pragma once
#include "../Domain/Models.mqh"
#include "../Safety/TradeGuards.mqh"

class AS_Preflight {
private:
   AS_TradeGuards m_guards;
   bool ResolveFilling(const string symbol,ENUM_ORDER_TYPE_FILLING &out,string &reason){
      long flags=SymbolInfoInteger(symbol,SYMBOL_FILLING_MODE);
      if((flags&SYMBOL_FILLING_FOK)==SYMBOL_FILLING_FOK){out=ORDER_FILLING_FOK;return true;}
      if((flags&SYMBOL_FILLING_IOC)==SYMBOL_FILLING_IOC){out=ORDER_FILLING_IOC;return true;}
      long execution=SymbolInfoInteger(symbol,SYMBOL_TRADE_EXEMODE);
      if(execution==SYMBOL_TRADE_EXECUTION_MARKET){reason="NO_SUPPORTED_FILLING_FOR_MARKET_EXECUTION";return false;}
      out=ORDER_FILLING_RETURN;return true;
   }
public:
   bool Validate(const AS_TradePlan &p,MqlTradeRequest &request,MqlTradeCheckResult &check,string &reason){
      ZeroMemory(request);ZeroMemory(check);reason="";
      if(AccountInfoInteger(ACCOUNT_TRADE_MODE)!=ACCOUNT_TRADE_MODE_DEMO){reason="REAL_ACCOUNT_BLOCKED";return false;}
      if(!p.valid||TimeCurrent()>p.expires_at){reason="PLAN_EXPIRED";return false;}
      if(m_guards.HasExposure(p.symbol)){reason="EXPOSURE_EXISTS";return false;}
      string codes="";if(!m_guards.TradePermissions(p.symbol,codes)||!m_guards.StopsValid(p,codes)){reason=codes;return false;}
      MqlTick tick;if(!SymbolInfoTick(p.symbol,tick)){reason="NO_TICK";return false;}
      double point=SymbolInfoDouble(p.symbol,SYMBOL_POINT);double current=(p.direction==AS_DIR_LONG?tick.ask:tick.bid);
      if(point<=0||MathAbs(current-p.entry)/point>p.max_drift_points){reason="PRICE_DRIFT_EXCEEDED";return false;}
      request.action=TRADE_ACTION_DEAL;request.symbol=p.symbol;request.magic=AS_MAGIC;request.volume=p.lot_size;
      request.type=(p.direction==AS_DIR_LONG?ORDER_TYPE_BUY:ORDER_TYPE_SELL);request.price=current;request.sl=p.stop_loss;request.tp=p.take_profit;
      request.deviation=(ulong)p.max_drift_points;request.type_time=ORDER_TIME_GTC;
      if(!ResolveFilling(p.symbol,request.type_filling,reason))return false;
      if(!OrderCheck(request,check)){reason=StringFormat("ORDERCHECK_CALL_FAILED_%d",GetLastError());return false;}
      if(check.retcode!=TRADE_RETCODE_DONE&&check.retcode!=TRADE_RETCODE_PLACED){reason=StringFormat("ORDERCHECK_%u_%s",check.retcode,check.comment);return false;}
      return true;
   }
};
