"""Static checks over the MQL5 source tree.

Every check yields `Finding`s. A check that cannot analyse something with
confidence stays silent rather than guessing — a linter that cries wolf gets
ignored, and this one is the only automated gate the project has until a real
MetaEditor compile is available.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .lexer import balance_report
from .model import SourceFile, SourceTree


@dataclass(frozen=True)
class Finding:
    code: str
    rel: str
    line: int
    message: str

    def __str__(self) -> str:  # pragma: no cover - formatting only
        where = f"{self.rel}:{self.line}" if self.line else self.rel
        return f"{self.code:<26} {where}\n{'':<27}{self.message}"


# --------------------------------------------------------------------- basics


def check_include_graph(tree: SourceTree) -> list[Finding]:
    out: list[Finding] = []
    for sf in tree.files.values():
        for spec in sf.includes:
            # Standard-library includes (Trade/Trade.mqh, Canvas/…) are not ours.
            if not spec.startswith("AlikhandeScanner/") and not spec.startswith("."):
                if "/" in spec and tree.resolve_include(sf, spec) is None:
                    continue  # assume MT5 stdlib
            if tree.resolve_include(sf, spec) is None:
                idx = sf.text.find(spec)
                out.append(
                    Finding(
                        "BROKEN_INCLUDE",
                        sf.rel,
                        sf.line_of(idx) if idx >= 0 else 0,
                        f"cannot resolve #include \"{spec}\"",
                    )
                )
    return out


def check_include_cycles(tree: SourceTree) -> list[Finding]:
    """Report cycles. `#pragma once` makes these survivable, but they signal a
    layering violation and MetaEditor's behaviour with them is worth avoiding."""
    graph: dict[Path, list[Path]] = {}
    for sf in tree.files.values():
        graph[sf.path] = []
        for spec in sf.includes:
            target = tree.resolve_include(sf, spec)
            if target and target in tree.files:
                graph[sf.path].append(target)

    out: list[Finding] = []
    seen_cycles: set[tuple[str, ...]] = set()
    WHITE, GREY, BLACK = 0, 1, 2
    colour: dict[Path, int] = {p: WHITE for p in graph}

    def visit(node: Path, stack: list[Path]) -> None:
        colour[node] = GREY
        stack.append(node)
        for nxt in graph.get(node, []):
            if colour.get(nxt, BLACK) == GREY:
                cycle = stack[stack.index(nxt) :]
                key = tuple(sorted(str(p) for p in cycle))
                if key not in seen_cycles:
                    seen_cycles.add(key)
                    names = " -> ".join(tree.files[p].rel for p in cycle)
                    out.append(
                        Finding("INCLUDE_CYCLE", tree.files[node].rel, 0, names)
                    )
            elif colour.get(nxt, BLACK) == WHITE:
                visit(nxt, stack)
        stack.pop()
        colour[node] = BLACK

    for node in list(graph):
        if colour[node] == WHITE:
            visit(node, [])
    return out


def check_bracket_balance(tree: SourceTree) -> list[Finding]:
    out: list[Finding] = []
    for sf in tree.files.values():
        for kind, idx in balance_report(sf.text):
            out.append(
                Finding("BRACKET_IMBALANCE", sf.rel, sf.line_of(idx), kind)
            )
    return out


def check_pragma_once(tree: SourceTree) -> list[Finding]:
    out: list[Finding] = []
    for sf in tree.files.values():
        if sf.path.suffix == ".mqh" and "#pragma once" not in sf.text:
            out.append(
                Finding(
                    "MISSING_PRAGMA_ONCE",
                    sf.rel,
                    1,
                    "header without `#pragma once` risks duplicate definitions",
                )
            )
    return out


# ----------------------------------------------------------------- constants


