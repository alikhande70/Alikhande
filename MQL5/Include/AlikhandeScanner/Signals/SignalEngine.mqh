//+------------------------------------------------------------------+
//| SignalEngine.mqh                                                   |
//| Combines TrendEngine + ZoneEngine into scored candidates. Rules   |
//| enforced per docs/v1.1.0_ACCEPTANCE_TESTS.md "Logic Gate":         |
//|  - no setup label without zone proximity AND M5 confirmation       |
//|  - SL outside the relevant H1 zone with ATR protection             |
//|  - TP = 2R and a nearer opposing zone blocks the candidate         |
//+------------------------------------------------------------------+
#property strict
#include "../Analysis/TrendEngine.mqh"
#include "../Analysis/ZoneEngine.mqh"
#include "../Core/Config.mqh"

//+------------------------------------------------------------------+
//| M5 confirmation: an actual pullback (price re-entered the zone    |
//| then closed back in the trade direction) or rejection (wick       |
//| through the zone, close outside it) — not just "price is near a   |
//| zone", which was the pre-fix bug.                                 |
//+------------------------------------------------------------------+
ENUM_SETUP_TYPE DetectM5Confirmation(const string symbol, const ENUM_TREND_DIRECTION direction,
                                      const Zone &zone, const int lookbackBars)
  {
   double close[], low[], high[], open[];
   ArraySetAsSeries(close, true);
   ArraySetAsSeries(low, true);
   ArraySetAsSeries(high, true);
   ArraySetAsSeries(open, true);

   if(CopyClose(symbol, PERIOD_M5, 0, lookbackBars, close) <= 0)
      return SETUP_NONE;
   CopyLow(symbol, PERIOD_M5, 0, lookbackBars, low);
   CopyHigh(symbol, PERIOD_M5, 0, lookbackBars, high);
   CopyOpen(symbol, PERIOD_M5, 0, lookbackBars, open);

   bool wasInsideZone = false;
   for(int i = 1; i < lookbackBars; i++)
      if(low[i] <= zone.priceHigh && high[i] >= zone.priceLow)
        {
         wasInsideZone = true;
         break;
        }
   if(!wasInsideZone)
      return SETUP_NONE;

   double lastClose = close[0];
   double lastLow = low[0], lastHigh = high[0], lastOpen = open[0];

   if(direction == TREND_BULLISH)
     {
      bool closedBackAbove = lastClose > zone.priceHigh && lastOpen <= zone.priceHigh;
      bool rejectionWick = lastLow < zone.priceLow && lastClose > zone.priceLow;
      if(closedBackAbove) return SETUP_PULLBACK;
      if(rejectionWick)   return SETUP_REJECTION;
     }
   else if(direction == TREND_BEARISH)
     {
      bool closedBackBelow = lastClose < zone.priceLow && lastOpen >= zone.priceLow;
      bool rejectionWick = lastHigh > zone.priceHigh && lastClose < zone.priceHigh;
      if(closedBackBelow) return SETUP_PULLBACK;
      if(rejectionWick)   return SETUP_REJECTION;
     }

   return SETUP_NONE;
  }

