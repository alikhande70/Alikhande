#pragma once
#include "../Domain/Models.mqh"
#include "../Core/Config.mqh"
#include "../Data/IndicatorCache.mqh"

// Structural supply/demand zones from confirmed swing pivots.
//
// Two corrections against v1.1.0:
//
// 1. Zones are TYPED. v1.1.0 merged any two pivots whose ATR-scaled bands
//    overlapped, regardless of whether they came from swing highs or swing
//    lows, and incremented one shared `touches` counter. A band containing
//    three highs and three lows scored as six touches, and `touches` feeds
//    `quality`, which feeds the signal score. Supply and demand are now
//    separate populations and only merge with their own kind.
//
// 2. Zones are found relative to *price*, not relative to a strict inequality
//    against the current quote. The consumer decides whether price is above,
//    below, or inside a zone — being inside one is the pullback moment the
//    strategy exists to catch, and v1.1.0's nearest-zone search discarded
//    exactly that case.
//
// Pivot confirmation is lagged by design: a swing high at bar i is only
// confirmed once `right` further bars have closed without exceeding it, and
// `confirmation_time` records when that became knowable. Using the pivot's own
// timestamp would be look-ahead.

class AS_ZoneEngine
  {
private:
   AS_IndicatorCache *m_indicators;

   // Merge a pivot into an existing same-type zone whose band contains its
   // centre, or append it as a new zone.
   void Absorb(AS_Zone &zones[], const AS_Zone &pivot)
     {
      const int count = ArraySize(zones);
      for(int i = 0; i < count; i++)
        {
         if(zones[i].type != pivot.type)
            continue;
         if(pivot.center < zones[i].low || pivot.center > zones[i].high)
            continue;

         zones[i].low     = MathMin(zones[i].low, pivot.low);
         zones[i].high    = MathMax(zones[i].high, pivot.high);
         zones[i].center  = (zones[i].low + zones[i].high) / 2.0;
         zones[i].touches++;
         zones[i].quality = MathMin(100.0, zones[i].quality + 10.0);
         // Keep the most recent confirmation: a level retested last week is
         // more relevant than the same level from six months ago.
         if(pivot.confirmation_time > zones[i].confirmation_time)
            zones[i].confirmation_time = pivot.confirmation_time;
         return;
        }

      ArrayResize(zones, count + 1);
      zones[count] = pivot;
     }

public:
   AS_ZoneEngine(void) { m_indicators = NULL; }

   void Attach(AS_IndicatorCache &cache) { m_indicators = GetPointer(cache); }

   int Build(const string symbol, const ENUM_TIMEFRAMES tf, const int bars,
             const int left, const int right, const double atr_fraction,
             AS_Zone &zones[])
     {
      ArrayResize(zones, 0);
      if(m_indicators == NULL || bars < 50 || left < 1 || right < 1)
         return 0;

      // Start at shift 1: bar 0 is still forming and cannot host a confirmed
      // pivot.
      MqlRates rates[];
      ArraySetAsSeries(rates, true);
      if(CopyRates(symbol, tf, 1, bars, rates) != bars)
         return 0;

      const int atr_handle = m_indicators.Handle(symbol, tf, AS_IND_ATR, 14);
      if(atr_handle == INVALID_HANDLE)
         return 0;

      double atr[];
      if(!m_indicators.CopyClosed(atr_handle, 0, bars, atr))
         return 0;
      // CopyClosed is chronological; rates is series-indexed. Flip the ATR
      // window so atr_series[i] lines up with rates[i].
      double atr_series[];
      ArrayResize(atr_series, bars);
      for(int i = 0; i < bars; i++)
         atr_series[i] = atr[bars - 1 - i];

      const double point = SymbolInfoDouble(symbol, SYMBOL_POINT);
      if(point <= 0.0)
         return 0;

      // Series indexing: rates[i+k] is older than rates[i], rates[i-k] newer.
      // The loop bounds keep both neighbourhoods inside the copied window.
      for(int i = right; i < bars - left; i++)
        {
         bool is_high = true;
         bool is_low  = true;

         for(int k = 1; k <= left; k++)
           {
            if(rates[i].high <= rates[i + k].high) is_high = false;
            if(rates[i].low  >= rates[i + k].low)  is_low  = false;
           }
         for(int k = 1; k <= right; k++)
           {
            if(rates[i].high < rates[i - k].high) is_high = false;
            if(rates[i].low  > rates[i - k].low)  is_low  = false;
           }

         if(!is_high && !is_low)
            continue;

         // A single bar can be both the local high and the local low of a very
         // quiet neighbourhood. Emitting it as both would let one bar inflate
         // two zones, so an ambiguous pivot is discarded.
         if(is_high && is_low)
            continue;

         const double width = MathMax(atr_series[i] * atr_fraction, point * 5.0);
         const double price = is_high ? rates[i].high : rates[i].low;

         AS_Zone pivot;
         ZeroMemory(pivot);
         pivot.type              = is_high ? AS_ZONE_SUPPLY : AS_ZONE_DEMAND;
         pivot.timeframe         = tf;
         pivot.center            = price;
         pivot.low               = price - width;
         pivot.high              = price + width;
         pivot.pivot_time        = rates[i].time;
         // Knowable only once the confirming bar closed.
         pivot.confirmation_time = rates[i - right].time + PeriodSeconds(tf);
         pivot.touches           = 1;
         pivot.quality           = 30.0;
         pivot.valid             = true;
         pivot.broken            = false;
         pivot.id                = StringFormat("%s_%d_%d_%I64d", symbol, (int)tf,
                                                (int)pivot.type, (long)rates[i].time);
         Absorb(zones, pivot);
        }

      return ArraySize(zones);
     }
  };

