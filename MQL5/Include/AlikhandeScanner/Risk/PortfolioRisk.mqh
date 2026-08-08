#pragma once
#include "../Core/Config.mqh"

struct AS_PortfolioRiskSnapshotV13
  {
   double scanner_risk_pct;
   int scanner_positions;
   int foreign_positions;
   bool scanner_unbounded_risk;
   string reasons;
  };

class AS_PortfolioRisk {
public:
   bool Snapshot(const ulong magic,AS_PortfolioRiskSnapshotV13 &out){
      ZeroMemory(out);
      const double equity=AccountInfoDouble(ACCOUNT_EQUITY);
      if(equity<=0.0){out.scanner_unbounded_risk=true;out.scanner_risk_pct=100.0;out.reasons="INVALID_EQUITY;";return false;}
      double risk_amount=0.0;
      for(int i=PositionsTotal()-1;i>=0;i--){
         const ulong ticket=PositionGetTicket(i);if(ticket==0)continue;
         const ulong position_magic=(ulong)PositionGetInteger(POSITION_MAGIC);
         if(position_magic!=magic){out.foreign_positions++;continue;}
         out.scanner_positions++;
         const string sym=PositionGetString(POSITION_SYMBOL);
         const double volume=PositionGetDouble(POSITION_VOLUME);
         const double open=PositionGetDouble(POSITION_PRICE_OPEN);
         const double sl=PositionGetDouble(POSITION_SL);
         if(sl<=0.0){out.scanner_unbounded_risk=true;out.reasons+="SCANNER_POSITION_WITHOUT_SL:"+sym+";";continue;}
         const long type=PositionGetInteger(POSITION_TYPE);
         const ENUM_ORDER_TYPE ot=(type==POSITION_TYPE_BUY?ORDER_TYPE_BUY:ORDER_TYPE_SELL);
         double loss=0.0;
         if(!OrderCalcProfit(ot,sym,volume,open,sl,loss)){
            out.scanner_unbounded_risk=true;
            out.reasons+="RISK_CALC_FAILED:"+sym+";";
            continue;
         }
         risk_amount+=MathAbs(loss);
      }
      out.scanner_risk_pct=100.0*risk_amount/equity;
      if(out.foreign_positions>0)
         out.reasons+=StringFormat("FOREIGN_EXPOSURE_INFORMATIONAL:%d;",out.foreign_positions);
      return !out.scanner_unbounded_risk;
   }

   double ScannerOpenRiskPct(const ulong magic){
      AS_PortfolioRiskSnapshotV13 snapshot;
      Snapshot(magic,snapshot);
      if(snapshot.scanner_unbounded_risk)return 100.0;
      return snapshot.scanner_risk_pct;
   }

   bool AllowNewRisk(const double new_risk_pct,const double max_total_pct,const ulong magic,string &reason){
      reason="";
      AS_PortfolioRiskSnapshotV13 snapshot;
      Snapshot(magic,snapshot);
      if(snapshot.scanner_unbounded_risk){reason="UNBOUNDED_SCANNER_RISK;"+snapshot.reasons;return false;}
      if(new_risk_pct<=0.0){reason="INVALID_NEW_RISK";return false;}
      if(snapshot.scanner_risk_pct+new_risk_pct>max_total_pct){
         reason=StringFormat("TOTAL_OPEN_RISK %.2f+%.2f>%.2f",snapshot.scanner_risk_pct,new_risk_pct,max_total_pct);
         return false;
      }
      return true;
   }
};
