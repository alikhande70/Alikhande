#property strict
#property version "1.20"
#property script_show_inputs
#property description "Searches the whole broker symbol tree, not just Market Watch."

input string InpSearchTerms = "XAU,EUR,GBP,JPY,CHF,AUD,CAD,NZD";

void OnStart()
  {
   string terms[];
   const int term_count = StringSplit(InpSearchTerms, ',', terms);
   const int total = SymbolsTotal(false);

   PrintFormat("Alikhande symbol discovery: scanning %d broker symbols for %d terms",
               total, term_count);

   for(int t = 0; t < term_count; t++)
     {
      string term = terms[t];
      StringTrimLeft(term);
      StringTrimRight(term);
      if(term == "")
         continue;

      string needle = term;
      StringToUpper(needle);

      Print("------------------------------------------------------");
      PrintFormat("matches for '%s':", term);

      int matches = 0;
      for(int i = 0; i < total; i++)
        {
         const string name = SymbolName(i, false);
         string haystack = name;
         StringToUpper(haystack);
         if(StringFind(haystack, needle) < 0)
            continue;

         // Note whether the symbol was already in Market Watch, and put it
         // back if it was not: a discovery script should not change terminal
         // state as a side effect of looking.
         const bool was_selected = (bool)SymbolInfoInteger(name, SYMBOL_SELECT);
         string detail = "?";
         if(SymbolSelect(name, true))
           {
            detail = StringFormat("digits=%d point=%s",
                                  (int)SymbolInfoInteger(name, SYMBOL_DIGITS),
                                  DoubleToString(SymbolInfoDouble(name, SYMBOL_POINT), 8));
            if(!was_selected)
               SymbolSelect(name, false);
           }

         PrintFormat("   %-24s %s %s", name, detail, was_selected ? "(Market Watch)" : "");
         matches++;
        }

      if(matches == 0)
         PrintFormat("   no match for '%s'", term);
     }

   Print("Copy the exact broker symbol names into the EA's InpSymbols input.");
  }
