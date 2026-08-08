#property strict
#property script_show_inputs

#include <AlikhandeScanner/Risk/RiskMathV13.mqh>

int g_failures=0;
void Check(const bool condition,const string name){if(condition)Print("PASS ",name);else{Print("FAIL ",name);g_failures++;}}

void OnStart(){
   AS_RiskMathV13 math;
   AS_PositionRiskInputV13 a[3];
   a[0].risk_amount=100;a[0].bounded=true;
   a[1].risk_amount=50;a[1].bounded=true;
   a[2].risk_amount=25;a[2].bounded=true;
   double pct=0;string reason="";
   Check(math.Aggregate(a,10000,pct,reason),"bounded portfolio aggregates");
   Check(MathAbs(pct-1.75)<0.0001,"aggregate risk percent exact");

   AS_PositionRiskInputV13 b[3];
   b[0]=a[2];b[1]=a[0];b[2]=a[1];double pct2=0;string reason2="";
   Check(math.Aggregate(b,10000,pct2,reason2),"reordered portfolio aggregates");
   Check(MathAbs(pct-pct2)<0.0001,"portfolio aggregation is order-independent");

   b[1].bounded=false;
   Check(!math.Aggregate(b,10000,pct2,reason2),"unbounded position blocks portfolio risk");
   Check(reason2=="UNBOUNDED_POSITION_RISK","unbounded reason explicit");

   if(g_failures==0)Print("PHASE5_SELFTEST PASS");else PrintFormat("PHASE5_SELFTEST FAIL failures=%d",g_failures);
}
