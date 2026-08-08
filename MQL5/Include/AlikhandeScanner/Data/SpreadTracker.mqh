#pragma once
#include "../Domain/Enums.mqh"
#include "../Core/Config.mqh"

// Rolling spread sample per symbol.
//
// Classification is relative to the symbol's own median rather than an absolute
// point threshold, because "30 points" means something completely different on
// XAUUSD than on EURUSD. The percentile is exposed as well — the regime engine
// wants the distributional position, not just the bucket.

class AS_SpreadTracker
  {
private:
   double m_samples[];
   int    m_capacity;
   int    m_count;
   int    m_position;

public:
   AS_SpreadTracker(void)
     {
      m_capacity = AS_SPREAD_SAMPLE_CAPACITY;
      m_count = 0;
      m_position = 0;
      ArrayResize(m_samples, m_capacity);
      ArrayInitialize(m_samples, 0.0);
     }

   int Count(void) const { return m_count; }

   void Add(const double value)
     {
      if(value <= 0.0)
         return;
      m_samples[m_position] = value;
      m_position = (m_position + 1) % m_capacity;
      if(m_count < m_capacity)
         m_count++;
     }

   double Median(void) const
     {
      if(m_count == 0)
         return 0.0;
      double sorted[];
      ArrayResize(sorted, m_count);
      for(int i = 0; i < m_count; i++)
         sorted[i] = m_samples[i];
      ArraySort(sorted);
      if((m_count % 2) == 1)
         return sorted[m_count / 2];
      return (sorted[m_count / 2 - 1] + sorted[m_count / 2]) / 2.0;
     }

   // Fraction of observed samples at or below `value`, in 0..1.
   double Percentile(const double value) const
     {
      if(m_count == 0)
         return 0.5;
      int below = 0;
      for(int i = 0; i < m_count; i++)
         if(m_samples[i] <= value)
            below++;
      return (double)below / (double)m_count;
     }

   // `ratio` and `percentile` are outputs; both are zeroed while warming up so
   // a caller can never mistake an unwarmed tracker for a normal spread.
   ENUM_AS_SPREAD_STATE Classify(const double current, const int minimum_samples,
                                  double &ratio, double &percentile) const
     {
      ratio = 0.0;
      percentile = 0.0;
      if(m_count < minimum_samples)
         return AS_SPREAD_WARMING_UP;

      const double median = Median();
      if(median <= 0.0)
         return AS_SPREAD_WARMING_UP;

      ratio = current / median;
      percentile = Percentile(current);

      if(ratio < AS_SPREAD_NORMAL_MAX_RATIO)   return AS_SPREAD_NORMAL;
      if(ratio < AS_SPREAD_ELEVATED_MAX_RATIO) return AS_SPREAD_ELEVATED;
      if(ratio < AS_SPREAD_HIGH_MAX_RATIO)     return AS_SPREAD_HIGH;
      return AS_SPREAD_EXTREME;
     }
  };
