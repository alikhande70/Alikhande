#pragma once

// Structured logging with de-duplication.
//
// The scanner runs on a 250 ms timer across many symbols, so a naive
// `Print()` inside any per-slice branch floods the Experts tab within seconds
// and buries the one message that mattered. Every emit therefore carries a
// stable code, and identical (code, context) pairs are suppressed for a
// cooldown window.

enum ENUM_AS_LOG_LEVEL
  {
   AS_LOG_DEBUG = 0,
   AS_LOG_INFO  = 1,
   AS_LOG_WARN  = 2,
   AS_LOG_ERROR = 3
  };

#define AS_LOG_DEDUP_SLOTS      64
#define AS_LOG_DEDUP_SECONDS    60

class AS_Log
  {
private:
   ENUM_AS_LOG_LEVEL m_minimum;
   string            m_keys[AS_LOG_DEDUP_SLOTS];
   datetime          m_last_emit[AS_LOG_DEDUP_SLOTS];
   int               m_count;
   int               m_suppressed;

   string LevelName(const ENUM_AS_LOG_LEVEL level) const
     {
      switch(level)
        {
         case AS_LOG_DEBUG: return "DEBUG";
         case AS_LOG_INFO:  return "INFO";
         case AS_LOG_WARN:  return "WARN";
         case AS_LOG_ERROR: return "ERROR";
        }
      return "?";
     }

   // Returns true when this key is allowed to emit now, and records the emit.
   bool Allow(const string key)
     {
      const datetime now = TimeCurrent();

      for(int i = 0; i < m_count; i++)
        {
         if(m_keys[i] != key)
            continue;
         if(now - m_last_emit[i] < AS_LOG_DEDUP_SECONDS)
           {
            m_suppressed++;
            return false;
           }
         m_last_emit[i] = now;
         return true;
        }

      if(m_count < AS_LOG_DEDUP_SLOTS)
        {
         m_keys[m_count] = key;
         m_last_emit[m_count] = now;
         m_count++;
         return true;
        }

      // Table full: evict the least recently emitted slot rather than silently
      // dropping the message, so a new failure mode is never invisible.
      int oldest = 0;
      for(int i = 1; i < AS_LOG_DEDUP_SLOTS; i++)
         if(m_last_emit[i] < m_last_emit[oldest])
            oldest = i;
      m_keys[oldest] = key;
      m_last_emit[oldest] = now;
      return true;
     }

public:
   AS_Log(void)
     {
      m_minimum = AS_LOG_INFO;
      m_count = 0;
      m_suppressed = 0;
      ArrayInitialize(m_last_emit, 0);
     }

   void SetMinimumLevel(const ENUM_AS_LOG_LEVEL level) { m_minimum = level; }
   int  SuppressedCount(void) const { return m_suppressed; }

   // `code` is a stable machine-readable identifier (SPEC_DRIFT, NO_TICK, ...).
   // `context` narrows de-duplication — normally the symbol.
   void Emit(const ENUM_AS_LOG_LEVEL level, const string code,
             const string context, const string message)
     {
      if(level < m_minimum)
         return;
      if(!Allow(code + "|" + context))
         return;
      PrintFormat("[%s] %s %s | %s", LevelName(level), code,
                  (context == "" ? "-" : context), message);
     }

   void Debug(const string code, const string context, const string message)
     { Emit(AS_LOG_DEBUG, code, context, message); }
   void Info(const string code, const string context, const string message)
     { Emit(AS_LOG_INFO, code, context, message); }
   void Warn(const string code, const string context, const string message)
     { Emit(AS_LOG_WARN, code, context, message); }
   void Error(const string code, const string context, const string message)
     { Emit(AS_LOG_ERROR, code, context, message); }
  };
