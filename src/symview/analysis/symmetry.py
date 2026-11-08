"""Automatic detection of symmetry sets.

A constant ``C`` is proposed as a symmetry set only when *every* one of the
following holds.  Each check produces a machine-readable reason, so a rejected
candidate explains itself.

S1 ``C`` evaluates (in TLC, not in our imagination) to a non-empty set of model
   values with at least two elements; otherwise the permutation group is trivial.
S2 Every other constant's value is invariant under the adjacent transpositions of
   ``C``.  This is exact and cheap: those transpositions generate the full
   symmetric group and invariance is closed under composition.  It catches the
   classic mistakes -- a distinguished element (``Counter = p1``) and an
   asymmetric quorum family (``Majority = {{a1, a2}}``).
S3 No checked invariant or property mentions an individual element of ``C``.
S4 A demand-driven taint analysis shows that no value that may contain an element
   of ``C`` ever reaches a non-equivariant operator (order comparison,
   arithmetic, ``CHOOSE``, ``TLC!Any``, sorting, ``ToString``, ...).  Taint flows
   through user-defined operators, binders, assignments and record/set/sequence
   constructors, and stops at operators whose result cannot contain an atom
   (``Cardinality``, ``Len``, comparisons).
S5 Every module the specification depends on could be resolved, and every operator
   applied to a tainted value is classified.  Unknown operators mean "not
   certified", never "probably fine".

A candidate that passes S1-S5 is *sound for safety*.  If the model also checks a
temporal property or assumes fairness, the candidate is reported with a liveness
warning and the generator refuses to emit ``SYMMETRY`` unless the user overrides
it, because TLC's symmetry reduction is not sound for liveness in general.
"""

from __future__ import annotations

import collections
from dataclasses import dataclass, field

from ..astnodes import N
from ..values import (Atom, SetV, UnknownV, atom_names, invariance_report,
                      is_atom_set)
from .equivariance import ATOM, BOOL, INT, NON_EQUIVARIANT, classify
from .program import SpecProgram

MAX_FIXPOINT_ROUNDS = 8


@dataclass
class Flag:
    operator: str
    reason: str
    definition: str
    line: int
    tainted_operands: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return dict(self.__dict__)


@dataclass
class SymmetryCandidate:
    constant: str
    atoms: list[str]
    verdict: str                 # sound | unsound | trivial | unknown
    reasons: list[str] = field(default_factory=list)
    flags: list[Flag] = field(default_factory=list)
    value_checks: dict[str, dict] = field(default_factory=dict)
    unknown_operators: dict[str, int] = field(default_factory=dict)
    liveness_warning: bool = False
    liveness_reasons: list[str] = field(default_factory=list)
    group_order: int = 1
    manual_symmetry_in_config: str | None = None

    @property
    def accepted(self) -> bool:
        return self.verdict == "sound"

    def to_dict(self) -> dict:
        payload = dict(self.__dict__)
        payload["flags"] = [f.to_dict() for f in self.flags]
        return payload


@dataclass
class SymmetryProposal:
    candidates: list[SymmetryCandidate] = field(default_factory=list)
    selected: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"candidates": [c.to_dict() for c in self.candidates],
                "selected": self.selected, "notes": self.notes}


