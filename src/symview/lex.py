"""TLA+ lexer.

Tokenises a ``.tla`` module.  The operator spellings (including Unicode
synonyms) come from :mod:`symview.operators`, which is generated mechanically
from SANY's own table, so the lexer and TLC agree on what an operator is.

Design notes
------------
* Module banner lines (``---- MODULE Foo ----``, ``====``) are line oriented and
  are recognised only at the start of a line, so a decorative rule inside a
  comment cannot confuse the scanner.
* Comments (``\\*`` to end of line and nested ``(* ... *)``) are dropped.
* Unknown characters never abort the scan: they become ``BAD`` tokens so that
  the caller can report exact parse coverage instead of crashing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .operators import OPERATORS, all_spellings

# Structural punctuation that SANY's operator table does not contain because it
# belongs to the grammar rather than to the expression language.
PUNCTUATION = [
    "|->", "|_", "<<", ">>", "==", "->", "<-", "::", "(", ")", "[", "]", "{",
    "}", ",", ";", ":", "!", "@", "_", ".",
]

# Tokens that are grammar structure rather than operators, even though a few of
# them also appear in SANY's operator table (``[`` as postfix subscript, ``.``
# as record access).  The parser decides their meaning from context.
STRUCTURAL = {
    "(", ")", "[", "]", "{", "}", "<<", ">>", ",", ";", ":", "==", "->", "<-",
    "|->", "|_", "_", "!", "@", "::",
}

# Word shaped tokens that are reserved even though they look like identifiers.
RESERVED_OPERATORS = {"ENABLED", "UNCHANGED", "SUBSET", "UNION", "DOMAIN"}

# Quantifier symbols.  SANY handles these in its grammar rather than in the
# operator table, so they are added here; longest-match still prefers
# ``\equiv`` over ``\E``.
SYMBOLIC_KEYWORDS = {"\\A", "\\E", "\u2200", "\u2203"}

KEYWORDS = {
    "MODULE", "EXTENDS", "CONSTANT", "CONSTANTS", "VARIABLE", "VARIABLES",
    "ASSUME", "ASSUMPTION", "THEOREM", "PROPOSITION", "LEMMA", "COROLLARY",
    "INSTANCE", "WITH", "LET", "IN", "IF", "THEN", "ELSE", "CASE", "OTHER",
    "CHOOSE", "LOCAL", "RECURSIVE", "EXCEPT", "LAMBDA", "NEW", "STATE", "ACTION",
    "TEMPORAL", "USE", "DEFINE", "HIDE", "RECALL", "HAVE", "TAKE", "SUFFICES",
    "PICK", "PROOF", "PROVE", "STEP", "BY", "OBVIOUS", "OMITTED", "QED",
    "WITNESS", "DEF", "ONLY", "TRUE", "FALSE", "BOOLEAN", "ELSE",
}

PROOF_KEYWORDS = {
    "BY", "OBVIOUS", "OMITTED", "PROOF", "QED", "USE", "DEFINE", "HIDE",
    "RECALL", "HAVE", "TAKE", "SUFFICES", "PICK", "WITNESS", "DEF", "ONLY",
}

UNIT_KEYWORDS = {
    "EXTENDS", "CONSTANT", "CONSTANTS", "VARIABLE", "VARIABLES", "ASSUME",
    "ASSUMPTION", "THEOREM", "PROPOSITION", "LEMMA", "COROLLARY", "INSTANCE",
    "LOCAL", "RECURSIVE", "USE", "DEFINE", "HIDE", "MODULE",
}

IDENT_START = re.compile(r"[A-Za-z_\u00c0-\uffff]")
IDENT_REST = re.compile(r"[A-Za-z0-9_\u00c0-\uffff]")
NUM_RE = re.compile(r"(?:\\B[01]+|0b[01]+|\d+)")

# Combined longest-match table: operator spellings + punctuation.
_MATCH_TABLE: list[str] | None = None


def match_table() -> list[str]:
    """All symbolic tokens, longest first, so that ``-+->`` beats ``-``."""
    global _MATCH_TABLE
    if _MATCH_TABLE is None:
        symbolic = {s for s in OPERATORS if not IDENT_START.match(s[0])}
        _MATCH_TABLE = sorted(symbolic | set(PUNCTUATION) | SYMBOLIC_KEYWORDS,
                              key=lambda s: (-len(s), s))
    return _MATCH_TABLE


@dataclass(frozen=True)
class Tok:
    """One lexical token.

    ``kind`` is one of NAME, KEY, OP, NUM, STR, PUNCT, BANNER, FOOTER, BAD, EOF.
    """

    kind: str
    text: str
    line: int
    col: int
    idx: int = 0

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"{self.kind}({self.text!r}@{self.line}:{self.col})"


@dataclass
class LexResult:
    tokens: list[Tok] = field(default_factory=list)
    module_name: str | None = None
    bad_tokens: list[Tok] = field(default_factory=list)
    lines: int = 0
    chars: int = 0

    @property
    def ok(self) -> bool:
        return not self.bad_tokens


def tokenize(source: str) -> LexResult:
    result = LexResult(chars=len(source), lines=source.count("\n") + 1)
    tokens: list[Tok] = []
    i, n = 0, len(source)
    line, col = 1, 1
    line_start = 0
    at_line_start = True
    table = match_table()

    def push(kind: str, text: str, start_line: int, start_col: int) -> Tok:
        tok = Tok(kind, text, start_line, start_col, len(tokens))
        tokens.append(tok)
        return tok

    while i < n:
        ch = source[i]

        if ch == "\n":
            i += 1
            line += 1
            col = 1
            line_start = i
            at_line_start = True
            continue
        if ch in " \t\r\f\v":
            i += 1
            col += 1
            continue

        if at_line_start and i == line_start:
            banner = re.compile(r"-{4,}").match(source, i)
            footer = re.compile(r"={4,}").match(source, i)
            if banner or footer:
                end = source.find("\n", i)
                end = n if end < 0 else end
                text = source[i:end]
                if footer:
                    push("FOOTER", text.strip(), line, col)
                else:
                    module_match = re.search(r"MODULE\s+([A-Za-z0-9_]+)", text)
                    if module_match:
                        result.module_name = module_match.group(1)
                        push("BANNER", module_match.group(1), line, col)
                i, col, at_line_start = end, col + (end - i), False
                continue

        at_line_start = False

        if source.startswith("\\*", i):
            end = source.find("\n", i)
            i = n if end < 0 else end
            continue
        if source.startswith("(*", i):
            depth, j = 1, i + 2
            while j < n and depth:
                if source.startswith("(*", j):
                    depth += 1
                    j += 2
                elif source.startswith("*)", j):
                    depth -= 1
                    j += 2
                else:
                    if source[j] == "\n":
                        line += 1
                        col = 0
                    j += 1
                    col += 1
            i = j
            continue

        start_line, start_col = line, col

        if ch == '"':
            j = i + 1
            while j < n:
                if source[j] == "\\" and j + 1 < n:
                    j += 2
                    continue
                if source[j] == '"':
                    j += 1
                    break
                if source[j] == "\n":
                    line += 1
                j += 1
            text = source[i:j]
            push("STR", text, start_line, start_col)
            col += j - i
            i = j
            continue

        num = NUM_RE.match(source, i)
        if num and not (i > 0 and IDENT_REST.match(source[i - 1])):
            push("NUM", num.group(0), start_line, start_col)
            col += num.end() - i
            i = num.end()
            continue

        if IDENT_START.match(ch):
            j = i
            while j < n and IDENT_REST.match(source[j]):
                j += 1
            text = source[i:j]
            if text == "_":
                # A lone underscore is the subscript marker of ``[A]_v`` and the
                # placeholder of ``f(_, _)``; ``_vars`` however stays one name.
                push("PUNCT", text, start_line, start_col)
            elif text in RESERVED_OPERATORS:
                push("OP", text, start_line, start_col)
            elif text in KEYWORDS:
                push("KEY", text, start_line, start_col)
            else:
                push("NAME", text, start_line, start_col)
            col += j - i
            i = j
            continue

        matched = None
        for candidate in table:
            if source.startswith(candidate, i):
                matched = candidate
                break
        if matched is not None:
            if matched in SYMBOLIC_KEYWORDS:
                matched_kind = "KEY"
            elif matched in STRUCTURAL:
                matched_kind = "PUNCT"
            else:
                matched_kind = "OP"
            push(matched_kind, matched, start_line, start_col)
            col += len(matched)
            i += len(matched)
            continue

        push("BAD", ch, start_line, start_col)
        result.bad_tokens.append(tokens[-1])
        col += 1
        i += 1

    push("EOF", "", line, col)
    result.tokens = tokens
    return result
