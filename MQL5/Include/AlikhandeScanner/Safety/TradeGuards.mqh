//+------------------------------------------------------------------+
//| TradeGuards.mqh                                                    |
//| Per-trade safety checks that gate DemoExecution, independent of   |
//| RiskPlanner's sizing math: preview expiry and price drift.         |
//+------------------------------------------------------------------+
#property strict

struct PreviewGuardResult
  {
   bool   passed;
   string reason;
  };

//+------------------------------------------------------------------+
//| A previewed plan is only executable within `expirySeconds` of when|
//| it was shown, and only if price hasn't drifted more than          |
//| `maxDriftAtr` * ATR from the previewed entry — both required per  |
//| docs/v1.1.0_ACCEPTANCE_TESTS.md "Risk Gate".                       |
//+------------------------------------------------------------------+
PreviewGuardResult CheckPreviewGuard(const datetime previewedAt, const int expirySeconds,
                                      const double previewedEntry, const double currentPrice,
                                      const double atr, const double maxDriftAtr)
  {
   PreviewGuardResult r;
   r.passed = true;
   r.reason = "";

   if(TimeCurrent() - previewedAt > expirySeconds)
     {
      r.passed = false;
      r.reason = "preview expired";
      return r;
     }

   if(atr > 0.0)
     {
      double driftAtr = MathAbs(currentPrice - previewedEntry) / atr;
      if(driftAtr > maxDriftAtr)
        {
         r.passed = false;
         r.reason = StringFormat("price drifted %.2f ATR (max %.2f)", driftAtr, maxDriftAtr);
         return r;
        }
     }

   return r;
  }

//+------------------------------------------------------------------+
//| Alert-only mode blocks order sending outright — this is the last  |
//| gate before OrderPreflight/OrderSend, never bypassable by config  |
//| drift elsewhere in the pipeline.                                   |
//+------------------------------------------------------------------+
bool IsOrderSendBlocked(const bool alertOnlyMode, const bool isRealAccount)
  {
   if(isRealAccount)
      return true; // real-account execution is not approved, full stop
   if(alertOnlyMode)
      return true;
   return false;
  }
