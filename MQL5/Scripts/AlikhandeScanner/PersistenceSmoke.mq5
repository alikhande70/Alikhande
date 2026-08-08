#property strict
#property version "1.20"
#include <AlikhandeScanner/Persistence/Database.mqh>
#include <AlikhandeScanner/Persistence/RiskStateStore.mqh>

void OnStart(){
   AS_Database db;
   if(!db.Open()){Print("FAIL persistence: database open/migrate");return;}
   AS_RiskStateStore store;store.Attach(db);
   AS_RiskStateSnapshot original;
   original.day_key=2099001;
   original.day_start_equity=10000.0;
   original.peak_equity=10125.0;
   original.consecutive_losses=3;
   original.updated_at=TimeCurrent();
   if(!store.Save(original)){Print("FAIL persistence: risk state save");db.Close();return;}
   AS_RiskStateSnapshot loaded;
   if(!store.Load(loaded)){Print("FAIL persistence: risk state load");db.Close();return;}
   bool ok=(loaded.day_key==original.day_key && MathAbs(loaded.day_start_equity-original.day_start_equity)<0.01 && MathAbs(loaded.peak_equity-original.peak_equity)<0.01 && loaded.consecutive_losses==original.consecutive_losses);
   Print(ok?"PASS persistence risk-state roundtrip":"FAIL persistence risk-state mismatch");
   db.Close();
}