class TaintScanner:
    """May-analysis: can a value containing an atom of ``atoms`` reach here?"""

    def __init__(self, program: SpecProgram, atoms: set[str]) -> None:
        self.program = program
        self.atoms = atoms
        self.tainted: set[str] = set()
        self.flags: list[Flag] = []
        self.unknown: collections.Counter[str] = collections.Counter()
        self._memo: dict[tuple[str, frozenset[str]], bool] = {}
        self._active: set[tuple[str, frozenset[str]]] = set()
        self.current_definition = "<none>"
        # LET-bound operators are only visible inside their own body.
        self.let_ops: dict[str, N] = {}
        # Field-sensitive taint: does *any* record literal in the program put an
        # atom of the candidate set into this field?  Without it, ``aState[m.acc].bal``
        # looks tainted because the record it indexes has an atom in another field,
        # and every ballot comparison would be reported as non-equivariant.
        self.field_taint: dict[str, bool] = {}

    # -- public --------------------------------------------------------------
    def scan(self, seeds: set[str]) -> None:
        self.tainted |= seeds
        for _ in range(MAX_FIXPOINT_ROUNDS):
            before = set(self.tainted)
            self._compute_field_taint()
            for name in sorted(self.program.reachable):
                body = self.program.definition_body(name)
                if body is None:
                    continue
                self.current_definition = name
                self.value(body, {})
            if self.tainted == before:
                break

    def _compute_field_taint(self) -> None:
        fields: dict[str, bool] = {}
        for name in sorted(self.program.reachable):
            body = self.program.definition_body(name)
            if body is None:
                continue
            self.current_definition = name
            for node in body.walk():
                if node.kind not in ("record", "recordset"):
                    continue
                for field_node in node.kids_in("field"):
                    value = field_node.kid("value")
                    tainted = self.value(value, {}) if value is not None else False
                    fields[field_node.text] = fields.get(field_node.text, False) or tainted
        self.field_taint = fields

    def lookup_operator(self, name: str) -> N | None:
        return self.let_ops.get(name) or self.program.ctx.definition_of(name)

    # -- core ----------------------------------------------------------------
    def is_tainted_name(self, name: str, local: dict[str, bool]) -> bool:
        if name in local:
            return local[name]
        return name in self.tainted

    def value(self, node: N, local: dict[str, bool]) -> bool:
        kind = node.kind
        if kind == "name":
            return self.is_tainted_name(node.text, local)
        if kind in ("num", "str", "bool", "opref"):
            return False
        if kind == "postfix":
            if node.text == "'":
                operand = node.kid("operand")
                return self.value(operand, local) if operand is not None else False
            return False
        if kind == "infix":
            return self._infix(node, local)
        if kind == "prefix":
            return self._prefix(node, local)
        if kind == "apply":
            return self._apply(node, local)
        if kind == "except":
            # ``[f EXCEPT ![i] = v]``: the result takes its atoms from f and from
            # the substituted values; the index only selects a slot.
            target = node.kid("target")
            tainted = self.value(target, local) if target is not None else False
            for arm in node.kids_in("arm"):
                value = arm.kid("value")
                if value is not None and self.value(value, local):
                    tainted = True
            return tainted
        if kind in ("set", "tuple", "record", "recordset", "funcc", "funcset",
                    "exceptarm", "paren", "params", "body"):
            return any(self.value(child, local) for child in node.kids)
        if kind == "setfilter":
            return self._binders(node, local, "pred")
        if kind == "setmap":
            return self._binders(node, local, "body")
        if kind == "quant":
            self._binders(node, local, "body")
            return False
        if kind == "choose":
            return self._choose(node, local)
        if kind == "if":
            self._flag_if_tainted(node, local, [], "IF")
            return any(self.value(node.kid(role), local)
                       for role in ("then", "else") if node.kid(role) is not None)
        if kind == "case":
            out = False
            for arm in node.kids_in("arm"):
                body = arm.kid("body")
                out |= self.value(body, local) if body is not None else False
            other = node.kid("other")
            out |= self.value(other, local) if other is not None else False
            return out
        if kind == "let":
            inner = dict(local)
            saved = dict(self.let_ops)
            for definition in node.kids_in("def"):
                if definition.kind == "opdef":
                    self.let_ops[definition.text] = definition
                    body = definition.kid("body")
                    if definition.kid("params") is None and body is not None:
                        inner[definition.text] = self.value(body, inner)
                else:
                    self.value(definition, inner)
            body = node.kid("body")
            result = self.value(body, inner) if body is not None else False
            self.let_ops = saved
            return result
        if kind == "binder":
            domain = node.kid("domain")
            return self.value(domain, local) if domain is not None else False
        if kind == "stutter":
            action = node.kid("action")
            if action is not None:
                self.value(action, local)
            return False
        if kind == "fair":
            action = node.kid("action")
            if action is not None:
                self.value(action, local)
            return False
        if kind == "bang":
            return self._bang(node, local)
        if kind == "lambda":
            inner = dict(local)
            for param in node.kids_in("param"):
                inner[param.text] = False
            body = node.kid("body")
            return self.value(body, inner) if body is not None else False
        if kind == "unknown":
            self.unknown[f"<{node.text}>"] += 1
            return False
        if kind in ("opdef", "module", "file", "instance", "assume", "theorem",
                    "constant-decl", "variable-decl", "extends", "proofstep",
                    "directive", "ignored", "local", "recursive"):
            return any(self.value(child, local) for child in node.kids)
        return any(self.value(child, local) for child in node.kids)

    # -- operator cases ------------------------------------------------------
    def _infix(self, node: N, local: dict[str, bool]) -> bool:
        lhs, rhs = node.kid("lhs"), node.kid("rhs")
        left = self.value(lhs, local) if lhs is not None else False
        # ``v' = e``: the variable inherits the taint of its right-hand side.
        if node.text in ("=", "\\in") and lhs is not None and lhs.kind == "postfix" \
                and lhs.text == "'" and rhs is not None:
            operand = lhs.kid("operand")
            right = self.value(rhs, local)
            if operand is not None and operand.kind == "name" and right:
                self.tainted.add(operand.text)
            return False
        right = self.value(rhs, local) if rhs is not None else False
        if node.text == "." and rhs is not None and rhs.kind == "name":
            if rhs.text in self.field_taint:
                return self.field_taint[rhs.text]
            return left or right
        spec = classify(node.text)
        if spec is None:
            definition = self.lookup_operator(node.text)
            if definition is not None:
                return self._call_user_operator(node.text, definition, [left, right],
                                                node, local)
            self.unknown[node.text] += 1
            return left or right
        if spec.equivariance == NON_EQUIVARIANT and (left or right):
            self._flag(node, spec.canonical, spec.reason, [left, right], [lhs, rhs], local)
        if spec.result == ATOM:
            return left or right
        return False

    def _prefix(self, node: N, local: dict[str, bool]) -> bool:
        operand = node.kid("operand")
        tainted = self.value(operand, local) if operand is not None else False
        spec = classify(node.text)
        if spec is None:
            self.unknown[node.text] += 1
            return tainted
        if spec.equivariance == NON_EQUIVARIANT and tainted:
            self._flag(node, spec.canonical, spec.reason, [tainted], [operand], local)
        return tainted if spec.result == ATOM else False

    def _apply(self, node: N, local: dict[str, bool]) -> bool:
        head = node.kid("head")
        args = node.kids_in("arg")
        arg_taint = [self.value(a, local) for a in args]
        name = self._head_name(head)
        if name is None:
            self.unknown["<computed-head>"] += 1
            return any(arg_taint)

        if node.text == "[":
            # ``f[x]``: the result is a value *of* f, selected by x.  An atom used
            # as an index does not enter the result, so only f's taint matters --
            # otherwise every ``maxBallot[a] < m.ballot`` comparison with
            # ``a \in Replicas`` would look non-equivariant.
            return self.value(head, local)

        spec = classify(name)
        definition = self.lookup_operator(name)
        if definition is not None and definition.kind == "opdef":
            return self._call_user_operator(name, definition, arg_taint, node, local)
        if spec is None:
            self.unknown[name] += 1
            return any(arg_taint)
        if spec.equivariance == NON_EQUIVARIANT and any(arg_taint):
            self._flag(node, spec.canonical, spec.reason, arg_taint, args, local)
        if spec.result == ATOM:
            return any(arg_taint)
        return False

    def _call_user_operator(self, name: str, definition: N, arg_taint: list[bool],
                            node: N, local: dict[str, bool]) -> bool:
        params_node = definition.kid("params")
        body = definition.kid("body")
        if body is None:
            return any(arg_taint)
        param_names = [leaf.text for leaf in (params_node.walk() if params_node else [])
                       if leaf.kind == "name"]
        if not param_names:
            key = (name, frozenset())
            if key in self._memo:
                return self._memo[key]
            if key in self._active:
                return True
            self._active.add(key)
            inner = dict(local)
            result = self.value(body, inner)
            self._active.discard(key)
            self._memo[key] = result
            return result
        bound = frozenset(p for p, t in zip(param_names, arg_taint) if t)
        key = (name, bound)
        if key in self._memo:
            return self._memo[key]
        if key in self._active:
            self.unknown[f"<recursive:{name}>"] += 1
            return True
        self._active.add(key)
        inner = dict(local)
        for param in param_names:
            inner[param] = param in bound
        result = self.value(body, inner)
        self._active.discard(key)
        self._memo[key] = result
        return result

    def _bang(self, node: N, local: dict[str, bool]) -> bool:
        left, right = node.kid("left"), node.kid("right")
        if left is None or right is None:
            return False
        module = self.program.alias_module.get(left.text, left.text)
        for candidate in (f"{module}!{right.text}", right.text, left.text):
            definition = self.program.ctx.definition_of(candidate)
            if definition is not None:
                if definition.kind == "opdef":
                    return self.value(definition.kid("body") or definition, local)
                return False
        if left.kind in ("name", "bang"):
            return self.value(left, local)
        return False

    def _binders(self, node: N, local: dict[str, bool], body_role: str) -> bool:
        inner = dict(local)
        domain_tainted = False
        for binder in node.kids_in("binder"):
            domain = binder.kid("domain")
            tainted_domain = self.value(domain, inner) if domain is not None else False
            domain_tainted |= tainted_domain
            for var in binder.kids_in("var"):
                for leaf in var.walk():
                    if leaf.kind == "name":
                        inner[leaf.text] = tainted_domain
        body = node.kid(body_role)
        result = self.value(body, inner) if body is not None else False
        if node.kind == "setmap":
            return result
        return domain_tainted

    def _choose(self, node: N, local: dict[str, bool]) -> bool:
        inner = dict(local)
        tainted_domain = False
        for binder in node.kids_in("binder"):
            domain = binder.kid("domain")
            tainted = self.value(domain, inner) if domain is not None else False
            tainted_domain |= tainted
            for var in binder.kids_in("var"):
                for leaf in var.walk():
                    if leaf.kind == "name":
                        inner[leaf.text] = tainted
        body = node.kid("body")
        result = self.value(body, inner) if body is not None else False
        spec = classify("CHOOSE")
        if spec is not None and (tainted_domain or result):
            self._flag(node, "CHOOSE", spec.reason, [tainted_domain], None, local)
        return True if (tainted_domain or result) else False

    # -- helpers -------------------------------------------------------------
    def _head_name(self, head: N | None) -> str | None:
        if head is None:
            return None
        if head.kind == "name":
            return head.text
        if head.kind == "bang":
            left, right = head.kid("left"), head.kid("right")
            if left is not None and right is not None:
                module = self.program.alias_module.get(left.text, left.text)
                for candidate in (f"{module}!{right.text}", right.text):
                    if candidate in self.program.ctx.opdefs:
                        return candidate
                return right.text
        return None

    def _flag_if_tainted(self, node, local, taints, label) -> None:
        return None

    def _flag(self, node: N, operator: str, reason: str, taints: list[bool],
              operands: list[N] | None, local: dict[str, bool]) -> None:
        names: list[str] = []
        for operand in operands or []:
            if operand is None:
                continue
            names += [leaf.text for leaf in operand.walk()
                      if leaf.kind == "name" and self.is_tainted_name(leaf.text, local)]
        self.flags.append(Flag(operator=operator, reason=reason,
                               definition=self.current_definition, line=node.line,
                               tainted_operands=sorted(set(names))[:6]))


