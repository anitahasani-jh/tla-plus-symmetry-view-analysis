"""Which TLA+ operators commute with a permutation of model values.

Symmetry reduction is only sound if the specification is *equivariant* under the
permutation group: applying a permutation :math:`\\pi` to a state and then taking
a transition must give the same result as taking the transition and then applying
:math:`\\pi`.  Every operator used on a value that may contain elements of the
candidate symmetry set therefore has to commute with :math:`\\pi`.

Each operator is classified by what it does to "may contain atoms of the
candidate set":

``atom``
    the result may still contain those atoms, so taint keeps flowing
    (``\\cup``, ``Append``, ``f[x]``, ``DOMAIN``, ...).
``bool`` / ``int``
    the result is a truth value or a number, so it can no longer contain an
    atom; taint stops.  ``=`` and ``\\in`` are equivariant *and* bool-producing,
    while ``<`` is bool-producing but **not** equivariant.
``equivariant`` / ``nonequiv``
    whether ``op(pi(x), pi(y)) = pi(op(x, y))`` holds for every permutation.

Anything not listed is ``unknown`` and makes the analysis refuse to certify the
candidate: refusing is cheap (a little lost reduction) while a wrong acceptance
silently hides violations.
"""

from __future__ import annotations

from dataclasses import dataclass

ATOM = "atom"
BOOL = "bool"
INT = "int"
NONE = "none"

EQUIVARIANT = "equivariant"
NON_EQUIVARIANT = "non-equivariant"
UNKNOWN = "unknown"


@dataclass(frozen=True)
class OpClass:
    canonical: str
    equivariance: str
    result: str
    reason: str


def _c(canonical: str, equivariance: str, result: str, reason: str) -> OpClass:
    return OpClass(canonical, equivariance, result, reason)


# -- operators that commute with every permutation ---------------------------
EQUIVARIANT_OPS: dict[str, OpClass] = {
    op.canonical: op for op in [
        # equality / membership: comparing atoms is permutation invariant
        _c("=", EQUIVARIANT, BOOL, "equality of values is preserved by pi"),
        _c("#", EQUIVARIANT, BOOL, "disequality is preserved by pi"),
        _c("/=", EQUIVARIANT, BOOL, "disequality is preserved by pi"),
        _c("\\equiv", EQUIVARIANT, BOOL, "logical equivalence on equivariant parts"),
        _c("\\in", EQUIVARIANT, BOOL, "pi(x) in pi(S) iff x in S"),
        _c("\\notin", EQUIVARIANT, BOOL, "pi(x) in pi(S) iff x in S"),
        _c("\\subseteq", EQUIVARIANT, BOOL, "pi acts elementwise on both sides"),
        _c("\\subset", EQUIVARIANT, BOOL, "pi acts elementwise on both sides"),
        _c("\\supset", EQUIVARIANT, BOOL, "pi acts elementwise on both sides"),
        _c("\\supseteq", EQUIVARIANT, BOOL, "pi acts elementwise on both sides"),
        # propositional connectives
        _c("\\land", EQUIVARIANT, BOOL, "conjunction of equivariant parts"),
        _c("\\lor", EQUIVARIANT, BOOL, "disjunction of equivariant parts"),
        _c("\\lnot", EQUIVARIANT, BOOL, "negation of an equivariant part"),
        _c("=>", EQUIVARIANT, BOOL, "implication of equivariant parts"),
        _c("<=>", EQUIVARIANT, BOOL, "equivalence of equivariant parts"),
        # set algebra: pi distributes over all of them
        _c("\\union", EQUIVARIANT, ATOM, "pi(A \\\\cup B) = pi(A) \\\\cup pi(B)"),
        _c("\\intersect", EQUIVARIANT, ATOM, "pi(A \\\\cap B) = pi(A) \\\\cap pi(B)"),
        _c("\\", EQUIVARIANT, ATOM, "pi(A \\\\ B) = pi(A) \\\\ pi(B)"),
        _c("\\times", EQUIVARIANT, ATOM, "pi acts componentwise on pairs"),
        _c("SUBSET", EQUIVARIANT, ATOM, "pi maps the powerset onto the powerset"),
        _c("UNION", EQUIVARIANT, ATOM, "pi distributes over a union of sets"),
        _c("DOMAIN", EQUIVARIANT, ATOM, "pi renames domain elements consistently"),
        _c(".", EQUIVARIANT, ATOM, "record field selection is positional, not by name"),
        # sequence algebra: positions are untouched, elements are renamed
        _c("\\o", EQUIVARIANT, ATOM, "pi acts elementwise on concatenation"),
        # temporal / action operators
        _c("[]", EQUIVARIANT, BOOL, "always: pi commutes with taking steps"),
        _c("<>", EQUIVARIANT, BOOL, "eventually: pi commutes with taking steps"),
        _c("~>", EQUIVARIANT, BOOL, "leads-to is built from [] and <>"),
        _c("-+->", EQUIVARIANT, BOOL, "temporal implication"),
        _c("ENABLED", EQUIVARIANT, BOOL, "enabledness of an equivariant action"),
        _c("UNCHANGED", EQUIVARIANT, BOOL, "v' = v is preserved by pi"),
        _c("'", EQUIVARIANT, ATOM, "priming does not change the value"),
        # operators whose result cannot mention an atom, so taint stops
        _c("Cardinality", EQUIVARIANT, INT, "|pi(S)| = |S|"),
        _c("IsFiniteSet", EQUIVARIANT, BOOL, "finiteness is preserved by pi"),
        _c("Len", EQUIVARIANT, INT, "sequence length is preserved by pi"),
        _c("Permutations", EQUIVARIANT, NONE, "used only to build the symmetry set"),
    ]
}

