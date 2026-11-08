"""Concrete values of TLC constants, and permutation invariance over them.

SymView needs to answer an exact question: *is the value of every constant
unchanged when the elements of a candidate symmetry set are permuted?*  The
values are not guessed from the configuration text -- they are printed by TLC
itself (see :mod:`symview.consteval`) and parsed back with SymView's own
expression parser, so the answer uses the model checker's semantics.

Invariance only has to be checked on a generating set of the symmetric group:
the adjacent transpositions ``(a_i a_{i+1})`` generate ``S_k`` and invariance is
closed under composition, so ``k - 1`` checks decide what would otherwise be
``k!`` checks.  That is exact, not a heuristic.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator

from .astnodes import N


# NOTE: ``eq=False`` is essential.  The dataclass-generated ``__eq__`` would
# compare the ``items`` tuple positionally, so ``{a1, a2}`` and ``{a2, a1}``
# would differ and every permutation-invariance test would report a false
# violation.  Equality and hashing come from ``Val.key()`` instead.


class Val:
    """Base class for concrete TLA+ values."""

    kind = "val"

    def key(self) -> object:
        raise NotImplementedError

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Val) and self.key() == other.key()

    def __hash__(self) -> int:
        return hash(self.key())

    def render(self) -> str:
        raise NotImplementedError

    def __repr__(self) -> str:
        return self.render()

    def atoms(self) -> set[str]:
        return set()

    def walk(self) -> Iterator["Val"]:
        yield self


@dataclass(frozen=True, eq=False)
class Atom(Val):
    """An uninterpreted model value such as ``p1``."""

    name: str
    kind: str = "atom"

    def key(self) -> tuple[str, str]:
        return ("atom", self.name)

    def render(self) -> str:
        return self.name

    def atoms(self) -> set[str]:
        return {self.name}


@dataclass(frozen=True, eq=False)
class IntV(Val):
    value: int
    kind: str = "int"

    def key(self) -> tuple[str, int]:
        return ("int", self.value)

    def render(self) -> str:
        return str(self.value)


@dataclass(frozen=True, eq=False)
class StrV(Val):
    value: str
    kind: str = "str"

    def key(self) -> tuple[str, str]:
        return ("str", self.value)

    def render(self) -> str:
        return '"' + self.value.replace('"', '\\"') + '"'


@dataclass(frozen=True, eq=False)
class BoolV(Val):
    value: bool
    kind: str = "bool"

    def key(self) -> tuple[str, bool]:
        return ("bool", self.value)

    def render(self) -> str:
        return "TRUE" if self.value else "FALSE"


@dataclass(frozen=True, eq=False)
class SetV(Val):
    """A finite set.  Equality is by content, order is only for rendering."""

    items: tuple[Val, ...]
    kind: str = "set"

    def key(self) -> tuple[str, frozenset]:
        return ("set", frozenset(item.key() for item in self.items))

    def render(self) -> str:
        return "{" + ", ".join(sorted(item.render() for item in self.items)) + "}"

    def atoms(self) -> set[str]:
        out: set[str] = set()
        for item in self.items:
            out |= item.atoms()
        return out

    def walk(self) -> Iterator[Val]:
        yield self
        for item in self.items:
            yield from item.walk()


@dataclass(frozen=True, eq=False)
class TupleV(Val):
    items: tuple[Val, ...]
    kind: str = "tuple"

    def key(self) -> tuple[str, tuple]:
        return ("tuple", tuple(item.key() for item in self.items))

    def render(self) -> str:
        return "<<" + ", ".join(item.render() for item in self.items) + ">>"

    def atoms(self) -> set[str]:
        out: set[str] = set()
        for item in self.items:
            out |= item.atoms()
        return out

    def walk(self) -> Iterator[Val]:
        yield self
        for item in self.items:
            yield from item.walk()


@dataclass(frozen=True, eq=False)
class RecV(Val):
    fields: tuple[tuple[str, Val], ...]
    kind: str = "record"

    def key(self) -> tuple[str, tuple]:
        return ("record", tuple((k, v.key()) for k, v in sorted(self.fields)))

    def render(self) -> str:
        return "[" + ", ".join(f"{k} |-> {v.render()}" for k, v in sorted(self.fields)) + "]"

    def atoms(self) -> set[str]:
        out: set[str] = set()
        for _, value in self.fields:
            out |= value.atoms()
        return out

    def walk(self) -> Iterator[Val]:
        yield self
        for _, value in self.fields:
            yield from value.walk()


@dataclass(frozen=True, eq=False)
class FuncV(Val):
    pairs: tuple[tuple[Val, Val], ...]
    kind: str = "func"

    def key(self) -> tuple[str, frozenset]:
        return ("func", frozenset((k.key(), v.key()) for k, v in self.pairs))

    def render(self) -> str:
        rendered = [f"{k.render()} :> {v.render()}" for k, v in self.pairs]
        return "(" + " @@ ".join(rendered) + ")" if rendered else "<<" + ">>"

    def atoms(self) -> set[str]:
        out: set[str] = set()
        for key, value in self.pairs:
            out |= key.atoms() | value.atoms()
        return out

    def walk(self) -> Iterator[Val]:
        yield self
        for key, value in self.pairs:
            yield from key.walk()
            yield from value.walk()


@dataclass(frozen=True, eq=False)
class UnknownV(Val):
    """A value SymView could not interpret; forces a conservative verdict."""

    text: str
    kind: str = "unknown"

    def key(self) -> tuple[str, str]:
        return ("unknown", self.text)

    def render(self) -> str:
        return f"<unknown: {self.text}>"


def value_from_ast(node: N) -> Val:
    """Interpret the AST of a *printed concrete value* (no free variables)."""
    kind = node.kind
    if kind == "num":
        try:
            return IntV(int(node.text))
        except ValueError:
            return UnknownV(node.text)
    if kind == "str":
        return StrV(node.text[1:-1].replace('\\"', '"'))
    if kind == "bool":
        return BoolV(node.text == "TRUE")
    if kind == "name":
        return Atom(node.text)
    if kind == "set":
        return SetV(tuple(value_from_ast(k) for k in node.kids_in("item")))
    if kind == "tuple":
        return TupleV(tuple(value_from_ast(k) for k in node.kids_in("item")))
    if kind == "record":
        fields = []
        for field in node.kids_in("field"):
            value = field.kid("value")
            fields.append((field.text, value_from_ast(value) if value else UnknownV("?")))
        return RecV(tuple(fields))
    if kind == "infix":
        if node.text == "..":
            low, high = node.kid("lhs"), node.kid("rhs")
            if low is not None and high is not None and low.kind == "num" and high.kind == "num":
                lo, hi = int(low.text), int(high.text)
                if 0 <= hi - lo <= 100000:
                    return SetV(tuple(IntV(i) for i in range(lo, hi + 1)))
            return UnknownV(node.text)
        if node.text == ":>":
            key, value = node.kid("lhs"), node.kid("rhs")
            if key is not None and value is not None:
                return FuncV(((value_from_ast(key), value_from_ast(value)),))
            return UnknownV(node.text)
        if node.text == "@@":
            left, right = node.kid("lhs"), node.kid("rhs")
            if left is None or right is None:
                return UnknownV(node.text)
            lv, rv = value_from_ast(left), value_from_ast(right)
            if isinstance(lv, FuncV) and isinstance(rv, FuncV):
                return FuncV(tuple(lv.pairs) + tuple(rv.pairs))
            return UnknownV(node.text)
        return UnknownV(node.text)
    if kind == "prefix" and node.text == "-.":
        operand = node.kid("operand")
        if operand is not None and operand.kind == "num":
            return IntV(-int(operand.text))
    if kind == "paren":
        body = node.kid("body")
        if body is not None:
            return value_from_ast(body)
    if kind == "apply":
        return UnknownV("function-value")
    return UnknownV(kind)


def permute(value: Val, mapping: dict[str, str]) -> Val:
    """Apply a permutation of model values to a value, structurally."""
    if isinstance(value, Atom):
        return Atom(mapping.get(value.name, value.name))
    if isinstance(value, SetV):
        return SetV(tuple(permute(item, mapping) for item in value.items))
    if isinstance(value, TupleV):
        return TupleV(tuple(permute(item, mapping) for item in value.items))
    if isinstance(value, RecV):
        return RecV(tuple((k, permute(v, mapping)) for k, v in value.fields))
    if isinstance(value, FuncV):
        return FuncV(tuple((permute(k, mapping), permute(v, mapping))
                           for k, v in value.pairs))
    return value


def adjacent_transpositions(atoms: list[str]) -> list[dict[str, str]]:
    """The ``k-1`` adjacent swaps that generate the symmetric group on ``atoms``."""
    swaps = []
    for i in range(len(atoms) - 1):
        mapping = {a: a for a in atoms}
        mapping[atoms[i]], mapping[atoms[i + 1]] = atoms[i + 1], atoms[i]
        swaps.append(mapping)
    return swaps


def invariance_report(value: Val, atoms: list[str]) -> dict:
    """Exact invariance of ``value`` under every permutation of ``atoms``.

    Only adjacent transpositions are tested; they generate the full symmetric
    group and invariance is closed under composition, so this is equivalent to
    testing all ``k!`` permutations.
    """
    if not atoms:
        return {"invariant": True, "checked": 0, "witness": None, "reason": "empty-set"}
    if isinstance(value, UnknownV):
        return {"invariant": None, "checked": 0, "witness": value.text,
                "reason": "value-not-interpreted"}
    for mapping in adjacent_transpositions(atoms):
        if permute(value, mapping) != value:
            swapped = [k for k, v in mapping.items() if k != v]
            return {"invariant": False, "checked": len(atoms) - 1,
                    "witness": f"swap({','.join(sorted(swapped))})",
                    "rendered": value.render()[:400],
                    "reason": "value-changes-under-permutation"}
    return {"invariant": True, "checked": len(atoms) - 1, "witness": None,
            "reason": "invariant-under-generators"}


def is_atom_set(value: Val) -> bool:
    return isinstance(value, SetV) and bool(value.items) and \
        all(isinstance(item, Atom) for item in value.items)


def atom_names(value: Val) -> list[str]:
    if isinstance(value, SetV):
        return sorted(item.name for item in value.items if isinstance(item, Atom))
    return []
