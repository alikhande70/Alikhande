#pragma once
#include "../Domain/Models.mqh"
#include "../Core/Config.mqh"
#include "../Core/Hash.mqh"
#include "../Core/Log.mqh"
#include "Preflight.mqh"
#include "../Persistence/Repositories.mqh"

// The single boundary where an order leaves the terminal.
//
// This is the ONLY module in the codebase permitted to call OrderSend; the
// static gate enforces that, so no future change can quietly open a second
// path that skips the guards.
//
// Real accounts are blocked unconditionally. There is no configuration, no
// input and no enum member that reaches a live account in the 1.x line — the
// check is a hard return, not a policy flag.
//
// Reconciliation is built on MetaQuotes' documented reality that trade
// transaction delivery is UNORDERED, may repeat, and can be dropped when the
// 1024-element queue overflows. Nothing here waits for a particular event
// sequence: every handler re-reads authoritative state, deals are recorded by
// ticket so a replay cannot double-count, and a sweep escalates anything left
// unresolved past a grace period.

string AS_ExecStateName(const ENUM_AS_EXEC_STATE state)
  {
   switch(state)
     {
      case AS_EXEC_IDLE:             return "IDLE";
      case AS_EXEC_SUBMITTING:       return "SUBMITTING";
      case AS_EXEC_ACCEPTED:         return "ACCEPTED";
      case AS_EXEC_PARTIALLY_FILLED: return "PARTIALLY_FILLED";
      case AS_EXEC_FILLED:           return "FILLED";
      case AS_EXEC_POSITION_ACTIVE:  return "POSITION_ACTIVE";
      case AS_EXEC_REJECTED:         return "REJECTED";
      case AS_EXEC_CANCELLED:        return "CANCELLED";
      case AS_EXEC_UNKNOWN:          return "UNKNOWN";
      case AS_EXEC_RECONCILING:      return "RECONCILING";
      case AS_EXEC_COMPLETED:        return "COMPLETED";
     }
   return "UNKNOWN";
  }

