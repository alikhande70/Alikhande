"""Typed reads and writes over the SQLite schema.

A port of ``Persistence/Repositories.mqh``. Every method is a single statement
with bound parameters — no string-built SQL anywhere, which in MQL5 was a
discipline and here is enforced by the driver.

The important method is ``record_deal_once``. It is an **admission gate**, not
a log: it returns True only the first time a deal ticket is seen, and the
execution engine is only allowed to move fill state when it returns True. The
MQL5 predecessor recorded the ticket and then mutated state regardless, which
made the idempotency decorative — a replayed fill double-counted.
"""

from __future__ import annotations

import sqlite3

from ...core.enums import Direction, RunMode, SignalState
from ...core.journal import Event, Level
from ...core.lifecycle import transition_allowed
from ...core.models import (
    DealInfo,
    ExecutionRecord,
    Outcome,
    RiskState,
    SignalCandidate,
    SymbolSpec,
    TradePlan,
)
from ...core.enums import ExecState
from .database import Database


class SignalIdentityCollision(ValueError):
    """One hash names two different structural signals; never merge them."""


def _direction(value) -> Direction:
    try:
        return Direction(int(value or 0))
    except (TypeError, ValueError):
        return Direction.NONE


def _execution_from_row(row) -> ExecutionRecord:
    try:
        state = ExecState[row["state"]]
    except KeyError:
        state = ExecState.UNKNOWN
    try:
        mode = RunMode[row["execution_mode"]]
    except (KeyError, IndexError):
        mode = RunMode.ALERT_ONLY
    return ExecutionRecord(
        execution_id=row["execution_id"],
        plan_id=row["plan_id"],
        signal_id=row["signal_id"],
        symbol=row["symbol"],
        state=state,
        mode=mode,
        request_id=row["request_id"] or 0,
        order_ticket=row["order_ticket"] or 0,
        deal_ticket=row["deal_ticket"] or 0,
        position_id=row["position_id"] or 0,
        requested_volume=row["requested_volume"] or 0.0,
        filled_volume=row["filled_volume"] or 0.0,
        closed_volume=row["closed_volume"] or 0.0,
        correlation_key=row["correlation_key"] or "",
        direction=_direction(row["direction"]),
        planned_entry=row["planned_entry"] or 0.0,
        stop_loss=row["stop_loss"] or 0.0,
        take_profit=row["take_profit"] or 0.0,
        initial_risk_amount=row["initial_risk_amount"] or 0.0,
        retcode=row["retcode"] or 0,
        message=row["message"] or "",
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        terminal=bool(row["terminal"]),
    )


def _outcome_from_row(row) -> Outcome:
    return Outcome(
        signal_id=row["signal_id"],
        result=row["result"],
        realized_r=row["realized_r"] or 0.0,
        mfe_r=row["mfe_r"],
        mae_r=row["mae_r"],
        closed_at=row["closed_at"] or 0,
        execution_id=row["execution_id"] or "",
        source=row["source"] or "",
        evidence_quality=row["evidence_quality"] or "",
        entry_price=row["entry_price"] or 0.0,
        exit_price=row["exit_price"] or 0.0,
        filled_volume=row["filled_volume"] or 0.0,
        net_profit=row["net_profit"] or 0.0,
        valid_for_statistics=bool(row["valid_for_statistics"]),
        rule_version=row["rule_version"] or "",
        scoring_version=row["scoring_version"] or "",
        parameter_hash=row["parameter_hash"] or "",
        broker_spec_hash=row["broker_spec_hash"] or "",
    )


