//+------------------------------------------------------------------+
//| RunAllTests.mq5                                                   |
//| Runs the dependency-free unit tests (Include/.../Tests/*.mqh).    |
//| DB-backed and acceptance-level tests are covered separately by    |
//| docs/ACCEPTANCE_TESTS.md against a live/demo terminal.            |
//+------------------------------------------------------------------+
#property copyright "Alikhande"
#property version   "1.20"
#property script_show_inputs

#include <AlikhandeScanner/Tests/TestFramework.mqh>
#include <AlikhandeScanner/Tests/SignalLifecycleTests.mqh>
#include <AlikhandeScanner/Tests/PortfolioRiskTests.mqh>
#include <AlikhandeScanner/Tests/ExecutionTests.mqh>

void OnStart()
  {
   RunSignalLifecycleTests();
   RunPortfolioRiskTests();
   RunExecutionTests();
   TestSummary();
  }
