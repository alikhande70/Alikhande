"""Translation, layout direction and locale-aware number formatting.

Deliberately small and dependency-free. Qt ships a full translation system
(``.ts`` files, ``lupdate``, ``QTranslator``), and it was the wrong tool here:
it needs a build step, it lives outside the Python source, and this application
has exactly two languages and a few hundred strings. A dict that ships with the
code is inspectable, diffable, and testable — and the test suite asserts the
Persian catalogue covers every English key, which a ``.ts`` workflow makes
harder rather than easier.

## Three decisions worth stating

**Keys are symbolic, not English source text.** ``t("dash.verdict.nothing")``
rather than ``t("Nothing actionable")``. English is a catalogue like any other,
so fixing an English typo does not silently orphan the Persian string.

**Prices always use Latin digits, everything else follows the locale.**
Persian traders read prices in Latin digits — every terminal, broker statement
and chart shows them that way — and Persian digits are not monospaced in the
fonts this ships with, so a column of them would not align. Counts, durations
and percentages do take Persian digits. ``fmt_price`` and ``fmt_count`` are
separate functions precisely so the distinction cannot be lost by accident.

**The price chart never mirrors.** Right-to-left flips reading order, not time.
Financial charts run older-to-newer left-to-right in every locale, and mirroring
one would make an uptrend look like a downtrend to anybody who has seen a chart
before. Text and layout mirror; the time axis does not.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

# --------------------------------------------------------------------- languages


@dataclass(frozen=True)
class Language:
    code: str
    name: str  # in the language itself, as language pickers should always do
    rtl: bool
    digits: str | None  # None means Latin digits


ENGLISH = Language("en", "English", rtl=False, digits=None)
PERSIAN = Language("fa", "فارسی", rtl=True, digits="۰۱۲۳۴۵۶۷۸۹")

LANGUAGES: dict[str, Language] = {ENGLISH.code: ENGLISH, PERSIAN.code: PERSIAN}

_current: Language = ENGLISH


def current() -> Language:
    return _current


def set_language(code: str) -> Language:
    global _current
    _current = LANGUAGES.get(code, ENGLISH)
    return _current


def is_rtl() -> bool:
    return _current.rtl


# ----------------------------------------------------------------- catalogues

EN: dict[str, str] = {
    # ---- shell
    "app.title": "Alikhande Scanner",
    "app.brand": "ALIKHANDE",
    "app.brandsub": "SCANNER",
    "nav.dashboard": "Dashboard",
    "nav.signal": "Signal",
    "nav.risk": "Risk",
    "nav.execution": "Execution",
    "nav.health": "Health",
    "nav.guide": "Guide",
    "nav.dashboard.tip": "What is happening right now",
    "nav.signal.tip": "One symbol, with the structure it is built on",
    "nav.risk.tip": "Exposure against its limits, and the evidence base",
    "nav.execution.tip": "The in-flight order and its reconciliation",
    "nav.health.tip": "What this build has and has not proven",
    "nav.guide.tip": "How to use this application safely",
    "shell.mode": "MODE",
    "shell.language": "LANGUAGE",
    "mode.alert": "Alert only",
    "mode.shadow": "Shadow",
    "mode.demo": "Demo · arm + confirm",
    # ---- environments (2.2) --------------------------------------------
    # ---- operations (2.2) -----------------------------------------------
    "nav.ops": "Operations",
    "nav.ops.tip": "The link, the data, the record and the recovery tools",
    "ops.link": "BROKER LINK",
    "ops.link.unknown": "NOT PROBED",
    "ops.link.latency": "Latency",
    "ops.link.peak": "Peak latency",
    "ops.link.availability": "Availability",
    "ops.link.failures": "Failed probes",
    "ops.link.probes": "Total probes",
    "ops.data": "DATA QUALITY",
    "ops.data.clean.title": "No chronic problems",
    "ops.data.clean.body": "A symbol appears here once it has been unusable in most of at least thirty passes.",
    "ops.data.chronic": "unusable in {fraction} of {passes} passes",
    "ops.data.note": "One bad pass is a symbol still downloading. The same symbol failing for two days is one the broker does not serve, and only the accumulated record can tell them apart.",
    "ops.sessions": "SESSION HISTORY",
    "ops.exit.clean": "closed cleanly",
    "ops.exit.crash": "ended without closing",
    "ops.exit.running": "running",
    "ops.exit.unknown": "unknown",
    "ops.recovery": "BACKUP AND RECOVERY",
    "ops.recovery.idle": "No maintenance has run in this session yet.",
    "ops.backup.now": "Back up now",
    "ops.backup.ok": "Backup written and verified: {path}",
    "ops.backup.failed": "Backup FAILED and was not written: {error}",
    "ops.diagnostics": "Diagnostics bundle",
    "ops.diagnostics.ok": "Diagnostics written to {path}",
    "ops.settings.export": "Export settings",
    "ops.settings.ok": "Settings written to {path}",
    "ops.backups": "BACKUPS",
    "ops.backups.empty.title": "No backups yet",
    "ops.backups.empty.body": "Take one now, or let the robot take them on a schedule.",
    "ops.backups.size": "{kb} KB",
    "ops.restore": "Restore",
    "ops.restore.placeholder": "path to a backup file",
    "ops.restore.confirm.title": "Restore this backup?",
    "ops.restore.confirm.body": "The current database will be moved aside to a timestamped file, not deleted, and {path} will take its place.",
    "ops.restore.ok": "Restored. The previous database was kept at {path}",
    "ops.restore.failed": "Restore refused: {error}",
    "ops.journal": "JOURNAL",
    "ops.journal.search": "filter by code, context or message",
    "ops.journal.count": "{shown} of {total}",
    # ---- robot (2.2) ----------------------------------------------------
    "nav.robot": "Robot",
    "nav.robot.tip": "The automation, and the line it does not cross",
    "robot.status": "STATUS",
    "robot.actions": "LAST PASS",
    "robot.actions.empty.title": "Nothing to do yet",
    "robot.actions.empty.body": "Actions the robot takes appear here as it takes them.",
    "robot.start": "Start robot",
    "robot.stop": "Stop robot",
    "robot.resume": "Resume now",
    "robot.state.stopped": "STOPPED",
    "robot.state.idle": "IDLE",
    "robot.state.watching": "WATCHING",
    "robot.state.holding": "HOLDING",
    "robot.state.paused": "PAUSED",
    "robot.watching": "In a session window and scanning. Candidates appear on the Scanner.",
    "robot.idle": "Outside every session window. Maintenance still runs.",
    "robot.holding": "Not presenting candidates: {reason}.",
    "robot.field.window": "Session window",
    "robot.field.next": "Next window",
    "robot.field.candidates": "Candidates",
    "robot.field.backup": "Backup",
    "robot.next_in": "{window}, in {minutes} min",
    "robot.backup.never": "not taken this session",
    "robot.backup.taken": "taken this session",
    "robot.permissions": "WHAT IT MAY DO",
    "robot.perm.reconnect": "Reconnect a dropped or stalled link",
    "robot.perm.disarm": "Disarm a stale intent, and cancel on invalidation",
    "robot.perm.pause_guard": "Pause itself when a risk guard trips",
    "robot.perm.pause_degraded": "Pause itself when data or the link go unusable",
    "robot.perm.backup": "Take a verified backup on a schedule",
    "robot.perm.backup_every": "Back up every",
    "robot.hours": "h",
    "robot.windows": "SESSION WINDOWS",
    "robot.window.london": "London",
    "robot.window.newyork": "New York",
    "robot.window.asia": "Asia",
    "robot.window.test": "Test",
    "robot.window.off": "off",
    "robot.windows.note": "Broker server time, not local time. A session window is a statement about the market, and the market does not know what timezone this machine is set to.",
    "robot.lock.title": "UNATTENDED EXECUTION",
    "robot.lock.body": "The robot never arms and never confirms. Execution requires two deliberate human actions on separate controls, and an autopilot performing either one would not weaken that gate — it would remove it, because a single click would then be enough to send an order.",
    "robot.lock.reason.1": "RunMode has no member that selects live trading.",
    "robot.lock.reason.2": "core.execution refuses any non-demo account with a hard return.",
    "robot.lock.reason.3": "The MT5 adapter refuses again, sharing no code with that check.",
    "robot.lock.reason.4": "The declared environment refuses on what the operator declared rather than on what the terminal reported.",
    "code.AUTO_EXECUTE_NOT_AUTHORISED": "unattended execution is not authorised",
    "code.OUTSIDE_WINDOW": "outside every session window",
    "code.LINK_UNUSABLE": "the broker link is not usable",
    "code.DATA_UNUSABLE": "the data is not usable",
    "code.NEWS_BLOCKED": "a news window is open",
    "code.RISK_GUARD": "a risk guard has tripped",
    "code.EXECUTION_UNRESOLVED": "an execution is unresolved",
    "code.ENVIRONMENT_LOCKED": "this environment cannot send",
    "code.BACKUP": "took a backup",
    "code.RECONNECT": "reconnecting",
    "code.DISARM": "disarmed a stale intent",
    "code.PAUSE": "paused itself",
    "code.PAUSE_EXPIRED": "pause expired, re-evaluating",
    "code.PRESENT": "presenting candidates",
    "unit.ms": "ms",
    "env.demo": "Demo",
    "env.production": "Production",
    "env.backtest": "Backtest",
    "env.locked": "Locked",
    "env.demo.tip": "A live terminal on a demo account. The only environment in which an order can be sent, and only after Arm and Confirm.",
    "env.production.tip": "A live terminal on a real account. Everything runs — connection, sizing, preflight, reconciliation, reporting. Sending an order is hard-locked.",
    "env.backtest.tip": "Replay over recorded or synthetic bars. No broker, so nothing can be sent.",
    # Runtime kinds and execution states were previously rendered as raw enum
    # names, which left English words like IDLE and OFFLINE sitting untranslated
    # in the Persian interface.
    "code.LIVE": "live",
    "code.REPLAY": "replay",
    "code.OFFLINE": "offline",
    "code.IDLE": "idle",
    "code.SUBMITTING": "submitting",
    "code.ACCEPTED": "accepted",
    "code.PARTIALLY_FILLED": "partially filled",
    "code.FILLED": "filled",
    "code.POSITION_ACTIVE": "position active",
    "code.REJECTED": "rejected",
    "code.CANCELLED": "cancelled",
    "code.UNKNOWN": "unknown",
    "code.RECONCILING": "reconciling",
    "code.COMPLETED": "completed",
    "code.PRODUCTION_SEND_HARD_LOCKED": "production sending is hard-locked",
    "code.MODE_NOT_AVAILABLE_IN_PRODUCTION": "not available in production",
    "code.MODE_NOT_AVAILABLE_IN_BACKTEST": "not available in a backtest",
    "code.BACKTEST_HAS_NO_BROKER": "a backtest has no broker",
    "code.REAL_ACCOUNT_IN_DEMO_ENVIRONMENT": "a real account is attached while Demo is declared",
    "code.DEMO_ACCOUNT_IN_PRODUCTION": "a demo account is attached while Production is declared",
    "code.REAL_ACCOUNT_AS_DECLARED": "real account, as declared",
    "code.DEMO_ACCOUNT_AS_DECLARED": "demo account, as declared",
    "code.ACCOUNT_UNKNOWN": "account not readable",
    "chip.starting": "STARTING",
    "chip.no_account": "NO ACCOUNT",
    "chip.no_broker": "NO BROKER",
    "chip.simulated": "SIMULATED",
    "chip.connected": "CONNECTED",
    "chip.disconnected": "DISCONNECTED",
    "chip.demo": "DEMO",
    "chip.real_blocked": "REAL — BLOCKED",
    "chip.no_broker.tip": (
        "No MetaTrader terminal is attached. Prices are synthetic and nothing "
        "here describes a real market."
    ),
    "banner.real": (
        "REAL ACCOUNT DETECTED ({login} @ {server}). Execution is blocked "
        "unconditionally and the mode selector is locked to Alert-only. This "
        "build never trades a live account."
    ),
    "banner.review": (
        "An execution could not be reconciled against the broker. Submission is "
        "blocked until it is reviewed and acknowledged on the Execution view."
    ),
    "status.pass": "pass {passes}  ·  {ms} ms  ·  {runtime}  ·  open risk {risk}",
    "status.starting": "starting…",
    # ---- dashboard
    "dash.opportunities": "OPPORTUNITIES",
    "dash.watchlist": "Watchlist",
    "dash.tile.actionable": "Actionable",
    "dash.tile.actionable.caption": "qualified with a sized plan",
    "dash.tile.watching": "Watching",
    "dash.tile.watching.caption": "of {total} configured symbols",
    "dash.tile.risk": "Open risk",
    "dash.tile.risk.caption": "cap {cap}",
    "dash.tile.evidence": "Evidence",
    "dash.tile.evidence.none": "no outcomes recorded yet",
    "dash.tile.evidence.below": "{count}/{floor} before any win rate shows",
    "dash.tile.evidence.ok": "outcomes recorded",
    "dash.verdict.ready": "{count} setup(s) ready",
    "dash.verdict.ready.detail": (
        "{names} qualified and sized. Open one to see the structure it is built "
        "on before doing anything with it."
    ),
    "dash.verdict.unresolved": "No symbols resolved",
    "dash.verdict.unresolved.detail": (
        "None of the configured symbols matched a name on this broker. Check "
        "Market Watch in MetaTrader."
    ),
    "dash.verdict.warming": "Warming up",
    "dash.verdict.warming.detail": (
        "{warming} of {total} symbols still gathering the spread and history "
        "they need before anything can be scored. This is normal for the first "
        "minute or two."
    ),
    "dash.verdict.nothing": "Nothing actionable",
    "dash.verdict.nothing.detail": (
        "All {total} symbols scanned; none currently meet the {threshold}-point "
        "threshold with a confirmed setup at a structural zone. That is the "
        "normal state most of the time."
    ),
    "dash.empty.title": "Nothing actionable right now",
    "dash.empty.detail": (
        "A setup appears here only when a confirmed structure, a clear spread "
        "and a sized plan all line up. Refusals are shown per symbol on the "
        "Signal view — the scanner is working when this space is empty."
    ),
    "dash.guards.ok": "GUARDS OK",
    "dash.guards.review": "REVIEW REQUIRED",
    "dash.guards.halted": "HALTED",
    "dash.guards.newsblind": "NEWS-BLIND",
    "col.symbol": "Symbol",
    "col.trend": "Trend",
    "col.bias": "Bias",
    "col.score": "Score",
    "col.structure": "Structure",
    "col.spread": "Spread",
    "col.state": "State",
    "cell.unresolved": "unresolved on this broker",
    "cell.building": "building structure",
    "cell.plan_ready": "plan ready",
    "cell.watching": "watching",
    "card.top_contributors": "Top contributors: {items}",
    "card.no_breakdown": "No score breakdown available.",
    "card.not_sized": "not sized",
    "card.lots": "{lots} lots",
    "card.risk": "risk {amount} ({percent})",
    "card.rr": "R:R 1 : {ratio}",
    # ---- signal
    "signal.chart": "Price and structure",
    "signal.chart.title": "{symbol} · M5 · last 120 bars",
    "signal.chart.legend": "supply / demand zones shaded",
    "signal.chart.waiting": "Waiting for price history",
    "signal.why": "Why this score",
    "signal.plan": "Plan",
    "signal.refusals": "Why this is not tradeable",
    "signal.execute": "Execute",
    "signal.no_setup": "No setup",
    "signal.score_note": (
        "Long {long}  ·  Short {short}  ·  threshold {threshold} with a "
        "{separation}-point lead required.  This is a weighted sum of "
        "conditions, not a probability."
    ),
    "signal.no_components": "No contributions — this symbol has no qualifying side.",
    "plan.entry": "Entry",
    "plan.stop": "Stop loss",
    "plan.target": "Take profit",
    "plan.rr": "Risk : reward",
    "plan.lots": "Lot size",
    "plan.risk": "Risk amount",
    "plan.margin": "Margin",
    "plan.expires": "Expires in",
    "plan.historical": "Historical",
    "btn.arm": "ARM",
    "btn.confirm": "CONFIRM SEND",
    "exec.armed": (
        "ARMED — confirm within {seconds}s or the intent expires and must be "
        "re-armed against a fresh plan."
    ),
    "exec.mode_blocks": "{mode} — no order can leave the application in this mode.",
    "exec.review_blocks": (
        "An execution could not be reconciled against the broker. Submission is "
        "blocked until it is reviewed on the Execution view."
    ),
    "exec.news_blocks": "Blocked by the news gate.",
    "exec.ready": "Plan ready. Arm, then confirm — two separate actions, deliberately.",
    "exec.no_plan": "No valid plan for this symbol.",
    # ---- risk
    "risk.tile.equity": "Equity",
    "risk.tile.equity.caption": "account currency",
    "risk.tile.risk": "Open risk",
    "risk.tile.positions": "Positions",
    "risk.tile.positions.caption": "opened by this app",
    "risk.tile.drawdown": "Drawdown",
    "risk.tile.drawdown.caption": "from peak equity",
    "risk.exposure": "Exposure against limits",
    "risk.meter.open": "Aggregate open risk",
    "risk.meter.currency": "Dominant currency leg",
    "risk.meter.class": "Asset class",
    "risk.bounded": "ALL POSITIONS BOUNDED",
    "risk.unbounded": (
        "{count} POSITION(S) WITHOUT A COMPUTABLE WORST CASE — every figure "
        "above is a LOWER BOUND and new risk is refused ({symbols})"
    ),
    "risk.policy": "Policy",
    "risk.guards": "Guard state",
    "risk.evidence": "Evidence base",
    "risk.positions": "Open positions",
    "risk.no_positions": "No open positions",
    "risk.no_positions.detail": "Nothing has been opened by this application.",
    "risk.no_outcomes": "No outcomes yet",
    "risk.no_outcomes.detail": (
        "A win rate appears only after {floor} resolved trades on the same "
        "symbol, setup and rule version. Until then there is nothing honest to "
        "show."
    ),
    "risk.no_database": "No database",
    "risk.no_database.detail": (
        "This session records nothing, so there is no evidence base to show."
    ),
    "policy.per_trade": "Per-trade risk",
    "policy.ceiling": "Per-trade ceiling",
    "policy.min_rr": "Minimum R:R",
    "policy.aggregate": "Aggregate cap",
    "policy.currency": "Per-currency cap",
    "policy.class": "Asset-class cap",
    "policy.breakers": "Circuit breakers",
    "policy.enabled": "enabled",
    "policy.disabled": "disabled (default)",
    "guard.permitted": "Trading permitted",
    "guard.breached": "Breached guards",
    "guard.peak": "Peak equity",
    "guard.daystart": "Day-start equity",
    "guard.losses": "Consecutive losses",
    "guard.used": "Daily risk used",
    "guard.yes": "yes",
    "guard.no": "NO",
    "guard.none": "none",
    "evidence.trades": "Resolved trades",
    "evidence.wins": "Wins / losses",
    "evidence.winrate": "Win rate",
    "evidence.wilson": "95% Wilson",
    "evidence.total_r": "Total R",
    "evidence.expectancy": "Expectancy",
    "evidence.withheld": "withheld — {count}/{floor}",
    "col.side": "Side",
    "col.volume": "Volume",
    "col.entry": "Entry",
    "col.stop": "Stop",
    "col.target": "Target",
    "col.pl": "P/L",
    "col.bounded": "Bounded",
    "cell.bounded": "bounded",
    "cell.unbounded": "UNBOUNDED — new risk refused",
    # ---- execution
    "exec.review_title": "Manual review required",
    "exec.review_body": (
        "Execution {id} on {symbol} could not be resolved against open "
        "positions, working orders, order history or deal history after "
        "{grace}s.\n\nAn order may be live that this application cannot see, so "
        "submission is blocked — and stays blocked across a restart. Verify the "
        "account in MetaTrader before clearing this."
    ),
    "exec.note_placeholder": (
        "State what you verified in MetaTrader — e.g. 'checked Trade and History "
        "tabs, no order or position under magic 20260806'"
    ),
    "exec.acknowledge": "Acknowledge and clear",
    "exec.current": "Current execution",
    "exec.idle": "No execution in flight",
    "exec.idle.detail": (
        "Nothing has been submitted in this session. When an order is sent its "
        "progress appears here, and if the broker cannot account for it the "
        "submit gate closes until you clear it."
    ),
    "exec.policy": "Execution policy",
    "exec.orders": "Working orders",
    "exec.no_orders": "No working orders",
    "step.submitting": "Submitting",
    "step.accepted": "Accepted",
    "step.partial": "Partial",
    "step.filled": "Filled",
    "step.position": "Position",
    "step.completed": "Completed",
    "exec.field.id": "Execution id",
    "exec.field.symbol": "Symbol",
    "exec.field.state": "State",
    "exec.field.resolved": "Resolved",
    "exec.field.order": "Order ticket",
    "exec.field.deal": "Deal ticket",
    "exec.field.position": "Position id",
    "exec.field.volume": "Requested / filled",
    "exec.field.retcode": "Retcode",
    "exec.field.message": "Message",
    "exec.resolved.yes": "yes",
    "exec.resolved.no": "NO — gate held shut",
    "exec.field.mode": "Run mode",
    "exec.field.account": "Account type",
    "exec.field.real": "Real accounts",
    "exec.field.boundary": "Order boundary",
    "exec.field.arming": "Arming",
    "exec.field.ttl": "Arm TTL",
    "exec.field.grace": "Reconcile grace",
    "exec.field.magic": "Magic number",
    "exec.real_blocked": "blocked unconditionally",
    "exec.boundary": "core.execution only",
    "exec.arming.required": "arm + confirm required",
    "exec.arming.na": "not applicable in this mode",
    # ---- health
    "health.session": "Session",
    "health.verification": "Verification status",
    "health.assumptions": "Assumption registry",
    "health.assumptions.note": (
        "[ASSUMED] is a working default that has not been validated against a "
        "live broker. [POLICY] is a project decision, enforced structurally."
    ),
    "health.journal": "Event journal",
    "health.journal.note": (
        "Repeated events are counted rather than repeated — a refusal logged "
        "every 250 ms is the same as no log at all."
    ),
    "health.field.build": "Build",
    "health.field.rule": "Rule version",
    "health.field.scoring": "Scoring version",
    "health.field.runtime": "Runtime",
    "health.field.evidence": "Counts as evidence",
    "health.field.database": "Database",
    "health.field.gateway": "Gateway",
    "health.field.passes": "Passes",
    "health.field.passtime": "Pass time",
    "health.field.news": "News filtering",
    "health.evidence.yes": "yes — production history",
    "health.evidence.no": "NO — not production data",
    "health.news.blind": "NONE — this run is news-blind",
    "health.news.active": "active",
    "health.gateway.none": "no broker — synthetic data",
    "health.verify.core": "Core engines",
    "health.verify.core.status": "unit tested and executed",
    "health.verify.persistence": "Persistence",
    "health.verify.persistence.status": "tested against real sqlite3",
    "health.verify.backtest": "Backtest replay",
    "health.verify.backtest.status": "executed end to end",
    "health.verify.indicators": "Indicator agreement",
    "health.verify.indicators.status": "NOT verified against a terminal",
    "health.verify.live": "Live broker path",
    "health.verify.live.status": "NOT verified — needs Windows + MT5",
    "health.verify.edge": "Strategy edge",
    "health.verify.edge.status": "NOT established, and not claimed",
    "health.verify.note": (
        "Anything marked NOT verified has not been executed. See "
        "docs/VERIFICATION.md for the full accounting."
    ),
    "col.parameter": "Parameter",
    "col.value": "Value",
    "col.kind": "Kind",
    # ---- domain vocabulary that reaches the screen
    # These come from enums and refusal codes rather than prose, but the
    # operator reads them as words, so they get translated like words.
    "zone.inside": "inside",
    "zone.above": "above",
    "zone.below": "below",
    "zone.unavailable": "unavailable",
    "code.NO_CONFIRMED_SETUP": "no confirmed setup",
    "code.SPREAD_OR_QUOTE_BLOCK": "spread or quote blocked",
    "code.OPPOSING_ZONE_BEFORE_2R": "opposing zone before 2R",
    "code.H4_H1_CONFLICT_LONG": "H4/H1 conflict (long)",
    "code.H4_H1_CONFLICT_SHORT": "H4/H1 conflict (short)",
    "code.STOP_ON_WRONG_SIDE_OF_ENTRY": "stop on wrong side of entry",
    "code.INVALID_STRUCTURAL_STOP": "invalid structural stop",
    "code.ALREADY_EXPOSED": "already exposed on this symbol",
    "code.NO_STRUCTURE": "no structure yet",
    "code.NO_ATR": "no ATR yet",
    # ---- shared
    "dir.long": "BUY",
    "dir.short": "SELL",
    "chart.bars": "last {count} bars",
    "chart.zones": "supply / demand zones shaded",
    "common.none": "—",
    "common.disabled": "disabled — {reason}",
    "common.samples": "n/a ({count}/{floor} samples)",
    "common.probability": "{rate} [{low}–{high}] n={count}",
    # ---- scanner
    "nav.scanner": "Scanner",
    "nav.scanner.tip": "Every symbol, ranked by what the evidence supports",
    "nav.settings": "Settings",
    "nav.settings.tip": "Presets, thresholds and appearance",
    "scan.col.symbol": "SYMBOL",
    "scan.col.trend": "TREND",
    "scan.col.rate": "WIN RATE",
    "scan.col.side": "SIDE",
    "scan.col.confidence": "WIN RATE",
    "scan.col.rr": "RR",
    "scan.col.edge": "EDGE",
    "scan.col.status": "STATUS",
    "scan.filter.all": "All",
    "scan.filter.tradable": "Tradable",
    "scan.filter.measured": "Measured",
    "scan.tier.measured": "MEASURED",
    "scan.tier.provisional": "PROVISIONAL",
    "scan.tier.unmeasured": "NO DATA",
    "scan.tier.measured.tip": "{count} resolved trades — enough for the interval to mean something",
    "scan.tier.provisional.tip": "Only {count} resolved trades. Too few for a headline rate; the interval is shown instead",
    "scan.tier.unmeasured.tip": "Fewer than {floor} resolved trades. No rate is claimed — the number shown is a rule score",
    "scan.prov.replay": "from backtest",
    "scan.prov.live": "from live/demo",
    "scan.prov.mixed": "mixed sources",
    "scan.prov.none": "no source",
    "scan.score": "score {score}",
    "scan.score.note": "not a probability",
    "scan.no_rate": "no rate yet",
    "scan.breakeven": "break-even {rate}",
    "scan.edge": "{value}R",
    "scan.edge.per_trade": "{value}R expected per trade",
    "scan.interval": "95% interval {low}–{high}",
    "scan.sample": "n={count}",
    "scan.verdict.take": "Backed by evidence",
    "scan.verdict.take.body": "The conservative bound ({low}) clears the {breakeven} this reward-to-risk needs. Expected {edge}R per trade.",
    "scan.verdict.watch": "Tradable, not yet evidenced",
    "scan.verdict.watch.body": "Every gate passed, but there is no measured win rate for this setup yet. The number shown is a rule score, not a probability.",
    "scan.verdict.thin": "Evidence too thin",
    "scan.verdict.thin.body": "The conservative bound ({low}) does not clear the {breakeven} this reward-to-risk needs. More data, or a better entry.",
    "scan.verdict.blocked": "Blocked",
    "scan.verdict.blocked.body": "Not tradable right now: {reason}.",
    "scan.empty.title": "Scanning",
    "scan.empty.body": "No symbols have reported yet. The first pass completes within a few seconds of the terminal connecting.",
    "scan.detail.empty": "Select a row to see the chart and the reasoning behind it.",
    "scan.evidence": "EVIDENCE",
    "scan.plan": "PLAN",
    "scan.entry": "Entry",
    "scan.stop": "Stop",
    "scan.target": "Target",
    "scan.open": "Open in Signal view",
    "scan.count": "{shown} of {total} symbols",
    "scan.actionable": "{count} backed by evidence",
    # ---- settings
    "set.profile": "PRESET",
    "set.profile.default": "Default",
    "set.profile.auto": "Auto",
    "set.profile.manual": "Manual",
    "set.profile.default.body": "The shipped values, unchanged. Every one of them is marked [ASSUMED] or [POLICY] on the Health tab, and none has been validated against your broker yet.",
    "set.profile.auto.body": "Starts from Default and tightens where measured evidence supports it. It only ever makes the scanner more selective — it cannot loosen a policy floor.",
    "set.profile.manual.body": "Your values, kept across restarts. The policy floors still apply: risk per trade cannot exceed its ceiling and reward-to-risk cannot go below its floor.",
    "set.auto.note": "Auto adjusts these. Switch to Manual to set them yourself.",
    "set.locked": "Fixed by policy — not adjustable in v1.x.",
    "set.thresholds": "THRESHOLDS",
    "set.score_threshold": "Minimum rule score",
    "set.min_rr": "Minimum reward-to-risk",
    "set.risk_percent": "Risk per trade",
    "set.min_sample": "Minimum sample before a rate is shown",
    "set.appearance": "APPEARANCE",
    "set.theme": "Theme",
    "set.theme.dark": "Dark",
    "set.theme.light": "Light",
    "set.symbols": "SYMBOLS",
    "set.symbols.note": "One per line. Takes effect on the next restart.",
    "set.reset": "Reset to Default",
    "set.applied": "Applied.",
    "set.restart": "Saved. Symbol changes take effect on restart.",
    # ---- backtest view
    "nav.backtest": "Backtest",
    "nav.backtest.tip": "Replay history through the same pipeline and read the result",
    "bt.source": "DATA SOURCE",
    "bt.source.sample": "Sample data",
    "bt.source.files": "Broker files…",
    "bt.source.sample.chip": "SAMPLE DATA",
    "bt.source.files.chip": "BROKER FILES",
    "bt.source.sample.body": "A seeded generator, not a market. Its trend is a sum of sine waves, so the series is predictable by construction and a trend-pullback strategy scores far better on it than on real prices. A good result here means the pipeline runs. It means nothing else.",
    "bt.source.files.body": "MetaTrader CSV exports from {folder}. Real prices, so the result is worth reading — subject to the caveats the report prints about bar-resolution fills and cost modelling.",
    "bt.parameters": "PARAMETERS",
    "bt.symbols": "Symbols (comma separated)",
    "bt.h4_bars": "H4 bars to generate",
    "bt.warmup": "Warm-up bars to skip",
    "bt.persist": "Write results into the evidence base",
    "bt.persist.body": "The scanner will then show these as measured rates, labelled \"from backtest\". Writing REPLACES any previous backtest evidence rather than adding to it — appending would double the sample behind every rate while describing the same trades twice.",
    "bt.persist.tip": "Replaces the previous backtest evidence",
    "bt.persist.unavailable": "No database in this session — nothing to write to",
    "bt.run": "Run backtest",
    "bt.stop": "Stop",
    "bt.progress": "{done} / {total} bars",
    "bt.running": "Running. The window stays responsive — the replay is on its own thread.",
    "bt.report": "REPORT",
    "bt.report.empty": "No run yet.\n\nChoose a data source above, then press Run backtest.\n\nThe report will state what the run does and does not establish, including whether the sample cleared the minimum and whether the data was real.",
    "bt.error.no_symbols": "No symbols given. Enter at least one, for example: EURUSD,XAUUSD",
    "bt.error.failed": "The run failed and stopped:\n\n{message}",
}

FA: dict[str, str] = {
    # ---- shell
    "app.title": "اسکنر علیخنده",
    "app.brand": "علیخنده",
    "app.brandsub": "اسکنر",
    "nav.dashboard": "داشبورد",
    "nav.signal": "سیگنال",
    "nav.risk": "ریسک",
    "nav.execution": "اجرا",
    "nav.health": "سلامت",
    "nav.guide": "راهنما",
    "nav.dashboard.tip": "همین حالا چه خبر است",
    "nav.signal.tip": "یک نماد، همراه با ساختاری که بر آن بنا شده",
    "nav.risk.tip": "میزان ریسک در برابر سقف‌ها، و پایگاه شواهد",
    "nav.execution.tip": "سفارش در جریان و تطبیق آن",
    "nav.health.tip": "این نسخه چه چیزی را اثبات کرده و چه چیزی را نکرده",
    "nav.guide.tip": "چطور از این برنامه ایمن استفاده کنیم",
    "shell.mode": "حالت",
    "shell.language": "زبان",
    "mode.alert": "فقط هشدار",
    "mode.shadow": "سایه",
    "mode.demo": "دمو · مسلح + تأیید",
    # ---- environments (2.2) --------------------------------------------
    # ---- operations (2.2) -----------------------------------------------
    "nav.ops": "عملیات",
    "nav.ops.tip": "اتصال، داده، سابقه و ابزارهای بازیابی",
    "ops.link": "اتصال بروکر",
    "ops.link.unknown": "بررسی نشده",
    "ops.link.latency": "تأخیر",
    "ops.link.peak": "بیشینهٔ تأخیر",
    "ops.link.availability": "در دسترس‌بودن",
    "ops.link.failures": "بررسی‌های ناموفق",
    "ops.link.probes": "کل بررسی‌ها",
    "ops.data": "کیفیت داده",
    "ops.data.clean.title": "مشکل مزمنی نیست",
    "ops.data.clean.body": "نمادی این‌جا می‌آید که دست‌کم در سی پویش، بیشترشان غیرقابل‌استفاده بوده باشد.",
    "ops.data.chronic": "در {fraction} از {passes} پویش غیرقابل استفاده",
    "ops.data.note": "یک پویش بد یعنی نماد هنوز در حال دانلود است. همان نماد اگر دو روز خطا بدهد یعنی بروکر آن را سرو نمی‌کند، و فقط سابقهٔ تجمیع‌شده این دو را از هم جدا می‌کند.",
    "ops.sessions": "تاریخچهٔ نشست‌ها",
    "ops.exit.clean": "درست بسته شد",
    "ops.exit.crash": "بدون بسته‌شدن تمام شد",
    "ops.exit.running": "در حال اجرا",
    "ops.exit.unknown": "نامعلوم",
    "ops.recovery": "پشتیبان و بازیابی",
    "ops.recovery.idle": "در این نشست هنوز نگهداری‌ای اجرا نشده.",
    "ops.backup.now": "همین حالا پشتیبان بگیر",
    "ops.backup.ok": "پشتیبان نوشته و تأیید شد: {path}",
    "ops.backup.failed": "پشتیبان‌گیری شکست خورد و چیزی نوشته نشد: {error}",
    "ops.diagnostics": "بستهٔ عیب‌یابی",
    "ops.diagnostics.ok": "عیب‌یابی در {path} نوشته شد",
    "ops.settings.export": "خروجی تنظیمات",
    "ops.settings.ok": "تنظیمات در {path} نوشته شد",
    "ops.backups": "پشتیبان‌ها",
    "ops.backups.empty.title": "هنوز پشتیبانی نیست",
    "ops.backups.empty.body": "همین حالا یکی بگیر، یا بگذار ربات طبق زمان‌بندی بگیرد.",
    "ops.backups.size": "{kb} کیلوبایت",
    "ops.restore": "بازیابی",
    "ops.restore.placeholder": "مسیر فایل پشتیبان",
    "ops.restore.confirm.title": "این پشتیبان بازیابی شود؟",
    "ops.restore.confirm.body": "پایگاه‌دادهٔ فعلی به فایلی با مهر زمانی منتقل می‌شود، نه حذف، و {path} جای آن را می‌گیرد.",
    "ops.restore.ok": "بازیابی شد. پایگاه‌دادهٔ قبلی در {path} نگه داشته شد",
    "ops.restore.failed": "بازیابی رد شد: {error}",
    "ops.journal": "دفترچه",
    "ops.journal.search": "فیلتر بر اساس کد، زمینه یا پیام",
    "ops.journal.count": "{shown} از {total}",
    # ---- robot (2.2) ----------------------------------------------------
    "nav.robot": "ربات",
    "nav.robot.tip": "خودکارسازی، و مرزی که از آن عبور نمی‌کند",
    "robot.status": "وضعیت",
    "robot.actions": "آخرین پویش",
    "robot.actions.empty.title": "هنوز کاری نیست",
    "robot.actions.empty.body": "کارهایی که ربات انجام می‌دهد همین‌جا ظاهر می‌شوند.",
    "robot.start": "شروع ربات",
    "robot.stop": "توقف ربات",
    "robot.resume": "ادامه بده",
    "robot.state.stopped": "متوقف",
    "robot.state.idle": "بی‌کار",
    "robot.state.watching": "در حال دیده‌بانی",
    "robot.state.holding": "در حال انتظار",
    "robot.state.paused": "مکث‌کرده",
    "robot.watching": "داخل پنجرهٔ معاملاتی و در حال پویش. کاندیداها در اسکنر دیده می‌شوند.",
    "robot.idle": "بیرون از همهٔ پنجره‌های معاملاتی. نگهداری همچنان اجرا می‌شود.",
    "robot.holding": "کاندیدایی ارائه نمی‌شود: {reason}.",
    "robot.field.window": "پنجرهٔ معاملاتی",
    "robot.field.next": "پنجرهٔ بعدی",
    "robot.field.candidates": "کاندیداها",
    "robot.field.backup": "پشتیبان",
    "robot.next_in": "{window}، تا {minutes} دقیقه",
    "robot.backup.never": "در این نشست گرفته نشده",
    "robot.backup.taken": "در این نشست گرفته شد",
    "robot.permissions": "چه کارهایی مجاز است",
    "robot.perm.reconnect": "اتصال قطع‌شده یا یخ‌زده را دوباره برقرار کند",
    "robot.perm.disarm": "قصد کهنه را خلع‌سلاح و در ابطال ساختار لغو کند",
    "robot.perm.pause_guard": "با فعال‌شدن نگهبان ریسک، خودش مکث کند",
    "robot.perm.pause_degraded": "با غیرقابل‌استفاده‌شدن داده یا اتصال، خودش مکث کند",
    "robot.perm.backup": "طبق زمان‌بندی، پشتیبان تأییدشده بگیرد",
    "robot.perm.backup_every": "پشتیبان‌گیری هر",
    "robot.hours": "ساعت",
    "robot.windows": "پنجره‌های معاملاتی",
    "robot.window.london": "لندن",
    "robot.window.newyork": "نیویورک",
    "robot.window.asia": "آسیا",
    "robot.window.test": "آزمایشی",
    "robot.window.off": "خاموش",
    "robot.windows.note": "به وقت سرور بروکر، نه وقت محلی. پنجرهٔ معاملاتی حرفی دربارهٔ بازار است، و بازار نمی‌داند ساعت این دستگاه روی چه منطقه‌ای تنظیم شده.",
    "robot.lock.title": "اجرای بدون نظارت",
    "robot.lock.body": "ربات هرگز مسلح نمی‌کند و هرگز تأیید نمی‌کند. اجرا به دو اقدام عمدی انسانی روی دو کنترل جدا نیاز دارد، و خلبان خودکاری که یکی از آن دو را انجام دهد این دروازه را تضعیف نمی‌کند — حذفش می‌کند، چون آن‌وقت یک کلیک برای ارسال سفارش کافی است.",
    "robot.lock.reason.1": "در RunMode هیچ عضوی برای معاملهٔ واقعی وجود ندارد.",
    "robot.lock.reason.2": "core.execution هر حساب غیردمو را با بازگشت قطعی رد می‌کند.",
    "robot.lock.reason.3": "آداپتر MT5 دوباره رد می‌کند، بدون هیچ کد مشترکی با آن بررسی.",
    "robot.lock.reason.4": "محیط اعلام‌شده بر پایهٔ آنچه کاربر اعلام کرده رد می‌کند، نه آنچه ترمینال گزارش داده.",
    "code.AUTO_EXECUTE_NOT_AUTHORISED": "اجرای بدون نظارت مجاز نیست",
    "code.OUTSIDE_WINDOW": "بیرون از همهٔ پنجره‌های معاملاتی",
    "code.LINK_UNUSABLE": "اتصال بروکر قابل استفاده نیست",
    "code.DATA_UNUSABLE": "داده قابل استفاده نیست",
    "code.NEWS_BLOCKED": "پنجرهٔ خبری باز است",
    "code.RISK_GUARD": "نگهبان ریسک فعال شده",
    "code.EXECUTION_UNRESOLVED": "یک اجرا حل‌نشده مانده",
    "code.ENVIRONMENT_LOCKED": "این محیط نمی‌تواند ارسال کند",
    "code.BACKUP": "پشتیبان گرفت",
    "code.RECONNECT": "در حال اتصال دوباره",
    "code.DISARM": "قصد کهنه را خلع‌سلاح کرد",
    "code.PAUSE": "خودش مکث کرد",
    "code.PAUSE_EXPIRED": "مکث تمام شد، بازارزیابی",
    "code.PRESENT": "ارائهٔ کاندیداها",
    "unit.ms": "م‌ث",
    "env.demo": "دمو",
    "env.production": "تولید",
    "env.backtest": "بک‌تست",
    "env.locked": "قفل‌شده",
    "env.demo.tip": "ترمینال زنده روی حساب دمو. تنها محیطی که سفارش می‌تواند ارسال شود، آن هم فقط پس از مسلح‌کردن و تأیید.",
    "env.production.tip": "ترمینال زنده روی حساب واقعی. همه‌چیز اجرا می‌شود — اتصال، حجم‌دهی، پیش‌پرواز، تطبیق، گزارش. ارسال سفارش سخت‌قفل است.",
    "env.backtest.tip": "بازپخش روی کندل‌های ضبط‌شده یا مصنوعی. بروکری در کار نیست، پس چیزی ارسال نمی‌شود.",
    "code.LIVE": "زنده",
    "code.REPLAY": "بازپخش",
    "code.OFFLINE": "آفلاین",
    "code.IDLE": "بی‌کار",
    "code.SUBMITTING": "در حال ارسال",
    "code.ACCEPTED": "پذیرفته‌شده",
    "code.PARTIALLY_FILLED": "پرشدن جزئی",
    "code.FILLED": "پرشده",
    "code.POSITION_ACTIVE": "پوزیشن فعال",
    "code.REJECTED": "ردشده",
    "code.CANCELLED": "لغوشده",
    "code.UNKNOWN": "نامعلوم",
    "code.RECONCILING": "در حال تطبیق",
    "code.COMPLETED": "تمام‌شده",
    "code.PRODUCTION_SEND_HARD_LOCKED": "ارسال در محیط تولید سخت‌قفل است",
    "code.MODE_NOT_AVAILABLE_IN_PRODUCTION": "در محیط تولید در دسترس نیست",
    "code.MODE_NOT_AVAILABLE_IN_BACKTEST": "در بک‌تست در دسترس نیست",
    "code.BACKTEST_HAS_NO_BROKER": "بک‌تست بروکر ندارد",
    "code.REAL_ACCOUNT_IN_DEMO_ENVIRONMENT": "حساب واقعی متصل است ولی محیط دمو اعلام شده",
    "code.DEMO_ACCOUNT_IN_PRODUCTION": "حساب دمو متصل است ولی محیط تولید اعلام شده",
    "code.REAL_ACCOUNT_AS_DECLARED": "حساب واقعی، مطابق اعلام",
    "code.DEMO_ACCOUNT_AS_DECLARED": "حساب دمو، مطابق اعلام",
    "code.ACCOUNT_UNKNOWN": "حساب خوانده نشد",
    "chip.starting": "در حال شروع",
    "chip.no_account": "بدون حساب",
    "chip.no_broker": "بدون بروکر",
    "chip.simulated": "شبیه‌سازی‌شده",
    "chip.connected": "متصل",
    "chip.disconnected": "قطع",
    "chip.demo": "دمو",
    "chip.real_blocked": "واقعی — مسدود",
    "chip.no_broker.tip": (
        "هیچ ترمینال متاتریدری متصل نیست. قیمت‌ها ساختگی‌اند و هیچ‌چیز اینجا "
        "بازار واقعی را توصیف نمی‌کند."
    ),
    "banner.real": (
        "حساب واقعی شناسایی شد ({login} @ {server}). اجرا بدون قید و شرط مسدود "
        "است و انتخاب حالت روی «فقط هشدار» قفل شده. این نسخه هرگز روی حساب "
        "واقعی معامله نمی‌کند."
    ),
    "banner.review": (
        "یک اجرا با بروکر تطبیق داده نشد. ارسال سفارش مسدود است تا در نمای «اجرا» "
        "بررسی و تأیید شود."
    ),
    "status.pass": "پویش {passes}  ·  {ms} میلی‌ثانیه  ·  {runtime}  ·  ریسک باز {risk}",
    "status.starting": "در حال شروع…",
    # ---- dashboard
    "dash.opportunities": "فرصت‌ها",
    "dash.watchlist": "فهرست پایش",
    "dash.tile.actionable": "قابل اقدام",
    "dash.tile.actionable.caption": "واجد شرایط با حجم محاسبه‌شده",
    "dash.tile.watching": "در حال پایش",
    "dash.tile.watching.caption": "از {total} نماد پیکربندی‌شده",
    "dash.tile.risk": "ریسک باز",
    "dash.tile.risk.caption": "سقف {cap}",
    "dash.tile.evidence": "شواهد",
    "dash.tile.evidence.none": "هنوز هیچ نتیجه‌ای ثبت نشده",
    "dash.tile.evidence.below": "{count} از {floor} تا نمایش نرخ برد",
    "dash.tile.evidence.ok": "نتیجه ثبت‌شده",
    "dash.verdict.ready": "{count} ستاپ آماده",
    "dash.verdict.ready.detail": (
        "{names} واجد شرایط شد و حجمش محاسبه شد. قبل از هر اقدامی بازش کنید تا "
        "ساختاری را که بر آن بنا شده ببینید."
    ),
    "dash.verdict.unresolved": "هیچ نمادی شناسایی نشد",
    "dash.verdict.unresolved.detail": (
        "هیچ‌یک از نمادهای پیکربندی‌شده با نامی روی این بروکر مطابقت نداشت. "
        "Market Watch متاتریدر را بررسی کنید."
    ),
    "dash.verdict.warming": "در حال آماده‌سازی",
    "dash.verdict.warming.detail": (
        "{warming} نماد از {total} نماد هنوز در حال جمع‌آوری اسپرد و تاریخچه‌ای "
        "است که برای امتیازدهی لازم دارد. این برای یکی دو دقیقهٔ اول طبیعی است."
    ),
    "dash.verdict.nothing": "چیزی برای اقدام نیست",
    "dash.verdict.nothing.detail": (
        "هر {total} نماد پویش شد؛ هیچ‌کدام در حال حاضر به آستانهٔ {threshold} "
        "امتیاز با ستاپ تأییدشده روی یک ناحیهٔ ساختاری نمی‌رسند. این بیشتر وقت‌ها "
        "حالت طبیعی است."
    ),
    "dash.empty.title": "در حال حاضر چیزی برای اقدام نیست",
    "dash.empty.detail": (
        "یک ستاپ فقط وقتی اینجا ظاهر می‌شود که ساختار تأییدشده، اسپرد تمیز و حجم "
        "محاسبه‌شده هر سه با هم جور شوند. دلایل رد شدن برای هر نماد در نمای "
        "«سیگنال» نشان داده می‌شود — خالی بودن این فضا یعنی اسکنر دارد کار می‌کند."
    ),
    "dash.guards.ok": "محافظ‌ها سالم",
    "dash.guards.review": "نیازمند بررسی",
    "dash.guards.halted": "متوقف",
    "dash.guards.newsblind": "کور نسبت به اخبار",
    "col.symbol": "نماد",
    "col.trend": "روند",
    "col.bias": "جهت",
    "col.score": "امتیاز",
    "col.structure": "ساختار",
    "col.spread": "اسپرد",
    "col.state": "وضعیت",
    "cell.unresolved": "روی این بروکر شناسایی نشد",
    "cell.building": "در حال ساخت ساختار",
    "cell.plan_ready": "طرح آماده",
    "cell.watching": "در حال پایش",
    "card.top_contributors": "بیشترین سهم: {items}",
    "card.no_breakdown": "تفکیک امتیاز در دسترس نیست.",
    "card.not_sized": "حجم محاسبه نشد",
    "card.lots": "{lots} لات",
    "card.risk": "ریسک {amount} ({percent})",
    "card.rr": "ریسک به ریوارد ۱ : {ratio}",
    # ---- signal
    "signal.chart": "قیمت و ساختار",
    "signal.chart.title": "{symbol} · M5 · ۱۲۰ کندل آخر",
    "signal.chart.legend": "نواحی عرضه / تقاضا سایه‌دار",
    "signal.chart.waiting": "در انتظار تاریخچهٔ قیمت",
    "signal.why": "چرا این امتیاز",
    "signal.plan": "طرح معامله",
    "signal.refusals": "چرا قابل معامله نیست",
    "signal.execute": "اجرا",
    "signal.no_setup": "بدون ستاپ",
    "signal.score_note": (
        "خرید {long}  ·  فروش {short}  ·  آستانه {threshold} با اختلاف لازم "
        "{separation} امتیاز.  این جمع وزنی شرط‌هاست، نه احتمال."
    ),
    "signal.no_components": "بدون سهم — این نماد هیچ سمت واجد شرایطی ندارد.",
    "plan.entry": "ورود",
    "plan.stop": "حد ضرر",
    "plan.target": "حد سود",
    "plan.rr": "ریسک : ریوارد",
    "plan.lots": "حجم (لات)",
    "plan.risk": "مبلغ ریسک",
    "plan.margin": "مارجین",
    "plan.expires": "انقضا تا",
    "plan.historical": "سابقهٔ آماری",
    "btn.arm": "مسلح کردن",
    "btn.confirm": "تأیید ارسال",
    "exec.armed": (
        "مسلح شد — ظرف {seconds} ثانیه تأیید کنید وگرنه منقضی می‌شود و باید روی "
        "یک طرح تازه دوباره مسلح شود."
    ),
    "exec.mode_blocks": "{mode} — در این حالت هیچ سفارشی از برنامه خارج نمی‌شود.",
    "exec.review_blocks": (
        "یک اجرا با بروکر تطبیق داده نشد. ارسال مسدود است تا در نمای «اجرا» "
        "بررسی شود."
    ),
    "exec.news_blocks": "توسط دروازهٔ اخبار مسدود شد.",
    "exec.ready": "طرح آماده است. اول مسلح کنید، بعد تأیید — عمداً دو اقدام جداگانه.",
    "exec.no_plan": "طرح معتبری برای این نماد وجود ندارد.",
    # ---- risk
    "risk.tile.equity": "اکوئیتی",
    "risk.tile.equity.caption": "واحد پول حساب",
    "risk.tile.risk": "ریسک باز",
    "risk.tile.positions": "پوزیشن‌ها",
    "risk.tile.positions.caption": "بازشده توسط این برنامه",
    "risk.tile.drawdown": "افت سرمایه",
    "risk.tile.drawdown.caption": "نسبت به اوج اکوئیتی",
    "risk.exposure": "میزان ریسک در برابر سقف‌ها",
    "risk.meter.open": "ریسک باز کل",
    "risk.meter.currency": "پرتکرارترین ارز",
    "risk.meter.class": "طبقهٔ دارایی",
    "risk.bounded": "همهٔ پوزیشن‌ها کران‌دار",
    "risk.unbounded": (
        "{count} پوزیشن بدون بدترین حالت قابل محاسبه — همهٔ اعداد بالا کران "
        "پایین‌اند و ریسک جدید رد می‌شود ({symbols})"
    ),
    "risk.policy": "سیاست ریسک",
    "risk.guards": "وضعیت محافظ‌ها",
    "risk.evidence": "پایگاه شواهد",
    "risk.positions": "پوزیشن‌های باز",
    "risk.no_positions": "پوزیشن بازی نیست",
    "risk.no_positions.detail": "این برنامه چیزی باز نکرده است.",
    "risk.no_outcomes": "هنوز نتیجه‌ای نیست",
    "risk.no_outcomes.detail": (
        "نرخ برد فقط پس از {floor} معاملهٔ بسته‌شده روی همان نماد، ستاپ و نسخهٔ "
        "قوانین نمایش داده می‌شود. تا آن زمان چیز صادقانه‌ای برای نشان دادن نیست."
    ),
    "risk.no_database": "بدون پایگاه‌داده",
    "risk.no_database.detail": (
        "این نشست چیزی ثبت نمی‌کند، پس پایگاه شواهدی برای نمایش وجود ندارد."
    ),
    "policy.per_trade": "ریسک هر معامله",
    "policy.ceiling": "سقف هر معامله",
    "policy.min_rr": "حداقل ریسک به ریوارد",
    "policy.aggregate": "سقف مجموع",
    "policy.currency": "سقف هر ارز",
    "policy.class": "سقف طبقهٔ دارایی",
    "policy.breakers": "قطع‌کننده‌های مدار",
    "policy.enabled": "فعال",
    "policy.disabled": "غیرفعال (پیش‌فرض)",
    "guard.permitted": "اجازهٔ معامله",
    "guard.breached": "محافظ‌های نقض‌شده",
    "guard.peak": "اوج اکوئیتی",
    "guard.daystart": "اکوئیتی ابتدای روز",
    "guard.losses": "باخت‌های متوالی",
    "guard.used": "ریسک مصرف‌شدهٔ امروز",
    "guard.yes": "بله",
    "guard.no": "خیر",
    "guard.none": "هیچ",
    "evidence.trades": "معاملات بسته‌شده",
    "evidence.wins": "برد / باخت",
    "evidence.winrate": "نرخ برد",
    "evidence.wilson": "فاصلهٔ ویلسون ۹۵٪",
    "evidence.total_r": "مجموع R",
    "evidence.expectancy": "امید ریاضی",
    "evidence.withheld": "نمایش داده نمی‌شود — {count} از {floor}",
    "col.side": "سمت",
    "col.volume": "حجم",
    "col.entry": "ورود",
    "col.stop": "حد ضرر",
    "col.target": "حد سود",
    "col.pl": "سود/زیان",
    "col.bounded": "کران‌دار",
    "cell.bounded": "کران‌دار",
    "cell.unbounded": "بدون کران — ریسک جدید رد می‌شود",
    # ---- execution
    "exec.review_title": "نیازمند بررسی دستی",
    "exec.review_body": (
        "اجرای {id} روی {symbol} پس از {grace} ثانیه با پوزیشن‌های باز، سفارش‌های "
        "فعال، تاریخچهٔ سفارش‌ها و تاریخچهٔ معاملات تطبیق داده نشد.\n\nممکن است "
        "سفارشی زنده باشد که این برنامه آن را نمی‌بیند، پس ارسال مسدود است — و پس "
        "از ری‌استارت هم مسدود می‌ماند. قبل از پاک کردن، حساب را در متاتریدر "
        "بررسی کنید."
    ),
    "exec.note_placeholder": (
        "بنویسید در متاتریدر چه چیزی را بررسی کردید — مثلاً «تب‌های Trade و "
        "History بررسی شد، هیچ سفارش یا پوزیشنی با magic 20260806 نبود»"
    ),
    "exec.acknowledge": "تأیید و پاک کردن",
    "exec.current": "اجرای جاری",
    "exec.idle": "هیچ اجرایی در جریان نیست",
    "exec.idle.detail": (
        "در این نشست چیزی ارسال نشده است. وقتی سفارشی ارسال شود پیشرفتش اینجا "
        "دیده می‌شود، و اگر بروکر نتواند حسابش را بدهد دروازهٔ ارسال تا پاک کردن "
        "آن بسته می‌ماند."
    ),
    "exec.policy": "سیاست اجرا",
    "exec.orders": "سفارش‌های فعال",
    "exec.no_orders": "سفارش فعالی نیست",
    "step.submitting": "در حال ارسال",
    "step.accepted": "پذیرفته‌شده",
    "step.partial": "پر شدن جزئی",
    "step.filled": "پر شد",
    "step.position": "پوزیشن",
    "step.completed": "تکمیل شد",
    "exec.field.id": "شناسهٔ اجرا",
    "exec.field.symbol": "نماد",
    "exec.field.state": "وضعیت",
    "exec.field.resolved": "تعیین تکلیف",
    "exec.field.order": "تیکت سفارش",
    "exec.field.deal": "تیکت معامله",
    "exec.field.position": "شناسهٔ پوزیشن",
    "exec.field.volume": "درخواستی / پرشده",
    "exec.field.retcode": "کد بازگشت",
    "exec.field.message": "پیام",
    "exec.resolved.yes": "بله",
    "exec.resolved.no": "خیر — دروازه بسته نگه داشته شد",
    "exec.field.mode": "حالت اجرا",
    "exec.field.account": "نوع حساب",
    "exec.field.real": "حساب واقعی",
    "exec.field.boundary": "مرز ارسال سفارش",
    "exec.field.arming": "مسلح‌سازی",
    "exec.field.ttl": "مهلت مسلح ماندن",
    "exec.field.grace": "مهلت تطبیق",
    "exec.field.magic": "شمارهٔ Magic",
    "exec.real_blocked": "بدون قید و شرط مسدود",
    "exec.boundary": "فقط core.execution",
    "exec.arming.required": "مسلح + تأیید لازم است",
    "exec.arming.na": "در این حالت کاربرد ندارد",
    # ---- health
    "health.session": "نشست",
    "health.verification": "وضعیت اثبات",
    "health.assumptions": "فهرست فرض‌ها",
    "health.assumptions.note": (
        "[ASSUMED] یعنی مقدار پیش‌فرضی که روی بروکر واقعی اعتبارسنجی نشده است. "
        "[POLICY] یعنی تصمیم پروژه که ساختاراً اعمال می‌شود."
    ),
    "health.journal": "دفتر رویدادها",
    "health.journal.note": (
        "رویدادهای تکراری شمرده می‌شوند نه تکرار — رد شدنی که هر ۲۵۰ میلی‌ثانیه "
        "لاگ شود با نبودن لاگ فرقی ندارد."
    ),
    "health.field.build": "نسخه",
    "health.field.rule": "نسخهٔ قوانین",
    "health.field.scoring": "نسخهٔ امتیازدهی",
    "health.field.runtime": "محیط اجرا",
    "health.field.evidence": "به‌عنوان شواهد شمرده می‌شود",
    "health.field.database": "پایگاه‌داده",
    "health.field.gateway": "دروازه",
    "health.field.passes": "تعداد پویش",
    "health.field.passtime": "زمان هر پویش",
    "health.field.news": "فیلتر اخبار",
    "health.evidence.yes": "بله — تاریخچهٔ عملیاتی",
    "health.evidence.no": "خیر — دادهٔ عملیاتی نیست",
    "health.news.blind": "هیچ — این اجرا نسبت به اخبار کور است",
    "health.news.active": "فعال",
    "health.gateway.none": "بدون بروکر — دادهٔ ساختگی",
    "health.verify.core": "موتورهای هسته",
    "health.verify.core.status": "تست واحد شده و اجرا شده",
    "health.verify.persistence": "ذخیره‌سازی",
    "health.verify.persistence.status": "روی sqlite3 واقعی تست شده",
    "health.verify.backtest": "بازپخش بک‌تست",
    "health.verify.backtest.status": "سرتاسر اجرا شده",
    "health.verify.indicators": "تطابق اندیکاتورها",
    "health.verify.indicators.status": "با ترمینال اثبات نشده",
    "health.verify.live": "مسیر بروکر زنده",
    "health.verify.live.status": "اثبات نشده — نیازمند ویندوز + متاتریدر",
    "health.verify.edge": "برتری استراتژی",
    "health.verify.edge.status": "اثبات نشده، و ادعا هم نمی‌شود",
    "health.verify.note": (
        "هر چیزی که «اثبات نشده» علامت خورده، اجرا نشده است. برای شرح کامل به "
        "docs/VERIFICATION.md مراجعه کنید."
    ),
    "col.parameter": "پارامتر",
    "col.value": "مقدار",
    "col.kind": "نوع",
    # ---- domain vocabulary that reaches the screen
    "zone.inside": "داخل ناحیه",
    "zone.above": "بالای ناحیه",
    "zone.below": "زیر ناحیه",
    "zone.unavailable": "ناحیه‌ای نیست",
    "code.NO_CONFIRMED_SETUP": "ستاپ تأییدشده‌ای نیست",
    "code.SPREAD_OR_QUOTE_BLOCK": "اسپرد یا قیمت مسدود کرد",
    "code.OPPOSING_ZONE_BEFORE_2R": "ناحیهٔ مخالف پیش از ۲R",
    "code.H4_H1_CONFLICT_LONG": "تضاد H4/H1 (خرید)",
    "code.H4_H1_CONFLICT_SHORT": "تضاد H4/H1 (فروش)",
    "code.STOP_ON_WRONG_SIDE_OF_ENTRY": "حد ضرر در سمت اشتباه ورود",
    "code.INVALID_STRUCTURAL_STOP": "حد ضرر ساختاری نامعتبر",
    "code.ALREADY_EXPOSED": "روی این نماد از قبل پوزیشن هست",
    "code.NO_STRUCTURE": "هنوز ساختاری نیست",
    "code.NO_ATR": "هنوز ATR نیست",
    # ---- shared
    "dir.long": "خرید",
    "dir.short": "فروش",
    "chart.bars": "‏{count} کندل آخر",
    "chart.zones": "نواحی عرضه / تقاضا سایه‌دار شده‌اند",
    "common.none": "—",
    "common.disabled": "غیرفعال — {reason}",
    "common.samples": "نامعلوم ({count}/{floor} نمونه)",
    "common.probability": "{rate} [{low}–{high}] n={count}",
    # ---- scanner
    "nav.scanner": "اسکنر",
    "nav.scanner.tip": "همه‌ی نمادها، مرتب‌شده بر اساس آنچه شواهد پشتیبانی می‌کند",
    "nav.settings": "تنظیمات",
    "nav.settings.tip": "پیش‌تنظیم‌ها، آستانه‌ها و ظاهر",
    "scan.col.symbol": "نماد",
    "scan.col.trend": "روند",
    "scan.col.rate": "نرخ برد",
    "scan.col.side": "جهت",
    "scan.col.confidence": "نرخ برد",
    "scan.col.rr": "R:R",
    "scan.col.edge": "برتری",
    "scan.col.status": "وضعیت",
    "scan.filter.all": "همه",
    "scan.filter.tradable": "قابل معامله",
    "scan.filter.measured": "اندازه‌گیری‌شده",
    "scan.tier.measured": "اندازه‌گیری‌شده",
    "scan.tier.provisional": "موقت",
    "scan.tier.unmeasured": "بدون داده",
    "scan.tier.measured.tip": "{count} معامله‌ی بسته‌شده — به‌اندازه‌ای هست که بازه معنا داشته باشد",
    "scan.tier.provisional.tip": "فقط {count} معامله‌ی بسته‌شده. برای نمایش نرخ اصلی کم است؛ در عوض بازه نشان داده می‌شود",
    "scan.tier.unmeasured.tip": "کمتر از {floor} معامله‌ی بسته‌شده. هیچ نرخی ادعا نمی‌شود — عددی که می‌بینید امتیاز قانون است",
    "scan.prov.replay": "از بک‌تست",
    "scan.prov.live": "از زنده/دمو",
    "scan.prov.mixed": "منابع ترکیبی",
    "scan.prov.none": "بدون منبع",
    "scan.score": "امتیاز {score}",
    "scan.score.note": "یک احتمال نیست",
    "scan.no_rate": "هنوز نرخی نیست",
    "scan.breakeven": "سربه‌سر {rate}",
    "scan.edge": "{value}R",
    "scan.edge.per_trade": "{value}R انتظار به ازای هر معامله",
    "scan.interval": "بازه ۹۵٪: {low}–{high}",
    "scan.sample": "n={count}",
    "scan.verdict.take": "متکی بر شواهد",
    "scan.verdict.take.body": "کران محافظه‌کارانه ({low}) از {breakeven} که این نسبت ریسک به ریوارد نیاز دارد عبور می‌کند. انتظار {edge}R به ازای هر معامله.",
    "scan.verdict.watch": "قابل معامله، ولی هنوز بدون شواهد",
    "scan.verdict.watch.body": "همه‌ی دروازه‌ها را رد کرد، اما هنوز نرخ برد اندازه‌گیری‌شده‌ای برای این ستاپ وجود ندارد. عددی که می‌بینید امتیاز قانون است، نه احتمال.",
    "scan.verdict.thin": "شواهد بسیار کم",
    "scan.verdict.thin.body": "کران محافظه‌کارانه ({low}) از {breakeven} موردنیاز این نسبت ریسک به ریوارد عبور نمی‌کند. یا داده‌ی بیشتر لازم است، یا ورود بهتر.",
    "scan.verdict.blocked": "مسدود",
    "scan.verdict.blocked.body": "همین حالا قابل معامله نیست: {reason}.",
    "scan.empty.title": "در حال اسکن",
    "scan.empty.body": "هنوز هیچ نمادی گزارش نداده است. اولین پاس ظرف چند ثانیه پس از اتصال ترمینال کامل می‌شود.",
    "scan.detail.empty": "یک ردیف را انتخاب کنید تا چارت و استدلال پشت آن را ببینید.",
    "scan.evidence": "شواهد",
    "scan.plan": "طرح معامله",
    "scan.entry": "ورود",
    "scan.stop": "حد ضرر",
    "scan.target": "حد سود",
    "scan.open": "باز کردن در نمای سیگنال",
    "scan.count": "{shown} از {total} نماد",
    "scan.actionable": "{count} متکی بر شواهد",
    # ---- settings
    "set.profile": "پیش‌تنظیم",
    "set.profile.default": "پیش‌فرض",
    "set.profile.auto": "خودکار",
    "set.profile.manual": "دستی",
    "set.profile.default.body": "مقادیر ارسالی، بدون تغییر. همه‌ی آن‌ها در تب سلامت با برچسب [ASSUMED] یا [POLICY] مشخص شده‌اند و هیچ‌کدام هنوز روی بروکر شما اعتبارسنجی نشده است.",
    "set.profile.auto.body": "از پیش‌فرض شروع می‌کند و هرجا شواهد اندازه‌گیری‌شده اجازه بدهد سخت‌گیرتر می‌شود. فقط می‌تواند اسکنر را انتخابی‌تر کند — نمی‌تواند کف سیاستی را شل کند.",
    "set.profile.manual.body": "مقادیر خودتان، که بین اجراها حفظ می‌شود. کف‌های سیاستی همچنان برقرارند: ریسک هر معامله از سقفش بالاتر نمی‌رود و نسبت ریسک به ریوارد از کفش پایین‌تر نمی‌آید.",
    "set.auto.note": "حالت خودکار این‌ها را تنظیم می‌کند. برای تنظیم دستی، به حالت دستی بروید.",
    "set.locked": "تثبیت‌شده توسط سیاست — در نسخه ۱.x قابل تغییر نیست.",
    "set.thresholds": "آستانه‌ها",
    "set.score_threshold": "حداقل امتیاز قانون",
    "set.min_rr": "حداقل نسبت ریسک به ریوارد",
    "set.risk_percent": "ریسک هر معامله",
    "set.min_sample": "حداقل نمونه پیش از نمایش نرخ",
    "set.appearance": "ظاهر",
    "set.theme": "تم",
    "set.theme.dark": "تیره",
    "set.theme.light": "روشن",
    "set.symbols": "نمادها",
    "set.symbols.note": "هر خط یک نماد. پس از راه‌اندازی مجدد اعمال می‌شود.",
    "set.reset": "بازگشت به پیش‌فرض",
    "set.applied": "اعمال شد.",
    "set.restart": "ذخیره شد. تغییر نمادها پس از راه‌اندازی مجدد اعمال می‌شود.",
    # ---- backtest view
    "nav.backtest": "بک‌تست",
    "nav.backtest.tip": "بازپخش تاریخچه از همان مسیر پردازش و خواندن نتیجه",
    "bt.source": "منبع داده",
    "bt.source.sample": "دادهٔ نمونه",
    "bt.source.files": "فایل‌های بروکر…",
    "bt.source.sample.chip": "دادهٔ نمونه",
    "bt.source.files.chip": "فایل بروکر",
    "bt.source.sample.body": "یک تولیدکنندهٔ داده است، نه یک بازار. روند آن جمع چند موج سینوسی است، پس سری قیمت ذاتاً قابل‌پیش‌بینی است و یک استراتژی پولبک روی آن خیلی بهتر از قیمت واقعی نتیجه می‌گیرد. نتیجهٔ خوب اینجا فقط یعنی مسیر پردازش کار می‌کند. هیچ معنای دیگری ندارد.",
    "bt.source.files.body": "خروجی‌های CSV متاتریدر از {folder}. قیمت واقعی است، پس نتیجه ارزش خواندن دارد — با همان هشدارهایی که گزارش دربارهٔ پرشدن در سطح کندل و مدل‌نشدن هزینه‌ها چاپ می‌کند.",
    "bt.parameters": "پارامترها",
    "bt.symbols": "نمادها (با کاما جدا کنید)",
    "bt.h4_bars": "تعداد کندل H4 برای تولید",
    "bt.warmup": "کندل‌های گرم‌کردن (نادیده گرفته می‌شوند)",
    "bt.persist": "نتیجه در پایگاه شواهد نوشته شود",
    "bt.persist.body": "بعد از آن اسکنر این‌ها را به‌عنوان نرخ اندازه‌گیری‌شده و با برچسب «از بک‌تست» نشان می‌دهد. نوشتن، شواهد بک‌تست قبلی را جایگزین می‌کند نه اینکه به آن اضافه کند — افزودن، نمونهٔ پشت هر نرخ را دو برابر می‌کرد در حالی که همان معاملات را دو بار توصیف می‌کند.",
    "bt.persist.tip": "شواهد بک‌تست قبلی را جایگزین می‌کند",
    "bt.persist.unavailable": "در این نشست پایگاه‌داده‌ای نیست — جایی برای نوشتن وجود ندارد",
    "bt.run": "اجرای بک‌تست",
    "bt.stop": "توقف",
    "bt.progress": "{done} از {total} کندل",
    "bt.running": "در حال اجرا. پنجره پاسخگو می‌ماند — بازپخش روی نخ جداگانه‌ای اجرا می‌شود.",
    "bt.report": "گزارش",
    "bt.report.empty": "هنوز اجرایی انجام نشده.\n\nاز بالا یک منبع داده انتخاب کنید، بعد «اجرای بک‌تست» را بزنید.\n\nگزارش می‌گوید این اجرا چه چیزی را اثبات می‌کند و چه چیزی را نه — از جمله اینکه نمونه از حداقل عبور کرده یا نه، و اینکه داده واقعی بوده یا نه.",
    "bt.error.no_symbols": "هیچ نمادی وارد نشده. دست‌کم یکی وارد کنید، مثلاً: EURUSD,XAUUSD",
    "bt.error.failed": "اجرا شکست خورد و متوقف شد:\n\n{message}",
}

CATALOGUES: dict[str, dict[str, str]] = {"en": EN, "fa": FA}


def t(key: str, **kwargs) -> str:
    """Look up ``key`` in the current language, falling back to English.

    A missing key returns the key itself rather than raising or returning an
    empty string: an interface showing ``dash.tile.evidence`` is obviously
    broken and gets fixed, whereas a blank label looks like a real empty value
    and can survive for months.
    """
    catalogue = CATALOGUES.get(_current.code, EN)
    template = catalogue.get(key) or EN.get(key) or key
    if not kwargs:
        return template
    try:
        return template.format(**kwargs)
    except (KeyError, IndexError):
        # A malformed placeholder must not take the window down.
        return template


# ------------------------------------------------------------------- numbers


def code(raw: str) -> str:
    """Human words for a refusal code or enum name.

    Falls back to the raw code with underscores softened, so an unlisted code
    still reads as something rather than vanishing — and looks conspicuous
    enough that somebody adds it to the catalogue.
    """
    base = raw.split("(")[0].strip()
    translated = t(f"code.{base}")
    if translated != f"code.{base}":
        return translated
    return base.replace("_", " ").lower()


def zone_relation_name(name: str) -> str:
    return t(f"zone.{name.lower()}")


def to_locale_digits(text: str) -> str:
    """Map Latin digits to the current language's digits."""
    digits = _current.digits
    if not digits:
        return text
    return text.translate(str.maketrans("0123456789", digits))


