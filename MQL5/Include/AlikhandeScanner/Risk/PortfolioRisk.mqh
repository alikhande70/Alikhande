#pragma once
#include "../Core/Config.mqh"
class AS_PortfolioRisk {
public:
   double ScannerOpenRiskPct(const ulong magic){double equity=AccountInfoDouble(ACCOUNT_EQUITY);if(equity<=0)return 100.0;double risk=0;for(int i=PositionsTotal()-1;i>=0;i--){ulong ticket=PositionGetTicket(i);if(ticket==0)continue;if((ulong)PositionGetInteger(POSITION_MAGIC)!=magic)continue;string sym=PositionGetString(POSITION_SYMBOL);double volume=PositionGetDouble(POSITION_VOLUME);double open=PositionGetDouble(POSITION_PRICE_OPEN);double sl=PositionGetDouble(POSITION_SL);if(sl<=0)continue;long type=PositionGetInteger(POSITION_TYPE);ENUM_ORDER_TYPE ot=(type==POSITION_TYPE_BUY?ORDER_TYPE_BUY:ORDER_TYPE_SELL);double loss=0;if(OrderCalcProfit(ot,sym,volume,open,sl,loss))risk+=MathAbs(loss);}return 100.0*risk/equity;}
   bool AllowNewRisk(const double new_risk_pct,const double max_total_pct,const ulong magic,string &reason){double current=ScannerOpenRiskPct(magic);if(current+new_risk_pct>max_total_pct){reason=StringFormat("TOTAL_OPEN_RISK %.2f+%.2f>%.2f",current,new_risk_pct,max_total_pct);return false;}return true;}
};
