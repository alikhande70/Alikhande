//+------------------------------------------------------------------+
//| Statistics.mqh                                                     |
//| v1.2.0 scope: sample count only, read from the `outcomes` table.  |
//| Historical Win Rate / Probability / Wilson CI / Expectancy are    |
//| v1.3 (docs/ROADMAP.md) — this module explicitly returns            |
//| "insufficient data" rather than fabricating a number, per the      |
//| project's stated principle (docs/ARCHITECTURE_V1.2.md).            |
//+------------------------------------------------------------------+
#property strict
#include "../Storage/Database.mqh"

#define STATISTICS_MIN_SAMPLE 30 // [ASSUMED] below this, no probability is shown at all

struct OutcomeSampleSummary
  {
   int    sampleCount;
   int    winCount;
   bool   sufficientData;
  };

OutcomeSampleSummary GetOutcomeSampleSummary(const string symbol, const string setup)
  {
   OutcomeSampleSummary s;
   s.sampleCount = 0;
   s.winCount = 0;
   s.sufficientData = false;

   if(!AlikhandeDbIsOpen())
      return s;

   int stmt = DatabasePrepare(g_AlikhandeDbHandle,
      "SELECT o.result FROM outcomes o "
      "JOIN signals sg ON sg.signal_id = o.signal_id "
      "WHERE sg.symbol = ? AND sg.setup = ? AND o.result IN ('TP','SL')");
   if(stmt == INVALID_HANDLE)
      return s;

   DatabaseBind(stmt, 0, symbol);
   DatabaseBind(stmt, 1, setup);

   while(DatabaseRead(stmt))
     {
      string result;
      DatabaseColumnText(stmt, 0, result);
      s.sampleCount++;
      if(result == "TP")
         s.winCount++;
     }
   DatabaseFinalize(stmt);

   s.sufficientData = (s.sampleCount >= STATISTICS_MIN_SAMPLE);
   return s;
  }

// Dashboard-facing label — never prints a bare percentage without the
// sample count next to it, and never prints anything at all below the
// minimum sample threshold.
string FormatProbabilityLabel(const OutcomeSampleSummary &s)
  {
   if(!s.sufficientData)
      return StringFormat("insufficient data (%d/%d samples)", s.sampleCount, STATISTICS_MIN_SAMPLE);

   double winRate = (double)s.winCount / (double)s.sampleCount * 100.0;
   return StringFormat("%.0f%% (n=%d) — point estimate, no confidence interval until v1.3",
                        winRate, s.sampleCount);
  }
