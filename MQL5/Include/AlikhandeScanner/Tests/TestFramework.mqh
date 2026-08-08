//+------------------------------------------------------------------+
//| TestFramework.mqh                                                 |
//| Minimal, dependency-free assert harness (MQL5Unit-style pattern,  |
//| written independently — no code copied, MQL5Unit is MIT-licensed  |
//| so direct reuse would have been fine, but the surface needed here |
//| is tiny). Run via a Script in the Strategy Tester or terminal.    |
//+------------------------------------------------------------------+
#property strict

int g_TestsRun = 0;
int g_TestsFailed = 0;

void TestAssertTrue(const bool condition, const string message)
  {
   g_TestsRun++;
   if(!condition)
     {
      g_TestsFailed++;
      PrintFormat("[FAIL] %s", message);
     }
   else
     {
      PrintFormat("[ OK ] %s", message);
     }
  }

void TestAssertEquals(const string actual, const string expected, const string message)
  {
   TestAssertTrue(actual == expected,
      StringFormat("%s (expected='%s' actual='%s')", message, expected, actual));
  }

void TestAssertEqualsDouble(const double actual, const double expected, const double tolerance,
                             const string message)
  {
   TestAssertTrue(MathAbs(actual - expected) <= tolerance,
      StringFormat("%s (expected=%.6f actual=%.6f)", message, expected, actual));
  }

void TestSummary()
  {
   PrintFormat("==== Alikhande Tests: %d run, %d failed ====", g_TestsRun, g_TestsFailed);
  }
