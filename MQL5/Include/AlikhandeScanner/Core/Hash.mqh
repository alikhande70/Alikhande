//+------------------------------------------------------------------+
//| Hash.mqh                                                           |
//| Deterministic string hashing (FNV-1a, 64-bit) used for parameter  |
//| snapshots, broker-spec drift detection, and signal IDs. No        |
//| cryptographic requirement — only stability and low collision rate |
//| for the sizes involved here.                                      |
//+------------------------------------------------------------------+
#property strict

string AlikhandeHashString(const string input)
  {
   ulong hash = 14695981039346656037; // FNV offset basis
   const ulong prime = 1099511628211;  // FNV prime

   int len = StringLen(input);
   for(int i = 0; i < len; i++)
     {
      hash ^= (ulong)StringGetCharacter(input, i);
      hash *= prime;
     }

   return StringFormat("%I64x", hash);
  }

// Convenience: hash + short human-readable prefix, used for IDs that must
// stay sortable-ish and short in logs/dashboard (e.g. SignalID, PlanID).
string AlikhandeHashWithPrefix(const string prefix, const string input)
  {
   return prefix + "-" + AlikhandeHashString(input);
  }
