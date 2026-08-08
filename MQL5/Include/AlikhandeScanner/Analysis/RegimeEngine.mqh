#pragma once
#include "../Domain/Models.mqh"

class AS_RegimeEngine {
public:
   bool Evaluate(const AS_TrendResult &h4,const AS_TrendResult &h1,const AS_TrendResult &m15,const AS_SymbolSnapshot &snap,AS_RegimeResult &out){
      out.regime=AS_REGIME_UNKNOWN;out.confidence=0;out.reasons="";out.tradable=false;
      if(!h4.valid||!h1.valid||!m15.valid)return false;
      if(snap.spread_state==AS_SPREAD_EXTREME||snap.spread_state==AS_SPREAD_STALE||snap.spread_state==AS_SPREAD_NO_TICK){out.regime=AS_REGIME_ILLIQUID;out.confidence=100;out.reasons="QUOTE_OR_SPREAD_RISK;";return true;}
      double align=(h4.direction_score+h1.direction_score+m15.direction_score)/3.0;
      if(h1.adx>=25&&align>=20){out.regime=AS_REGIME_TREND_UP;out.confidence=MathMin(100.0,55+h1.adx);out.tradable=true;out.reasons="ADX_TREND;MTF_UP;";return true;}
      if(h1.adx>=25&&align<=-20){out.regime=AS_REGIME_TREND_DOWN;out.confidence=MathMin(100.0,55+h1.adx);out.tradable=true;out.reasons="ADX_TREND;MTF_DOWN;";return true;}
      if(h1.atr_ratio>=1.6){out.regime=AS_REGIME_HIGH_VOL;out.confidence=MathMin(100.0,50+h1.atr_ratio*20);out.tradable=false;out.reasons="ATR_EXPANSION;";return true;}
      if(h1.atr_ratio>0&&h1.atr_ratio<=0.65){out.regime=AS_REGIME_LOW_VOL;out.confidence=75;out.tradable=false;out.reasons="ATR_COMPRESSION;";return true;}
      if(h1.adx<20&&MathAbs(align)<20){out.regime=AS_REGIME_RANGE;out.confidence=70;out.tradable=false;out.reasons="LOW_ADX;MIXED_MTF;";return true;}
      out.regime=AS_REGIME_TRANSITION;out.confidence=55;out.tradable=false;out.reasons="MIXED_CONTEXT;";return true;
   }
};
