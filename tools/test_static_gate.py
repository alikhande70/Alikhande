#!/usr/bin/env python3
"""Self-tests for the static gate.

A linter nobody trusts gets disabled, and the fastest way to lose trust is a
false positive. Every check therefore gets both a positive case (it fires when
it should) and a negative case (it stays quiet on correct code).

Run: python3 tools/test_static_gate.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mql5lint import checks  # noqa: E402
from mql5lint.lexer import balance_report, strip  # noqa: E402
from mql5lint.model import SourceTree  # noqa: E402

FAILURES: list[str] = []
RUN = 0


def check(condition: bool, label: str) -> None:
    global RUN
    RUN += 1
    if condition:
        print(f"  [ ok ] {label}")
    else:
        print(f"  [FAIL] {label}")
        FAILURES.append(label)


def tree_from(files: dict[str, str]) -> SourceTree:
    """Build a SourceTree from an in-memory {relative_path: source} map."""
    tmp = Path(tempfile.mkdtemp())
    include_root = tmp / "MQL5" / "Include"
    paths = []
    for rel, body in files.items():
        p = tmp / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
        paths.append(p)
    t = SourceTree(root=tmp, include_root=include_root)
    t.load(paths)
    return t


def codes(findings) -> set[str]:
    return {f.code for f in findings}


# ------------------------------------------------------------------ lexer


def test_lexer() -> None:
    print("lexer")
    s = strip('int a; // } not a brace\nint b;')
    check(s.text.count("}") == 0, "line comment contents blanked")

    s = strip('string x = "a { b } c"; int y;')
    check(s.text.count("{") == 0, "string literal contents blanked")

    s = strip('/* } */ int a;')
    check(s.text.count("}") == 0, "block comment contents blanked")

    original = 'int a;\nint b;\nint c;'
    s = strip(original)
    check(len(s.text) == len(original), "offsets preserved exactly")
    check(s.line_of(original.index("b")) == 2, "line mapping correct")

    check(balance_report("{ ( ) }") == [], "balanced brackets report nothing")
    check(any(k.startswith("UNCLOSED") for k, _ in balance_report("{ (")), "unclosed detected")
    check(any(k.startswith("UNEXPECTED") for k, _ in balance_report("}")), "unexpected closer detected")
    check(any(k.startswith("MISMATCH") for k, _ in balance_report("( ]")), "mismatched pair detected")


# ------------------------------------------------------------------ model


def test_member_extraction() -> None:
    print("member extraction")
    t = tree_from({
        "MQL5/Include/A.mqh": (
            "#pragma once\n"
            "struct AS_Packed {\n"
            "   string a; string b; double c;\n"   # several declarations, one line
            "   int d,e,f;\n"                       # comma list
            "   double arr[10];\n"                  # array declarator
            "};\n"
        )
    })
    m = t.types["AS_Packed"].members
    for name in "abcdef":
        check(name in m, f"multi-declaration line yields `{name}`")
    check("arr" in m, "array declarator yields `arr`")


def test_include_resolution_uses_original_text() -> None:
    print("include resolution")
    t = tree_from({
        "MQL5/Include/AlikhandeScanner/Core/Version.mqh": "#pragma once\n",
        "MQL5/Include/AlikhandeScanner/Core/User.mqh":
            '#pragma once\n#include "Version.mqh"\n',
    })
    # Include paths live inside string literals; the lexer blanks their contents,
    # so this only passes if includes are read from the original source.
    check(codes(checks.check_include_graph(t)) == set(), "relative include resolves")


# ----------------------------------------------------------------- checks


def test_unresolved_constants() -> None:
    print("unresolved constants")
    good = tree_from({
        "MQL5/Include/A.mqh": (
            "#pragma once\n"
            "#define AS_LIMIT 5\n"
            "enum ENUM_AS_DIR { AS_UP, AS_DOWN };\n"
            "string AS_Helper(){return \"\";}\n"
            "class AS_Thing { public: void Go(){ int x=AS_LIMIT; } };\n"
            "void Use(){ ENUM_AS_DIR d=AS_UP; AS_Helper(); AS_Thing t; }\n"
        )
    })
    check("UNRESOLVED_CONSTANT" not in codes(checks.check_unresolved_constants(good)),
          "defines, enum members, functions and classes all count as defined")

    bad = tree_from({"MQL5/Include/B.mqh": "#pragma once\nvoid f(){ int x=AS_TYPO_HERE; }\n"})
    check("UNRESOLVED_CONSTANT" in codes(checks.check_unresolved_constants(bad)),
          "undefined AS_ constant is reported")


def test_struct_field_access() -> None:
    print("struct field access")
    src = (
        "#pragma once\n"
        "struct AS_Plan { double entry; double stop; };\n"
    )
    good = tree_from({"MQL5/Include/A.mqh": src + "void f(){ AS_Plan p; double x=p.entry; }\n"})
    check(codes(checks.check_struct_field_access(good)) == set(), "valid member access is quiet")

    bad = tree_from({"MQL5/Include/A.mqh": src + "void f(){ AS_Plan p; double x=p.enrty; }\n"})
    check("UNKNOWN_MEMBER" in codes(checks.check_struct_field_access(bad)), "typo'd member reported")


def test_resize_without_init() -> None:
    print("resize without init")
    risky = tree_from({
        "MQL5/Experts/E.mq5": "datetime g_last[];\nvoid OnInit(){ ArrayResize(g_last,4); }\n"
    })
    check("RESIZE_WITHOUT_INIT" in codes(checks.check_resize_without_init(risky)),
          "file-scope array resized without init is reported")

    guarded = tree_from({
        "MQL5/Experts/E.mq5":
            "datetime g_last[];\nvoid OnInit(){ ArrayResize(g_last,4); ArrayInitialize(g_last,0); }\n"
    })
    check(codes(checks.check_resize_without_init(guarded)) == set(),
          "ArrayInitialize silences it")

    local = tree_from({
        "MQL5/Include/A.mqh":
            "#pragma once\n"
            "double Median(double &v[],int n){ double tmp[]; ArrayResize(tmp,n);"
            " for(int i=0;i<n;i++) tmp[i]=v[i]; return tmp[0]; }\n"
    })
    check(codes(checks.check_resize_without_init(local)) == set(),
          "local resize-then-fill is not flagged (no false positive)")


def test_invariants_scan_string_literals() -> None:
    print("invariant scan")
    t = tree_from({
        "MQL5/Include/A.mqh": '#pragma once\nvoid f(string &r){ r="REAL_ACCOUNT_BLOCKED"; }\n'
    })
    # The marker only exists inside a string literal, whose contents the lexer
    # blanks — this fails unless the check reads original source.
    found = checks.check_required_invariants(t, {"real block": "REAL_ACCOUNT_BLOCKED"})
    check(found == [], "invariant inside a string literal is detected")

    missing = checks.check_required_invariants(t, {"absent": "NOT_PRESENT_ANYWHERE"})
    check("MISSING_INVARIANT" in codes(missing), "absent invariant is reported")


def test_ordersend_boundary() -> None:
    print("OrderSend boundary")
    owner = "MQL5/Include/AlikhandeScanner/Execution/ExecutionEngine.mqh"
    t = tree_from({
        owner: "#pragma once\nvoid Send(){ OrderSend(a,b); }\n",
        "MQL5/Include/AlikhandeScanner/Trading/Other.mqh": "#pragma once\nvoid X(){ OrderSend(a,b); }\n",
    })
    found = checks.check_order_send_boundary(t, owner)
    check(len(found) == 1, "exactly the non-owner OrderSend is reported")
    check("Other.mqh" in found[0].rel, "the reported file is the violator, not the owner")


def test_include_cycle() -> None:
    print("include cycle")
    base = "MQL5/Include/AlikhandeScanner/"
    t = tree_from({
        base + "A.mqh": '#pragma once\n#include "B.mqh"\n',
        base + "B.mqh": '#pragma once\n#include "A.mqh"\n',
    })
    check("INCLUDE_CYCLE" in codes(checks.check_include_cycles(t)), "cycle detected")

    linear = tree_from({
        base + "A.mqh": '#pragma once\n#include "B.mqh"\n',
        base + "B.mqh": "#pragma once\n",
    })
    check(codes(checks.check_include_cycles(linear)) == set(), "acyclic graph is quiet")


def test_unchecked_copy() -> None:
    print("unchecked copy")
    bad = tree_from({"MQL5/Include/A.mqh": "#pragma once\nvoid f(){ CopyBuffer(h,0,0,3,buf); }\n"})
    check("UNCHECKED_COPY" in codes(checks.check_unchecked_copy(bad)), "bare CopyBuffer reported")

    good = tree_from({
        "MQL5/Include/A.mqh": "#pragma once\nvoid f(){ if(CopyBuffer(h,0,0,3,buf)!=3) return; }\n"
    })
    check(codes(checks.check_unchecked_copy(good)) == set(), "checked CopyBuffer is quiet")


def test_use_before_definition() -> None:
    print("use before definition")
    bad = tree_from({
        "MQL5/Include/A.mqh":
            "#pragma once\n"
            "class C { public: void Go(){ int x=Helper(); } };\n"
            "int Helper(){ return 1; }\n"
    })
    check("USE_BEFORE_DEFINITION" in codes(checks.check_use_before_definition(bad)),
          "global called before its definition is reported")

    good = tree_from({
        "MQL5/Include/A.mqh":
            "#pragma once\n"
            "int Helper(){ return 1; }\n"
            "class C { public: void Go(){ int x=Helper(); } };\n"
    })
    check(codes(checks.check_use_before_definition(good)) == set(),
          "correct ordering is quiet")

    # Class members may call each other in any order — not a forward reference.
    members = tree_from({
        "MQL5/Include/A.mqh":
            "#pragma once\n"
            "class C {\n"
            "  public: void First(){ Second(); }\n"
            "  private: void Second(){ }\n"
            "};\n"
    })
    check(codes(checks.check_use_before_definition(members)) == set(),
          "class members calling later members is not flagged (no false positive)")


def test_discarded_guard_results() -> None:
    print("discarded guard results")
    bad = tree_from({
        "MQL5/Include/A.mqh":
            "#pragma once\n"
            "void f(){ RecordDealOnce(t,a,b); volume += 1.0; }\n"
    })
    check("DISCARDED_GUARD_RESULT" in codes(
              checks.check_discarded_guard_results(bad, ["RecordDealOnce"])),
          "bare guard call is reported")

    guarded = tree_from({
        "MQL5/Include/A.mqh":
            "#pragma once\n"
            "void f(){ if(RecordDealOnce(t,a,b)) volume += 1.0; }\n"
    })
    check(codes(checks.check_discarded_guard_results(guarded, ["RecordDealOnce"])) == set(),
          "guard used in a condition is quiet")

    assigned = tree_from({
        "MQL5/Include/A.mqh":
            "#pragma once\n"
            "void f(){ bool ok = RecordDealOnce(t,a,b); }\n"
    })
    check(codes(checks.check_discarded_guard_results(assigned, ["RecordDealOnce"])) == set(),
          "guard whose result is assigned is quiet")


def test_unreachable_module() -> None:
    print("unreachable module")
    base = "MQL5/Include/AlikhandeScanner/"
    entry = "MQL5/Experts/AlikhandeScanner/AlikhandeScanner.mq5"
    t = tree_from({
        entry: '#include <AlikhandeScanner/Used.mqh>\nvoid OnTick(){}\n',
        base + "Used.mqh": "#pragma once\n",
        base + "Orphan.mqh": "#pragma once\n",
        # Harness code is legitimately unreachable from the EA.
        base + "Testing/Harness.mqh": "#pragma once\n",
    })
    found = checks.check_unreachable_from_entrypoint(t, entry)
    rels = {f.rel.replace("\\", "/") for f in found}
    check(any("Orphan.mqh" in r for r in rels), "orphaned module is reported")
    check(not any("Used.mqh" in r for r in rels), "included module is not reported")
    check(not any("Harness.mqh" in r for r in rels),
          "test harness is exempt (no false positive)")


def main() -> int:
    for fn in (
        test_lexer,
        test_member_extraction,
        test_include_resolution_uses_original_text,
        test_unresolved_constants,
        test_struct_field_access,
        test_resize_without_init,
        test_invariants_scan_string_literals,
        test_ordersend_boundary,
        test_include_cycle,
        test_unchecked_copy,
        test_use_before_definition,
        test_discarded_guard_results,
        test_unreachable_module,
    ):
        fn()

    print()
    if FAILURES:
        print(f"RESULT: FAIL — {len(FAILURES)}/{RUN} assertions failed")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print(f"RESULT: PASS — {RUN}/{RUN} assertions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