def check_unresolved_constants(tree: SourceTree) -> list[Finding]:
    """Every `AS_*` identifier must be a #define, an enum member, or an enum
    type name. This catches typos and deleted constants before MetaEditor does.
    """
    known = tree.all_defines | tree.all_enum_members | tree.all_enum_types
    # Class/struct names and free functions are declarations too.
    known |= set(tree.types)
    known |= tree.all_functions

    out: list[Finding] = []
    for sf in tree.files.values():
        for m in re.finditer(r"\b(AS_[A-Za-z0-9_]+)\b", sf.text):
            name = m.group(1)
            if name in known:
                continue
            out.append(
                Finding(
                    "UNRESOLVED_CONSTANT",
                    sf.rel,
                    sf.line_of(m.start()),
                    f"`{name}` is not defined by any #define, enum, struct or class",
                )
            )
    return out


# -------------------------------------------------------------- field access


DECL_RE = re.compile(r"\b(AS_[A-Za-z0-9_]+)\s+(\w+)\s*(?:[;,=\)\[]|$)", re.M)


def check_struct_field_access(tree: SourceTree) -> list[Finding]:
    """Catch `plan.enrty` style typos.

    Only checks variables whose type is unambiguously declared in the same file
    and whose type we successfully parsed members for. Anything ambiguous is
    skipped.
    """
    out: list[Finding] = []
    for sf in tree.files.values():
        # Build var -> type map, dropping any name declared with two types.
        var_types: dict[str, str] = {}
        conflicting: set[str] = set()
        for type_name, var in DECL_RE.findall(sf.text):
            if type_name not in tree.types:
                continue
            if var in var_types and var_types[var] != type_name:
                conflicting.add(var)
            var_types[var] = type_name
        for var in conflicting:
            var_types.pop(var, None)

        for m in re.finditer(r"\b(\w+)\s*\.\s*(\w+)\b", sf.text):
            var, member = m.group(1), m.group(2)
            type_name = var_types.get(var)
            if not type_name:
                continue
            decl = tree.types.get(type_name)
            if not decl or not decl.members:
                continue
            if member in decl.members:
                continue
            out.append(
                Finding(
                    "UNKNOWN_MEMBER",
                    sf.rel,
                    sf.line_of(m.start()),
                    f"`{var}` is {type_name}, which has no member `{member}`",
                )
            )
    return out


# ------------------------------------------------------------- MQL5 hazards


def check_unchecked_copy(tree: SourceTree) -> list[Finding]:
    """`CopyBuffer`/`CopyRates`/`CopyTime`… returning into an unchecked call.

    MQL5 returns the copied count; ignoring it means silently operating on a
    stale or partially-filled array. We flag calls used as a bare statement.
    """
    out: list[Finding] = []
    fns = ("CopyBuffer", "CopyRates", "CopyHigh", "CopyLow", "CopyClose", "CopyOpen", "CopyTime", "CopyTickVolume")
    pattern = re.compile(r"(^|[;{}])\s*(" + "|".join(fns) + r")\s*\(", re.M)
    for sf in tree.files.values():
        for m in pattern.finditer(sf.text):
            out.append(
                Finding(
                    "UNCHECKED_COPY",
                    sf.rel,
                    sf.line_of(m.start(2)),
                    f"`{m.group(2)}(...)` return value ignored; a short copy will "
                    f"read uninitialised array elements",
                )
            )
    return out


def check_indicator_handle_leak(tree: SourceTree) -> list[Finding]:
    """Indicator handles created inside a function that is called per-tick.

    Creating `iMA`/`iATR`/`iADX` on every call and releasing them is a known
    MT5 anti-pattern: it churns the indicator cache and `BarsCalculated` is
    unreliable immediately after creation. Handles belong in a cache.
    """
    out: list[Finding] = []
    creators = re.compile(r"\b(iMA|iATR|iADX|iRSI|iStochastic|iMACD|iBands|iCCI)\s*\(")
    for sf in tree.files.values():
        if "HandleCache" in sf.rel or "IndicatorCache" in sf.rel:
            continue  # the cache itself is allowed to create handles
        for m in creators.finditer(sf.text):
            out.append(
                Finding(
                    "UNCACHED_INDICATOR",
                    sf.rel,
                    sf.line_of(m.start()),
                    f"`{m.group(1)}(...)` called outside the handle cache; "
                    f"per-call handle creation churns the indicator cache",
                )
            )
    return out


