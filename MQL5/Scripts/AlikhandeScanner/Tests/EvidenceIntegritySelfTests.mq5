#property strict
#property script_show_inputs

#include <AlikhandeScanner/Core/VersionInfo.mqh>
#include <AlikhandeScanner/Core/Hash.mqh>
#include <AlikhandeScanner/Persistence/Database.mqh>
#include <AlikhandeScanner/Persistence/ReadModels.mqh>

int g_failures=0;
void Check(const bool condition,const string name){if(condition)Print("PASS ",name);else{Print("FAIL ",name);g_failures++;}}

void OnStart(){
   Check(AS_SCHEMA_VERSION>=6,"schema version includes scoped outcome provenance");
   Check((int)AS_OUTCOME_SOURCE_SHADOW!=(int)AS_OUTCOME_SOURCE_DEMO,"shadow and demo evidence sources are distinct");

   string structural="candidate-123";
   string a=AS_Fnv1a(structural+"|param-A|spec-X");
   string b=AS_Fnv1a(structural+"|param-B|spec-X");
   string c=AS_Fnv1a(structural+"|param-A|spec-Y");
   Check(a!=b,"parameter hash changes evidence identity");
   Check(a!=c,"broker spec changes evidence identity");

   AS_Database db;bool opened=db.Open();Check(opened,"database opens and migrates to current schema");
   if(opened){
      int q=DatabasePrepare(db.Handle(),"SELECT evidence_source,rule_version,scoring_version,parameter_hash,broker_spec_hash,execution_id FROM outcomes LIMIT 0");
      Check(q!=INVALID_HANDLE,"outcomes provenance columns are queryable");
      if(q!=INVALID_HANDLE)DatabaseFinalize(q);

      AS_ReadModels read;read.Attach(db);
      int total=0,wins=0,losses=0;double wr=0,avg=0,lo=0,hi=0;
      Check(!read.OutcomeStats(AS_OUTCOME_SOURCE_UNKNOWN,AS_RULE_VERSION,AS_SCORING_VERSION,"x",total,wins,losses,wr,avg,lo,hi),"unscoped outcome statistics are refused");
      db.Close();
   }

   if(g_failures==0)Print("EVIDENCE_INTEGRITY_SELFTEST PASS");else PrintFormat("EVIDENCE_INTEGRITY_SELFTEST FAIL failures=%d",g_failures);
}
