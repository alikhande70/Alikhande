#pragma once
#include "../Domain/Models.mqh"
#include "../Core/Config.mqh"
#include "../Persistence/Repositories.mqh"

// Account-level circuit breakers: daily loss, total drawdown, consecutive
// losses. Disabled by default, as in v1.1.0.
//
// Two corrections that matter more than the thresholds themselves:
//
// 1. STATE IS PERSISTED. v1.1.0's Initialize() set peak equity to *current*
//    equity, so restarting mid-drawdown reset the high-water mark and quietly
//    disarmed the drawdown guard — precisely when it was most needed.
//
// 2. ONLY THIS EA'S TRADES COUNT. v1.1.0 tallied every closing deal on the
//    account, so a manual trade or another EA's loss incremented the scanner's
//    consecutive-loss counter and could halt it for something it never did.

class AS_AccountRiskGuard
  {
private:
   AS_RiskState     m_state;
   AS_Repositories *m_repo;
   AS_Log          *m_log;
   bool             m_loaded;

   int DayKey(void) const
     {
      MqlDateTime dt;
      TimeToStruct(TimeTradeServer(), dt);
      return dt.year * 1000 + dt.day_of_year;
     }

   void Persist(void)
     {
      m_state.updated_at = TimeCurrent();
      if(m_repo != NULL)
         m_repo.SaveRiskState(m_state);
     }

public:
   AS_AccountRiskGuard(void)
     {
      ZeroMemory(m_state);
      m_repo = NULL;
      m_log = NULL;
      m_loaded = false;
     }

   void Attach(AS_Repositories &repo, AS_Log &log)
     {
      m_repo = GetPointer(repo);
      m_log = GetPointer(log);
     }

   AS_RiskState State(void) const { return m_state; }

   // Restores persisted state, or seeds it on first ever run. The peak-equity
   // high-water mark survives restarts; that is the whole point.
   void Initialize(void)
     {
      const double equity = AccountInfoDouble(ACCOUNT_EQUITY);

      if(m_repo != NULL && m_repo.LoadRiskState(m_state) && m_state.peak_equity > 0.0)
        {
         m_loaded = true;
         // Never lower the high-water mark on load; only equity growth moves it.
         if(equity > m_state.peak_equity)
            m_state.peak_equity = equity;
         if(m_log != NULL)
            m_log.Info("RISK_STATE_RESTORED", "",
                       StringFormat("peak=%.2f day_start=%.2f consecutive_losses=%d",
                                    m_state.peak_equity, m_state.day_start_equity,
                                    m_state.consecutive_losses));
        }
      else
        {
         m_state.day_key = DayKey();
         m_state.day_start_equity = equity;
         m_state.peak_equity = equity;
         m_state.consecutive_losses = 0;
         m_state.daily_risk_used_pct = 0.0;
         m_loaded = false;
        }

      RollDay();
      Persist();
     }

   // Rolls the daily baseline on a broker server-day change.
   void RollDay(void)
     {
      const int key = DayKey();
      if(key == m_state.day_key)
         return;
      m_state.day_key = key;
      m_state.day_start_equity = AccountInfoDouble(ACCOUNT_EQUITY);
      m_state.daily_risk_used_pct = 0.0;
      // Consecutive losses deliberately survive the day boundary: a losing
      // streak does not become irrelevant because midnight passed.
      Persist();
     }

   // Called only for deals this EA opened (magic-filtered upstream).
   void RegisterClosedProfit(const double net_profit)
     {
      if(net_profit < 0.0)
         m_state.consecutive_losses++;
      else if(net_profit > 0.0)
         m_state.consecutive_losses = 0;
      Persist();
     }

   void RegisterRiskUsed(const double risk_pct)
     {
      m_state.daily_risk_used_pct += risk_pct;
      Persist();
     }

   // Returns true when trading may continue. `codes` accumulates every breached
   // guard, so the dashboard can show all of them rather than just the first.
   bool Check(const bool enabled, string &codes)
     {
      codes = "";
      if(!enabled)
         return true;

      RollDay();

      const double equity = AccountInfoDouble(ACCOUNT_EQUITY);
      if(equity > m_state.peak_equity)
        {
         m_state.peak_equity = equity;
         Persist();
        }

      bool ok = true;

      if(m_state.day_start_equity > 0.0)
        {
         const double daily_loss_pct =
            (m_state.day_start_equity - equity) / m_state.day_start_equity * 100.0;
         if(daily_loss_pct >= AS_DEFAULT_DAILY_LOSS_LIMIT_PCT)
           {
            ok = false;
            codes += StringFormat("DAILY_LOSS_HALT(%.2f%%);", daily_loss_pct);
           }
        }

      if(m_state.peak_equity > 0.0)
        {
         const double drawdown_pct =
            (m_state.peak_equity - equity) / m_state.peak_equity * 100.0;
         if(drawdown_pct >= AS_DEFAULT_TOTAL_DRAWDOWN_LIMIT_PCT)
           {
            ok = false;
            codes += StringFormat("DRAWDOWN_HALT(%.2f%%);", drawdown_pct);
           }
        }

      if(m_state.consecutive_losses >= AS_DEFAULT_MAX_CONSECUTIVE_LOSSES)
        {
         ok = false;
         codes += StringFormat("CONSECUTIVE_LOSS_HALT(%d);", m_state.consecutive_losses);
        }

      return ok;
     }
  };
