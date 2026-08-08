#pragma once
#include "../Domain/Models.mqh"
#include "../Core/Hash.mqh"
#include "../Core/Log.mqh"

// Symbol specification reader with drift detection.
//
// Brokers do change contract specifications on a live account — tick value,
// stops level and contract size all move, sometimes intraday around rollover or
// a margin-policy update. Every risk calculation downstream is priced off these
// numbers, so a silent change means silently mis-sized trades.
//
// The fields that affect risk maths are fingerprinted. Every persisted signal
// carries the fingerprint that was in force when it was produced, and a change
// between sessions is surfaced rather than absorbed.

#define AS_SPEC_DRIFT_CAPACITY 64

// Result of comparing a live specification against the last known one. The
// caller needs to distinguish "first time we have seen this symbol" from
// "unchanged": the first case must still be persisted, or the baseline never
// reaches the database and drift can only ever be detected within a single
// session.
enum ENUM_AS_SPEC_STATUS
  {
   AS_SPEC_UNCHANGED,
   AS_SPEC_FIRST_SEEN,
   AS_SPEC_DRIFTED
  };

class AS_SymbolSpecReader
  {
private:
   string  m_symbols[AS_SPEC_DRIFT_CAPACITY];
   string  m_fingerprints[AS_SPEC_DRIFT_CAPACITY];
   int     m_count;
   AS_Log *m_log;

   string Fingerprint(const AS_SymbolSpec &s) const
     {
      return AS_Fnv1a64(StringFormat("%s|%d|%.10f|%.10f|%.10f|%.4f|%.4f|%.4f|%d|%d",
                                     s.symbol, s.digits, s.point, s.tick_size,
                                     s.tick_value, s.contract_size,
                                     s.volume_min, s.volume_step,
                                     s.stops_level, s.freeze_level));
     }

public:
   AS_SymbolSpecReader(void) { m_count = 0; m_log = NULL; }

   void Attach(AS_Log &log) { m_log = GetPointer(log); }

   // Reads the live spec. Returns false while the terminal has not yet
   // populated it — a normal transient state right after SymbolSelect, which is
   // why callers warm up rather than treating it as an error.
   bool Read(const string symbol, AS_SymbolSpec &s)
     {
      ZeroMemory(s);
      s.symbol        = symbol;
      s.digits        = (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS);
      s.point         = SymbolInfoDouble(symbol, SYMBOL_POINT);
      s.tick_size     = SymbolInfoDouble(symbol, SYMBOL_TRADE_TICK_SIZE);
      s.tick_value    = SymbolInfoDouble(symbol, SYMBOL_TRADE_TICK_VALUE);
      s.contract_size = SymbolInfoDouble(symbol, SYMBOL_TRADE_CONTRACT_SIZE);
      s.volume_min    = SymbolInfoDouble(symbol, SYMBOL_VOLUME_MIN);
      s.volume_max    = SymbolInfoDouble(symbol, SYMBOL_VOLUME_MAX);
      s.volume_step   = SymbolInfoDouble(symbol, SYMBOL_VOLUME_STEP);
      s.trade_mode    = SymbolInfoInteger(symbol, SYMBOL_TRADE_MODE);
      s.stops_level   = (int)SymbolInfoInteger(symbol, SYMBOL_TRADE_STOPS_LEVEL);
      s.freeze_level  = (int)SymbolInfoInteger(symbol, SYMBOL_TRADE_FREEZE_LEVEL);

      s.ready = (s.point > 0.0
                 && s.tick_size > 0.0
                 && s.tick_value > 0.0
                 && s.volume_min > 0.0
                 && s.volume_max >= s.volume_min
                 && s.volume_step > 0.0);

      s.fingerprint = s.ready ? Fingerprint(s) : "";
      return s.ready;
     }

   // Compares against the fingerprint last seen for this symbol.
   //
   // AS_SPEC_FIRST_SEEN and AS_SPEC_DRIFTED both mean "persist this"; only
   // AS_SPEC_UNCHANGED means there is nothing to write. Returning a plain bool
   // here was a real defect: a fresh symbol reported "no drift", so its
   // baseline never reached the database, SeedFingerprint found nothing on the
   // next start, and drift across restarts was undetectable.
   ENUM_AS_SPEC_STATUS DetectDrift(const AS_SymbolSpec &s)
     {
      if(!s.ready)
         return AS_SPEC_UNCHANGED;

      for(int i = 0; i < m_count; i++)
        {
         if(m_symbols[i] != s.symbol)
            continue;
         if(m_fingerprints[i] == s.fingerprint)
            return AS_SPEC_UNCHANGED;
         if(m_log != NULL)
            m_log.Warn("SPEC_DRIFT", s.symbol,
                       StringFormat("broker specification changed: %s -> %s; "
                                    "risk sizing for open plans is now stale",
                                    m_fingerprints[i], s.fingerprint));
         m_fingerprints[i] = s.fingerprint;
         return AS_SPEC_DRIFTED;
        }

      if(m_count < AS_SPEC_DRIFT_CAPACITY)
        {
         m_symbols[m_count] = s.symbol;
         m_fingerprints[m_count] = s.fingerprint;
         m_count++;
        }
      else if(m_log != NULL)
        {
         m_log.Warn("SPEC_TABLE_FULL", s.symbol,
                    StringFormat("drift tracking capacity %d exhausted; "
                                 "this symbol is not monitored", AS_SPEC_DRIFT_CAPACITY));
        }
      return AS_SPEC_FIRST_SEEN;
     }

   // Seeds the baseline from persisted state so drift is detected across a
   // restart, not just within one session.
   void SeedFingerprint(const string symbol, const string fingerprint)
     {
      if(fingerprint == "" || m_count >= AS_SPEC_DRIFT_CAPACITY)
         return;
      for(int i = 0; i < m_count; i++)
         if(m_symbols[i] == symbol)
           {
            m_fingerprints[i] = fingerprint;
            return;
           }
      m_symbols[m_count] = symbol;
      m_fingerprints[m_count] = fingerprint;
      m_count++;
     }
  };
