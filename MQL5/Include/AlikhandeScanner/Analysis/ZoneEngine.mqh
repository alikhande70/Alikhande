#pragma once
#include "../Domain/Models.mqh"

struct AS_ZoneAtrHandle {
   string symbol;
   ENUM_TIMEFRAMES timeframe;
   int atr;
};

class AS_ZoneEngine {
private:
   AS_ZoneAtrHandle m_handles[];

   int AtrHandle(const string symbol,const ENUM_TIMEFRAMES tf){
      for(int i=0;i<ArraySize(m_handles);i++)if(m_handles[i].symbol==symbol&&m_handles[i].timeframe==tf)return m_handles[i].atr;
      int handle=iATR(symbol,tf,14);if(handle==INVALID_HANDLE)return INVALID_HANDLE;
      AS_ZoneAtrHandle item;item.symbol=symbol;item.timeframe=tf;item.atr=handle;
      int n=ArraySize(m_handles);ArrayResize(m_handles,n+1);m_handles[n]=item;return handle;
   }

   void ReleaseAll(){for(int i=0;i<ArraySize(m_handles);i++)if(m_handles[i].atr!=INVALID_HANDLE)IndicatorRelease(m_handles[i].atr);ArrayResize(m_handles,0);}
public:
   ~AS_ZoneEngine(void){ReleaseAll();}

   int Build(const string symbol,const ENUM_TIMEFRAMES tf,const int bars,const int left,const int right,const double atr_fraction,AS_Zone &zones[]) {
      ArrayResize(zones,0); if(bars<50||left<1||right<1)return 0;
      MqlRates r[]; ArraySetAsSeries(r,true); if(CopyRates(symbol,tf,1,bars,r)!=bars)return 0;
      int ha=AtrHandle(symbol,tf); if(ha==INVALID_HANDLE)return 0; double a[];ArrayResize(a,bars);ArraySetAsSeries(a,true);
      if(BarsCalculated(ha)<bars||CopyBuffer(ha,0,1,bars,a)!=bars)return 0;
      AS_Zone pivots[]; int n=0;
      for(int i=right;i<bars-left;i++) {
         bool hi=true,lo=true;
         for(int k=1;k<=left;k++){ if(r[i].high<=r[i+k].high)hi=false; if(r[i].low>=r[i+k].low)lo=false; }
         for(int k=1;k<=right;k++){ if(r[i].high<r[i-k].high)hi=false; if(r[i].low>r[i-k].low)lo=false; }
         double width=MathMax(a[i]*atr_fraction,SymbolInfoDouble(symbol,SYMBOL_POINT)*5);
         if(hi){
            ArrayResize(pivots,n+1);double p=r[i].high;
            pivots[n].center=p;pivots[n].low=p-width;pivots[n].high=p+width;pivots[n].timeframe=tf;pivots[n].kind=AS_ZONE_SUPPLY;
            pivots[n].pivot_time=r[i].time;pivots[n].confirmation_time=r[i-right].time+PeriodSeconds(tf);
            pivots[n].touches=1;pivots[n].quality=30;pivots[n].valid=true;pivots[n].broken=false;
            pivots[n].id=StringFormat("%s_%d_SUP_%I64d",symbol,(int)tf,(long)r[i].time);n++;
         }
         if(lo){
            ArrayResize(pivots,n+1);double p=r[i].low;
            pivots[n].center=p;pivots[n].low=p-width;pivots[n].high=p+width;pivots[n].timeframe=tf;pivots[n].kind=AS_ZONE_DEMAND;
            pivots[n].pivot_time=r[i].time;pivots[n].confirmation_time=r[i-right].time+PeriodSeconds(tf);
            pivots[n].touches=1;pivots[n].quality=30;pivots[n].valid=true;pivots[n].broken=false;
            pivots[n].id=StringFormat("%s_%d_DEM_%I64d",symbol,(int)tf,(long)r[i].time);n++;
         }
      }
      int z=0;
      for(int i=0;i<n;i++){
         int found=-1;
         for(int j=0;j<z;j++){
            if(pivots[i].kind!=zones[j].kind)continue;
            if(pivots[i].center>=zones[j].low && pivots[i].center<=zones[j].high){found=j;break;}
         }
         if(found<0){ArrayResize(zones,z+1);zones[z]=pivots[i];z++;}
         else{zones[found].low=MathMin(zones[found].low,pivots[i].low);zones[found].high=MathMax(zones[found].high,pivots[i].high);zones[found].center=(zones[found].low+zones[found].high)/2.0;zones[found].touches++;zones[found].quality=MathMin(100.0,zones[found].quality+10.0);}
      }
      return z;
   }
};