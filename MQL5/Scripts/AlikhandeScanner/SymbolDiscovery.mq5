#property strict
#property version "1.20"
#property script_show_inputs
input string InpSearchTerms="XAU,EUR,GBP,JPY,CHF,AUD,CAD,NZD,NQ,AAPL,MSFT,NVDA,AMZN,GOOG,META,TSLA";
void OnStart(){string targets[];int n=StringSplit(InpSearchTerms,',',targets);int total=SymbolsTotal(false);PrintFormat("Alikhande SymbolDiscovery: scanning %d broker symbols for %d terms",total,n);for(int t=0;t<n;t++){StringTrimLeft(targets[t]);StringTrimRight(targets[t]);string needle=targets[t];StringToUpper(needle);int matches=0;for(int i=0;i<total;i++){string name=SymbolName(i,false),hay=name;StringToUpper(hay);if(StringFind(hay,needle)<0)continue;Print(name);matches++;}if(matches==0)PrintFormat("no match for %s",targets[t]);}}
