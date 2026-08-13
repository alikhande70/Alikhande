#pragma once
#include "../Domain/Models.mqh"
#include "../Core/Config.mqh"
#include "../Data/IndicatorCache.mqh"

// Multi-timeframe trend classification.
//
// The scoring model is inherited from v1.1.0 and deliberately unchanged — it is
// the part of the system that was actually reviewed and corrected, including
// two real fixes worth preserving explicitly:
//
//   * EMA slope reads the correct chronological ends of the buffer.
//   * Strength is a *magnitude*; direction carries the sign. Callers must
//     apply strength only to the side the direction already favours, or a
//     bearish trend ends up inflating the long score (the "two-sided strength"
//     bug). DirectionalBonus() below is the only sanctioned way to consume it.
//
// What changed: indicator handles come from the shared cache instead of being
// created and released on every call.

class AS_TrendEngine
  {
private:
   AS_IndicatorCache *m_indicators;

   ENUM_AS_TREND_CLASS Classify(const double d) const
     {
      if(d >=  75) return AS_STRONG_BULLISH;
      if(d >=  45) return AS_BULLISH;
      if(d >=  20) return AS_WEAK_BULLISH;
      if(d <= -75) return AS_STRONG_BEARISH;
      if(d <= -45) return AS_BEARISH;
      if(d <= -20) return AS_WEAK_BEARISH;
      return AS_NEUTRAL;
     }

   double Clamp(const double v, const double lo, const double hi) const
     {
      return MathMax(lo, MathMin(hi, v));
     }

   double Median(const double &values[]) const
     {
      const int count = ArraySize(values);
      if(count == 0)
         return 0.0;
      double sorted[];
      ArrayResize(sorted, count);
      ArrayCopy(sorted, values);
      ArraySort(sorted);
      if((count % 2) == 1)
         return sorted[count / 2];
      return (sorted[count / 2 - 1] + sorted[count / 2]) / 2.0;
     }

public:
   AS_TrendEngine(void) { m_indicators = NULL; }

   void Attach(AS_IndicatorCache &cache) { m_indicators = GetPointer(cache); }

   bool Analyze(const string symbol, const ENUM_TIMEFRAMES tf, AS_TrendResult &out)
     {
      ZeroMemory(out);
      if(m_indicators == NULL)
         return false;

      // Bars 1..3 are the three most recent CLOSED bars. Bar 0 is still
      // forming and is never read: acting on a forming bar is look-ahead.
      MqlRates rates[];
      ArraySetAsSeries(rates, true);
      if(CopyRates(symbol, tf, 0, 4, rates) != 4)
         return false;

      const int ema_fast = m_indicators.Handle(symbol, tf, AS_IND_EMA, 50);
      const int ema_slow = m_indicators.Handle(symbol, tf, AS_IND_EMA, 200);
      const int adx      = m_indicators.Handle(symbol, tf, AS_IND_ADX, 14);
      const int atr      = m_indicators.Handle(symbol, tf, AS_IND_ATR, 14);
      if(ema_fast == INVALID_HANDLE || ema_slow == INVALID_HANDLE
         || adx == INVALID_HANDLE || atr == INVALID_HANDLE)
         return false;

      // CopyClosed returns chronological order: last element is the most
      // recent closed bar, element 0 is the oldest of the requested window.
      double fast[], slow[], adx_values[], atr_history[];
      if(!m_indicators.CopyClosed(ema_fast, 0, 3, fast)
         || !m_indicators.CopyClosed(ema_slow, 0, 1, slow)
         || !m_indicators.CopyClosed(adx, 0, 1, adx_values)
         || !m_indicators.CopyClosed(atr, 0, AS_ATR_QUALITY_LOOKBACK, atr_history))
         return false;

      const double ema_fast_now = fast[2];
      const double ema_fast_old = fast[0];
      const double ema_slow_now = slow[0];
      const double atr_now      = atr_history[AS_ATR_QUALITY_LOOKBACK - 1];
      const double atr_median   = Median(atr_history);

      const double point = SymbolInfoDouble(symbol, SYMBOL_POINT);
      if(point <= 0.0 || atr_now <= 0.0)
         return false;

      // Swing structure over the last three closed bars: higher high AND
      // higher low, or the mirror image. Anything else contributes nothing.
      double structure = 0.0;
      if(rates[1].high > rates[3].high && rates[1].low > rates[3].low)
         structure = 40.0;
      else if(rates[1].high < rates[3].high && rates[1].low < rates[3].low)
         structure = -40.0;

      const double alignment = (ema_fast_now > ema_slow_now ? 20.0 : -20.0);
      const double slope     = Clamp((ema_fast_now - ema_fast_old) / point, -15.0, 15.0);
      const double location  = (rates[1].close > ema_fast_now ? 10.0 : -10.0);
      const double direction = Clamp(structure + alignment + slope + location, -100.0, 100.0);

      // A trend nobody is trading is not a trend: ADX scales conviction down,
      // and an ATR far from its own median means the regime is unreliable.
      const double adx_multiplier = Clamp((adx_values[0] - 12.0) / 18.0, 0.35, 1.0);
      const double atr_ratio = (atr_median > 0.0 ? atr_now / atr_median : 1.0);

      double volatility_multiplier = 1.0;
      if(atr_ratio < AS_ATR_QUALITY_FLOOR_RATIO || atr_ratio > AS_ATR_QUALITY_CEILING_RATIO)
         volatility_multiplier = 0.60;
      else if(atr_ratio < 0.75 || atr_ratio > 1.75)
         volatility_multiplier = 0.80;

      out.timeframe       = tf;
      out.direction_score = direction;
      out.strength        = MathAbs(direction) * adx_multiplier * volatility_multiplier;
      out.trend_class     = Classify(direction);
      out.ema50           = ema_fast_now;
      out.ema200          = ema_slow_now;
      out.adx             = adx_values[0];
      out.atr             = atr_now;
      out.atr_ratio       = atr_ratio;
      // The moment this information first became knowable: the close of bar 1.
      out.available_information_time = rates[1].time + PeriodSeconds(tf);
      out.valid           = true;
      return true;
     }
  };

// Strength contribution for one timeframe toward one side.
//
// Returns 0 for a neutral trend (neither side earns a bonus) and 0 when the
// trend opposes the requested direction. Consuming `strength` directly instead
// of going through here is how the two-sided inflation bug happens.
double AS_DirectionalBonus(const AS_TrendResult &trend, const ENUM_AS_DIRECTION wanted)
  {
   if(!trend.valid || wanted == AS_DIR_NONE)
      return 0.0;
   if(trend.direction_score == 0.0)
      return 0.0;
   const bool trend_is_long = trend.direction_score > 0.0;
   const bool want_long = (wanted == AS_DIR_LONG);
   if(trend_is_long != want_long)
      return 0.0;
   return trend.strength;
  }
