#property strict
#property script_show_inputs

#include <AlikhandeScanner/News/CalendarProviderV13.mqh>
#include <AlikhandeScanner/UI/Dashboard.mqh>

int g_failures=0;
void Check(const bool condition,const string name){if(condition)Print("PASS ",name);else{Print("FAIL ",name);g_failures++;}}

void OnStart(){
   AS_CalendarProviderV13 provider;
   AS_RuntimeContext tester;ZeroMemory(tester);tester.kind=AS_RUNTIME_TESTER;tester.is_tester=true;tester.identity="selftest";
   AS_NewsStateV13 news;provider.Evaluate(tester,"XAUUSD",15,10,news);
   Check(news.source==AS_NEWS_SOURCE_UNAVAILABLE,"tester does not reuse live calendar source");
   Check(!news.available,"tester calendar unavailable without explicit dataset");
   Check(news.reason=="TESTER_CALENDAR_DATASET_NOT_LOADED","tester unavailability reason explicit");

   AS_Dashboard ui;ui.Build();
   ui.SetTab(AS_TAB_NEWS);
   Check(ui.Tab()==AS_TAB_NEWS,"dashboard exposes dedicated News tab");
   ui.News(news,"XAUUSD");
   ui.Clear();

   if(g_failures==0)Print("PHASE7_SELFTEST PASS");else PrintFormat("PHASE7_SELFTEST FAIL failures=%d",g_failures);
}
