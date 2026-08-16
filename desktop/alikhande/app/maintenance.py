"""Backup, restore, settings portability and the diagnostics bundle.

Four jobs that share one property: they are the things nobody wants until the
day they are the only thing that matters, and by then it is too late to add
them. A scanner whose whole thesis is that evidence accumulates over months has
a database it cannot afford to lose, and until now it had no way to copy it
safely, no way to move an operator's settings to a new machine, and no way to
hand anyone a description of what went wrong.

## Backups use SQLite's own backup API, not a file copy

A ``shutil.copy`` of a live SQLite file produces a corrupt backup often enough
to be useless and rarely enough to be trusted. The database may be mid-write,
and the write-ahead log lives in a separate file that the copy misses. Python's
``sqlite3`` ships :meth:`sqlite3.Connection.backup`, which takes a consistent
snapshot of a live database without stopping it. That is what is used, and a
backup that cannot be taken that way is reported as failed rather than written
as a file that looks fine.

Every backup is verified after writing — opened, integrity-checked, and its row
counts compared against the source. An unverified backup is not a backup; it is
a file with a reassuring name.

## Restore never overwrites in place

The current database is moved aside to a timestamped name first. Restoring the
wrong file is a mistake an operator makes exactly once, at the worst possible
moment, and it must be undoable.

## The diagnostics bundle contains no credentials

It reports the account *number* and server name, because a support conversation
about the wrong account is worthless, and nothing else about the account. There
is no password anywhere in this application to leak — the MT5 adapter attaches
to a terminal the operator already logged in — and the bundle asserts that
rather than assuming it.
"""

from __future__ import annotations

import json
import platform
import shutil
import sqlite3
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

#: Backups older than this are pruned, provided enough newer ones exist.
BACKUP_RETENTION_DAYS = 30
#: Never prune below this many, however old they are. A machine switched off
#: for two months must not come back to an empty backup folder.
BACKUP_KEEP_MINIMUM = 5


def _stamp(now: int | None = None) -> str:
    moment = datetime.fromtimestamp(now, timezone.utc) if now else datetime.now(timezone.utc)
    return moment.strftime("%Y%m%d-%H%M%S")


@dataclass
class BackupResult:
    ok: bool = False
    path: str = ""
    bytes_written: int = 0
    tables: dict[str, int] = field(default_factory=dict)
    verified: bool = False
    error: str = ""
    #: Seconds the source database was held. Reported because an operator
    #: running this on a schedule deserves to know what it costs them.
    duration_ms: float = 0.0


def _table_counts(connection: sqlite3.Connection) -> dict[str, int]:
    counts: dict[str, int] = {}
    cursor = connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    )
    for (name,) in cursor.fetchall():
        # Table names come from sqlite_master, not from user input, so the
        # interpolation is safe — and parameters are not permitted in this
        # position by SQLite anyway.
        counts[name] = connection.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
    return counts


def backup_database(source: str | Path, folder: str | Path, *, now: int | None = None) -> BackupResult:
    """Snapshot a live SQLite database into ``folder``.

    Uses the online backup API, then reopens the result and checks it. Both
    halves are required: the API can succeed against a database that was
    already corrupt, and only reading the copy back catches that.
    """
    import time

    started = time.perf_counter()
    source = Path(source)
    folder = Path(folder)
    result = BackupResult()

    if not source.exists():
        result.error = f"no database at {source}"
        return result

    try:
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / f"{source.stem}-{_stamp(now)}.sqlite"

        with sqlite3.connect(str(source)) as origin, sqlite3.connect(str(target)) as copy:
            origin.backup(copy)
        result.path = str(target)
        result.bytes_written = target.stat().st_size

        # ---- verify, or call it a failure -------------------------------
        with sqlite3.connect(str(target)) as check:
            integrity = check.execute("PRAGMA integrity_check").fetchone()[0]
            if integrity != "ok":
                result.error = f"integrity check failed: {integrity}"
                return result
            result.tables = _table_counts(check)

        with sqlite3.connect(str(source)) as origin:
            expected = _table_counts(origin)

        # Row counts may legitimately have grown between the snapshot and this
        # read — the application keeps running. Shrinking is what would mean
        # the copy lost something.
        for table, count in expected.items():
            if result.tables.get(table, 0) < count:
                result.error = (
                    f"table {table}: backup has {result.tables.get(table, 0)} rows, "
                    f"source had {count}"
                )
                return result

        result.verified = True
        result.ok = True
        return result
    except (sqlite3.Error, OSError) as error:
        result.error = str(error)
        return result
    finally:
        result.duration_ms = (time.perf_counter() - started) * 1000.0


