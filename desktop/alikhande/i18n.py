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
    "scan.score.note": "A rule score is not a probability.",
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
    "scan.score.note": "امتیاز قانون یک احتمال نیست.",
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
