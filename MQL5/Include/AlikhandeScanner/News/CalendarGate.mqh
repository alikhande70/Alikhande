#pragma once
#include "../Core/RuntimeContext.mqh"
#include "../Core/Config.mqh"
#include "../Core/Log.mqh"

// Economic calendar gate with explicit provenance.
//
// The trap this module exists to avoid: MT5's calendar API is unavailable in
// the Strategy Tester and keeps no usable archive of past events. A naive
// implementation calls CalendarValueHistory(), gets nothing back, and reports
// "no upcoming news" — which is indistinguishable from a genuinely clear
// window. That is a fail-OPEN gate: it is silent exactly when it cannot see,
// and a backtest would trade straight through every NFP while appearing to
// respect a news filter.
//
// So the gate never answers "blocked or clear". It answers with a state AND a
// source, and UNAVAILABLE is a distinct third answer that callers must handle
// deliberately. The default policy for UNAVAILABLE is configurable but
// fail-SAFE by default: if the gate cannot see, it does not pretend the road is
// empty.

enum ENUM_AS_NEWS_SOURCE
  {
   AS_NEWS_SOURCE_LIVE,        // terminal calendar answered
   AS_NEWS_SOURCE_TEST_DATA,   // supplied dataset (tester)
   AS_NEWS_SOURCE_UNAVAILABLE  // no calendar could be consulted
  };

enum ENUM_AS_NEWS_STATE
  {
   AS_NEWS_CLEAR,      // consulted a source; nothing relevant in the window
   AS_NEWS_BLOCKED,    // consulted a source; a relevant event is in the window
   AS_NEWS_UNKNOWN     // no source could be consulted — NOT the same as clear
  };

struct AS_NewsVerdict
  {
   ENUM_AS_NEWS_STATE  state;
   ENUM_AS_NEWS_SOURCE source;
   string              event_name;
   string              currency;
   datetime            event_time;
   string              reason;
  };

