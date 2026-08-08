//+------------------------------------------------------------------+
//| VersionInfo.mqh                                                  |
//| Alikhande Scanner semantic version and DB schema version.        |
//+------------------------------------------------------------------+
#property strict

#define ALIKHANDE_VERSION_MAJOR   1
#define ALIKHANDE_VERSION_MINOR   2
#define ALIKHANDE_VERSION_PATCH   0
#define ALIKHANDE_VERSION_STRING  "1.2.0"
#define ALIKHANDE_EDITION         "Reliability & Evidence Edition"

// Bumped whenever the SQLite schema in Storage/Database.mqh changes shape.
#define ALIKHANDE_DB_SCHEMA_VERSION 1

// Bumped whenever scoring/rule logic changes, so every persisted signal can be
// traced back to the exact rule set that produced it.
#define ALIKHANDE_RULE_VERSION 1

string AlikhandeVersionString()
  {
   return StringFormat("Alikhande Scanner %s (%s) — schema v%d, rules v%d",
                        ALIKHANDE_VERSION_STRING, ALIKHANDE_EDITION,
                        ALIKHANDE_DB_SCHEMA_VERSION, ALIKHANDE_RULE_VERSION);
  }
