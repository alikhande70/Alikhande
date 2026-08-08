//+------------------------------------------------------------------+
//| ExecutionTests.mqh                                                 |
//| Pure-function coverage for the Execution layer. DB-backed          |
//| behavior (TradeRequestCreate idempotency, fill reconciliation)     |
//| needs a live/tester DB context and is covered by acceptance tests  |
//| instead — see docs/ARCHITECTURE_V1.2.md.                          |
//+------------------------------------------------------------------+
#property strict
#include "TestFramework.mqh"
#include "../Execution/TradeRequestTracker.mqh"

void RunExecutionTests()
  {
   TestAssertEquals(ExecStateToString(EXEC_SUBMITTING), "SUBMITTING", "SUBMITTING label");
   TestAssertEquals(ExecStateToString(EXEC_ACCEPTED), "ACCEPTED", "ACCEPTED label");
   TestAssertEquals(ExecStateToString(EXEC_REJECTED), "REJECTED", "REJECTED label");
   TestAssertEquals(ExecStateToString(EXEC_UNKNOWN), "UNKNOWN", "UNKNOWN label");
   TestAssertEquals(ExecStateToString(EXEC_PARTIALLY_FILLED), "PARTIALLY_FILLED",
      "PARTIALLY_FILLED label");
   TestAssertEquals(ExecStateToString(EXEC_FILLED), "FILLED", "FILLED label");

   string id1 = BuildRequestId("plan-abc123", 1);
   string id2 = BuildRequestId("plan-abc123", 2);
   TestAssertEquals(id1, "plan-abc123-req1", "RequestID format, attempt 1");
   TestAssertTrue(id1 != id2, "different attempts produce different RequestIDs (no silent resend collision)");
  }
