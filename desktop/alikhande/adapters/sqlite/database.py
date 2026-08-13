"""SQLite connection and schema management.

A port of ``Persistence/Database.mqh``, table for table, so a database written
by the EA and one written by this app have the same shape and can be inspected
with the same queries.

Migration policy: ``schema_meta.schema_version`` is the single authority.
``migrate()`` walks from the stored version to ``DB_SCHEMA_VERSION`` one step at
a time. Adding a schema change without adding its migration step is a release
blocker — the version check refuses to open a database rather than operate
against a shape it does not understand.

One addition over the MQL5 schema: a ``runs`` table. The EA could rely on the
terminal to keep tester and production files apart. A desktop app is a single
process the operator can point anywhere, so each session records what it was —
live, replay or offline — and every signal carries its ``run_id``. That makes
"was this win rate measured on real quotes?" a question the data itself can
answer, rather than one that depends on remembering which file is which.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from ...version import DB_SCHEMA_VERSION


class SchemaTooNew(RuntimeError):
    """The file was written by a newer build.

    Refusing is the whole point: operating against an unknown shape is how a
    "migration" silently drops columns somebody else's build depends on.
    """


_V1_STATEMENTS: tuple[str, ...] = (
    """CREATE TABLE IF NOT EXISTS runs(
        run_id TEXT PRIMARY KEY,
        kind TEXT NOT NULL,
        is_production INTEGER NOT NULL,
        app_version TEXT NOT NULL,
        rule_version TEXT NOT NULL,
        scoring_version TEXT NOT NULL,
        parameter_hash TEXT NOT NULL,
        symbols TEXT,
        started_at INTEGER NOT NULL,
        finished_at INTEGER,
        note TEXT)""",
    """CREATE TABLE IF NOT EXISTS signals(
        signal_id TEXT PRIMARY KEY,
        run_id TEXT,
        symbol TEXT NOT NULL,
        direction INTEGER NOT NULL,
        setup INTEGER NOT NULL,
        state TEXT NOT NULL,
        preferred_entry REAL, stop_loss REAL, take_profit REAL,
        nearest_support REAL, nearest_resistance REAL,
        demand_relation INTEGER, supply_relation INTEGER,
        long_score REAL, short_score REAL,
        regime INTEGER,
        reasons TEXT, validation_codes TEXT,
        confirmation_bar_time INTEGER,
        created_at INTEGER NOT NULL,
        expires_at INTEGER,
        rule_version TEXT NOT NULL,
        scoring_version TEXT NOT NULL,
        parameter_hash TEXT NOT NULL,
        broker_spec_hash TEXT NOT NULL)""",
    # Feature snapshot per signal. This is what a future meta-model would train
    # on; capturing it now is why the model becomes possible later.
    """CREATE TABLE IF NOT EXISTS signal_features(
        signal_id TEXT NOT NULL,
        name TEXT NOT NULL,
        value REAL,
        PRIMARY KEY(signal_id, name))""",
    """CREATE TABLE IF NOT EXISTS trade_plans(
        plan_id TEXT PRIMARY KEY,
        signal_id TEXT NOT NULL,
        symbol TEXT NOT NULL,
        direction INTEGER NOT NULL,
        entry REAL, stop_loss REAL, take_profit REAL,
        risk_percent REAL, risk_amount REAL, actual_risk_amount REAL,
        lot_size REAL, margin_required REAL,
        created_at INTEGER NOT NULL, expires_at INTEGER,
        validation_codes TEXT)""",
    """CREATE TABLE IF NOT EXISTS executions(
        execution_id TEXT PRIMARY KEY,
        plan_id TEXT NOT NULL,
        signal_id TEXT NOT NULL,
        symbol TEXT NOT NULL,
        state TEXT NOT NULL,
        request_id INTEGER, order_ticket INTEGER,
        deal_ticket INTEGER, position_id INTEGER,
        requested_volume REAL, filled_volume REAL,
        retcode INTEGER, message TEXT,
        created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL,
        terminal INTEGER NOT NULL)""",
    # Deals are recorded by ticket so replayed or duplicated transaction events
    # cannot double-count a fill. The PRIMARY KEY is the idempotency mechanism,
    # not a convenience.
    """CREATE TABLE IF NOT EXISTS deals(
        deal_ticket INTEGER PRIMARY KEY,
        execution_id TEXT,
        symbol TEXT NOT NULL,
        entry_type INTEGER,
        volume REAL, price REAL, net_profit REAL,
        recorded_at INTEGER NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS outcomes(
        signal_id TEXT PRIMARY KEY,
        result TEXT NOT NULL,
        realized_r REAL, mfe_r REAL, mae_r REAL,
        closed_at INTEGER)""",
    """CREATE TABLE IF NOT EXISTS symbol_specs(
        symbol TEXT PRIMARY KEY,
        fingerprint TEXT NOT NULL,
        digits INTEGER, point REAL, tick_size REAL, tick_value REAL,
        contract_size REAL, volume_min REAL, volume_step REAL,
        stops_level INTEGER, freeze_level INTEGER,
        updated_at INTEGER NOT NULL)""",
    # Single-row table (id = 1) holding guard state across restarts.
    """CREATE TABLE IF NOT EXISTS risk_state(
        id INTEGER PRIMARY KEY CHECK(id = 1),
        day_key INTEGER, day_start_equity REAL, peak_equity REAL,
        consecutive_losses INTEGER, daily_risk_used_pct REAL,
        updated_at INTEGER NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS runtime_events(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts INTEGER NOT NULL, level TEXT NOT NULL,
        code TEXT NOT NULL, context TEXT, message TEXT)""",
    "CREATE INDEX IF NOT EXISTS ix_signals_symbol_time ON signals(symbol, created_at)",
    "CREATE INDEX IF NOT EXISTS ix_signals_state ON signals(state)",
    "CREATE INDEX IF NOT EXISTS ix_signals_run ON signals(run_id)",
    "CREATE INDEX IF NOT EXISTS ix_executions_terminal ON executions(terminal)",
    "CREATE INDEX IF NOT EXISTS ix_events_ts ON runtime_events(ts)",
)


class Database:
    def __init__(self) -> None:
        self._connection: sqlite3.Connection | None = None
        self._path = ""

    @property
    def is_open(self) -> bool:
        return self._connection is not None

    @property
    def path(self) -> str:
        return self._path

    @property
    def connection(self) -> sqlite3.Connection:
        if self._connection is None:
            raise RuntimeError("database is not open")
        return self._connection

    def open(self, filename: str) -> bool:
        if self._connection is not None:
            return True

        path = Path(filename)
        path.parent.mkdir(parents=True, exist_ok=True)

        # ``check_same_thread=False`` because the scan worker owns the
        # connection while the UI thread reads snapshots the worker produced.
        # All actual SQL is issued from the worker thread; this flag only stops
        # sqlite3 from objecting to the handle being created elsewhere.
        connection = sqlite3.connect(str(path), check_same_thread=False)
        connection.row_factory = sqlite3.Row

        # WAL keeps a reader — an external inspection tool, or a second window —
        # from blocking the scanner's writes mid-session.
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA synchronous=NORMAL")

        self._connection = connection
        self._path = str(path)

        try:
            self.migrate()
        except Exception:
            self.close()
            raise
        return True

    def close(self) -> None:
        if self._connection is None:
            return
        try:
            self._connection.commit()
        finally:
            self._connection.close()
            self._connection = None

    def _schema_version(self) -> int:
        row = self.connection.execute(
            "SELECT value FROM schema_meta WHERE key='schema_version'"
        ).fetchone()
        return int(row["value"]) if row else 0

    def migrate(self) -> None:
        connection = self.connection
        connection.execute(
            "CREATE TABLE IF NOT EXISTS schema_meta("
            " key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        connection.commit()

        current = self._schema_version()
        if current > DB_SCHEMA_VERSION:
            raise SchemaTooNew(
                f"database is at v{current}, this build understands v{DB_SCHEMA_VERSION}; "
                "refusing to operate against an unknown shape"
            )

        # Each step is applied inside its own transaction so a failure leaves
        # the stored version pointing at the last shape that fully succeeded.
        while current < DB_SCHEMA_VERSION:
            target = current + 1
            statements = {1: _V1_STATEMENTS}.get(target)
            if statements is None:
                raise RuntimeError(f"no migration step defined for v{target}")

            try:
                for statement in statements:
                    connection.execute(statement)
                connection.execute(
                    "INSERT OR REPLACE INTO schema_meta(key, value) VALUES('schema_version', ?)",
                    (str(target),),
                )
                connection.commit()
            except Exception:
                connection.rollback()
                raise
            current = target

    def execute(self, sql: str, parameters: tuple = ()) -> sqlite3.Cursor:
        return self.connection.execute(sql, parameters)

    def commit(self) -> None:
        self.connection.commit()
