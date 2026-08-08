#pragma once
#include <Trade/Trade.mqh>
#include "../Domain/Models.mqh"
#include "../Safety/TradeGuards.mqh"

class AS_DemoExecution {
private:CTrade m_trade; AS_TradeGuards m_guards;
public:
   AS_DemoExecution(void){m_trade.SetAsyncMode(false);}
   bool IsDemo(void){return AccountInfoInteger(ACCOUNT_TRADE_MODE)==ACCOUNT_TRADE_MODE_DEMO;}
   bool Execute(const AS_TradePlan &p,const bool alert_only,const ulong magic,const string comment,string &result){
      if(alert_only){result="ALERT_ONLY_MODE";return false;}if(!IsDemo()){result="REAL_ACCOUNT_BLOCKED";return false;}if(!p.valid||TimeCurrent()>p.expires_at){result="PREVIEW_EXPIRED_OR_INVALID";return false;}if(m_guards.HasExposure(p.symbol)){result="EXPOSURE_EXISTS";return false;}
      string codes="";if(!m_guards.TradePermissions(p.symbol,codes)||!m_guards.StopsValid(p,codes)){result=codes;return false;}
      MqlTick tick;if(!SymbolInfoTick(p.symbol,tick)){result="NO_TICK";return false;}double point=SymbolInfoDouble(p.symbol,SYMBOL_POINT);double current=(p.direction==AS_DIR_LONG?tick.ask:tick.bid);if(point<=0||MathAbs(current-p.entry)/point>p.max_drift_points){result="PRICE_DRIFT_EXCEEDED";return false;}
      m_trade.SetExpertMagicNumber(magic);m_trade.SetTypeFillingBySymbol(p.symbol);bool ok=(p.direction==AS_DIR_LONG?m_trade.Buy(p.lot_size,p.symbol,0,p.stop_loss,p.take_profit,comment):m_trade.Sell(p.lot_size,p.symbol,0,p.stop_loss,p.take_profit,comment));
      result=StringFormat("retcode=%u %s",m_trade.ResultRetcode(),m_trade.ResultRetcodeDescription());return ok && (m_trade.ResultRetcode()==TRADE_RETCODE_DONE||m_trade.ResultRetcode()==TRADE_RETCODE_PLACED||m_trade.ResultRetcode()==TRADE_RETCODE_DONE_PARTIAL);
   }
};
