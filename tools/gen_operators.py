#!/usr/bin/env python3
"""Generate ``src/symview/operators.py`` from SANY's canonical operator table.

SymView does not re-implement the TLA+ operator table by hand: it is extracted
mechanically from the upstream SANY parser source vendored at
``third_party/tlaplus/tla2sany_parser_Operators.java`` (MIT licence, see the
NOTICE in that directory) so that precedences, associativity, fixity and the
Unicode/ASCII synonyms are exactly the ones TLC itself uses.

    python tools/gen_operators.py            # regenerate
    python tools/gen_operators.py --check    # fail if the generated file is stale
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JAVA = ROOT / "third_party" / "tlaplus" / "tla2sany_parser_Operators.java"
OUT = ROOT / "src" / "symview" / "operators.py"

UPSTREAM = "tlaplus/tlaplus@309e489a512e8017f1cdc8388fa6a5e8a01cf597"
UPSTREAM_PATH = "tlatools/org.lamport.tlatools/src/tla2sany/parser/Operators.java"

OPERATOR_RE = re.compile(
    r'new\s+Operator\(\s*"((?:[^"\\]|\\.)*)"\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*'
    r'Operators\.(assoc\w+)\s*,\s*Operators\.(\w+)\s*\)')
SYNONYM_RE = re.compile(r'new\s+String\[\]\s*\{([^}]*)\}')
STRING_RE = re.compile(r'"((?:[^"\\]|\\.)*)"')


def unescape(raw: str) -> str:
    out, i = [], 0
    while i < len(raw):
        ch = raw[i]
        if ch == "\\" and i + 1 < len(raw):
            nxt = raw[i + 1]
            mapping = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\"}
            out.append(mapping.get(nxt, nxt))
            i += 2
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def build() -> str:
    text = JAVA.read_text(encoding="utf-8")
    body = text.split("CanonicalOperators = {", 1)[1].split("};", 1)[0]
    synonyms_body = text.split("OperatorSynonyms = new String[][] {", 1)[1].split("};", 1)[0]

    canonical: list[tuple[str, int, int, str, str]] = []
    for match in OPERATOR_RE.finditer(body):
        symbol, low, high, assoc, fix = match.groups()
        canonical.append((unescape(symbol), int(low), int(high),
                          assoc.replace("assoc", "").lower(), fix))

    alias: dict[str, str] = {}
    for match in SYNONYM_RE.finditer(synonyms_body):
        strings = [unescape(s) for s in STRING_RE.findall(match.group(1))]
        if not strings:
            continue
        canon = strings[0]
        for alt in strings[1:]:
            alias[alt] = canon

    lines = [
        '"""TLA+ operator table extracted mechanically from SANY.',
        "",
        f"Upstream: {UPSTREAM}",
        f"File:     {UPSTREAM_PATH}",
        "Regenerate with ``python tools/gen_operators.py``.  Do not edit by hand.",
        "",
        "Each entry is ``OpSpec(canonical, low, high, assoc, fix)`` where ``low``",
        "and ``high`` are SANY's precedence *range* (an operator binds operands",
        "whose precedence lies in that range), ``assoc`` is one of",
        "left/right/none/nonassoc and ``fix`` is one of prefix/infix/postfix/nfix.",
        '"""',
        "",
        "from __future__ import annotations",
        "",
        "from dataclasses import dataclass",
        "",
        f'UPSTREAM_COMMIT = "{UPSTREAM}"',
        f'UPSTREAM_FILE = "{UPSTREAM_PATH}"',
        "",
        "",
        "@dataclass(frozen=True)",
        "class OpSpec:",
        "    canonical: str",
        "    low: int",
        "    high: int",
        "    assoc: str",
        "    fix: str",
        "",
        "    @property",
        "    def prec(self) -> int:",
        "        return self.low",
        "",
        "",
        "CANONICAL: dict[str, OpSpec] = {",
    ]
    for symbol, low, high, assoc, fix in canonical:
        lines.append(f"    {symbol!r}: OpSpec({symbol!r}, {low}, {high}, {assoc!r}, {fix!r}),")
    lines.append("}")
    lines += ["", "ALIASES: dict[str, str] = {"]
    for alt, canon in sorted(alias.items()):
        lines.append(f"    {alt!r}: {canon!r},")
    lines += [
        "}",
        "",
        "OPERATORS: dict[str, OpSpec] = {}",
        "for _spec in CANONICAL.values():",
        "    OPERATORS[_spec.canonical] = _spec",
        "for _alt, _canon in ALIASES.items():",
        "    OPERATORS[_alt] = CANONICAL[_canon]",
        "",
        "",
        "def spec_of(text: str) -> OpSpec | None:",
        "    \"\"\"Return the SANY operator spec for a lexed operator token, if any.\"\"\"",
        "    return OPERATORS.get(text)",
        "",
        "",
        "def is_operator(text: str) -> bool:",
        "    return text in OPERATORS",
        "",
        "",
        "def all_spellings() -> list[str]:",
        "    \"\"\"Every accepted spelling, longest first (needed by the lexer).\"\"\"",
        "    return sorted(OPERATORS, key=lambda s: (-len(s), s))",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    generated = build()
    if args.check:
        current = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
        if current != generated:
            print(f"[stale] {OUT} differs from the vendored SANY table", file=sys.stderr)
            return 1
        print("[ok] operator table is up to date")
        return 0
    OUT.write_text(generated, encoding="utf-8")
    print(f"[ok] wrote {OUT.relative_to(ROOT)} "
          f"({len(build().splitlines())} lines)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
