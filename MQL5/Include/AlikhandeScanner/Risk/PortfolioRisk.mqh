#pragma once
#include "../Domain/Models.mqh"
#include "../Core/Config.mqh"

// Aggregate exposure.
//
// v1.1.0 checked risk per trade and exposure per symbol, and stopped there.
// That misses the way a scanner actually goes wrong: EURUSD long, GBPUSD long
// and XAUUSD long are not three independent 0.25% bets, they are one ~0.75%
// bet that the dollar weakens. This module measures the aggregate.
//
// A breach BLOCKS the new trade. It never silently resizes it: a position the
// operator did not ask for is its own kind of surprise, and a blocked trade
// with a stated reason is information whereas a shrunken one is noise.

class AS_PortfolioRisk
  {
private:
   // Currency legs, tolerating broker decoration (`EURUSD_o`, `#GBPJPY`).
   void CurrencyLegs(const string symbol, string &base, string &quote) const
     {
      base = "";
      quote = "";
      string clean = symbol;
      if(StringLen(clean) > 0 && StringSubstr(clean, 0, 1) == "#")
         clean = StringSubstr(clean, 1);
      const int underscore = StringFind(clean, "_");
      if(underscore >= 6)
         clean = StringSubstr(clean, 0, underscore);
      if(StringLen(clean) >= 6)
        {
         base = StringSubstr(clean, 0, 3);
         quote = StringSubstr(clean, 3, 3);
        }
      else
        {
         base = clean;
        }
     }

   // Defined risk of one open position, in account currency.
   //
   // `bounded` is an OUTPUT, not a courtesy. A position with no stop, or one
   // whose symbol cannot be priced, has no computable worst case — and a
   // position with no computable worst case is not a position with zero risk.
   // Returning 0.0 and moving on (which this code used to do) makes an
   // unbounded position read as *free* to every downstream cap, which is the
   // most dangerous way a risk limit can fail: the more exposed the account
   // actually is, the more room the caps appear to have.
   double PositionRisk(const string symbol, const double open_price,
                       const double stop_loss, const double volume,
                       bool &bounded) const
     {
      bounded = false;
      if(stop_loss <= 0.0)
         return 0.0;
      const double tick_value = SymbolInfoDouble(symbol, SYMBOL_TRADE_TICK_VALUE);
      const double tick_size  = SymbolInfoDouble(symbol, SYMBOL_TRADE_TICK_SIZE);
      if(tick_size <= 0.0 || tick_value <= 0.0)
         return 0.0;
      bounded = true;
      return MathAbs(open_price - stop_loss) / tick_size * tick_value * volume;
     }

public:
   ENUM_AS_ASSET_CLASS AssetClass(const string symbol) const
     {
      string upper = symbol;
      StringToUpper(upper);
      if(StringFind(upper, "XAU") >= 0 || StringFind(upper, "XAG") >= 0
         || StringFind(upper, "XPT") >= 0 || StringFind(upper, "XPD") >= 0)
         return AS_ASSET_METAL;
      if(StringFind(upper, "BTC") >= 0 || StringFind(upper, "ETH") >= 0)
         return AS_ASSET_CRYPTO;
      string base = "", quote = "";
      CurrencyLegs(symbol, base, quote);
      if(StringLen(base) == 3 && StringLen(quote) == 3)
         return AS_ASSET_FX;
      return AS_ASSET_UNKNOWN;
     }

   // Walks this EA's open positions and totals exposure. Positions belonging to
   // other EAs or opened by hand are excluded by magic number: the scanner may
   // only be held accountable for what it opened.
   AS_ExposureSummary Summarise(const string candidate_symbol, const ulong magic) const
     {
      AS_ExposureSummary out;
      ZeroMemory(out);

      const double equity = AccountInfoDouble(ACCOUNT_EQUITY);
      if(equity <= 0.0)
         return out;

      string candidate_base = "", candidate_quote = "";
      CurrencyLegs(candidate_symbol, candidate_base, candidate_quote);
      const ENUM_AS_ASSET_CLASS candidate_class = AssetClass(candidate_symbol);

      double total_risk = 0.0;
      double symbol_risk = 0.0;
      double base_risk = 0.0;
      double quote_risk = 0.0;
      double class_risk = 0.0;

      for(int i = PositionsTotal() - 1; i >= 0; i--)
        {
         const ulong ticket = PositionGetTicket(i);
         if(ticket == 0)
            continue;
         if((ulong)PositionGetInteger(POSITION_MAGIC) != magic)
            continue;

         const string symbol = PositionGetString(POSITION_SYMBOL);
         bool bounded = false;
         const double risk = PositionRisk(symbol,
                                          PositionGetDouble(POSITION_PRICE_OPEN),
                                          PositionGetDouble(POSITION_SL),
                                          PositionGetDouble(POSITION_VOLUME),
                                          bounded);
         out.open_positions++;
         if(!bounded)
           {
            out.unbounded_positions++;
            out.unbounded_symbols += symbol + ";";
           }
         total_risk += risk;

         if(symbol == candidate_symbol)
            symbol_risk += risk;

         string base = "", quote = "";
         CurrencyLegs(symbol, base, quote);
         if(candidate_base != "" && (base == candidate_base || quote == candidate_base))
            base_risk += risk;
         if(candidate_quote != "" && (base == candidate_quote || quote == candidate_quote))
            quote_risk += risk;

         if(AssetClass(symbol) == candidate_class)
            class_risk += risk;
        }

      out.open_risk_pct         = total_risk  / equity * 100.0;
      out.symbol_risk_pct       = symbol_risk / equity * 100.0;
      out.asset_class_risk_pct  = class_risk  / equity * 100.0;

      // The binding constraint is whichever leg is more concentrated.
      if(base_risk >= quote_risk)
        {
         out.currency_risk_pct = base_risk / equity * 100.0;
         out.dominant_currency = candidate_base;
        }
      else
        {
         out.currency_risk_pct = quote_risk / equity * 100.0;
         out.dominant_currency = candidate_quote;
        }

      return out;
     }

   // Returns true when the new trade fits inside every cap. `reason` carries
   // the first breached cap, phrased for display.
   bool Allows(const AS_ExposureSummary &exposure, const double new_risk_pct,
               const double max_open_pct, const double max_currency_pct,
               const double max_class_pct, string &reason) const
     {
      reason = "";

      // Checked before every cap. With an unbounded position open, every
      // percentage below is a lower bound on true exposure, so comparing them
      // against a limit is meaningless — the limit would pass precisely
      // because the dangerous position is invisible to it.
      if(exposure.unbounded_positions > 0)
        {
         reason = StringFormat("UNBOUNDED_RISK %d position(s) without a computable "
                               "worst case: %s", exposure.unbounded_positions,
                               exposure.unbounded_symbols);
         return false;
        }

      if(exposure.open_risk_pct + new_risk_pct > max_open_pct)
        {
         reason = StringFormat("OPEN_RISK %.2f%%+%.2f%% > %.2f%%",
                               exposure.open_risk_pct, new_risk_pct, max_open_pct);
         return false;
        }
      if(exposure.currency_risk_pct + new_risk_pct > max_currency_pct)
        {
         reason = StringFormat("%s_EXPOSURE %.2f%%+%.2f%% > %.2f%%",
                               exposure.dominant_currency == "" ? "CURRENCY" : exposure.dominant_currency,
                               exposure.currency_risk_pct, new_risk_pct, max_currency_pct);
         return false;
        }
      if(exposure.asset_class_risk_pct + new_risk_pct > max_class_pct)
        {
         reason = StringFormat("ASSET_CLASS %.2f%%+%.2f%% > %.2f%%",
                               exposure.asset_class_risk_pct, new_risk_pct, max_class_pct);
         return false;
        }
      return true;
     }
  };
