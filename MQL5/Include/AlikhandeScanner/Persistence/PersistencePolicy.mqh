#pragma once
#include "../Core/RuntimeContext.mqh"
#include "../Core/Config.mqh"

// Where the database lives, and whether it should exist at all.
//
// The policy differs from simply giving every context its own file, and the
// difference is deliberate:
//
//   TERMINAL      production history. Persistence is REQUIRED — without it
//                 there is no de-duplication across restarts, no risk-state
//                 continuity and no outcome record, so the EA refuses to run.
//
//   TESTER        a single backtest is worth inspecting afterwards, so it gets
//                 its own file, keyed by the agent sandbox. Persistence is
//                 optional: a tester run that cannot open a database is still
//                 a useful run.
//
//   OPTIMIZATION  persistence is DISABLED outright. An optimization sweep runs
//                 thousands of passes across parallel agents; writing a
//                 database per pass produces thousands of files that are, by
//                 construction, evidence about nothing — each pass is a
//                 different parameter set on the same history. Per-pass results
//                 belong in OnTester()/frames, which is what they are for.
//
// The alternative — hashing sandbox paths into per-agent optimization files —
// keeps the data isolated but still generates the garbage. Not writing it is
// strictly better.

struct AS_PersistencePlan
  {
   bool   enabled;      // should a database be opened at all
   bool   required;     // is failing to open it fatal
   string filename;
   string rationale;
  };

class AS_PersistencePolicy
  {
public:
   AS_PersistencePlan Plan(const AS_RuntimeContext &ctx) const
     {
      AS_PersistencePlan plan;
      ZeroMemory(plan);

      switch(ctx.kind)
        {
         case AS_RUNTIME_TERMINAL:
            plan.enabled   = true;
            plan.required  = true;
            plan.filename  = AS_DATABASE_FILE;
            plan.rationale = "production history";
            break;

         case AS_RUNTIME_TESTER:
            plan.enabled   = true;
            plan.required  = false;
            // Agent-scoped so a parallel visual run cannot collide, and clearly
            // named so nobody mistakes it for production history.
            plan.filename  = StringFormat("AlikhandeScanner\\tester_%s.sqlite",
                                          ctx.agent_identity);
            plan.rationale = "isolated backtest history";
            break;

         case AS_RUNTIME_OPTIMIZATION:
            plan.enabled   = false;
            plan.required  = false;
            plan.filename  = "";
            plan.rationale = "optimization passes produce no durable evidence";
            break;
        }

      return plan;
     }
  };
