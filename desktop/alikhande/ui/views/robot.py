"""Robot view — the automation, and the line it does not cross.

Two halves, and the order matters.

The top half is **what the robot is doing right now**: its state, which session
window it is in or waiting for, why it is holding if it is holding, and a live
feed of the actions it took on the last pass. Unattended software has one
recurring credibility problem — a screen showing nothing changing is
indistinguishable from a process that died twenty minutes ago — and the action
feed is the cheapest honest answer to it.

The bottom half is **what it is allowed to do**, stated as a list rather than
buried in a settings page. Every capability appears, including the one that is
locked, because a reader who sees five permissions and no mention of execution
has to guess whether unattended trading is off, absent, or somewhere else in
the app. It is off, it is here, and it says so.

## Why the lock gets its own card rather than a greyed-out checkbox

A disabled checkbox reads as "not now" — as something a setting elsewhere would
enable. This is not that. There is no code path that opens it, and the card
says which four refusals stand behind the decision, because an operator who
believes the robot might start trading on its own is an operator who cannot
leave it running, and that is the entire point of having one.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ...core.robot import AUTO_EXECUTE_LOCK, HoldReason, RobotPolicy, RobotState
from ...i18n import code as code_text
from ...i18n import fmt_count, t
from ..components import Card, EmptyState, KeyValue, StatusChip, label
from ..theme import PALETTE, SPACE, severity_colour

#: Robot state to (chip icon, translation key, severity). Every state has an
#: icon and a word, so the colour is never the only channel.
STATE_PRESENTATION = {
    RobotState.STOPPED: ("○", "robot.state.stopped", "unknown"),
    RobotState.IDLE: ("◷", "robot.state.idle", "unknown"),
    RobotState.WATCHING: ("✓", "robot.state.watching", "good"),
    RobotState.HOLDING: ("!", "robot.state.holding", "warning"),
    RobotState.PAUSED: ("!", "robot.state.paused", "serious"),
}


class RobotView(QWidget):
    policy_changed = Signal(object)
    resume_requested = Signal()

    def __init__(self, policy: RobotPolicy | None = None, parent=None):
        super().__init__(parent)
        self._policy = policy or RobotPolicy()
        # Set while writing widget values from a policy, so the change signals
        # those writes emit are not mistaken for the operator editing. Without
        # it, rendering a policy re-emits it, which on a view refreshed every
        # pass is a loop.
        self._loading = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
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

        root.addLayout(self._build_status())
        root.addWidget(self._build_lock())
        root.addLayout(self._build_policy())
        root.addStretch(1)

        self.render_policy(self._policy)

    # ---------------------------------------------------------------- status
    def _build_status(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(SPACE.md)

        state = Card(t("robot.status"))
        header = QHBoxLayout()
        header.setSpacing(SPACE.md)
        self._state_chip = StatusChip("○", t("robot.state.stopped"), "unknown")
        header.addWidget(self._state_chip)
        header.addStretch(1)
        self._toggle = QPushButton(t("robot.start"))
        self._toggle.setObjectName("Primary")
        self._toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self._toggle.clicked.connect(self._on_toggle)
        header.addWidget(self._toggle)
        self._resume = QPushButton(t("robot.resume"))
        self._resume.setObjectName("Ghost")
        self._resume.setCursor(Qt.CursorShape.PointingHandCursor)
        self._resume.clicked.connect(self.resume_requested.emit)
        self._resume.setVisible(False)
        header.addWidget(self._resume)
        state.add_layout(header)

        self._detail = label("", "Body")
        self._detail.setWordWrap(True)
        state.add(self._detail)

        self._fields = KeyValue(160)
        for key in (
            "robot.field.window",
            "robot.field.next",
            "robot.field.candidates",
            "robot.field.backup",
        ):
            self._fields.row(t(key))
        state.add(self._fields)
        state.body().addStretch(1)
        row.addWidget(state, 3)

        actions = Card(t("robot.actions"))
        self._actions_empty = EmptyState(
            "◷", t("robot.actions.empty.title"), t("robot.actions.empty.body")
        )
        actions.add(self._actions_empty)
        self._actions = label("", "Mono")
        self._actions.setWordWrap(True)
        self._actions.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._actions.setVisible(False)
        actions.add(self._actions, 1)
        row.addWidget(actions, 2)
        return row

    # ------------------------------------------------------------------ lock
    def _build_lock(self) -> QWidget:
        card = Card(t("robot.lock.title"))
        headline = QHBoxLayout()
        headline.setSpacing(SPACE.md)
        headline.addWidget(StatusChip("✕", code_text(AUTO_EXECUTE_LOCK), "critical"))
        headline.addStretch(1)
        card.add_layout(headline)

        body = label(t("robot.lock.body"), "Body")
        body.setWordWrap(True)
        card.add(body)

        # The four refusals, named. An operator deciding whether to leave this
        # running overnight is entitled to see the list rather than a promise.
        for key in (
            "robot.lock.reason.1",
            "robot.lock.reason.2",
            "robot.lock.reason.3",
            "robot.lock.reason.4",
        ):
            line = label(f"·  {t(key)}", "Caption")
            line.setWordWrap(True)
            card.add(line)
        return card

    # ---------------------------------------------------------------- policy
    def _build_policy(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(SPACE.md)

        permissions = Card(t("robot.permissions"))
        self._checks: dict[str, QCheckBox] = {}
        for field, key in (
            ("auto_reconnect", "robot.perm.reconnect"),
            ("auto_disarm", "robot.perm.disarm"),
            ("auto_pause_on_guard", "robot.perm.pause_guard"),
            ("auto_pause_on_degradation", "robot.perm.pause_degraded"),
            ("auto_backup", "robot.perm.backup"),
        ):
            box = QCheckBox(t(key))
            box.stateChanged.connect(self._on_edited)
            self._checks[field] = box
            permissions.add(box)

        interval = QHBoxLayout()
        interval.setSpacing(SPACE.sm)
        interval.addWidget(label(t("robot.perm.backup_every"), "Caption"))
        self._backup_hours = QSpinBox()
        self._backup_hours.setRange(1, 168)
        self._backup_hours.setSuffix(f" {t('robot.hours')}")
        self._backup_hours.valueChanged.connect(self._on_edited)
        interval.addWidget(self._backup_hours)
        interval.addStretch(1)
        permissions.add_layout(interval)
        permissions.body().addStretch(1)
        row.addWidget(permissions, 1)

        windows = Card(t("robot.windows"))
        self._windows = KeyValue(150)
        windows.add(self._windows)
        note = label(t("robot.windows.note"), "Caption")
        note.setWordWrap(True)
        windows.add(note)
        windows.body().addStretch(1)
        row.addWidget(windows, 1)
        return row

    # ----------------------------------------------------------------- edits
    def _on_toggle(self) -> None:
        from dataclasses import replace

        self._emit(replace(self._policy, enabled=not self._policy.enabled))

    def _on_edited(self) -> None:
        if self._loading:
            return
        from dataclasses import replace

        self._emit(
            replace(
                self._policy,
                **{field: box.isChecked() for field, box in self._checks.items()},
                backup_interval_hours=self._backup_hours.value(),
            )
        )

    def _emit(self, policy: RobotPolicy) -> None:
        self._policy = policy
        self.render_policy(policy)
        self.policy_changed.emit(policy)

    # --------------------------------------------------------------- render
    def render_policy(self, policy: RobotPolicy) -> None:
        self._loading = True
        try:
            self._policy = policy
            for field, box in self._checks.items():
                box.setChecked(bool(getattr(policy, field)))
            self._backup_hours.setValue(policy.backup_interval_hours)
            self._toggle.setText(t("robot.stop") if policy.enabled else t("robot.start"))

            self._windows.clear()
            for window in policy.windows:
                start = f"{window.start_minute // 60:02d}:{window.start_minute % 60:02d}"
                end = f"{window.end_minute // 60:02d}:{window.end_minute % 60:02d}"
                enabled = window.enabled
                value = f"{start} – {end}" if enabled else t("robot.window.off")
                # Times are data and align down the column; "off" is a word.
                self._windows.row(
                    t(f"robot.window.{window.name}"), value, mono=enabled
                )
        finally:
            self._loading = False

    def update_view(self, status) -> None:
        """Render a :class:`RobotStatus` from the last pass."""
        icon, key, severity = STATE_PRESENTATION.get(
            status.state, ("?", "robot.state.stopped", "unknown")
        )
        self._state_chip.set(icon, t(key), severity)

        if status.hold != HoldReason.NONE:
            self._detail.setText(t("robot.holding", reason=code_text(status.hold.name)))
            self._detail.setStyleSheet(f"color: {severity_colour(severity)};")
        elif status.state == RobotState.WATCHING:
            self._detail.setText(t("robot.watching"))
            self._detail.setStyleSheet(f"color: {PALETTE.ink_secondary};")
        else:
            self._detail.setText(t("robot.idle"))
            self._detail.setStyleSheet(f"color: {PALETTE.ink_muted};")

        self._resume.setVisible(status.state == RobotState.PAUSED)

        self._fields.set(
            t("robot.field.window"),
            t(f"robot.window.{status.window}") if status.window else "—",
        )
        self._fields.set(
            t("robot.field.next"),
            t(
                "robot.next_in",
                window=t(f"robot.window.{status.next_window}"),
                minutes=fmt_count(status.next_window_in),
            )
            if status.next_window
            else "—",
        )
        self._fields.set(t("robot.field.candidates"), fmt_count(status.candidates))
        self._fields.set(
            t("robot.field.backup"),
            t("robot.backup.taken") if status.last_backup_at else t("robot.backup.never"),
        )

        has_actions = bool(status.actions)
        self._actions_empty.setVisible(not has_actions)
        self._actions.setVisible(has_actions)
        if has_actions:
            self._actions.setText("\n".join(f"·  {code_text(a)}" for a in status.actions))