//+------------------------------------------------------------------+
//| Build a scored candidate for one direction, or return false if it |
//| fails any gate (no zone proximity, no M5 confirmation, insufficient|
//| room-to-target, etc). blockLines explains why when it fails.      |
//+------------------------------------------------------------------+
bool BuildCandidate(const string symbol, const ENUM_TREND_DIRECTION direction,
                     const MtfSnapshot &mtf, const Zone &zones[], const double price,
                     const double atr, Candidate &outCandidate, string &blockLines[])
  {
   ArrayResize(blockLines, 0);
   ENUM_ZONE_TYPE relevantZoneType = (direction == TREND_BULLISH) ? ZONE_SUPPORT : ZONE_RESISTANCE;
   ENUM_ZONE_TYPE opposingZoneType = (direction == TREND_BULLISH) ? ZONE_RESISTANCE : ZONE_SUPPORT;

   Zone nearZone;
   double maxDistance = atr * (CFG_ZONE_TOLERANCE_ATR + 1.0);
   if(!FindNearestZone(zones, relevantZoneType, price, maxDistance, nearZone))
     {
      int n = ArraySize(blockLines);
      ArrayResize(blockLines, n + 1);
      blockLines[n] = "no zone within proximity tolerance";
      return false;
     }

   ENUM_SETUP_TYPE setup = DetectM5Confirmation(symbol, direction, nearZone, 20);
   if(setup == SETUP_NONE)
     {
      int n = ArraySize(blockLines);
      ArrayResize(blockLines, n + 1);
      blockLines[n] = "no M5 pullback/rejection confirmation";
      return false;
     }

   double slBuffer = atr * CFG_ATR_SL_BUFFER_MULT;
   double entry = price;
   double sl, tp;

   if(direction == TREND_BULLISH)
     {
      sl = nearZone.priceLow - slBuffer;
      double riskDistance = entry - sl;
      tp = entry + riskDistance * CFG_MIN_RR;
     }
   else
     {
      sl = nearZone.priceHigh + slBuffer;
      double riskDistance = sl - entry;
      tp = entry - riskDistance * CFG_MIN_RR;
     }

   Zone opposingZone;
   bool hasOpposing = FindNearestZone(zones, opposingZoneType, price, DBL_MAX, opposingZone);
   if(hasOpposing)
     {
      bool blocksRoom = (direction == TREND_BULLISH) ? (opposingZone.priceLow < tp)
                                                       : (opposingZone.priceHigh > tp);
      if(blocksRoom)
        {
         int n = ArraySize(blockLines);
         ArrayResize(blockLines, n + 1);
         blockLines[n] = "nearer opposing zone blocks 2R room-to-target";
         return false;
        }
     }

   outCandidate.symbol = symbol;
   outCandidate.direction = direction;
   outCandidate.setup = setup;
   outCandidate.mtf = mtf;
   outCandidate.nearestZone = nearZone;
   outCandidate.entry = entry;
   outCandidate.sl = sl;
   outCandidate.tp = tp;
   outCandidate.atr = atr;
   outCandidate.ts = TimeCurrent();
   return true;
  }

//+------------------------------------------------------------------+
//| Rule score. Each timeframe contributes only to its own direction  |
//| (TrendEngine.DirectionalBonus already enforces that), plus a zone |
//| quality term and a volatility-regime term (v1.2.0: ATR quality    |
//| ratio only; the full multi-input Regime Engine is v1.3).          |
//+------------------------------------------------------------------+
void ComputeScore(const MtfSnapshot &mtf, const double atrQualityRatio, const int zoneTouches,
                   ScoreBreakdown &score)
  {
   ArrayResize(score.explanationLines, 0);

   double longScore = 0.0, shortScore = 0.0;

   double h4Long = DirectionalBonus(mtf.h4, TREND_BULLISH);
   double h4Short = DirectionalBonus(mtf.h4, TREND_BEARISH);
   double h1Long = DirectionalBonus(mtf.h1, TREND_BULLISH);
   double h1Short = DirectionalBonus(mtf.h1, TREND_BEARISH);
   double m15Long = DirectionalBonus(mtf.m15, TREND_BULLISH);
   double m15Short = DirectionalBonus(mtf.m15, TREND_BEARISH);

   longScore  = h4Long * 0.30 + h1Long * 0.35 + m15Long * 0.20;
   shortScore = h4Short * 0.30 + h1Short * 0.35 + m15Short * 0.20;

   double zoneQuality = MathMin(zoneTouches, 5) * 2.0; // [ASSUMED] weighting
   double volatilityTerm = MathMax(0.0, MathMin(10.0, (atrQualityRatio - 1.0) * 10.0));

   longScore  += zoneQuality + volatilityTerm;
   shortScore += zoneQuality + volatilityTerm;

   score.longScore = MathMin(longScore, 100.0);
   score.shortScore = MathMin(shortScore, 100.0);
  }
