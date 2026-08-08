#pragma once
#include "../Domain/Models.mqh"
#include "../Core/Config.mqh"

struct AS_TrendHandleSet {
   string symbol;
   ENUM_TIMEFRAMES timeframe;
   int ema50;
   int ema200;
   int adx;
   int atr;
};

class AS_TrendEngine {
private:
   AS_TrendHandleSet m_handles[];

   ENUM_AS_TREND_CLASS Classify(const double d){ if(d>=75)return AS_STRONG_BULLISH; if(d>=45)return AS_BULLISH; if(d>=20)return AS_WEAK_BULLISH; if(d<=-75)return AS_STRONG_BEARISH; if(d<=-45)return AS_BEARISH; if(d<=-20)return AS_WEAK_BEARISH; return AS_NEUTRAL; }
   double Clamp(const double v,const double lo,const double hi){return MathMax(lo,MathMin(hi,v));}
   double Median(double &values[],const int count){double tmp[];ArrayResize(tmp,count);for(int i=0;i<count;i++)tmp[i]=values[i];ArraySort(tmp);if((count%2)==1)return tmp[count/2];return (tmp[count/2-1]+tmp[count/2])/2.0;}

   bool GetHandles(const string symbol,const ENUM_TIMEFRAMES tf,AS_TrendHandleSet &out){
      for(int i=0;i<ArraySize(m_handles);i++){
         if(m_handles[i].symbol==symbol&&m_handles[i].timeframe==tf){out=m_handles[i];return true;}
      }
      AS_TrendHandleSet h;h.symbol=symbol;h.timeframe=tf;
      h.ema50=iMA(symbol,tf,50,0,MODE_EMA,PRICE_CLOSE);
      h.ema200=iMA(symbol,tf,200,0,MODE_EMA,PRICE_CLOSE);
      h.adx=iADX(symbol,tf,14);
      h.atr=iATR(symbol,tf,14);
      if(h.ema50==INVALID_HANDLE||h.ema200==INVALID_HANDLE||h.adx==INVALID_HANDLE||h.atr==INVALID_HANDLE){
         if(h.ema50!=INVALID_HANDLE)IndicatorRelease(h.ema50);if(h.ema200!=INVALID_HANDLE)IndicatorRelease(h.ema200);if(h.adx!=INVALID_HANDLE)IndicatorRelease(h.adx);if(h.atr!=INVALID_HANDLE)IndicatorRelease(h.atr);return false;
      }
      int n=ArraySize(m_handles);ArrayResize(m_handles,n+1);m_handles[n]=h;out=h;return true;
   }

   void ReleaseAll(){
      for(int i=0;i<ArraySize(m_handles);i++){
         if(m_handles[i].ema50!=INVALID_HANDLE)IndicatorRelease(m_handles[i].ema50);
         if(m_handles[i].ema200!=INVALID_HANDLE)IndicatorRelease(m_handles[i].ema200);
         if(m_handles[i].adx!=INVALID_HANDLE)IndicatorRelease(m_handles[i].adx);
         if(m_handles[i].atr!=INVALID_HANDLE)IndicatorRelease(m_handles[i].atr);
      }
      ArrayResize(m_handles,0);
   }
public:
   ~AS_TrendEngine(void){ReleaseAll();}

   bool Analyze(const string symbol,const ENUM_TIMEFRAMES tf,AS_TrendResult &out) {
      ZeroMemory(out); const int need=260; MqlRates r[]; ArraySetAsSeries(r,true); if(CopyRates(symbol,tf,0,need,r)!=need)return false;
      AS_TrendHandleSet h;if(!GetHandles(symbol,tf,h))return false;
      if(BarsCalculated(h.ema50)<need||BarsCalculated(h.ema200)<need||BarsCalculated(h.adx)<need||BarsCalculated(h.atr)<need)return false;
      double e50[3],e200[3],adx[1],atr_hist[];ArrayResize(atr_hist,AS_ATR_QUALITY_LOOKBACK);
      bool ok=CopyBuffer(h.ema50,0,1,3,e50)==3 && CopyBuffer(h.ema200,0,1,3,e200)==3 && CopyBuffer(h.adx,0,1,1,adx)==1 && CopyBuffer(h.atr,0,1,AS_ATR_QUALITY_LOOKBACK,atr_hist)==AS_ATR_QUALITY_LOOKBACK;
      if(!ok)return false;
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