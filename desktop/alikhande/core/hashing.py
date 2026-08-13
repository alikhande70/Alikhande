"""FNV-1a hashing.

Not cryptographic. Used for stable identity — signal ids, parameter and
broker-spec fingerprints — where the only requirements are determinism across
runs and processes, and a low collision rate at the scale of a few million
strings.

Determinism across *implementations* matters too: these produce byte-identical
output to ``Core/Hash.mqh``, so a signal id computed by the desktop app and one
computed by the EA agree for the same inputs. That is what makes the two builds
comparable at all.

The MQL5 original iterates ``StringGetCharacter``, which yields UTF-16 code
units. This encodes to UTF-16LE and folds the two bytes of each unit in the
same order, so non-ASCII input hashes identically as well.
"""

from __future__ import annotations

_MASK32 = 0xFFFFFFFF
_MASK64 = 0xFFFFFFFFFFFFFFFF

_FNV32_OFFSET = 2166136261
_FNV32_PRIME = 16777619

_FNV64_OFFSET = 14695981039346656037
_FNV64_PRIME = 1099511628211


def _code_units(text: str) -> list[int]:
    """The UTF-16 code units of ``text``, matching MQL5's string model."""
    raw = text.encode("utf-16-le", errors="surrogatepass")
    return [raw[i] | (raw[i + 1] << 8) for i in range(0, len(raw), 2)]


def fnv1a(text: str) -> str:
    """32-bit FNV-1a, rendered as 8 uppercase hex digits."""
    digest = _FNV32_OFFSET
    for unit in _code_units(text):
        digest = ((digest ^ unit) * _FNV32_PRIME) & _MASK32
    return f"{digest:08X}"


def fnv1a64(text: str) -> str:
    """64-bit FNV-1a, rendered as 16 uppercase hex digits.

    Used where a collision would silently corrupt history — parameter sets,
    broker specs — rather than merely duplicate a row.
    """
    digest = _FNV64_OFFSET
    for unit in _code_units(text):
        digest = ((digest ^ unit) * _FNV64_PRIME) & _MASK64
    return f"{digest:016X}"
