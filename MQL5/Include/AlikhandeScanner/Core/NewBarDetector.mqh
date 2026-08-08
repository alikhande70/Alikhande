#pragma once
class AS_NewBarDetector {
public:
   bool ClosedBarChanged(const string symbol,const ENUM_TIMEFRAMES tf,datetime &last_seen,datetime &closed_bar_time){
      closed_bar_time=iTime(symbol,tf,1);
      if(closed_bar_time<=0)return false;
      if(closed_bar_time==last_seen)return false;
      last_seen=closed_bar_time;
      return true;
   }
};
