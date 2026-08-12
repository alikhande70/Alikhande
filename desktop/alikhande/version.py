"""Product and provenance versions.

These mirror ``MQL5/Include/AlikhandeScanner/Core/VersionInfo.mqh``. They are
stamped onto every persisted signal so a stored result can always be traced
back to the exact logic that produced it.

``RULE_VERSION`` carries a ``-PY`` suffix and that is deliberate. The desktop
build computes its indicators in Python rather than reading MetaTrader's
indicator buffers, so its numbers are *not* guaranteed to be bit-identical to
the EA's. Pooling outcomes across the two would describe a system that never
ran. A different suffix means the statistics layer, which scopes every sample
by rule version, keeps them apart automatically.
"""

from __future__ import annotations

APP_NAME = "Alikhande Scanner Desktop"
VERSION = "2.2.0"
EDITION = "Standalone"

# Bump RULE_VERSION when setup qualification changes, SCORING_VERSION when the
# score weights change. Historical statistics must never mix versions.
RULE_VERSION = "RULE-2.0.0-PY"
SCORING_VERSION = "SCORE-2.0.0-PY"
STATS_VERSION = "STATS-2.0.0-PY"

# SQLite schema version. Migrations in adapters/sqlite/database.py key off this;
# bumping it without adding a migration step is a release blocker.
DB_SCHEMA_VERSION = 1

# CSV export schema, independent of the SQLite schema.
EXPORT_SCHEMA_VERSION = "3"
