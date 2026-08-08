//+------------------------------------------------------------------+
//| RiskPlanner.mqh                                                    |
//| Converts a Candidate into a sized TradePlan. Per                  |
//| docs/v1.1.0_ACCEPTANCE_TESTS.md "Risk Gate":                       |
//|  - a raw lot below broker minimum REJECTS the plan (never bumps   |
//|    risk to force a fillable lot)                                   |
//|  - normalized lot cannot exceed requested monetary risk by more   |
//|    than 1% rounding tolerance                                      |
//| v1.2.0 addition: consults Risk/PortfolioRisk.mqh before accepting. |
//+------------------------------------------------------------------+
#property strict
#include "../Domain/Models.mqh"
#include "../Broker/SymbolSpec.mqh"
#include "../Risk/PortfolioRisk.mqh"

struct RiskPlanResult
  {
   bool   accepted;
   string rejectReason;
   double lot;
   double riskMoney;
   double riskPct;
  };

//+------------------------------------------------------------------+
//| Pure sizing math: given a risk percentage and the stop distance,  |
//| compute the lot, then reject (not clamp-up) if it falls below the |
//| broker's minimum tradable volume.                                  |
//+------------------------------------------------------------------+
RiskPlanResult ComputeTradePlan(const string symbol, const double entry, const double sl,
                                 const double riskPct)
  {
   RiskPlanResult r;
   r.accepted = false;
   r.lot = 0.0;

   SymbolSpecSnapshot spec = FetchSymbolSpec(symbol);
   if(!spec.ready)
     {
      r.rejectReason = "symbol spec not ready";
      return r;
     }

   double equity = AccountInfoDouble(ACCOUNT_EQUITY);
   double riskMoney = equity * (riskPct / 100.0);

   double stopDistance = MathAbs(entry - sl);
   if(stopDistance <= 0.0 || spec.tickSize <= 0.0)
     {
      r.rejectReason = "invalid stop distance";
      return r;
     }

   double lossPerLot = (stopDistance / spec.tickSize) * spec.tickValue;
   if(lossPerLot <= 0.0)
     {
      r.rejectReason = "cannot price stop distance for this symbol";
      return r;
     }

   double rawLot = riskMoney / lossPerLot;

   if(rawLot < spec.volumeMin)
     {
      r.rejectReason = StringFormat("raw lot %.4f below broker minimum %.2f — plan rejected, "
                                     "not risk-increased", rawLot, spec.volumeMin);
      return r;
     }

   double steps = MathFloor((rawLot - spec.volumeMin) / spec.volumeStep);
   double normalizedLot = spec.volumeMin + steps * spec.volumeStep;
   normalizedLot = MathMin(normalizedLot, spec.volumeMax);

   double actualRiskMoney = normalizedLot * lossPerLot;
   double overshootPct = (actualRiskMoney - riskMoney) / riskMoney * 100.0;
   if(overshootPct > 1.0)
     {
      r.rejectReason = StringFormat("normalized lot overshoots requested risk by %.2f%% "
                                     "(tolerance 1%%)", overshootPct);
      return r;
     }

   r.accepted = true;
   r.lot = normalizedLot;
   r.riskMoney = actualRiskMoney;
   r.riskPct = actualRiskMoney / equity * 100.0;
   return r;
  }

//+------------------------------------------------------------------+
//| Full plan build: sizing + portfolio exposure gate. This is the    |
//| function callers should use — ComputeTradePlan alone doesn't know |
//| about open positions.                                              |
//+------------------------------------------------------------------+
RiskPlanResult BuildRiskPlan(const string symbol, const double entry, const double sl,
                              const double riskPct, const PortfolioRiskLimits &portfolioLimits,
                              const long magicNumber, const double dailyUsedRiskPct)
  {
   RiskPlanResult r = ComputeTradePlan(symbol, entry, sl, riskPct);
   if(!r.accepted)
      return r;

   PortfolioRiskGateResult gate = EvaluatePortfolioRiskGate(symbol, r.riskPct, portfolioLimits,
                                                             magicNumber, dailyUsedRiskPct);
   if(!gate.allowed)
     {
      r.accepted = false;
      r.rejectReason = gate.blockReason;
     }
   return r;
  }
