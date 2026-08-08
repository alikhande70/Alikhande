#pragma once
#include "Hash.mqh"

// Which execution environment is this program running in?
//
// This matters because the scanner's whole value proposition is that its stored
// history is evidence. A backtest and an optimization sweep both produce
// signals and outcomes that look identical to real ones in the database, and if
// they land in the same file, the evidence is silently contaminated: a win rate
// computed afterwards would be measuring a mixture of live scanning and
// whatever parameter sweep happened to run that afternoon.
//
// MetaQuotes documents that MQL_OPTIMIZATION, MQL_FORWARD and MQL_VISUAL_MODE
// all imply MQL_TESTER, so the classification is a hierarchy rather than a set
// of independent flags.

enum ENUM_AS_RUNTIME_KIND
  {
   AS_RUNTIME_TERMINAL,      // live chart in the terminal — the only production context
   AS_RUNTIME_TESTER,        // single Strategy Tester pass (visual or fast)
   AS_RUNTIME_OPTIMIZATION   // one pass of an optimization sweep, possibly forward
  };

struct AS_RuntimeContext
  {
   ENUM_AS_RUNTIME_KIND kind;
   bool     visual_mode;
   bool     forward_pass;
   bool     is_production;    // only true for AS_RUNTIME_TERMINAL
   string   agent_identity;   // distinguishes parallel tester/optimization agents
   string   description;
  };

class AS_RuntimeProbe
  {
public:
   AS_RuntimeContext Detect(void) const
     {
      AS_RuntimeContext ctx;
      ZeroMemory(ctx);

      const bool tester       = (bool)MQLInfoInteger(MQL_TESTER);
      const bool optimization = (bool)MQLInfoInteger(MQL_OPTIMIZATION);
      const bool forward      = (bool)MQLInfoInteger(MQL_FORWARD);
      const bool visual       = (bool)MQLInfoInteger(MQL_VISUAL_MODE);

      ctx.visual_mode  = visual;
      ctx.forward_pass = forward;

      if(!tester)
        {
         ctx.kind = AS_RUNTIME_TERMINAL;
         ctx.is_production = true;
         ctx.description = "terminal";
        }
      else if(optimization)
        {
         ctx.kind = AS_RUNTIME_OPTIMIZATION;
         ctx.is_production = false;
         ctx.description = forward ? "optimization/forward" : "optimization";
        }
      else
        {
         ctx.kind = AS_RUNTIME_TESTER;
         ctx.is_production = false;
         ctx.description = visual ? "tester/visual" : "tester";
        }

      // Tester and optimization agents each get an isolated data sandbox.
      // Hashing the data path makes that isolation explicit and stable rather
      // than relying on the terminal's behaviour to keep files apart.
      ctx.agent_identity = AS_Fnv1a(TerminalInfoString(TERMINAL_DATA_PATH));
      return ctx;
     }
  };

string AS_RuntimeKindName(const ENUM_AS_RUNTIME_KIND kind)
  {
   switch(kind)
     {
      case AS_RUNTIME_TERMINAL:     return "TERMINAL";
      case AS_RUNTIME_TESTER:       return "TESTER";
      case AS_RUNTIME_OPTIMIZATION: return "OPTIMIZATION";
     }
   return "UNKNOWN";
  }
