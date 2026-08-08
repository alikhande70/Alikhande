#pragma once
#include "../Domain/Models.mqh"
#include "../Core/Config.mqh"

class AS_RiskPlanner {
private:
   int VolumeDigits(const double step){int d=0;double x=step;while(d<8&&MathAbs(x-MathRound(x))>1e-8){x*=10.0;d++;}return d;}
   bool NormalizeVolume(const string symbol,const double raw,double &normalized,string &code){
      double mn=SymbolInfoDouble(symbol,SYMBOL_VOLUME_MIN),mx=SymbolInfoDouble(symbol,SYMBOL_VOLUME_MAX),st=SymbolInfoDouble(symbol,SYMBOL_VOLUME_STEP);
      if(st<=0||mn<=0||mx<mn){code="INVALID_VOLUME_SPEC";return false;}
      if(raw<mn){code="RISK_BELOW_BROKER_MIN_VOLUME";return false;}
      normalized=MathFloor(raw/st+1e-9)*st;normalized=NormalizeDouble(normalized,VolumeDigits(st));
      if(normalized<mn||normalized>mx){code="VOLUME_OUT_OF_RANGE";return false;}return true;
   }
public:
   bool Build(const AS_SignalCandidate &s,const double risk_percent,const int ttl_seconds,const double max_drift,AS_TradePlan &p){
      ZeroMemory(p);if(s.direction==AS_DIR_NONE||s.hard_blocked)return false;if(risk_percent<=0||risk_percent>AS_MAXIMUM_RISK_PERCENT)return false;
      double equity=AccountInfoDouble(ACCOUNT_EQUITY),risk=equity*risk_percent/100.0,loss1=0;ENUM_ORDER_TYPE type=(s.direction==AS_DIR_LONG?ORDER_TYPE_BUY:ORDER_TYPE_SELL);
      if(!OrderCalcProfit(type,s.symbol,1.0,s.preferred_entry,s.stop_loss,loss1))return false;loss1=MathAbs(loss1);if(loss1<=0)return false;
      double lot=0;string code="";if(!NormalizeVolume(s.symbol,risk/loss1,lot,code)){p.validation_codes=code;return false;}
      double actual_loss=0;if(!OrderCalcProfit(type,s.symbol,lot,s.preferred_entry,s.stop_loss,actual_loss))return false;actual_loss=MathAbs(actual_loss);
      if(actual_loss>risk*1.01){p.validation_codes="NORMALIZED_VOLUME_EXCEEDS_RISK";return false;}
      double margin=0;if(!OrderCalcMargin(type,s.symbol,lot,s.preferred_entry,margin))return false;if(margin>AccountInfoDouble(ACCOUNT_MARGIN_FREE)){p.validation_codes="INSUFFICIENT_FREE_MARGIN";return false;}
      p.plan_id=s.signal_id+"_PLAN";p.symbol=s.symbol;p.direction=s.direction;p.entry=s.preferred_entry;p.stop_loss=s.stop_loss;p.take_profit=s.take_profit;p.risk_percent=risk_percent;p.risk_amount=risk;p.actual_risk_amount=actual_loss;p.lot_size=lot;p.margin_required=margin;p.created_at=TimeCurrent();p.expires_at=p.created_at+ttl_seconds;p.max_drift_points=max_drift;p.minimum_rr=AS_MINIMUM_RISK_REWARD;p.preview_bid=SymbolInfoDouble(s.symbol,SYMBOL_BID);p.preview_ask=SymbolInfoDouble(s.symbol,SYMBOL_ASK);p.valid=true;p.validation_codes="";return true;
   }
};