// ---------------------------------------------------------------- lookups
//
// These are free functions rather than engine methods because they are pure
// queries over an already-built zone set, and the signal engine needs several
// different views of the same set.

// Nearest zone of `type` whose centre is within `max_distance` of `price`.
// Unlike v1.1.0 this does NOT require the zone to sit entirely on one side of
// the quote, so a zone price is currently inside remains findable.
bool AS_FindNearestZone(const AS_Zone &zones[], const ENUM_AS_ZONE_TYPE type,
                        const double price, const double max_distance,
                        int &index)
  {
   index = -1;
   double best = DBL_MAX;
   const int count = ArraySize(zones);

   for(int i = 0; i < count; i++)
     {
      if(!zones[i].valid || zones[i].broken || zones[i].type != type)
         continue;
      const double distance = MathAbs(price - zones[i].center);
      if(distance > max_distance || distance >= best)
         continue;
      best = distance;
      index = i;
     }
   return index >= 0;
  }

// Where price sits relative to a zone.
//
// An explicit three-way relation rather than a pair of booleans. The boolean
// form quietly conflates two different situations — "price is not inside the
// zone" and "there is no usable zone" — and that conflation is what produced
// v1.1.0's blindness at the entry trigger. Making UNAVAILABLE its own answer
// forces every caller to decide what to do about it.
ENUM_AS_ZONE_RELATION AS_ZoneRelation(const AS_Zone &zone, const double price)
  {
   if(!zone.valid || zone.broken || zone.low <= 0.0 || zone.high <= 0.0
      || zone.low > zone.high)
      return AS_ZONE_REL_UNAVAILABLE;
   if(price < zone.low)
      return AS_ZONE_REL_BELOW;
   if(price > zone.high)
      return AS_ZONE_REL_ABOVE;
   return AS_ZONE_REL_INSIDE;
  }

// True when `price` sits inside the zone's band.
bool AS_PriceInsideZone(const AS_Zone &zone, const double price)
  {
   return AS_ZoneRelation(zone, price) == AS_ZONE_REL_INSIDE;
  }

// A zone can only anchor a trade in the direction it supports: demand anchors
// longs, supply anchors shorts. Stated once here rather than re-derived at each
// call site, where getting it backwards is silent and expensive.
bool AS_ZoneAnchors(const AS_Zone &zone, const ENUM_AS_DIRECTION direction)
  {
   if(!zone.valid || zone.broken)
      return false;
   if(direction == AS_DIR_LONG)
      return zone.type == AS_ZONE_DEMAND;
   if(direction == AS_DIR_SHORT)
      return zone.type == AS_ZONE_SUPPLY;
   return false;
  }

string AS_ZoneRelationName(const ENUM_AS_ZONE_RELATION relation)
  {
   switch(relation)
     {
      case AS_ZONE_REL_BELOW:  return "BELOW";
      case AS_ZONE_REL_INSIDE: return "INSIDE";
      case AS_ZONE_REL_ABOVE:  return "ABOVE";
     }
   return "UNAVAILABLE";
  }

// Nearest zone of `type` strictly beyond `price` in the given direction —
// used to check whether an opposing level blocks the road to target.
bool AS_FindZoneBeyond(const AS_Zone &zones[], const ENUM_AS_ZONE_TYPE type,
                       const double price, const bool above, int &index)
  {
   index = -1;
   double best = DBL_MAX;
   const int count = ArraySize(zones);

   for(int i = 0; i < count; i++)
     {
      if(!zones[i].valid || zones[i].broken || zones[i].type != type)
         continue;
      const double edge = above ? zones[i].low : zones[i].high;
      if(above && edge <= price) continue;
      if(!above && edge >= price) continue;
      const double distance = MathAbs(edge - price);
      if(distance >= best)
         continue;
      best = distance;
      index = i;
     }
   return index >= 0;
  }