class AS_CalendarGate
  {
private:
   AS_Log *m_log;
   bool    m_treat_unknown_as_blocking;

   // Currency legs, tolerating broker decoration.
   void CurrencyLegs(const string symbol, string &base, string &quote) const
     {
      base = "";
      quote = "";
      string clean = symbol;
      if(StringLen(clean) > 0 && StringSubstr(clean, 0, 1) == "#")
         clean = StringSubstr(clean, 1);
      const int underscore = StringFind(clean, "_");
      if(underscore >= 6)
         clean = StringSubstr(clean, 0, underscore);
      if(StringLen(clean) >= 6)
        {
         base = StringSubstr(clean, 0, 3);
         quote = StringSubstr(clean, 3, 3);
        }
     }

   // Queries the terminal calendar for one currency. Returns false when the
   // API itself is unusable, which is different from returning true with no
   // events found.
   bool QueryCurrency(const string currency, const datetime from, const datetime to,
                      const bool include_medium, AS_NewsVerdict &verdict) const
     {
      if(currency == "")
         return true;   // nothing to ask about is not a failure

      MqlCalendarValue values[];
      ResetLastError();
      const int count = CalendarValueHistory(values, from, to, NULL, currency);
      if(count < 0)
         return false;  // API unavailable (tester, or no calendar data)

      for(int i = 0; i < count; i++)
        {
         MqlCalendarEvent event;
         if(!CalendarEventById(values[i].event_id, event))
            continue;

         const bool high = (event.importance == CALENDAR_IMPORTANCE_HIGH);
         const bool medium = (event.importance == CALENDAR_IMPORTANCE_MODERATE);
         if(!high && !(include_medium && medium))
            continue;

         verdict.state      = AS_NEWS_BLOCKED;
         verdict.event_name = event.name;
         verdict.currency   = currency;
         verdict.event_time = values[i].time;
         verdict.reason     = StringFormat("%s %s", currency, event.name);
         return true;
        }
      return true;
     }

public:
   AS_CalendarGate(void) { m_log = NULL; m_treat_unknown_as_blocking = true; }

   void Attach(AS_Log &log) { m_log = GetPointer(log); }

   // How UNKNOWN is resolved depends on what is at stake, and the two cases
   // genuinely differ:
   //
   //   Production — UNKNOWN blocks. Real orders against a calendar the system
   //   cannot see is exactly the situation a news filter exists to prevent.
   //
   //   Tester/optimization — UNKNOWN does not block, because blocking would
   //   mean no backtest ever produces a trade, which makes the filter's
   //   presence unfalsifiable rather than safe. The run proceeds NEWS-BLIND and
   //   must be labelled as such: its results describe a system with no news
   //   filter, and comparing them to a live run that has one is invalid.
   void ApplyRuntimePolicy(const AS_RuntimeContext &runtime)
     {
      m_treat_unknown_as_blocking = runtime.is_production;
      if(!runtime.is_production && m_log != NULL)
         m_log.Warn("NEWS_BLIND_RUN", "",
                    "no calendar outside the terminal: this run applies NO news "
                    "filtering and its results are not comparable to a live run");
     }

   // True when UNKNOWN is being allowed through — i.e. the run is news-blind.
   bool IsNewsBlind(void) const { return !m_treat_unknown_as_blocking; }

   // Evaluates the window [now - pre, now + post] on both currency legs.
   //
   // In any non-terminal runtime the terminal calendar is not consulted at all:
   // asking an API that is documented not to work there and interpreting its
   // empty answer is precisely the fail-open bug this module avoids.
   AS_NewsVerdict Evaluate(const string symbol, const AS_RuntimeContext &runtime,
                           const int pre_minutes, const int post_minutes,
                           const bool include_medium)
     {
      AS_NewsVerdict verdict;
      ZeroMemory(verdict);
      verdict.state = AS_NEWS_UNKNOWN;
      verdict.source = AS_NEWS_SOURCE_UNAVAILABLE;

      if(runtime.kind != AS_RUNTIME_TERMINAL)
        {
         // No embedded historical dataset ships with this build, so the honest
         // answer in the tester is UNKNOWN. Reporting CLEAR here would make
         // every backtest silently news-blind while appearing filtered.
         verdict.reason = "calendar unavailable outside the terminal";
         return verdict;
        }

      string base = "", quote = "";
      CurrencyLegs(symbol, base, quote);

      const datetime now  = TimeTradeServer();
      const datetime from = now - pre_minutes * 60;
      const datetime to   = now + post_minutes * 60;

      verdict.state = AS_NEWS_CLEAR;
      verdict.source = AS_NEWS_SOURCE_LIVE;

      if(!QueryCurrency(base, from, to, include_medium, verdict)
         || !QueryCurrency(quote, from, to, include_medium, verdict))
        {
         verdict.state = AS_NEWS_UNKNOWN;
         verdict.source = AS_NEWS_SOURCE_UNAVAILABLE;
         verdict.reason = "calendar query failed";
         if(m_log != NULL)
            m_log.Warn("CALENDAR_UNAVAILABLE", symbol,
                       "calendar could not be consulted; treating as unknown");
        }

      return verdict;
     }

   // The only place the tri-state collapses to a decision. Keeping this
   // separate from Evaluate() means the UI can always show the true state even
   // when the trading decision has to be binary.
   bool BlocksTrading(const AS_NewsVerdict &verdict) const
     {
      if(verdict.state == AS_NEWS_BLOCKED)
         return true;
      if(verdict.state == AS_NEWS_UNKNOWN)
         return m_treat_unknown_as_blocking;
      return false;
     }
  };

string AS_NewsStateName(const ENUM_AS_NEWS_STATE state)
  {
   switch(state)
     {
      case AS_NEWS_CLEAR:   return "CLEAR";
      case AS_NEWS_BLOCKED: return "BLOCKED";
      case AS_NEWS_UNKNOWN: return "UNKNOWN";
     }
   return "?";
  }

string AS_NewsSourceName(const ENUM_AS_NEWS_SOURCE source)
  {
   switch(source)
     {
      case AS_NEWS_SOURCE_LIVE:        return "LIVE";
      case AS_NEWS_SOURCE_TEST_DATA:   return "TEST_DATA";
      case AS_NEWS_SOURCE_UNAVAILABLE: return "UNAVAILABLE";
     }
   return "?";
  }
