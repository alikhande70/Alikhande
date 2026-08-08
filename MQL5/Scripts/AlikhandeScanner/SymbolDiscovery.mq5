#property strict
#property version "1.10"
#property script_show_inputs

input string InpSearchTerms="XAU,EUR,GBP,JPY,CHF,AUD,CAD,NZD,NQ,AAPL,MSFT,NVDA,AMZN,GOOG,META,TSLA";

void OnStart(){
   string targets[];int n=StringSplit(InpSearchTerms,',',targets);int total=SymbolsTotal(false);
   PrintFormat("Alikhande SymbolDiscovery: scanning %d broker symbols for %d terms",total,n);
   for(int t=0;t<n;t++){StringTrimLeft(targets[t]);StringTrimRight(targets[t]);string needle=targets[t];StringToUpper(needle);int matches=0;Print("------------------------------------------------------");PrintFormat("MATCHES FOR '%s':",targets[t]);
      for(int i=0;i<total;i++){string name=SymbolName(i,false),hay=name;StringToUpper(hay);if(StringFind(hay,needle)<0)continue;bool selected=(bool)SymbolInfoInteger(name,SYMBOL_SELECT);string spec="?";if(SymbolSelect(name,true)){int d=(int)SymbolInfoInteger(name,SYMBOL_DIGITS);double point=SymbolInfoDouble(name,SYMBOL_POINT);spec=StringFormat("digits=%d point=%s",d,DoubleToString(point,8));if(!selected)SymbolSelect(name,false);}PrintFormat("   %-24s %s %s",name,spec,(selected?"(Market Watch)":""));matches++;}
      if(matches==0)PrintFormat("   no match for '%s'",targets[t]);
   }
   Print("DONE. Copy the exact broker symbols into Alikhande Scanner inputs or extend SymbolResolver.mqh.");
}
