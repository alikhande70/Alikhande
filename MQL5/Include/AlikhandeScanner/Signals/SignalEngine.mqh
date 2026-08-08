#pragma once
#include "../Domain/Models.mqh"
#include "../Core/VersionInfo.mqh"
#include "../Core/Hash.mqh"
#include "../Core/Config.mqh"

class AS_SignalEngine {
private:
   double Clamp(double v){return MathMax(0.0,MathMin(100.0,v));}
   void NearestZones(const AS_Zone &zones[],const AS_SymbolSnapshot &snap,int &support_index,int &resistance_index){
      support_index=-1;resistance_index=-1;
      for(int i=0;i<ArraySize(zones);i++){
         if(!zones[i].valid)continue;
         if(zones[i].high<=snap.bid && (support_index<0||zones[i].high>zones[support_index].high))support_index=i;
         if(zones[i].low>=snap.ask && (resistance_index<0||zones[i].low<zones[resistance_index].low))resistance_index=i;
      }
   }
public:
   bool Evaluate(const string symbol,const AS_TrendResult &h4,const AS_TrendResult &h1,const AS_TrendResult &m15,const AS_TrendResult &m5,const AS_SymbolSnapshot &snap,const AS_Zone &zones[],AS_SignalCandidate &s) {
      ZeroMemory(s);if(!h4.valid||!h1.valid||!m15.valid||!m5.valid)return false;
      int si,ri;NearestZones(zones,snap,si,ri);
      double support=(si>=0?zones[si].high:0),resistance=(ri>=0?zones[ri].low:0);
      bool near_support=(si>=0 && snap.bid>=zones[si].low-h1.atr*0.10 && snap.bid-zones[si].high<=h1.atr*1.50);
      bool near_resistance=(ri>=0 && snap.ask<=zones[ri].high+h1.atr*0.10 && zones[ri].low-snap.ask<=h1.atr*1.50);
      ENUM_AS_SETUP_TYPE long_setup=AS_SETUP_NONE,short_setup=AS_SETUP_NONE;
      if(h1.direction_score>=20 && near_support && m15.direction_score>-20 && m5.direction_score>=15)long_setup=AS_TREND_PULLBACK;
      else if(h1.direction_score>-45 && near_support && m15.direction_score>=0 && m5.direction_score>=20)long_setup=AS_SUPPORT_REJECTION;
      if(h1.direction_score<=-20 && near_resistance && m15.direction_score<20 && m5.direction_score<=-15)short_setup=AS_TREND_PULLBACK;
      else if(h1.direction_score<45 && near_resistance && m15.direction_score<=0 && m5.direction_score<=-20)short_setup=AS_RESISTANCE_REJECTION;

      double long_base=0,short_base=0;string lr="",sr="";
      if(h4.direction_score>0){long_base+=10;lr+="H4_SUPPORTS_LONG;";}else if(h4.direction_score<0){short_base+=10;sr+="H4_SUPPORTS_SHORT;";}
      if(h1.direction_score>=20){long_base+=20+MathMin(10.0,h1.strength*0.10);lr+="H1_BULL;";}
      else if(h1.direction_score<=-20){short_base+=20+MathMin(10.0,h1.strength*0.10);sr+="H1_BEAR;";}
      if(long_setup!=AS_SETUP_NONE){long_base+=25;lr+="VALID_LONG_SETUP;";}if(short_setup!=AS_SETUP_NONE){short_base+=25;sr+="VALID_SHORT_SETUP;";}
      if(si>=0){long_base+=MathMin(15.0,zones[si].quality*0.15);lr+="STRUCTURAL_SUPPORT;";}
      if(ri>=0){short_base+=MathMin(15.0,zones[ri].quality*0.15);sr+="STRUCTURAL_RESISTANCE;";}
      if(m5.direction_score>=15){long_base+=15;lr+="M5_CONFIRM;";}else if(m5.direction_score<=-15){short_base+=15;sr+="M5_CONFIRM;";}
      if(h1.direction_score>0&&m15.direction_score>0&&m5.direction_score>0){long_base+=10;lr+="MTF_ALIGNED;";}
      if(h1.direction_score<0&&m15.direction_score<0&&m5.direction_score<0){short_base+=10;sr+="MTF_ALIGNED;";}
      if(snap.spread_state==AS_SPREAD_NORMAL){long_base+=5;short_base+=5;}else if(snap.spread_state==AS_SPREAD_ELEVATED){long_base+=2;short_base+=2;}

      double long_pen=0,short_pen=0;bool hard=false;string codes="";
      if(h4.direction_score<=-45 && h1.direction_score>=45){long_pen+=30;codes+="H4_H1_CONFLICT_LONG;";}
      if(h4.direction_score>=45 && h1.direction_score<=-45){short_pen+=30;codes+="H4_H1_CONFLICT_SHORT;";}
      if(snap.spread_state==AS_SPREAD_HIGH||snap.spread_state==AS_SPREAD_EXTREME||snap.spread_state==AS_SPREAD_STALE||snap.spread_state==AS_SPREAD_NO_TICK||snap.spread_state==AS_SPREAD_WARMING_UP){hard=true;codes+="SPREAD_OR_QUOTE_BLOCK;";}
      if(long_setup==AS_SETUP_NONE&&short_setup==AS_SETUP_NONE)codes+="NO_CONFIRMED_SETUP;";

      s.long_score=Clamp(long_base-long_pen);s.short_score=Clamp(short_base-short_pen);s.direction=AS_DIR_NONE;s.setup=AS_SETUP_NONE;
      if(!hard && long_setup!=AS_SETUP_NONE && s.long_score>=75 && s.long_score-s.short_score>=10){s.direction=AS_DIR_LONG;s.setup=long_setup;}
      else if(!hard && short_setup!=AS_SETUP_NONE && s.short_score>=75 && s.short_score-s.long_score>=10){s.direction=AS_DIR_SHORT;s.setup=short_setup;}

      double entry=(s.direction==AS_DIR_SHORT?snap.bid:snap.ask),buffer=MathMax(h1.atr*0.15,snap.point*5),stop=0;
      if(s.direction==AS_DIR_LONG){if(si<0){hard=true;codes+="NO_STRUCTURAL_SUPPORT;";}else stop=zones[si].low-buffer;}
      if(s.direction==AS_DIR_SHORT){if(ri<0){hard=true;codes+="NO_STRUCTURAL_RESISTANCE;";}else stop=zones[ri].high+buffer;}
      double risk_distance=(stop>0?MathAbs(entry-stop):0),tp=0;
      if(s.direction!=AS_DIR_NONE){
         if(risk_distance<=0||risk_distance>h1.atr*2.50){hard=true;codes+="INVALID_STRUCTURAL_STOP;";}
         else tp=(s.direction==AS_DIR_LONG?entry+AS_MINIMUM_RISK_REWARD*risk_distance:entry-AS_MINIMUM_RISK_REWARD*risk_distance);
         if(s.direction==AS_DIR_LONG&&ri>=0&&zones[ri].low<tp){hard=true;codes+="OPPOSING_ZONE_BEFORE_2R;";}
         if(s.direction==AS_DIR_SHORT&&si>=0&&zones[si].high>tp){hard=true;codes+="OPPOSING_ZONE_BEFORE_2R;";}
      }
      if(hard)s.direction=AS_DIR_NONE;
      s.symbol=symbol;s.preferred_entry=entry;s.entry_low=entry-h1.atr*0.10;s.entry_high=entry+h1.atr*0.10;s.stop_loss=stop;s.take_profit=tp;
      s.nearest_support=support;s.nearest_resistance=resistance;s.creation_time=TimeCurrent();s.confirmation_bar_time=m5.available_information_time;s.expires_at=s.creation_time+15*60;
      s.rule_version=AS_RULE_VERSION;s.scoring_version=AS_SCORING_VERSION;
      string key=StringFormat("%s|%d|%d|%I64d|%s",symbol,(int)s.direction,(int)s.setup,(long)s.confirmation_bar_time,AS_RULE_VERSION);s.signal_id=AS_Fnv1a(key);s.parameter_hash=AS_Fnv1a("alikhande-v1.1-defaults");
      s.reasons=(s.direction==AS_DIR_LONG?lr:(s.direction==AS_DIR_SHORT?sr:""));s.hard_blocked=hard;s.validation_codes=codes;
      s.has_historical_estimate=false;s.historical_win_rate=0;s.sample_size=0;s.confidence_low=0;s.confidence_high=0;return true;
   }
};
