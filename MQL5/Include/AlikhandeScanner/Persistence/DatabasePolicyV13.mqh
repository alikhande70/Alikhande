#pragma once
#include "../Core/RuntimeContext.mqh"
#include "../Core/Hash.mqh"

class AS_DatabasePolicyV13
  {
public:
   string FileName(const AS_RuntimeContext &ctx) const
     {
      if(ctx.kind==AS_RUNTIME_TERMINAL)
         return "AlikhandeScanner\\runtime_v13.sqlite";

      // Tester agents run in isolated data sandboxes. Hashing the actual data
      // path makes the identity explicit instead of relying on that behavior.
      const string sandbox=TerminalInfoString(TERMINAL_DATA_PATH);
      const string key=AS_Fnv1a(ctx.identity+"|"+sandbox);
      if(ctx.kind==AS_RUNTIME_OPTIMIZATION)
         return "AlikhandeScanner\\optimization_"+key+".sqlite";
      return "AlikhandeScanner\\tester_"+key+".sqlite";
     }

   bool IsProductionHistory(const AS_RuntimeContext &ctx) const
     {
      return ctx.kind==AS_RUNTIME_TERMINAL;
     }
  };
