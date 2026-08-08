//+------------------------------------------------------------------+
//| SignalLifecycle.mqh                                               |
//| A signal is never "just shown on the dashboard and forgotten".    |
//| Every signal moves through this state machine and every           |
//| transition is persisted to Storage/Database.mqh.                  |
//+------------------------------------------------------------------+
#property strict
#include "../Storage/Database.mqh"

enum ENUM_SIGNAL_STATE
  {
   SIGNAL_CANDIDATE,     // rule score crossed threshold, not yet shown as actionable
   SIGNAL_CONFIRMED,     // passed zone proximity + MTF confirmation
   SIGNAL_PREVIEWED,     // shown to user with entry/SL/TP snapshot
   SIGNAL_ACTIVE,        // position opened against this signal
   SIGNAL_TP,
   SIGNAL_SL,
   SIGNAL_EXPIRED,       // preview window elapsed, never confirmed by user
   SIGNAL_INVALIDATED,   // market moved past the setup's validity condition
   SIGNAL_AMBIGUOUS,     // execution outcome could not be reconciled — needs manual review
   SIGNAL_NOT_FILLED
  };

string SignalStateToString(const ENUM_SIGNAL_STATE s)
  {
   switch(s)
     {
      case SIGNAL_CANDIDATE:   return "CANDIDATE";
      case SIGNAL_CONFIRMED:   return "CONFIRMED";
      case SIGNAL_PREVIEWED:   return "PREVIEWED";
      case SIGNAL_ACTIVE:      return "ACTIVE";
      case SIGNAL_TP:          return "TP";
      case SIGNAL_SL:          return "SL";
      case SIGNAL_EXPIRED:     return "EXPIRED";
      case SIGNAL_INVALIDATED: return "INVALIDATED";
      case SIGNAL_AMBIGUOUS:   return "AMBIGUOUS";
      case SIGNAL_NOT_FILLED:  return "NOT_FILLED";
     }
   return "UNKNOWN";
  }

// Terminal states — once here, a signal is closed for good and only the
// Statistics/Outcome engine (v1.3) reads it back.
bool SignalStateIsTerminal(const ENUM_SIGNAL_STATE s)
  {
   return s == SIGNAL_TP || s == SIGNAL_SL || s == SIGNAL_EXPIRED ||
          s == SIGNAL_INVALIDATED || s == SIGNAL_AMBIGUOUS || s == SIGNAL_NOT_FILLED;
  }

// Explicit allow-list of transitions. Anything not listed here is a bug in
// the caller, not a state the signal can silently jump to.
bool SignalTransitionAllowed(const ENUM_SIGNAL_STATE from, const ENUM_SIGNAL_STATE to)
  {
   if(SignalStateIsTerminal(from))
      return false;

   switch(from)
     {
      case SIGNAL_CANDIDATE:
         return to == SIGNAL_CONFIRMED || to == SIGNAL_INVALIDATED;
      case SIGNAL_CONFIRMED:
         return to == SIGNAL_PREVIEWED || to == SIGNAL_INVALIDATED || to == SIGNAL_EXPIRED;
      case SIGNAL_PREVIEWED:
         return to == SIGNAL_ACTIVE || to == SIGNAL_EXPIRED ||
                to == SIGNAL_INVALIDATED || to == SIGNAL_NOT_FILLED;
      case SIGNAL_ACTIVE:
         return to == SIGNAL_TP || to == SIGNAL_SL || to == SIGNAL_AMBIGUOUS;
     }
   return false;
  }

struct SignalRecord
  {
   string             signalId;
   datetime           ts;
   string             symbol;
   string             direction;
   string             setup;
   string             h4State, h1State, m15State, m5State;
   double             spread, atr;
   double             support, resistance;
   double             entry, sl, tp;
   double             longScore, shortScore;
   int                ruleVersion;
   string             parameterHash;
   string             brokerSpecHash;
   ENUM_SIGNAL_STATE  state;
  };

//+------------------------------------------------------------------+
//| Persist a brand-new signal. Called once, at CANDIDATE creation.   |
//+------------------------------------------------------------------+
bool SignalPersistNew(const SignalRecord &rec)
  {
   if(!AlikhandeDbIsOpen())
      return false;

   int stmt = DatabasePrepare(g_AlikhandeDbHandle,
      "INSERT INTO signals(signal_id, ts, symbol, direction, setup, h4_state, h1_state, "
      "m15_state, m5_state, spread, atr, support, resistance, entry, sl, tp, long_score, "
      "short_score, rule_version, parameter_hash, broker_spec_hash, state, created_at) "
      "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)");
   if(stmt == INVALID_HANDLE)
      return false;

   int i = 0;
   DatabaseBind(stmt, i++, rec.signalId);
   DatabaseBind(stmt, i++, (long)rec.ts);
   DatabaseBind(stmt, i++, rec.symbol);
   DatabaseBind(stmt, i++, rec.direction);
   DatabaseBind(stmt, i++, rec.setup);
   DatabaseBind(stmt, i++, rec.h4State);
   DatabaseBind(stmt, i++, rec.h1State);
   DatabaseBind(stmt, i++, rec.m15State);
   DatabaseBind(stmt, i++, rec.m5State);
   DatabaseBind(stmt, i++, rec.spread);
   DatabaseBind(stmt, i++, rec.atr);
   DatabaseBind(stmt, i++, rec.support);
   DatabaseBind(stmt, i++, rec.resistance);
   DatabaseBind(stmt, i++, rec.entry);
   DatabaseBind(stmt, i++, rec.sl);
   DatabaseBind(stmt, i++, rec.tp);
   DatabaseBind(stmt, i++, rec.longScore);
   DatabaseBind(stmt, i++, rec.shortScore);
   DatabaseBind(stmt, i++, rec.ruleVersion);
   DatabaseBind(stmt, i++, rec.parameterHash);
   DatabaseBind(stmt, i++, rec.brokerSpecHash);
   DatabaseBind(stmt, i++, SignalStateToString(rec.state));
   DatabaseBind(stmt, i++, (long)TimeCurrent());

   bool ok = DatabaseRead(stmt);
   DatabaseFinalize(stmt);
   return ok;
  }

//+------------------------------------------------------------------+
//| Transition an existing signal. Rejects illegal jumps so a bug     |
//| upstream fails loudly instead of silently corrupting history.     |
//+------------------------------------------------------------------+
bool SignalTransition(const string signalId, const ENUM_SIGNAL_STATE from,
                       const ENUM_SIGNAL_STATE to)
  {
   if(!SignalTransitionAllowed(from, to))
     {
      AlikhandeDbLogEvent("ERROR", "SIGNAL_ILLEGAL_TRANSITION",
         StringFormat("signal=%s from=%s to=%s", signalId,
                      SignalStateToString(from), SignalStateToString(to)));
      return false;
     }

   if(!AlikhandeDbIsOpen())
      return false;

   int stmt = DatabasePrepare(g_AlikhandeDbHandle,
      "UPDATE signals SET state=? WHERE signal_id=? AND state=?");
   if(stmt == INVALID_HANDLE)
      return false;

   DatabaseBind(stmt, 0, SignalStateToString(to));
   DatabaseBind(stmt, 1, signalId);
   DatabaseBind(stmt, 2, SignalStateToString(from));

   bool ok = DatabaseRead(stmt);
   DatabaseFinalize(stmt);
   return ok;
  }
