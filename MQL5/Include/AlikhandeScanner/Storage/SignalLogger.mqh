//+------------------------------------------------------------------+
//| SignalLogger.mqh                                                   |
//| CSV export — a read-only projection of the `signals` table for    |
//| Excel/Python, per docs/ARCHITECTURE_V1.2.md section 3. SQLite is   |
//| the source of truth; this module never writes anything the DB     |
//| doesn't already have.                                              |
//+------------------------------------------------------------------+
#property strict
#include "Database.mqh"

#define SIGNAL_CSV_FILENAME "AlikhandeScanner\\signals_export.csv"

bool ExportSignalsToCsv()
  {
   if(!AlikhandeDbIsOpen())
      return false;

   int fileHandle = FileOpen(SIGNAL_CSV_FILENAME, FILE_WRITE | FILE_CSV | FILE_ANSI, ',');
   if(fileHandle == INVALID_HANDLE)
      return false;

   FileWrite(fileHandle, "signal_id", "ts", "symbol", "direction", "setup", "long_score",
             "short_score", "entry", "sl", "tp", "state", "rule_version");

   int stmt = DatabasePrepare(g_AlikhandeDbHandle,
      "SELECT signal_id, ts, symbol, direction, setup, long_score, short_score, entry, sl, tp, "
      "state, rule_version FROM signals ORDER BY ts DESC");
   if(stmt == INVALID_HANDLE)
     {
      FileClose(fileHandle);
      return false;
     }

   while(DatabaseRead(stmt))
     {
      string signalId, symbol, direction, setup, state;
      long ts;
      double longScore, shortScore, entry, sl, tp;
      int ruleVersion;

      DatabaseColumnText(stmt, 0, signalId);
      DatabaseColumnLong(stmt, 1, ts);
      DatabaseColumnText(stmt, 2, symbol);
      DatabaseColumnText(stmt, 3, direction);
      DatabaseColumnText(stmt, 4, setup);
      DatabaseColumnDouble(stmt, 5, longScore);
      DatabaseColumnDouble(stmt, 6, shortScore);
      DatabaseColumnDouble(stmt, 7, entry);
      DatabaseColumnDouble(stmt, 8, sl);
      DatabaseColumnDouble(stmt, 9, tp);
      DatabaseColumnText(stmt, 10, state);
      DatabaseColumnInteger(stmt, 11, ruleVersion);

      FileWrite(fileHandle, signalId, TimeToString((datetime)ts, TIME_DATE|TIME_SECONDS),
                symbol, direction, setup, longScore, shortScore, entry, sl, tp, state, ruleVersion);
     }

   DatabaseFinalize(stmt);
   FileClose(fileHandle);
   return true;
  }