class AS_ExecutionEngine
  {
private:
   AS_Preflight       m_preflight;
   AS_Repositories   *m_repo;
   AS_Log            *m_log;
   AS_ExecutionRecord m_current;
   ulong              m_magic;

   void Save(void)
     {
      m_current.updated_at = TimeCurrent();
      if(m_repo != NULL)
         m_repo.SaveExecution(m_current, AS_ExecStateName(m_current.state));
     }

   // Is this deal one of ours? Magic number is the authority — without it,
   // manual trades and other EAs' fills get attributed to the scanner.
   bool IsOwnDeal(const ulong deal_ticket) const
     {
      if(deal_ticket == 0 || !HistoryDealSelect(deal_ticket))
         return false;
      return (ulong)HistoryDealGetInteger(deal_ticket, DEAL_MAGIC) == m_magic;
     }

public:
   AS_ExecutionEngine(void)
     {
      m_repo = NULL;
      m_log = NULL;
      m_magic = AS_MAGIC;
      ZeroMemory(m_current);
      m_current.state = AS_EXEC_IDLE;
     }

   void Attach(AS_Repositories &repo, AS_Log &log, const ulong magic)
     {
      m_repo = GetPointer(repo);
      m_log = GetPointer(log);
      m_magic = magic;
     }

   AS_ExecutionRecord Current(void) const { return m_current; }

   bool HasUnresolved(void) const
     {
      return m_current.execution_id != ""
             && !m_current.terminal
             && m_current.state != AS_EXEC_IDLE;
     }

   // Restores an in-flight execution after a restart so reconciliation
   // resumes instead of the order being forgotten.
   void RecoverAfterRestart(void)
     {
      if(m_repo == NULL)
         return;
      if(!m_repo.LoadUnresolvedExecution(m_current))
         return;
      m_current.state = AS_EXEC_RECONCILING;
      if(m_log != NULL)
         m_log.Warn("EXECUTION_RECOVERED", m_current.symbol,
                    StringFormat("execution %s was in flight at shutdown; reconciling",
                                 m_current.execution_id));
      Save();
     }

   // Submits a plan. `mode` decides whether an order actually leaves:
   //   ALERT_ONLY — never sends.
   //   SHADOW     — runs the full preflight and records the intent, sends nothing.
   //   DEMO       — sends, demo accounts only.
   bool Submit(const AS_TradePlan &plan, const ENUM_AS_RUN_MODE mode, string &reason)
     {
      reason = "";

      if(mode == AS_MODE_ALERT_ONLY)
        {
         reason = "ALERT_ONLY_MODE";
         return false;
        }

      // Unconditional. Not a setting, not overridable.
      if((ENUM_ACCOUNT_TRADE_MODE)AccountInfoInteger(ACCOUNT_TRADE_MODE)
         != ACCOUNT_TRADE_MODE_DEMO)
        {
         reason = "REAL_ACCOUNT_BLOCKED";
         if(m_log != NULL)
            m_log.Error("REAL_ACCOUNT_BLOCKED", plan.symbol,
                        "execution refused: this build never trades a live account");
         return false;
        }

      // One in-flight execution at a time. Concurrent sends cannot be
      // attributed reliably under unordered transaction delivery.
      if(HasUnresolved())
        {
         reason = "EXECUTION_ALREADY_UNRESOLVED";
         return false;
        }

      MqlTradeRequest request;
      MqlTradeCheckResult check;
      if(!m_preflight.Validate(plan, m_magic, AS_ORDER_COMMENT, request, check, reason))
         return false;

      ZeroMemory(m_current);
      m_current.execution_id     = AS_Fnv1a64(plan.plan_id + "|" + IntegerToString((long)TimeCurrent()));
      m_current.plan_id          = plan.plan_id;
      m_current.signal_id        = plan.signal_id;
      m_current.symbol           = plan.symbol;
      m_current.requested_volume = plan.lot_size;
      m_current.created_at       = TimeCurrent();
      m_current.state            = AS_EXEC_SUBMITTING;
      m_current.terminal         = false;

      if(mode == AS_MODE_SHADOW)
        {
         // Everything a real send would do, minus the send. This is what makes
         // the mode useful: identical validation path, identical persistence,
         // so a shadow run exercises the same code a demo run would.
         m_current.state = AS_EXEC_COMPLETED;
         m_current.terminal = true;
         m_current.message = "SHADOW_NOT_SENT";
         Save();
         reason = "SHADOW_MODE";
         if(m_log != NULL)
            m_log.Info("SHADOW_EXECUTION", plan.symbol,
                       StringFormat("plan %s passed preflight; not sent (shadow mode)",
                                    plan.plan_id));
         return true;
        }

      // Persist the intent BEFORE sending. If the terminal dies between here
      // and the reply, restart recovery still finds the record.
      Save();

      MqlTradeResult result;
      ZeroMemory(result);
      const bool sent = OrderSend(request, result);

      m_current.request_id   = result.request_id;
      m_current.order_ticket = result.order;
      m_current.deal_ticket  = result.deal;
      m_current.retcode      = result.retcode;
      m_current.message      = result.comment;

      if(!sent)
        {
         m_current.state = AS_EXEC_REJECTED;
         m_current.terminal = true;
         reason = StringFormat("ORDERSEND_FAILED(%u:%s)", result.retcode, result.comment);
        }
      else if(result.retcode == TRADE_RETCODE_DONE)
         m_current.state = AS_EXEC_FILLED;
      else if(result.retcode == TRADE_RETCODE_DONE_PARTIAL)
         m_current.state = AS_EXEC_PARTIALLY_FILLED;
      else if(result.retcode == TRADE_RETCODE_PLACED)
         m_current.state = AS_EXEC_ACCEPTED;
      else
        {
         // Anything else is genuinely unknown until reconciled. Treating an
         // unrecognised retcode as failure risks a live position nobody tracks.
         m_current.state = AS_EXEC_UNKNOWN;
         reason = StringFormat("UNKNOWN_RETCODE(%u:%s)", result.retcode, result.comment);
        }

      Save();
      return sent;
     }

   // OnTradeTransaction handler. Never assumes ordering; correlates by
   // request id, order ticket, deal ticket, or magic-filtered symbol match.
   void OnTransaction(const MqlTradeTransaction &trans,
                      const MqlTradeRequest &request,
                      const MqlTradeResult &result)
     {
      // Deals are recorded even when they belong to no tracked execution, so
      // the account guard sees this EA's closed trades regardless of whether
      // the scanner was the thing that opened them in this session.
      if(trans.type == TRADE_TRANSACTION_DEAL_ADD && IsOwnDeal(trans.deal))
        {
         const double volume = HistoryDealGetDouble(trans.deal, DEAL_VOLUME);
         const double price  = HistoryDealGetDouble(trans.deal, DEAL_PRICE);
         const int    entry  = (int)HistoryDealGetInteger(trans.deal, DEAL_ENTRY);
         const double net    = HistoryDealGetDouble(trans.deal, DEAL_PROFIT)
                               + HistoryDealGetDouble(trans.deal, DEAL_COMMISSION)
                               + HistoryDealGetDouble(trans.deal, DEAL_SWAP);
         const string symbol = HistoryDealGetString(trans.deal, DEAL_SYMBOL);

         // Keyed by ticket: a replayed transaction cannot double-count.
         if(m_repo != NULL)
            m_repo.RecordDealOnce(trans.deal, m_current.execution_id, symbol,
                                  entry, volume, price, net);
        }

      if(!HasUnresolved())
         return;

      bool related = false;
      if(m_current.request_id > 0 && result.request_id == m_current.request_id)
         related = true;
      if(m_current.order_ticket > 0 && trans.order == m_current.order_ticket)
         related = true;
      if(m_current.deal_ticket > 0 && trans.deal == m_current.deal_ticket)
         related = true;
      if(!related && trans.type == TRADE_TRANSACTION_DEAL_ADD
         && IsOwnDeal(trans.deal)
         && HistoryDealGetString(trans.deal, DEAL_SYMBOL) == m_current.symbol)
         related = true;
      if(!related)
         return;

      if(trans.order > 0)    m_current.order_ticket = trans.order;
      if(trans.deal > 0)     m_current.deal_ticket = trans.deal;
      if(trans.position > 0) m_current.position_id = trans.position;
      if(result.retcode > 0) m_current.retcode = result.retcode;

      if(trans.type == TRADE_TRANSACTION_DEAL_ADD && HistoryDealSelect(trans.deal))
        {
         const long entry = HistoryDealGetInteger(trans.deal, DEAL_ENTRY);
         if(entry == DEAL_ENTRY_OUT || entry == DEAL_ENTRY_OUT_BY)
           {
            m_current.state = AS_EXEC_COMPLETED;
            m_current.terminal = true;
           }
         else
           {
            m_current.filled_volume += HistoryDealGetDouble(trans.deal, DEAL_VOLUME);
            const double step = SymbolInfoDouble(m_current.symbol, SYMBOL_VOLUME_STEP);
            const double tolerance = (step > 0.0 ? step * 0.5 : 1e-8);
            m_current.state = (m_current.filled_volume + tolerance >= m_current.requested_volume
                               ? AS_EXEC_FILLED : AS_EXEC_PARTIALLY_FILLED);
           }
        }
      else if(trans.type == TRADE_TRANSACTION_POSITION)
         m_current.state = AS_EXEC_POSITION_ACTIVE;
      else if(trans.type == TRADE_TRANSACTION_ORDER_DELETE && m_current.filled_volume <= 0.0)
         m_current.state = AS_EXEC_RECONCILING;

      Save();
     }

   // Periodic sweep. Events can be dropped entirely when the transaction queue
   // overflows, so nothing may depend on an event arriving; this re-reads
   // authoritative position state and escalates what it cannot resolve.
   void Reconcile(void)
     {
      if(!HasUnresolved())
         return;

      bool position_found = false;
      for(int i = PositionsTotal() - 1; i >= 0; i--)
        {
         const ulong ticket = PositionGetTicket(i);
         if(ticket == 0)
            continue;
         if(PositionGetString(POSITION_SYMBOL) == m_current.symbol
            && (ulong)PositionGetInteger(POSITION_MAGIC) == m_magic)
           {
            m_current.position_id = (ulong)PositionGetInteger(POSITION_IDENTIFIER);
            m_current.state = AS_EXEC_POSITION_ACTIVE;
            position_found = true;
            break;
           }
        }

      if(!position_found)
        {
         if(m_current.state == AS_EXEC_POSITION_ACTIVE)
           {
            m_current.state = AS_EXEC_COMPLETED;
            m_current.terminal = true;
            m_current.message = "POSITION_CLOSED";
           }
         else if(TimeCurrent() - m_current.updated_at > AS_RECONCILE_GRACE_SECONDS)
           {
            // Unresolved past the grace period with no position to show for it.
            // Marked terminal so the engine is not wedged forever, but flagged
            // loudly: this is the state that needs a human to look.
            m_current.state = AS_EXEC_UNKNOWN;
            m_current.terminal = true;
            m_current.message = "RECONCILIATION_FAILED";
            if(m_log != NULL)
               m_log.Error("RECONCILIATION_FAILED", m_current.symbol,
                           StringFormat("execution %s unresolved after %d s; "
                                        "verify the account manually",
                                        m_current.execution_id, AS_RECONCILE_GRACE_SECONDS));
           }
         else
            m_current.state = AS_EXEC_RECONCILING;
        }

      Save();
     }
  };
