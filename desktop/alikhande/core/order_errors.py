"""What a broker rejection actually means, and whether it is worth retrying.

MetaTrader answers a failed order with an integer. ``10016`` is not a
diagnosis, and an application that shows the operator ``10016`` has passed the
problem along rather than solved it. Worse, the integers are not uniform in
kind: some mean *the market moved* (send it again), some mean *your request is
malformed* (sending it again will fail identically forever), and one of them —
``10008``/``10009`` — is not a failure at all.

Conflating those is how a retry loop hammers a broker four hundred times with a
request that was never going to be accepted, and how a genuinely transient
requote gets surfaced as a permanent defect.

So every retcode this application can receive is classified along three axes:

**Category** — whose problem is it? A ``REQUEST`` error is the application's own
fault and a bug report; a ``MARKET`` error is the market being the market; an
``ACCOUNT`` error is the operator's account state; a ``CONNECTION`` error is the
link.

**Retryable** — would sending the identical request again plausibly succeed? For
``REQUEST`` errors the answer is always no, and saying so is the entire point:
it converts an infinite loop into one clear failure.

**Guidance** — one sentence the operator can act on, keyed for translation.

## The unknown retcode is the important case

A code not in this table returns ``UNKNOWN``, **not retryable**, and says so.
Defaulting an unrecognised rejection to retryable is how a build meets a new
broker's custom code and spins; defaulting it to a known category is how it
gets mis-reported. Not knowing is a real answer and it is recorded as one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum


class ErrorCategory(IntEnum):
    """Whose problem this is. Ordered by who has to do something about it."""

    NONE = 0  # not an error
    MARKET = 1  # price moved, market closed, no quotes
    ACCOUNT = 2  # funds, limits, permissions
    REQUEST = 3  # malformed — this application built a bad order
    CONNECTION = 4  # the link to the terminal or the server
    UNKNOWN = 5  # not in the table


@dataclass(frozen=True)
class OrderError:
    retcode: int
    code: str
    category: ErrorCategory
    retryable: bool
    #: Translation key for one actionable sentence.
    guidance_key: str

    @property
    def is_failure(self) -> bool:
        return self.category != ErrorCategory.NONE

    @property
    def is_defect(self) -> bool:
        """A REQUEST error means this application built an invalid order.

        Surfaced separately from ordinary failures because it is the only
        category the operator cannot fix and should not be asked to — it
        belongs in the diagnostics bundle, not in a "try again" dialog.
        """
        return self.category == ErrorCategory.REQUEST


def _e(retcode, code, category, retryable, key) -> OrderError:
    return OrderError(retcode, code, category, retryable, key)


# MetaTrader 5 trade server return codes. Only the ones reachable from this
# application's single order path are listed; the rest fall through to UNKNOWN,
# which is a real answer rather than a gap.
_TABLE: dict[int, OrderError] = {
    e.retcode: e
    for e in (
        # ---- not failures ---------------------------------------------------
        _e(10008, "PLACED", ErrorCategory.NONE, False, "order.err.placed"),
        _e(10009, "DONE", ErrorCategory.NONE, False, "order.err.done"),
        _e(10010, "DONE_PARTIAL", ErrorCategory.NONE, False, "order.err.partial"),
        # ---- the market -----------------------------------------------------
        _e(10004, "REQUOTE", ErrorCategory.MARKET, True, "order.err.requote"),
        _e(10020, "PRICE_CHANGED", ErrorCategory.MARKET, True, "order.err.price_changed"),
        _e(10021, "PRICE_OFF", ErrorCategory.MARKET, True, "order.err.price_off"),
        _e(10018, "MARKET_CLOSED", ErrorCategory.MARKET, False, "order.err.market_closed"),
        _e(10031, "CONNECTION", ErrorCategory.CONNECTION, True, "order.err.connection"),
        _e(10024, "TOO_MANY_REQUESTS", ErrorCategory.CONNECTION, True, "order.err.too_many"),
        _e(10012, "REQUEST_TIMEOUT", ErrorCategory.CONNECTION, True, "order.err.timeout"),
        # ---- the account ----------------------------------------------------
        _e(10019, "NO_MONEY", ErrorCategory.ACCOUNT, False, "order.err.no_money"),
        _e(10017, "TRADE_DISABLED", ErrorCategory.ACCOUNT, False, "order.err.trade_disabled"),
        _e(10027, "AUTOTRADING_DISABLED", ErrorCategory.ACCOUNT, False, "order.err.algo_off"),
        _e(
            10026,
            "SERVER_DISABLES_AT",
            ErrorCategory.ACCOUNT,
            False,
            "order.err.server_algo_off",
        ),
        _e(10025, "NO_CHANGES", ErrorCategory.ACCOUNT, False, "order.err.no_changes"),
        _e(10034, "LIMIT_VOLUME", ErrorCategory.ACCOUNT, False, "order.err.limit_volume"),
        _e(10033, "LIMIT_ORDERS", ErrorCategory.ACCOUNT, False, "order.err.limit_orders"),
        _e(10032, "ONLY_REAL", ErrorCategory.ACCOUNT, False, "order.err.only_real"),
        # ---- the request this application built -----------------------------
        # Every one of these is a defect here, never something for the operator
        # to retry. `INVALID_VOLUME` and `INVALID_STOPS` in particular are the
        # two the sizing and preflight layers exist to make impossible, so
        # seeing one is a signal that a broker specification changed underneath
        # a cached value.
        _e(10013, "INVALID_REQUEST", ErrorCategory.REQUEST, False, "order.err.invalid"),
        _e(10014, "INVALID_VOLUME", ErrorCategory.REQUEST, False, "order.err.invalid_volume"),
        _e(10015, "INVALID_PRICE", ErrorCategory.REQUEST, False, "order.err.invalid_price"),
        _e(10016, "INVALID_STOPS", ErrorCategory.REQUEST, False, "order.err.invalid_stops"),
        _e(10030, "INVALID_FILL", ErrorCategory.REQUEST, False, "order.err.invalid_fill"),
        _e(10022, "INVALID_EXPIRATION", ErrorCategory.REQUEST, False, "order.err.invalid_exp"),
        _e(10035, "INVALID_ORDER", ErrorCategory.REQUEST, False, "order.err.invalid_order"),
        _e(10036, "POSITION_CLOSED", ErrorCategory.REQUEST, False, "order.err.pos_closed"),
        _e(10011, "REQUEST_ERROR", ErrorCategory.REQUEST, False, "order.err.request_error"),
        _e(10006, "REJECT", ErrorCategory.REQUEST, False, "order.err.reject"),
        _e(10007, "CANCEL", ErrorCategory.NONE, False, "order.err.cancel"),
    )
}


def classify(retcode: int) -> OrderError:
    """Look up a retcode. An unknown one is UNKNOWN and not retryable.

    Never raises and never guesses. A broker that invents a code gets an honest
    "this build does not recognise it" rather than a plausible-looking category
    that would send the operator chasing the wrong fix.
    """
    known = _TABLE.get(int(retcode))
    if known is not None:
        return known
    return OrderError(
        retcode=int(retcode),
        code=f"UNKNOWN_{int(retcode)}",
        category=ErrorCategory.UNKNOWN,
        retryable=False,
        guidance_key="order.err.unknown",
    )


def is_success(retcode: int) -> bool:
    return classify(retcode).category == ErrorCategory.NONE


@dataclass
class ErrorTally:
    """Order rejections over the session, grouped by what they were.

    Kept because a single rejection is noise and a pattern is a diagnosis:
    forty ``INVALID_STOPS`` against one symbol says its stops level changed,
    and nothing in a per-order message ever says that.
    """

    counts: dict[str, int] = field(default_factory=dict)
    first_seen: dict[str, int] = field(default_factory=dict)
    last_seen: dict[str, int] = field(default_factory=dict)
    last_symbol: dict[str, str] = field(default_factory=dict)

    def record(self, retcode: int, symbol: str, now: int) -> OrderError:
        error = classify(retcode)
        if not error.is_failure:
            return error
        self.counts[error.code] = self.counts.get(error.code, 0) + 1
        self.first_seen.setdefault(error.code, now)
        self.last_seen[error.code] = now
        self.last_symbol[error.code] = symbol
        return error

    def total(self) -> int:
        return sum(self.counts.values())

    def defects(self) -> dict[str, int]:
        """Only the REQUEST-category failures — the ones that are this
        application's bugs rather than the market's behaviour."""
        return {
            code: count
            for code, count in self.counts.items()
            if _by_code(code).category == ErrorCategory.REQUEST
        }

    def ranked(self) -> list[tuple[str, int]]:
        return sorted(self.counts.items(), key=lambda kv: (-kv[1], kv[0]))


def _by_code(code: str) -> OrderError:
    for error in _TABLE.values():
        if error.code == code:
            return error
    return classify(0)
