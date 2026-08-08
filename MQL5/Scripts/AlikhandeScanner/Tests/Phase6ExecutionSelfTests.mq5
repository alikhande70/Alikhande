#property strict
#property script_show_inputs

#include <AlikhandeScanner/Persistence/Database.mqh>
#include <AlikhandeScanner/Execution/DealLedgerV13.mqh>
#include <AlikhandeScanner/Execution/ReconcilerV13.mqh>

int g_failures=0;
void Check(const bool condition,const string name){if(condition)Print("PASS ",name);else{Print("FAIL ",name);g_failures++;}}

void OnStart(){
   AS_Database db;bool opened=db.Open();Check(opened,"database available for execution safety test");
   if(opened){
      AS_DealLedgerV13 ledger;ledger.Attach(db);
      const ulong synthetic=(ulong)(900000000000000000+((ulong)TimeCurrent()%100000000));
      bool first=ledger.Admit(synthetic,"SELFTEST","SELFTEST",0,0.10,1.0,0.0);
      bool second=ledger.Admit(synthetic,"SELFTEST","SELFTEST",0,0.10,1.0,0.0);
      Check(first,"first deal ticket admitted");
      Check(!second,"duplicate deal ticket rejected before state mutation");
   }

   AS_ExecutionRecord empty;ZeroMemory(empty);AS_ReconcileResultV13 rebuilt;AS_ReconcilerV13 reconciler;
   Check(!reconciler.Rebuild(empty,AS_MAGIC,rebuilt),"reconciler refuses execution without symbol");
   Check(rebuilt.reason=="NO_SYMBOL","reconciler exposes failure reason");

   if(opened)db.Close();
   if(g_failures==0)Print("PHASE6_SELFTEST PASS");else PrintFormat("PHASE6_SELFTEST FAIL failures=%d",g_failures);
}
