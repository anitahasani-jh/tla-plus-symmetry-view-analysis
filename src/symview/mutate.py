"""Deterministic bug injection, used to measure violation preservation (RQ2).

A reduction is only useful if it still finds the bugs the unreduced model finds.
SymView therefore injects small, realistic faults into a copy of the
specification, keeps only the mutants that the *unreduced* run actually detects
(a mutant the baseline cannot see proves nothing about the reduction), and then
replays exactly those mutants under every reduction arm.

Injection is purely textual and never touches the corpus: the mutated module is
handed to TLC as an overlay file in the run directory.  Three operators are
implemented, all of which target the parts of a specification that guards live
in:

``drop-guard``
    delete one guard conjunct, making an action fire when it should not -- the
    classic mutual-exclusion / type-safety bug.
``flip-literal``
    turn a ``TRUE`` guard into ``FALSE`` (or the reverse), disabling or enabling
    a branch.
``weaken-comparison``
    turn ``<`` into ``<=`` and ``>`` into ``>=`` in a guard, an off-by-one.

Sites are chosen deterministically from a seed, and every mutant records the
exact source line it changed so a human can review the whole set.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass, field
from pathlib import Path

from .analysis.program import SpecProgram
from .astnodes import N

COMPARISON_FAMILY = {
    "<": "lt", "\\leq": "le", "<=": "le", "=<": "le",
    ">": "gt", "\\geq": "ge", ">=": "ge",
}
WEAKEN = {"lt": "<=", "le": "<", "gt": ">=", "ge": ">"}
ASSIGN_OPS = {"=", "\\in"}


@dataclass
class Site:
    kind: str
    module: str
    file: str
    line_start: int
    line_end: int
    col: int
    definition: str
    description: str
    source_op: str = ""
    replacement: str = ""
    t0: int = -1
    t1: int = -1


@dataclass
class Mutant:
    mutant_id: str
    model_id: str
    operator: str
    module: str
    file: str
    description: str
    line: int
    original_snippet: str
    mutated_snippet: str
    content: str = ""
    detected: bool | None = None
    baseline_verdict: str | None = None
    violated: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        payload = {k: v for k, v in self.__dict__.items() if k != "content"}
        return payload


def _line_offsets(text: str) -> list[int]:
    offsets = [0]
    for line in text.splitlines(keepends=True):
        offsets.append(offsets[-1] + len(line))
    return offsets


def _offset(text: str, line: int, col: int) -> int:
    offsets = _line_offsets(text)
    index = min(max(line - 1, 0), len(offsets) - 1)
    return offsets[index] + max(col - 1, 0)


def _max_line(node: N) -> int:
    lines = [leaf.line for leaf in node.walk() if leaf.line]
    return max(lines) if lines else node.line


def _is_assignment(node: N) -> bool:
    if node.kind == "infix" and node.text in ASSIGN_OPS:
        lhs = node.kid("lhs")
        return lhs is not None and lhs.kind == "postfix" and lhs.text == "'"
    return node.kind == "prefix" and node.text == "UNCHANGED"


def _spelling_at(text: str, line: int, col: int, canonical: str,
                 aliases: list[str]) -> str | None:
    start = _offset(text, line, col)
    for spelling in sorted([canonical] + aliases, key=len, reverse=True):
        if text.startswith(spelling, start):
            return spelling
    return None


def _start_pos(node: N, tokens) -> tuple[int, int]:
    """Source position of the first token of a node.

    ``N.line``/``N.col`` point at the node's *operator* for infix nodes, so the
    token span is the only reliable way to find where a conjunct begins.
    """
    if tokens and 0 <= node.t0 < len(tokens):
        token = tokens[node.t0]
        return token.line, token.col
    return node.line, node.col


def _starts_bullet_line(source_lines: list[str], line: int, col: int) -> bool:
    """True if the node begins a line whose only prefix is a bullet.

    Deleting a line is only safe when nothing else shares it, so the text before
    the node has to be empty or a single ``/\\`` / ``\\/``.
    """
    if not (0 < line <= len(source_lines)):
        return False
    prefix = source_lines[line - 1][: max(0, col - 1)]
    return prefix.strip() in ("", "/\\", "\\/")


def collect_sites(program: SpecProgram) -> list[Site]:
    ctx = program.ctx
    sites: list[Site] = []
    skip_defs = set(program.invariant_names + program.property_names)
    if program.init_name:
        skip_defs.add(program.init_name.split("!")[-1])
    for module_name, ast in ctx.modules.items():
        file_path = ctx.module_files.get(module_name)
        if not file_path:
            continue
        source_path = Path(file_path)
        if source_path.parent.resolve() != ctx.spec_dir.resolve():
            continue      # support/community module, not part of this model
        source = source_path.read_text(encoding="utf-8", errors="replace")
        source_lines = source.splitlines()
        tokens = ctx.module_tokens.get(module_name, [])
        for unit in ast.kids_in("unit"):
            if unit.kind != "opdef" or unit.text in skip_defs:
                continue
            body = unit.kid("body")
            if body is None:
                continue
            for node in body.walk():
                if node.kind == "infix" and node.text == "\\land":
                    for role in ("lhs", "rhs"):
                        conjunct = node.kid(role)
                        if conjunct is None or conjunct.kind == "unknown":
                            continue
                        if conjunct.kind == "infix" and conjunct.text == "\\land":
                            continue      # only leaf conjuncts
                        if _is_assignment(conjunct) or _is_type_invariant(conjunct):
                            continue
                        start_line, start_col = _start_pos(conjunct, tokens)
                        if conjunct.t0 < 0 or conjunct.t1 <= conjunct.t0:
                            continue
                        sites.append(Site(
                            kind="drop-guard", module=module_name,
                            file=Path(file_path).name, line_start=start_line,
                            line_end=_max_line(conjunct), col=start_col,
                            definition=unit.text,
                            description=f"replace a guard conjunct of {unit.text} with TRUE",
                            t0=conjunct.t0, t1=conjunct.t1))
                elif node.kind == "bool":
                    sites.append(Site(
                        kind="flip-literal", module=module_name,
                        file=Path(file_path).name, line_start=node.line,
                        line_end=node.line, col=node.col, definition=unit.text,
                        description=f"flip {node.text} in {unit.text}",
                        source_op=node.text,
                        replacement="FALSE" if node.text == "TRUE" else "TRUE"))
                elif node.kind == "infix" and node.text in ("<", "\\leq", ">", "\\geq"):
                    aliases = {"\\leq": ["<=", "=<"], "\\geq": [">="],
                               "<": [], ">": []}[node.text]
                    spelling = _spelling_at(source, node.line, node.col,
                                            node.text, aliases)
                    if spelling is None:
                        continue
                    family = COMPARISON_FAMILY[spelling]
                    sites.append(Site(
                        kind="weaken-comparison", module=module_name,
                        file=Path(file_path).name, line_start=node.line,
                        line_end=node.line, col=node.col, definition=unit.text,
                        description=f"{spelling} -> {WEAKEN[family]} in {unit.text}",
                        source_op=spelling, replacement=WEAKEN[family]))
    return sites


def _is_type_invariant(node: N) -> bool:
    """``v \\in SomeType`` conjuncts are type annotations, not guards."""
    if node.kind != "infix" or node.text != "\\in":
        return False
    lhs, rhs = node.kid("lhs"), node.kid("rhs")
    if lhs is None or rhs is None:
        return False
    return lhs.kind == "name" and rhs.kind in ("funcset", "set", "recordset",
                                               "apply", "name")


def generate_mutants(program: SpecProgram, model_id: str, count: int = 5,
                     seed: int = 20261106) -> list[Mutant]:
    """Pick ``count`` distinct sites and materialise one mutant per site."""
    sites = collect_sites(program)
    if not sites:
        return []
    rng = random.Random(f"{seed}:{model_id}")
    by_kind: dict[str, list[Site]] = {}
    for site in sites:
        by_kind.setdefault(site.kind, []).append(site)
    for pool in by_kind.values():
        rng.shuffle(pool)
    chosen: list[Site] = []
    kinds = sorted(by_kind)
    while len(chosen) < count and any(by_kind.values()):
        for kind in kinds:
            if by_kind[kind] and len(chosen) < count:
                chosen.append(by_kind[kind].pop())
    mutants: list[Mutant] = []
    for index, site in enumerate(chosen, start=1):
        origin = program.ctx.module_files.get(site.module)
        path = Path(origin) if origin else (program.ctx.spec_dir / site.file)
        text = path.read_text(encoding="utf-8", errors="replace")
        tokens = program.ctx.module_tokens.get(site.module, [])
        mutated, before, after = _apply(text, site, tokens)
        if mutated is None or mutated == text:
            continue
        mutants.append(Mutant(
            mutant_id=f"{model_id}-m{index}", model_id=model_id,
            operator=site.kind, module=site.module, file=site.file,
            description=site.description, line=site.line_start,
            original_snippet=before, mutated_snippet=after, content=mutated))
    return mutants


def _span_offsets(text: str, tokens, t0: int, t1: int) -> tuple[int, int] | None:
    """Character span of the token range ``[t0, t1)``."""
    if not tokens or t0 < 0 or t1 <= t0 or t1 > len(tokens):
        return None
    first, last = tokens[t0], tokens[t1 - 1]
    start = _offset(text, first.line, first.col)
    end = _offset(text, last.line, last.col) + len(last.text)
    return (start, end) if 0 <= start <= end <= len(text) else None


def _apply(text: str, site: Site, tokens) -> tuple[str | None, str, str]:
    if site.kind == "drop-guard":
        # Replace the conjunct's own token span with TRUE.  The bullet (/\ or \/)
        # is not part of the node, so it stays and the file remains well formed.
        span = _span_offsets(text, tokens, site.t0, site.t1)
        if span is None:
            return None, "", ""
        start, end = span
        snippet = text[start:end]
        return text[:start] + "TRUE" + text[end:], snippet.strip()[:200], "TRUE"
    if not site.source_op:
        return None, "", ""
    start = _offset(text, site.line_start, site.col)
    if not text.startswith(site.source_op, start):
        # The AST position can be one column off for multi-character operators
        # that were written with an alias; fall back to a bounded search.
        window_start = max(0, start - 3)
        found = text.find(site.source_op, window_start, start + 4)
        if found < 0:
            return None, "", ""
        start = found
    mutated = text[:start] + site.replacement + text[start + len(site.source_op):]
    return mutated, site.source_op, site.replacement


def describe_catalog() -> list[dict]:
    return [
        {"operator": "drop-guard",
         "mutation": "one top-level non-assignment conjunct is commented out",
         "why": "an action becomes enabled in a state where its guard should "
                "block it, so safety invariants typically fail",
         "expected": "invariant violation"},
        {"operator": "flip-literal",
         "mutation": "a boolean literal in the specification is negated",
         "why": "a branch becomes permanently enabled or disabled",
         "expected": "invariant violation"},
        {"operator": "weaken-comparison",
         "mutation": "< becomes <=, > becomes >= (and the reverse for <= / >=)",
         "why": "off-by-one in a guard or bound",
         "expected": "invariant violation or a larger state space"},
    ]
