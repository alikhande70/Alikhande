#property strict
#property script_show_inputs

#include <AlikhandeScanner/Signal/ExplainableScoringV13.mqh>
#include <AlikhandeScanner/Signal/LifecycleV13.mqh>

int g_failures=0;
void Check(const bool condition,const string name){if(condition)Print("PASS ",name);else{Print("FAIL ",name);g_failures++;}}

void OnStart(){
   AS_ScoreComponentV13 c[];ArrayResize(c,3);
   c[0].code="H1_TREND";c[0].contribution=30;
   c[1].code="ZONE_QUALITY";c[1].contribution=25;
   c[2].code="M5_CONFIRM";c[2].contribution=20;
   string penalties[1]={"SPREAD_ELEVATED"};double values[1]={5.0};string vetoes[];
   AS_ExplainableScoringV13 engine;AS_ScoreResultV13 score;engine.Evaluate(c,penalties,values,vetoes,score);
   Check(score.raw_score==75.0,"raw score is sum of components");
   Check(score.final_score==70.0,"penalty is explicit subtraction");
   Check(!score.hard_blocked,"no veto means not hard blocked");
   Check(StringFind(score.positive_reasons,"H1_TREND")>=0,"score exposes component reason");

   string hard[1]={"NEWS_BLOCK"};engine.Evaluate(c,penalties,values,hard,score);
   Check(score.hard_blocked,"veto blocks independently of score");
   Check(StringFind(score.veto_codes,"NEWS_BLOCK")>=0,"veto reason is inspectable");

   AS_LifecycleV13 life;
   Check(life.CanTransition(AS_V13_CANDIDATE,AS_V13_CONFIRMED),"candidate -> confirmed allowed");
   Check(life.CanTransition(AS_V13_CONFIRMED,AS_V13_LIVE_BLOCKED),"confirmed -> live blocked allowed");
   Check(life.CanTransition(AS_V13_LIVE_BLOCKED,AS_V13_LIVE_TRADABLE),"blocked -> tradable recovery allowed");
   Check(life.CanTransition(AS_V13_LIVE_TRADABLE,AS_V13_ACTIVE),"tradable -> active allowed");
   Check(life.CanTransition(AS_V13_ACTIVE,AS_V13_TP),"active -> TP allowed");
   Check(!life.CanTransition(AS_V13_TP,AS_V13_ACTIVE),"terminal state cannot reopen");
   Check(!life.CanTransition(AS_V13_CANDIDATE,AS_V13_ACTIVE),"candidate cannot skip confirmation");

   if(g_failures==0)Print("PHASE3_SELFTEST PASS");else PrintFormat("PHASE3_SELFTEST FAIL failures=%d",g_failures);
}
