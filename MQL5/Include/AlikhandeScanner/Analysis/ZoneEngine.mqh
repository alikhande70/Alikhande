//+------------------------------------------------------------------+
//| ZoneEngine.mqh                                                     |
//| H1 support/resistance zones from confirmed swing pivots. A pivot  |
//| is confirmed once `confirmBars` bars have closed on both sides    |
//| with lower/higher highs-lows — ConfirmationTime is stamped as the |
//| CLOSE time of the confirming bar (not the pivot bar itself), per  |
//| docs/v1.1.0_ACCEPTANCE_TESTS.md "Logic Gate".                     |
//+------------------------------------------------------------------+
#property strict
#include "../Domain/Models.mqh"

#define ZONE_MAX_TRACKED 32

//+------------------------------------------------------------------+
//| Scans the last `lookbackBars` H1 bars for confirmed swing highs/  |
//| lows and returns them as zones. `confirmBars` bars on each side   |
//| of the pivot must be less extreme for it to count as confirmed.   |
//+------------------------------------------------------------------+
int FindZones(const string symbol, const ENUM_TIMEFRAMES tf, const int lookbackBars,
              const int confirmBars, Zone &zones[])
  {
   ArrayResize(zones, 0);

   double highs[], lows[];
   datetime times[];
   ArraySetAsSeries(highs, true);
   ArraySetAsSeries(lows, true);
   ArraySetAsSeries(times, true);

   int copied = CopyHigh(symbol, tf, 0, lookbackBars, highs);
   CopyLow(symbol, tf, 0, lookbackBars, lows);
   CopyTime(symbol, tf, 0, lookbackBars, times);
   if(copied < (2 * confirmBars + 1))
      return 0;

   int count = 0;
   for(int i = confirmBars; i < lookbackBars - confirmBars && count < ZONE_MAX_TRACKED; i++)
     {
      bool isSwingHigh = true, isSwingLow = true;
      for(int k = 1; k <= confirmBars; k++)
        {
         if(highs[i - k] >= highs[i] || highs[i + k] >= highs[i])
            isSwingHigh = false;
         if(lows[i - k] <= lows[i] || lows[i + k] <= lows[i])
            isSwingLow = false;
        }

      if(isSwingHigh)
        {
         ArrayResize(zones, count + 1);
         zones[count].type = ZONE_RESISTANCE;
         zones[count].priceHigh = highs[i];
         zones[count].priceLow  = highs[i]; // pivot zones start as a single price; width added below
         // Confirming bar is `confirmBars` bars closer to "now" than the pivot
         // (i - confirmBars, since index 0 is most recent) — its CLOSE time,
         // i.e. the open time of the NEXT bar toward the present.
         int confirmIdx = MathMax(i - confirmBars - 1, 0);
         zones[count].confirmationTime = times[confirmIdx];
         zones[count].touches = 1;
         count++;
        }
      else if(isSwingLow)
        {
         ArrayResize(zones, count + 1);
         zones[count].type = ZONE_SUPPORT;
         zones[count].priceHigh = lows[i];
         zones[count].priceLow  = lows[i];
         int confirmIdx = MathMax(i - confirmBars - 1, 0);
         zones[count].confirmationTime = times[confirmIdx];
         zones[count].touches = 1;
         count++;
        }
     }

   return count;
  }

//+------------------------------------------------------------------+
//| Widen each zone by an ATR-scaled buffer so "proximity to zone"    |
//| checks aren't pixel-exact against a single historical price.      |
//+------------------------------------------------------------------+
void ApplyZoneAtrBuffer(Zone &zones[], const double atr, const double bufferMult)
  {
   double buffer = atr * bufferMult;
   for(int i = 0; i < ArraySize(zones); i++)
     {
      zones[i].priceHigh += buffer;
      zones[i].priceLow  -= buffer;
     }
  }

//+------------------------------------------------------------------+
//| Nearest zone of the requested type to `price`, or a zero-filled   |
//| zone with touches=0 if none exist within `maxDistance`.           |
//+------------------------------------------------------------------+
bool FindNearestZone(const Zone &zones[], const ENUM_ZONE_TYPE type, const double price,
                      const double maxDistance, Zone &outZone)
  {
   double bestDist = DBL_MAX;
   bool found = false;

   for(int i = 0; i < ArraySize(zones); i++)
     {
      if(zones[i].type != type)
         continue;
      double mid = (zones[i].priceHigh + zones[i].priceLow) / 2.0;
      double dist = MathAbs(price - mid);
      if(dist < bestDist && dist <= maxDistance)
        {
         bestDist = dist;
         outZone = zones[i];
         found = true;
        }
     }
   return found;
  }
