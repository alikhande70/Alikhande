#pragma once
#include "../Domain/Models.mqh"

// Pre-trade permission and distance checks.
//
// These are the cheap, deterministic refusals — the ones that can be answered
// from terminal and symbol state without touching the trade server. Anything
// requiring the server's opinion belongs in Preflight.

class AS_TradeGuards
  {
public:
   // Any position or pending order on this symbol from this EA. Magic-filtered:
   // the scanner must not refuse to trade because a human has a manual position
   // open, and must not treat someone else's order as its own.
   bool HasExposure(const string symbol, const ulong magic) const
     {
      for(int i = PositionsTotal() - 1; i >= 0; i--)
        {
         const ulong ticket = PositionGetTicket(i);
         if(ticket == 0)
            continue;
         if(PositionGetString(POSITION_SYMBOL) == symbol
            && (ulong)PositionGetInteger(POSITION_MAGIC) == magic)
            return true;
        }
      for(int i = OrdersTotal() - 1; i >= 0; i--)
        {
         const ulong ticket = OrderGetTicket(i);
         if(ticket == 0)
            continue;
         if(OrderGetString(ORDER_SYMBOL) == symbol
            && (ulong)OrderGetInteger(ORDER_MAGIC) == magic)
            return true;
        }
      return false;
     }

   // Any position on this symbol regardless of origin. Reported separately so
   // the operator can see that a manual trade overlaps a scanner signal.
   bool HasForeignExposure(const string symbol, const ulong magic) const
     {
      for(int i = PositionsTotal() - 1; i >= 0; i--)
        {
         const ulong ticket = PositionGetTicket(i);
         if(ticket == 0)
            continue;
         if(PositionGetString(POSITION_SYMBOL) == symbol
            && (ulong)PositionGetInteger(POSITION_MAGIC) != magic)
            return true;
        }
      return false;
     }

   bool TradePermissions(const string symbol, string &codes) const
     {
      bool ok = true;
      if(!TerminalInfoInteger(TERMINAL_TRADE_ALLOWED))
        { ok = false; codes += "TERMINAL_TRADE_DISABLED;"; }
      if(!MQLInfoInteger(MQL_TRADE_ALLOWED))
        { ok = false; codes += "MQL_TRADE_DISABLED;"; }
      if(!AccountInfoInteger(ACCOUNT_TRADE_ALLOWED))
        { ok = false; codes += "ACCOUNT_TRADE_DISABLED;"; }

      const long mode = SymbolInfoInteger(symbol, SYMBOL_TRADE_MODE);
      if(mode == SYMBOL_TRADE_MODE_DISABLED || mode == SYMBOL_TRADE_MODE_CLOSEONLY)
        { ok = false; codes += "SYMBOL_TRADE_DISABLED;"; }

      return ok;
     }

   // Stops must clear BOTH the stops level and the freeze level. v1.1.0 read
   // the freeze level into its spec struct and then never checked it; inside
   // the freeze band the server rejects modification and closure, which is a
   // materially different failure from a too-tight stop.
   bool StopsValid(const AS_TradePlan &plan, string &codes) const
     {
      const double point = SymbolInfoDouble(plan.symbol, SYMBOL_POINT);
      if(point <= 0.0)
        {
         codes += "NO_POINT;";
         return false;
        }

      const int stops_level  = (int)SymbolInfoInteger(plan.symbol, SYMBOL_TRADE_STOPS_LEVEL);
      const int freeze_level = (int)SymbolInfoInteger(plan.symbol, SYMBOL_TRADE_FREEZE_LEVEL);
      const double required = MathMax(stops_level, freeze_level) * point;

      if(required <= 0.0)
         return true;   // broker imposes no minimum distance

      bool ok = true;
      if(plan.stop_loss > 0.0 && MathAbs(plan.entry - plan.stop_loss) < required)
        {
         ok = false;
         codes += StringFormat("SL_INSIDE_BROKER_LEVEL(%.0f pts);", required / point);
        }
      if(plan.take_profit > 0.0 && MathAbs(plan.take_profit - plan.entry) < required)
        {
         ok = false;
         codes += StringFormat("TP_INSIDE_BROKER_LEVEL(%.0f pts);", required / point);
        }
      return ok;
     }
  };
