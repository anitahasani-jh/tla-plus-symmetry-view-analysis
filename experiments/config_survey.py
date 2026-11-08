#!/usr/bin/env python3
"""Survey the configuration files of the public corpus.

Produces the numbers the soundness report cites about how the *community* uses
the two reductions: how many configurations ship a SYMMETRY or a VIEW, how many
check temporal properties, and -- the interesting part -- how many contain a
**commented out** reduction with a warning, which is direct evidence that the
configuration is easy to get wrong.

    python experiments/config_survey.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from symview.parse_cfg import parse_config_file  # noqa: E402
from symview.util import ensure_utf8_stdio, write_json  # noqa: E402

OUT = ROOT / "results" / "raw" / "config_survey.json"
DISABLED_RE = re.compile(r"^\s*\\?\*+\s*(SYMMETRY|VIEW)\b", re.IGNORECASE)
WARNING_WORDS = ("LIVENESS", "liveness", "does not work", "DOES NOT WORK",
                 "unsound", "wrong")


def main() -> int:
    ensure_utf8_stdio()
    cfgs = sorted((ROOT / "benchmarks" / "public").rglob("*.cfg"))
    rows = []
    disabled = []
    for path in cfgs:
        text = path.read_text(encoding="utf-8", errors="replace")
        cfg = parse_config_file(path)
        row = {
            "file": str(path.relative_to(ROOT)).replace("\\", "/"),
            "model": path.stem,
            "has_init": bool(cfg.init or cfg.specification),
            "symmetry": cfg.symmetry,
            "view": cfg.view,
            "properties": cfg.properties,
            "invariants": cfg.invariants,
            "check_deadlock": cfg.check_deadlock,
        }
        rows.append(row)
        lines = text.splitlines()
        for index, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("\\*") and re.search(r"\b(SYMMETRY|VIEW)\b", stripped):
                context = " ".join(lines[max(0, index - 2): index + 1])
                disabled.append({
                    "file": row["file"],
                    "line": stripped[:160],
                    "warns": any(word in context for word in WARNING_WORDS),
                })
    summary = {
        "configurations": len(rows),
        "with_model": sum(1 for r in rows if r["has_init"]),
        "with_symmetry": sum(1 for r in rows if r["symmetry"]),
        "with_view": sum(1 for r in rows if r["view"]),
        "with_properties": sum(1 for r in rows if r["properties"]),
        "with_invariants_only": sum(1 for r in rows
                                    if r["invariants"] and not r["properties"]),
        "disabled_reduction_lines": len(disabled),
        "disabled_with_warning": sum(1 for d in disabled if d["warns"]),
        "symmetry_examples": [{"file": r["file"], "operator": r["symmetry"]}
                              for r in rows if r["symmetry"]],
        "view_examples": [{"file": r["file"], "operator": r["view"]}
                          for r in rows if r["view"]],
        "disabled": disabled,
    }
    write_json(OUT, {"summary": summary, "configurations": rows})
    print(json.dumps(summary, indent=2, ensure_ascii=False)[:1800])
    print(f"\n[ok] {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
