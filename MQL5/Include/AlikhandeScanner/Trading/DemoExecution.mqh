//+------------------------------------------------------------------+
//| DemoExecution.mqh                                                  |
//| The only execution path in this codebase. Real-account execution  |
//| is not approved (docs/v1.1.0_README.md limitations) — this module |
//| refuses outright on a non-demo account, independent of any other  |
//| config. Routes through TradeGuards -> OrderPreflight ->            |
//| TradeRequestTracker so every send is idempotent and reconciled.    |
//+------------------------------------------------------------------+
#property strict
#include "../Safety/TradeGuards.mqh"
#include "../Execution/OrderPreflight.mqh"
#include "../Domain/SignalLifecycle.mqh"

struct DemoExecutionResult
  {
   bool   submitted;
   string reason;
   string requestId;
  };

bool IsDemoAccount()
  {
   return (ENUM_ACCOUNT_TRADE_MODE)AccountInfoInteger(ACCOUNT_TRADE_MODE) == ACCOUNT_TRADE_MODE_DEMO;
  }

//+------------------------------------------------------------------+
//| Attempt to execute a previewed, user-confirmed signal. Every gate |
//| is re-checked here even if it was already checked earlier in the  |
//| pipeline — a plan can sit in PREVIEWED state for a while, and      |
//| nothing about market conditions is assumed still true.             |
//+------------------------------------------------------------------+
DemoExecutionResult ExecuteDemoTrade(const string symbol, const ENUM_TREND_DIRECTION direction,
                                      const double lot, const double previewedEntry,
                                      const double sl, const double tp,
                                      const datetime previewedAt, const int previewExpirySeconds,
                                      const double maxDriftAtr, const double atr,
                                      const bool alertOnlyMode, const string planId,
                                      const int attempt)
  {
   DemoExecutionResult result;
   result.submitted = false;

   if(IsOrderSendBlocked(alertOnlyMode, !IsDemoAccount()))
     {
      result.reason = !IsDemoAccount() ? "real-account execution is not approved"
                                        : "alert-only mode";
      return result;
     }

   MqlTick tick;
   if(!SymbolInfoTick(symbol, tick))
     {
      result.reason = "no live tick";
      return result;
     }
   double currentPrice = (direction == TREND_BULLISH) ? tick.ask : tick.bid;

   PreviewGuardResult guard = CheckPreviewGuard(previewedAt, previewExpirySeconds,
                                                 previewedEntry, currentPrice, atr, maxDriftAtr);
   if(!guard.passed)
     {
      result.reason = guard.reason;
      return result;
     }

   ENUM_ORDER_TYPE orderType = (direction == TREND_BULLISH) ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;
   PreflightResult preflight = RunOrderPreflight(symbol, orderType, lot, currentPrice, sl, tp);
   if(!preflight.passed)
     {
      result.reason = preflight.failReason;
      return result;
     }

   string requestId = BuildRequestId(planId, attempt);
   bool sent = SubmitPreflightedOrder(symbol, orderType, lot, sl, tp, requestId, planId);

   result.submitted = sent;
   result.requestId = requestId;
   result.reason = sent ? "" : "OrderSend rejected — see trade_requests.retcode";
   return result;
  }
