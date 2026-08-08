//+------------------------------------------------------------------+
//| ParameterHash.mqh                                                 |
//| Hashes the active input set so every persisted signal can be      |
//| traced back to the exact parameters that produced it.             |
//| Depends on Core/Hash.mqh (existing project hash primitive).       |
//+------------------------------------------------------------------+
#property strict
#include "Hash.mqh"

// Build a stable, order-independent key=value blob from the inputs the caller
// cares about (pass the already-formatted "key=value;key=value;..." string —
// callers own the list of which inputs are hash-relevant so unrelated cosmetic
// inputs like UI colors don't force a new hash on every run).
string ComputeParameterHash(const string paramBlob)
  {
   return AlikhandeHashString(paramBlob);
  }

// Convenience: build the blob from the fields that actually affect signal
// generation. Extend this list as new scoring inputs are added — anything not
// listed here silently will NOT invalidate old signal snapshots on change.
string BuildScoringParameterBlob(const double atrBufferMult,
                                  const double minRR,
                                  const int    pullbackLookback,
                                  const double zoneToleranceAtr,
                                  const int    ruleVersion)
  {
   return StringFormat("atrBufferMult=%.4f;minRR=%.4f;pullbackLookback=%d;zoneToleranceAtr=%.4f;ruleVersion=%d",
                        atrBufferMult, minRR, pullbackLookback, zoneToleranceAtr, ruleVersion);
  }