SCALAR_TYPES = "double|int|long|datetime|ulong|uint|float|bool|short|char|color"


def _file_scope_arrays(text: str) -> set[str]:
    """Names of scalar arrays declared at file scope (brace depth 0).

    Locals are excluded deliberately: the overwhelmingly common local pattern is
    resize-then-fill in the next statement, which is safe. File-scope arrays are
    resized in one function and read in another, which is where the real hazard
    lives.
    """
    names: set[str] = set()
    depth = 0
    for m in re.finditer(rf"[{{}}]|\b({SCALAR_TYPES})\s+(\w+)\s*\[\s*\]", text):
        tok = m.group(0)
        if tok == "{":
            depth += 1
        elif tok == "}":
            depth = max(0, depth - 1)
        elif depth == 0:
            names.add(m.group(2))
    return names


def check_resize_without_init(tree: SourceTree) -> list[Finding]:
    """`ArrayResize` on a file-scope scalar array with no `ArrayInitialize`.

    MQL5 does not guarantee zero-initialisation of newly added elements, so
    reading before writing yields garbage. This is exactly bug B1 in v1.1.0:
    `g_last_alert` holds an uninitialised `datetime`, so the alert cooldown
    comparison is undefined on the first pass for every symbol.
    """
    out: list[Finding] = []
    for sf in tree.files.values():
        candidates = _file_scope_arrays(sf.text)
        if not candidates:
            continue
        resized = {m.group(1) for m in re.finditer(r"ArrayResize\s*\(\s*(\w+)", sf.text)}
        initialised = {m.group(1) for m in re.finditer(r"ArrayInitialize\s*\(\s*(\w+)", sf.text)}
        # Arrays fully overwritten by a Copy* call are fine.
        copied = {
            m.group(1)
            for m in re.finditer(r"Copy\w+\s*\([^;]*?,\s*(\w+)\s*\)", sf.text)
        }
        for name in sorted((resized & candidates) - initialised - copied):
            idx = sf.text.find(f"ArrayResize({name}")
            out.append(
                Finding(
                    "RESIZE_WITHOUT_INIT",
                    sf.rel,
                    sf.line_of(idx) if idx >= 0 else 0,
                    f"file-scope `{name}` is ArrayResize'd but never "
                    f"ArrayInitialize'd; new elements are not guaranteed zero",
                )
            )
    return out


# ------------------------------------------------------------ policy / safety


FORBIDDEN = {
    "martingale": "position sizing policy forbids martingale",
    "averaging down": "position sizing policy forbids averaging down",
    "OrderSendAsync(": "async sends cannot be reconciled deterministically",
    "WebRequest(": "synchronous and unavailable in Strategy Tester; breaks reproducibility",
}


FUNC_DEF_POS_RE = re.compile(r"\b[A-Za-z_]\w*\s+([A-Za-z_]\w*)\s*\([^;{}]*\)\s*\{")


def _brace_depths(text: str) -> list[int]:
    """Brace nesting depth at every character offset.

    The depth reported for a `{` is the depth *outside* it, so a file-scope
    function's opening brace reads as 0.
    """
    depths = [0] * (len(text) + 1)
    depth = 0
    for i, ch in enumerate(text):
        depths[i] = depth
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth = max(0, depth - 1)
    depths[len(text)] = depth
    return depths


