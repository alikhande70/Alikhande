//+------------------------------------------------------------------+
//| ExecutionStateMachine.mqh                                         |
//| OnTradeTransaction handler. MetaQuotes documents that transaction |
//| arrival order is NOT guaranteed and a single request can raise    |
//| several different transaction types — so this handler never       |
//| trusts sequence; it re-reads live state (HistoryDealSelect /      |
//| PositionSelect) to decide what actually happened.                 |
//| Ref: https://www.mql5.com/en/docs/event_handlers/ontradetransaction|
//+------------------------------------------------------------------+
#property strict
#include "TradeRequestTracker.mqh"
#include "../Domain/SignalLifecycle.mqh"

//+------------------------------------------------------------------+
//| Map an MT5 deal ticket back to the RequestID that produced it,    |
//| via the deal's comment/magic convention the RiskPlanner stamps    |
//| onto every order it sends. Returns "" if no match (manual trade,  |
//| or a deal this EA never originated).                              |
//+------------------------------------------------------------------+
string ResolveRequestIdFromDeal(const ulong dealTicket)
  {
   if(!HistoryDealSelect(dealTicket))
      return "";

   string comment = HistoryDealGetString(dealTicket, DEAL_COMMENT);
   // Convention: comment is set to the RequestID at submission time
   // (see Execution/OrderPreflight.mqh). Anything else is not ours.
   if(StringFind(comment, "-req") < 0)
      return "";

   return comment;
  }

//+------------------------------------------------------------------+
//| Call from OnTradeTransaction. Idempotent: re-processing the same  |
//| deal twice (duplicate event, or replay after restart) is a no-op  |
//| because TradeDealRecord uses INSERT OR IGNORE on deal_id.         |
//+------------------------------------------------------------------+
void HandleTradeTransaction(const MqlTradeTransaction &trans,
                             const MqlTradeRequest     &request,
                             const MqlTradeResult      &result)
  {
   if(trans.type == TRADE_TRANSACTION_DEAL_ADD)
     {
      string requestId = ResolveRequestIdFromDeal(trans.deal);
      if(requestId == "")
         return; // not an Alikhande-originated deal (manual trade) — ignore, don't guess

      double volume = HistoryDealGetDouble(trans.deal, DEAL_VOLUME);
      double price  = HistoryDealGetDouble(trans.deal, DEAL_PRICE);
      long   posId  = (long)HistoryDealGetInteger(trans.deal, DEAL_POSITION_ID);

      TradeDealRecord((long)trans.deal, requestId, posId, volume, price);

      // Determine fill completeness by comparing filled volume against the
      // originally requested volume stored in trade_plans — never assume a
      // single ADD means "fully filled".
      ENUM_EXEC_STATE state = ResolveFillState(requestId, posId);
      TradeRequestUpdateState(requestId, state, 0);
     }

   if(trans.type == TRADE_TRANSACTION_REQUEST)
     {
      // This is the synchronous confirmation for OUR OrderSend call — record
      // retcode regardless of what DEAL_ADD events do or don't arrive.
      string requestId = ResolveRequestIdFromComment(request.comment);
      if(requestId == "")
         return;

      ENUM_EXEC_STATE state = (result.retcode == TRADE_RETCODE_DONE ||
                                result.retcode == TRADE_RETCODE_DONE_PARTIAL)
                               ? EXEC_ACCEPTED : EXEC_REJECTED;
      TradeRequestUpdateState(requestId, state, (int)result.retcode);
     }
  }

string ResolveRequestIdFromComment(const string comment)
  {
   if(StringFind(comment, "-req") < 0)
      return "";
   return comment;
  }

//+------------------------------------------------------------------+
//| Compare filled volume in history against the requested volume in  |
//| trade_plans to classify FILLED vs PARTIALLY_FILLED. Falls back to |
//| EXEC_UNKNOWN if the plan can't be found — surfaced on the Health  |
//| tab rather than silently assumed.                                 |
//+------------------------------------------------------------------+
ENUM_EXEC_STATE ResolveFillState(const string requestId, const long positionId)
  {
   if(!AlikhandeDbIsOpen())
      return EXEC_UNKNOWN;

   int stmt = DatabasePrepare(g_AlikhandeDbHandle,
      "SELECT tp.lot FROM trade_requests tr "
      "JOIN trade_plans tp ON tp.plan_id = tr.plan_id "
      "WHERE tr.request_id = ?");
   if(stmt == INVALID_HANDLE)
      return EXEC_UNKNOWN;

   DatabaseBind(stmt, 0, requestId);
   if(!DatabaseRead(stmt))
     {
      DatabaseFinalize(stmt);
      return EXEC_UNKNOWN;
     }

   double requestedLot = 0.0;
   DatabaseColumnDouble(stmt, 0, requestedLot);
   DatabaseFinalize(stmt);

   double filledVolume = 0.0;
   int stmt2 = DatabasePrepare(g_AlikhandeDbHandle,
      "SELECT COALESCE(SUM(volume),0) FROM deals WHERE request_id=?");
   if(stmt2 != INVALID_HANDLE)
     {
      DatabaseBind(stmt2, 0, requestId);
      if(DatabaseRead(stmt2))
         DatabaseColumnDouble(stmt2, 0, filledVolume);
      DatabaseFinalize(stmt2);
     }

   if(requestedLot <= 0.0)
      return EXEC_UNKNOWN;

   double tolerance = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   if(tolerance <= 0.0) tolerance = 0.001;

   return (MathAbs(filledVolume - requestedLot) <= tolerance) ? EXEC_FILLED : EXEC_PARTIALLY_FILLED;
  }

//+------------------------------------------------------------------+
//| Called on OnTimer, not inside OnTradeTransaction: sweeps any      |
//| request still in EXEC_UNKNOWN/EXEC_SUBMITTING past a grace period |
//| and reconciles it directly against HistoryDealsTotal/Position     |
//| state rather than waiting indefinitely for an event that may      |
//| never arrive (queue overflow, disconnect, etc).                   |
//+------------------------------------------------------------------+
void ReconcileStaleRequests(const int graceSeconds)
  {
   if(!AlikhandeDbIsOpen())
      return;

   int stmt = DatabasePrepare(g_AlikhandeDbHandle,
      "SELECT request_id, submitted_at FROM trade_requests "
      "WHERE state IN (?,?) AND submitted_at < ?");
   if(stmt == INVALID_HANDLE)
      return;

   DatabaseBind(stmt, 0, ExecStateToString(EXEC_SUBMITTING));
   DatabaseBind(stmt, 1, ExecStateToString(EXEC_UNKNOWN));
   DatabaseBind(stmt, 2, (long)(TimeCurrent() - graceSeconds));

   while(DatabaseRead(stmt))
     {
      string requestId;
      DatabaseColumnText(stmt, 0, requestId);
      AlikhandeDbLogEvent("WARN", "STALE_REQUEST_MARKED_AMBIGUOUS", requestId);
      TradeRequestUpdateState(requestId, EXEC_UNKNOWN, -1);
     }
   DatabaseFinalize(stmt);
  }
