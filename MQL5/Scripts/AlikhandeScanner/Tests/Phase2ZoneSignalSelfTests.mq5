#property strict
#property script_show_inputs

#include <AlikhandeScanner/Signal/SignalDomainV13.mqh>
#include <AlikhandeScanner/Signal/ZoneSemanticsV13.mqh>
#include <AlikhandeScanner/Signal/LiveValidatorV13.mqh>

int g_failures=0;
void Check(const bool condition,const string name){if(condition)Print("PASS ",name);else{Print("FAIL ",name);g_failures++;}}

AS_TypedZone DemandZone(){AS_TypedZone z;ZeroMemory(z);z.id="D1";z.symbol=_Symbol;z.timeframe=PERIOD_H1;z.kind=AS_ZONE_DEMAND;z.low=100.0;z.high=110.0;z.center=105.0;z.quality=80;z.valid=true;z.broken=false;return z;}
AS_TypedZone SupplyZone(){AS_TypedZone z=DemandZone();z.id="S1";z.kind=AS_ZONE_SUPPLY;return z;}

void OnStart(){
   AS_ZoneSemanticsV13 semantics;
   AS_TypedZone d=DemandZone();
   Check(semantics.Relation(d,99.0)==AS_ZONE_BELOW,"price below zone");
   Check(semantics.Relation(d,100.0)==AS_ZONE_INSIDE,"lower boundary is inside");
   Check(semantics.Relation(d,105.0)==AS_ZONE_INSIDE,"middle of zone is inside");
   Check(semantics.Relation(d,110.0)==AS_ZONE_INSIDE,"upper boundary is inside");
   Check(semantics.Relation(d,111.0)==AS_ZONE_ABOVE,"price above zone");
   d.broken=true;Check(semantics.Relation(d,105.0)==AS_ZONE_UNAVAILABLE,"broken zone unavailable");
   d=DemandZone();Check(semantics.IsUsableAnchor(d,AS_DIR_LONG),"demand anchors long");
   Check(!semantics.IsUsableAnchor(d,AS_DIR_SHORT),"demand cannot anchor short");
   AS_TypedZone s=SupplyZone();Check(semantics.IsUsableAnchor(s,AS_DIR_SHORT),"supply anchors short");

   AS_StructuralCandidateV13 c;ZeroMemory(c);c.candidate_id="C1";c.symbol=_Symbol;c.direction=AS_DIR_LONG;c.setup=AS_TREND_PULLBACK;c.anchor_zone_id="D1";c.anchor_zone_low=100;c.anchor_zone_high=110;c.structural_atr=20;c.structural_score=82;c.valid=true;
   AS_QuoteState q;ZeroMemory(q);q.symbol=_Symbol;q.bid=105;q.ask=106;q.point=0.01;q.fresh=true;q.data_state=AS_DATA_READY;
   AS_LiveValidationV13 out;AS_LiveValidatorV13 validator;
   Check(validator.Validate(c,d,q,2.0,out),"inside-zone live validation passes");
   Check(out.tradable,"inside-zone candidate tradable");
   Check(out.entry==106,"long entry uses live ask");
   Check(out.take_profit>out.entry,"long TP above entry");

   q.bid=120;q.ask=121;AS_LiveValidationV13 moved;
   Check(!validator.Validate(c,d,q,2.0,moved),"same structure revalidates false after quote leaves zone");
   Check(moved.candidate_id==c.candidate_id,"live quote does not change structural candidate identity");

   if(g_failures==0)Print("PHASE2_SELFTEST PASS");else PrintFormat("PHASE2_SELFTEST FAIL failures=%d",g_failures);
}
