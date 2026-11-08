"""Automatic view abstraction: which variables are pure history?

TLC's ``VIEW`` merges states that a zero-argument operator maps to the same
value, so dropping a variable is only sound if the variable cannot influence
anything that is observed.  SymView decides this with an influence graph:

* ``u -> v`` for every assignment ``v' = e`` whose right-hand side reads ``u``;
* ``u -> ENABLED`` for every read of ``u`` outside an assignment right-hand side,
  because such a read decides whether an action can happen at all;
* a variable is **observable** if a checked invariant or temporal property reads
  it, or if it is read in a guard while TLC is also checking for deadlock.

A variable is *history* when it is not observable and cannot reach an observable
variable or ``ENABLED`` in that graph.  Self-loops are allowed, which is exactly
the accumulating-log case ``log' = Append(log, x)``: the variable is read, but
only to recompute itself.

Under that condition the projection is a bisimulation of the original transition
system, so every property over the retained variables -- safety and, because the
quotient preserves traces, liveness too -- is preserved.  SymView still warns
when a temporal property is checked, because TLC's view merging interacts with
fairness in ways worth a human look, and it refuses to emit a constant view.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..astnodes import N
from .program import SpecProgram

ENABLED_SINK = "<enabledness>"


@dataclass
class VariableEvidence:
    name: str
    observable: bool = False
    observable_reasons: list[str] = field(default_factory=list)
    read_in_rhs: int = 0
    read_in_guard: int = 0
    read_in_init: int = 0
    read_in_property: int = 0
    writes: int = 0
    influences: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return dict(self.__dict__)


@dataclass
class HistoryProposal:
    retained: list[str] = field(default_factory=list)
    dropped: list[str] = field(default_factory=list)
    verdict: str = "none"        # sound | none | unknown
    reasons: list[str] = field(default_factory=list)
    evidence: dict[str, VariableEvidence] = field(default_factory=dict)
    liveness_warning: bool = False
    liveness_reasons: list[str] = field(default_factory=list)
    view_operator: str = ""

    @property
    def accepted(self) -> bool:
        return self.verdict == "sound" and bool(self.dropped)

    def to_dict(self) -> dict:
        payload = dict(self.__dict__)
        payload["evidence"] = {k: v.to_dict() for k, v in self.evidence.items()}
        return payload


def free_variables(node: N | None, program: SpecProgram,
                   bound: set[str] | None = None) -> set[str]:
    """State variables read anywhere inside ``node`` (binder aware)."""
    out: set[str] = set()
    if node is None:
        return out
    bound = set(bound or ())

    def walk(current: N, local: set[str]) -> None:
        kind = current.kind
        if kind == "name":
            if current.text not in local and \
                    program.name_kind.get(current.text) == "variable":
                out.add(current.text)
            return
        if kind in ("binder", "lambda", "opdef"):
            inner = set(local)
            for role in ("var", "param"):
                for child in current.kids_in(role):
                    for leaf in child.walk():
                        if leaf.kind == "name":
                            inner.add(leaf.text)
            for child in current.kids:
                if child.role in ("domain", "body", "param") and child.kind != "name":
                    walk(child, local if child.role == "domain" else inner)
                elif child.role not in ("var", "param"):
                    walk(child, inner)
            return
        if kind == "let":
            inner = set(local)
            for definition in current.kids_in("def"):
                walk(definition, inner)
                if definition.kind == "opdef":
                    inner.add(definition.text)
            body = current.kid("body")
            if body is not None:
                walk(body, inner)
            return
        for child in current.kids:
            walk(child, local)

    walk(node, bound)
    return out


def analyze_history(program: SpecProgram, allow_liveness_view: bool = True) -> HistoryProposal:
    ctx = program.ctx
    proposal = HistoryProposal()
    variables = list(ctx.variables)
    if not variables:
        proposal.verdict = "none"
        proposal.reasons.append("the specification declares no variables")
        return proposal

    evidence = {name: VariableEvidence(name=name) for name in variables}
    deadlock_checked = ctx.cfg.check_deadlock is not False

    # --- classify every read -------------------------------------------------
    for read in program.reads:
        if read.kind != "variable" or read.name not in evidence:
            continue
        item = evidence[read.name]
        if read.mode == "rhs":
            item.read_in_rhs += 1
        elif read.mode == "property":
            item.read_in_property += 1
            item.observable = True
            item.observable_reasons.append(
                f"read by checked property/invariant {read.opdef}")
        elif read.mode == "init":
            # Reading a variable inside Init only constrains its own initial
            # value (or feeds another initial value, which is already an
            # influence edge), so it never makes the variable observable.
            item.read_in_init += 1
        else:
            item.read_in_guard += 1

    for name in variables:
        item = evidence[name]
        item.writes = len(program.writes_of(name))
        if item.read_in_guard and deadlock_checked:
            item.observable = True
            item.observable_reasons.append(
                "read outside an assignment right-hand side while TLC checks for "
                "deadlock, so it decides whether a state is a deadlock")

    # --- influence edges -----------------------------------------------------
    successors: dict[str, set[str]] = {name: set() for name in variables}
    guard_readers: set[str] = set()
    for write in program.writes:
        if write.var not in successors:
            continue
        for source in free_variables(write.rhs, program):
            if source in successors:
                successors[source].add(write.var)
                evidence[source].influences.append(write.var)
    for read in program.reads:
        if read.kind != "variable" or read.mode != "guard":
            continue
        if read.name in successors:
            guard_readers.add(read.name)

    # --- backward reachability from everything observable --------------------
    observable = {name for name in variables if evidence[name].observable}
    retained = set(observable) | guard_readers
    queue = sorted(retained)
    predecessors: dict[str, set[str]] = {name: set() for name in variables}
    for source, targets in successors.items():
        for target in targets:
            if target in predecessors:
                predecessors[target].add(source)
    while queue:
        current = queue.pop()
        for source in sorted(predecessors.get(current, ())):
            if source not in retained:
                retained.add(source)
                queue.append(source)

    proposal.retained = [name for name in variables if name in retained]
    proposal.dropped = [name for name in variables if name not in retained]
    proposal.evidence = evidence

    for name in proposal.dropped:
        item = evidence[name]
        proposal.reasons.append(
            f"{name} is written {item.writes} time(s) and read "
            f"{item.read_in_rhs} time(s) only to recompute itself; no checked "
            "property mentions it and it cannot influence any observable "
            "variable or the enabledness of any action")

    # --- refusals ------------------------------------------------------------
    for name in (ctx.cfg.view, ctx.cfg.postcondition):
        if not name:
            continue
        body = program.definition_body(name)
        for used in free_variables(body, program):
            if used in proposal.dropped:
                proposal.dropped.remove(used)
                proposal.retained.append(used)
                proposal.reasons.append(
                    f"{used} is retained because the configuration's "
                    f"{'VIEW' if name == ctx.cfg.view else 'POSTCONDITION'} uses it")
    for constraint in list(ctx.cfg.constraints) + list(ctx.cfg.action_constraints):
        body = program.definition_body(constraint)
        for used in free_variables(body, program):
            if used in proposal.dropped:
                proposal.dropped.remove(used)
                proposal.retained.append(used)
                proposal.reasons.append(
                    f"{used} is retained because the constraint {constraint} uses it")
    for assume in ctx.assumes:
        for used in free_variables(assume.kid("body"), program):
            if used in proposal.dropped:
                proposal.dropped.remove(used)
                proposal.retained.append(used)
                proposal.reasons.append(
                    f"{used} is retained because an ASSUME mentions it")

    proposal.retained = [name for name in variables if name in set(proposal.retained)]
    proposal.dropped = [name for name in variables if name in set(proposal.dropped)]

    if ctx.unresolved_modules:
        proposal.verdict = "unknown"
        proposal.reasons.append(
            "unresolved modules ("
            + ", ".join(sorted(ctx.unresolved_modules))
            + ") mean not every read of these variables was inspected")
    elif not proposal.dropped:
        proposal.verdict = "none"
        proposal.reasons.append(
            "every variable is observable or influences an observable one, so no "
            "view abstraction is possible")
    elif not proposal.retained:
        proposal.verdict = "unknown"
        proposal.reasons.append(
            "the view would be constant (no variable is observable); SymView "
            "refuses to propose a view that merges every state")
    elif not observable and deadlock_checked is False and not ctx.cfg.invariants \
            and not ctx.cfg.properties:
        proposal.verdict = "unknown"
        proposal.reasons.append(
            "the configuration checks no invariant, no property and no deadlock, "
            "so nothing is observable and a reduction cannot be justified")
    else:
        proposal.verdict = "sound"

    if program.liveness:
        proposal.liveness_warning = True
        proposal.liveness_reasons = list(program.liveness_reasons)
        if not allow_liveness_view and proposal.verdict == "sound":
            proposal.verdict = "unknown"
            proposal.reasons.append(
                "a temporal property is checked and view abstraction for liveness "
                "is disabled by configuration")
        else:
            proposal.reasons.append(
                "note: a temporal property is checked; the dropped variables are "
                "provably without influence, so the projection is a bisimulation, "
                "but this combination is reported for manual review")

    if proposal.verdict == "sound":
        proposal.view_operator = "<< " + ", ".join(proposal.retained) + " >>"
    return proposal
