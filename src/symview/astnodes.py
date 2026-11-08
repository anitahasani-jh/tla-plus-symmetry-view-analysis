"""A single uniform AST node type for TLA+.

SymView does not need a pretty syntax tree, it needs *occurrences with context*.
One node type with a role-tagged child list keeps the analysis passes short and
makes token-coverage checking trivial: every node records the half-open token
span ``[t0, t1)`` it consumed, so ``coverage()`` can prove that no token was
silently dropped and that unparseable input is reported rather than ignored.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterator


@dataclass
class N:
    kind: str
    text: str = ""
    kids: list["N"] = field(default_factory=list)
    line: int = 0
    col: int = 0
    role: str = ""
    t0: int = -1
    t1: int = -1
    parent: "N | None" = field(default=None, repr=False, compare=False)
    note: str = ""

    # -- construction helpers ------------------------------------------------
    def add(self, kid: "N", role: str = "") -> "N":
        kid.role = role
        kid.parent = self
        self.kids.append(kid)
        return kid

    def span(self, t0: int, t1: int) -> "N":
        self.t0, self.t1 = t0, t1
        return self

    # -- queries -------------------------------------------------------------
    def kids_in(self, *roles: str) -> list["N"]:
        return [k for k in self.kids if k.role in roles]

    def kid(self, role: str) -> "N | None":
        for k in self.kids:
            if k.role == role:
                return k
        return None

    @property
    def name(self) -> str:
        """Identifier text for name-like nodes."""
        return self.text

    def walk(self) -> Iterator["N"]:
        yield self
        for kid in self.kids:
            yield from kid.walk()

    def path_to_root(self) -> list["N"]:
        chain, node = [], self
        while node is not None:
            chain.append(node)
            node = node.parent
        return chain

    def render(self, indent: int = 0) -> str:  # pragma: no cover - debugging aid
        pad = "  " * indent
        label = f"{self.kind}:{self.text}" if self.text else self.kind
        extra = f"  [{self.role}]" if self.role else ""
        out = [f"{pad}{label}{extra} <{self.line}:{self.col}>"]
        out += [kid.render(indent + 1) for kid in self.kids]
        return "\n".join(out)


def link(node: N) -> N:
    """Set parent pointers for a whole tree (idempotent)."""
    for kid in node.kids:
        kid.parent = node
        link(kid)
    return node


def coverage(root: N, total_tokens: int) -> dict[str, object]:
    """How much of the token stream the AST accounts for."""
    covered: set[int] = set()
    unknown: set[int] = set()
    for node in root.walk():
        if node.t0 >= 0 and node.t1 >= node.t0:
            span = set(range(node.t0, node.t1))
            covered |= span
            if node.kind == "unknown":
                unknown |= span
    return {
        "total_tokens": total_tokens,
        "covered_tokens": len(covered),
        "uncovered_tokens": sorted(set(range(total_tokens)) - covered),
        "unknown_tokens": len(unknown),
        "coverage": (len(covered) / total_tokens) if total_tokens else 1.0,
    }
