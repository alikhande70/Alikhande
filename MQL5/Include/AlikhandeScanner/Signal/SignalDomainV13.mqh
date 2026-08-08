#pragma once
#include "../Domain/Enums.mqh"

enum ENUM_AS_ZONE_KIND
  {
   AS_ZONE_DEMAND = 0,
   AS_ZONE_SUPPLY = 1
  };

enum ENUM_AS_ZONE_RELATION
  {
   AS_ZONE_BELOW = -1,
   AS_ZONE_INSIDE = 0,
   AS_ZONE_ABOVE = 1,
   AS_ZONE_UNAVAILABLE = 2
  };

struct AS_TypedZone
  {
   string id;
   string symbol;
   ENUM_TIMEFRAMES timeframe;
   ENUM_AS_ZONE_KIND kind;
   double low;
   double high;
   double center;
   double quality;
   int touches;
   datetime pivot_time;
   datetime confirmation_time;
   bool broken;
   bool valid;
  };

struct AS_StructuralCandidateV13
  {
   string candidate_id;
   string symbol;
   ENUM_AS_DIRECTION direction;
   ENUM_AS_SETUP_TYPE setup;
   string anchor_zone_id;
   double anchor_zone_low;
   double anchor_zone_high;
   double anchor_zone_quality;
   double structural_atr;
   double structural_score;
   datetime confirmation_bar_time;
   datetime expires_at;
   string reasons;
   bool valid;
  };

struct AS_LiveValidationV13
  {
   string candidate_id;
   string symbol;
   ENUM_AS_DIRECTION direction;
   ENUM_AS_ZONE_RELATION zone_relation;
   double bid;
   double ask;
   double entry;
   double stop_loss;
   double take_profit;
   double risk_distance;
   double live_score;
   string reasons;
   string veto_codes;
   bool tradable;
   datetime evaluated_at;
  };
