#pragma once
#include "../Core/RuntimeContext.mqh"

enum ENUM_AS_NEWS_SOURCE_V13
  {
   AS_NEWS_SOURCE_LIVE = 0,
   AS_NEWS_SOURCE_TEST_DATA = 1,
   AS_NEWS_SOURCE_UNAVAILABLE = 2
  };

struct AS_NewsStateV13
  {
   ENUM_AS_NEWS_SOURCE_V13 source;
   bool blocked;
   bool available;
   string reason;
   datetime evaluated_at;
  };

class AS_CalendarProviderV13
  {
private:
   string Ccy1(const string symbol) const {return StringLen(symbol)>=3?StringSubstr(symbol,0,3):"";}
   string Ccy2(const string symbol) const {return StringLen(symbol)>=6?StringSubstr(symbol,3,3):"";}
   bool Relevant(const string symbol,const string currency) const {
      if(StringFind(symbol,"XAU")>=0||StringFind(symbol,"GOLD")>=0)return currency=="USD";
      return currency==Ccy1(symbol)||currency==Ccy2(symbol);
   }

   void Live(const string symbol,const int before_min,const int after_min,AS_NewsStateV13 &out) const {
      out.source=AS_NEWS_SOURCE_LIVE;out.available=true;out.blocked=false;out.reason="";out.evaluated_at=TimeTradeServer();
      datetime from=out.evaluated_at-before_min*60,to=out.evaluated_at+after_min*60;
      MqlCalendarValue values[];int count=CalendarValueHistory(values,from,to,NULL,NULL);
      if(count<0){out.available=false;out.source=AS_NEWS_SOURCE_UNAVAILABLE;out.reason="LIVE_CALENDAR_UNAVAILABLE";return;}
      for(int i=0;i<count;i++){
         MqlCalendarEvent ev;if(!CalendarEventById(values[i].event_id,ev))continue;
         if(ev.importance!=CALENDAR_IMPORTANCE_HIGH)continue;
         MqlCalendarCountry country;if(!CalendarCountryById(ev.country_id,country))continue;
         if(!Relevant(symbol,country.currency))continue;
         if(values[i].time>=from&&values[i].time<=to){out.blocked=true;out.reason=StringFormat("HIGH_IMPACT_%s_%s",country.currency,ev.name);return;}
      }
   }

public:
   void Evaluate(const AS_RuntimeContext &ctx,const string symbol,const int before_min,const int after_min,AS_NewsStateV13 &out) const {
      ZeroMemory(out);
      if(ctx.kind==AS_RUNTIME_TERMINAL){Live(symbol,before_min,after_min,out);return;}
      // Tester calendar data must come from an explicit historical dataset.
      // Until a dataset is loaded, unavailable is a first-class result rather
      // than silently pretending the live calendar semantics were tested.
      out.source=AS_NEWS_SOURCE_UNAVAILABLE;out.available=false;out.blocked=false;
      out.reason="TESTER_CALENDAR_DATASET_NOT_LOADED";out.evaluated_at=TimeCurrent();
   }
  };
