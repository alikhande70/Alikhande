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

from ...core.enums import (
    DIRECTION_NAMES,
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

WATCH_HEADERS = ["Symbol", "Trend", "Bias", "Score", "Structure", "Spread", "State"]


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
        self._ring.set(max(signal.long_score, signal.short_score), "rule score")

        self._levels.setText(
            f"entry {signal.preferred_entry:.{digits}f}    "
            f"stop {signal.stop_loss:.{digits}f}    "
            f"target {signal.take_profit:.{digits}f}"
        )

        components = signal.components[:3]
        self._why.setText(
            "Top contributors: "
            + ", ".join(f"{c.component.replace('_', ' ').lower()} {c.contribution:+.0f}" for c in components)
            if components
            else "No score breakdown available."
        )

        relation = (
            signal.demand_relation
            if signal.direction == Direction.LONG
            else signal.supply_relation
        )
        inside = relation.name == "INSIDE"
        self._chip_zone.set(
            "◈" if inside else "◇",
            f"ZONE {relation.name}",
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
            self._size.setText(f"{plan.lot_size:.2f} lots")
            self._risk.setText(
                f"risk {plan.actual_risk_amount:,.2f} ({plan.risk_percent:.2f}%)"
            )
            self._rr.setText(
                f"R:R 1 : {reward / risk_distance:.2f}" if risk_distance > 0 else ""
            )
        else:
            codes = plan.codes_text() if plan is not None else "not sized"
            self._size.setText("not sized")
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
        self._verdict = label("Starting up", "H1")
        self._verdict_detail = label("", "Body")
        self._verdict_detail.setWordWrap(True)
        headline.addWidget(self._verdict)
        headline.addWidget(self._verdict_detail)
        verdict_row.addLayout(headline, 1)

        self._verdict_chips = QHBoxLayout()
        self._verdict_chips.setSpacing(SPACE.sm)
        self._chip_mode = StatusChip("◆", "ALERT ONLY", "neutral")
        self._chip_guards = StatusChip("✓", "GUARDS OK", "good")
        self._verdict_chips.addWidget(self._chip_mode)
        self._verdict_chips.addWidget(self._chip_guards)
        verdict_row.addLayout(self._verdict_chips)

        verdict.add_layout(verdict_row)
        root.addWidget(verdict)

        # ---- tier 1b: the four numbers that matter ---------------------------
        tiles = QHBoxLayout()
        tiles.setSpacing(SPACE.md)
        self._tile_actionable = StatTile("Actionable", "0", "qualified with a sized plan")
        self._tile_watching = StatTile("Watching", "0", "symbols resolved and scanning")
        self._tile_risk = StatTile("Open risk", "0.00%", "aggregate, opened by this app")
        self._tile_evidence = StatTile("Evidence", "0", "outcomes recorded so far")
        for tile in (
            self._tile_actionable,
            self._tile_watching,
            self._tile_risk,
            self._tile_evidence,
        ):
            tiles.addWidget(tile)
        root.addLayout(tiles)

        # ---- tier 2: signal cards --------------------------------------------
        root.addWidget(label("OPPORTUNITIES", "CardTitle"))

        self._card_host = QWidget()
        self._card_layout = QVBoxLayout(self._card_host)
        self._card_layout.setContentsMargins(0, 0, 0, 0)
        self._card_layout.setSpacing(SPACE.md)
        root.addWidget(self._card_host)

        self._empty = EmptyState("◎", "Nothing actionable", "")
        self._empty_card = Card()
        self._empty_card.add(self._empty)
        root.addWidget(self._empty_card)

        # ---- tier 3: the watchlist -------------------------------------------
        watch = Card("Watchlist")
        self._table = QTableWidget(0, len(WATCH_HEADERS))
        self._table.setHorizontalHeaderLabels(WATCH_HEADERS)
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
            names = ", ".join(v.symbol for v in actionable[:4])
            self._verdict.setText(
                f"{len(actionable)} setup{'s' if len(actionable) > 1 else ''} ready"
            )
            self._verdict.setStyleSheet(f"color: {PALETTE.ink};")
            self._verdict_detail.setText(
                f"{names} qualified and sized. Open one to see the structure it is "
                "built on before doing anything with it."
            )
        elif not resolved:
            self._verdict.setText("No symbols resolved")
            self._verdict.setStyleSheet(f"color: {PALETTE.critical};")
            self._verdict_detail.setText(
                "None of the configured symbols matched a name on this broker. "
                "Check Market Watch in MetaTrader."
            )
        elif warming:
            self._verdict.setText("Warming up")
            self._verdict.setStyleSheet(f"color: {PALETTE.ink};")
            self._verdict_detail.setText(
                f"{len(warming)} of {len(resolved)} symbols still gathering the spread "
                "and history they need before anything can be scored. This is normal "
                "for the first minute or two."
            )
        else:
            self._verdict.setText("Nothing actionable")
            self._verdict.setStyleSheet(f"color: {PALETTE.ink};")
            self._verdict_detail.setText(
                f"All {len(resolved)} symbols scanned; none currently meet the "
                f"{self._threshold:.0f}-point threshold with a confirmed setup at a "
                "structural zone. That is the normal state most of the time."
            )

        self._chip_mode.set("◆", snapshot.mode.name.replace("_", " "), "neutral")

        if snapshot.requires_manual_review:
            self._chip_guards.set("✕", "REVIEW REQUIRED", "critical")
        elif not snapshot.may_trade:
            self._chip_guards.set("✕", "HALTED", "critical")
        elif snapshot.news_blind:
            self._chip_guards.set("!", "NEWS-BLIND", "warning")
        else:
            self._chip_guards.set("✓", "GUARDS OK", "good")

    def _render_tiles(self, snapshot, resolved, actionable, evidence_count: int) -> None:
        self._tile_actionable.set(
            str(len(actionable)),
            "qualified with a sized plan",
            PALETTE.accent if actionable else None,
        )
        self._tile_watching.set(
            f"{len(resolved)}",
            f"of {len(snapshot.symbols)} configured symbols",
        )

        cap = self._config.risk.max_open_risk_pct
        self._tile_risk.set(
            f"{snapshot.exposure_open_pct:.2f}%",
            f"cap {cap:.2f}%",
            PALETTE.critical if snapshot.exposure_open_pct > cap else None,
        )

        floor = self._config.statistics.min_outcome_sample
        if evidence_count == 0:
            self._tile_evidence.set("0", "no outcomes recorded yet", PALETTE.ink_muted)
        elif evidence_count < floor:
            self._tile_evidence.set(
                str(evidence_count), f"{evidence_count}/{floor} before any win rate shows"
            )
        else:
            self._tile_evidence.set(str(evidence_count), "outcomes recorded")

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
            self._empty.set(
                "◎",
                "Nothing actionable right now",
                "A setup appears here only when a confirmed structure, a clear "
                "spread and a sized plan all line up. Refusals are shown per "
                "symbol on the Signal view — the scanner is working when this "
                "space is empty.",
            )

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
                self._cell(row, 6, "unresolved on this broker", PALETTE.critical)
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
                self._cell(row, 6, view.last_error or "building structure", PALETTE.ink_muted)
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
                f"{score:.0f}",
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
                relation.name.lower(),
                PALETTE.accent if relation.name == "INSIDE" else PALETTE.ink_muted,
            )
            self._cell(
                row,
                5,
                f"{view.snapshot.spread_points:.1f} pts",
                PALETTE.ink_secondary,
                mono=True,
                right=True,
            )

            if signal.hard_blocked and signal.validation_codes:
                text = signal.validation_codes[0].split("(")[0].replace("_", " ").lower()
                self._cell(row, 6, text, PALETTE.ink_muted)
            elif view.plan is not None and view.plan.valid:
                self._cell(row, 6, "plan ready", PALETTE.good)
            else:
                self._cell(row, 6, "watching", PALETTE.ink_muted)

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
