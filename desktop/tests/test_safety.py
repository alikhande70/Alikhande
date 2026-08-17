"""Tests for every safety gate.

If one file in this repository must not be allowed to rot, it is this one. Each
test names the failure it prevents, because a gate whose purpose is forgotten
gets "simplified" away by the next person reading the code.

The central one is ``TestUnresolvedExecution``: an execution the broker cannot
account for must keep the submit gate shut, survive a restart still shut, and
open only on a deliberate, recorded human acknowledgement.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from alikhande.adapters.offline.gateway import OfflineGateway, default_spec
from alikhande.config import AppConfig
from alikhande.core.arming import IntentArming
from alikhande.core.calendar_gate import (
    CalendarEvent,
    CalendarGate,
    CsvCalendar,
    StaticCalendar,
)
from alikhande.core.enums import (
    Direction,
    ExecState,
    NewsSource,
    NewsState,
    RunMode,
    RuntimeKind,
    SetupType,
)
from alikhande.core.execution import DealLedger, ExecutionEngine, may_be_auto_terminal
from alikhande.core.guards import AccountRiskGuard, TradeGuards
from alikhande.core.journal import Journal
from alikhande.core.models import (
    AccountInfo,
    DealInfo,
    ExecutionRecord,
    PositionInfo,
    RiskState,
    SignalCandidate,
    SymbolSpec,
    TradePlan,
)
from alikhande.core.portfolio import PortfolioRisk, position_risk
from alikhande.core.risk import RiskPlanner, normalize_volume
from alikhande.core.runtime import detect_runtime, persistence_plan


def demo_account(equity: float = 10_000.0) -> AccountInfo:
    return AccountInfo(
        login=1, currency="USD", balance=equity, equity=equity,
        margin_free=equity, is_demo=True, trade_allowed=True,
    )


def real_account(equity: float = 10_000.0) -> AccountInfo:
    return AccountInfo(
        login=2, currency="USD", balance=equity, equity=equity,
        margin_free=equity, is_demo=False, trade_allowed=True,
    )


def valid_plan(symbol: str = "EURUSD", now: int = 1000) -> TradePlan:
    return TradePlan(
        plan_id="P1", signal_id="S1", symbol=symbol, direction=Direction.LONG,
        entry=1.10000, stop_loss=1.09800, take_profit=1.10400,
        risk_percent=0.25, risk_amount=25.0, actual_risk_amount=20.0,
        lot_size=0.10, margin_required=110.0, created_at=now,
        expires_at=now + 30, max_drift_points=30.0, minimum_rr=2.0, valid=True,
    )


class StubGateway:
    """A broker that answers exactly what a test tells it to.

    Deliberately silent by default — every reconciliation source returns
    nothing — because "the broker says nothing" is the state the P0 is about.
    """

    def __init__(self, account: AccountInfo | None = None, *, tick_time: int = 1000):
        self._account = account or demo_account()
        self.sent: list = []
        self.result = None
        self.positions_list: list[PositionInfo] = []
        self.orders_list: list = []
        self.history_orders_list: list = []
        self.history_deals_list: list[DealInfo] = []
        self.history_deal_magic_args: list[int | None] = []
        self.tick_time = tick_time
        self.check_ok = True

    def is_connected(self): return True
    def server_time(self): return self.tick_time
    def symbols(self): return ["EURUSD"]
    def resolve_symbol(self, requested): return requested
    def symbol_spec(self, symbol): return default_spec(symbol)

    def tick(self, symbol):
        from alikhande.core.models import Tick
        return Tick(time=self.tick_time, bid=1.09999, ask=1.10001)

    def bars(self, symbol, timeframe, count): return []
    def account(self): return self._account
    def positions(self, magic=None): return list(self.positions_list)
    def orders(self, magic=None): return list(self.orders_list)
    def history_orders(self, since, until, magic=None): return list(self.history_orders_list)
    def history_deals(self, since, until, magic=None):
        self.history_deal_magic_args.append(magic)
        return list(self.history_deals_list)
    def calc_profit(self, symbol, direction, volume, price_open, price_close): return -20.0
    def calc_margin(self, symbol, direction, volume, price): return 110.0
    def check_order(self, request): return (self.check_ok, 0, "ok")

    def send_order(self, request):
        from alikhande.core.models import OrderResult
        self.sent.append(request)
        return self.result or OrderResult(
            ok=True, retcode=10009, order=11, deal=22, request_id=33,
            volume=request.volume, price=request.price,
        )


# ---------------------------------------------------------------------------
class TestRealAccountBlock(unittest.TestCase):
    """No configuration, input or mode may reach a live account."""

    def test_no_run_mode_selects_live_trading(self):
        self.assertEqual(
            {m.name for m in RunMode}, {"ALERT_ONLY", "SHADOW", "DEMO_CONFIRM"}
        )

    def test_submit_refuses_a_real_account(self):
        gateway = StubGateway(real_account())
        engine = ExecutionEngine(AppConfig(), Journal())
        ok, reason = engine.submit(
            valid_plan(), RunMode.DEMO_CONFIRM, gateway=gateway,
            account=real_account(), spec=default_spec("EURUSD"), now=1000,
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "REAL_ACCOUNT_BLOCKED")
        self.assertEqual(gateway.sent, [], "no order may reach the gateway")

    def test_submit_refuses_when_there_is_no_account(self):
        gateway = StubGateway()
        engine = ExecutionEngine(AppConfig(), Journal())
        ok, reason = engine.submit(
            valid_plan(), RunMode.DEMO_CONFIRM, gateway=gateway,
            account=None, spec=default_spec("EURUSD"), now=1000,
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "NO_ACCOUNT")

    def test_alert_only_never_sends(self):
        gateway = StubGateway()
        engine = ExecutionEngine(AppConfig(), Journal())
        ok, reason = engine.submit(
            valid_plan(), RunMode.ALERT_ONLY, gateway=gateway,
            account=demo_account(), spec=default_spec("EURUSD"), now=1000,
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "ALERT_ONLY_MODE")
        self.assertEqual(gateway.sent, [])

    def test_shadow_runs_the_full_path_but_sends_nothing(self):
        gateway = StubGateway()
        engine = ExecutionEngine(AppConfig(), Journal())
        ok, reason = engine.submit(
            valid_plan(), RunMode.SHADOW, gateway=gateway,
            account=demo_account(), spec=default_spec("EURUSD"), now=1000,
        )
        self.assertTrue(ok)
        self.assertEqual(reason, "SHADOW_MODE")
        self.assertEqual(gateway.sent, [])
        self.assertEqual(engine.current.message, "SHADOW_NOT_SENT")
        self.assertTrue(engine.current.terminal)

    def test_shadow_can_rehearse_a_real_account_without_sending(self):
        gateway = StubGateway(real_account())
        engine = ExecutionEngine(AppConfig(), Journal(), environment="PRODUCTION")
        ok, reason = engine.submit(
            valid_plan(), RunMode.SHADOW, gateway=gateway,
            account=real_account(), spec=default_spec("EURUSD"), now=1000,
        )
        self.assertTrue(ok)
        self.assertEqual(reason, "SHADOW_MODE")
        self.assertEqual(gateway.sent, [])

    def test_offline_gateway_refuses_independently_of_the_engine(self):
        """Defence in depth: the gateway refuses even if the engine is bypassed."""
        from alikhande.core.models import OrderRequest

        gateway = OfflineGateway(is_demo=False)
        result = gateway.send_order(
            OrderRequest(
                symbol="EURUSD", direction=Direction.LONG, volume=0.1, price=1.1,
                stop_loss=1.09, take_profit=1.12, deviation=10, magic=1, comment="x",
            )
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.comment, "REAL_ACCOUNT_BLOCKED")

    def test_only_the_execution_module_calls_send_order(self):
        """The single-OrderSend-boundary property, asserted mechanically.

        Matches a CALL — ``send_order(`` — rather than any mention of the name.
        The in-app guide explains the boundary in prose, and a check that
        flagged the documentation for describing the rule it documents would
        get the rule weakened rather than the prose fixed.
        """
        import pathlib
        import re

        root = pathlib.Path(__file__).resolve().parent.parent / "alikhande"
        call = re.compile(r"\bsend_order\s*\(")
        offenders = []
        for path in root.rglob("*.py"):
            relative = path.relative_to(root).as_posix()
            # The engine calls it; the ports declare it; the adapters implement
            # it. Nothing else may call it.
            if relative in ("core/execution.py", "core/ports.py"):
                continue
            if relative.startswith("adapters/"):
                continue
            if call.search(path.read_text(encoding="utf-8")):
                offenders.append(relative)
        self.assertEqual(offenders, [], f"send_order called outside the boundary: {offenders}")

    def test_the_boundary_check_would_actually_catch_a_call(self):
        """Guard the guard: a check that matches nothing proves nothing."""
        import re

        call = re.compile(r"\bsend_order\s*\(")
        self.assertTrue(call.search("gateway.send_order(request)"))
        self.assertTrue(call.search("    send_order (req)"))
        self.assertIsNone(call.search("the adapter refuses inside send_order, again"))


# ---------------------------------------------------------------------------
class TestUnresolvedExecution(unittest.TestCase):
    """The P0: an unresolved execution must never release the submit gate."""

    def test_unknown_is_not_an_auto_terminal_state(self):
        self.assertFalse(may_be_auto_terminal(ExecState.UNKNOWN))
        self.assertFalse(may_be_auto_terminal(ExecState.RECONCILING))
        self.assertFalse(may_be_auto_terminal(ExecState.POSITION_ACTIVE))
        self.assertFalse(may_be_auto_terminal(ExecState.FILLED))
        for state in (ExecState.COMPLETED, ExecState.REJECTED, ExecState.CANCELLED):
            self.assertTrue(may_be_auto_terminal(state))

    def _wedged_engine(self):
        """An engine whose order left and whose broker then went silent."""
        from alikhande.core.models import OrderResult

        gateway = StubGateway()
        gateway.result = OrderResult(ok=True, retcode=99999, comment="weird")
        engine = ExecutionEngine(AppConfig(), Journal())
        engine.submit(
            valid_plan(), RunMode.DEMO_CONFIRM, gateway=gateway,
            account=demo_account(), spec=default_spec("EURUSD"), now=1000,
        )
        return engine, gateway

    def test_an_unrecognised_retcode_becomes_unknown_not_rejected(self):
        engine, _ = self._wedged_engine()
        self.assertEqual(engine.current.state, ExecState.UNKNOWN)
        self.assertFalse(engine.current.terminal)
        self.assertTrue(engine.has_unresolved())

    def test_an_unrecognised_negative_result_is_also_unknown(self):
        gateway = StubGateway()
        from alikhande.core.models import OrderResult

        gateway.result = OrderResult(ok=False, retcode=77777, comment="custom broker code")
        engine = ExecutionEngine(AppConfig(), Journal())
        accepted, _ = engine.submit(
            valid_plan(), RunMode.DEMO_CONFIRM, gateway=gateway,
            account=demo_account(), spec=default_spec("EURUSD"), now=1000,
        )
        self.assertFalse(accepted)
        self.assertEqual(engine.current.state, ExecState.UNKNOWN)
        self.assertFalse(engine.current.terminal)

    def test_send_transport_exception_is_uncertain_not_rejected(self):
        gateway = StubGateway()

        def transport_failed(_request):
            raise RuntimeError("IPC reply lost")

        gateway.send_order = transport_failed
        engine = ExecutionEngine(AppConfig(), Journal())
        accepted, reason = engine.submit(
            valid_plan(), RunMode.DEMO_CONFIRM, gateway=gateway,
            account=demo_account(), spec=default_spec("EURUSD"), now=1000,
        )
        self.assertFalse(accepted)
        self.assertIn("ORDER_SEND_UNCERTAIN", reason)
        self.assertEqual(engine.current.state, ExecState.UNKNOWN)
        self.assertFalse(engine.current.terminal)
        self.assertTrue(engine.has_unresolved())
        self.assertTrue(engine.current.correlation_key)

    def test_reconcile_leaves_a_silent_broker_unresolved_and_non_terminal(self):
        engine, gateway = self._wedged_engine()
        # Well past the grace period, every source still silent.
        engine.reconcile(gateway, 1000 + 10_000)
        self.assertEqual(engine.current.state, ExecState.UNKNOWN)
        self.assertFalse(
            engine.current.terminal,
            "an unresolved execution must never be recorded as finished",
        )
        self.assertTrue(engine.has_unresolved())
        self.assertTrue(engine.requires_manual_review())

    def test_the_next_order_is_refused_while_unresolved(self):
        engine, gateway = self._wedged_engine()
        engine.reconcile(gateway, 1000 + 10_000)
        before = len(gateway.sent)
        ok, reason = engine.submit(
            valid_plan(now=20_000), RunMode.DEMO_CONFIRM, gateway=gateway,
            account=demo_account(), spec=default_spec("EURUSD"), now=20_000,
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "UNRESOLVED_MANUAL_REVIEW_REQUIRED")
        self.assertEqual(len(gateway.sent), before, "no further order may leave")

    def test_the_block_survives_a_restart(self):
        """Stored non-terminal, so a fresh process reloads a shut gate."""
        engine, gateway = self._wedged_engine()
        engine.reconcile(gateway, 1000 + 10_000)
        stored = engine.current

        restarted = ExecutionEngine(AppConfig(), Journal())
        restarted.recover_after_restart(stored, 30_000)
        self.assertTrue(restarted.has_unresolved())
        self.assertTrue(restarted.requires_manual_review())
        ok, _ = restarted.submit(
            valid_plan(now=30_000), RunMode.DEMO_CONFIRM, gateway=gateway,
            account=demo_account(), spec=default_spec("EURUSD"), now=30_000,
        )
        self.assertFalse(ok)

    def test_acknowledgement_requires_a_real_note(self):
        engine, gateway = self._wedged_engine()
        engine.reconcile(gateway, 1000 + 10_000)
        self.assertFalse(engine.acknowledge_unresolved("", 20_000))
        self.assertFalse(engine.acknowledge_unresolved("   ", 20_000))
        self.assertTrue(engine.requires_manual_review())

    def test_acknowledgement_clears_and_is_recorded(self):
        engine, gateway = self._wedged_engine()
        engine.reconcile(gateway, 1000 + 10_000)
        self.assertTrue(engine.acknowledge_unresolved("verified in terminal", 20_000))
        self.assertFalse(engine.has_unresolved())
        self.assertIn("ACKNOWLEDGED", engine.current.message)

    def test_a_live_position_resolves_but_stays_non_terminal(self):
        engine, gateway = self._wedged_engine()
        gateway.positions_list = [
            PositionInfo(ticket=5, symbol="EURUSD", magic=AppConfig().execution.magic,
                         position_id=5, direction=Direction.LONG, volume=0.1,
                         comment=engine.current.correlation_key)
        ]
        engine.reconcile(gateway, 1000 + 10_000)
        self.assertEqual(engine.current.state, ExecState.POSITION_ACTIVE)
        self.assertFalse(engine.current.terminal, "an open position is not a finished execution")
        self.assertTrue(engine.has_unresolved())

    def test_a_working_order_resolves_but_stays_non_terminal(self):
        from alikhande.core.models import OrderInfo

        engine, gateway = self._wedged_engine()
        gateway.orders_list = [
            OrderInfo(ticket=11, symbol="EURUSD", magic=AppConfig().execution.magic,
                      state="PLACED", comment=engine.current.correlation_key)
        ]
        engine.reconcile(gateway, 1000 + 10_000)
        self.assertEqual(engine.current.state, ExecState.ACCEPTED)
        self.assertFalse(engine.current.terminal)

    def test_history_deals_resolve_a_round_trip_as_completed(self):
        engine, gateway = self._wedged_engine()
        magic = AppConfig().execution.magic
        gateway.history_deals_list = [
            DealInfo(ticket=1, order=11, position_id=7, symbol="EURUSD", magic=magic,
                     entry=0, volume=0.10, price=1.10, time=1100,
                     comment=engine.current.correlation_key),
            # A manual/SL/TP exit may not inherit the opener's magic. Exact
            # position identity must still close this execution.
            DealInfo(ticket=2, order=12, position_id=7, symbol="EURUSD", magic=0,
                     entry=1, volume=0.10, price=1.10400, time=1200),
        ]
        engine.reconcile(gateway, 1000 + 10_000)
        self.assertEqual(engine.current.state, ExecState.COMPLETED)
        self.assertTrue(engine.current.terminal)
        self.assertFalse(engine.has_unresolved())
        self.assertIsNone(gateway.history_deal_magic_args[-1])

    def test_historical_entry_without_current_or_exit_truth_needs_review(self):
        engine, gateway = self._wedged_engine()
        gateway.history_deals_list = [
            DealInfo(ticket=1, order=11, position_id=7, symbol="EURUSD",
                     magic=AppConfig().execution.magic, entry=0, volume=0.10,
                     price=1.10, time=1100, comment=engine.current.correlation_key),
        ]
        engine.reconcile(gateway, 1000 + 10_000)
        self.assertEqual(engine.current.state, ExecState.UNKNOWN)
        self.assertFalse(engine.current.terminal)
        self.assertTrue(engine.requires_manual_review())
        self.assertAlmostEqual(engine.current.filled_volume, 0.10)

    def test_a_raising_source_does_not_count_as_an_answer(self):
        engine, gateway = self._wedged_engine()

        def explode(*_args, **_kwargs):
            raise RuntimeError("connection lost")

        gateway.positions = explode
        gateway.orders = explode
        gateway.history_orders = explode
        gateway.history_deals = explode
        engine.reconcile(gateway, 1000 + 10_000)
        self.assertEqual(engine.current.state, ExecState.UNKNOWN)
        self.assertFalse(engine.current.terminal)

    def test_same_symbol_is_never_a_transaction_identity(self):
        """An older scanner trade on EURUSD must not be stolen by this intent."""
        engine, gateway = self._wedged_engine()
        gateway.positions_list = [
            PositionInfo(
                ticket=77,
                position_id=77,
                symbol="EURUSD",
                magic=AppConfig().execution.magic,
                direction=Direction.LONG,
                volume=0.1,
                comment="AK-OLDER-EXECUTION",
            )
        ]
        engine.reconcile(gateway, 1000 + 10_000)
        self.assertEqual(engine.current.state, ExecState.UNKNOWN)
        self.assertNotEqual(engine.current.position_id, 77)

    def test_exact_comment_recovers_when_send_response_tickets_were_lost(self):
        engine, gateway = self._wedged_engine()
        self.assertEqual(engine.current.order_ticket, 0)
        gateway.history_deals_list = [
            DealInfo(
                ticket=90,
                order=80,
                position_id=70,
                symbol="EURUSD",
                magic=AppConfig().execution.magic,
                entry=0,
                volume=0.1,
                price=1.1,
                time=1001,
                comment=engine.current.correlation_key,
            )
        ]
        engine.reconcile(gateway, 1001)
        self.assertEqual(engine.current.state, ExecState.FILLED)
        self.assertEqual(engine.current.position_id, 70)
        self.assertEqual(engine.current.order_ticket, 80)

    def test_deal_learned_position_id_finds_a_position_without_a_comment(self):
        engine, gateway = self._wedged_engine()
        key = engine.current.correlation_key
        gateway.history_deals_list = [
            DealInfo(
                ticket=90,
                order=80,
                position_id=70,
                symbol="EURUSD",
                magic=AppConfig().execution.magic,
                entry=0,
                volume=0.1,
                price=1.1,
                time=1001,
                comment=key,
            )
        ]
        # Some brokers do not copy the opening order comment onto a position.
        # The exact position id learned above must bridge that gap in this pass.
        gateway.positions_list = [
            PositionInfo(
                ticket=70,
                position_id=70,
                symbol="EURUSD",
                magic=AppConfig().execution.magic,
                direction=Direction.LONG,
                volume=0.1,
                comment="",
            )
        ]
        engine.reconcile(gateway, 1000 + 10_000)
        self.assertEqual(engine.current.state, ExecState.POSITION_ACTIVE)
        self.assertFalse(engine.requires_manual_review())

    def test_closed_observed_partial_fill_stays_unknown_if_live_reads_fail(self):
        engine, gateway = self._wedged_engine()
        key = engine.current.correlation_key
        gateway.history_deals_list = [
            DealInfo(ticket=1, order=11, position_id=7, symbol="EURUSD",
                     entry=0, volume=0.05, price=1.1, time=1001, comment=key),
            DealInfo(ticket=2, order=12, position_id=7, symbol="EURUSD",
                     entry=1, volume=0.05, price=1.101, time=1002, reason="CLIENT"),
        ]
        gateway.orders = lambda *_a, **_k: (_ for _ in ()).throw(
            RuntimeError("orders unavailable")
        )
        engine.reconcile(gateway, 1002)
        self.assertEqual(engine.current.state, ExecState.UNKNOWN)
        self.assertFalse(engine.current.terminal)

        restarted = ExecutionEngine(AppConfig(), Journal())
        restarted.recover_after_restart(engine.current, 1003)
        persisted = restarted.truth_from_persisted_deals(
            list(gateway.history_deals_list)
        )
        self.assertEqual(persisted.state, ExecState.UNKNOWN)
        self.assertFalse(persisted.terminal)

    def test_duplicate_history_deal_ticket_is_counted_once(self):
        engine, gateway = self._wedged_engine()
        key = engine.current.correlation_key
        entry = DealInfo(
            ticket=1, order=11, position_id=7, symbol="EURUSD", entry=0,
            volume=0.1, price=1.1, time=1001, comment=key,
        )
        gateway.history_deals_list = [
            entry,
            entry,
            DealInfo(ticket=2, order=12, position_id=7, symbol="EURUSD",
                     entry=1, volume=0.1, price=1.104, time=1002, reason="TP"),
        ]
        truth = engine.reconcile(gateway, 1002)
        self.assertTrue(truth.terminal)
        self.assertAlmostEqual(truth.filled_volume, 0.1)

    def test_history_deals_outrank_a_filled_history_order(self):
        """A closed round trip may not stick forever at FILLED."""
        from alikhande.core.models import OrderInfo

        engine, gateway = self._wedged_engine()
        key = engine.current.correlation_key
        magic = AppConfig().execution.magic
        gateway.history_orders_list = [
            OrderInfo(
                ticket=11,
                symbol="EURUSD",
                magic=magic,
                state="FILLED",
                volume_initial=0.1,
                comment=key,
            )
        ]
        gateway.history_deals_list = [
            DealInfo(ticket=1, order=11, position_id=7, symbol="EURUSD", magic=magic,
                     entry=0, volume=0.1, price=1.1, time=1100, comment=key),
            DealInfo(ticket=2, order=12, position_id=7, symbol="EURUSD", magic=magic,
                     entry=1, volume=0.1, price=1.104, time=1200, reason="TP"),
        ]
        engine.reconcile(gateway, 2000)
        self.assertEqual(engine.current.state, ExecState.COMPLETED)
        self.assertTrue(engine.current.terminal)

    def test_unlinked_entry_into_same_netting_position_is_ambiguous(self):
        engine, gateway = self._wedged_engine()
        key = engine.current.correlation_key
        magic = AppConfig().execution.magic
        gateway.history_deals_list = [
            DealInfo(ticket=1, order=11, position_id=7, symbol="EURUSD", magic=magic,
                     entry=0, volume=0.1, price=1.1, time=1001, comment=key),
            DealInfo(ticket=2, order=22, position_id=7, symbol="EURUSD", magic=0,
                     entry=0, volume=0.1, price=1.101, time=1002, comment="manual"),
        ]
        engine.reconcile(gateway, 1002)
        self.assertEqual(engine.current.state, ExecState.UNKNOWN)
        self.assertTrue(engine.requires_manual_review())

    def test_mixed_or_missing_exit_reason_is_not_promoted_to_tp(self):
        engine, gateway = self._wedged_engine()
        key = engine.current.correlation_key
        magic = AppConfig().execution.magic
        gateway.history_deals_list = [
            DealInfo(ticket=1, order=11, position_id=7, symbol="EURUSD", magic=magic,
                     entry=0, volume=0.1, price=1.1, time=1001, comment=key),
            DealInfo(ticket=2, order=12, position_id=7, symbol="EURUSD", magic=magic,
                     entry=1, volume=0.05, price=1.104, time=1002, reason=""),
            DealInfo(ticket=3, order=13, position_id=7, symbol="EURUSD", magic=magic,
                     entry=1, volume=0.05, price=1.104, time=1003, reason="TP"),
        ]
        truth = engine.reconcile(gateway, 1003)
        self.assertTrue(truth.terminal)
        self.assertEqual(truth.close_reason, "MIXED")

    def test_exact_entry_volume_above_request_is_ambiguous(self):
        engine, gateway = self._wedged_engine()
        key = engine.current.correlation_key
        magic = AppConfig().execution.magic
        gateway.history_deals_list = [
            DealInfo(ticket=1, order=11, position_id=7, symbol="EURUSD", magic=magic,
                     entry=0, volume=0.06, price=1.1, time=1001, comment=key),
            DealInfo(ticket=2, order=11, position_id=7, symbol="EURUSD", magic=magic,
                     entry=0, volume=0.06, price=1.1, time=1002, comment=key),
        ]
        engine.reconcile(gateway, 1002)
        self.assertEqual(engine.current.state, ExecState.UNKNOWN)
        self.assertTrue(engine.requires_manual_review())

    def test_transaction_event_cannot_claim_a_foreign_netting_entry(self):
        engine, _ = self._wedged_engine()
        engine.current.position_id = 7
        engine.current.filled_volume = 0.1
        engine.current.state = ExecState.POSITION_ACTIVE
        admitted = engine.apply_deal(
            DealInfo(
                ticket=99,
                order=88,
                position_id=7,
                symbol="EURUSD",
                magic=0,
                entry=0,
                volume=0.1,
                price=1.101,
                time=1100,
                comment="manual",
            ),
            1100,
        )
        self.assertFalse(admitted)
        self.assertEqual(engine.current.state, ExecState.UNKNOWN)
        self.assertEqual(engine.current.filled_volume, 0.1)
        self.assertTrue(engine.requires_manual_review())

    def test_live_position_volume_mismatch_is_ambiguous_after_grace(self):
        engine, gateway = self._wedged_engine()
        key = engine.current.correlation_key
        magic = AppConfig().execution.magic
        gateway.positions_list = [
            PositionInfo(
                ticket=7, position_id=7, symbol="EURUSD", magic=magic,
                direction=Direction.LONG, volume=0.2, comment=key,
            )
        ]
        gateway.history_deals_list = [
            DealInfo(
                ticket=1, order=11, position_id=7, symbol="EURUSD", magic=magic,
                entry=0, volume=0.1, price=1.1, time=1001, comment=key,
            )
        ]
        engine.reconcile(gateway, 1000 + 10_000)
        self.assertEqual(engine.current.state, ExecState.UNKNOWN)
        self.assertTrue(engine.requires_manual_review())

    def test_exact_sources_disagreeing_on_position_id_are_ambiguous(self):
        engine, gateway = self._wedged_engine()
        key = engine.current.correlation_key
        magic = AppConfig().execution.magic
        gateway.positions_list = [
            PositionInfo(
                ticket=8, position_id=8, symbol="EURUSD", magic=magic,
                direction=Direction.LONG, volume=0.1, comment=key,
            )
        ]
        gateway.history_deals_list = [
            DealInfo(
                ticket=22, order=11, position_id=7, symbol="EURUSD", magic=magic,
                entry=0, volume=0.1, price=1.1, time=1001, comment=key,
            )
        ]
        engine.reconcile(gateway, 1001)
        self.assertEqual(engine.current.state, ExecState.UNKNOWN)
        self.assertTrue(engine.requires_manual_review())

    def test_polling_does_not_renew_the_reconciliation_grace_period(self):
        engine, gateway = self._wedged_engine()
        grace = AppConfig().execution.reconcile_grace_seconds
        engine.reconcile(gateway, 1001)
        self.assertEqual(engine.current.state, ExecState.RECONCILING)
        # _persist changed updated_at above; the fixed deadline is created_at.
        engine.reconcile(gateway, 1000 + grace + 1)
        self.assertEqual(engine.current.state, ExecState.UNKNOWN)
        self.assertTrue(engine.requires_manual_review())


# ---------------------------------------------------------------------------
class TestDealIdempotency(unittest.TestCase):
    """A replayed transaction must not double-count a fill."""

    def test_the_ledger_admits_a_ticket_once(self):
        ledger = DealLedger()
        self.assertTrue(ledger.admit(1))
        self.assertFalse(ledger.admit(1))
        self.assertFalse(ledger.admit(0))

    def test_a_replayed_deal_does_not_inflate_filled_volume(self):
        engine = ExecutionEngine(AppConfig(), Journal(), DealLedger())
        gateway = StubGateway()
        engine.submit(
            valid_plan(), RunMode.DEMO_CONFIRM, gateway=gateway,
            account=demo_account(), spec=default_spec("EURUSD"), now=1000,
        )
        deal = DealInfo(ticket=99, order=11, position_id=7, symbol="EURUSD",
                        magic=AppConfig().execution.magic, entry=0, volume=0.05,
                        price=1.10, time=1100)

        self.assertTrue(engine.apply_deal(deal, 1100))
        self.assertAlmostEqual(engine.current.filled_volume, 0.05)

        # The same event delivered twice, as MetaQuotes documents can happen.
        self.assertFalse(engine.apply_deal(deal, 1101))
        self.assertAlmostEqual(
            engine.current.filled_volume, 0.05,
            "a replayed deal must not be counted again",
        )

    def test_partial_then_completing_fill_reaches_filled(self):
        engine = ExecutionEngine(AppConfig(), Journal(), DealLedger())
        gateway = StubGateway()
        engine.submit(
            valid_plan(), RunMode.DEMO_CONFIRM, gateway=gateway,
            account=demo_account(), spec=default_spec("EURUSD"), now=1000,
        )
        magic = AppConfig().execution.magic
        engine.apply_deal(DealInfo(ticket=1, symbol="EURUSD", magic=magic, entry=0,
                                   volume=0.05, time=1100,
                                   comment=engine.current.correlation_key), 1100)
        self.assertEqual(engine.current.state, ExecState.PARTIALLY_FILLED)
        engine.apply_deal(DealInfo(ticket=2, symbol="EURUSD", magic=magic, entry=0,
                                   volume=0.05, time=1101,
                                   comment=engine.current.correlation_key), 1101)
        self.assertEqual(engine.current.state, ExecState.FILLED)


# ---------------------------------------------------------------------------
class TestUnboundedRisk(unittest.TestCase):
    """A position with no computable worst case is not a zero-risk position."""

    def test_a_stopless_position_is_reported_unbounded(self):
        risk, bounded = position_risk(
            PositionInfo(symbol="EURUSD", volume=1.0, price_open=1.1, stop_loss=0.0),
            default_spec("EURUSD"),
        )
        self.assertFalse(bounded)
        self.assertEqual(risk, 0.0)

    def test_an_unpriceable_symbol_is_reported_unbounded(self):
        spec = SymbolSpec(symbol="X", tick_size=0.0, tick_value=0.0)
        _, bounded = position_risk(
            PositionInfo(symbol="X", volume=1.0, price_open=1.1, stop_loss=1.0), spec
        )
        self.assertFalse(bounded)

    def test_new_risk_is_refused_before_any_cap_is_consulted(self):
        """The dangerous failure: an invisible position makes caps look roomy."""
        portfolio = PortfolioRisk()
        exposure = portfolio.summarise(
            "EURUSD",
            [PositionInfo(symbol="EURUSD", volume=1.0, price_open=1.1, stop_loss=0.0)],
            {"EURUSD": default_spec("EURUSD")},
            10_000.0,
        )
        self.assertEqual(exposure.unbounded_positions, 1)
        allowed, reason = portfolio.allows(exposure, 0.01, 99.0, 99.0, 99.0)
        self.assertFalse(allowed, "caps are meaningless while exposure is a lower bound")
        self.assertIn("UNBOUNDED_RISK", reason)

    def test_bounded_positions_are_measured_normally(self):
        portfolio = PortfolioRisk()
        exposure = portfolio.summarise(
            "EURUSD",
            [PositionInfo(symbol="EURUSD", volume=0.1, price_open=1.1, stop_loss=1.09)],
            {"EURUSD": default_spec("EURUSD")},
            10_000.0,
        )
        self.assertEqual(exposure.unbounded_positions, 0)
        self.assertGreater(exposure.open_risk_pct, 0.0)
        self.assertTrue(portfolio.allows(exposure, 0.25, 5.0, 5.0, 5.0)[0])

    def test_correlated_symbols_aggregate_on_the_shared_leg(self):
        portfolio = PortfolioRisk()
        exposure = portfolio.summarise(
            "GBPUSD",
            [
                PositionInfo(symbol="EURUSD", volume=0.1, price_open=1.1, stop_loss=1.09),
                PositionInfo(symbol="AUDUSD", volume=0.1, price_open=0.65, stop_loss=0.64),
            ],
            {s: default_spec(s) for s in ("EURUSD", "AUDUSD")},
            10_000.0,
        )
        # Both existing positions share USD with the candidate, so the USD leg
        # carries both — the concentration v1.1.0 could not see.
        self.assertEqual(exposure.dominant_currency, "USD")
        self.assertGreater(exposure.currency_risk_pct, 0.0)


# ---------------------------------------------------------------------------
class TestPositionSizing(unittest.TestCase):
    def test_a_budget_below_the_minimum_lot_is_refused_not_rounded_up(self):
        """The commonest way a careful risk model gets quietly defeated."""
        volume, code = normalize_volume(0.003, default_spec("EURUSD"))
        self.assertEqual(volume, 0.0)
        self.assertIn("RISK_BELOW_BROKER_MIN_VOLUME", code)

    def test_volume_rounds_down_never_to_nearest(self):
        volume, code = normalize_volume(0.199, default_spec("EURUSD"))
        self.assertEqual(code, "")
        self.assertAlmostEqual(volume, 0.19)

    def test_an_invalid_volume_spec_is_refused(self):
        _, code = normalize_volume(1.0, SymbolSpec(symbol="X"))
        self.assertEqual(code, "INVALID_VOLUME_SPEC")

    def test_planning_refuses_when_the_broker_cannot_price_the_stop(self):
        """No fallback formula. An approximation is not risk control."""
        gateway = StubGateway()
        gateway.calc_profit = lambda *a, **k: None
        signal = SignalCandidate(
            symbol="EURUSD", direction=Direction.LONG, setup=SetupType.TREND_PULLBACK,
            preferred_entry=1.10, stop_loss=1.098, take_profit=1.104,
        )
        plan = RiskPlanner(AppConfig()).build(
            signal, gateway=gateway, account=demo_account(), spec=default_spec("EURUSD"),
            own_positions=[], specs={}, now=1000,
        )
        self.assertFalse(plan.valid)
        self.assertIn("CALC_PROFIT_UNAVAILABLE", plan.validation_codes)

    def test_planning_refuses_a_risk_percent_above_policy(self):
        gateway = StubGateway()
        signal = SignalCandidate(
            symbol="EURUSD", direction=Direction.LONG, setup=SetupType.TREND_PULLBACK,
            preferred_entry=1.10, stop_loss=1.098, take_profit=1.104,
        )
        plan = RiskPlanner(AppConfig()).build(
            signal, gateway=gateway, account=demo_account(), spec=default_spec("EURUSD"),
            own_positions=[], specs={}, now=1000, risk_percent=5.0,
        )
        self.assertFalse(plan.valid)
        self.assertIn("RISK_PERCENT_OUT_OF_POLICY(5.00)", plan.validation_codes)

    def test_planning_refuses_a_blocked_signal(self):
        signal = SignalCandidate(symbol="EURUSD", direction=Direction.LONG, hard_blocked=True)
        plan = RiskPlanner(AppConfig()).build(
            signal, gateway=StubGateway(), account=demo_account(),
            spec=default_spec("EURUSD"), own_positions=[], specs={}, now=1000,
        )
        self.assertFalse(plan.valid)
        self.assertIn("NO_ACTIONABLE_SIGNAL", plan.validation_codes)

    def test_a_valid_plan_stays_inside_its_risk_budget(self):
        signal = SignalCandidate(
            symbol="EURUSD", direction=Direction.LONG, setup=SetupType.TREND_PULLBACK,
            preferred_entry=1.10, stop_loss=1.098, take_profit=1.104,
        )
        plan = RiskPlanner(AppConfig()).build(
            signal, gateway=StubGateway(), account=demo_account(),
            spec=default_spec("EURUSD"), own_positions=[], specs={}, now=1000,
        )
        self.assertTrue(plan.valid, plan.validation_codes)
        self.assertLessEqual(plan.actual_risk_amount, plan.risk_amount * 1.01)


# ---------------------------------------------------------------------------
class TestArming(unittest.TestCase):
    """No single action may send an order."""

    def test_confirm_without_arm_is_refused(self):
        ok, reason = IntentArming(AppConfig().execution, Journal()).confirm(valid_plan(), 1000)
        self.assertFalse(ok)
        self.assertEqual(reason, "NO_ARMED_INTENT")

    def test_arm_then_confirm_succeeds_once(self):
        arming = IntentArming(AppConfig().execution, Journal())
        plan = valid_plan()
        self.assertTrue(arming.arm(plan, 1000))
        self.assertEqual(arming.confirm(plan, 1005), (True, ""))
        # The intent is consumed; a second confirm cannot reuse it.
        self.assertFalse(arming.confirm(plan, 1006)[0])

    def test_an_expired_intent_is_refused(self):
        arming = IntentArming(AppConfig().execution, Journal())
        plan = valid_plan()
        arming.arm(plan, 1000)
        ok, reason = arming.confirm(plan, 1000 + AppConfig().execution.arm_ttl_seconds + 1)
        self.assertFalse(ok)
        self.assertEqual(reason, "ARMED_INTENT_EXPIRED")

    def test_a_superseded_plan_is_refused(self):
        arming = IntentArming(AppConfig().execution, Journal())
        arming.arm(valid_plan(), 1000)
        other = valid_plan()
        other.plan_id = "P2"
        ok, reason = arming.confirm(other, 1005)
        self.assertFalse(ok)
        self.assertEqual(reason, "ARMED_PLAN_SUPERSEDED")

    def test_a_silently_replanned_plan_is_refused(self):
        """Same id, different numbers — the same slot, not the same plan."""
        arming = IntentArming(AppConfig().execution, Journal())
        arming.arm(valid_plan(), 1000)
        moved = valid_plan()
        moved.entry = 1.10500
        ok, reason = arming.confirm(moved, 1005)
        self.assertFalse(ok)
        self.assertEqual(reason, "ARMED_PLAN_CHANGED")

    def test_sweep_clears_an_expired_intent(self):
        arming = IntentArming(AppConfig().execution, Journal())
        arming.arm(valid_plan(), 1000)
        self.assertTrue(arming.is_armed(1005))
        self.assertTrue(arming.sweep(1000 + 999))
        self.assertFalse(arming.is_armed(1000 + 999))


# ---------------------------------------------------------------------------
class TestCalendarGate(unittest.TestCase):
    """An unseen calendar must never read as a clear one."""

    def test_no_source_yields_unknown_not_clear(self):
        runtime = detect_runtime(connected=True, replay=False)
        verdict = CalendarGate(None, journal=Journal()).evaluate("EURUSD", runtime, 1000)
        self.assertEqual(verdict.state, NewsState.UNKNOWN)
        self.assertEqual(verdict.source, NewsSource.UNAVAILABLE)

    def test_unknown_blocks_in_production(self):
        gate = CalendarGate(None, journal=Journal())
        gate.apply_runtime_policy(detect_runtime(connected=True, replay=False), 0)
        self.assertFalse(gate.is_news_blind)
        self.assertTrue(gate.blocks_trading(gate.evaluate("EURUSD", detect_runtime(connected=True, replay=False), 1000)))

    def test_unknown_does_not_block_a_replay_but_is_flagged(self):
        """Otherwise no backtest ever trades and the filter is unfalsifiable."""
        journal = Journal()
        gate = CalendarGate(None, journal=journal)
        runtime = detect_runtime(connected=False, replay=True)
        gate.apply_runtime_policy(runtime, 0)
        self.assertTrue(gate.is_news_blind)
        self.assertFalse(gate.blocks_trading(gate.evaluate("EURUSD", runtime, 1000)))
        self.assertTrue(any(e.code == "NEWS_BLIND_RUN" for e in journal.entries()))

    def test_a_loaded_calendar_with_no_events_is_clear_not_unknown(self):
        gate = CalendarGate(StaticCalendar([], loaded=True), journal=Journal())
        verdict = gate.evaluate("EURUSD", detect_runtime(connected=True, replay=False), 1000)
        self.assertEqual(verdict.state, NewsState.CLEAR)
        self.assertEqual(verdict.source, NewsSource.LIVE)
        self.assertFalse(gate.blocks_trading(verdict))

    def test_a_high_impact_event_blocks_on_either_leg(self):
        calendar = StaticCalendar(
            [CalendarEvent(time=1000, currency="USD", name="NFP", importance="HIGH")]
        )
        gate = CalendarGate(calendar, journal=Journal())
        verdict = gate.evaluate("EURUSD", detect_runtime(connected=True, replay=False), 1000)
        self.assertEqual(verdict.state, NewsState.BLOCKED)
        self.assertTrue(gate.blocks_trading(verdict))

    def test_medium_impact_is_ignored_by_default(self):
        calendar = StaticCalendar(
            [CalendarEvent(time=1000, currency="USD", name="PMI", importance="MEDIUM")]
        )
        gate = CalendarGate(calendar, journal=Journal())
        verdict = gate.evaluate("EURUSD", detect_runtime(connected=True, replay=False), 1000)
        self.assertEqual(verdict.state, NewsState.CLEAR)

    def test_an_event_outside_the_window_does_not_block(self):
        calendar = StaticCalendar(
            [CalendarEvent(time=999_999, currency="USD", name="NFP", importance="HIGH")]
        )
        gate = CalendarGate(calendar, journal=Journal())
        self.assertEqual(
            gate.evaluate("EURUSD", detect_runtime(connected=True, replay=False), 1000).state,
            NewsState.CLEAR,
        )

    def test_a_raising_source_yields_unknown(self):
        class Broken:
            def available(self): return True
            def events(self, *a): raise RuntimeError("network")

        gate = CalendarGate(Broken(), journal=Journal())
        verdict = gate.evaluate("EURUSD", detect_runtime(connected=True, replay=False), 1000)
        self.assertEqual(verdict.state, NewsState.UNKNOWN)

    def test_operator_csv_is_a_wired_live_source(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "calendar.csv"
            path.write_text(
                "time,currency,name,importance,coverage_until\n"
                "1000,USD,NFP,HIGH,2000\n",
                encoding="utf-8",
            )
            gate = CalendarGate(CsvCalendar(path), journal=Journal())
            gate.apply_runtime_policy(detect_runtime(connected=True, replay=False), 0)
            verdict = gate.evaluate(
                "EURUSD", detect_runtime(connected=True, replay=False), 1000
            )
            self.assertEqual(verdict.state, NewsState.BLOCKED)

    def test_malformed_operator_csv_fails_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "calendar.csv"
            path.write_text("when,currency\n1000,USD\n", encoding="utf-8")
            gate = CalendarGate(CsvCalendar(path), journal=Journal())
            gate.apply_runtime_policy(detect_runtime(connected=True, replay=False), 0)
            verdict = gate.evaluate(
                "EURUSD", detect_runtime(connected=True, replay=False), 1000
            )
            self.assertEqual(verdict.state, NewsState.UNKNOWN)
            self.assertTrue(gate.blocks_trading(verdict))

    def test_stale_calendar_coverage_fails_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "calendar.csv"
            path.write_text(
                "time,currency,name,importance,coverage_until\n"
                "1000,USD,NFP,HIGH,1100\n",
                encoding="utf-8",
            )
            gate = CalendarGate(CsvCalendar(path), journal=Journal())
            gate.apply_runtime_policy(detect_runtime(connected=True, replay=False), 0)
            verdict = gate.evaluate(
                "EURUSD", detect_runtime(connected=True, replay=False), 2000
            )
            self.assertEqual(verdict.state, NewsState.UNKNOWN)
            self.assertTrue(gate.blocks_trading(verdict))


# ---------------------------------------------------------------------------
class TestRuntimeAndPersistence(unittest.TestCase):
    """Evidence from different contexts must never share a file."""

    def test_only_a_live_session_is_production(self):
        self.assertTrue(detect_runtime(connected=True, replay=False).is_production)
        self.assertFalse(detect_runtime(connected=False, replay=False).is_production)
        self.assertFalse(detect_runtime(connected=True, replay=True).is_production)

    def test_a_replay_is_never_production_even_when_connected(self):
        runtime = detect_runtime(connected=True, replay=True)
        self.assertEqual(runtime.kind, RuntimeKind.REPLAY)
        self.assertFalse(runtime.is_production)

    def test_persistence_is_required_for_live_and_disabled_offline(self):
        from pathlib import Path

        live = persistence_plan(detect_runtime(connected=True, replay=False), Path("/tmp/x"))
        self.assertTrue(live.enabled)
        self.assertTrue(live.required)

        replay = persistence_plan(detect_runtime(connected=False, replay=True), Path("/tmp/x"))
        self.assertTrue(replay.enabled)
        self.assertFalse(replay.required)
        self.assertIn("replay_", replay.filename)

        offline = persistence_plan(detect_runtime(connected=False, replay=False), Path("/tmp/x"))
        self.assertFalse(offline.enabled)

    def test_live_and_replay_never_share_a_filename(self):
        from pathlib import Path

        live = persistence_plan(detect_runtime(connected=True, replay=False), Path("/tmp/x"))
        replay = persistence_plan(detect_runtime(connected=False, replay=True), Path("/tmp/x"))
        self.assertNotEqual(live.filename, replay.filename)


# ---------------------------------------------------------------------------
class TestAccountGuards(unittest.TestCase):
    def test_the_peak_equity_high_water_mark_survives_a_restart(self):
        """v1.1.0 reset it on start, disarming the drawdown guard mid-drawdown."""
        stored = RiskState(day_key=0, day_start_equity=10_000.0, peak_equity=12_000.0)
        guard = AccountRiskGuard()
        guard.initialize(9_000.0, 1_700_000_000, stored)
        self.assertEqual(guard.state.peak_equity, 12_000.0)

    def test_equity_growth_raises_the_high_water_mark(self):
        guard = AccountRiskGuard()
        guard.initialize(10_000.0, 1_700_000_000, RiskState(peak_equity=9_000.0))
        self.assertEqual(guard.state.peak_equity, 10_000.0)

    def test_guards_are_disabled_by_default(self):
        guard = AccountRiskGuard()
        guard.initialize(10_000.0, 1_700_000_000, None)
        self.assertEqual(guard.check(1.0, 1_700_000_000), (True, []))

    def test_the_drawdown_guard_halts_when_enabled(self):
        from dataclasses import replace

        config = replace(AppConfig().risk, guards_enabled=True)
        guard = AccountRiskGuard(config)
        guard.initialize(10_000.0, 1_700_000_000, None)
        may_trade, codes = guard.check(8_000.0, 1_700_000_000)
        self.assertFalse(may_trade)
        self.assertTrue(any("DRAWDOWN_HALT" in c for c in codes))

    def test_consecutive_losses_survive_the_day_boundary(self):
        guard = AccountRiskGuard()
        guard.initialize(10_000.0, 1_700_000_000, None)
        guard.register_closed_profit(-10.0, 1_700_000_000)
        guard.register_closed_profit(-10.0, 1_700_000_000)
        guard.roll_day(10_000.0, 1_700_000_000 + 86_400 * 2)
        self.assertEqual(guard.state.consecutive_losses, 2)

    def test_a_win_resets_the_streak(self):
        guard = AccountRiskGuard()
        guard.initialize(10_000.0, 1_700_000_000, None)
        guard.register_closed_profit(-10.0, 1)
        guard.register_closed_profit(5.0, 2)
        self.assertEqual(guard.state.consecutive_losses, 0)


# ---------------------------------------------------------------------------
class TestTradeGuards(unittest.TestCase):
    def test_stops_must_clear_both_stops_and_freeze_levels(self):
        """v1.1.0 read the freeze level and then never checked it."""
        spec = default_spec("EURUSD")
        spec.stops_level = 0
        spec.freeze_level = 100  # 100 points = 0.00100
        plan = valid_plan()  # stop is 0.00200 away — clears it
        self.assertEqual(TradeGuards().stops_valid(plan, spec), [])

        spec.freeze_level = 500  # 0.00500 — the stop is now inside the band
        codes = TradeGuards().stops_valid(plan, spec)
        self.assertTrue(any("SL_INSIDE_BROKER_LEVEL" in c for c in codes))

    def test_permissions_refuse_a_disabled_symbol(self):
        spec = default_spec("EURUSD")
        spec.trade_mode = 0  # SYMBOL_TRADE_MODE_DISABLED
        self.assertIn("SYMBOL_TRADE_DISABLED", TradeGuards().trade_permissions(demo_account(), spec))

    def test_permissions_refuse_when_the_account_forbids_trading(self):
        from dataclasses import replace

        account = replace(demo_account(), trade_allowed=False)
        self.assertIn(
            "ACCOUNT_TRADE_DISABLED",
            TradeGuards().trade_permissions(account, default_spec("EURUSD")),
        )

    def test_own_exposure_is_detected(self):
        positions = [PositionInfo(symbol="EURUSD", magic=1)]
        self.assertTrue(TradeGuards().has_exposure("EURUSD", positions, []))
        self.assertFalse(TradeGuards().has_exposure("GBPUSD", positions, []))

    def test_foreign_exposure_is_reported_separately(self):
        positions = [PositionInfo(symbol="EURUSD", magic=999)]
        self.assertTrue(TradeGuards().has_foreign_exposure("EURUSD", positions, 1))
        self.assertFalse(TradeGuards().has_foreign_exposure("EURUSD", positions, 999))


# ---------------------------------------------------------------------------
class TestPreflight(unittest.TestCase):
    def test_a_stale_tick_refuses_the_send(self):
        """A tick nobody has updated is not a quote, it is a memory.

        The plan here is deliberately fresh — created at 1050, still inside its
        30s preview window at 1060 — so the only thing wrong is the tick's age.
        Otherwise PREVIEW_EXPIRED fires first and the test proves nothing about
        staleness.
        """
        from alikhande.core.preflight import Preflight

        gateway = StubGateway(tick_time=1000)
        result = Preflight(AppConfig()).validate(
            valid_plan(now=1050), gateway=gateway, account=demo_account(),
            spec=default_spec("EURUSD"), now=1060,
        )
        self.assertFalse(result.ok)
        self.assertIn("STALE_TICK", result.reason)

    def test_an_expired_preview_refuses_the_send(self):
        from alikhande.core.preflight import Preflight

        result = Preflight(AppConfig()).validate(
            valid_plan(now=1000), gateway=StubGateway(), account=demo_account(),
            spec=default_spec("EURUSD"), now=1000 + 999,
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.reason, "PREVIEW_EXPIRED")

    def test_excess_drift_refuses_the_send(self):
        from alikhande.core.preflight import Preflight

        plan = valid_plan()
        plan.entry = 1.05000  # market has moved far from where the plan was sized
        result = Preflight(AppConfig()).validate(
            plan, gateway=StubGateway(), account=demo_account(),
            spec=default_spec("EURUSD"), now=1000,
        )
        self.assertFalse(result.ok)
        self.assertIn("PRICE_DRIFT_EXCEEDED", result.reason)

    def test_a_rejected_order_check_refuses_the_send(self):
        from alikhande.core.preflight import Preflight

        gateway = StubGateway()
        gateway.check_ok = False
        result = Preflight(AppConfig()).validate(
            valid_plan(), gateway=gateway, account=demo_account(),
            spec=default_spec("EURUSD"), now=1000,
        )
        self.assertFalse(result.ok)
        self.assertIn("ORDER_CHECK_FAILED", result.reason)

    def test_an_order_check_transport_error_fails_closed(self):
        from alikhande.core.preflight import Preflight

        gateway = StubGateway()
        gateway.check_order = lambda _request: (_ for _ in ()).throw(
            RuntimeError("IPC failed")
        )
        result = Preflight(AppConfig()).validate(
            valid_plan(), gateway=gateway, account=demo_account(),
            spec=default_spec("EURUSD"), now=1000,
        )
        self.assertFalse(result.ok)
        self.assertIn("ORDER_CHECK_UNAVAILABLE", result.reason)

    def test_exposure_that_appeared_after_preview_refuses_the_send(self):
        from alikhande.core.preflight import Preflight

        gateway = StubGateway()
        gateway.positions_list = [PositionInfo(symbol="EURUSD")]
        result = Preflight(AppConfig()).validate(
            valid_plan(), gateway=gateway, account=demo_account(),
            spec=default_spec("EURUSD"), now=1000,
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.reason, "ALREADY_EXPOSED")

    def test_unreadable_exposure_is_not_treated_as_empty(self):
        from alikhande.core.preflight import Preflight

        gateway = StubGateway()
        gateway.positions = lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("IPC failed")
        )
        result = Preflight(AppConfig()).validate(
            valid_plan(), gateway=gateway, account=demo_account(),
            spec=default_spec("EURUSD"), now=1000,
        )
        self.assertFalse(result.ok)
        self.assertIn("BROKER_EXPOSURE_UNAVAILABLE", result.reason)

    def test_spec_change_after_preview_requires_replanning(self):
        from alikhande.core.preflight import Preflight

        expected = default_spec("EURUSD")
        changed = default_spec("EURUSD")
        changed.fingerprint = "CHANGED"
        gateway = StubGateway()
        gateway.symbol_spec = lambda _symbol: changed
        result = Preflight(AppConfig()).validate(
            valid_plan(), gateway=gateway, account=demo_account(),
            spec=expected, now=1000,
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.reason, "BROKER_SPEC_CHANGED_REPLAN")

    def test_a_clean_plan_produces_a_sendable_request(self):
        from alikhande.core.preflight import Preflight

        result = Preflight(AppConfig()).validate(
            valid_plan(), gateway=StubGateway(), account=demo_account(),
            spec=default_spec("EURUSD"), now=1000,
        )
        self.assertTrue(result.ok, result.reason)
        self.assertIsNotNone(result.request)
        self.assertEqual(result.request.magic, AppConfig().execution.magic)
        self.assertAlmostEqual(result.actual_risk_amount, 20.0)

    def test_last_moment_cash_risk_above_the_plan_is_refused(self):
        from alikhande.core.preflight import Preflight

        gateway = StubGateway()
        gateway.calc_profit = lambda *_args, **_kwargs: -30.0
        result = Preflight(AppConfig()).validate(
            valid_plan(), gateway=gateway, account=demo_account(),
            spec=default_spec("EURUSD"), now=1000,
        )
        self.assertFalse(result.ok)
        self.assertIn("ACTUAL_RISK_EXCEEDS_PLAN", result.reason)


if __name__ == "__main__":
    unittest.main()
