#pragma once
#include "../Core/Config.mqh"
#include "../Domain/Models.mqh"
#include "../Persistence/Repositories.mqh"

// Outcome statistics.
//
// The governing rule of this module: a rule score is not a probability, and a
// probability computed from a handful of trades is not evidence. Two guards
// enforce that:
//
//   1. Nothing is reported below AS_MIN_OUTCOME_SAMPLE observations.
//   2. Any reported rate is accompanied by a Wilson interval and the sample
//      size, and callers render all three or none.
//
// v1.1.0 shipped a correct Wilson implementation that nothing ever called, and
// a candidate struct whose has_historical_estimate flag was hardcoded false.
// The maths was right and unreachable; here it is wired to real stored outcomes.

class AS_Statistics
  {
private:
   AS_Repositories *m_repo;

public:
   AS_Statistics(void) { m_repo = NULL; }

   void Attach(AS_Repositories &repo) { m_repo = GetPointer(repo); }

   // Wilson score interval. Preferred over the normal approximation because it
   // stays inside [0,1] and stays honest at small n and at rates near 0 or 1 —
   // exactly the regime a young strategy database lives in.
   static bool Wilson(const int wins, const int total, double &low, double &high)
     {
      low = 0.0;
      high = 0.0;
      if(total <= 0 || wins < 0 || wins > total)
         return false;

      const double z = 1.96;              // 95%
      const double n = (double)total;
      const double p = (double)wins / n;
      const double denominator = 1.0 + z * z / n;
      const double center = (p + z * z / (2.0 * n)) / denominator;
      const double margin = z * MathSqrt((p * (1.0 - p) + z * z / (4.0 * n)) / n) / denominator;

      low  = MathMax(0.0, center - margin);
      high = MathMin(1.0, center + margin);
      return true;
     }

   // Populates the historical fields on a candidate, or leaves
   // has_historical_estimate false when the evidence is insufficient.
   //
   // Outcomes are scoped to the candidate's own rule version: mixing results
   // from before and after a logic change describes a system that never ran.
   bool Enrich(AS_SignalCandidate &s)
     {
      s.has_historical_estimate = false;
      s.historical_win_rate = 0.0;
      s.sample_size = 0;
      s.confidence_low = 0.0;
      s.confidence_high = 0.0;

      if(m_repo == NULL || s.setup == AS_SETUP_NONE)
         return false;

      int wins = 0, total = 0;
      if(!m_repo.OutcomeCounts(s.symbol, (int)s.setup, s.rule_version, wins, total))
         return false;

      s.sample_size = total;
      if(total < AS_MIN_OUTCOME_SAMPLE)
         return false;

      double low = 0.0, high = 0.0;
      if(!Wilson(wins, total, low, high))
         return false;

      s.historical_win_rate = (double)wins / (double)total;
      s.confidence_low = low;
      s.confidence_high = high;
      s.has_historical_estimate = true;
      return true;
     }
  };

// Rendering helper. Centralised so no call site can accidentally print a bare
// percentage without its sample size, or print anything at all below the
// minimum sample.
string AS_FormatProbability(const AS_SignalCandidate &s)
  {
   if(!s.has_historical_estimate)
      return StringFormat("n/a (%d/%d samples)", s.sample_size, AS_MIN_OUTCOME_SAMPLE);
   return StringFormat("%.0f%% [%.0f-%.0f] n=%d",
                       s.historical_win_rate * 100.0,
                       s.confidence_low * 100.0,
                       s.confidence_high * 100.0,
                       s.sample_size);
  }