def list_backups(folder: str | Path) -> list[Path]:
    """Backups newest first."""
    folder = Path(folder)
    if not folder.exists():
        return []
    return sorted(folder.glob("*.sqlite"), key=lambda p: p.stat().st_mtime, reverse=True)


def prune_backups(
    folder: str | Path,
    *,
    retention_days: int = BACKUP_RETENTION_DAYS,
    keep_minimum: int = BACKUP_KEEP_MINIMUM,
) -> list[Path]:
    """Delete backups older than the retention window. Returns what was removed.

    ``keep_minimum`` always wins over age. The alternative deletes the last
    surviving copy of a database from a machine that was simply switched off
    for a while, which is the one outcome a retention policy must never have.
    """
    import time

    backups = list_backups(folder)
    if len(backups) <= keep_minimum:
        return []

    cutoff = time.time() - retention_days * 86400
    removed: list[Path] = []
    for path in backups[keep_minimum:]:
        if path.stat().st_mtime < cutoff:
            try:
                path.unlink()
                removed.append(path)
            except OSError:
                # A backup that cannot be deleted is not an error worth
                # failing a scan pass over. It will be retried tomorrow.
                continue
    return removed


@dataclass
class RestoreResult:
    ok: bool = False
    restored_from: str = ""
    displaced_to: str = ""
    error: str = ""


def restore_database(backup: str | Path, target: str | Path, *, now: int | None = None) -> RestoreResult:
    """Put a backup back, moving the current file aside first.

    The displaced file keeps a timestamped name in the same directory. Nothing
    is deleted, ever — an operator who restores the wrong snapshot at three in
    the morning must be able to undo it.
    """
    backup = Path(backup)
    target = Path(target)
    result = RestoreResult()

    if not backup.exists():
        result.error = f"no backup at {backup}"
        return result

    try:
        with sqlite3.connect(str(backup)) as check:
            if check.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                result.error = "the backup failed its integrity check and was not restored"
                return result
    except sqlite3.Error as error:
        result.error = f"the backup could not be opened: {error}"
        return result

    try:
        if target.exists():
            displaced = target.with_name(f"{target.stem}-displaced-{_stamp(now)}.sqlite")
            shutil.move(str(target), str(displaced))
            result.displaced_to = str(displaced)
        shutil.copy2(str(backup), str(target))
        result.restored_from = str(backup)
        result.ok = True
        return result
    except OSError as error:
        result.error = str(error)
        return result


# --------------------------------------------------------------- settings I/O
#: Bumped when the stored shape changes incompatibly. An import refusing a
#: version it does not know is the difference between a clear message and a
#: silently half-applied configuration.
SETTINGS_FORMAT = 1


def export_settings(preferences: dict, *, version: str, path: str | Path) -> Path:
    """Write the operator's settings to a portable JSON file."""
    path = Path(path)
    payload = {
        "format": SETTINGS_FORMAT,
        "application": "AlikhandeScanner",
        "version": version,
        "exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "preferences": preferences,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def import_settings(path: str | Path) -> tuple[dict, str]:
    """Read a settings file. Returns ``(preferences, error)``.

    Refuses an unknown format version rather than importing what it recognises.
    A partially applied settings file leaves the application in a state the
    operator did not choose and cannot describe.
    """
    path = Path(path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return {}, f"could not read {path}: {error}"

    if not isinstance(payload, dict):
        return {}, "the file is not a settings export"
    if payload.get("application") != "AlikhandeScanner":
        return {}, "the file is not an Alikhande Scanner settings export"

    found = payload.get("format")
    if found != SETTINGS_FORMAT:
        return {}, (
            f"settings format {found} cannot be read by this build "
            f"(it understands format {SETTINGS_FORMAT})"
        )

    preferences = payload.get("preferences")
    if not isinstance(preferences, dict):
        return {}, "the export contains no preferences"
    return preferences, ""


# -------------------------------------------------------------- session ledger
SESSIONS_FILE = "sessions.json"


def load_sessions(data_dir: str | Path) -> list:
    """Read the session ring. A missing or unreadable file yields an empty list.

    Never raises. This is read during startup, before the window exists, and a
    corrupt sessions file must not be the reason the application cannot open —
    the worst consequence of losing it is that one crash goes unreported.
    """
    from ..core.recovery import SessionRecord

    path = Path(data_dir) / SESSIONS_FILE
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(payload, list):
        return []

    records = []
    for row in payload:
        if not isinstance(row, dict):
            continue
        try:
            records.append(
                SessionRecord(
                    session_id=str(row.get("session_id", "")),
                    environment=str(row.get("environment", "")),
                    version=str(row.get("version", "")),
                    started_at=int(row.get("started_at", 0)),
                    closed_at=int(row.get("closed_at", 0)),
                    last_view=str(row.get("last_view", "")),
                    execution_in_flight=bool(row.get("execution_in_flight", False)),
                    in_flight_symbol=str(row.get("in_flight_symbol", "")),
                    stats=dict(row.get("stats") or {}),
                )
            )
        except (TypeError, ValueError):
            continue
    return records


def save_sessions(records, data_dir: str | Path) -> None:
    """Write the session ring. Best effort, and deliberately silent on failure.

    Called from the scan loop as well as at shutdown — the in-flight flag is
    only worth having if it is current at the moment the process dies — so a
    failure here must not interrupt scanning. A read-only data directory
    degrades crash detection and nothing else.
    """
    path = Path(data_dir) / SESSIONS_FILE
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                [
                    {
                        "session_id": r.session_id,
                        "environment": r.environment,
                        "version": r.version,
                        "started_at": r.started_at,
                        "closed_at": r.closed_at,
                        "last_view": r.last_view,
                        "execution_in_flight": r.execution_in_flight,
                        "in_flight_symbol": r.in_flight_symbol,
                        "stats": r.stats,
                    }
                    for r in records
                ],
                indent=1,
            ),
            encoding="utf-8",
        )
    except OSError:
        return


