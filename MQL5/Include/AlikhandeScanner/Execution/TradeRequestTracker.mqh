//+------------------------------------------------------------------+
//| TradeRequestTracker.mqh                                           |
//| SignalID -> TradePlanID -> RequestID -> DealID mapping, with      |
//| idempotency so a duplicate OnTradeTransaction event or a restart  |
//| can never submit the same plan twice.                             |
//+------------------------------------------------------------------+
#property strict
#include "../Storage/Database.mqh"

enum ENUM_EXEC_STATE
  {
   EXEC_SUBMITTING,
   EXEC_ACCEPTED,
   EXEC_REJECTED,
   EXEC_UNKNOWN,          // sent, no confirmation yet — must be reconciled
   EXEC_PARTIALLY_FILLED,
   EXEC_FILLED
  };

string ExecStateToString(const ENUM_EXEC_STATE s)
  {
   switch(s)
     {
      case EXEC_SUBMITTING:       return "SUBMITTING";
      case EXEC_ACCEPTED:         return "ACCEPTED";
      case EXEC_REJECTED:         return "REJECTED";
      case EXEC_UNKNOWN:          return "UNKNOWN";
      case EXEC_PARTIALLY_FILLED: return "PARTIALLY_FILLED";
      case EXEC_FILLED:           return "FILLED";
     }
   return "UNKNOWN";
  }

// Deterministic RequestID so a resend of the same plan (e.g. after a restart)
// is recognizable as a duplicate instead of creating a second live order.
string BuildRequestId(const string planId, const int attempt)
  {
   return StringFormat("%s-req%d", planId, attempt);
  }

bool TradeRequestExists(const string requestId)
  {
   if(!AlikhandeDbIsOpen())
      return false;

   int stmt = DatabasePrepare(g_AlikhandeDbHandle,
      "SELECT request_id FROM trade_requests WHERE request_id=?");
   if(stmt == INVALID_HANDLE)
      return false;

   DatabaseBind(stmt, 0, requestId);
   bool found = DatabaseRead(stmt);
   DatabaseFinalize(stmt);
   return found;
  }

bool TradeRequestCreate(const string requestId, const string planId)
  {
   // Idempotency guard: never insert the same request twice.
   if(TradeRequestExists(requestId))
     {
      AlikhandeDbLogEvent("WARN", "DUPLICATE_REQUEST_BLOCKED", requestId);
      return false;
     }

   int stmt = DatabasePrepare(g_AlikhandeDbHandle,
      "INSERT INTO trade_requests(request_id, plan_id, submitted_at, state, retcode) "
      "VALUES(?,?,?,?,NULL)");
   if(stmt == INVALID_HANDLE)
      return false;

   DatabaseBind(stmt, 0, requestId);
   DatabaseBind(stmt, 1, planId);
   DatabaseBind(stmt, 2, (long)TimeCurrent());
   DatabaseBind(stmt, 3, ExecStateToString(EXEC_SUBMITTING));

   bool ok = DatabaseRead(stmt);
   DatabaseFinalize(stmt);
   return ok;
  }

bool TradeRequestUpdateState(const string requestId, const ENUM_EXEC_STATE state,
                              const int retcode)
  {
   int stmt = DatabasePrepare(g_AlikhandeDbHandle,
      "UPDATE trade_requests SET state=?, retcode=? WHERE request_id=?");
   if(stmt == INVALID_HANDLE)
      return false;

   DatabaseBind(stmt, 0, ExecStateToString(state));
   DatabaseBind(stmt, 1, retcode);
   DatabaseBind(stmt, 2, requestId);

   bool ok = DatabaseRead(stmt);
   DatabaseFinalize(stmt);
   return ok;
  }

bool TradeDealRecord(const long dealTicket, const string requestId, const long positionId,
                      const double volume, const double price)
  {
   int stmt = DatabasePrepare(g_AlikhandeDbHandle,
      "INSERT OR IGNORE INTO deals(deal_id, request_id, position_id, volume, price, ts) "
      "VALUES(?,?,?,?,?,?)");
   if(stmt == INVALID_HANDLE)
      return false;

   DatabaseBind(stmt, 0, dealTicket);
   DatabaseBind(stmt, 1, requestId);
   DatabaseBind(stmt, 2, positionId);
   DatabaseBind(stmt, 3, volume);
   DatabaseBind(stmt, 4, price);
   DatabaseBind(stmt, 5, (long)TimeCurrent());

   bool ok = DatabaseRead(stmt);
   DatabaseFinalize(stmt);
   return ok;
  }

// Called from OnInit: any request left non-terminal from a previous run must
// be reconciled against live positions/history before scanning resumes.
void TradeRequestRecoverAfterRestart()
  {
   if(!AlikhandeDbIsOpen())
      return;

   int stmt = DatabasePrepare(g_AlikhandeDbHandle,
      "SELECT request_id FROM trade_requests WHERE state IN (?,?,?)");
   if(stmt == INVALID_HANDLE)
      return;

   DatabaseBind(stmt, 0, ExecStateToString(EXEC_SUBMITTING));
   DatabaseBind(stmt, 1, ExecStateToString(EXEC_UNKNOWN));
   DatabaseBind(stmt, 2, ExecStateToString(EXEC_PARTIALLY_FILLED));

   int recovered = 0;
   while(DatabaseRead(stmt))
     {
      string requestId;
      DatabaseColumnText(stmt, 0, requestId);
      // Reconciliation itself (matching against HistoryDeals/PositionSelect) is
      // implemented in Execution/ExecutionStateMachine.mqh — this only flags
      // the set of requests that need it so the boot sequence is explicit.
      AlikhandeDbLogEvent("WARN", "RESTART_RECOVERY_NEEDED", requestId);
      recovered++;
     }
   DatabaseFinalize(stmt);

   if(recovered > 0)
      PrintFormat("Alikhande: %d trade request(s) need restart reconciliation", recovered);
  }
