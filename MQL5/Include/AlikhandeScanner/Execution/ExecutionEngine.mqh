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

// May reconciliation record this state as finished?
//
// AS_EXEC_UNKNOWN is deliberately absent. It means "not resolved", and a state
// meaning not-resolved must never be auto-recorded as finished — doing so was
// the P0 this predicate exists to prevent: it released the submit gate in the
// one situation where an untracked order might be live.
//
// The single documented exception is AcknowledgeUnresolved(), where a human has
// inspected the account and taken responsibility for the decision.
bool AS_ExecStateMayBeAutoTerminal(const ENUM_AS_EXEC_STATE state)
  {
   return state == AS_EXEC_COMPLETED
          || state == AS_EXEC_REJECTED
          || state == AS_EXEC_CANCELLED;
  }

// What the broker says happened to an execution, rebuilt from live and
// historical state rather than from events that may never have arrived.
struct AS_BrokerTruth
  {
   bool               resolved;      // did any source have a definite answer
   ENUM_AS_EXEC_STATE state;
   bool               terminal;      // is that answer final
   string             source;        // which source answered
   string             detail;
   double             filled_volume;
   ulong              position_id;
  };

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

   // ---------------------------------------------------------- broker truth
   //
   // Four sources, consulted in descending order of authority. Each answers a
   // different question, and consulting only one is how a live order gets
   // mistaken for nothing having happened:
   //
   //   1. Open positions   — "is there a position right now"
   //   2. Working orders   — "is an order still live but unfilled"
   //   3. History orders   — "what was the order's final disposition"
   //   4. History deals    — "what actually executed"

   bool FindOpenPosition(AS_BrokerTruth &truth) const
     {
      for(int i = PositionsTotal() - 1; i >= 0; i--)
        {
         const ulong ticket = PositionGetTicket(i);
         if(ticket == 0)
            continue;
         if((ulong)PositionGetInteger(POSITION_MAGIC) != m_magic)
            continue;

         const bool matches_id = (m_current.position_id > 0
                                  && (ulong)PositionGetInteger(POSITION_IDENTIFIER)
                                     == m_current.position_id);
         if(!matches_id && PositionGetString(POSITION_SYMBOL) != m_current.symbol)
            continue;

         truth.resolved      = true;
         truth.state         = AS_EXEC_POSITION_ACTIVE;
         truth.terminal      = false;   // a live position is not a finished execution
         truth.source        = "POSITION";
         truth.detail        = StringFormat("position %I64u open",
                                            (ulong)PositionGetInteger(POSITION_IDENTIFIER));
         truth.position_id   = (ulong)PositionGetInteger(POSITION_IDENTIFIER);
         truth.filled_volume = PositionGetDouble(POSITION_VOLUME);
         return true;
        }
      return false;
     }

   bool FindWorkingOrder(AS_BrokerTruth &truth) const
     {
      for(int i = OrdersTotal() - 1; i >= 0; i--)
        {
         const ulong ticket = OrderGetTicket(i);
         if(ticket == 0)
            continue;
         if((ulong)OrderGetInteger(ORDER_MAGIC) != m_magic)
            continue;
         if(m_current.order_ticket > 0 && ticket != m_current.order_ticket
            && OrderGetString(ORDER_SYMBOL) != m_current.symbol)
            continue;
         if(m_current.order_ticket == 0 && OrderGetString(ORDER_SYMBOL) != m_current.symbol)
            continue;

         truth.resolved = true;
         truth.state    = AS_EXEC_ACCEPTED;
         truth.terminal = false;        // still working: emphatically not finished
         truth.source   = "WORKING_ORDER";
         truth.detail   = StringFormat("order %I64u still live", ticket);
         return true;
        }
      return false;
     }

   // Maps a completed order's final state. Only reached when the order is no
   // longer working, so every branch here is a definite disposition.
   bool ResolveHistoryOrder(const ulong ticket, AS_BrokerTruth &truth) const
     {
      if(ticket == 0 || !HistoryOrderSelect(ticket))
         return false;
      if((ulong)HistoryOrderGetInteger(ticket, ORDER_MAGIC) != m_magic)
         return false;

      const long order_state = HistoryOrderGetInteger(ticket, ORDER_STATE);
      truth.resolved = true;
      truth.source   = "HISTORY_ORDER";

      switch(order_state)
        {
         case ORDER_STATE_FILLED:
            truth.state    = AS_EXEC_FILLED;
            truth.terminal = false;   // filled, but the position's fate is still open
            truth.detail   = StringFormat("order %I64u filled", ticket);
            break;
         case ORDER_STATE_PARTIAL:
            truth.state    = AS_EXEC_PARTIALLY_FILLED;
            truth.terminal = false;
            truth.detail   = StringFormat("order %I64u partially filled", ticket);
            break;
         case ORDER_STATE_CANCELED:
         case ORDER_STATE_EXPIRED:
            truth.state    = AS_EXEC_CANCELLED;
            truth.terminal = true;
            truth.detail   = StringFormat("order %I64u cancelled/expired", ticket);
            break;
         case ORDER_STATE_REJECTED:
            truth.state    = AS_EXEC_REJECTED;
            truth.terminal = true;
            truth.detail   = StringFormat("order %I64u rejected", ticket);
            break;
         default:
            // Transitional states say nothing final; treat as no answer rather
            // than inventing one.
            truth.resolved = false;
            return false;
        }
      return true;
     }

   // Sums this execution's deals. An IN followed by an OUT on the same position
   // means the trade opened and closed while we were not watching — which is a
   // genuinely finished execution, not a missing one.
   bool ResolveFromDeals(AS_BrokerTruth &truth) const
     {
      double volume_in = 0.0;
      double volume_out = 0.0;
      ulong position_id = 0;
      int matched = 0;

      const int total = HistoryDealsTotal();
      for(int i = 0; i < total; i++)
        {
         const ulong deal = HistoryDealGetTicket(i);
         if(deal == 0)
            continue;
         if((ulong)HistoryDealGetInteger(deal, DEAL_MAGIC) != m_magic)
            continue;
         if(HistoryDealGetString(deal, DEAL_SYMBOL) != m_current.symbol)
            continue;

         // Prefer an exact link when we have one; otherwise magic+symbol within
         // the selected history window is the best available correlation.
         if(m_current.order_ticket > 0
            && (ulong)HistoryDealGetInteger(deal, DEAL_ORDER) != m_current.order_ticket
            && m_current.position_id > 0
            && (ulong)HistoryDealGetInteger(deal, DEAL_POSITION_ID) != m_current.position_id)
            continue;

         const long entry = HistoryDealGetInteger(deal, DEAL_ENTRY);
         const double volume = HistoryDealGetDouble(deal, DEAL_VOLUME);
         if(entry == DEAL_ENTRY_IN)
            volume_in += volume;
         else if(entry == DEAL_ENTRY_OUT || entry == DEAL_ENTRY_OUT_BY)
            volume_out += volume;
         if(position_id == 0)
            position_id = (ulong)HistoryDealGetInteger(deal, DEAL_POSITION_ID);
         matched++;
        }

      if(matched == 0)
         return false;

      truth.resolved      = true;
      truth.source        = "HISTORY_DEAL";
      truth.filled_volume = volume_in;
      truth.position_id   = position_id;

      if(volume_in > 0.0 && volume_out + 1e-8 >= volume_in)
        {
         truth.state    = AS_EXEC_COMPLETED;
         truth.terminal = true;
         truth.detail   = StringFormat("opened %.2f and closed %.2f", volume_in, volume_out);
        }
      else
        {
         truth.state    = AS_EXEC_FILLED;
         truth.terminal = false;
         truth.detail   = StringFormat("filled %.2f, %.2f still open", volume_in,
                                       volume_in - volume_out);
        }
      return true;
     }

   AS_BrokerTruth ResolveFromBroker(void) const
     {
      AS_BrokerTruth truth;
      ZeroMemory(truth);
      truth.resolved = false;

      // History must be selected before the history calls will see anything.
      // The window is anchored on when this execution was created, widened so a
      // clock skew between terminal and server cannot hide the records.
      const datetime from = (m_current.created_at > 0
                             ? m_current.created_at - 3600 : TimeCurrent() - 86400);
      HistorySelect(from, TimeCurrent() + 3600);

      if(FindOpenPosition(truth))
         return truth;
      if(FindWorkingOrder(truth))
         return truth;
      if(m_current.order_ticket > 0 && ResolveHistoryOrder(m_current.order_ticket, truth))
         return truth;
      if(ResolveFromDeals(truth))
         return truth;

      return truth;   // resolved == false: every source was silent
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
      // The deal ledger is an ADMISSION GATE, not a log. MetaQuotes documents
      // that transaction delivery may repeat, so a deal ticket is allowed to
      // move execution state at most once. Recording the ticket and then
      // mutating state regardless — which is what this code used to do — makes
      // the idempotency decorative: a replayed DEAL_ADD double-counts the fill
      // and can drive a partially-filled order to FILLED on volume that only
      // ever arrived once.
      bool deal_admitted = false;
      if(trans.type == TRADE_TRANSACTION_DEAL_ADD && IsOwnDeal(trans.deal))
        {
         const double volume = HistoryDealGetDouble(trans.deal, DEAL_VOLUME);
         const double price  = HistoryDealGetDouble(trans.deal, DEAL_PRICE);
         const int    entry  = (int)HistoryDealGetInteger(trans.deal, DEAL_ENTRY);
         const double net    = HistoryDealGetDouble(trans.deal, DEAL_PROFIT)
                               + HistoryDealGetDouble(trans.deal, DEAL_COMMISSION)
                               + HistoryDealGetDouble(trans.deal, DEAL_SWAP);
         const string symbol = HistoryDealGetString(trans.deal, DEAL_SYMBOL);

         // Deals are admitted even when they belong to no tracked execution, so
         // the account guard still sees this EA's closed trades from a previous
         // session.
         deal_admitted = (m_repo != NULL)
                         && m_repo.RecordDealOnce(trans.deal, m_current.execution_id,
                                                  symbol, entry, volume, price, net);

         if(!deal_admitted && m_log != NULL)
            m_log.Debug("DEAL_REPLAY_IGNORED", symbol,
                        StringFormat("deal %I64u already applied", trans.deal));
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

      // Only an admitted deal may move fill state. A replay is correlated and
      // may still refresh tickets above, but it must not be counted again.
      if(trans.type == TRADE_TRANSACTION_DEAL_ADD && deal_admitted
         && HistoryDealSelect(trans.deal))
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

   // Periodic sweep. Transaction events can be dropped entirely when the
   // terminal's queue overflows, so nothing may depend on one arriving; this
   // rebuilds the truth from the broker instead.
   //
   // The governing rule, and the reason this was redesigned: `terminal` means
   // RESOLVED. It never means "gave up". An earlier version marked a genuinely
   // unresolved execution terminal after the grace period so the engine would
   // not wedge — which released the submit gate and allowed the next order out
   // in precisely the situation where nobody knew whether the previous one was
   // live. That is exactly backwards: "we do not know" is the strongest
   // possible reason to send nothing further.
   void Reconcile(void)
     {
      if(!HasUnresolved())
         return;

      const AS_BrokerTruth truth = ResolveFromBroker();

      if(truth.resolved)
        {
         m_current.state = truth.state;
         // Belt and braces: even a resolver bug cannot mark a
         // not-actually-finished state as finished and reopen the gate.
         m_current.terminal = truth.terminal && AS_ExecStateMayBeAutoTerminal(truth.state);
         m_current.message = truth.detail;
         if(truth.position_id > 0)
            m_current.position_id = truth.position_id;
         if(truth.filled_volume > 0.0)
            m_current.filled_volume = truth.filled_volume;

         if(m_log != NULL)
            m_log.Info("RECONCILED", m_current.symbol,
                       StringFormat("execution %s resolved as %s via %s (%s)",
                                    m_current.execution_id, AS_ExecStateName(truth.state),
                                    truth.source, truth.detail));
         Save();
         return;
        }

      // Not resolvable yet. Inside the grace period this is normal — the server
      // may simply not have answered.
      if(TimeCurrent() - m_current.updated_at <= AS_RECONCILE_GRACE_SECONDS)
        {
         m_current.state = AS_EXEC_RECONCILING;
         Save();
         return;
        }

      // Past the grace period with all four broker sources silent. This is a
      // real unknown: an order may be live that this EA cannot see. The
      // execution stays NON-terminal, which keeps HasUnresolved() true, which
      // keeps the submit gate shut — and because the record is stored with
      // terminal=0 the block survives a restart as well.
      //
      // Only a deliberate operator acknowledgement clears it.
      if(m_current.state != AS_EXEC_UNKNOWN && m_log != NULL)
         m_log.Error("RECONCILIATION_FAILED", m_current.symbol,
                     StringFormat("execution %s unresolved after %d s across positions, "
                                  "working orders, history orders and history deals; "
                                  "submission is blocked until acknowledged",
                                  m_current.execution_id, AS_RECONCILE_GRACE_SECONDS));

      m_current.state = AS_EXEC_UNKNOWN;
      m_current.terminal = false;
      m_current.message = "UNRESOLVED_MANUAL_REVIEW_REQUIRED";
      Save();
     }

   // True when the engine is refusing to submit because an execution could not
   // be resolved. Surfaced on the Health tab; distinct from merely having a
   // live execution in flight.
   bool RequiresManualReview(void) const
     {
      return m_current.execution_id != ""
             && !m_current.terminal
             && m_current.state == AS_EXEC_UNKNOWN;
     }

   // Operator escape hatch. Without this the engine would wedge permanently on
   // an unresolvable execution, and a permanently wedged system gets "fixed" by
   // deleting the database — which loses the evidence too. Clearing is a
   // deliberate, logged act that records who decided the account was verified.
   bool AcknowledgeUnresolved(const string operator_note)
     {
      if(!RequiresManualReview())
         return false;

      m_current.terminal = true;
      m_current.message = "ACKNOWLEDGED: " + operator_note;
      if(m_log != NULL)
         m_log.Warn("UNRESOLVED_ACKNOWLEDGED", m_current.symbol,
                    StringFormat("execution %s cleared by operator: %s",
                                 m_current.execution_id, operator_note));
      Save();
      return true;
     }
  };
