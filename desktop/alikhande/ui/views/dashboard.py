"""Dashboard — the view that answers "what should I do right now?".

The v1 Overview was a fourteen-column table. Every field was present and every
field had the same visual weight, so finding out that nothing was actionable
meant reading fourteen columns across eight rows. That is a spreadsheet, not an
interface.

This is built the other way round, in three tiers of decreasing urgency:

1. **The verdict.** One sentence and one number. If nothing is actionable, that
   is the headline, stated plainly, with the reason.
2. **Signal cards.** Only for setups that actually qualified. Each is a
   self-contained decision: direction, score, the levels, the R:R, and one line
   saying why. If there are none, an empty state explains which kind of nothing
   it is — no setup found, or not ready yet.
3. **The watchlist.** Everything else, compact, six columns instead of fourteen,
   as a reference rather than the main event.

Anything a card cannot fit belongs on the Signal view, one click away. Detail is
not deleted; it is deferred.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...i18n import code as t_code
from ...i18n import fmt_count, fmt_money, fmt_percent, fmt_price, t
from ...i18n import zone_relation_name
from ...core.enums import (
    DIRECTION_NAMES,
    RunMode,
    SETUP_NAMES,
    Direction,
    NewsState,
    SpreadState,
)
from ..charts import Sparkline
from ..components import (
    Card,
    DirectionBadge,
    EmptyState,
    ScoreRing,
    StatTile,
    StatusChip,
    label,
    rule,
)
from ..theme import PALETTE, SPACE, TYPE

# Header keys, resolved at render time so a language switch relabels them.
WATCH_KEYS = [
    "col.symbol", "col.trend", "col.bias", "col.score",
    "col.structure", "col.spread", "col.state",
]


class SignalCard(QFrame):
    """One qualifying setup, as a single readable object."""

    activated = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("SignalCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._symbol = ""

        root = QHBoxLayout(self)
        root.setContentsMargins(SPACE.lg + 2, SPACE.lg, SPACE.lg + 2, SPACE.lg)
        root.setSpacing(SPACE.lg)

        self._ring = ScoreRing(diameter=76)
        root.addWidget(self._ring, 0, Qt.AlignmentFlag.AlignVCenter)

        middle = QVBoxLayout()
        middle.setSpacing(SPACE.sm)

        heading = QHBoxLayout()
        heading.setSpacing(SPACE.sm)
        self._name = label("", "H2")
        self._badge = DirectionBadge()
        self._setup = label("", "Caption")
        heading.addWidget(self._name)
        heading.addWidget(self._badge)
        heading.addWidget(self._setup)
        heading.addStretch(1)
        middle.addLayout(heading)

        self._levels = label("", "Mono")
        middle.addWidget(self._levels)

        self._why = label("", "Caption")
        self._why.setWordWrap(True)
        middle.addWidget(self._why)

        chips = QHBoxLayout()
        chips.setSpacing(SPACE.sm)
        self._chip_news = StatusChip("○", "NEWS", "unknown")
        self._chip_spread = StatusChip("○", "SPREAD", "neutral")
        self._chip_zone = StatusChip("◈", "ZONE", "neutral")
        for chip in (self._chip_zone, self._chip_spread, self._chip_news):
            chips.addWidget(chip)
        chips.addStretch(1)
        middle.addLayout(chips)

        root.addLayout(middle, 1)

        right = QVBoxLayout()
        right.setSpacing(2)
        right.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._size = label("", "MonoBig")
        self._size.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._risk = label("", "Caption")
        self._risk.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._rr = label("", "Caption")
        self._rr.setAlignment(Qt.AlignmentFlag.AlignRight)
        right.addWidget(self._size)
        right.addWidget(self._risk)
        right.addWidget(self._rr)
        root.addLayout(right)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt naming
        self.activated.emit(self._symbol)
        super().mouseReleaseEvent(event)

    def bind(self, view, threshold: float) -> None:
        signal = view.signal
        plan = view.plan
        self._symbol = view.symbol
        digits = view.spec.digits if view.spec else 5

        self._name.setText(view.symbol)
        self._badge.set(int(signal.direction))
        self._setup.setText(SETUP_NAMES[signal.setup])
        self._ring.set(max(signal.long_score, signal.short_score), t("col.score").lower())

        self._levels.setText(
            f'{t("plan.entry")} {fmt_price(signal.preferred_entry, digits)}    '
            f'{t("plan.stop")} {fmt_price(signal.stop_loss, digits)}    '
            f'{t("plan.target")} {fmt_price(signal.take_profit, digits)}'
        )

        components = signal.components[:3]
        if components:
            items = ", ".join(
                f"{c.component.replace('_', ' ').lower()} {c.contribution:+.0f}"
                for c in components
            )
            self._why.setText(t("card.top_contributors", items=items))
        else:
            self._why.setText(t("card.no_breakdown"))

        relation = (
            signal.demand_relation
            if signal.direction == Direction.LONG
            else signal.supply_relation
        )
        inside = relation.name == "INSIDE"
        self._chip_zone.set(
            "◈" if inside else "◇",
            zone_relation_name(relation.name).upper(),
            "good" if inside else "neutral",
        )

        spread_state = view.snapshot.spread_state
        self._chip_spread.set(
            "✓" if spread_state == SpreadState.NORMAL else "!",
            f"SPREAD {spread_state.name}",
            "good" if spread_state == SpreadState.NORMAL else "warning",
        )

        news_tone = {
            NewsState.CLEAR: ("✓", "good"),
            NewsState.BLOCKED: ("✕", "critical"),
            NewsState.UNKNOWN: ("?", "unknown"),
        }[view.news.state]
        self._chip_news.set(news_tone[0], f"NEWS {view.news.state.name}", news_tone[1])

        if plan is not None and plan.valid:
            risk_distance = abs(plan.entry - plan.stop_loss)
            reward = abs(plan.take_profit - plan.entry)
            self._size.setText(t("card.lots", lots=f"{plan.lot_size:.2f}"))
            self._risk.setText(
                t(
                    "card.risk",
                    amount=fmt_money(plan.actual_risk_amount),
                    percent=fmt_percent(plan.risk_percent),
                )
            )
            self._rr.setText(
                t("card.rr", ratio=f"{reward / risk_distance:.2f}")
                if risk_distance > 0
                else ""
            )
        else:
            codes = plan.codes_text() if plan is not None else t("card.not_sized")
            self._size.setText(t("card.not_sized"))
            self._risk.setText(codes[:44])
            self._rr.setText("")


class DashboardView(QWidget):
    symbol_activated = Signal(str)

    def __init__(self, config, statistics):
        super().__init__()
        self._config = config
        self._statistics = statistics
        self._threshold = config.scoring.score_threshold
        self._cards: list[SignalCard] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        outer.addWidget(scroll)

        page = QWidget()
        page.setObjectName("Content")
        root = QVBoxLayout(page)
        root.setContentsMargins(SPACE.xl, SPACE.lg, SPACE.xl, SPACE.xl)
        root.setSpacing(SPACE.lg)
        scroll.setWidget(page)

        # ---- tier 1: the verdict --------------------------------------------
        verdict = Card()
        verdict_row = QHBoxLayout()
        verdict_row.setSpacing(SPACE.lg)

        headline = QVBoxLayout()
        headline.setSpacing(SPACE.xs)
        self._verdict = label(t("status.starting"), "H1")
        self._verdict_detail = label("", "Body")
        self._verdict_detail.setWordWrap(True)
        headline.addWidget(self._verdict)
        headline.addWidget(self._verdict_detail)
        verdict_row.addLayout(headline, 1)

        self._verdict_chips = QHBoxLayout()
        self._verdict_chips.setSpacing(SPACE.sm)
        self._chip_mode = StatusChip("◆", t("mode.alert"), "neutral")
        self._chip_guards = StatusChip("✓", t("dash.guards.ok"), "good")
        self._verdict_chips.addWidget(self._chip_mode)
        self._verdict_chips.addWidget(self._chip_guards)
        verdict_row.addLayout(self._verdict_chips)

        verdict.add_layout(verdict_row)
        root.addWidget(verdict)

        # ---- tier 1b: the four numbers that matter ---------------------------
        tiles = QHBoxLayout()
        tiles.setSpacing(SPACE.md)
        self._tile_actionable = StatTile(t("dash.tile.actionable"), "0")
        self._tile_watching = StatTile(t("dash.tile.watching"), "0")
        self._tile_risk = StatTile(t("dash.tile.risk"), "0.00%")
        self._tile_evidence = StatTile(t("dash.tile.evidence"), "0")
        for tile in (
            self._tile_actionable,
            self._tile_watching,
            self._tile_risk,
            self._tile_evidence,
        ):
            tiles.addWidget(tile)
        root.addLayout(tiles)

        # ---- tier 2: signal cards --------------------------------------------
        root.addWidget(label(t("dash.opportunities"), "CardTitle"))

        self._card_host = QWidget()
        self._card_layout = QVBoxLayout(self._card_host)
        self._card_layout.setContentsMargins(0, 0, 0, 0)
        self._card_layout.setSpacing(SPACE.md)
        root.addWidget(self._card_host)

        self._empty = EmptyState("◎", t("dash.empty.title"), t("dash.empty.detail"))
        self._empty_card = Card()
        self._empty_card.add(self._empty)
        root.addWidget(self._empty_card)

        # ---- tier 3: the watchlist -------------------------------------------
        watch = Card(t("dash.watchlist"))
        self._table = QTableWidget(0, len(WATCH_KEYS))
        self._table.setHorizontalHeaderLabels([t(k) for k in WATCH_KEYS])
        self._table.verticalHeader().setVisible(False)
        self._table.setShowGrid(False)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.verticalHeader().setDefaultSectionSize(40)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
        )
        self._table.itemDoubleClicked.connect(self._on_row_activated)
        watch.add(self._table)
        root.addWidget(watch)
        root.addStretch(1)

    def _on_row_activated(self, item) -> None:
        cell = self._table.item(item.row(), 0)
        if cell is not None:
            self.symbol_activated.emit(cell.text())

    # ---------------------------------------------------------------- render
    def update_view(self, snapshot, evidence_count: int) -> None:
        views = snapshot.symbols
        resolved = [v for v in views if v.resolved]
        actionable = [
            v
            for v in resolved
            if v.signal is not None
            and v.plan is not None
            and v.plan.valid
            and not v.news_blocks
        ]

        self._render_verdict(snapshot, resolved, actionable)
        self._render_tiles(snapshot, resolved, actionable, evidence_count)
        self._render_cards(actionable)
        self._render_watchlist(views)

    def _render_verdict(self, snapshot, resolved, actionable) -> None:
        warming = [
            v
            for v in resolved
            if v.snapshot.spread_state == SpreadState.WARMING_UP or v.signal is None
        ]

        if actionable:
            names = "، ".join(v.symbol for v in actionable[:4])
            self._verdict.setText(
                t("dash.verdict.ready", count=fmt_count(len(actionable)))
            )
            self._verdict.setStyleSheet(f"color: {PALETTE.ink};")
            self._verdict_detail.setText(t("dash.verdict.ready.detail", names=names))
        elif not resolved:
            self._verdict.setText(t("dash.verdict.unresolved"))
            self._verdict.setStyleSheet(f"color: {PALETTE.critical};")
            self._verdict_detail.setText(t("dash.verdict.unresolved.detail"))
        elif warming:
            self._verdict.setText(t("dash.verdict.warming"))
            self._verdict.setStyleSheet(f"color: {PALETTE.ink};")
            self._verdict_detail.setText(
                t(
                    "dash.verdict.warming.detail",
                    warming=fmt_count(len(warming)),
                    total=fmt_count(len(resolved)),
                )
            )
        else:
            self._verdict.setText(t("dash.verdict.nothing"))
            self._verdict.setStyleSheet(f"color: {PALETTE.ink};")
            self._verdict_detail.setText(
                t(
                    "dash.verdict.nothing.detail",
                    total=fmt_count(len(resolved)),
                    threshold=fmt_count(int(self._threshold)),
                )
            )

        self._chip_mode.set(
            "◆",
            {
                RunMode.ALERT_ONLY: t("mode.alert"),
                RunMode.SHADOW: t("mode.shadow"),
                RunMode.DEMO_CONFIRM: t("mode.demo"),
            }.get(snapshot.mode, snapshot.mode.name),
            "neutral",
        )

        if snapshot.requires_manual_review:
            self._chip_guards.set("✕", t("dash.guards.review"), "critical")
        elif not snapshot.may_trade:
            self._chip_guards.set("✕", t("dash.guards.halted"), "critical")
        elif snapshot.news_blind:
            self._chip_guards.set("!", t("dash.guards.newsblind"), "warning")
        else:
            self._chip_guards.set("✓", t("dash.guards.ok"), "good")

    def _render_tiles(self, snapshot, resolved, actionable, evidence_count: int) -> None:
        self._tile_actionable.set(
            fmt_count(len(actionable)),
            t("dash.tile.actionable.caption"),
            PALETTE.accent if actionable else None,
        )
        self._tile_watching.set(
            fmt_count(len(resolved)),
            t("dash.tile.watching.caption", total=fmt_count(len(snapshot.symbols))),
        )

        cap = self._config.risk.max_open_risk_pct
        self._tile_risk.set(
            fmt_percent(snapshot.exposure_open_pct),
            t("dash.tile.risk.caption", cap=fmt_percent(cap)),
            PALETTE.critical if snapshot.exposure_open_pct > cap else None,
        )

        floor = self._config.statistics.min_outcome_sample
        if evidence_count == 0:
            self._tile_evidence.set(
                fmt_count(0), t("dash.tile.evidence.none"), PALETTE.ink_muted
            )
        elif evidence_count < floor:
            self._tile_evidence.set(
                fmt_count(evidence_count),
                t(
                    "dash.tile.evidence.below",
                    count=fmt_count(evidence_count),
                    floor=fmt_count(floor),
                ),
            )
        else:
            self._tile_evidence.set(
                fmt_count(evidence_count), t("dash.tile.evidence.ok")
            )

    def _render_cards(self, actionable) -> None:
        while len(self._cards) < len(actionable):
            card = SignalCard()
            card.activated.connect(self.symbol_activated)
            self._cards.append(card)
            self._card_layout.addWidget(card)

        for index, card in enumerate(self._cards):
            if index < len(actionable):
                card.bind(actionable[index], self._threshold)
                card.setVisible(True)
            else:
                card.setVisible(False)

        self._empty_card.setVisible(not actionable)
        if not actionable:
            self._empty.set("◎", t("dash.empty.title"), t("dash.empty.detail"))

    def _render_watchlist(self, views) -> None:
        self._table.setRowCount(len(views))
        for row, view in enumerate(views):
            self._table.setRowHeight(row, 40)
            self._cell(row, 0, view.symbol or view.requested, mono=True)

            if not view.resolved:
                self._cell(row, 1, "—", PALETTE.ink_faint)
                self._cell(row, 2, "—", PALETTE.ink_faint)
                self._cell(row, 3, "—", PALETTE.ink_faint)
                self._cell(row, 4, "—", PALETTE.ink_faint)
                self._cell(row, 5, "—", PALETTE.ink_faint)
                self._cell(row, 6, t("cell.unresolved"), PALETTE.critical)
                continue

            # An item left from an earlier render still paints its text beside
            # the cell widget, so the placeholder dash has to be cleared before
            # the sparkline goes in.
            self._table.setItem(row, 1, QTableWidgetItem(""))
            spark = Sparkline()
            spark.set([b.close for b in view.bars])
            self._table.setCellWidget(row, 1, spark)

            signal = view.signal
            if signal is None:
                self._cell(row, 2, "—", PALETTE.ink_faint)
                self._cell(row, 3, "—", PALETTE.ink_faint)
                self._cell(row, 4, "—", PALETTE.ink_faint)
                self._cell(row, 5, view.snapshot.spread_state.name.lower(), PALETTE.ink_muted)
                self._cell(row, 6, view.last_error or t("cell.building"), PALETTE.ink_muted)
                continue

            colour = {
                Direction.LONG: PALETTE.long,
                Direction.SHORT: PALETTE.short,
            }.get(signal.direction, PALETTE.ink_faint)
            self._cell(row, 2, DIRECTION_NAMES[signal.direction], colour)

            score = max(signal.long_score, signal.short_score)
            self._cell(
                row,
                3,
                fmt_count(int(score)),
                PALETTE.ink if score >= self._threshold else PALETTE.ink_muted,
                mono=True,
                right=True,
            )

            relation = (
                signal.demand_relation
                if signal.direction != Direction.SHORT
                else signal.supply_relation
            )
            self._cell(
                row,
                4,
                zone_relation_name(relation.name),
                PALETTE.accent if relation.name == "INSIDE" else PALETTE.ink_muted,
            )
            self._cell(
                row,
                5,
                f"{view.snapshot.spread_points:.1f}",
                PALETTE.ink_secondary,
                mono=True,
                right=True,
            )

            if signal.hard_blocked and signal.validation_codes:
                self._cell(
                    row, 6, t_code(signal.validation_codes[0]), PALETTE.ink_muted
                )
            elif view.plan is not None and view.plan.valid:
                self._cell(row, 6, t("cell.plan_ready"), PALETTE.good)
            else:
                self._cell(row, 6, t("cell.watching"), PALETTE.ink_muted)

        # Height must cover the header, every row and the frame, or the last
        # symbol in the list is silently cut in half.
        self._table.setFixedHeight(
            self._table.horizontalHeader().height() + len(views) * 40 + 14
        )
        self._table.resizeColumnsToContents()
        self._table.horizontalHeader().setStretchLastSection(True)

    def _cell(
        self,
        row: int,
        column: int,
        text: str,
        colour: str | None = None,
        mono: bool = False,
        right: bool = False,
    ) -> None:
        item = QTableWidgetItem(text)
        if colour:
            from PySide6.QtGui import QColor

            item.setForeground(QColor(colour))
        if mono:
            from PySide6.QtGui import QFont

            item.setFont(QFont(PALETTE.mono.split(",")[0].strip("'"), TYPE.small))
        if right:
            item.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
        self._table.setItem(row, column, item)
