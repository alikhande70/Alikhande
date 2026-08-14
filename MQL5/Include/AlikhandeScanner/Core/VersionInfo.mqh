#pragma once

// Product version. Bumped on every release.
#define AS_VERSION            "1.3.0"
#define AS_EDITION            "Evidence Integrity"

// Rule and scoring versions are stamped onto every persisted signal so a stored
// signal can always be traced back to the exact logic that produced it. Bump
// AS_RULE_VERSION when setup qualification changes and AS_SCORING_VERSION when
// score weights change; historical statistics must never mix versions.
#define AS_RULE_VERSION       "RULE-1.3.0"
#define AS_SCORING_VERSION    "SCORE-1.3.0"
#define AS_STATS_VERSION      "STATS-1.3.0"

// CSV export schema. Independent of the SQLite schema below.
#define AS_SCHEMA_VERSION     "3"

// SQLite schema version. Migrations in Persistence/Database.mqh key off this;
// bumping it without adding a migration step is a release blocker.
#define AS_DB_SCHEMA_VERSION  1
