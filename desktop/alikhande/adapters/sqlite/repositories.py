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

from ...core.enums import SignalState
from ...core.journal import Event, Level
from ...core.models import (
    ExecutionRecord,
    Outcome,
    RiskState,
    SignalCandidate,
    SymbolSpec,
    TradePlan,
)
from ...core.enums import ExecState
from .database import Database


class Repositories:
    def __init__(self, database: Database) -> None:
        self._db = database

    @property
    def ready(self) -> bool:
        return self._db.is_open

    # ------------------------------------------------------------------- runs
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
        self._db.execute(
            "INSERT OR REPLACE INTO runs(run_id, kind, is_production, app_version,"
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

        ``INSERT OR IGNORE`` rather than ``REPLACE``: the identity of a signal
        is its structural situation, and a signal re-evaluated a few seconds
        later at a slightly different quote is the SAME signal. Replacing would
        overwrite the moment it was first seen, which is the timestamp any
        later analysis depends on.
        """
        if not self.ready:
            return False
        self._db.execute(
            "INSERT OR IGNORE INTO signals(signal_id, run_id, symbol, direction, setup,"
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
        self._db.execute(
            "UPDATE signals SET state = ? WHERE signal_id = ?", (state.name, signal_id)
        )
        self._db.commit()
        return True

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
            " state, request_id, order_ticket, deal_ticket, position_id,"
            " requested_volume, filled_volume, retcode, message, created_at,"
            " updated_at, terminal) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                execution.execution_id,
                execution.plan_id,
                execution.signal_id,
                execution.symbol,
                execution.state.name,
                execution.request_id,
                execution.order_ticket,
                execution.deal_ticket,
                execution.position_id,
                execution.requested_volume,
                execution.filled_volume,
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

        try:
            state = ExecState[row["state"]]
        except KeyError:
            # An unparseable stored state is not a reason to assume the
            # execution finished. UNKNOWN keeps the gate shut.
            state = ExecState.UNKNOWN

        return ExecutionRecord(
            execution_id=row["execution_id"],
            plan_id=row["plan_id"],
            signal_id=row["signal_id"],
            symbol=row["symbol"],
            state=state,
            request_id=row["request_id"] or 0,
            order_ticket=row["order_ticket"] or 0,
            deal_ticket=row["deal_ticket"] or 0,
            position_id=row["position_id"] or 0,
            requested_volume=row["requested_volume"] or 0.0,
            filled_volume=row["filled_volume"] or 0.0,
            retcode=row["retcode"] or 0,
            message=row["message"] or "",
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            terminal=bool(row["terminal"]),
        )

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
                " volume, price, net_profit, recorded_at) VALUES(?,?,?,?,?,?,?,?)",
                (
                    deal_ticket,
                    execution_id,
                    symbol,
                    entry,
                    volume,
                    price,
                    net_profit,
                    recorded_at,
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

    # --------------------------------------------------------------- outcomes
    def save_outcome(self, outcome: Outcome) -> bool:
        if not self.ready:
            return False
        self._db.execute(
            "INSERT OR REPLACE INTO outcomes(signal_id, result, realized_r, mfe_r,"
            " mae_r, closed_at) VALUES(?,?,?,?,?,?)",
            (
                outcome.signal_id,
                outcome.result,
                outcome.realized_r,
                outcome.mfe_r,
                outcome.mae_r,
                outcome.closed_at,
            ),
        )
        self._db.commit()
        return True

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
            " WHERE s.symbol = ? AND s.setup = ? AND s.rule_version = ?"
            "   AND o.result IN ('TP','SL')",
            (symbol, setup, rule_version),
        ).fetchone()
        if row is None or row["total"] is None:
            return 0, 0
        return int(row["wins"] or 0), int(row["total"] or 0)

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
                " WHERE o.result IN ('TP','SL') AND s.rule_version = ?",
                (rule_version,),
            ).fetchone()
        else:
            row = self._db.execute(
                "SELECT COUNT(*) AS total,"
                " SUM(CASE WHEN result='TP' THEN 1 ELSE 0 END) AS wins,"
                " SUM(realized_r) AS sum_r"
                " FROM outcomes WHERE result IN ('TP','SL')"
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
