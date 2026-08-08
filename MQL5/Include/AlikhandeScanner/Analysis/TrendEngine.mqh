#pragma once
#include "../Domain/Models.mqh"
#include "../Core/Config.mqh"

class AS_TrendEngine {
private:
   ENUM_AS_TREND_CLASS Classify(const double d){ if(d>=75)return AS_STRONG_BULLISH; if(d>=45)return AS_BULLISH; if(d>=20)return AS_WEAK_BULLISH; if(d<=-75)return AS_STRONG_BEARISH; if(d<=-45)return AS_BEARISH; if(d<=-20)return AS_WEAK_BEARISH; return AS_NEUTRAL; }
   double Clamp(const double v,const double lo,const double hi){return MathMax(lo,MathMin(hi,v));}
   double Median(double &values[],const int count){double tmp[];ArrayResize(tmp,count);for(int i=0;i<count;i++)tmp[i]=values[i];ArraySort(tmp);if((count%2)==1)return tmp[count/2];return (tmp[count/2-1]+tmp[count/2])/2.0;}
public:
   bool Analyze(const string symbol,const ENUM_TIMEFRAMES tf,AS_TrendResult &out) {
      ZeroMemory(out); const int need=260; MqlRates r[]; ArraySetAsSeries(r,true); if(CopyRates(symbol,tf,0,need,r)!=need)return false;
      int h50=iMA(symbol,tf,50,0,MODE_EMA,PRICE_CLOSE), h200=iMA(symbol,tf,200,0,MODE_EMA,PRICE_CLOSE);
      int hadx=iADX(symbol,tf,14), hatr=iATR(symbol,tf,14); if(h50==INVALID_HANDLE||h200==INVALID_HANDLE||hadx==INVALID_HANDLE||hatr==INVALID_HANDLE){if(h50!=INVALID_HANDLE)IndicatorRelease(h50);if(h200!=INVALID_HANDLE)IndicatorRelease(h200);if(hadx!=INVALID_HANDLE)IndicatorRelease(hadx);if(hatr!=INVALID_HANDLE)IndicatorRelease(hatr);return false;}
      if(BarsCalculated(h50)<need||BarsCalculated(h200)<need||BarsCalculated(hadx)<need||BarsCalculated(hatr)<need){IndicatorRelease(h50);IndicatorRelease(h200);IndicatorRelease(hadx);IndicatorRelease(hatr);return false;}
      double e50[3],e200[3],adx[1],atr_hist[];ArrayResize(atr_hist,AS_ATR_QUALITY_LOOKBACK);
      bool ok=CopyBuffer(h50,0,1,3,e50)==3 && CopyBuffer(h200,0,1,3,e200)==3 && CopyBuffer(hadx,0,1,1,adx)==1 && CopyBuffer(hatr,0,1,AS_ATR_QUALITY_LOOKBACK,atr_hist)==AS_ATR_QUALITY_LOOKBACK;
      IndicatorRelease(h50);IndicatorRelease(h200);IndicatorRelease(hadx);IndicatorRelease(hatr); if(!ok)return false;
      // CopyBuffer stores the oldest copied element at index 0. For shifts 1..3, index 2 is the most recent closed bar.
      double ema50_recent=e50[2],ema50_old=e50[0],ema200_recent=e200[2];
      double atr_current=atr_hist[AS_ATR_QUALITY_LOOKBACK-1],atr_median=Median(atr_hist,AS_ATR_QUALITY_LOOKBACK);
      double point=SymbolInfoDouble(symbol,SYMBOL_POINT); if(point<=0||atr_current<=0)return false;
      double structure=0; if(r[1].high>r[3].high && r[1].low>r[3].low)structure=40; else if(r[1].high<r[3].high && r[1].low<r[3].low)structure=-40;
      double align=(ema50_recent>ema200_recent?20:-20); double slope=Clamp((ema50_recent-ema50_old)/point,-15,15);
      double price_loc=(r[1].close>ema50_recent?10:-10); double direction=Clamp(structure+align+slope+price_loc,-100,100);
      double adx_mult=Clamp((adx[0]-12.0)/18.0,0.35,1.0); double atr_ratio=(atr_median>0?atr_current/atr_median:1.0);
      double vol_mult=1.0;if(atr_ratio<AS_ATR_QUALITY_FLOOR_RATIO||atr_ratio>AS_ATR_QUALITY_CEILING_RATIO)vol_mult=0.60;else if(atr_ratio<0.75||atr_ratio>1.75)vol_mult=0.80;
      out.timeframe=tf; out.direction_score=direction; out.strength=MathAbs(direction)*adx_mult*vol_mult; out.trend_class=Classify(direction);
      out.ema50=ema50_recent;out.ema200=ema200_recent;out.adx=adx[0];out.atr=atr_current;out.atr_ratio=atr_ratio;
      out.available_information_time=r[1].time+PeriodSeconds(tf);out.valid=true;return true;
   }
};
