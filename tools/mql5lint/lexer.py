"""Minimal MQL5 lexer.

MQL5 is close enough to C++ that a comment/string-aware scanner gets us most of
the way. Everything downstream (brace balance, symbol extraction, field access
checks) runs on *stripped* source so a brace inside a string literal or a
`//` inside a string can never produce a false positive.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StrippedSource:
    """Source with comments and string/char literal *contents* blanked out.

    Length and line structure are preserved exactly, so any offset computed on
    the stripped text maps back to the original file position 1:1.
    """

    text: str
    original: str

    def line_of(self, index: int) -> int:
        return self.original.count("\n", 0, index) + 1


def strip(source: str) -> StrippedSource:
    """Blank out comments and literal contents, preserving offsets and newlines.

    Replacement uses spaces (and keeps newlines) so line/column math still works.
    String literals collapse to empty quotes `""` rather than vanishing, so
    expression structure stays parseable.
    """
    out = list(source)
    i = 0
    n = len(source)

    while i < n:
        c = source[i]

        # Line comment
        if c == "/" and i + 1 < n and source[i + 1] == "/":
            while i < n and source[i] != "\n":
                out[i] = " "
                i += 1
            continue

        # Block comment
        if c == "/" and i + 1 < n and source[i + 1] == "*":
            out[i] = out[i + 1] = " "
            i += 2
            while i < n and not (source[i] == "*" and i + 1 < n and source[i + 1] == "/"):
                if source[i] != "\n":
                    out[i] = " "
                i += 1
            if i < n:
                out[i] = " "
                if i + 1 < n:
                    out[i + 1] = " "
                i += 2
            continue

        # String / char literal — blank the contents, keep the delimiters.
        if c in ('"', "'"):
            quote = c
            i += 1
            while i < n:
                if source[i] == "\\" and i + 1 < n:
                    out[i] = " "
                    out[i + 1] = " "
                    i += 2
                    continue
                if source[i] == quote:
                    i += 1
                    break
                if source[i] != "\n":
                    out[i] = " "
                i += 1
            continue

        # Preprocessor line continuation and everything else pass through.
        i += 1

    return StrippedSource(text="".join(out), original=source)


def balance_report(stripped: str) -> list[tuple[str, int]]:
    """Return unbalanced bracket positions as (kind, index).

    `kind` is one of: UNCLOSED_<char>, UNEXPECTED_<char>, MISMATCH_<char>.
    """
    pairs = {"(": ")", "[": "]", "{": "}"}
    closers = {v: k for k, v in pairs.items()}
    stack: list[tuple[str, int]] = []
    problems: list[tuple[str, int]] = []

    for idx, ch in enumerate(stripped):
        if ch in pairs:
            stack.append((ch, idx))
        elif ch in closers:
            if not stack:
                problems.append((f"UNEXPECTED_{ch}", idx))
            elif stack[-1][0] != closers[ch]:
                problems.append((f"MISMATCH_{ch}", idx))
                stack.pop()
            else:
                stack.pop()

    for ch, idx in stack:
        problems.append((f"UNCLOSED_{ch}", idx))

    return problems
