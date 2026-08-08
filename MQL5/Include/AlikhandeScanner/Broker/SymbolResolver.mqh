#pragma once
#include "../Core/Log.mqh"

// Broker-aware symbol resolution.
//
// The resolution ladder itself is inherited unchanged from v1.1.0 because it
// is genuinely good and broker-tested against LiteFinance naming: exact name,
// then `_o` suffix, then `#` prefix, then a normalised scan of the *entire*
// broker symbol tree (not just Market Watch).
//
// Hardened here: results are cached, so a symbol that needed the O(n) tree scan
// pays for it once instead of on every OnInit, and the scan is skipped entirely
// once a mapping is known.

#define AS_RESOLVER_CACHE_CAPACITY 64

class AS_SymbolResolver
  {
private:
   string  m_requested[AS_RESOLVER_CACHE_CAPACITY];
   string  m_resolved[AS_RESOLVER_CACHE_CAPACITY];
   int     m_count;
   AS_Log *m_log;

   string Upper(string value) const { StringToUpper(value); return value; }

   // Strip broker decoration so `#XAUUSD` and `XAUUSD_o` both reduce to `XAUUSD`.
   string BaseName(string value) const
     {
      StringTrimLeft(value);
      StringTrimRight(value);
      if(StringLen(value) > 0 && StringSubstr(value, 0, 1) == "#")
         value = StringSubstr(value, 1);
      const int len = StringLen(value);
      if(len > 2 && StringSubstr(value, len - 2, 2) == "_o")
         value = StringSubstr(value, 0, len - 2);
      return value;
     }

   bool SelectCandidate(const string candidate, string &resolved) const
     {
      if(candidate == "")
         return false;
      bool custom = false;
      if(SymbolExist(candidate, custom) && SymbolSelect(candidate, true))
        {
         resolved = candidate;
         return true;
        }
      return false;
     }

   bool Cached(const string requested, string &resolved) const
     {
      for(int i = 0; i < m_count; i++)
         if(m_requested[i] == requested)
           {
            resolved = m_resolved[i];
            return true;
           }
      return false;
     }

   void Remember(const string requested, const string resolved)
     {
      if(m_count >= AS_RESOLVER_CACHE_CAPACITY)
         return;
      m_requested[m_count] = requested;
      m_resolved[m_count] = resolved;
      m_count++;
     }

public:
   AS_SymbolResolver(void) { m_count = 0; m_log = NULL; }

   void Attach(AS_Log &log) { m_log = GetPointer(log); }

   // Returns false and leaves `resolved` empty when the symbol does not exist
   // on this broker. Callers must treat an unresolved symbol as permanently
   // excluded from scanning — never as a transient error to retry per tick.
   bool Resolve(const string requested, string &resolved)
     {
      resolved = "";
      string clean = requested;
      StringTrimLeft(clean);
      StringTrimRight(clean);
      if(clean == "")
         return false;

      if(Cached(clean, resolved))
         return resolved != "";

      const string base = BaseName(clean);
      if(SelectCandidate(clean, resolved)
         || SelectCandidate(base + "_o", resolved)
         || SelectCandidate("#" + base, resolved)
         || SelectCandidate(base, resolved))
        {
         Remember(clean, resolved);
         return true;
        }

      // Last resort: normalise every symbol the broker exposes and compare.
      // This is O(total symbols) and is exactly why the result gets cached.
      const string target = Upper(base);
      const int total = SymbolsTotal(false);
      for(int i = 0; i < total; i++)
        {
         const string name = SymbolName(i, false);
         if(Upper(BaseName(name)) != target)
            continue;
         if(SymbolSelect(name, true))
           {
            resolved = name;
            Remember(clean, resolved);
            if(m_log != NULL)
               m_log.Info("SYMBOL_RESOLVED_BY_SCAN", clean,
                          StringFormat("matched broker symbol '%s'", name));
            return true;
           }
        }

      Remember(clean, "");
      if(m_log != NULL)
         m_log.Warn("SYMBOL_UNRESOLVED", clean,
                    "not present in the broker symbol tree; excluded from scanning");
      return false;
     }
  };
