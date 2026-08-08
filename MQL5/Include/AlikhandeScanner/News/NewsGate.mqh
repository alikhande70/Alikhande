#pragma once
#include "../Core/Config.mqh"
class AS_NewsGate {
private:
   string Ccy1(const string symbol){if(StringLen(symbol)>=3)return StringSubstr(symbol,0,3);return "";}
   string Ccy2(const string symbol){if(StringLen(symbol)>=6)return StringSubstr(symbol,3,3);return "";}
   bool Relevant(const string symbol,const string currency){if(StringFind(symbol,"XAU")>=0||StringFind(symbol,"GOLD")>=0)return currency=="USD";return currency==Ccy1(symbol)||currency==Ccy2(symbol);}
public:
   bool BlockedNow(const string symbol,const int before_min,const int after_min,string &reason){reason="";if((bool)MQLInfoInteger(MQL_TESTER)){reason="NEWS_TESTER_DATASET_NOT_LOADED";return false;}datetime now=TimeTradeServer();datetime from=now-before_min*60;datetime to=now+after_min*60;MqlCalendarValue values[];int count=CalendarValueHistory(values,from,to,NULL,NULL);if(count<0){reason="NEWS_API_UNAVAILABLE";return false;}for(int i=0;i<count;i++){MqlCalendarEvent ev;if(!CalendarEventById(values[i].event_id,ev))continue;if(ev.importance!=CALENDAR_IMPORTANCE_HIGH)continue;MqlCalendarCountry country;if(!CalendarCountryById(ev.country_id,country))continue;if(!Relevant(symbol,country.currency))continue;datetime t=values[i].time;if(t>=from&&t<=to){reason=StringFormat("HIGH_IMPACT_%s_%s",country.currency,ev.name);return true;}}return false;}
};
