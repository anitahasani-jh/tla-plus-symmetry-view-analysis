"""Debug helper: parse a source snippet and dump the AST."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from symview.lex import tokenize  # noqa: E402
from symview.parse_tla import Parser, parse_source  # noqa: E402
from symview.util import ensure_utf8_stdio  # noqa: E402

SNIPPETS = [
    "---- MODULE T ----\nA == [Next]_vars\n====\n",
    "---- MODULE T ----\nA == [][V!Next]_<<votes, maxBal>>\n====\n",
    "---- MODULE T ----\nA == <<Next>>_vars\n====\n",
    "---- MODULE T ----\nA == [x \\in S |-> 1]\n====\n",
]


def dump(source: str) -> None:
    lex = tokenize(source)
    print("TOKENS:", [(t.kind, t.text) for t in lex.tokens])
    parser = Parser(lex.tokens)
    ast = parser.parse_file()
    print(ast.render())
    print("NOTES:", parser.notes[:5])
    print("-" * 70)


def main() -> int:
    ensure_utf8_stdio()
    if len(sys.argv) > 1:
        for path in sys.argv[1:]:
            ast, lex, stats = parse_source(Path(path).read_text(encoding="utf-8"), path)
            print(stats["module"], "unknown:", stats["unknown_nodes"])
            print(ast.render())
        return 0
    for snippet in SNIPPETS:
        dump(snippet)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