def analyze_symmetry(program: SpecProgram) -> SymmetryProposal:
    ctx = program.ctx
    proposal = SymmetryProposal()
    if ctx.unresolved_modules:
        proposal.notes.append(
            "unresolved modules (analysis is therefore conservative): "
            + ", ".join(sorted(ctx.unresolved_modules)))

    atom_constants: dict[str, list[str]] = {}
    for name, info in ctx.constants.items():
        if info.arity != 0 or info.value is None:
            continue
        if is_atom_set(info.value):
            atom_constants[name] = atom_names(info.value)

    for name, atoms in sorted(atom_constants.items()):
        candidate = SymmetryCandidate(constant=name, atoms=atoms, verdict="sound",
                                      manual_symmetry_in_config=ctx.cfg.symmetry)
        candidate.group_order = _factorial(len(atoms))
        if len(atoms) < 2:
            candidate.verdict = "trivial"
            candidate.reasons.append(
                f"{name} has {len(atoms)} element(s); its permutation group is trivial "
                "so symmetry reduction cannot remove any state")
        if isinstance(ctx.constants[name].value, UnknownV):
            candidate.verdict = "unknown"
            candidate.reasons.append("TLC did not print a value for this constant")

        # S2 exact invariance of every other constant value
        for other, other_info in sorted(ctx.constants.items()):
            if other == name or other_info.arity != 0:
                continue
            if isinstance(other_info.value, Atom)                     and other_info.value.name in atoms                     and not program.reads_of(other):
                # The constant merely names an element of the set and the
                # specification never reads it, so it distinguishes nothing.
                continue
            report = invariance_report(other_info.value
                                       if other_info.value is not None
                                       else UnknownV("no-value"), atoms)
            candidate.value_checks[other] = report
            if report["invariant"] is False:
                candidate.verdict = "unsound"
                candidate.reasons.append(
                    f"constant {other} = {other_info.value.render()[:80]} is not "
                    f"invariant under permutations of {name} ({report['witness']}): "
                    "an element of the set is distinguished")
            elif report["invariant"] is None:
                if candidate.verdict == "sound":
                    candidate.verdict = "unknown"
                candidate.reasons.append(
                    f"value of constant {other} could not be interpreted "
                    f"({report.get('witness')}), so invariance cannot be certified")

        # S3 checked properties must not name an individual element
        element_constants = {other for other, info in ctx.constants.items()
                             if info.arity == 0 and isinstance(info.value, Atom)
                             and info.value.name in atoms}
        for property_name in program.invariant_names + program.property_names:
            body = program.definition_body(property_name)
            if body is None:
                continue
            for leaf in body.walk():
                if leaf.kind == "name" and leaf.text in element_constants:
                    candidate.verdict = "unsound"
                    candidate.reasons.append(
                        f"checked property {property_name} mentions {leaf.text}, an "
                        f"individual element of {name}; the property is not symmetric")

        # S4 equivariant use of every value that may hold an element of the set
        seeds = {name} | element_constants
        scanner = TaintScanner(program, set(atoms))
        scanner.scan(seeds)
        candidate.flags = scanner.flags
        candidate.unknown_operators = dict(scanner.unknown.most_common(12))
        if scanner.flags:
            candidate.verdict = "unsound"
            distinct = sorted({f.operator for f in scanner.flags})
            candidate.reasons.append(
                "values drawn from "
                f"{name} reach a non-equivariant operator: {', '.join(distinct)} "
                f"({len(scanner.flags)} occurrence(s)); permuting the set would "
                "change the transition relation")
        if scanner.unknown and candidate.verdict == "sound":
            candidate.verdict = "unknown"
            candidate.reasons.append(
                "unclassified operators applied to values from "
                f"{name}: {', '.join(sorted(scanner.unknown)[:8])}; "
                "SymView does not certify a reduction it cannot justify")

        if ctx.unresolved_modules and candidate.verdict == "sound":
            candidate.verdict = "unknown"
            candidate.reasons.append(
                "some extended modules could not be resolved, so not every use of "
                f"{name} was inspected")

        # liveness caveat
        if program.liveness:
            candidate.liveness_warning = True
            candidate.liveness_reasons = list(program.liveness_reasons)
            candidate.reasons.append(
                "the model checks a temporal property or assumes fairness; TLC's "
                "symmetry reduction is not sound for liveness in general, so "
                "SymView will not enable SYMMETRY for this model by default")
        if candidate.verdict == "sound":
            candidate.reasons.append(
                f"{name} = {{{', '.join(atoms)}}} is used only through "
                "permutation-equivariant operators and no other constant "
                "distinguishes its elements")
        proposal.candidates.append(candidate)

    accepted = [c for c in proposal.candidates
                if c.accepted and not c.liveness_warning]
    selected: list[str] = []
    used_atoms: set[str] = set()
    for candidate in sorted(accepted, key=lambda c: -len(c.atoms)):
        if used_atoms & set(candidate.atoms):
            proposal.notes.append(
                f"{candidate.constant} overlaps an already selected symmetry set")
            continue
        selected.append(candidate.constant)
        used_atoms |= set(candidate.atoms)
    proposal.selected = selected
    if not proposal.candidates:
        proposal.notes.append("no constant evaluates to a set of model values, so "
                              "this model has no symmetry set to propose")
    return proposal


def _factorial(n: int) -> int:
    out = 1
    for i in range(2, n + 1):
        out *= i
    return out
