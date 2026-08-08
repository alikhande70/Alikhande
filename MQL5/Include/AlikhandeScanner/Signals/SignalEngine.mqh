#pragma once
#include "../Domain/Models.mqh"
#include "../Core/Config.mqh"
#include "../Core/VersionInfo.mqh"
#include "../Core/Hash.mqh"
#include "../Analysis/TrendEngine.mqh"
#include "../Analysis/ZoneEngine.mqh"
#include "../Analysis/RegimeEngine.mqh"

// Signal generation, split into a cached structural half and a live half.
//
// This split is the fix for the most dangerous defect in v1.1.0. There, the
// whole candidate — including entry, stop, target and the "is price at a zone?"
// decision — was computed once per closed bar and then displayed and alerted
// against a *live* quote until the next bar closed. On M5 that is up to five
// minutes during which the dashboard shows LONG at an entry price the market
// left long ago, and the logged entry is not the entry a human would get.
//
// The structural half (multi-timeframe trend, zones, regime) genuinely only
// changes on bar close and stays cached. The live half — zone proximity, entry,
// stop, target, spread state — is recomputed on every pass against the current
// quote. A signal is therefore never older than the tick it is shown with.

// Fingerprint of the tunables that shape scoring. Stamped onto every persisted
// signal so a stored result can be tied to the exact configuration that made
// it; changing any of these invalidates comparison against older signals.
// Defined before its first use — MQL5 has no forward declarations for these.
string AS_ParameterHash(void)
  {
   return AS_Fnv1a64(StringFormat(
                        "prox=%.3f;stopbuf=%.3f;maxstop=%.3f;rr=%.3f;thr=%.1f;sep=%.1f;"
                        "zlb=%d;zl=%d;zr=%d;zw=%.3f",
                        AS_ZONE_PROXIMITY_ATR, AS_STOP_BUFFER_ATR, AS_MAX_STOP_DISTANCE_ATR,
                        AS_MINIMUM_RISK_REWARD, AS_SIGNAL_SCORE_THRESHOLD,
                        AS_SIGNAL_SCORE_SEPARATION, AS_ZONE_LOOKBACK_BARS,
                        AS_ZONE_PIVOT_LEFT, AS_ZONE_PIVOT_RIGHT, AS_ZONE_WIDTH_ATR_FRACTION));
  }

struct AS_StructuralContext
  {
   string          symbol;
   AS_TrendResult  h4;
   AS_TrendResult  h1;
   AS_TrendResult  m15;
   AS_TrendResult  m5;
   AS_Zone         zones[];
   AS_RegimeResult regime;
   datetime        built_at;
   bool            valid;
  };

