#pragma once

struct AS_PositionRiskInputV13
  {
   double risk_amount;
   bool bounded;
  };

class AS_RiskMathV13
  {
public:
   bool Aggregate(const AS_PositionRiskInputV13 &positions[],const double equity,double &risk_pct,string &reason) const
     {
      risk_pct=0.0;reason="";
      if(equity<=0.0){reason="INVALID_EQUITY";return false;}
      double total=0.0;
      for(int i=0;i<ArraySize(positions);i++){
         if(!positions[i].bounded){reason="UNBOUNDED_POSITION_RISK";return false;}
         total+=MathMax(0.0,positions[i].risk_amount);
      }
      risk_pct=100.0*total/equity;
      return true;
   }
  };
