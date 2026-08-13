#pragma once
#include "../Domain/Models.mqh"
#include "../Core/Config.mqh"

// Market regime classification.
//
// Before asking "long or short?" the system should answer "is this market
// tradeable at all, and by what kind of strategy?". A pullback setup in a dead
// range and the same setup in a clean trend are not the same trade.
//
// Deliberately built from measurements the system already computes — ADX, the
// ATR-to-median ratio, EMA alignment across H4/H1, and the spread percentile —
// rather than a new indicator stack. The classification is only as good as its
// inputs, and adding more inputs before the outcome database can score them
// would be guessing with extra steps.
//
// The regime is currently ADVISORY: it is recorded on every signal and shown on
// the dashboard, but it does not gate signals. Gating on it is a decision for
// when there is outcome data to justify the threshold.

class AS_RegimeEngine
  {
private:
   double Clamp01(const double v) const { return MathMax(0.0, MathMin(1.0, v)); }

public:
   AS_RegimeResult Classify(const AS_TrendResult &h4, const AS_TrendResult &h1,
                            const AS_SymbolSnapshot &snap) const
     {
      AS_RegimeResult out;
      ZeroMemory(out);
      out.regime = AS_REGIME_UNKNOWN;
      out.valid = false;

      if(!h4.valid || !h1.valid)
        {
         out.reason = "TREND_DATA_UNAVAILABLE";
         return out;
        }

      // An unusable spread makes the regime question moot — nothing should be
      // traded here regardless of what the trend looks like.
      if(snap.spread_state == AS_SPREAD_EXTREME || snap.spread_state == AS_SPREAD_HIGH)
        {
         out.regime = AS_REGIME_ILLIQUID;
         out.confidence = 90.0;
         out.reason = "SPREAD_" + (snap.spread_state == AS_SPREAD_EXTREME ? "EXTREME" : "HIGH");
         out.valid = true;
         return out;
        }

      const bool aligned_up   = (h4.direction_score > 0.0 && h1.direction_score >= 20.0);
      const bool aligned_down = (h4.direction_score < 0.0 && h1.direction_score <= -20.0);

      // ADX is the trend/range discriminator; the ATR ratio separates a
      // healthy trend from a volatility event, and a dead tape from a range.
      const double adx = MathMax(h1.adx, 0.0);
      const double atr_ratio = h1.atr_ratio;

      if(atr_ratio > AS_ATR_QUALITY_CEILING_RATIO)
        {
         out.regime = AS_REGIME_VOLATILE;
         out.confidence = 100.0 * Clamp01((atr_ratio - AS_ATR_QUALITY_CEILING_RATIO) / 1.0);
         out.reason = StringFormat("ATR_RATIO_%.2f_ABOVE_CEILING", atr_ratio);
        }
      else if(atr_ratio < AS_ATR_QUALITY_FLOOR_RATIO)
        {
         out.regime = AS_REGIME_QUIET;
         out.confidence = 100.0 * Clamp01((AS_ATR_QUALITY_FLOOR_RATIO - atr_ratio) / 0.5);
         out.reason = StringFormat("ATR_RATIO_%.2f_BELOW_FLOOR", atr_ratio);
        }
      else if(aligned_up && adx >= 20.0)
        {
         out.regime = AS_REGIME_TREND_UP;
         out.confidence = 100.0 * Clamp01((adx - 15.0) / 25.0);
         out.reason = StringFormat("H4_H1_ALIGNED_UP_ADX_%.0f", adx);
        }
      else if(aligned_down && adx >= 20.0)
        {
         out.regime = AS_REGIME_TREND_DOWN;
         out.confidence = 100.0 * Clamp01((adx - 15.0) / 25.0);
         out.reason = StringFormat("H4_H1_ALIGNED_DOWN_ADX_%.0f", adx);
        }
      else
        {
         out.regime = AS_REGIME_RANGE;
         out.confidence = 100.0 * Clamp01((25.0 - adx) / 25.0);
         out.reason = StringFormat("NO_MTF_ALIGNMENT_ADX_%.0f", adx);
        }

      out.valid = true;
      return out;
     }
  };

string AS_RegimeName(const ENUM_AS_REGIME regime)
  {
   switch(regime)
     {
      case AS_REGIME_TREND_UP:   return "Trend Up";
      case AS_REGIME_TREND_DOWN: return "Trend Dn";
      case AS_REGIME_RANGE:      return "Range";
      case AS_REGIME_VOLATILE:   return "Volatile";
      case AS_REGIME_QUIET:      return "Quiet";
      case AS_REGIME_ILLIQUID:   return "Illiquid";
     }
   return "Unknown";
  }
