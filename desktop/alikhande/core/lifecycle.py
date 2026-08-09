"""Signal lifecycle rules.

A signal that is shown once and forgotten can never produce a win rate. Every
candidate walks an explicit state machine, every transition is persisted, and
illegal transitions are rejected loudly rather than silently accepted — a
corrupted lifecycle is worse than no statistics, because it looks like data.
"""

from __future__ import annotations

from .enums import SignalState

_TERMINAL_STATES = frozenset(
    {
        SignalState.TP,
        SignalState.SL,
        SignalState.EXPIRED,
        SignalState.INVALIDATED,
        SignalState.NOT_FILLED,
        SignalState.AMBIGUOUS,
    }
)

# Explicit allow-list. Anything absent is a bug in the caller, not a state the
# signal is permitted to reach.
_ALLOWED: dict[SignalState, frozenset[SignalState]] = {
    SignalState.NONE: frozenset({SignalState.CANDIDATE}),
    SignalState.CANDIDATE: frozenset(
        {SignalState.CONFIRMED, SignalState.INVALIDATED, SignalState.EXPIRED}
    ),
    SignalState.CONFIRMED: frozenset(
        {SignalState.PREVIEWED, SignalState.INVALIDATED, SignalState.EXPIRED}
    ),
    SignalState.PREVIEWED: frozenset(
        {
            SignalState.ACTIVE,
            SignalState.NOT_FILLED,
            SignalState.INVALIDATED,
            SignalState.EXPIRED,
        }
    ),
    SignalState.ACTIVE: frozenset({SignalState.TP, SignalState.SL, SignalState.AMBIGUOUS}),
}


def is_terminal(state: SignalState) -> bool:
    """Terminal states are final. Only the statistics layer reads them after."""
    return state in _TERMINAL_STATES


def is_scorable(state: SignalState) -> bool:
    """Only TP and SL are outcomes a win rate may be computed from.

    Expiry and invalidation say something about the *scanner*, not about the
    setup's edge, and pooling them into a win rate would quietly flatter or damn
    the strategy.
    """
    return state in (SignalState.TP, SignalState.SL)


def transition_allowed(source: SignalState, target: SignalState) -> bool:
    if is_terminal(source):
        return False
    if source == target:
        return False
    return target in _ALLOWED.get(source, frozenset())


class IllegalTransition(RuntimeError):
    """Raised when a caller tries to move a signal somewhere it cannot go.

    An exception rather than a silent no-op: a lifecycle that quietly refuses
    is a lifecycle whose stored history no longer matches what happened.
    """

    def __init__(self, signal_id: str, source: SignalState, target: SignalState) -> None:
        super().__init__(
            f"signal {signal_id}: {source.name} -> {target.name} is not a permitted transition"
        )
        self.signal_id = signal_id
        self.source = source
        self.target = target
