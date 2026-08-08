//+------------------------------------------------------------------+
//| AccountRiskGuard.mqh                                               |
//| Optional account-level daily loss, drawdown, and consecutive-loss |
//| guards — disabled by default, per v1.1.0 changelog.                |
//+------------------------------------------------------------------+
#property strict

struct AccountGuardConfig
  {
   bool   enabled;
   double maxDailyLossPct;
   double maxDrawdownPct;
   int    maxConsecutiveLosses;
  };

struct AccountGuardState
  {
   double dayStartEquity;
   datetime dayStartTs;
   double peakEquity;
   int    consecutiveLosses;
  };

void AccountGuardResetDay(AccountGuardState &state)
  {
   state.dayStartEquity = AccountInfoDouble(ACCOUNT_EQUITY);
   state.dayStartTs = TimeTradeServer();
  }

// Call once per tick/timer; rolls the daily baseline forward on a broker
// server day change so "daily loss" always means "since today's server open".
void AccountGuardMaybeRollDay(AccountGuardState &state)
  {
   MqlDateTime now, start;
   TimeToStruct(TimeTradeServer(), now);
   TimeToStruct(state.dayStartTs, start);

   bool sameDay = (now.year == start.year && now.mon == start.mon && now.day == start.day);
   if(!sameDay)
      AccountGuardResetDay(state);

   double equity = AccountInfoDouble(ACCOUNT_EQUITY);
   if(equity > state.peakEquity)
      state.peakEquity = equity;
  }

struct AccountGuardResult
  {
   bool   tripped;
   string reason;
  };

AccountGuardResult EvaluateAccountGuards(const AccountGuardConfig &cfg, const AccountGuardState &state)
  {
   AccountGuardResult r;
   r.tripped = false;

   if(!cfg.enabled)
      return r;

   double equity = AccountInfoDouble(ACCOUNT_EQUITY);

   if(state.dayStartEquity > 0.0)
     {
      double dailyLossPct = (state.dayStartEquity - equity) / state.dayStartEquity * 100.0;
      if(dailyLossPct >= cfg.maxDailyLossPct)
        {
         r.tripped = true;
         r.reason = StringFormat("daily loss %.2f%% >= cap %.2f%%", dailyLossPct, cfg.maxDailyLossPct);
         return r;
        }
     }

   if(state.peakEquity > 0.0)
     {
      double drawdownPct = (state.peakEquity - equity) / state.peakEquity * 100.0;
      if(drawdownPct >= cfg.maxDrawdownPct)
        {
         r.tripped = true;
         r.reason = StringFormat("drawdown %.2f%% >= cap %.2f%%", drawdownPct, cfg.maxDrawdownPct);
         return r;
        }
     }

   if(state.consecutiveLosses >= cfg.maxConsecutiveLosses)
     {
      r.tripped = true;
      r.reason = StringFormat("%d consecutive losses >= cap %d",
                               state.consecutiveLosses, cfg.maxConsecutiveLosses);
      return r;
     }

   return r;
  }

// Called from the Outcome Engine (v1.3) or, in v1.2.0, directly when a
// SIGNAL_TP/SIGNAL_SL transition is recorded.
void AccountGuardRecordTradeResult(AccountGuardState &state, const bool wasWin)
  {
   state.consecutiveLosses = wasWin ? 0 : state.consecutiveLosses + 1;
  }
