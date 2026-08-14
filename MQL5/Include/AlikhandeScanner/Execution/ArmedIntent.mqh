#pragma once
#include "../Domain/Models.mqh"
#include "../Core/Config.mqh"
#include "../Core/Log.mqh"

// Two-step arming for demo execution.
//
// v1.2 sent orders automatically the moment a plan validated in DEMO mode.
// That is the wrong default even on a demo account: the system's stated
// purpose is to gather evidence under human supervision, and an EA that fires
// on its own is not supervised, it is merely watched.
//
// So execution requires two distinct human actions separated in time:
//
//   1. ARM     — the operator selects a previewed plan and arms it.
//   2. CONFIRM — the operator confirms the armed plan.
//
// The arming carries a short TTL. If the market moves or the operator hesitates
// past it, the intent expires and must be re-armed against a fresh plan. This
// is what stops "I armed it a while ago and forgot" turning into an order at a
// price nobody evaluated.
//
// A single click cannot execute. Arm and confirm are separate objects on the
// panel, and the confirm is only meaningful while an intent is armed and live.

struct AS_ArmedIntent
  {
   bool     armed;
   string   plan_id;
   string   signal_id;
   string   symbol;
   double   entry;
   double   stop_loss;
   double   take_profit;
   double   lot_size;
   datetime armed_at;
   datetime expires_at;
  };

class AS_IntentArming
  {
private:
   AS_ArmedIntent m_intent;
   AS_Log        *m_log;
   int            m_ttl_seconds;

public:
   AS_IntentArming(void)
     {
      ZeroMemory(m_intent);
      m_log = NULL;
      m_ttl_seconds = AS_ARM_TTL_SECONDS;
     }

   void Attach(AS_Log &log) { m_log = GetPointer(log); }
   void SetTtl(const int seconds) { m_ttl_seconds = MathMax(5, seconds); }

   AS_ArmedIntent Current(void) const { return m_intent; }

   bool IsArmed(void) const
     {
      return m_intent.armed && TimeCurrent() <= m_intent.expires_at;
     }

   // Expiry is evaluated lazily on read, but also swept so the UI stops showing
   // an armed state that is no longer actionable.
   bool Sweep(void)
     {
      if(!m_intent.armed)
         return false;
      if(TimeCurrent() <= m_intent.expires_at)
         return false;
      if(m_log != NULL)
         m_log.Info("INTENT_EXPIRED", m_intent.symbol,
                    StringFormat("armed plan %s expired unconfirmed", m_intent.plan_id));
      ZeroMemory(m_intent);
      return true;
     }

   // Arming replaces any previous intent. Only one plan may be armed at a
   // time — the same single-in-flight discipline the execution engine uses,
   // for the same reason: concurrent intents cannot be attributed to a click.
   bool Arm(const AS_TradePlan &plan)
     {
      if(!plan.valid)
         return false;

      ZeroMemory(m_intent);
      m_intent.armed       = true;
      m_intent.plan_id     = plan.plan_id;
      m_intent.signal_id   = plan.signal_id;
      m_intent.symbol      = plan.symbol;
      m_intent.entry       = plan.entry;
      m_intent.stop_loss   = plan.stop_loss;
      m_intent.take_profit = plan.take_profit;
      m_intent.lot_size    = plan.lot_size;
      m_intent.armed_at    = TimeCurrent();
      m_intent.expires_at  = m_intent.armed_at + m_ttl_seconds;

      if(m_log != NULL)
         m_log.Info("INTENT_ARMED", plan.symbol,
                    StringFormat("plan %s armed for %d s; confirmation required",
                                 plan.plan_id, m_ttl_seconds));
      return true;
     }

   void Disarm(const string reason)
     {
      if(!m_intent.armed)
         return;
      if(m_log != NULL)
         m_log.Info("INTENT_DISARMED", m_intent.symbol, reason);
      ZeroMemory(m_intent);
     }

   // Consumes the armed intent. Returns false unless an intent is armed, live,
   // and refers to the plan being confirmed — so a stale click cannot fire a
   // plan the operator never looked at.
   bool Confirm(const AS_TradePlan &plan, string &reason)
     {
      reason = "";

      if(!m_intent.armed)
        {
         reason = "NO_ARMED_INTENT";
         return false;
        }
      if(TimeCurrent() > m_intent.expires_at)
        {
         reason = "ARMED_INTENT_EXPIRED";
         Disarm(reason);
         return false;
        }
      if(m_intent.plan_id != plan.plan_id)
        {
         // The armed plan is not the plan now on screen: the signal was
         // re-planned underneath the operator. Refuse rather than execute
         // something they did not evaluate.
         reason = "ARMED_PLAN_SUPERSEDED";
         Disarm(reason);
         return false;
        }

      ZeroMemory(m_intent);
      return true;
     }
  };
