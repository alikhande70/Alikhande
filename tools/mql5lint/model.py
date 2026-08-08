"""Lightweight structural model of an MQL5 source tree.

This is deliberately *not* a full parser. It extracts the declarations the
checks actually need — includes, `#define`s, enum members, struct fields, class
methods — using regex over comment/string-stripped source. Anything it cannot
confidently parse it simply does not report on, so the analyzer stays free of
false positives at the cost of some false negatives.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .lexer import StrippedSource, strip

INCLUDE_RE = re.compile(r'#include\s+[<"]([^>"]+)[>"]')
DEFINE_RE = re.compile(r"^[ \t]*#define[ \t]+([A-Za-z_]\w*)", re.M)
ENUM_RE = re.compile(r"\benum\s+(\w+)\s*\{([^}]*)\}", re.S)
STRUCT_RE = re.compile(r"\bstruct\s+(\w+)\s*\{", re.S)
CLASS_RE = re.compile(r"\bclass\s+(\w+)\s*(?::[^{]*)?\{", re.S)
IDENT_RE = re.compile(r"\b([A-Za-z_]\w*)\b")
# Free functions: `string AS_Fnv1a(const string text) {`
FUNC_DEF_RE = re.compile(r"\b[A-Za-z_]\w*\s+([A-Za-z_]\w*)\s*\([^;{}]*\)\s*\{")


@dataclass
class TypeDecl:
    name: str
    kind: str  # "struct" | "class"
    file: Path
    members: set[str] = field(default_factory=set)


@dataclass
class SourceFile:
    path: Path
    rel: str
    stripped: StrippedSource
    includes: list[str] = field(default_factory=list)
    defines: set[str] = field(default_factory=set)
    enum_members: set[str] = field(default_factory=set)
    enum_types: set[str] = field(default_factory=set)
    functions: set[str] = field(default_factory=set)

    @property
    def text(self) -> str:
        return self.stripped.text

    def line_of(self, index: int) -> int:
        return self.stripped.line_of(index)


def _find_matching_brace(text: str, open_index: int) -> int:
    """Index of the `}` matching the `{` at `open_index`, or -1."""
    depth = 0
    for i in range(open_index, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return i
    return -1


# Field declarations look like `double entry_low;` or `string a,b,c;`, and the
# codebase freely packs several onto one physical line. Splitting on `;` rather
# than anchoring to line starts is what makes multi-declaration lines work.
DECLARATOR_RE = re.compile(
    r"^\s*(?:static\s+|const\s+|virtual\s+|unsigned\s+)*"
    r"([A-Za-z_]\w*)\s+"              # type
    r"([^{}()]+)$"                     # declarator list
)


def _extract_members(body: str) -> set[str]:
    members: set[str] = set()
    # Drop nested braces (method bodies, initialiser blocks) so only the
    # declaration level of the type is considered.
    depth = 0
    flat_chars: list[str] = []
    for ch in body:
        if ch == "{":
            depth += 1
            continue
        if ch == "}":
            depth = max(0, depth - 1)
            continue
        if depth == 0:
            flat_chars.append(ch)
    flat = "".join(flat_chars)

    for segment in flat.split(";"):
        m = DECLARATOR_RE.match(segment)
        if not m:
            continue
        for part in m.group(2).split(","):
            part = part.strip().lstrip("*&")
            part = re.sub(r"\[.*?\]", "", part)
            part = part.split("=")[0].strip()
            if re.fullmatch(r"[A-Za-z_]\w*", part):
                members.add(part)
    return members


def _extract_methods(body: str) -> set[str]:
    """Method names: `ret Name(` at declaration depth."""
    names: set[str] = set()
    for m in re.finditer(r"\b([A-Za-z_]\w*)\s*\(", body):
        names.add(m.group(1))
    return names


class SourceTree:
    def __init__(self, root: Path, include_root: Path):
        self.root = root
        self.include_root = include_root
        self.files: dict[Path, SourceFile] = {}
        self.types: dict[str, TypeDecl] = {}

    # ------------------------------------------------------------------ load

    def load(self, paths: list[Path]) -> None:
        # Keys are resolved absolute paths so they always compare equal to what
        # resolve_include() returns. Mixing relative and resolved paths made
        # every include lookup miss, which silently reported the entire tree as
        # unreachable — a check that can fail *open* like that is worse than no
        # check, because the output looks like a real finding.
        self.root = self.root.resolve()
        self.include_root = self.include_root.resolve()
        for p in sorted({q.resolve() for q in paths}):
            raw = p.read_text(encoding="utf-8", errors="replace")
            sf = SourceFile(
                path=p,
                rel=str(p.relative_to(self.root)),
                stripped=strip(raw),
            )
            # Include paths live *inside* string literals, whose contents the
            # lexer blanks — so these must come from the original text.
            sf.includes = INCLUDE_RE.findall(raw)
            sf.defines = set(DEFINE_RE.findall(sf.text))
            sf.functions = set(FUNC_DEF_RE.findall(sf.text))
            for enum_name, body in ENUM_RE.findall(sf.text):
                sf.enum_types.add(enum_name)
                for token in re.findall(r"\b([A-Za-z_]\w*)\b", body):
                    # Skip values in `NAME=123` right-hand sides that are idents.
                    sf.enum_members.add(token)
            self.files[p] = sf

        self._index_types()

    def _index_types(self) -> None:
        for sf in self.files.values():
            for regex, kind in ((STRUCT_RE, "struct"), (CLASS_RE, "class")):
                for m in regex.finditer(sf.text):
                    open_brace = sf.text.index("{", m.end() - 1)
                    close = _find_matching_brace(sf.text, open_brace)
                    if close < 0:
                        continue
                    body = sf.text[open_brace + 1 : close]
                    decl = self.types.get(m.group(1))
                    if decl is None:
                        decl = TypeDecl(name=m.group(1), kind=kind, file=sf.path)
                        self.types[m.group(1)] = decl
                    decl.members |= _extract_members(body)
                    if kind == "class":
                        decl.members |= _extract_methods(body)

    # --------------------------------------------------------------- queries

    @property
    def all_defines(self) -> set[str]:
        out: set[str] = set()
        for sf in self.files.values():
            out |= sf.defines
        return out

    @property
    def all_enum_members(self) -> set[str]:
        out: set[str] = set()
        for sf in self.files.values():
            out |= sf.enum_members
        return out

    @property
    def all_enum_types(self) -> set[str]:
        out: set[str] = set()
        for sf in self.files.values():
            out |= sf.enum_types
        return out

    @property
    def all_functions(self) -> set[str]:
        out: set[str] = set()
        for sf in self.files.values():
            out |= sf.functions
        return out

    def resolve_include(self, sf: SourceFile, spec: str) -> Path | None:
        """Resolve an `#include` the way MetaEditor does.

        `"..."` is relative to the including file; `<...>` is relative to the
        MQL5/Include root. We try both for either form because the codebase
        mixes them and MetaEditor tolerates it.
        """
        candidates = [
            (sf.path.parent / spec).resolve(),
            (self.include_root / spec).resolve(),
        ]
        for c in candidates:
            if c.is_file():
                return c
        return None
