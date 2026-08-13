"""Runtime context and where its evidence is allowed to live.

The MQL5 build distinguished TERMINAL / TESTER / OPTIMIZATION because a
backtest and an optimization sweep both write records that look identical to
real ones, and if they land in the same file the evidence is silently
contaminated: a win rate computed afterwards would be measuring a mixture of
live scanning and whatever parameter sweep ran that afternoon.

The desktop build has the same problem with different names:

``LIVE``
    Attached to a running MT5 terminal. Production history. Persistence is
    REQUIRED — without it there is no de-duplication across restarts, no
    risk-state continuity and no outcome record, so the app refuses to enter a
    trading mode.

``REPLAY``
    Deterministic replay over recorded or synthetic bars. Worth inspecting
    afterwards, so it gets its own file, clearly named. Persistence is optional:
    a replay that cannot open a database is still a useful replay.

``OFFLINE``
    No gateway at all — the UI running with nothing behind it. Persistence is
    DISABLED. There is nothing here worth keeping, and writing it would produce
    files that are, by construction, evidence about nothing.

Note the asymmetry with MQL5: there, OPTIMIZATION was the disabled case because
it generated thousands of meaningless files. Here it is OFFLINE, for the same
reason — no market data means no observation.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .enums import RuntimeKind
from .hashing import fnv1a
from .models import RuntimeContext


def detect_runtime(*, connected: bool, replay: bool, identity_seed: str = "") -> RuntimeContext:
    """Classify the current run.

    ``connected`` means a broker gateway answered. ``replay`` means the caller
    deliberately started a replay session. A replay is never production even
    when a live gateway happens to be reachable — the classification follows
    what the data *is*, not what happens to be plugged in.
    """
    session_identity = fnv1a(identity_seed or "default")

    if replay:
        return RuntimeContext(
            kind=RuntimeKind.REPLAY,
            is_production=False,
            session_identity=session_identity,
            description="replay",
        )
    if connected:
        return RuntimeContext(
            kind=RuntimeKind.LIVE,
            is_production=True,
            session_identity=session_identity,
            description="live terminal",
        )
    return RuntimeContext(
        kind=RuntimeKind.OFFLINE,
        is_production=False,
        session_identity=session_identity,
        description="offline",
    )


@dataclass(frozen=True)
class PersistencePlan:
    enabled: bool
    required: bool
    filename: str
    rationale: str


def persistence_plan(context: RuntimeContext, data_dir: Path) -> PersistencePlan:
    """Decide whether a database should exist, and where.

    The file names are deliberately self-describing. Somebody who finds
    ``replay_3F2A1C08.sqlite`` on disk in a year should not have to guess
    whether the win rate inside it came from a live session.
    """
    if context.kind == RuntimeKind.LIVE:
        return PersistencePlan(
            enabled=True,
            required=True,
            filename=str(data_dir / "alikhande.sqlite"),
            rationale="production history",
        )
    if context.kind == RuntimeKind.REPLAY:
        return PersistencePlan(
            enabled=True,
            required=False,
            filename=str(data_dir / f"replay_{context.session_identity}.sqlite"),
            rationale="isolated replay history",
        )
    return PersistencePlan(
        enabled=False,
        required=False,
        filename="",
        rationale="an offline session observes nothing and has no evidence to store",
    )
