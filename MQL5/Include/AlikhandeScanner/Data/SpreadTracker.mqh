//+------------------------------------------------------------------+
//| SpreadTracker.mqh                                                  |
//| Tick-staleness detection and a rolling spread sample used both by |
//| the Runtime Gate ("a stale quote blocks candidates") and by the   |
//| v1.3 spread-percentile regime input.                              |
//+------------------------------------------------------------------+
#property strict

#define SPREAD_SAMPLE_SIZE 100

struct SpreadSample
  {
   double values[SPREAD_SAMPLE_SIZE];
   int    count;
   int    nextIndex;
  };

void SpreadSampleReset(SpreadSample &s)
  {
   s.count = 0;
   s.nextIndex = 0;
  }

void SpreadSamplePush(SpreadSample &s, const double spreadPoints)
  {
   s.values[s.nextIndex] = spreadPoints;
   s.nextIndex = (s.nextIndex + 1) % SPREAD_SAMPLE_SIZE;
   if(s.count < SPREAD_SAMPLE_SIZE)
      s.count++;
  }

double SpreadSampleAverage(const SpreadSample &s)
  {
   if(s.count == 0)
      return 0.0;
   double sum = 0.0;
   for(int i = 0; i < s.count; i++)
      sum += s.values[i];
   return sum / s.count;
  }

// Percentile of `value` within the sample (0..1). Used by v1.3's Regime
// Engine input; v1.2.0 only needs the average for the "abnormal spread"
// dashboard label, but this is cheap to have ready now.
double SpreadSamplePercentile(const SpreadSample &s, const double value)
  {
   if(s.count == 0)
      return 0.5;
   int below = 0;
   for(int i = 0; i < s.count; i++)
      if(s.values[i] <= value)
         below++;
   return (double)below / (double)s.count;
  }

bool IsQuoteStale(const string symbol, const int staleSeconds)
  {
   MqlTick tick;
   if(!SymbolInfoTick(symbol, tick))
      return true;
   return (TimeCurrent() - tick.time) > staleSeconds;
  }