# -- operators that do NOT commute with a permutation ------------------------
NON_EQUIVARIANT_OPS: dict[str, OpClass] = {
    op.canonical: op for op in [
        _c("<", NON_EQUIVARIANT, BOOL, "order on identities is not preserved by pi"),
        _c("\\leq", NON_EQUIVARIANT, BOOL, "order on identities is not preserved"),
        _c(">", NON_EQUIVARIANT, BOOL, "order on identities is not preserved"),
        _c("\\geq", NON_EQUIVARIANT, BOOL, "order on identities is not preserved"),
        _c("\\prec", NON_EQUIVARIANT, BOOL, "a user-chosen order on identities"),
        _c("\\preceq", NON_EQUIVARIANT, BOOL, "a user-chosen order on identities"),
        _c("\\succ", NON_EQUIVARIANT, BOOL, "a user-chosen order on identities"),
        _c("\\succeq", NON_EQUIVARIANT, BOOL, "a user-chosen order on identities"),
        _c("\\ll", NON_EQUIVARIANT, BOOL, "ordering relation"),
        _c("\\gg", NON_EQUIVARIANT, BOOL, "ordering relation"),
        _c("+", NON_EQUIVARIANT, INT, "arithmetic on an atom is not type-correct "
                                      "and cannot be equivariant"),
        _c("-.", NON_EQUIVARIANT, INT, "arithmetic negation on an atom"),
        _c("-", NON_EQUIVARIANT, INT, "arithmetic on an atom"),
        _c("*", NON_EQUIVARIANT, INT, "arithmetic on an atom"),
        _c("\\div", NON_EQUIVARIANT, INT, "arithmetic on an atom"),
        _c("%", NON_EQUIVARIANT, INT, "arithmetic on an atom"),
        _c("^", NON_EQUIVARIANT, INT, "exponentiation on an atom"),
        _c("..", NON_EQUIVARIANT, ATOM, "an integer interval exposes an ordering"),
        # choice and randomness pick one element by an internal rule
        _c("CHOOSE", NON_EQUIVARIANT, ATOM,
           "TLC's CHOOSE returns a fixed but arbitrary element; pi(CHOOSE x: P) "
           "need not equal CHOOSE x: pi(P), so the transition relation is not "
           "equivariant"),
        _c("Any", NON_EQUIVARIANT, ATOM, "TLC!Any picks an element by internal order"),
        _c("RandomElement", NON_EQUIVARIANT, ATOM, "random pick is not equivariant"),
        _c("ToString", NON_EQUIVARIANT, NONE,
           "the printed form of an atom depends on its name"),
        _c("SortSeq", NON_EQUIVARIANT, ATOM, "sorting uses a comparison function"),
        _c("SelectSeq", NON_EQUIVARIANT, ATOM,
           "selection order depends on the comparison predicate; only sound if "
           "the predicate itself is equivariant, which SymView does not assume"),
        _c("JavaTime", NON_EQUIVARIANT, INT, "wall-clock value, not a model value"),
        _c("Randomization", NON_EQUIVARIANT, INT, "randomness"),
    ]
}

# Standard-module operators that are equivariant and keep atoms.
SEQUENCE_ATOM_OPS = ["Append", "Head", "Tail", "SubSeq", "Seq", "SetOfAllSeq"]
FINITE_SET_OPS = ["SetFold", "SetReduce"]


def classify(name: str) -> OpClass | None:
    """Classification of a *built-in* operator, or None if unknown."""
    if name in EQUIVARIANT_OPS:
        return EQUIVARIANT_OPS[name]
    if name in NON_EQUIVARIANT_OPS:
        return NON_EQUIVARIANT_OPS[name]
    if name in SEQUENCE_ATOM_OPS:
        return _c(name, EQUIVARIANT, ATOM,
                  "sequence operators act elementwise, positions are untouched")
    if name in FINITE_SET_OPS:
        return _c(name, EQUIVARIANT, ATOM, "folding an equivariant function over a set")
    if name in ("BOOLEAN", "Nat", "Int", "TRUE", "FALSE", "String"):
        return _c(name, EQUIVARIANT, NONE, "a built-in constant that contains no atom")
    return None


def classification_table() -> list[dict]:
    """Every classification as a row, used to generate the documentation table."""
    rows = []
    for table in (EQUIVARIANT_OPS, NON_EQUIVARIANT_OPS):
        for op in table.values():
            rows.append({"operator": op.canonical, "equivariance": op.equivariance,
                         "result": op.result, "reason": op.reason})
    for name in SEQUENCE_ATOM_OPS + FINITE_SET_OPS:
        op = classify(name)
        rows.append({"operator": op.canonical, "equivariance": op.equivariance,
                     "result": op.result, "reason": op.reason})
    return sorted(rows, key=lambda r: (r["equivariance"], r["operator"]))
