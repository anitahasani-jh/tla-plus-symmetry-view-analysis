"""Quick parser sanity check over the probe spec and a few corpus specs."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from symview.parse_tla import parse_file  # noqa: E402
from symview.util import ensure_utf8_stdio  # noqa: E402


def show(path: Path) -> None:
    ast, lex, stats = parse_file(path)
    print(f"== {path.name}: module={stats['module']} bad={stats['bad_tokens']} "
          f"unknown={stats['unknown_nodes']} notes={stats['parser_notes']} "
          f"cov={stats['cov_coverage']:.3f} uncov={len(stats['cov_uncovered_tokens'])} "
          f"proofskip={stats['proof_tokens_skipped']}")
    if stats["unknown_nodes"]:
        for node in ast.walk():
            if node.kind == "unknown" and node.line:
                print(f"     unknown @{node.line}:{node.col} {node.text} tok={node.note!r}")
    if stats["cov_uncovered_tokens"]:
        idx = stats["cov_uncovered_tokens"][:12]
        print("     uncovered tokens:", [(lex.tokens[i].kind, lex.tokens[i].text,
                                          lex.tokens[i].line) for i in idx])


def main() -> int:
    ensure_utf8_stdio()
    targets = [Path(p) for p in sys.argv[1:]]
    for target in targets:
        show(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
