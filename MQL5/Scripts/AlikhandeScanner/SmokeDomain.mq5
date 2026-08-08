#property strict
#include <AlikhandeScanner/Core/Hash.mqh>
#include <AlikhandeScanner/Statistics/Statistics.mqh>
void OnStart(){AS_Statistics s;double lo=0,hi=0;bool ok=s.Wilson(60,100,lo,hi);if(!ok||lo<=0||hi<=lo)Print("FAIL Wilson");else PrintFormat("PASS Wilson %.4f %.4f hash=%s",lo,hi,AS_Fnv1a("alikhande"));}
