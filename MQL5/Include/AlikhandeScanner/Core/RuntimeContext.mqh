#pragma once

// Runtime identity is explicit because persistence, calendar semantics and
// verification rules differ between a normal terminal, a single tester run
// and an optimization agent.
enum ENUM_AS_RUNTIME_CONTEXT
  {
   AS_RUNTIME_TERMINAL = 0,
   AS_RUNTIME_TESTER = 1,
   AS_RUNTIME_OPTIMIZATION = 2
  };

struct AS_RuntimeContext
  {
   ENUM_AS_RUNTIME_CONTEXT kind;
   bool is_tester;
   bool is_optimization;
   bool is_forward;
   bool is_visual;
   string identity;
  };

class AS_RuntimeContextReader
  {
public:
   void Read(AS_RuntimeContext &out) const
     {
      ZeroMemory(out);
      out.is_tester       = (bool)MQLInfoInteger(MQL_TESTER);
      out.is_optimization = (bool)MQLInfoInteger(MQL_OPTIMIZATION);
      out.is_forward      = (bool)MQLInfoInteger(MQL_FORWARD);
      out.is_visual       = (bool)MQLInfoInteger(MQL_VISUAL_MODE);

      if(out.is_optimization)
         out.kind = AS_RUNTIME_OPTIMIZATION;
      else if(out.is_tester)
         out.kind = AS_RUNTIME_TESTER;
      else
         out.kind = AS_RUNTIME_TERMINAL;

      out.identity = StringFormat("kind=%d|tester=%d|opt=%d|forward=%d|visual=%d",
                                  (int)out.kind,
                                  (int)out.is_tester,
                                  (int)out.is_optimization,
                                  (int)out.is_forward,
                                  (int)out.is_visual);
     }
  };