class AS_SignalEngine
  {
private:
   double Clamp100(const double v) const { return MathMax(0.0, MathMin(100.0, v)); }

   void AddReason(string &reasons, const string code, const double contribution) const
     {
      reasons += StringFormat("%s%+.0f;", code, contribution);
     }

   // Qualification requires an actual pullback or rejection, not merely a
   // directional bias. Both branches demand M5 confirmation.
   ENUM_AS_SETUP_TYPE QualifyLong(const AS_StructuralContext &ctx, const bool at_demand) const
     {
      if(!at_demand)
         return AS_SETUP_NONE;
      if(ctx.h1.direction_score >= 20.0
         && ctx.m15.direction_score > -20.0
         && ctx.m5.direction_score >= 15.0)
         return AS_TREND_PULLBACK;
      if(ctx.h1.direction_score > -45.0
         && ctx.m15.direction_score >= 0.0
         && ctx.m5.direction_score >= 20.0)
         return AS_SUPPORT_REJECTION;
      return AS_SETUP_NONE;
     }

   ENUM_AS_SETUP_TYPE QualifyShort(const AS_StructuralContext &ctx, const bool at_supply) const
     {
      if(!at_supply)
         return AS_SETUP_NONE;
      if(ctx.h1.direction_score <= -20.0
         && ctx.m15.direction_score < 20.0
         && ctx.m5.direction_score <= -15.0)
         return AS_TREND_PULLBACK;
      if(ctx.h1.direction_score < 45.0
         && ctx.m15.direction_score <= 0.0
         && ctx.m5.direction_score <= -20.0)
         return AS_RESISTANCE_REJECTION;
      return AS_SETUP_NONE;
     }

public:
   // ------------------------------------------------------------- structure
   //
   // Called only when a closed bar changed on any analysed timeframe.
   bool BuildContext(const string symbol, AS_TrendEngine &trend, AS_ZoneEngine &zone_engine,
                     AS_RegimeEngine &regime_engine, const AS_SymbolSnapshot &snap,
                     AS_StructuralContext &ctx)
     {
      ctx.symbol = symbol;
      ctx.valid = false;

      if(!trend.Analyze(symbol, PERIOD_H4,  ctx.h4)
         || !trend.Analyze(symbol, PERIOD_H1,  ctx.h1)
         || !trend.Analyze(symbol, PERIOD_M15, ctx.m15)
         || !trend.Analyze(symbol, PERIOD_M5,  ctx.m5))
         return false;

      zone_engine.Build(symbol, PERIOD_H1, AS_ZONE_LOOKBACK_BARS,
                        AS_ZONE_PIVOT_LEFT, AS_ZONE_PIVOT_RIGHT,
                        AS_ZONE_WIDTH_ATR_FRACTION, ctx.zones);

      ctx.regime = regime_engine.Classify(ctx.h4, ctx.h1, snap);
      ctx.built_at = TimeCurrent();
      ctx.valid = true;
      return true;
     }

   // ------------------------------------------------------------------ live
   //
   // Called on EVERY scan pass with the current quote. Cheap: no indicator
   // reads, no history copies — just arithmetic over the cached structure.
   bool Evaluate(const AS_StructuralContext &ctx, const AS_SymbolSnapshot &snap,
                 AS_SignalCandidate &s)
     {
      ZeroMemory(s);
      s.symbol = ctx.symbol;
      s.state = AS_SIGNAL_NONE;
      s.direction = AS_DIR_NONE;
      s.setup = AS_SETUP_NONE;
      s.has_historical_estimate = false;

      if(!ctx.valid)
         return false;

      const double atr = ctx.h1.atr;
      if(atr <= 0.0)
        {
         s.validation_codes = "NO_ATR;";
         s.hard_blocked = true;
         return true;
        }

      // ---- structure relative to the LIVE quote --------------------------
      const double proximity = atr * AS_ZONE_PROXIMITY_ATR;
      int demand_index = -1;
      int supply_index = -1;
      const bool has_demand = AS_FindNearestZone(ctx.zones, AS_ZONE_DEMAND, snap.bid,
                                                 proximity, demand_index);
      const bool has_supply = AS_FindNearestZone(ctx.zones, AS_ZONE_SUPPLY, snap.ask,
                                                 proximity, supply_index);

      s.nearest_support    = has_demand ? ctx.zones[demand_index].center : 0.0;
      s.nearest_resistance = has_supply ? ctx.zones[supply_index].center : 0.0;

      const ENUM_AS_SETUP_TYPE long_setup  = QualifyLong(ctx, has_demand);
      const ENUM_AS_SETUP_TYPE short_setup = QualifyShort(ctx, has_supply);

      // ---- rule score -----------------------------------------------------
      // This is a RULE SCORE, not a probability. It is a weighted sum of
      // conditions the author believes matter; nothing here has been validated
      // against outcomes. Probability lives in AS_SignalCandidate's
      // historical_* fields and only appears once an outcome sample exists.
      double long_score = 0.0, short_score = 0.0;
      string long_reasons = "", short_reasons = "";

      if(ctx.h4.direction_score > 0.0)
        { long_score += 10.0; AddReason(long_reasons, "H4_BIAS", 10.0); }
      else if(ctx.h4.direction_score < 0.0)
        { short_score += 10.0; AddReason(short_reasons, "H4_BIAS", 10.0); }

      // Strength only ever reaches the side its own direction favours.
      const double h1_long  = AS_DirectionalBonus(ctx.h1, AS_DIR_LONG);
      const double h1_short = AS_DirectionalBonus(ctx.h1, AS_DIR_SHORT);
      if(ctx.h1.direction_score >= 20.0)
        {
         const double bonus = 20.0 + MathMin(10.0, h1_long * 0.10);
         long_score += bonus; AddReason(long_reasons, "H1_TREND", bonus);
        }
      else if(ctx.h1.direction_score <= -20.0)
        {
         const double bonus = 20.0 + MathMin(10.0, h1_short * 0.10);
         short_score += bonus; AddReason(short_reasons, "H1_TREND", bonus);
        }

      if(long_setup != AS_SETUP_NONE)
        { long_score += 25.0; AddReason(long_reasons, "SETUP", 25.0); }
      if(short_setup != AS_SETUP_NONE)
        { short_score += 25.0; AddReason(short_reasons, "SETUP", 25.0); }

      if(has_demand)
        {
         const double bonus = MathMin(15.0, ctx.zones[demand_index].quality * 0.15);
         long_score += bonus; AddReason(long_reasons, "ZONE_QUALITY", bonus);
        }
      if(has_supply)
        {
         const double bonus = MathMin(15.0, ctx.zones[supply_index].quality * 0.15);
         short_score += bonus; AddReason(short_reasons, "ZONE_QUALITY", bonus);
        }

      if(ctx.m5.direction_score >= 15.0)
        { long_score += 15.0; AddReason(long_reasons, "M5_CONFIRM", 15.0); }
      else if(ctx.m5.direction_score <= -15.0)
        { short_score += 15.0; AddReason(short_reasons, "M5_CONFIRM", 15.0); }

      if(ctx.h1.direction_score > 0.0 && ctx.m15.direction_score > 0.0 && ctx.m5.direction_score > 0.0)
        { long_score += 10.0; AddReason(long_reasons, "MTF_ALIGNED", 10.0); }
      if(ctx.h1.direction_score < 0.0 && ctx.m15.direction_score < 0.0 && ctx.m5.direction_score < 0.0)
        { short_score += 10.0; AddReason(short_reasons, "MTF_ALIGNED", 10.0); }

      if(snap.spread_state == AS_SPREAD_NORMAL)
        {
         long_score += 5.0; short_score += 5.0;
         AddReason(long_reasons, "SPREAD_NORMAL", 5.0);
         AddReason(short_reasons, "SPREAD_NORMAL", 5.0);
        }
      else if(snap.spread_state == AS_SPREAD_ELEVATED)
        { long_score += 2.0; short_score += 2.0; }

      // ---- penalties and hard blocks --------------------------------------
      string codes = "";
      bool hard = false;

      if(ctx.h4.direction_score <= -45.0 && ctx.h1.direction_score >= 45.0)
        { long_score -= 30.0; codes += "H4_H1_CONFLICT_LONG;"; }
      if(ctx.h4.direction_score >= 45.0 && ctx.h1.direction_score <= -45.0)
        { short_score -= 30.0; codes += "H4_H1_CONFLICT_SHORT;"; }

      if(snap.spread_state == AS_SPREAD_HIGH || snap.spread_state == AS_SPREAD_EXTREME
         || snap.spread_state == AS_SPREAD_STALE || snap.spread_state == AS_SPREAD_NO_TICK
         || snap.spread_state == AS_SPREAD_WARMING_UP)
        { hard = true; codes += "SPREAD_OR_QUOTE_BLOCK;"; }

      if(long_setup == AS_SETUP_NONE && short_setup == AS_SETUP_NONE)
         codes += "NO_CONFIRMED_SETUP;";

      s.long_score  = Clamp100(long_score);
      s.short_score = Clamp100(short_score);

      // ---- direction selection --------------------------------------------
      ENUM_AS_DIRECTION direction = AS_DIR_NONE;
      ENUM_AS_SETUP_TYPE setup = AS_SETUP_NONE;

      if(!hard && long_setup != AS_SETUP_NONE
         && s.long_score >= AS_SIGNAL_SCORE_THRESHOLD
         && s.long_score - s.short_score >= AS_SIGNAL_SCORE_SEPARATION)
        { direction = AS_DIR_LONG; setup = long_setup; }
      else if(!hard && short_setup != AS_SETUP_NONE
              && s.short_score >= AS_SIGNAL_SCORE_THRESHOLD
              && s.short_score - s.long_score >= AS_SIGNAL_SCORE_SEPARATION)
        { direction = AS_DIR_SHORT; setup = short_setup; }

      // ---- structural stop and 2R target ----------------------------------
      double entry = 0.0, stop = 0.0, target = 0.0;
      if(direction != AS_DIR_NONE)
        {
         entry = (direction == AS_DIR_SHORT ? snap.bid : snap.ask);
         const double buffer = MathMax(atr * AS_STOP_BUFFER_ATR, snap.point * 5.0);

         if(direction == AS_DIR_LONG)
            stop = ctx.zones[demand_index].low - buffer;
         else
            stop = ctx.zones[supply_index].high + buffer;

         const double risk_distance = MathAbs(entry - stop);
         if(risk_distance <= 0.0 || risk_distance > atr * AS_MAX_STOP_DISTANCE_ATR)
           {
            hard = true;
            codes += "INVALID_STRUCTURAL_STOP;";
           }
         else
           {
            target = (direction == AS_DIR_LONG
                      ? entry + AS_MINIMUM_RISK_REWARD * risk_distance
                      : entry - AS_MINIMUM_RISK_REWARD * risk_distance);

            // An opposing level inside the road to target means the 2R is
            // arithmetic, not something the market is likely to deliver.
            int blocking = -1;
            if(direction == AS_DIR_LONG
               && AS_FindZoneBeyond(ctx.zones, AS_ZONE_SUPPLY, entry, true, blocking)
               && ctx.zones[blocking].low < target)
              { hard = true; codes += "OPPOSING_ZONE_BEFORE_2R;"; }
            if(direction == AS_DIR_SHORT
               && AS_FindZoneBeyond(ctx.zones, AS_ZONE_DEMAND, entry, false, blocking)
               && ctx.zones[blocking].high > target)
              { hard = true; codes += "OPPOSING_ZONE_BEFORE_2R;"; }
           }
        }

      // A hard block clears BOTH direction and setup. v1.1.0 cleared only
      // direction, leaving a phantom setup on a blocked candidate.
      if(hard)
        {
         direction = AS_DIR_NONE;
         setup = AS_SETUP_NONE;
         entry = 0.0;
         stop = 0.0;
         target = 0.0;
        }

      s.direction          = direction;
      s.setup              = setup;
      s.hard_blocked       = hard;
      s.validation_codes   = codes;
      s.reasons            = (direction == AS_DIR_LONG ? long_reasons
                              : (direction == AS_DIR_SHORT ? short_reasons : ""));
      s.preferred_entry    = entry;
      s.entry_low          = (entry > 0.0 ? entry - atr * 0.10 : 0.0);
      s.entry_high         = (entry > 0.0 ? entry + atr * 0.10 : 0.0);
      s.stop_loss          = stop;
      s.take_profit        = target;

      s.creation_time          = TimeCurrent();
      s.confirmation_bar_time  = ctx.m5.available_information_time;
      s.expires_at             = s.creation_time + AS_SIGNAL_TTL_SECONDS;
      s.rule_version           = AS_RULE_VERSION;
      s.scoring_version        = AS_SCORING_VERSION;
      s.parameter_hash         = AS_ParameterHash();

      // Identity is keyed on the structural situation, not on the live price:
      // the same setup re-evaluated a few seconds later at a slightly
      // different quote is the SAME signal, and must not be logged twice.
      s.signal_id = AS_Fnv1a(StringFormat("%s|%d|%d|%I64d|%s",
                                          ctx.symbol, (int)direction, (int)setup,
                                          (long)s.confirmation_bar_time, AS_RULE_VERSION));

      s.state = (direction != AS_DIR_NONE ? AS_SIGNAL_CONFIRMED
                 : (hard ? AS_SIGNAL_NONE : AS_SIGNAL_CANDIDATE));
      return true;
     }
  };
