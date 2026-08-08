#property strict
#include <AlikhandeScanner/Persistence/Database.mqh>
void OnStart(){AS_Database db;if(!db.Open()){Print("FAIL database open/migrate");return;}PrintFormat("PASS database schema=%d",AS_SCHEMA_VERSION);db.Close();}
