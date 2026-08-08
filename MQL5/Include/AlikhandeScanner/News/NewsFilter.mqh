//+------------------------------------------------------------------+
//| NewsFilter.mqh                                                    |
//| P0 scope only: a BLOCK_NEW_SIGNAL gate driven by MT5's native     |
//| economic calendar (CalendarValueHistory), currency-aware, using   |
//| broker/server time. It does not close positions or otherwise act  |
//| — a candidate signal is simply not raised inside the news window. |
//|                                                                    |
//| Deferred to P2 (v1.3): a static historical dataset embedded as an |
//| MQL5 resource for realistic Strategy Tester backtesting — the     |
//| Tester has no internet access and does not retain a real news     |
//| archive, so CalendarValueHistory only works live. See             |
//| docs/ARCHITECTURE_V1.2.md section 6.                              |
//+------------------------------------------------------------------+
#property strict

struct NewsGateResult
  {
   bool     blocked;
   string   currency;
   string   eventTitle;
   datetime eventTime;
   ENUM_CALENDAR_EVENT_IMPORTANCE importance;
  };

// Currencies relevant to a symbol — same 6-letter split PortfolioRisk uses,
// duplicated locally to keep News/ dependency-free of Risk/.
void NewsExtractCurrencyLegs(const string rawSymbol, string &base, string &quote)
  {
   string s = rawSymbol;
   int firstHash = StringFind(s, "#");
   if(firstHash == 0) s = StringSubstr(s, 1);
   int suffixPos = StringFind(s, "_");
   if(suffixPos == 6) s = StringSubstr(s, 0, 6);

   if(StringLen(s) >= 6)
     {
      base  = StringSubstr(s, 0, 3);
      quote = StringSubstr(s, 3, 3);
     }
   else
     {
      base = s;   // e.g. XAUUSD -> base "XAU" quote "USD" still holds (6 chars)
      quote = "";
     }
  }

//+------------------------------------------------------------------+
//| Checks whether now() falls inside [event - preMinutes, event +    |
//| postMinutes] for any HIGH (and optionally MEDIUM) importance      |
//| event on either currency leg of the symbol.                       |
//+------------------------------------------------------------------+
NewsGateResult EvaluateNewsGate(const string symbol, const int preMinutes,
                                 const int postMinutes, const bool includeMedium)
  {
   NewsGateResult res;
   res.blocked = false;

   string base, quote;
   NewsExtractCurrencyLegs(symbol, base, quote);

   string currencies[];
   int n = (quote == "") ? 1 : 2;
   ArrayResize(currencies, n);
   currencies[0] = base;
   if(n == 2) currencies[1] = quote;

   datetime nowServer = TimeTradeServer();
   datetime windowStart = nowServer - preMinutes * 60;
   datetime windowEnd   = nowServer + postMinutes * 60;

   for(int c = 0; c < n; c++)
     {
      MqlCalendarValue values[];
      // CalendarValueHistory works against the terminal's internal calendar
      // DB — live only. In the Strategy Tester this returns nothing before
      // a P2 static-dataset resource is wired in (see file header).
      int count = CalendarValueHistory(values, windowStart, windowEnd, NULL, currencies[c]);
      if(count <= 0)
         continue;

      for(int i = 0; i < count; i++)
        {
         MqlCalendarEvent ev;
         if(!CalendarEventById(values[i].event_id, ev))
            continue;

         bool isHigh   = (ev.importance == CALENDAR_IMPORTANCE_HIGH);
         bool isMedium = (ev.importance == CALENDAR_IMPORTANCE_MODERATE);
         if(!isHigh && !(includeMedium && isMedium))
            continue;

         res.blocked    = true;
         res.currency   = currencies[c];
         res.eventTitle = ev.name;
         res.eventTime  = values[i].time;
         res.importance = ev.importance;
         return res; // first match is enough to block; Detail panel shows it
        }
     }

   return res;
  }
