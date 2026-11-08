"""Smoke test: the generated operator table matches SANY's canonical table."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from symview import operators as O  # noqa: E402
from symview.util import ensure_utf8_stdio  # noqa: E402

LAND = "\\" + "land"
IN = "\\" + "in"
LEQ = "\\" + "leq"
TIMES = "\\" + "X"


def main() -> int:
    ensure_utf8_stdio()
    print("canonical:", len(O.CANONICAL), "aliases:", len(O.ALIASES),
          "spellings:", len(O.OPERATORS))
    checks = [
        ("/" + "\\", O.CANONICAL[LAND].low, 30, "left", "infix"),
        (IN, O.CANONICAL[IN].low, 50, "none", "infix"),
        ("<=", O.CANONICAL[LEQ].low, 50, "none", "infix"),
        (TIMES, O.CANONICAL["\\" + "times"].low, 100, "left", "nfix"),
        ("~>", O.CANONICAL["~>"].low, 20, "none", "infix"),
        ("\u2264", O.CANONICAL[LEQ].low, 50, "none", "infix"),
    ]
    ok = True
    for spelling, got, want, assoc, fix in checks:
        spec = O.spec_of(spelling)
        good = spec is not None and spec.low == want and spec.assoc == assoc and spec.fix == fix
        ok &= good
        print(("  ok  " if good else " FAIL "), repr(spelling), spec)
    longest = O.all_spellings()[:6]
    print("longest-first spellings:", longest)
    assert O.all_spellings() == sorted(O.OPERATORS, key=lambda s: (-len(s), s))
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
