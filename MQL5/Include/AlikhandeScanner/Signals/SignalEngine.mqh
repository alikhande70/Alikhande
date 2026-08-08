#pragma once
#include "../Domain/Models.mqh"
#include "../Core/VersionInfo.mqh"
#include "../Core/Hash.mqh"
#include "../Core/Config.mqh"
#include "../Signal/SignalDomainV13.mqh"
#include "../Signal/ZoneSemanticsV13.mqh"
#include "../Signal/LiveValidatorV13.mqh"
#include "../Signal/ExplainableScoringV13.mqh"

class AS_SignalEngine {
private:
   AS_ZoneSemanticsV13 m_zone_semantics;
   AS_LiveValidatorV13 m_live_validator;
   AS_ExplainableScoringV13 m_scoring;

   void ToTyped(const string symbol,const AS_Zone &src,AS_TypedZone &dst) const {
      ZeroMemory(dst);dst.id=src.id;dst.symbol=symbol;dst.timeframe=src.timeframe;dst.kind=src.kind;
      dst.low=src.low;dst.high=src.high;dst.center=src.center;dst.quality=src.quality;dst.touches=src.touches;
      dst.pivot_time=src.pivot_time;dst.confirmation_time=src.confirmation_time;dst.broken=src.broken;dst.valid=src.valid;
   }

   int BestAnchor(const AS_Zone &zones[],const string symbol,const ENUM_AS_ZONE_KIND kind,const double price,const double atr,ENUM_AS_ZONE_RELATION &relation,double &distance) const {
      int best=-1;distance=1.0e100;relation=AS_ZONE_UNAVAILABLE;
      for(int i=0;i<ArraySize(zones);i++){
         if(!zones[i].valid||zones[i].broken||zones[i].kind!=kind)continue;
         AS_TypedZone typed;ToTyped(symbol,zones[i],typed);
         ENUM_AS_ZONE_RELATION rel=m_zone_semantics.Relation(typed,price);
         if(rel==AS_ZONE_UNAVAILABLE)continue;
         double d=0.0;
         if(rel==AS_ZONE_INSIDE)d=0.0;
         else if(kind==AS_ZONE_DEMAND && rel==AS_ZONE_ABOVE)d=price-zones[i].high;
         else if(kind==AS_ZONE_SUPPLY && rel==AS_ZONE_BELOW)d=zones[i].low-price;
         else continue;
         if(d<0.0)continue;
         if(atr>0.0 && d>atr*1.50)continue;
         if(best<0 || d<distance || (MathAbs(d-distance)<1e-8 && zones[i].quality>zones[best].quality)){
            best=i;distance=d;relation=rel;
         }
      }
      return best;
   }

   void AddComponent(AS_ScoreComponentV13 &items[],const string code,const double value,const string explanation) const {
      int n=ArraySize(items);ArrayResize(items,n+1);items[n].code=code;items[n].weight=value;items[n].contribution=value;items[n].explanation=explanation;
   }

