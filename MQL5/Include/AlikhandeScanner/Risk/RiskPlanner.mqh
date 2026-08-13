#pragma once
#include "../Domain/Models.mqh"
#include "../Core/Config.mqh"
#include "PortfolioRisk.mqh"

// Turns a confirmed signal into a sized, validated trade plan.
//
// The discipline inherited from v1.1.0 and kept deliberately: when the risk
// budget buys less than the broker's minimum lot, the plan is REJECTED. It is
// never rounded up to the minimum. Rounding up silently converts "risk 0.25%"
// into whatever the minimum lot happens to cost, which on a small account can
// be several times the intended risk — the single most common way a careful
// risk model gets quietly defeated.

class AS_RiskPlanner
  {
private:
   AS_PortfolioRisk m_portfolio;

   int VolumeDigits(const double step) const
     {
      int digits = 0;
      double value = step;
      while(digits < 8 && MathAbs(value - MathRound(value)) > 1e-8)
        {
         value *= 10.0;
         digits++;
        }
      return digits;
     }

   bool NormalizeVolume(const string symbol, const double raw,
                        double &normalized, string &code) const
     {
      const double minimum = SymbolInfoDouble(symbol, SYMBOL_VOLUME_MIN);
      const double maximum = SymbolInfoDouble(symbol, SYMBOL_VOLUME_MAX);
      const double step    = SymbolInfoDouble(symbol, SYMBOL_VOLUME_STEP);

      if(step <= 0.0 || minimum <= 0.0 || maximum < minimum)
        {
         code = "INVALID_VOLUME_SPEC";
         return false;
        }
      if(raw < minimum)
        {
         code = StringFormat("RISK_BELOW_BROKER_MIN_VOLUME(%.4f<%.2f)", raw, minimum);
         return false;
        }

      // Round DOWN. Rounding to nearest can exceed the risk budget by up to
      // half a step, which on a 0.01-step symbol with a tight stop is material.
      normalized = MathFloor(raw / step + 1e-9) * step;
      normalized = NormalizeDouble(normalized, VolumeDigits(step));

      if(normalized < minimum || normalized > maximum)
        {
         code = StringFormat("VOLUME_OUT_OF_RANGE(%.4f)", normalized);
         return false;
        }
      return true;
     }

public:
   // `risk_percent` is per-trade risk. Portfolio caps are applied on top; a
   // plan that fits its own budget but breaches an aggregate cap is rejected
   // with the breached cap named.
   bool Build(const AS_SignalCandidate &s, const double risk_percent,
              const int ttl_seconds, const double max_drift_points,
              const double max_open_pct, const double max_currency_pct,
              const double max_class_pct, const ulong magic,
              AS_TradePlan &plan)
     {
      ZeroMemory(plan);
      plan.valid = false;

      if(s.direction == AS_DIR_NONE || s.hard_blocked)
        {
         plan.validation_codes = "NO_ACTIONABLE_SIGNAL";
         return false;
        }
      if(risk_percent <= 0.0 || risk_percent > AS_MAXIMUM_RISK_PERCENT)
        {
         plan.validation_codes = StringFormat("RISK_PERCENT_OUT_OF_POLICY(%.2f)", risk_percent);
         return false;
        }
      if(s.stop_loss <= 0.0 || s.preferred_entry <= 0.0)
        {
         plan.validation_codes = "NO_STRUCTURAL_STOP";
         return false;
        }

      const double equity = AccountInfoDouble(ACCOUNT_EQUITY);
      if(equity <= 0.0)
        {
         plan.validation_codes = "NO_EQUITY";
         return false;
        }
      const double risk_amount = equity * risk_percent / 100.0;

      const ENUM_ORDER_TYPE order_type =
         (s.direction == AS_DIR_LONG ? ORDER_TYPE_BUY : ORDER_TYPE_SELL);

      // OrderCalcProfit prices the stop through the broker's own conversion
      // chain, which is the only way to get this right for a cross-currency
      // symbol on an account denominated in a third currency.
      double loss_per_lot = 0.0;
      if(!OrderCalcProfit(order_type, s.symbol, 1.0,
                          s.preferred_entry, s.stop_loss, loss_per_lot))
        {
         plan.validation_codes = "ORDER_CALC_PROFIT_FAILED";
         return false;
        }
      loss_per_lot = MathAbs(loss_per_lot);
      if(loss_per_lot <= 0.0)
        {
         plan.validation_codes = "ZERO_LOSS_PER_LOT";
         return false;
        }

      double lot = 0.0;
      string code = "";
      if(!NormalizeVolume(s.symbol, risk_amount / loss_per_lot, lot, code))
        {
         plan.validation_codes = code;
         return false;
        }

      double actual_loss = 0.0;
      if(!OrderCalcProfit(order_type, s.symbol, lot,
                          s.preferred_entry, s.stop_loss, actual_loss))
        {
         plan.validation_codes = "ORDER_CALC_PROFIT_FAILED";
         return false;
        }
      actual_loss = MathAbs(actual_loss);

      // Rounding may only ever move risk DOWN, within a small tolerance.
      if(actual_loss > risk_amount * AS_RISK_ROUNDING_TOLERANCE)
        {
         plan.validation_codes = StringFormat("NORMALIZED_VOLUME_EXCEEDS_RISK(%.2f>%.2f)",
                                              actual_loss, risk_amount);
         return false;
        }

      double margin = 0.0;
      if(!OrderCalcMargin(order_type, s.symbol, lot, s.preferred_entry, margin))
        {
         plan.validation_codes = "ORDER_CALC_MARGIN_FAILED";
         return false;
        }
      if(margin > AccountInfoDouble(ACCOUNT_MARGIN_FREE))
        {
         plan.validation_codes = "INSUFFICIENT_FREE_MARGIN";
         return false;
        }

      // Aggregate exposure, measured against what this EA already holds.
      const double actual_risk_pct = actual_loss / equity * 100.0;
      const AS_ExposureSummary exposure = m_portfolio.Summarise(s.symbol, magic);
      string exposure_reason = "";
      if(!m_portfolio.Allows(exposure, actual_risk_pct, max_open_pct,
                             max_currency_pct, max_class_pct, exposure_reason))
        {
         plan.validation_codes = exposure_reason;
         return false;
        }

      plan.plan_id            = s.signal_id + "_PLAN";
      plan.signal_id          = s.signal_id;
      plan.symbol             = s.symbol;
      plan.direction          = s.direction;
      plan.entry              = s.preferred_entry;
      plan.stop_loss          = s.stop_loss;
      plan.take_profit        = s.take_profit;
      plan.risk_percent       = risk_percent;
      plan.risk_amount        = risk_amount;
      plan.actual_risk_amount = actual_loss;
      plan.lot_size           = lot;
      plan.margin_required    = margin;
      plan.created_at         = TimeCurrent();
      plan.expires_at         = plan.created_at + ttl_seconds;
      plan.max_drift_points   = max_drift_points;
      plan.minimum_rr         = AS_MINIMUM_RISK_REWARD;
      plan.preview_bid        = SymbolInfoDouble(s.symbol, SYMBOL_BID);
      plan.preview_ask        = SymbolInfoDouble(s.symbol, SYMBOL_ASK);
      plan.validation_codes   = "";
      plan.valid              = true;
      return true;
     }

   AS_ExposureSummary Exposure(const string symbol, const ulong magic) const
     {
      return m_portfolio.Summarise(symbol, magic);
     }
  };