class Repositories:
    def __init__(self, database: Database) -> None:
        self._db = database

    @property
    def ready(self) -> bool:
        return self._db.is_open

    @property
    def database_path(self) -> str:
        return self._db.path

    def close(self) -> None:
        self._db.close()

    # ------------------------------------------------------------------- runs
    def run_exists(self, run_id: str) -> bool:
        if not self.ready or not run_id:
            return False
        return (
            self._db.execute("SELECT 1 FROM runs WHERE run_id=?", (run_id,)).fetchone()
            is not None
        )

    def start_run(
        self,
        run_id: str,
        kind: str,
        is_production: bool,
        app_version: str,
        rule_version: str,
        scoring_version: str,
        parameter_hash: str,
        symbols: str,
        started_at: int,
        note: str = "",
    ) -> bool:
        if not self.ready:
            return False
        try:
            self._db.execute(
                "INSERT INTO runs(run_id, kind, is_production, app_version,"
                " rule_version, scoring_version, parameter_hash, symbols, started_at, note)"
                " VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    run_id,
                    kind,
                    1 if is_production else 0,
                    app_version,
                    rule_version,
                    scoring_version,
                    parameter_hash,
                    symbols,
                    started_at,
                    note,
                ),
            )
        except sqlite3.IntegrityError:
            return False
        self._db.commit()
        return True

    def finish_run(self, run_id: str, finished_at: int) -> bool:
        if not self.ready:
            return False
        self._db.execute(
            "UPDATE runs SET finished_at = ? WHERE run_id = ?", (finished_at, run_id)
        )
        self._db.commit()
        return True

    # ---------------------------------------------------------------- signals
    def signal_exists(self, signal_id: str) -> bool:
        if not self.ready:
            return False
        row = self._db.execute(
            "SELECT 1 FROM signals WHERE signal_id = ?", (signal_id,)
        ).fetchone()
        return row is not None

    def save_signal(self, signal: SignalCandidate, run_id: str = "") -> bool:
        """Insert a signal, or leave the existing row alone.

        The identity of a signal is its structural situation, and a signal
        re-evaluated a few seconds later at a slightly different quote is the
        SAME signal. Its first row is preserved. If the same hash is already
        attached to a *different* structural tuple, that is a collision and a
        hard failure—not permission to merge two evidence lifecycles.
        """
        if not self.ready:
            return False
        existing = self._db.execute(
            "SELECT symbol, direction, setup, confirmation_bar_time, rule_version"
            ", scoring_version, parameter_hash, broker_spec_hash"
            " FROM signals WHERE signal_id=?",
            (signal.signal_id,),
        ).fetchone()
        if existing is not None:
            stored_identity = (
                existing["symbol"],
                int(existing["direction"]),
                int(existing["setup"]),
                int(existing["confirmation_bar_time"] or 0),
                existing["rule_version"],
                existing["scoring_version"],
                existing["parameter_hash"],
                existing["broker_spec_hash"],
            )
            incoming_identity = (
                signal.symbol,
                int(signal.direction),
                int(signal.setup),
                int(signal.confirmation_bar_time),
                signal.rule_version,
                signal.scoring_version,
                signal.parameter_hash,
                signal.broker_spec_hash,
            )
            if stored_identity != incoming_identity:
                raise SignalIdentityCollision(
                    f"signal id {signal.signal_id} maps to both "
                    f"{stored_identity!r} and {incoming_identity!r}"
                )
            return True
        self._db.execute(
            "INSERT INTO signals(signal_id, run_id, symbol, direction, setup,"
            " state, preferred_entry, stop_loss, take_profit, nearest_support,"
            " nearest_resistance, demand_relation, supply_relation, long_score,"
            " short_score, regime, reasons, validation_codes, confirmation_bar_time,"
            " created_at, expires_at, rule_version, scoring_version, parameter_hash,"
            " broker_spec_hash)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                signal.signal_id,
                run_id,
                signal.symbol,
                int(signal.direction),
                int(signal.setup),
                signal.state.name,
                signal.preferred_entry,
                signal.stop_loss,
                signal.take_profit,
                signal.nearest_support,
                signal.nearest_resistance,
                int(signal.demand_relation),
                int(signal.supply_relation),
                signal.long_score,
                signal.short_score,
                int(signal.regime),
                signal.reasons_text(),
                signal.codes_text(),
                signal.confirmation_bar_time,
                signal.creation_time,
                signal.expires_at,
                signal.rule_version,
                signal.scoring_version,
                signal.parameter_hash,
                signal.broker_spec_hash,
            ),
        )
        self._db.commit()
        return True

    def update_signal_state(self, signal_id: str, state: SignalState) -> bool:
        if not self.ready:
            return False
        current = self.signal_state(signal_id)
        if current is None:
            return False
        if current == state:
            return True
        if not transition_allowed(current, state):
            return False
        cursor = self._db.execute(
            "UPDATE signals SET state = ? WHERE signal_id = ?", (state.name, signal_id)
        )
        self._db.commit()
        return cursor.rowcount == 1

    def signal_state(self, signal_id: str) -> SignalState | None:
        if not self.ready:
            return None
        row = self._db.execute(
            "SELECT state FROM signals WHERE signal_id = ?", (signal_id,)
        ).fetchone()
        if row is None:
            return None
        try:
            return SignalState[row["state"]]
        except KeyError:
            return None

    def signal_metadata(self, signal_id: str) -> dict[str, str]:
        """Version stamps needed when a recovered execution closes."""
        if not self.ready:
            return {}
        row = self._db.execute(
            "SELECT rule_version, scoring_version, parameter_hash, broker_spec_hash"
            " FROM signals WHERE signal_id = ?",
            (signal_id,),
        ).fetchone()
        if row is None:
            return {}
        return {
            "rule_version": row["rule_version"] or "",
            "scoring_version": row["scoring_version"] or "",
            "parameter_hash": row["parameter_hash"] or "",
            "broker_spec_hash": row["broker_spec_hash"] or "",
        }

    def save_feature(self, signal_id: str, name: str, value: float) -> bool:
        if not self.ready:
            return False
        self._db.execute(
            "INSERT OR REPLACE INTO signal_features(signal_id, name, value) VALUES(?,?,?)",
            (signal_id, name, value),
        )
        return True

    def save_features(self, signal_id: str, features: dict[str, float]) -> bool:
        if not self.ready:
            return False
        self._db.connection.executemany(
            "INSERT OR REPLACE INTO signal_features(signal_id, name, value) VALUES(?,?,?)",
            [(signal_id, name, value) for name, value in features.items()],
        )
        self._db.commit()
        return True

    # ------------------------------------------------------------------ plans
    def save_plan(self, plan: TradePlan) -> bool:
        if not self.ready:
            return False
        self._db.execute(
            "INSERT OR REPLACE INTO trade_plans(plan_id, signal_id, symbol, direction,"
            " entry, stop_loss, take_profit, risk_percent, risk_amount,"
            " actual_risk_amount, lot_size, margin_required, created_at, expires_at,"
            " validation_codes) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                plan.plan_id,
                plan.signal_id,
                plan.symbol,
                int(plan.direction),
                plan.entry,
                plan.stop_loss,
                plan.take_profit,
                plan.risk_percent,
                plan.risk_amount,
                plan.actual_risk_amount,
                plan.lot_size,
                plan.margin_required,
                plan.created_at,
                plan.expires_at,
                plan.codes_text(),
            ),
        )
        self._db.commit()
        return True

    # ------------------------------------------------------------- executions
    def save_execution(self, execution: ExecutionRecord) -> bool:
        if not self.ready:
            return False
        self._db.execute(
            "INSERT OR REPLACE INTO executions(execution_id, plan_id, signal_id, symbol,"
            " state, execution_mode, request_id, order_ticket, deal_ticket, position_id,"
            " requested_volume, filled_volume, closed_volume, correlation_key, direction,"
            " planned_entry, stop_loss, take_profit, initial_risk_amount, retcode, message,"
            " created_at, updated_at, terminal)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                execution.execution_id,
                execution.plan_id,
                execution.signal_id,
                execution.symbol,
                execution.state.name,
                execution.mode.name,
                execution.request_id,
                execution.order_ticket,
                execution.deal_ticket,
                execution.position_id,
                execution.requested_volume,
                execution.filled_volume,
                execution.closed_volume,
                execution.correlation_key,
                int(execution.direction),
                execution.planned_entry,
                execution.stop_loss,
                execution.take_profit,
                execution.initial_risk_amount,
                execution.retcode,
                execution.message,
                execution.created_at,
                execution.updated_at,
                1 if execution.terminal else 0,
            ),
        )
        self._db.commit()
        return True

    def load_unresolved_execution(self) -> ExecutionRecord | None:
        """The in-flight execution left behind by a previous session, if any.

        ``terminal = 0`` is what makes a block survive a restart: an execution
        that could not be resolved was stored non-terminal precisely so this
        query finds it and the submit gate stays shut.
        """
        if not self.ready:
            return None
        row = self._db.execute(
            "SELECT * FROM executions WHERE terminal = 0 ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        if row is None:
            return None

        return _execution_from_row(row)

    # ------------------------------------------------------------------ deals
    def record_deal_once(
        self,
        deal_ticket: int,
        *,
        execution_id: str,
        symbol: str,
        entry: int,
        volume: float,
        price: float,
        net_profit: float,
        recorded_at: int,
        order_ticket: int = 0,
        position_id: int = 0,
        broker_time: int = 0,
        reason: str = "",
        comment: str = "",
    ) -> bool:
        """Admission gate. True only the first time this ticket is seen.

        The PRIMARY KEY on ``deals.deal_ticket`` does the work: a second insert
        raises ``IntegrityError``, which is the durable answer to "have I
        already counted this fill?" — durable meaning it survives the restart
        that empties any in-memory set.
        """
        if not self.ready or deal_ticket <= 0:
            return False
        try:
            self._db.execute(
                "INSERT INTO deals(deal_ticket, execution_id, symbol, entry_type,"
                " volume, price, net_profit, recorded_at, order_ticket, position_id,"
                " broker_time, reason, comment) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    deal_ticket,
                    execution_id,
                    symbol,
                    entry,
                    volume,
                    price,
                    net_profit,
                    recorded_at,
                    order_ticket,
                    position_id,
                    broker_time,
                    reason,
                    comment,
                ),
            )
        except sqlite3.IntegrityError:
            return False
        self._db.commit()
        return True

    def known_deal_tickets(self) -> list[int]:
        if not self.ready:
            return []
        return [row[0] for row in self._db.execute("SELECT deal_ticket FROM deals")]

    def deals_for_execution(self, execution_id: str) -> list[DealInfo]:
        """Exact broker facts already admitted for one execution."""
        if not self.ready or not execution_id:
            return []
        rows = self._db.execute(
            "SELECT * FROM deals WHERE execution_id=? ORDER BY broker_time, deal_ticket",
            (execution_id,),
        ).fetchall()
        return [
            DealInfo(
                ticket=int(row["deal_ticket"] or 0),
                order=int(row["order_ticket"] or 0),
                position_id=int(row["position_id"] or 0),
                symbol=row["symbol"] or "",
                entry=int(row["entry_type"] or 0),
                volume=float(row["volume"] or 0.0),
                price=float(row["price"] or 0.0),
                # Stored net is already profit + commission + swap + fee. Keeping it
                # in ``profit`` reconstructs DealInfo.net_profit exactly.
                profit=float(row["net_profit"] or 0.0),
                time=int(row["broker_time"] or 0),
                comment=row["comment"] or "",
                reason=row["reason"] or "",
            )
            for row in rows
        ]

    # --------------------------------------------------------------- outcomes
    def save_outcome(self, outcome: Outcome) -> bool:
        """Persist once; a later replay/error may not rewrite valid evidence."""
        if not self.ready:
            return False
        cursor = self._db.execute(
            "INSERT OR IGNORE INTO outcomes(signal_id, result, realized_r, mfe_r,"
            " mae_r, closed_at, execution_id, source, evidence_quality, entry_price,"
            " exit_price, filled_volume, net_profit, valid_for_statistics, rule_version,"
            " scoring_version, parameter_hash, broker_spec_hash)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                outcome.signal_id,
                outcome.result,
                outcome.realized_r,
                outcome.mfe_r,
                outcome.mae_r,
                outcome.closed_at,
                outcome.execution_id,
                outcome.source,
                outcome.evidence_quality,
                outcome.entry_price,
                outcome.exit_price,
                outcome.filled_volume,
                outcome.net_profit,
                1 if outcome.valid_for_statistics else 0,
                outcome.rule_version,
                outcome.scoring_version,
                outcome.parameter_hash,
                outcome.broker_spec_hash,
            ),
        )
        self._db.commit()
        return cursor.rowcount == 1

    def save_outcome_with_state(
        self,
        outcome: Outcome,
        state: SignalState,
        *,
        risk_state: RiskState | None = None,
    ) -> bool:
        """Commit outcome evidence and its terminal lifecycle state together.

        A crash may occur between any two Python statements. Keeping these two
        writes in one SQLite transaction prevents an outcome row paired with a
        signal that remains ACTIVE forever (or a terminal signal with no
        evidence row).
        """
        if not self.ready:
            return False
        connection = self._db.connection
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT state FROM signals WHERE signal_id=?", (outcome.signal_id,)
            ).fetchone()
            if row is None:
                connection.rollback()
                return False
            try:
                current = SignalState[row["state"]]
            except KeyError:
                connection.rollback()
                return False
            if current != state and not transition_allowed(current, state):
                connection.rollback()
                return False

            cursor = connection.execute(
                "INSERT OR IGNORE INTO outcomes(signal_id, result, realized_r, mfe_r,"
                " mae_r, closed_at, execution_id, source, evidence_quality, entry_price,"
                " exit_price, filled_volume, net_profit, valid_for_statistics, rule_version,"
                " scoring_version, parameter_hash, broker_spec_hash)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    outcome.signal_id,
                    outcome.result,
                    outcome.realized_r,
                    outcome.mfe_r,
                    outcome.mae_r,
                    outcome.closed_at,
                    outcome.execution_id,
                    outcome.source,
                    outcome.evidence_quality,
                    outcome.entry_price,
                    outcome.exit_price,
                    outcome.filled_volume,
                    outcome.net_profit,
                    1 if outcome.valid_for_statistics else 0,
                    outcome.rule_version,
                    outcome.scoring_version,
                    outcome.parameter_hash,
                    outcome.broker_spec_hash,
                ),
            )
            if cursor.rowcount != 1:
                connection.rollback()
                return False
            if current != state:
                connection.execute(
                    "UPDATE signals SET state=? WHERE signal_id=?",
                    (state.name, outcome.signal_id),
                )
            if risk_state is not None:
                connection.execute(
                    "INSERT OR REPLACE INTO risk_state(id, day_key, day_start_equity,"
                    " peak_equity, consecutive_losses, daily_risk_used_pct, updated_at)"
                    " VALUES(1,?,?,?,?,?,?)",
                    (
                        risk_state.day_key,
                        risk_state.day_start_equity,
                        risk_state.peak_equity,
                        risk_state.consecutive_losses,
                        risk_state.daily_risk_used_pct,
                        risk_state.updated_at,
                    ),
                )
            connection.commit()
            return True
        except Exception:
            connection.rollback()
            raise

    def outcome_for_execution(self, execution_id: str) -> Outcome | None:
        if not self.ready or not execution_id:
            return None
        row = self._db.execute(
            "SELECT * FROM outcomes WHERE execution_id = ?", (execution_id,)
        ).fetchone()
        return _outcome_from_row(row) if row is not None else None

    def load_execution_awaiting_outcome(self) -> ExecutionRecord | None:
        """A terminal broker disposition whose outcome was not committed.

        A crash can land after COMPLETED, REJECTED or CANCELLED was persisted
        but before the atomic outcome/lifecycle commit. Returning all three
        prevents a rejected send from becoming a preview that can be submitted
        again after restart.
        """
        if not self.ready:
            return None
        row = self._db.execute(
            "SELECT e.* FROM executions e"
            " LEFT JOIN outcomes o ON o.execution_id = e.execution_id"
            " WHERE e.terminal = 1"
            " AND e.state IN ('COMPLETED','REJECTED','CANCELLED')"
            " AND o.signal_id IS NULL"
            " ORDER BY e.created_at DESC LIMIT 1"
        ).fetchone()
        return _execution_from_row(row) if row is not None else None

    def outcome_counts(self, symbol: str, setup: int, rule_version: str) -> tuple[int, int]:
        """``(wins, total)`` for this symbol, setup and rule version.

        Only TP and SL are counted. Expiry and invalidation say something about
        the scanner, not the setup's edge, and pooling them into a win rate
        would quietly flatter or damn the strategy.

        Scoping by ``rule_version`` is not optional: mixing results from before
        and after a logic change describes a system that never ran.
        """
        if not self.ready:
            return 0, 0
        row = self._db.execute(
            "SELECT"
            "  SUM(CASE WHEN o.result = 'TP' THEN 1 ELSE 0 END) AS wins,"
            "  COUNT(*) AS total"
            " FROM outcomes o JOIN signals s ON s.signal_id = o.signal_id"
            " LEFT JOIN runs r ON r.run_id = s.run_id"
            " WHERE s.symbol = ? AND s.setup = ? AND s.rule_version = ?"
            "   AND o.result IN ('TP','SL') AND o.valid_for_statistics = 1"
            "   AND (r.kind IS NULL OR r.kind <> 'REPLAY' OR r.finished_at IS NOT NULL)",
            (symbol, setup, rule_version),
        ).fetchone()
        if row is None or row["total"] is None:
            return 0, 0
        return int(row["wins"] or 0), int(row["total"] or 0)

    @staticmethod
    def _purge_kind(connection, kind: str) -> None:
        execution_scope = (
            "SELECT e.execution_id FROM executions e"
            " JOIN signals s ON s.signal_id=e.signal_id"
            " JOIN runs r ON r.run_id=s.run_id WHERE r.kind=?"
        )
        signal_scope = (
            "SELECT s.signal_id FROM signals s JOIN runs r ON r.run_id=s.run_id"
            " WHERE r.kind=?"
        )
        connection.execute(
            f"DELETE FROM deals WHERE execution_id IN ({execution_scope})", (kind,)
        )
        connection.execute(
            f"DELETE FROM executions WHERE execution_id IN ({execution_scope})", (kind,)
        )
        for table in ("outcomes", "signal_features", "trade_plans"):
            connection.execute(
                f"DELETE FROM {table} WHERE signal_id IN ({signal_scope})", (kind,)
            )
        connection.execute(
            "DELETE FROM signals WHERE run_id IN (SELECT run_id FROM runs WHERE kind=?)",
            (kind,),
        )
        connection.execute("DELETE FROM runs WHERE kind=?", (kind,))

    def discard_run(self, run_id: str) -> None:
        """Remove one incomplete run without touching any previous evidence."""
        if not self.ready or not run_id:
            return
        connection = self._db.connection
        try:
            connection.execute("BEGIN IMMEDIATE")
            execution_scope = (
                "SELECT execution_id FROM executions WHERE signal_id IN"
                " (SELECT signal_id FROM signals WHERE run_id=?)"
            )
            signal_scope = "SELECT signal_id FROM signals WHERE run_id=?"
            connection.execute(
                f"DELETE FROM deals WHERE execution_id IN ({execution_scope})", (run_id,)
            )
            connection.execute(
                f"DELETE FROM executions WHERE execution_id IN ({execution_scope})", (run_id,)
            )
            for table in ("outcomes", "signal_features", "trade_plans"):
                connection.execute(
                    f"DELETE FROM {table} WHERE signal_id IN ({signal_scope})", (run_id,)
                )
            connection.execute("DELETE FROM signals WHERE run_id=?", (run_id,))
            connection.execute("DELETE FROM runs WHERE run_id=?", (run_id,))
            connection.commit()
        except Exception:
            connection.rollback()
            raise

    def replace_runs_of_kind_from(self, staged_database: str, kind: str) -> int:
        """Atomically swap one evidence kind from a completed staging DB.

        The expensive replay runs elsewhere. The live database sees either its
        previous valid sample or the complete replacement, never a partially
        written run. Any copy error rolls the delete back with the inserts.
        """
        if not self.ready:
            return 0
        connection = self._db.connection
        alias = "staged_evidence"
        connection.execute(f"ATTACH DATABASE ? AS {alias}", (staged_database,))
        try:
            unfinished = connection.execute(
                f"SELECT COUNT(*) FROM {alias}.runs"
                " WHERE kind=? AND finished_at IS NULL",
                (kind,),
            ).fetchone()[0]
            if unfinished:
                raise ValueError("staged evidence contains an unfinished run")
            staged_count = connection.execute(
                f"SELECT COUNT(*) FROM {alias}.signals s"
                f" JOIN {alias}.runs r ON r.run_id=s.run_id WHERE r.kind=?",
                (kind,),
            ).fetchone()[0]

            connection.execute("BEGIN IMMEDIATE")
            self._purge_kind(connection, kind)
            connection.execute(
                f"INSERT INTO runs SELECT * FROM {alias}.runs WHERE kind=?", (kind,)
            )
            connection.execute(
                f"INSERT INTO signals SELECT s.* FROM {alias}.signals s"
                f" JOIN {alias}.runs r ON r.run_id=s.run_id WHERE r.kind=?",
                (kind,),
            )
            for table in ("signal_features", "trade_plans", "outcomes"):
                connection.execute(
                    f"INSERT INTO {table} SELECT child.* FROM {alias}.{table} child"
                    f" JOIN {alias}.signals s ON s.signal_id=child.signal_id"
                    f" JOIN {alias}.runs r ON r.run_id=s.run_id WHERE r.kind=?",
                    (kind,),
                )
            connection.execute(
                f"INSERT INTO executions SELECT e.* FROM {alias}.executions e"
                f" JOIN {alias}.signals s ON s.signal_id=e.signal_id"
                f" JOIN {alias}.runs r ON r.run_id=s.run_id WHERE r.kind=?",
                (kind,),
            )
            connection.execute(
                f"INSERT INTO deals SELECT d.* FROM {alias}.deals d"
                f" JOIN {alias}.executions e ON e.execution_id=d.execution_id"
                f" JOIN {alias}.signals s ON s.signal_id=e.signal_id"
                f" JOIN {alias}.runs r ON r.run_id=s.run_id WHERE r.kind=?",
                (kind,),
            )
            connection.commit()
            return int(staged_count)
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.execute(f"DETACH DATABASE {alias}")

    def outcome_provenance(
        self, symbol: str, setup: int, rule_version: str
    ) -> tuple[int, int, set[str]]:
        """``(wins, total, run kinds)`` for this symbol, setup and rule version.

        The same query as :meth:`outcome_counts` plus the set of run kinds the
        counted outcomes came from. Kept separate rather than widening
        ``outcome_counts``, because that method is the ``OutcomeCounter``
        protocol the pure statistics layer depends on, and that protocol is
        deliberately as narrow as it is.

        The join to ``runs`` is a LEFT JOIN: a signal written with no run
        attached has a null ``run_id``, and dropping those rows would silently
        shrink a sample rather than label it. They come back as an unrecognised
        kind, which :func:`core.evidence.provenance_of` maps to ``NONE`` —
        unknown provenance, stated as such.
        """
        if not self.ready:
            return 0, 0, set()
        rows = self._db.execute(
            "SELECT o.result AS result, r.kind AS kind"
            " FROM outcomes o"
            " JOIN signals s ON s.signal_id = o.signal_id"
            " LEFT JOIN runs r ON r.run_id = s.run_id"
            " WHERE s.symbol = ? AND s.setup = ? AND s.rule_version = ?"
            "   AND o.result IN ('TP','SL') AND o.valid_for_statistics = 1"
            "   AND (r.kind IS NULL OR r.kind <> 'REPLAY' OR r.finished_at IS NOT NULL)",
            (symbol, setup, rule_version),
        ).fetchall()

        wins = sum(1 for row in rows if row["result"] == "TP")
        kinds = {row["kind"] for row in rows if row["kind"]}
        return wins, len(rows), kinds

    def outcome_summary(self, rule_version: str | None = None) -> dict[str, float]:
        """Aggregate statistics across every scorable outcome.

        Used by the backtest report and the Risk tab. Returns zeros rather than
        None for an empty database so callers can render without branching —
        and a zero sample size is itself the honest answer.
        """
        if not self.ready:
            return {"total": 0, "wins": 0, "losses": 0, "sum_r": 0.0, "avg_r": 0.0}

        if rule_version:
            row = self._db.execute(
                "SELECT COUNT(*) AS total,"
                " SUM(CASE WHEN o.result='TP' THEN 1 ELSE 0 END) AS wins,"
                " SUM(o.realized_r) AS sum_r"
                " FROM outcomes o JOIN signals s ON s.signal_id = o.signal_id"
                " LEFT JOIN runs r ON r.run_id = s.run_id"
                " WHERE o.result IN ('TP','SL') AND o.valid_for_statistics = 1"
                " AND s.rule_version = ?"
                " AND (r.kind IS NULL OR r.kind <> 'REPLAY' OR r.finished_at IS NOT NULL)",
                (rule_version,),
            ).fetchone()
        else:
            row = self._db.execute(
                "SELECT COUNT(*) AS total,"
                " SUM(CASE WHEN o.result='TP' THEN 1 ELSE 0 END) AS wins,"
                " SUM(o.realized_r) AS sum_r"
                " FROM outcomes o JOIN signals s ON s.signal_id=o.signal_id"
                " LEFT JOIN runs r ON r.run_id=s.run_id"
                " WHERE o.result IN ('TP','SL')"
                " AND o.valid_for_statistics = 1"
                " AND (r.kind IS NULL OR r.kind <> 'REPLAY' OR r.finished_at IS NOT NULL)"
            ).fetchone()

        total = int(row["total"] or 0)
        wins = int(row["wins"] or 0)
        sum_r = float(row["sum_r"] or 0.0)
        return {
            "total": total,
            "wins": wins,
            "losses": total - wins,
            "sum_r": sum_r,
            "avg_r": sum_r / total if total else 0.0,
        }

    # ------------------------------------------------------------- risk state
    def save_risk_state(self, state: RiskState) -> bool:
        if not self.ready:
            return False
        self._db.execute(
            "INSERT OR REPLACE INTO risk_state(id, day_key, day_start_equity,"
            " peak_equity, consecutive_losses, daily_risk_used_pct, updated_at)"
            " VALUES(1,?,?,?,?,?,?)",
            (
                state.day_key,
                state.day_start_equity,
                state.peak_equity,
                state.consecutive_losses,
                state.daily_risk_used_pct,
                state.updated_at,
            ),
        )
        self._db.commit()
        return True

    def load_risk_state(self) -> RiskState | None:
        if not self.ready:
            return None
        row = self._db.execute("SELECT * FROM risk_state WHERE id = 1").fetchone()
        if row is None:
            return None
        return RiskState(
            day_key=row["day_key"] or 0,
            day_start_equity=row["day_start_equity"] or 0.0,
            peak_equity=row["peak_equity"] or 0.0,
            consecutive_losses=row["consecutive_losses"] or 0,
            daily_risk_used_pct=row["daily_risk_used_pct"] or 0.0,
            updated_at=row["updated_at"] or 0,
        )

    # ------------------------------------------------------------------ specs
    def save_spec(self, spec: SymbolSpec, now: int) -> bool:
        if not self.ready:
            return False
        self._db.execute(
            "INSERT OR REPLACE INTO symbol_specs(symbol, fingerprint, digits, point,"
            " tick_size, tick_value, contract_size, volume_min, volume_step,"
            " stops_level, freeze_level, updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                spec.symbol,
                spec.fingerprint,
                spec.digits,
                spec.point,
                spec.tick_size,
                spec.tick_value,
                spec.contract_size,
                spec.volume_min,
                spec.volume_step,
                spec.stops_level,
                spec.freeze_level,
                now,
            ),
        )
        self._db.commit()
        return True

    def spec_fingerprint(self, symbol: str) -> str | None:
        """The last recorded fingerprint, so drift can be detected.

        A broker changing a contract's tick value or minimum volume overnight
        silently changes what every stored position size meant. Comparing
        fingerprints turns that into a visible event.
        """
        if not self.ready:
            return None
        row = self._db.execute(
            "SELECT fingerprint FROM symbol_specs WHERE symbol = ?", (symbol,)
        ).fetchone()
        return row["fingerprint"] if row else None

    # ----------------------------------------------------------------- events
    def log_event(self, event: Event) -> bool:
        if not self.ready:
            return False
        self._db.execute(
            "INSERT INTO runtime_events(ts, level, code, context, message)"
            " VALUES(?,?,?,?,?)",
            (event.ts, event.level.name, event.code, event.context, event.message),
        )
        self._db.commit()
        return True

    def recent_events(self, limit: int = 100) -> list[Event]:
        if not self.ready:
            return []
        rows = self._db.execute(
            "SELECT ts, level, code, context, message FROM runtime_events"
            " ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        events: list[Event] = []
        for row in reversed(rows):
            try:
                level = Level[row["level"]]
            except KeyError:
                level = Level.INFO
            events.append(
                Event(
                    ts=row["ts"],
                    level=level,
                    code=row["code"],
                    context=row["context"] or "",
                    message=row["message"] or "",
                )
            )
        return events
