//+------------------------------------------------------------------+
//| TrendEngine.mqh                                                    |
//| Multi-timeframe trend classification via EMA structure (20/50/200)|
//| plus ADX-based strength. Two rules fixed per the v1.1.0 changelog |
//| and re-encoded as tests in Tests/TrendEngineTests.mqh:            |
//|  - H4 neutral gives NEITHER direction a bonus (not "50/50 split") |
//|  - Strength on any timeframe benefits ONLY its own direction      |
//|    (a bullish H1 strength score must never add to the short side) |
//+------------------------------------------------------------------+
#property strict
#include "../Domain/Models.mqh"
#include "../Data/MarketData.mqh"
#include "../Core/Config.mqh"

ENUM_TREND_DIRECTION ClassifyEmaStructure(const double ema20, const double ema50,
                                           const double ema200)
  {
   if(ema20 > ema50 && ema50 > ema200)
      return TREND_BULLISH;
   if(ema20 < ema50 && ema50 < ema200)
      return TREND_BEARISH;
   return TREND_NEUTRAL;
  }

double ReadAdxStrength(const string symbol, const ENUM_TIMEFRAMES tf, const int period)
  {
   int handle = iADX(symbol, tf, period);
   if(handle == INVALID_HANDLE)
      return 0.0;

   double buf[];
   ArraySetAsSeries(buf, true);
   if(CopyBuffer(handle, 0, 0, 1, buf) <= 0) // main ADX line
      return 0.0;
   return MathMin(buf[0], 100.0);
  }

TrendState ComputeTrendState(const string symbol, const ENUM_TIMEFRAMES tf)
  {
   TrendState state;
   MarketSnapshot snap = FetchMarketSnapshot(symbol, tf, CFG_ATR_PERIOD);
   state.direction = ClassifyEmaStructure(snap.ema20, snap.ema50, snap.ema200);
   state.strength  = (state.direction == TREND_NEUTRAL) ? 0.0
                      : ReadAdxStrength(symbol, tf, 14);
   return state;
  }

MtfSnapshot ComputeMtfSnapshot(const string symbol)
  {
   MtfSnapshot mtf;
   mtf.h4  = ComputeTrendState(symbol, CFG_TF_H4);
   mtf.h1  = ComputeTrendState(symbol, CFG_TF_H1);
   mtf.m15 = ComputeTrendState(symbol, CFG_TF_M15);
   mtf.m5  = ComputeTrendState(symbol, CFG_TF_M5);
   return mtf;
  }

//+------------------------------------------------------------------+
//| Directional bonus for one timeframe's contribution to the score.  |
//| Neutral => 0 for BOTH directions (the H4-neutral bug fix). A      |
//| directional state contributes its strength ONLY to its own side   |
//| (the two-sided scoring bug fix) — the opposite side gets 0, not a |
//| penalty and not a share of the bonus.                             |
//+------------------------------------------------------------------+
double DirectionalBonus(const TrendState &state, const ENUM_TREND_DIRECTION wantDirection)
  {
   if(state.direction == TREND_NEUTRAL)
      return 0.0;
   if(state.direction != wantDirection)
      return 0.0;
   return state.strength;
  }
