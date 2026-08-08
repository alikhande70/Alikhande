#property strict
#property script_show_inputs

#include <AlikhandeScanner/Core/RuntimeContext.mqh>
#include <AlikhandeScanner/Data/RuntimeSnapshots.mqh>

int g_failures=0;

void Check(const bool condition,const string name)
  {
   if(condition)
      Print("PASS ",name);
   else
     {
      Print("FAIL ",name);
      g_failures++;
     }
  }

void OnStart()
  {
   AS_RuntimeContextReader runtime_reader;
   AS_RuntimeContext runtime;
   runtime_reader.Read(runtime);
   Check(runtime.identity!="","runtime identity is explicit");
   Check(!(runtime.kind==AS_RUNTIME_TERMINAL && runtime.is_tester),"terminal context is not tester");
   Check(!(runtime.kind==AS_RUNTIME_OPTIMIZATION && !runtime.is_optimization),"optimization context is self-consistent");

   AS_RuntimeSnapshots snapshots;
   AS_ClosedBarSnapshot invalid_forming;
   Check(!snapshots.ClosedBar(_Symbol,PERIOD_M5,0,invalid_forming),"forming bar rejected from structural snapshot");

   AS_ClosedBarSnapshot a,b;
   bool first=snapshots.ClosedBar(_Symbol,PERIOD_M5,1,a);
   bool second=snapshots.ClosedBar(_Symbol,PERIOD_M5,1,b);
   Check(first&&second,"closed bar snapshot available");
   if(first&&second)
     {
      Check(a.valid&&b.valid,"closed bar snapshots valid");
      Check(a.structural_id==b.structural_id,"same closed bar has deterministic structural identity");
      Check(a.bar_time==b.bar_time,"closed bar timestamp stable");
     }

   AS_QuoteState q;
   bool quote_ok=snapshots.Quote(_Symbol,10,q);
   Check(!quote_ok || q.symbol==_Symbol,"quote state is symbol scoped");
   Check(!quote_ok || q.ask>=q.bid,"quote spread is non-negative");

   if(g_failures==0)
      Print("PHASE1_SELFTEST PASS");
   else
      PrintFormat("PHASE1_SELFTEST FAIL failures=%d",g_failures);
  }
