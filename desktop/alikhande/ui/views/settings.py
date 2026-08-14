"""Presets, thresholds and appearance.

Three presets, and the screen changes shape between them rather than greying
out a few fields: Default and Auto show their values as *read-only facts about
what the preset decided*, Manual makes them editable. The difference is worth
the extra branch — a spinbox that is enabled but ignored is the worst of both,
and one that is disabled with no explanation reads as a bug.

The clamping that keeps a value inside its policy floor lives in
``alikhande.profiles``, not here. The spinbox ranges below are a courtesy to
whoever is typing; the enforcement happens where the config is built, so a
hand-edited preferences file is clamped the same way a mouse-driven change is.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ...config import AppConfig
from ...i18n import t
from ...profiles import Overrides, Profile, resolve
from ..components import Card, label
from ..theme import PALETTE, RADIUS_PILL, SPACE, THEMES

PROFILE_ORDER = (Profile.DEFAULT, Profile.AUTO, Profile.MANUAL)


class SettingsView(QWidget):
    """Reads and writes the preset; the window owns applying it."""

    changed = Signal()  # preset or override values moved
    theme_changed = Signal(str)

    def __init__(
        self,
        config: AppConfig,
        profile: Profile,
        overrides: Overrides,
        theme: str,
        summary: dict | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self._config = config
        self._profile = profile
        self._overrides = overrides
        self._summary = summary or {}
        self._loading = False

        column = QVBoxLayout(self)
        column.setContentsMargins(SPACE.xl, SPACE.lg, SPACE.xl, SPACE.lg)
        column.setSpacing(SPACE.md)

        column.addWidget(self._build_profile_card())
        column.addWidget(self._build_thresholds_card())
        column.addWidget(self._build_appearance_card(theme))
        column.addStretch(1)

        self._load()

    # --------------------------------------------------------------- presets
    def _build_profile_card(self) -> QWidget:
        card = Card(t("set.profile"))

        segmented = QFrame()
        segmented.setStyleSheet(
            f"background: {PALETTE.surface_high}; border: 1px solid {PALETTE.border};"
            f" border-radius: {RADIUS_PILL}px;"
        )
        inner = QHBoxLayout(segmented)
        inner.setContentsMargins(3, 3, 3, 3)
        inner.setSpacing(2)

        self._profiles = QButtonGroup(self)
        self._profiles.setExclusive(True)
        for index, profile in enumerate(PROFILE_ORDER):
            button = QPushButton(t(f"set.profile.{profile.value}"))
            button.setObjectName("Quiet")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _=False, p=profile: self._choose(p))
            self._profiles.addButton(button, index)
            inner.addWidget(button)

        holder = QHBoxLayout()
        holder.addWidget(segmented)
        holder.addStretch(1)
        card.add_layout(holder)

        self._profile_body = label("", "Body")
        self._profile_body.setWordWrap(True)
        card.add(self._profile_body)
        return card

    def _choose(self, profile: Profile) -> None:
        self._profile = profile
        self._load()
        self.changed.emit()

    # ------------------------------------------------------------ thresholds
    def _build_thresholds_card(self) -> QWidget:
        card = Card(t("set.thresholds"))

        self._score = QDoubleSpinBox()
        self._score.setRange(50.0, 100.0)
        self._score.setSingleStep(1.0)
        self._score.setDecimals(0)

        self._reward_risk = QDoubleSpinBox()
        # The lower bound *is* the policy floor. A spinbox that cannot be
        # dialled below it is clearer than one that can, and then silently
        # snaps back on apply.
        self._reward_risk.setRange(self._config.risk.minimum_risk_reward, 10.0)
        self._reward_risk.setSingleStep(0.1)
        self._reward_risk.setDecimals(2)

        self._risk = QDoubleSpinBox()
        self._risk.setRange(0.01, self._config.risk.maximum_risk_percent)
        self._risk.setSingleStep(0.05)
        self._risk.setDecimals(2)
        self._risk.setSuffix(" %")

        self._sample = QSpinBox()
        self._sample.setRange(self._config.statistics.min_outcome_sample, 500)
        self._sample.setSingleStep(10)

        for key, widget in (
            ("set.score_threshold", self._score),
            ("set.min_rr", self._reward_risk),
            ("set.risk_percent", self._risk),
            ("set.min_sample", self._sample),
        ):
            row = QHBoxLayout()
            row.setSpacing(SPACE.md)
            row.addWidget(label(t(key), "Body"), 1)
            widget.setFixedWidth(140)
            widget.valueChanged.connect(self._on_edit)
            row.addWidget(widget)
            card.add_layout(row)

        self._threshold_note = label("", "Caption")
        self._threshold_note.setWordWrap(True)
        card.add(self._threshold_note)

        self._reset = QPushButton(t("set.reset"))
        self._reset.setObjectName("Ghost")
        self._reset.clicked.connect(self._reset_to_default)
        reset_row = QHBoxLayout()
        reset_row.addStretch(1)
        reset_row.addWidget(self._reset)
        card.add_layout(reset_row)
        return card

    def _reset_to_default(self) -> None:
        self._overrides = Overrides()
        self._profile = Profile.DEFAULT
        self._load()
        self.changed.emit()

    def _on_edit(self) -> None:
        """Only Manual writes back. Auto's spinboxes show its decision."""
        if self._loading or self._profile is not Profile.MANUAL:
            return
        self._overrides = Overrides(
            score_threshold=self._score.value(),
            minimum_risk_reward=self._reward_risk.value(),
            risk_percent=self._risk.value(),
            min_outcome_sample=self._sample.value(),
        )
        self.changed.emit()

    # ------------------------------------------------------------ appearance
    def _build_appearance_card(self, theme: str) -> QWidget:
        card = Card(t("set.appearance"))

        segmented = QFrame()
        segmented.setStyleSheet(
            f"background: {PALETTE.surface_high}; border: 1px solid {PALETTE.border};"
            f" border-radius: {RADIUS_PILL}px;"
        )
        inner = QHBoxLayout(segmented)
        inner.setContentsMargins(3, 3, 3, 3)
        inner.setSpacing(2)

        self._themes = QButtonGroup(self)
        self._themes.setExclusive(True)
        for index, name in enumerate(THEMES):
            button = QPushButton(t(f"set.theme.{name}"))
            button.setObjectName("Quiet")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setChecked(name == theme)
            button.clicked.connect(lambda _=False, n=name: self.theme_changed.emit(n))
            self._themes.addButton(button, index)
            inner.addWidget(button)

        row = QHBoxLayout()
        row.addWidget(label(t("set.theme"), "Body"), 1)
        row.addWidget(segmented)
        card.add_layout(row)
        return card

    # ------------------------------------------------------------------ state
    def _load(self) -> None:
        """Push the current preset's values into the widgets.

        ``_loading`` suppresses the change signals the assignments would
        otherwise raise — without it, selecting Auto writes Auto's computed
        values back as if the operator had typed them, and the next switch to
        Manual inherits them silently.
        """
        self._loading = True
        try:
            values = resolve(self._profile, self._overrides, self._summary)
            self._score.setValue(values.score_threshold)
            self._reward_risk.setValue(values.minimum_risk_reward)
            self._risk.setValue(values.risk_percent)
            self._sample.setValue(values.min_outcome_sample)

            editable = self._profile is Profile.MANUAL
            for widget in (self._score, self._reward_risk, self._risk, self._sample):
                widget.setEnabled(editable)

            index = PROFILE_ORDER.index(self._profile)
            self._profiles.button(index).setChecked(True)
            self._profile_body.setText(t(f"set.profile.{self._profile.value}.body"))
            self._threshold_note.setText(
                "" if editable else t("set.auto.note")
            )
        finally:
            self._loading = False

    def profile(self) -> Profile:
        return self._profile

    def overrides(self) -> Overrides:
        return self._overrides