def check_use_before_definition(tree: SourceTree) -> list[Finding]:
    """Free function called earlier in the file than it is defined.

    MQL5 has no implicit forward declarations: a global function must be defined
    before its first use *within the same translation unit position*. Calling one
    from a class method that appears above it is a hard compile error, and it is
    an easy mistake to make when moving helpers around.

    Only same-file cases are reported — a function defined in an included header
    is available everywhere below the `#include`, which the include graph
    already validates.
    """
    out: list[Finding] = []
    for sf in tree.files.values():
        # Only file-scope functions qualify. Class and struct members may be
        # called in any order within their own type, so a member matching the
        # same syntactic shape is not a use-before-definition at all.
        depths = _brace_depths(sf.text)

        definitions: dict[str, int] = {}
        for m in FUNC_DEF_POS_RE.finditer(sf.text):
            if depths[m.start()] != 0:
                continue
            # Keep the earliest definition if a name somehow appears twice.
            definitions.setdefault(m.group(1), m.start())

        for name, def_pos in definitions.items():
            for call in re.finditer(rf"\b{re.escape(name)}\s*\(", sf.text):
                if call.start() >= def_pos:
                    continue
                # The definition site itself matches the call pattern; skip it.
                if call.start() == def_pos:
                    continue
                out.append(
                    Finding(
                        "USE_BEFORE_DEFINITION",
                        sf.rel,
                        sf.line_of(call.start()),
                        f"`{name}(...)` is called here but defined at line "
                        f"{sf.line_of(def_pos)}; MQL5 requires definition first",
                    )
                )
                break
    return out


def check_forbidden(tree: SourceTree) -> list[Finding]:
    out: list[Finding] = []
    for sf in tree.files.values():
        lowered = sf.text.lower()
        for needle, why in FORBIDDEN.items():
            pos = lowered.find(needle.lower())
            if pos >= 0:
                out.append(
                    Finding("FORBIDDEN_PATTERN", sf.rel, sf.line_of(pos), f"`{needle}` — {why}")
                )
    return out


def check_order_send_boundary(tree: SourceTree, allowed_rel: str) -> list[Finding]:
    """Exactly one module may call `OrderSend`. Everything else routes through it."""
    out: list[Finding] = []
    for sf in tree.files.values():
        for m in re.finditer(r"\bOrderSend\s*\(", sf.text):
            if sf.rel.replace("\\", "/") == allowed_rel:
                continue
            out.append(
                Finding(
                    "ORDERSEND_BOUNDARY",
                    sf.rel,
                    sf.line_of(m.start()),
                    f"OrderSend may only be called from {allowed_rel}",
                )
            )
    return out


def check_required_invariants(tree: SourceTree, required: dict[str, str]) -> list[Finding]:
    """Safety invariants that must exist *somewhere* in the tree.

    Scans the *original* text, not the stripped text: most of these markers are
    result-code string literals (`"REAL_ACCOUNT_BLOCKED"`), whose contents the
    lexer deliberately blanks.
    """
    joined = "\n".join(sf.stripped.original for sf in tree.files.values())
    out: list[Finding] = []
    for label, needle in required.items():
        if needle not in joined:
            out.append(Finding("MISSING_INVARIANT", "<tree>", 0, f"{label}: expected `{needle}`"))
    return out


def check_dead_types(tree: SourceTree, entry_points: list[str]) -> list[Finding]:
    """Classes that are declared but never instantiated anywhere.

    v1.1.0 shipped four such classes (RiskPlanner, DemoExecution, NewBarDetector,
    Statistics) — compiled, included, and unreachable.
    """
    joined = "\n".join(sf.text for sf in tree.files.values())
    out: list[Finding] = []
    for name, decl in sorted(tree.types.items()):
        if decl.kind != "class":
            continue
        # Instantiation looks like `AS_Foo x;` / `new AS_Foo(` / `AS_Foo *p`.
        uses = re.findall(rf"\b{re.escape(name)}\b", joined)
        # One hit is the declaration itself; anything referencing it adds more.
        if len(uses) <= 1:
            out.append(
                Finding(
                    "DEAD_TYPE",
                    str(decl.file.name),
                    0,
                    f"class `{name}` is declared but never referenced",
                )
            )
    return out
