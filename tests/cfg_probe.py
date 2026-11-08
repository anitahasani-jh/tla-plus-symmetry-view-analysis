"""Parse every .cfg in the corpus and report what the parser did not understand."""

from __future__ import annotations

import collections
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from symview.parse_cfg import parse_config_file  # noqa: E402
from symview.util import ensure_utf8_stdio  # noqa: E402


def main() -> int:
    ensure_utf8_stdio()
    files = sorted((ROOT / "benchmarks" / "public").rglob("*.cfg"))
    unknown_kw: collections.Counter[str] = collections.Counter()
    unknown_tok: collections.Counter[str] = collections.Counter()
    no_model = []
    with_symmetry = []
    with_view = []
    with_liveness = []
    for path in files:
        cfg = parse_config_file(path)
        for kw in cfg.unknown_keywords:
            unknown_kw[kw] += 1
        for tok in cfg.unknown_tokens:
            unknown_tok[tok] += 1
        if not (cfg.init or cfg.specification):
            no_model.append(path.name)
        if cfg.symmetry:
            with_symmetry.append(f"{path.parent.name}/{path.name}: {cfg.symmetry}")
        if cfg.view:
            with_view.append(f"{path.parent.name}/{path.name}: {cfg.view}")
        if cfg.properties:
            with_liveness.append(f"{path.parent.name}/{path.name}: {','.join(cfg.properties)}")
    print(f"cfg files: {len(files)}")
    print(f"no INIT/SPECIFICATION: {len(no_model)} -> {no_model[:12]}")
    print(f"unknown keywords: {dict(unknown_kw)}")
    print(f"unknown stray tokens (top 12): {unknown_tok.most_common(12)}")
    print(f"\nshipped SYMMETRY ({len(with_symmetry)}):")
    for item in with_symmetry:
        print("   ", item)
    print(f"\nshipped VIEW ({len(with_view)}):")
    for item in with_view:
        print("   ", item)
    print(f"\nconfigs with temporal PROPERTIES ({len(with_liveness)}), first 15:")
    for item in with_liveness[:15]:
        print("   ", item)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
