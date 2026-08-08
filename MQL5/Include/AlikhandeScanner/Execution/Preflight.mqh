#pragma once
#include <Trade/Trade.mqh>
#include "../Domain/Models.mqh"
#include "../Core/Config.mqh"
#include "../Risk/TradeGuards.mqh"

// Everything that must be true immediately before an order is sent.
//
// Note on OrderCheck: MetaQuotes is explicit that a successful OrderCheck does
// NOT guarantee the order will fill. It screens out requests that are certain
// to be rejected; it says nothing about what the market does next. The result
// therefore still has to be reconciled after submission — see ExecutionEngine.

class AS_Preflight
  {
private:
   AS_TradeGuards m_guards;

public:
   // Builds the request and validates it. On success `request` is ready to send
   // verbatim; on failure `reason` names the first failed gate.
   bool Validate(const AS_TradePlan &plan, const ulong magic, const string comment,
                 MqlTradeRequest &request, MqlTradeCheckResult &check, string &reason)
     {
      ZeroMemory(request);
      ZeroMemory(check);
      reason = "";

      if(!plan.valid)
        {
         reason = "PLAN_INVALID";
         return false;
        }
      if(TimeCurrent() > plan.expires_at)
        {
         reason = "PREVIEW_EXPIRED";
         return false;
        }

      string codes = "";
      if(!m_guards.TradePermissions(plan.symbol, codes))
        {
         reason = codes;
         return false;
        }
      if(!m_guards.StopsValid(plan, codes))
        {
         reason = codes;
         return false;
        }

      MqlTick tick;
      if(!SymbolInfoTick(plan.symbol, tick))
        {
         reason = "NO_TICK";
         return false;
        }

      const double point = SymbolInfoDouble(plan.symbol, SYMBOL_POINT);
      if(point <= 0.0)
        {
         reason = "NO_POINT";
         return false;
        }

      // The plan was sized against a specific price. If the market has moved
      // beyond tolerance the plan's risk arithmetic no longer describes the
      // trade that would actually open, so it is re-planned rather than sent.
      const double current = (plan.direction == AS_DIR_LONG ? tick.ask : tick.bid);
      const double drift_points = MathAbs(current - plan.entry) / point;
      if(drift_points > plan.max_drift_points)
        {
         reason = StringFormat("PRICE_DRIFT_EXCEEDED(%.0f>%.0f pts)",
                               drift_points, plan.max_drift_points);
         return false;
        }

      // Filling policy comes from the symbol rather than a hardcoded guess;
      // an unsupported filling mode is a common source of retcode 10030.
      CTrade probe;
      probe.SetTypeFillingBySymbol(plan.symbol);

      request.action       = TRADE_ACTION_DEAL;
      request.symbol       = plan.symbol;
      request.volume       = plan.lot_size;
      request.type         = (plan.direction == AS_DIR_LONG ? ORDER_TYPE_BUY : ORDER_TYPE_SELL);
      request.price        = current;
      request.sl           = plan.stop_loss;
      request.tp           = plan.take_profit;
      request.deviation    = (ulong)MathMax(1.0, plan.max_drift_points);
      request.magic        = magic;
      request.comment      = comment;
      request.type_filling = probe.RequestTypeFilling();

      if(!OrderCheck(request, check))
        {
         reason = StringFormat("ORDER_CHECK_FAILED(%u:%s)", check.retcode, check.comment);
         return false;
        }

      return true;
     }
  };
