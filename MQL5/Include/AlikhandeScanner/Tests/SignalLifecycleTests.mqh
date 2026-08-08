//+------------------------------------------------------------------+
//| SignalLifecycleTests.mqh                                          |
//| Pure state-machine tests — no DB, no chart context required, so   |
//| these can run from any Script host.                                |
//+------------------------------------------------------------------+
#property strict
#include "TestFramework.mqh"
#include "../Domain/SignalLifecycle.mqh"

void RunSignalLifecycleTests()
  {
   TestAssertTrue(SignalTransitionAllowed(SIGNAL_CANDIDATE, SIGNAL_CONFIRMED),
      "CANDIDATE -> CONFIRMED allowed");
   TestAssertTrue(SignalTransitionAllowed(SIGNAL_CONFIRMED, SIGNAL_PREVIEWED),
      "CONFIRMED -> PREVIEWED allowed");
   TestAssertTrue(SignalTransitionAllowed(SIGNAL_PREVIEWED, SIGNAL_ACTIVE),
      "PREVIEWED -> ACTIVE allowed");
   TestAssertTrue(SignalTransitionAllowed(SIGNAL_ACTIVE, SIGNAL_TP),
      "ACTIVE -> TP allowed");

   TestAssertTrue(!SignalTransitionAllowed(SIGNAL_CANDIDATE, SIGNAL_ACTIVE),
      "CANDIDATE -> ACTIVE must be rejected (skips CONFIRMED/PREVIEWED)");
   TestAssertTrue(!SignalTransitionAllowed(SIGNAL_TP, SIGNAL_ACTIVE),
      "terminal state TP cannot transition anywhere");
   TestAssertTrue(!SignalTransitionAllowed(SIGNAL_SL, SIGNAL_CONFIRMED),
      "terminal state SL cannot transition anywhere");

   TestAssertTrue(SignalStateIsTerminal(SIGNAL_TP), "TP is terminal");
   TestAssertTrue(SignalStateIsTerminal(SIGNAL_AMBIGUOUS), "AMBIGUOUS is terminal");
   TestAssertTrue(!SignalStateIsTerminal(SIGNAL_CANDIDATE), "CANDIDATE is not terminal");

   TestAssertEquals(SignalStateToString(SIGNAL_CONFIRMED), "CONFIRMED",
      "state-to-string round trip");
  }
