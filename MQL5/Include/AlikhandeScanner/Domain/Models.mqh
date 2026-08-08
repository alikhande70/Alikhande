//+------------------------------------------------------------------+
//| Models.mqh                                                         |
//| Plain-data structs shared across the scoring pipeline.            |
//+------------------------------------------------------------------+
#property strict
#include "Enums.mqh"

struct Zone
  {
   ENUM_ZONE_TYPE type;
   double         priceHigh;
   double         priceLow;
   datetime       confirmationTime; // close time of the confirming bar
   int            touches;
  };

struct TrendState
  {
   ENUM_TREND_DIRECTION direction;
   double                strength; // 0..100, own-direction only (see TrendEngine.mqh)
  };

struct MtfSnapshot
  {
   TrendState h4;
   TrendState h1;
   TrendState m15;
   TrendState m5;
  };

struct ScoreBreakdown
  {
   double longScore;
   double shortScore;
   string explanationLines[]; // "+18 H4 trend" style, for the Dashboard Detail tab
   string blockLines[];       // reasons the candidate is not tradable, if any
  };

struct Candidate
  {
   string           symbol;
   ENUM_TREND_DIRECTION direction;
   ENUM_SETUP_TYPE  setup;
   MtfSnapshot      mtf;
   Zone             nearestZone;
   double           entry, sl, tp;
   double           atr;
   double           spread;
   ScoreBreakdown   score;
   datetime         ts;
  };

struct TradePlanInput
  {
   string symbol;
   ENUM_TREND_DIRECTION direction;
   double entry, sl, tp;
   double riskPct;
  };
