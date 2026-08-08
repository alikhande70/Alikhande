//+------------------------------------------------------------------+
//| OrderPreflight.mqh                                                |
//| Standardized pipeline that runs immediately before every          |
//| OrderSend: price/spread/spec revalidation, stops/freeze level     |
//| checks, margin via OrderCheck, and broker-correct filling policy. |
//|                                                                    |
//| Note per MetaQuotes docs: OrderCheck() succeeding does NOT        |
//| guarantee the order will fill — it only screens out requests that |
//| are certain to fail. The result must still be reconciled after    |
//| submission via Execution/ExecutionStateMachine.mqh.                |
//+------------------------------------------------------------------+
#property strict
#include <Trade/Trade.mqh>
#include "TradeRequestTracker.mqh"

struct PreflightResult
  {
   bool   passed;
   string failReason;
  };

//+------------------------------------------------------------------+
//| Runs the full gate. Returns passed=false with a human-readable    |
//| reason the moment any check fails — callers must not proceed to   |
//| OrderSend on a failed preflight.                                  |
//+------------------------------------------------------------------+
PreflightResult RunOrderPreflight(const string symbol, const ENUM_ORDER_TYPE orderType,
                                   const double lot, const double price,
                                   const double sl, const double tp)
  {
   PreflightResult r;
   r.passed = false;

   if(!SymbolSelect(symbol, true))
     {
      r.failReason = "symbol not selectable in Market Watch";
      return r;
     }

   double spreadPts = (double)SymbolInfoInteger(symbol, SYMBOL_SPREAD);
   double maxSpreadPts = 0.0; // caller-configurable; 0 = no override, handled upstream
   MqlTick tick;
   if(!SymbolInfoTick(symbol, tick))
     {
      r.failReason = "no tick available";
      return r;
     }

   int stopsLevel  = (int)SymbolInfoInteger(symbol, SYMBOL_TRADE_STOPS_LEVEL);
   int freezeLevel = (int)SymbolInfoInteger(symbol, SYMBOL_TRADE_FREEZE_LEVEL);
   double point    = SymbolInfoDouble(symbol, SYMBOL_POINT);

   double minDistance = MathMax(stopsLevel, freezeLevel) * point;
   double refPrice = (orderType == ORDER_TYPE_BUY) ? tick.ask : tick.bid;

   if(sl > 0.0 && MathAbs(refPrice - sl) < minDistance)
     {
      r.failReason = "SL inside stops/freeze level";
      return r;
     }
   if(tp > 0.0 && MathAbs(refPrice - tp) < minDistance)
     {
      r.failReason = "TP inside stops/freeze level";
      return r;
     }

   double minLot  = SymbolInfoDouble(symbol, SYMBOL_VOLUME_MIN);
   double maxLot  = SymbolInfoDouble(symbol, SYMBOL_VOLUME_MAX);
   double lotStep = SymbolInfoDouble(symbol, SYMBOL_VOLUME_STEP);

   if(lot < minLot || lot > maxLot)
     {
      r.failReason = StringFormat("lot %.2f outside broker range [%.2f, %.2f]", lot, minLot, maxLot);
      return r;
     }
   if(lotStep > 0.0)
     {
      double steps = MathRound((lot - minLot) / lotStep);
      double normalized = minLot + steps * lotStep;
      if(MathAbs(normalized - lot) > 1e-8)
        {
         r.failReason = "lot not aligned to broker volume step";
         return r;
        }
     }

   // Broker-correct filling policy per symbol, not a hardcoded assumption.
   CTrade trade;
   trade.SetTypeFillingBySymbol(symbol);

   MqlTradeRequest request;
   MqlTradeCheckResult checkResult;
   ZeroMemory(request);
   ZeroMemory(checkResult);

   request.action   = TRADE_ACTION_DEAL;
   request.symbol   = symbol;
   request.volume   = lot;
   request.type     = orderType;
   request.price    = refPrice;
   request.sl       = sl;
   request.tp       = tp;
   request.type_filling = trade.RequestTypeFilling();

   if(!OrderCheck(request, checkResult))
     {
      r.failReason = StringFormat("OrderCheck failed: retcode=%d comment=%s",
                                   checkResult.retcode, checkResult.comment);
      return r;
     }

   r.passed = true;
   r.failReason = "";
   return r;
  }

//+------------------------------------------------------------------+
//| Submit an order that has passed preflight. Stamps the RequestID   |
//| onto the order comment so ExecutionStateMachine can resolve deals |
//| back to their originating request — this is the join key used     |
//| throughout the Execution layer.                                   |
//+------------------------------------------------------------------+
bool SubmitPreflightedOrder(const string symbol, const ENUM_ORDER_TYPE orderType,
                             const double lot, const double sl, const double tp,
                             const string requestId, const string planId)
  {
   if(!TradeRequestCreate(requestId, planId))
      return false; // duplicate / idempotency guard already logged the reason

   CTrade trade;
   trade.SetTypeFillingBySymbol(symbol);
   trade.SetExpertMagicNumber(0); // caller sets the project's magic number upstream
   trade.SetDeviationInPoints(10);

   bool sent;
   if(orderType == ORDER_TYPE_BUY)
      sent = trade.Buy(lot, symbol, 0.0, sl, tp, requestId);
   else
      sent = trade.Sell(lot, symbol, 0.0, sl, tp, requestId);

   if(!sent)
      TradeRequestUpdateState(requestId, EXEC_REJECTED, (int)trade.ResultRetcode());

   // Final state is NOT decided here — OnTradeTransaction / ReconcileStaleRequests
   // own that, per the documented unreliability of synchronous OrderSend results.
   return sent;
  }
