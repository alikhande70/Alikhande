"""Animation helpers.

Motion in this application has one job: to make a change legible. A value that
jumps is a value the operator may not have noticed changed, and on a screen
whose whole purpose is that somebody notices things, that is a functional
defect rather than a missing flourish.

So every animation here is tied to a state change, none is decorative, and all
of them share one duration from :data:`theme.MOTION_MS`. An interface whose
animations disagree about their own speed reads as several interfaces.

## Three rules

**Nothing animates on first paint.** A window that fades every panel in on
launch takes half a second to become readable and looks like a marketing site.
Widgets appear instantly; only *subsequent* changes move.

**Nothing that carries a number animates the number's meaning.** The value ring
animates its arc, not its digits — the digits are set the moment the value
arrives, because an operator reading a price mid-tween is reading a number that
was never true.

**Every animation is cancellable and idempotent.** A scan pass lands every
250ms. An animation that queued rather than replaced would fall further behind
the data on every pass, and would eventually be showing a value from a minute
ago while claiming to be live.

## Why animations are parented to their widget

Qt destroys child objects with their parent. An animation left unparented
outlives the widget it drives, and fires into a deleted object — which surfaces
as a hard crash on a language switch, since that rebuilds every view while
animations from the previous one are still running.
"""

from __future__ import annotations

from PySide6.QtCore import (
    QAbstractAnimation,
    QEasingCurve,
    QObject,
    QPropertyAnimation,
    QTimer,
    QVariantAnimation,
    Signal,
)
from PySide6.QtWidgets import QGraphicsOpacityEffect, QWidget

from .theme import MOTION_MS, MOTION_SLOW_MS

#: The one curve. Decelerating: fast departure, gentle arrival, which is what
#: makes a transition feel responsive rather than sluggish at the same duration.
EASE = QEasingCurve.Type.OutCubic


def _stop(widget: QWidget, key: str) -> None:
    """Cancel any animation previously stored under ``key`` on ``widget``."""
    existing = widget.property(key)
    if isinstance(existing, QAbstractAnimation):
        existing.stop()


def fade_in(widget: QWidget, duration: int = MOTION_SLOW_MS) -> None:
    """Fade a widget up from transparent.

    Used when a view is swapped in. The effect is removed on completion rather
    than left attached — a permanent ``QGraphicsOpacityEffect`` forces Qt to
    render the whole subtree through an offscreen buffer, which visibly costs
    frames on a table of a hundred rows.
    """
    _stop(widget, "_fade")
    effect = QGraphicsOpacityEffect(widget)
    effect.setOpacity(0.0)
    widget.setGraphicsEffect(effect)

    animation = QPropertyAnimation(effect, b"opacity", widget)
    animation.setDuration(duration)
    animation.setStartValue(0.0)
    animation.setEndValue(1.0)
    animation.setEasingCurve(EASE)

    def done() -> None:
        # Guard: the widget may have been destroyed between the last frame and
        # this callback, which happens routinely on a language switch.
        try:
            widget.setGraphicsEffect(None)
        except RuntimeError:  # pragma: no cover - Qt object already gone
            pass

    animation.finished.connect(done)
    widget.setProperty("_fade", animation)
    animation.start(QAbstractAnimation.DeletionPolicy.KeepWhenStopped)


class Tween(QObject):
    """Animates a float and calls back on every frame.

    The general-purpose primitive behind the animated ring, meter and
    sparkline. Callers keep a ``Tween`` per animated quantity and call
    :meth:`to`; each call replaces the previous animation rather than queueing
    behind it.
    """

    changed = Signal(float)

    def __init__(self, parent: QWidget, start: float = 0.0, duration: int = MOTION_MS):
        super().__init__(parent)
        self._value = start
        self._duration = duration
        self._animation = QVariantAnimation(self)
        self._animation.setDuration(duration)
        self._animation.setEasingCurve(EASE)
        self._animation.valueChanged.connect(self._on_frame)
        self._first = True

    @property
    def value(self) -> float:
        return self._value

    def _on_frame(self, value) -> None:
        self._value = float(value)
        self.changed.emit(self._value)

    def to(self, target: float, *, animate: bool = True) -> None:
        target = float(target)
        if abs(target - self._value) < 1e-9:
            return
        # First arrival is not a change — it is the initial state, and animating
        # it means every panel counts up from zero on launch.
        if self._first or not animate:
            self._first = False
            self._animation.stop()
            self._value = target
            self.changed.emit(target)
            return
        self._animation.stop()
        self._animation.setStartValue(self._value)
        self._animation.setEndValue(target)
        self._animation.start()

    def set_immediately(self, value: float) -> None:
        self._animation.stop()
        self._value = float(value)
        self._first = False
        self.changed.emit(self._value)


class Pulse(QObject):
    """A slow repeating 0→1→0 ramp, for a live indicator.

    Deliberately not a blink. A hard on/off at one hertz is an alarm; a smooth
    ramp over two seconds reads as a heartbeat, which is what a "this is live"
    indicator should say. It also means the widget is never fully invisible, so
    the dot does not appear to disappear on a screenshot.
    """

    changed = Signal(float)

    def __init__(self, parent: QWidget, period_ms: int = 2000):
        super().__init__(parent)
        self._animation = QVariantAnimation(self)
        self._animation.setDuration(period_ms)
        self._animation.setStartValue(0.0)
        self._animation.setEndValue(1.0)
        self._animation.setEasingCurve(QEasingCurve.Type.InOutSine)
        self._animation.setLoopCount(-1)
        self._animation.valueChanged.connect(lambda v: self.changed.emit(float(v)))
        self._running = False

    @property
    def running(self) -> bool:
        return self._running

    def start(self) -> None:
        if not self._running:
            self._running = True
            self._animation.start()

    def stop(self) -> None:
        """Stop and settle at full strength, not at whatever phase it was in.

        A pulse frozen mid-fade leaves a half-lit dot that reads as a third
        state the operator has no way to interpret.
        """
        if self._running:
            self._running = False
            self._animation.stop()
            self.changed.emit(1.0)


class Flash(QObject):
    """A brief highlight that decays, for a value that just changed.

    The oldest trick in a trading terminal and still the right one: the eye
    finds a transient far better than it finds a static difference, so a price
    that ticked gets a fading wash rather than a permanent marker.
    """

    changed = Signal(float)

    def __init__(self, parent: QWidget, duration: int = 420):
        super().__init__(parent)
        self._animation = QVariantAnimation(self)
        self._animation.setDuration(duration)
        self._animation.setStartValue(1.0)
        self._animation.setEndValue(0.0)
        self._animation.setEasingCurve(QEasingCurve.Type.OutQuad)
        self._animation.valueChanged.connect(lambda v: self.changed.emit(float(v)))
        self._animation.finished.connect(lambda: self.changed.emit(0.0))
        self._direction = 0

    @property
    def direction(self) -> int:
        """+1 when the last flash was an increase, -1 a decrease, 0 none."""
        return self._direction

    def trigger(self, direction: int = 0) -> None:
        self._direction = direction
        self._animation.stop()
        self._animation.start()


def after(parent: QObject, milliseconds: int, callback) -> QTimer:
    """A parented single-shot timer.

    ``QTimer.singleShot`` with a bound method keeps the receiver alive and
    fires into it after the widget is gone. Parenting the timer means Qt
    destroys it with the widget, which is what makes it safe to use from a view
    that a language switch may throw away at any moment.
    """
    timer = QTimer(parent)
    timer.setSingleShot(True)
    timer.timeout.connect(callback)
    timer.start(milliseconds)
    return timer
