"""The three environments, and what each one is structurally allowed to do.

Until now the environment was *inferred*: ``detect_runtime`` looked at whether a
gateway answered and whether the caller had asked for a replay, and named the
result LIVE / REPLAY / OFFLINE. That is the right answer to the question "what
kind of data am I looking at", and it stays exactly as it was.

It is the wrong answer to a different question the operator actually asks:
**"which of my three set-ups am I in right now?"** Those are not the same thing.
A replay and a demo session both produce signals; a demo account and a real
account both come from a live terminal and are indistinguishable to
``detect_runtime``. Inferring the environment from the plumbing means the most
consequential fact about a session — whether the account on the other end is
real — is a derived property of something else.

So the environment is chosen, declared, and carries its own capability matrix:

``BACKTEST``
    Replay over recorded or synthetic bars. No live gateway. Nothing can be
    sent because there is nothing to send to.

``DEMO``
    A live terminal on a demo account. The only environment in which an order
    can leave this application, and only then after arm *and* confirm.

``PRODUCTION``
    A live terminal on a real account. Everything runs: connection supervision,
    data quality, risk, planning, preflight, reconciliation, reporting,
    recovery. The send is **hard-locked**.

## What the production lock is, and what it is not

It is not a setting. :data:`PRODUCTION_SEND_LOCK` is a module constant with no
setter, no configuration key, no environment variable and no enum member that
turns it off. :func:`capabilities` reads it, and every path that could reach a
broker consults the result.

It is also not the only thing standing between this build and a live order.
Three independent refusals already existed and none of them were touched:
``RunMode`` has no live member, ``core.execution.submit`` returns
``REAL_ACCOUNT_BLOCKED`` on any non-demo account, and the MT5 adapter refuses
again in ``send_order`` through code sharing nothing with either. This lock is a
fourth, added at a different altitude — it refuses based on the *declared
environment* rather than on the account flag, so it holds even in the case the
other three cannot see: a real account that a broker has mislabelled, or a demo
flag read from a terminal that has since been switched underneath the session.

Unlocking is deliberately not implemented. When real trading is eventually
authorised it should arrive as its own reviewed change with its own tests, not
as a flag somebody flips.
"""

from __future__ import annotations

from dataclasses import dataclass

from .enums import RunMode, RuntimeKind

# ---------------------------------------------------------------------------
# The lock.
#
# A constant, not a setting. Nothing in this codebase writes to it; the test
# suite asserts that nothing does, and that no code path produces capabilities
# permitting a send in PRODUCTION.
PRODUCTION_SEND_LOCK = True

#: Why a send was refused, when it was refused for being in production. A code
#: rather than a sentence so the UI can translate it and the journal can group
#: by it.
PRODUCTION_LOCK_CODE = "PRODUCTION_SEND_HARD_LOCKED"


class Environment:
    """The three environments as string constants.

    Strings rather than an ``IntEnum`` on purpose. This value is written to the
    preferences file, stamped onto every persisted run and printed in the
    diagnostics bundle; a stored integer whose meaning lives in a source file
    somebody has to look up is exactly how a year-old database becomes
    unreadable. ``"PRODUCTION"`` still means production in a text editor.
    """

    BACKTEST = "BACKTEST"
    DEMO = "DEMO"
    PRODUCTION = "PRODUCTION"

    ALL = (BACKTEST, DEMO, PRODUCTION)

    @staticmethod
    def parse(value: object, default: str = "DEMO") -> str:
        """Coerce stored or user input to a known environment.

        Falls back rather than raising: the value arrives from a preferences
        file the operator can edit by hand, and a typo there must not stop the
        application from starting. The fallback is DEMO — never PRODUCTION —
        because an unreadable setting should land in the more restricted place,
        not the more consequential one.
        """
        if isinstance(value, str) and value.upper() in Environment.ALL:
            return value.upper()
        return default if default in Environment.ALL else Environment.DEMO


@dataclass(frozen=True)
class Capabilities:
    """What one environment may do. Derived, never stored.

    Computed from the environment name on every read rather than held as a
    table. A table can be mutated at runtime by anything holding a reference;
    a pure function of a string cannot.
    """

    environment: str

    #: May an order ever leave the application in this environment?
    may_send_orders: bool
    #: Empty when sending is permitted; a reason code when it is not.
    send_lock: str

    #: Does this environment need a live terminal to function at all?
    requires_live_gateway: bool
    #: Is a real (non-demo) account expected here? Used to decide whether an
    #: account-type mismatch is a warning or a hard stop.
    expects_real_account: bool

    #: Must persistence succeed for the session to proceed?
    persistence_required: bool
    #: Base filename for this environment's database. Separate files are what
    #: keep a replay's win rate from being read as a demo account's.
    database_stem: str

    #: Run modes selectable in this environment. Anything outside this tuple is
    #: refused by :func:`coerce_mode` rather than silently accepted.
    allowed_modes: tuple[RunMode, ...]

    #: Does an unconsultable news calendar block trading here? Production and
    #: demo say yes; a backtest says no, because there is no live calendar to
    #: consult for bars recorded last year and blocking on that would make
    #: every replay empty.
    news_unknown_blocks: bool

    #: The runtime kind a session in this environment reports when it has no
    #: gateway evidence to say otherwise.
    default_runtime_kind: RuntimeKind

    def may_use(self, mode: RunMode) -> bool:
        return mode in self.allowed_modes

    def strongest_mode(self) -> RunMode:
        """The most capable mode this environment permits.

        Used by the automation engine, which must never assume DEMO_CONFIRM is
        available: in production the strongest mode is SHADOW, and an autopilot
        that assumed otherwise would spend every cycle being refused.
        """
        return max(self.allowed_modes, key=int)


