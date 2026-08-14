#pragma once

// Minimal assertion harness for in-terminal tests.
//
// The Python static gate proves structural properties; it cannot evaluate MQL5
// expressions. These tests cover the logic that is pure arithmetic or pure
// state-machine transitions — the parts where being wrong is silent.

class AS_TestRunner
  {
private:
   int m_run;
   int m_failed;
   string m_suite;

public:
   AS_TestRunner(void) { m_run = 0; m_failed = 0; m_suite = ""; }

   void Suite(const string name)
     {
      m_suite = name;
      PrintFormat("--- %s", name);
     }

   void Check(const bool condition, const string label)
     {
      m_run++;
      if(condition)
         PrintFormat("  [ ok ] %s", label);
      else
        {
         m_failed++;
         PrintFormat("  [FAIL] %s", label);
        }
     }

   void CheckClose(const double actual, const double expected,
                   const double tolerance, const string label)
     {
      Check(MathAbs(actual - expected) <= tolerance,
            StringFormat("%s (expected %.6f, got %.6f)", label, expected, actual));
     }

   bool Summary(void)
     {
      PrintFormat("=== %d run, %d failed ===", m_run, m_failed);
      return m_failed == 0;
     }

   int Failed(void) const { return m_failed; }
  };
