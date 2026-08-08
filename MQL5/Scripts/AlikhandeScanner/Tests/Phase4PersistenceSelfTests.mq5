#property strict
#property script_show_inputs

#include <AlikhandeScanner/Core/RuntimeContext.mqh>
#include <AlikhandeScanner/Persistence/DatabasePolicyV13.mqh>
#include <AlikhandeScanner/Persistence/Database.mqh>

int g_failures=0;
void Check(const bool condition,const string name){if(condition)Print("PASS ",name);else{Print("FAIL ",name);g_failures++;}}

void OnStart(){
   AS_RuntimeContext terminal;ZeroMemory(terminal);terminal.kind=AS_RUNTIME_TERMINAL;terminal.identity="terminal";
   AS_RuntimeContext tester=terminal;tester.kind=AS_RUNTIME_TESTER;tester.is_tester=true;tester.identity="tester";
   AS_RuntimeContext opt=tester;opt.kind=AS_RUNTIME_OPTIMIZATION;opt.is_optimization=true;opt.identity="optimization";
   AS_DatabasePolicyV13 policy;
   string prod=policy.FileName(terminal),test=policy.FileName(tester),optimization=policy.FileName(opt);
   Check(prod!=test,"terminal and tester database names differ");
   Check(prod!=optimization,"terminal and optimization database names differ");
   Check(test!=optimization,"tester and optimization database names differ");
   Check(policy.IsProductionHistory(terminal),"terminal is production-history context");
   Check(!policy.IsProductionHistory(tester),"tester is not production-history context");
   Check(!policy.IsProductionHistory(opt),"optimization is not production-history context");

   AS_Database db;bool opened=db.Open();Check(opened,"database opens in current runtime context");
   if(opened){Check(db.Ready(),"database ready after migration");Check(db.FileName()!="","database exposes runtime-specific filename");db.Close();}

   if(g_failures==0)Print("PHASE4_SELFTEST PASS");else PrintFormat("PHASE4_SELFTEST FAIL failures=%d",g_failures);
}