def capabilities(environment: str) -> Capabilities:
    """The capability matrix for one environment.

    The single place any of these questions is answered. A caller that needs to
    know whether it may send asks here rather than comparing environment names
    itself, so adding a fourth environment later cannot leave a stale
    ``== "DEMO"`` comparison behind that quietly permits something.
    """
    environment = Environment.parse(environment)

    if environment == Environment.BACKTEST:
        return Capabilities(
            environment=environment,
            may_send_orders=False,
            send_lock="BACKTEST_HAS_NO_BROKER",
            requires_live_gateway=False,
            expects_real_account=False,
            persistence_required=False,
            database_stem="replay",
            # SHADOW is permitted so a replay exercises the whole planning and
            # preflight path rather than stopping at the signal. That is the
            # entire value of a replay: running the real code.
            allowed_modes=(RunMode.ALERT_ONLY, RunMode.SHADOW),
            news_unknown_blocks=False,
            default_runtime_kind=RuntimeKind.REPLAY,
        )

    if environment == Environment.PRODUCTION:
        return Capabilities(
            environment=environment,
            # The lock. Note this is not `not PRODUCTION_SEND_LOCK` — writing it
            # as a plain False means flipping the constant does not silently
            # open the gate either; the constant exists to be asserted against,
            # not to be a switch.
            may_send_orders=False,
            send_lock=PRODUCTION_LOCK_CODE,
            requires_live_gateway=True,
            expects_real_account=True,
            persistence_required=True,
            database_stem="production",
            # Everything short of the send. Preflight, sizing, reconciliation
            # and reporting all run against the real account, which is the
            # point: production readiness is measured, not assumed.
            allowed_modes=(RunMode.ALERT_ONLY, RunMode.SHADOW),
            news_unknown_blocks=True,
            default_runtime_kind=RuntimeKind.LIVE,
        )

    return Capabilities(
        environment=Environment.DEMO,
        may_send_orders=True,
        send_lock="",
        requires_live_gateway=True,
        expects_real_account=False,
        persistence_required=True,
        database_stem="alikhande",
        allowed_modes=(RunMode.ALERT_ONLY, RunMode.SHADOW, RunMode.DEMO_CONFIRM),
        news_unknown_blocks=True,
        default_runtime_kind=RuntimeKind.LIVE,
    )


def coerce_mode(environment: str, mode: RunMode) -> tuple[RunMode, str]:
    """Clamp a run mode to what the environment allows.

    Returns ``(mode, reason)`` where ``reason`` is empty when nothing was
    changed. Clamping downward rather than raising: switching from demo to
    production while DEMO_CONFIRM is selected is an ordinary thing to do, and
    the correct response is to drop to the strongest permitted mode and say so
    — not to refuse the environment change and leave the operator in demo.
    """
    caps = capabilities(environment)
    if caps.may_use(mode):
        return mode, ""
    return caps.strongest_mode(), f"MODE_NOT_AVAILABLE_IN_{caps.environment}"


def send_refusal(environment: str, mode: RunMode) -> str:
    """The reason an order may not be sent, or ``""`` when it may.

    Consulted before the account is even looked at, so an environment that
    cannot send never reaches the code that would inspect a real account's
    balance. Order matters: the environment lock is checked first because it is
    the one refusal that does not depend on the broker telling the truth.
    """
    caps = capabilities(environment)
    if not caps.may_send_orders:
        return caps.send_lock
    if not caps.may_use(mode):
        return f"MODE_NOT_AVAILABLE_IN_{caps.environment}"
    if mode == RunMode.ALERT_ONLY:
        return "ALERT_ONLY_MODE"
    if mode == RunMode.SHADOW:
        return "SHADOW_MODE"
    return ""


def account_verdict(environment: str, is_demo: bool | None) -> tuple[str, str]:
    """Does the attached account match the declared environment?

    Returns ``(severity, code)`` with severity in ``good`` / ``warning`` /
    ``critical`` / ``unknown``.

    The mismatch that matters is **a real account while DEMO is declared**. It
    is critical rather than merely wrong because the operator believes they are
    in the environment where arm-and-confirm sends orders. The reverse — a demo
    account under PRODUCTION — is only a warning: the readiness rehearsal is
    measuring the wrong account, which wastes the rehearsal but risks nothing.
    """
    caps = capabilities(environment)
    if is_demo is None:
        return "unknown", "ACCOUNT_UNKNOWN"
    if caps.expects_real_account:
        if is_demo:
            return "warning", "DEMO_ACCOUNT_IN_PRODUCTION"
        return "good", "REAL_ACCOUNT_AS_DECLARED"
    if not is_demo:
        return "critical", "REAL_ACCOUNT_IN_DEMO_ENVIRONMENT"
    return "good", "DEMO_ACCOUNT_AS_DECLARED"
