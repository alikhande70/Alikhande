#pragma once
#include "../Domain/Enums.mqh"

// Signal lifecycle rules.
//
// A signal that is shown once and forgotten can never produce a win rate. Every
// candidate walks an explicit state machine, every transition is persisted, and
// illegal transitions are rejected loudly rather than silently accepted — a
// corrupted lifecycle is worse than no statistics, because it looks like data.

string AS_SignalStateName(const ENUM_AS_SIGNAL_STATE state)
  {
   switch(state)
     {
      case AS_SIGNAL_NONE:        return "NONE";
      case AS_SIGNAL_CANDIDATE:   return "CANDIDATE";
      case AS_SIGNAL_CONFIRMED:   return "CONFIRMED";
      case AS_SIGNAL_PREVIEWED:   return "PREVIEWED";
      case AS_SIGNAL_ACTIVE:      return "ACTIVE";
      case AS_SIGNAL_TP:          return "TP";
      case AS_SIGNAL_SL:          return "SL";
      case AS_SIGNAL_EXPIRED:     return "EXPIRED";
      case AS_SIGNAL_INVALIDATED: return "INVALIDATED";
      case AS_SIGNAL_NOT_FILLED:  return "NOT_FILLED";
      case AS_SIGNAL_AMBIGUOUS:   return "AMBIGUOUS";
     }
   return "UNKNOWN";
  }

// Terminal states are final. Only the statistics layer reads them afterwards.
bool AS_SignalStateIsTerminal(const ENUM_AS_SIGNAL_STATE state)
  {
   return state == AS_SIGNAL_TP
          || state == AS_SIGNAL_SL
          || state == AS_SIGNAL_EXPIRED
          || state == AS_SIGNAL_INVALIDATED
          || state == AS_SIGNAL_NOT_FILLED
          || state == AS_SIGNAL_AMBIGUOUS;
  }

// Only TP and SL are outcomes a win rate may be computed from. Expiry and
// invalidation say something about the *scanner*, not about the setup's edge,
// and pooling them into a win rate would quietly flatter or damn the strategy.
bool AS_SignalStateIsScorable(const ENUM_AS_SIGNAL_STATE state)
  {
   return state == AS_SIGNAL_TP || state == AS_SIGNAL_SL;
  }

// Explicit allow-list. Anything absent is a bug in the caller, not a state the
// signal is permitted to reach.
bool AS_SignalTransitionAllowed(const ENUM_AS_SIGNAL_STATE from,
                                const ENUM_AS_SIGNAL_STATE to)
  {
   if(AS_SignalStateIsTerminal(from))
      return false;
   if(from == to)
      return false;

   switch(from)
     {
      case AS_SIGNAL_NONE:
         return to == AS_SIGNAL_CANDIDATE;

      case AS_SIGNAL_CANDIDATE:
         return to == AS_SIGNAL_CONFIRMED
                || to == AS_SIGNAL_INVALIDATED
                || to == AS_SIGNAL_EXPIRED;

      case AS_SIGNAL_CONFIRMED:
         return to == AS_SIGNAL_PREVIEWED
                || to == AS_SIGNAL_INVALIDATED
                || to == AS_SIGNAL_EXPIRED;

      case AS_SIGNAL_PREVIEWED:
         return to == AS_SIGNAL_ACTIVE
                || to == AS_SIGNAL_NOT_FILLED
                || to == AS_SIGNAL_INVALIDATED
                || to == AS_SIGNAL_EXPIRED;

      case AS_SIGNAL_ACTIVE:
         return to == AS_SIGNAL_TP
                || to == AS_SIGNAL_SL
                || to == AS_SIGNAL_AMBIGUOUS;
     }
   return false;
  }