   double Score(const ENUM_AS_DIRECTION direction,const AS_TrendResult &h4,const AS_TrendResult &h1,const AS_TrendResult &m15,const AS_TrendResult &m5,const AS_Zone &anchor,const ENUM_AS_SETUP_TYPE setup,const AS_SymbolSnapshot &snap,string &explanation) {
      AS_ScoreComponentV13 c[];string penalties[];double penalty_values[];string vetoes[];
      if(direction==AS_DIR_LONG){
         if(h4.direction_score>0)AddComponent(c,"H4_LONG",10,"H4 alignment");
         if(h1.direction_score>=20)AddComponent(c,"H1_BULL",20+MathMin(10.0,h1.strength*0.10),"H1 direction and strength");
         if(m15.direction_score>0)AddComponent(c,"M15_CONFIRM",10,"M15 agrees");
         if(m5.direction_score>=15)AddComponent(c,"M5_TRIGGER",15,"M5 trigger");
      } else {
         if(h4.direction_score<0)AddComponent(c,"H4_SHORT",10,"H4 alignment");
         if(h1.direction_score<=-20)AddComponent(c,"H1_BEAR",20+MathMin(10.0,h1.strength*0.10),"H1 direction and strength");
         if(m15.direction_score<0)AddComponent(c,"M15_CONFIRM",10,"M15 agrees");
         if(m5.direction_score<=-15)AddComponent(c,"M5_TRIGGER",15,"M5 trigger");
      }
      if(setup!=AS_SETUP_NONE)AddComponent(c,"SETUP",25,"structural setup present");
      if(anchor.valid)AddComponent(c,"ZONE_QUALITY",MathMin(15.0,anchor.quality*0.15),"anchor-zone quality");
      if(snap.spread_state==AS_SPREAD_NORMAL)AddComponent(c,"SPREAD_NORMAL",5,"spread normal");
      if(snap.spread_state==AS_SPREAD_ELEVATED){ArrayResize(penalties,1);ArrayResize(penalty_values,1);penalties[0]="SPREAD_ELEVATED";penalty_values[0]=5.0;}
      AS_ScoreResultV13 result;m_scoring.Evaluate(c,penalties,penalty_values,vetoes,result);
      explanation=result.positive_reasons+result.penalties;
      return result.final_score;
   }

public:
   bool Evaluate(const string symbol,const AS_TrendResult &h4,const AS_TrendResult &h1,const AS_TrendResult &m15,const AS_TrendResult &m5,const AS_SymbolSnapshot &snap,const AS_Zone &zones[],const AS_RegimeResult &regime,const AS_SymbolSpec &spec,AS_SignalCandidate &s){
      ZeroMemory(s);if(!h4.valid||!h1.valid||!m15.valid||!m5.valid||!spec.ready)return false;

      ENUM_AS_ZONE_RELATION demand_rel,supply_rel;double demand_dist=0,supply_dist=0;
      int di=BestAnchor(zones,symbol,AS_ZONE_DEMAND,snap.bid,h1.atr,demand_rel,demand_dist);
      int si=BestAnchor(zones,symbol,AS_ZONE_SUPPLY,snap.ask,h1.atr,supply_rel,supply_dist);
      bool near_demand=(di>=0),near_supply=(si>=0);

      ENUM_AS_SETUP_TYPE long_setup=AS_SETUP_NONE,short_setup=AS_SETUP_NONE;
      if(h1.direction_score>=20&&near_demand&&m15.direction_score>-20&&m5.direction_score>=15)long_setup=AS_TREND_PULLBACK;
      else if(h1.direction_score>-45&&near_demand&&m15.direction_score>=0&&m5.direction_score>=20)long_setup=AS_SUPPORT_REJECTION;
      if(h1.direction_score<=-20&&near_supply&&m15.direction_score<20&&m5.direction_score<=-15)short_setup=AS_TREND_PULLBACK;
      else if(h1.direction_score<45&&near_supply&&m15.direction_score<=0&&m5.direction_score<=-20)short_setup=AS_RESISTANCE_REJECTION;

      AS_Zone empty;ZeroMemory(empty);AS_Zone long_anchor=empty;AS_Zone short_anchor=empty;
      if(di>=0)long_anchor=zones[di];if(si>=0)short_anchor=zones[si];
      string long_explain="",short_explain="";
      s.long_score=Score(AS_DIR_LONG,h4,h1,m15,m5,long_anchor,long_setup,snap,long_explain);
      s.short_score=Score(AS_DIR_SHORT,h4,h1,m15,m5,short_anchor,short_setup,snap,short_explain);

      bool hard=false;string codes="";
      if(!regime.tradable){hard=true;codes+="REGIME_NOT_READY;";}
      if(snap.spread_state==AS_SPREAD_HIGH||snap.spread_state==AS_SPREAD_EXTREME||snap.spread_state==AS_SPREAD_STALE||snap.spread_state==AS_SPREAD_NO_TICK||snap.spread_state==AS_SPREAD_WARMING_UP){hard=true;codes+="SPREAD_OR_QUOTE_BLOCK;";}

      ENUM_AS_DIRECTION direction=AS_DIR_NONE;ENUM_AS_SETUP_TYPE setup=AS_SETUP_NONE;int anchor_index=-1;
      if(!hard&&long_setup!=AS_SETUP_NONE&&s.long_score>=75&&s.long_score-s.short_score>=10){direction=AS_DIR_LONG;setup=long_setup;anchor_index=di;}
      else if(!hard&&short_setup!=AS_SETUP_NONE&&s.short_score>=75&&s.short_score-s.long_score>=10){direction=AS_DIR_SHORT;setup=short_setup;anchor_index=si;}

      s.symbol=symbol;s.creation_time=TimeCurrent();s.confirmation_bar_time=m5.available_information_time;s.expires_at=s.creation_time+AS_DEFAULT_SIGNAL_TTL_SECONDS;
      s.rule_version=AS_RULE_VERSION;s.scoring_version=AS_SCORING_VERSION;s.parameter_hash=AS_Fnv1a("alikhande-v1.3-production");s.broker_spec_hash=spec.spec_hash;
      s.regime=regime.regime;s.regime_confidence=regime.confidence;s.has_historical_estimate=false;s.historical_win_rate=0;s.sample_size=0;s.confidence_low=0;s.confidence_high=0;

      if(direction!=AS_DIR_NONE && anchor_index>=0){
         AS_TypedZone anchor;ToTyped(symbol,zones[anchor_index],anchor);
         AS_StructuralCandidateV13 structural;ZeroMemory(structural);
         structural.symbol=symbol;structural.direction=direction;structural.setup=setup;structural.anchor_zone_id=anchor.id;structural.anchor_zone_low=anchor.low;structural.anchor_zone_high=anchor.high;
         structural.anchor_zone_quality=anchor.quality;structural.structural_atr=h1.atr;structural.structural_score=(direction==AS_DIR_LONG?s.long_score:s.short_score);structural.confirmation_bar_time=m5.available_information_time;structural.expires_at=s.expires_at;structural.valid=true;
         structural.candidate_id=AS_Fnv1a(StringFormat("%s|%d|%d|%I64d|%s|%s",symbol,(int)direction,(int)setup,(long)structural.confirmation_bar_time,anchor.id,AS_RULE_VERSION));
         AS_QuoteState quote;ZeroMemory(quote);quote.symbol=symbol;quote.bid=snap.bid;quote.ask=snap.ask;quote.point=snap.point;quote.digits=snap.digits;quote.spread_points=snap.spread_points;quote.tick_time=snap.tick_time;quote.data_state=snap.data_state;quote.fresh=(snap.data_state==AS_DATA_READY&&snap.spread_state!=AS_SPREAD_STALE&&snap.spread_state!=AS_SPREAD_NO_TICK);
         AS_LiveValidationV13 live;
         if(m_live_validator.Validate(structural,anchor,quote,AS_MINIMUM_RISK_REWARD,live)){
            s.direction=direction;s.setup=setup;s.preferred_entry=live.entry;s.stop_loss=live.stop_loss;s.take_profit=live.take_profit;s.signal_id=structural.candidate_id;
            s.reasons=(direction==AS_DIR_LONG?long_explain:short_explain)+live.reasons;
            s.nearest_support=(di>=0?zones[di].high:0);s.nearest_resistance=(si>=0?zones[si].low:0);
            if(direction==AS_DIR_LONG&&si>=0&&zones[si].low<s.take_profit){hard=true;codes+="OPPOSING_ZONE_BEFORE_2R;";}
            if(direction==AS_DIR_SHORT&&di>=0&&zones[di].high>s.take_profit){hard=true;codes+="OPPOSING_ZONE_BEFORE_2R;";}
         } else {
            hard=true;codes+=live.veto_codes;s.signal_id=structural.candidate_id;s.reasons=(direction==AS_DIR_LONG?long_explain:short_explain)+live.reasons;
         }
      }

      if(hard){s.direction=AS_DIR_NONE;s.setup=AS_SETUP_NONE;}
      if(s.signal_id=="")s.signal_id=AS_Fnv1a(StringFormat("%s|WATCH|%I64d|%s",symbol,(long)m5.available_information_time,AS_RULE_VERSION));
      s.hard_blocked=hard;s.validation_codes=codes;s.state=(s.direction==AS_DIR_NONE?AS_SIGNAL_WATCH:AS_SIGNAL_CONFIRMED);
      return true;
   }
};