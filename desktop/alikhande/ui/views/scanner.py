"""The landing screen: every symbol, ranked, with the chart beside it.

This is what the application opens on, and it is built around one question —
*which of these is worth my attention right now, and how sure are we?* Ranked
list on the left, chart and reasoning on the right, no navigation required
between seeing a candidate and being able to disagree with it.

## The number in the "win rate" column is not always a win rate

It is whichever of three things the evidence actually supports, and the row
says which:

* **MEASURED** — a real rate over a real sample, shown with its interval.
* **PROVISIONAL** — an interval only. A headline "67%" over nine trades is a
  lie told with true numbers, so the headline is withheld and the interval is
  what appears.
* **NO DATA** — the rule score, in muted ink, labelled as a rule score.

The tier chip is not decoration. It is the difference between a number you can
act on and a number that merely exists, and it is why this column can carry a
percentage at all without breaking the rule this project has held since
v1.1.0: a rule score is not a probability.

## Rows are widgets, not table cells

A ``QTableWidget`` would be less code, but each row here carries a headline
figure, a caption under it, a chip and a status line — four typographic weights
that a cell's single string cannot express. The widgets are built once per
symbol and updated in place, so a 250 ms refresh mutates labels rather than
rebuilding a layout.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QPushButton,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ...app import scanner as scanner_app
from ...config import AppConfig
from ...core.evidence import EvidenceTier, Opportunity, Provenance
from ...i18n import code as code_text
from ...i18n import fmt_count, fmt_percent, fmt_price, t
from ..charts import PriceChart, TradeLevels
from ..components import Card, DirectionBadge, EmptyState, KeyValue, label
from ..theme import PALETTE, RADIUS, RADIUS_PILL, SPACE, TYPE, score_ramp

# Tier -> (translation key, StatusChip tone). Grey for the two tiers that make
# no claim, because "we have not measured this" is the absence of a status and
# must never borrow the colour of one.
TIER_TONE = {
    EvidenceTier.MEASURED: ("scan.tier.measured", "good"),
    EvidenceTier.PROVISIONAL: ("scan.tier.provisional", "unknown"),
    EvidenceTier.UNMEASURED: ("scan.tier.unmeasured", "unknown"),
}

PROVENANCE_KEY = {
    Provenance.REPLAY: "scan.prov.replay",
    Provenance.LIVE: "scan.prov.live",
    Provenance.MIXED: "scan.prov.mixed",
    Provenance.NONE: "scan.prov.none",
}


def _rate(value: float) -> str:
    return fmt_percent(value * 100.0, 0)


class OpportunityRow(QFrame):
    """One symbol's line in the ranked list."""

    clicked = Signal(str)

    def __init__(self, symbol: str, parent=None):
        super().__init__(parent)
        self.symbol = symbol
        self.setObjectName("SignalCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._selected = False

        row = QHBoxLayout(self)
        row.setContentsMargins(SPACE.lg, SPACE.md, SPACE.lg, SPACE.md)
        row.setSpacing(SPACE.lg)

        # ---- identity
        identity = QVBoxLayout()
        identity.setSpacing(2)
        self._symbol = label(symbol, "H3")
        self._tier = label("", "Micro")
        identity.addWidget(self._symbol)
        identity.addWidget(self._tier)
        row.addLayout(identity)
        row.addSpacing(SPACE.sm)

        self._side = DirectionBadge()
        row.addWidget(self._side)
        row.addStretch(1)

        # ---- the three numbers, each with its own caption
        self._rate_value, self._rate_caption, rate_block = self._number_block()
        self._rr_value, self._rr_caption, rr_block = self._number_block(width=64)
        self._edge_value, self._edge_caption, edge_block = self._number_block(width=78)
        for block in (rate_block, rr_block, edge_block):
            row.addLayout(block)
            row.addSpacing(SPACE.md)

        self._status = label("", "Caption")
        self._status.setFixedWidth(150)
        self._status.setWordWrap(True)
        self._status.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        row.addWidget(self._status)

    def _number_block(self, width: int = 96):
        """A figure with a caption under it, right-aligned as a column.

        Right-aligned because these are quantities read down a column, and a
        left-aligned column of varying-width numbers has no shared edge for the
        eye to compare against.
        """
        column = QVBoxLayout()
        column.setSpacing(1)
        value = label("—", "H2")
        caption = label("", "Micro")
        for widget in (value, caption):
            widget.setFixedWidth(width)
            widget.setAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
        column.addWidget(value)
        column.addWidget(caption)
        return value, caption, column

    # ------------------------------------------------------------------ paint
    def set_selected(self, selected: bool) -> None:
        self._selected = selected
        self.setStyleSheet(
            f"QFrame#SignalCard {{ background: {PALETTE.surface_hover};"
            f" border: 1px solid {PALETTE.border_strong};"
            f" border-radius: {RADIUS}px; }}"
            if selected
            else ""
        )

    def update_from(self, opportunity: Opportunity, config: AppConfig) -> None:
        evidence = opportunity.evidence
        self._symbol.setText(opportunity.symbol)
        self._side.set(opportunity.direction if opportunity.tradable else 0)

        key, _tone = TIER_TONE[evidence.tier]
        self._tier.setText(t(key))
        self._tier.setStyleSheet(
            f"color: {PALETTE.good if evidence.tier == EvidenceTier.MEASURED else PALETTE.ink_faint};"
            f" font-size: {TYPE.micro}px; font-weight: 700; letter-spacing: 0.7px;"
        )

        self._set_rate(evidence, config)
        self._set_reward_risk(opportunity)
        self._set_edge(evidence)

        if opportunity.blocked_reason:
            self._status.setText(code_text(opportunity.blocked_reason))
            self._status.setStyleSheet(f"color: {PALETTE.ink_faint};")
        else:
            self._status.setText(t(PROVENANCE_KEY[evidence.provenance]))
            self._status.setStyleSheet(f"color: {PALETTE.ink_muted};")

    def _set_rate(self, evidence, config: AppConfig) -> None:
        if evidence.tier == EvidenceTier.MEASURED:
            self._rate_value.setText(_rate(evidence.point))
            self._rate_value.setStyleSheet(f"color: {PALETTE.ink};")
            self._rate_caption.setText(
                t("scan.interval", low=_rate(evidence.low), high=_rate(evidence.high))
            )
            self._rate_value.setToolTip(
                t("scan.tier.measured.tip", count=fmt_count(evidence.total))
            )
        elif evidence.tier == EvidenceTier.PROVISIONAL:
            # Interval only. Withholding the point estimate is the whole point
            # of this branch: at n=9 it would be read as precision.
            self._rate_value.setText(
                f"{_rate(evidence.low)}–{_rate(evidence.high)}"
            )
            self._rate_value.setStyleSheet(
                f"color: {PALETTE.ink_muted}; font-size: {TYPE.body}px;"
            )
            self._rate_caption.setText(t("scan.sample", count=fmt_count(evidence.total)))
            self._rate_value.setToolTip(
                t("scan.tier.provisional.tip", count=fmt_count(evidence.total))
            )
        else:
            self._rate_value.setText(
                t("scan.score", score=fmt_count(int(round(evidence.rule_score))))
            )
            self._rate_value.setStyleSheet(
                f"color: {score_ramp(evidence.rule_score, config.scoring.score_threshold)};"
                f" font-size: {TYPE.body}px;"
            )
            self._rate_caption.setText(t("scan.score.note"))
            self._rate_value.setToolTip(
                t(
                    "scan.tier.unmeasured.tip",
                    floor=fmt_count(config.statistics.min_outcome_sample),
                )
            )

    def _set_reward_risk(self, opportunity: Opportunity) -> None:
        if opportunity.reward_risk > 0.0:
            self._rr_value.setText(f"{opportunity.reward_risk:.1f}")
            self._rr_value.setStyleSheet(f"color: {PALETTE.ink};")
            self._rr_caption.setText(
                t("scan.breakeven", rate=_rate(opportunity.evidence.breakeven))
            )
        else:
            self._rr_value.setText(t("common.none"))
            self._rr_value.setStyleSheet(f"color: {PALETTE.ink_faint};")
            self._rr_caption.setText("")

    def _set_edge(self, evidence) -> None:
        """Expectancy from the *conservative* bound, or nothing at all.

        Shown only at MEASURED. An expectancy computed from a rule score would
        be a probability claim wearing a different unit, which is precisely the
        substitution this whole module exists to prevent.
        """
        if evidence.tier != EvidenceTier.MEASURED:
            self._edge_value.setText(t("common.none"))
            self._edge_value.setStyleSheet(f"color: {PALETTE.ink_faint};")
            self._edge_caption.setText("")
            return

        value = evidence.expectancy_low_r
        self._edge_value.setText(f"{value:+.2f}R")
        self._edge_value.setStyleSheet(
            f"color: {PALETTE.good if value > 0 else PALETTE.critical};"
        )
        self._edge_caption.setText(t("scan.prov." + evidence.provenance.name.lower()))

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt naming
        self.clicked.emit(self.symbol)
        super().mousePressEvent(event)


class ScannerView(QWidget):
    """Ranked opportunities, with the selected one drawn beside them."""

    symbol_activated = Signal(str)

    def __init__(self, config: AppConfig, parent=None):
        super().__init__(parent)
        self._config = config
        self._rows: dict[str, OpportunityRow] = {}
        self._opportunities: dict[str, Opportunity] = {}
        self._selected = ""
        self._filter = "all"
        # Held so the detail panel can draw structure without asking the engine
        # again — the snapshot already carried it across the thread boundary.
        self._views: dict[str, object] = {}

        outer = QVBoxLayout(self)
        outer.setContentsMargins(SPACE.xl, SPACE.lg, SPACE.xl, SPACE.lg)
        outer.setSpacing(SPACE.md)

        outer.addLayout(self._build_toolbar())

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._build_list())
        splitter.addWidget(self._build_detail())
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([760, 560])
        outer.addWidget(splitter, 1)

    # --------------------------------------------------------------- toolbar
    def _build_toolbar(self) -> QHBoxLayout:
        bar = QHBoxLayout()
        bar.setSpacing(SPACE.xs)

        segmented = QFrame()
        segmented.setStyleSheet(
            f"background: {PALETTE.surface}; border: 1px solid {PALETTE.border};"
            f" border-radius: {RADIUS_PILL}px;"
        )
        inner = QHBoxLayout(segmented)
        inner.setContentsMargins(3, 3, 3, 3)
        inner.setSpacing(2)

        self._filters = QButtonGroup(self)
        self._filters.setExclusive(True)
        for index, (name, key) in enumerate(
            (("all", "scan.filter.all"), ("tradable", "scan.filter.tradable"),
             ("measured", "scan.filter.measured"))
        ):
            button = QPushButton(t(key))
            button.setObjectName("Quiet")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _=False, n=name: self._set_filter(n))
            self._filters.addButton(button, index)
            inner.addWidget(button)
        self._filters.button(0).setChecked(True)

        bar.addWidget(segmented)
        bar.addStretch(1)

        self._count = label("", "Caption")
        self._actionable = label("", "Caption")
        self._actionable.setStyleSheet(f"color: {PALETTE.good}; font-weight: 600;")
        bar.addWidget(self._actionable)
        bar.addSpacing(SPACE.md)
        bar.addWidget(self._count)
        return bar

    def _set_filter(self, name: str) -> None:
        self._filter = name
        self._relayout()

    # ------------------------------------------------------------------ list
    def _build_list(self) -> QWidget:
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        holder = QWidget()
        # The scroll area is transparent, but its *viewport child* is not — Qt
        # paints that one from the default palette, which shows up as a pale
        # slab under the last row in dark mode. Naming it gives the stylesheet
        # something to bind to.
        holder.setObjectName("Content")
        self._list = QVBoxLayout(holder)
        self._list.setContentsMargins(0, 0, SPACE.sm, 0)
        self._list.setSpacing(SPACE.sm)

        self._empty = EmptyState("◎", t("scan.empty.title"), t("scan.empty.body"))
        self._list.addWidget(self._empty)
        self._list.addStretch(1)

        self._scroll.setWidget(holder)
        return self._scroll

    # ---------------------------------------------------------------- detail
    def _build_detail(self) -> QWidget:
        panel = QWidget()
        column = QVBoxLayout(panel)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(SPACE.md)

        verdict = Card()
        self._verdict_title = label(t("scan.detail.empty"), "H2")
        self._verdict_title.setWordWrap(True)
        self._verdict_body = label("", "Body")
        self._verdict_body.setWordWrap(True)
        verdict.add(self._verdict_title)
        verdict.add(self._verdict_body)
        column.addWidget(verdict)

        chart_card = Card()
        self._chart = PriceChart()
        chart_card.add(self._chart, 1)
        column.addWidget(chart_card, 1)

        plan = Card(t("scan.plan"))
        self._plan = KeyValue(key_width=96)
        for key in ("scan.entry", "scan.stop", "scan.target"):
            self._plan.row(t(key))
        self._plan.row(t("scan.col.rr"))
        plan.add(self._plan)
        self._open = QPushButton(t("scan.open"))
        self._open.setObjectName("Ghost")
        self._open.clicked.connect(
            lambda: self._selected and self.symbol_activated.emit(self._selected)
        )
        plan.add(self._open)
        column.addWidget(plan)

        return panel

    # ----------------------------------------------------------------- update
    def update_snapshot(self, snapshot, repositories=None) -> None:
        """Rebuild the ranking from a fresh engine snapshot.

        The ranking itself lives in ``app.scanner``; this method only renders
        what that returns. Keeping the ordering out of the widget is what makes
        it testable without a display server.
        """
        ranked = scanner_app.build(snapshot, self._config, repositories)
        self._opportunities = {o.symbol: o for o in ranked}
        self._views = {view.symbol or view.requested: view for view in snapshot.symbols}
        self._order = [o.symbol for o in ranked]

        for opportunity in ranked:
            row = self._rows.get(opportunity.symbol)
            if row is None:
                row = OpportunityRow(opportunity.symbol)
                row.clicked.connect(self.select)
                self._rows[opportunity.symbol] = row
                self._list.insertWidget(self._list.count() - 1, row)
            row.update_from(opportunity, self._config)

        self._actionable.setText(
            t("scan.actionable", count=fmt_count(len(scanner_app.actionable(ranked))))
        )

        # Select the top row on the first snapshot so the chart is never empty
        # on a screen whose entire purpose is to be looked at immediately.
        if not self._selected and self._order:
            self.select(self._order[0])

        self._relayout()
        if self._selected:
            self._render_detail(self._selected)

    def _visible(self) -> list[str]:
        symbols = getattr(self, "_order", [])
        if self._filter == "tradable":
            return [s for s in symbols if self._opportunities[s].tradable]
        if self._filter == "measured":
            return [
                s
                for s in symbols
                if self._opportunities[s].evidence.tier == EvidenceTier.MEASURED
            ]
        return list(symbols)

    def _relayout(self) -> None:
        """Reorder the rows in place and apply the filter.

        Widgets are moved rather than rebuilt: ``insertWidget`` on a widget the
        layout already owns reparents it to the new index, so a re-sort costs
        pointer moves instead of a few hundred label constructions per second.
        """
        visible = self._visible()
        shown = set(visible)

        for index, symbol in enumerate(visible):
            row = self._rows.get(symbol)
            if row is not None:
                self._list.insertWidget(index, row)
                row.setVisible(True)
                row.set_selected(symbol == self._selected)

        for symbol, row in self._rows.items():
            if symbol not in shown:
                row.setVisible(False)

        self._empty.setVisible(not visible)
        self._count.setText(
            t(
                "scan.count",
                shown=fmt_count(len(visible)),
                total=fmt_count(len(self._rows)),
            )
        )

    # ----------------------------------------------------------------- detail
    def select(self, symbol: str) -> None:
        if symbol not in self._opportunities:
            return
        self._selected = symbol
        for name, row in self._rows.items():
            row.set_selected(name == symbol)
        self._render_detail(symbol)

    def _render_detail(self, symbol: str) -> None:
        opportunity = self._opportunities.get(symbol)
        if opportunity is None:
            return

        self._render_verdict(opportunity)

        view = self._views.get(symbol)
        bars = list(getattr(view, "bars", []) or [])
        zones = list(getattr(view, "zones", []) or [])
        self._chart.set(
            bars,
            zones,
            TradeLevels(
                entry=opportunity.entry,
                stop=opportunity.stop_loss,
                target=opportunity.take_profit,
                direction=opportunity.direction,
            ),
            digits=opportunity.digits,
            title=symbol,
        )

        digits = opportunity.digits
        for key, value in (
            ("scan.entry", opportunity.entry),
            ("scan.stop", opportunity.stop_loss),
            ("scan.target", opportunity.take_profit),
        ):
            self._plan.set(
                t(key),
                fmt_price(value, digits) if value > 0 else t("common.none"),
            )
        self._plan.set(
            t("scan.col.rr"),
            f"{opportunity.reward_risk:.2f}"
            if opportunity.reward_risk > 0
            else t("common.none"),
        )
        self._open.setEnabled(True)

    def _render_verdict(self, opportunity: Opportunity) -> None:
        """Four outcomes, and each one says what to do about it.

        A verdict panel that only restates the numbers above it is wasted
        space. The distinction that matters is whether the conservative bound
        clears break-even, because that is the difference between a setup
        backed by evidence and one that merely passed a gate.
        """
        evidence = opportunity.evidence

        if opportunity.blocked_reason:
            title, tone = t("scan.verdict.blocked"), PALETTE.ink_muted
            body = t(
                "scan.verdict.blocked.body",
                reason=code_text(opportunity.blocked_reason),
            )
        elif evidence.tier != EvidenceTier.MEASURED:
            title, tone = t("scan.verdict.watch"), PALETTE.ink
            body = t("scan.verdict.watch.body")
        elif evidence.clears_breakeven:
            title, tone = t("scan.verdict.take"), PALETTE.good
            body = t(
                "scan.verdict.take.body",
                low=_rate(evidence.low),
                breakeven=_rate(evidence.breakeven),
                edge=f"{evidence.expectancy_low_r:+.2f}",
            )
        else:
            title, tone = t("scan.verdict.thin"), PALETTE.warning
            body = t(
                "scan.verdict.thin.body",
                low=_rate(evidence.low),
                breakeven=_rate(evidence.breakeven),
            )

        self._verdict_title.setText(f"{opportunity.symbol} · {title}")
        self._verdict_title.setStyleSheet(f"color: {tone};")
        self._verdict_body.setText(body)