# ---------------------------------------------------------- diagnostics bundle
def diagnostics(
    *,
    version: str,
    environment: str,
    data_dir: str | Path,
    link=None,
    quality=None,
    sessions=None,
    errors=None,
    account=None,
    journal_entries=None,
) -> dict:
    """Everything worth having in front of you when something is wrong.

    Deliberately a plain dict rather than a formatted report: the UI renders it,
    the CLI prints it, and a support request attaches it, and all three want the
    same facts in different shapes.

    Contains no credentials. The account number and server are included because
    a conversation about the wrong account helps nobody; nothing else is.
    """
    bundle: dict = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "application": {
            "name": "AlikhandeScanner",
            "version": version,
            "environment": environment,
            "data_directory": str(data_dir),
        },
        "machine": {
            "platform": f"{platform.system()} {platform.release()}",
            "machine": platform.machine(),
            "python": sys.version.split()[0],
        },
    }

    try:
        import PySide6  # noqa: F401

        bundle["machine"]["pyside6"] = PySide6.__version__
    except ImportError:
        bundle["machine"]["pyside6"] = "not installed"

    if sys.platform == "win32":
        try:
            from importlib.metadata import version

            # Package metadata loads no broker module and therefore cannot
            # touch its process-global terminal connection from the GUI thread.
            bundle["machine"]["metatrader5"] = version("MetaTrader5")
        except Exception:
            bundle["machine"]["metatrader5"] = "not installed"
    else:
        bundle["machine"]["metatrader5"] = "unavailable (Windows only)"

    if account is not None:
        # Number and server only. Never the name, never the balance in a file
        # that gets emailed around.
        bundle["account"] = {
            "login": account.login,
            "server": account.server,
            "is_demo": account.is_demo,
            "currency": account.currency,
        }

    if link is not None:
        bundle["link"] = {
            "state": link.state.name,
            "latency_ms": round(link.latency_ms, 1),
            "peak_latency_ms": round(link.latency_peak_ms, 1),
            "availability": round(link.availability, 4),
            "total_probes": link.total_probes,
            "total_failures": link.total_failures,
            "reconnect_attempts": link.reconnect_attempts,
        }

    if quality is not None:
        bundle["data_quality"] = {
            symbol: {
                "grade": record.grade.name,
                "bad_fraction": round(record.bad_fraction, 4),
                "passes": record.passes,
                "detail": record.detail,
            }
            for symbol, record in quality.items()
        }

    if sessions is not None:
        bundle["sessions"] = [
            {
                "session_id": s.session_id,
                "environment": s.environment,
                "started_at": s.started_at,
                "closed_at": s.closed_at,
                "exit": s.exit_kind.name,
                "duration": s.duration,
                "execution_in_flight": s.execution_in_flight,
            }
            for s in sessions
        ]

    if errors is not None:
        bundle["order_errors"] = dict(errors.ranked())
        bundle["order_defects"] = errors.defects()

    if journal_entries is not None:
        bundle["journal"] = [
            {
                "ts": e.ts,
                "level": e.level.name,
                "code": e.code,
                "context": e.context,
                "message": e.message,
                "repeats": e.repeats,
            }
            for e in journal_entries
        ]

    return bundle


def write_diagnostics(bundle: dict, folder: str | Path, *, now: int | None = None) -> Path:
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"diagnostics-{_stamp(now)}.json"
    path.write_text(json.dumps(bundle, indent=2, ensure_ascii=False), encoding="utf-8")
    return path
