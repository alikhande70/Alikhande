#property strict
#property version "1.20"
#property script_show_inputs
#property description "Prints the broker specification the risk maths depends on."

#include <AlikhandeScanner/Broker/SymbolResolver.mqh>
#include <AlikhandeScanner/Broker/SymbolSpec.mqh>
#include <AlikhandeScanner/Core/Log.mqh>

input string InpSymbols = AS_DEFAULT_SYMBOLS;

void OnStart()
  {
   AS_Log log;
   AS_SymbolResolver resolver;
   AS_SymbolSpecReader reader;
   resolver.Attach(log);
   reader.Attach(log);

   string requested[];
   const int count = StringSplit(InpSymbols, ',', requested);

   Print("Alikhande symbol specification report");
   Print("Every number below feeds position sizing. Verify them before trusting a lot size.");

   for(int i = 0; i < count; i++)
     {
      string name = requested[i];
      StringTrimLeft(name);
      StringTrimRight(name);
      if(name == "")
         continue;

      string resolved = "";
      if(!resolver.Resolve(name, resolved))
        {
         PrintFormat("%-14s UNRESOLVED", name);
         continue;
        }

      AS_SymbolSpec spec;
      if(!reader.Read(resolved, spec))
        {
         PrintFormat("%-14s -> %-14s NOT READY (terminal has not populated the spec yet)",
                     name, resolved);
         continue;
        }

      PrintFormat("%-14s -> %-14s digits=%d point=%g tick_size=%g tick_value=%g",
                  name, resolved, spec.digits, spec.point, spec.tick_size, spec.tick_value);
      PrintFormat("%-14s    contract=%g vol[min=%g max=%g step=%g] stops=%d freeze=%d",
                  "", spec.contract_size, spec.volume_min, spec.volume_max,
                  spec.volume_step, spec.stops_level, spec.freeze_level);
      PrintFormat("%-14s    fingerprint=%s", "", spec.fingerprint);
     }
  }