def fmt_price(value: float, digits: int) -> str:
    """A price. **Always Latin digits.**

    Persian traders read prices in Latin digits — every terminal, statement and
    chart shows them that way — and the Persian digits in the bundled fonts are
    not monospaced, so a column of them would not align. Identity and alignment
    both argue for leaving these alone.
    """
    return f"{value:.{digits}f}"


def fmt_count(value: int) -> str:
    """A count. Follows the locale."""
    return to_locale_digits(f"{value:,}")


def fmt_percent(value: float, places: int = 2) -> str:
    return to_locale_digits(f"{value:.{places}f}%")


def fmt_money(value: float, places: int = 2) -> str:
    return to_locale_digits(f"{value:,.{places}f}")


def fmt_seconds(value: int) -> str:
    return to_locale_digits(f"{value}") + ("s" if not _current.rtl else " ثانیه")


# ----------------------------------------------------------------- preference


def preference_path(data_dir: Path) -> Path:
    return data_dir / "ui-preferences.json"


def load_preferences(data_dir: Path) -> dict:
    """Read stored UI preferences, tolerating a missing or corrupt file.

    A broken preferences file must never stop the application starting — it is
    convenience state, not evidence, and the correct response to unreadable
    convenience state is to ignore it.
    """
    try:
        return json.loads(preference_path(data_dir).read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_preferences(data_dir: Path, preferences: dict) -> bool:
    try:
        preference_path(data_dir).write_text(
            json.dumps(preferences, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return True
    except Exception:
        return False
