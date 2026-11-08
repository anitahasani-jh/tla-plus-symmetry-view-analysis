"""A resolved, analysis-ready view of one TLC model.

:class:`SpecProgram` answers the questions both analyses need:

* which names are constants, variables, operators or built-ins;
* which operator definitions are reachable from the initial predicate, the
  next-state relation and the properties actually being checked;
* where every variable is written and where it is read, and whether a read is
  inside an assignment right-hand side (it only feeds that variable) or inside a
  guard (it decides whether an action can happen at all);
* whether the model checks liveness, which is what makes symmetry reduction
  dangerous.

The read/write split is the backbone of the view abstraction: a variable that is
only ever read in order to recompute itself, and that no checked property
mentions, cannot influence the observable behaviour.
"""

from __future__ import annotations

import collections
from dataclasses import dataclass, field
from pathlib import Path

from ..astnodes import N
from ..context import SpecContext

BUILTIN_OPERATORS = {
    "Append", "Head", "Tail", "Len", "SubSeq", "SelectSeq", "Seq", "SetOfAllSeq",
    "Cardinality", "IsFiniteSet", "SetFold", "SetReduce", "Permutations",
    "Print", "PrintT", "Assert", "Any", "RandomElement", "ToString", "SortSeq",
    "JavaTime", "Randomize", "Deserialize", "Serialize", "AppendStr", "Split",
    "BOOLEAN", "Nat", "Int", "String", "TRUE", "FALSE", "TLCGet", "TLCSet",
    "ColoredSVG", "SVG", "Dot", "Csv", "Json",
}
TEMPORAL_PREFIX = {"[]", "<>"}
TEMPORAL_INFIX = {"~>", "-+->"}
# ``[]P`` and ``[A]_v`` are safety forms: TLC's symmetry reduction preserves
# them.  Only eventualities and fairness make symmetry reduction unsound.
EVENTUALITY_PREFIX = {"<>"}
EVENTUALITY_INFIX = {"~>", "-+->"}


@dataclass
class Write:
    var: str
    form: str            # "=" | "\\in" | "unchanged"
    rhs: N | None
    opdef: str
    module: str
    line: int


@dataclass
class Read:
    name: str
    kind: str            # variable | constant | operator | builtin | unknown
    mode: str            # rhs | guard | property | init | unchanged | decl
    opdef: str
    module: str
    line: int
    node: N | None = None


@dataclass
class SpecProgram:
    ctx: SpecContext
    name_kind: dict[str, str] = field(default_factory=dict)
    alias_module: dict[str, str] = field(default_factory=dict)
    roots: list[str] = field(default_factory=list)
    init_name: str | None = None
    next_name: str | None = None
    reachable: set[str] = field(default_factory=set)
    writes: list[Write] = field(default_factory=list)
    reads: list[Read] = field(default_factory=list)
    invariant_names: list[str] = field(default_factory=list)
    property_names: list[str] = field(default_factory=list)
    liveness: bool = False
    liveness_reasons: list[str] = field(default_factory=list)
    has_fairness: bool = False
    has_eventuality: bool = False
    temporal_properties: list[str] = field(default_factory=list)
    unresolved: collections.Counter = field(default_factory=collections.Counter)
    notes: list[str] = field(default_factory=list)

    # -- construction --------------------------------------------------------
    @classmethod
    def build(cls, ctx: SpecContext) -> "SpecProgram":
        program = cls(ctx=ctx)
        program._classify_names()
        program._collect_aliases()
        program._resolve_roots()
        program._reachability()
        program._extract_reads_writes()
        program._detect_liveness()
        return program

    def _classify_names(self) -> None:
        for name, info in self.ctx.constants.items():
            self.name_kind[name] = "constant" if info.arity == 0 else "operator-constant"
        for name in self.ctx.variables:
            self.name_kind[name] = "variable"
        for name in self.ctx.opdefs:
            self.name_kind.setdefault(name, "operator")
        for name in BUILTIN_OPERATORS:
            self.name_kind.setdefault(name, "builtin")

    def _collect_aliases(self) -> None:
        for name, definition in self.ctx.opdefs.items():
            body = definition.kid("body")
            if body is not None and body.kind == "instance":
                module = body.text.split("!")[0]
                if module:
                    self.alias_module[name] = module

    def _definition_body(self, name: str) -> N | None:
        definition = self.ctx.definition_of(name)
        return definition.kid("body") if definition is not None else None

    def definition_body(self, name: str) -> N | None:
        """Body of an operator definition, following ``Alias!Op`` bang paths."""
        if not name:
            return None
        body = self._definition_body(name)
        if body is not None:
            return body
        if "!" in name:
            return self._definition_body(name.split("!")[-1])
        for alias, module in self.alias_module.items():
            if name.startswith(alias + "!"):
                candidate = self._definition_body(f"{module}!{name.split('!')[-1]}")
                if candidate is not None:
                    return candidate
        return None

    def _resolve_roots(self) -> None:
        cfg = self.ctx.cfg
        self.invariant_names = list(cfg.invariants)
        self.property_names = list(cfg.properties)
        self.roots = [n for n in [cfg.init, cfg.next, cfg.specification,
                                  *cfg.invariants, *cfg.properties,
                                  *cfg.constraints, *cfg.action_constraints] if n]
        for name in (cfg.symmetry, cfg.view):
            if name:
                self.roots.append(name)

        if cfg.specification and not cfg.init:
            body = self._definition_body(cfg.specification.split("!")[-1])
            if body is not None:
                for part in flatten_conjunction(body):
                    if part.kind in ("name", "bang") and self.init_name is None:
                        self.init_name = self._simple_name(part)
                # ``Init /\ [][Next]_vars`` nests the stutter inside the always
                # operator, so the whole body is searched, not just the top level.
                for node in body.walk():
                    if node.kind in ("stutter", "fair") and self.next_name is None:
                        action = node.kid("action")
                        if action is not None and action.kind in ("name", "bang"):
                            self.next_name = self._simple_name(action)
        self.init_name = cfg.init or self.init_name or _guess(self.ctx.opdefs, ("Init",))
        self.next_name = cfg.next or self.next_name or _guess(self.ctx.opdefs, ("Next",))
        if self.init_name:
            self.roots.append(self.init_name)
        if self.next_name:
            self.roots.append(self.next_name)
        if not self.init_name and not cfg.specification:
            self.notes.append("no initial predicate identified")
        if not self.next_name and not cfg.specification:
            self.notes.append("no next-state relation identified")

    @staticmethod
    def _simple_name(node: N) -> str:
        if node.kind == "bang":
            left, right = node.kid("left"), node.kid("right")
            if left is not None and right is not None:
                return f"{left.text}!{right.text}"
        return node.text

    def _reachability(self) -> None:
        queue = list(self.roots)
        seen: set[str] = set()
        while queue:
            name = queue.pop()
            target = name.split("!")[-1]
            if target in seen:
                continue
            seen.add(target)
            body = self._definition_body(name)
            if body is None:
                if target not in self.name_kind or self.name_kind[target] == "unknown":
                    self.unresolved[name] += 1
                continue
            for node in body.walk():
                if node.kind == "name":
                    if node.text in self.ctx.opdefs:
                        queue.append(node.text)
                elif node.kind == "bang":
                    left, right = node.kid("left"), node.kid("right")
                    if left is None or right is None:
                        continue
                    module = self.alias_module.get(left.text, left.text)
                    qualified = f"{module}!{right.text}"
                    if qualified in self.ctx.opdefs:
                        queue.append(qualified)
                    elif right.text in self.ctx.opdefs:
                        queue.append(right.text)
        self.reachable = seen

    def _extract_reads_writes(self) -> None:
        targets = sorted(self.reachable)
        if self.init_name and self.init_name not in targets:
            targets.append(self.init_name)
        for name in targets:
            body = self._definition_body(name)
            if body is None:
                continue
            module = self.ctx.opdef_module.get(name.split("!")[-1], self.ctx.module_name)
            mode = "property" if name in set(self.invariant_names + self.property_names) \
                else ("init" if name == self.init_name else "guard")
            self._walk(body, name, module, mode, bound=set(), in_rhs=False)

    def _walk(self, node: N, opdef: str, module: str, mode: str,
              bound: set[str], in_rhs: bool) -> None:
        kind = node.kind
        local_bound = set(bound)

        if kind == "name":
            if node.text not in local_bound:
                resolved = self.name_kind.get(node.text, "unknown")
                if resolved == "unknown":
                    self.unresolved[node.text] += 1
                self.reads.append(Read(name=node.text, kind=resolved,
                                       mode="rhs" if in_rhs else mode,
                                       opdef=opdef, module=module,
                                       line=node.line, node=node))
            return

        if kind == "infix" and node.text in ("=", "\\in"):
            lhs, rhs = node.kid("lhs"), node.kid("rhs")
            target: tuple[str, str] | None = None
            if lhs is not None and lhs.kind == "postfix" and lhs.text == "'":
                operand = lhs.kid("operand")
                if operand is not None and operand.kind == "name" \
                        and operand.text not in local_bound:
                    target = (operand.text, node.text)
            elif mode == "init" and lhs is not None and lhs.kind == "name" \
                    and lhs.text not in local_bound \
                    and self.name_kind.get(lhs.text) == "variable":
                # ``Init`` assigns without primes by convention; it is still an
                # assignment for the purpose of influence.
                target = (lhs.text, "=init")
            if target is not None:
                self.writes.append(Write(var=target[0], form=target[1], rhs=rhs,
                                         opdef=opdef, module=module, line=node.line))
                if rhs is not None:
                    self._walk(rhs, opdef, module, mode, local_bound, in_rhs=True)
                return

        if kind == "postfix" and node.text == "'":
            # Not an assignment target, so this is a read of a next-state value.
            operand = node.kid("operand")
            if operand is not None and operand.kind == "name" \
                    and operand.text not in local_bound:
                self.reads.append(Read(
                    name=operand.text,
                    kind=self.name_kind.get(operand.text, "unknown"),
                    mode="rhs" if in_rhs else mode, opdef=opdef, module=module,
                    line=node.line, node=node))
            return

        if kind == "prefix" and node.text == "UNCHANGED":
            for leaf in node.walk():
                if leaf.kind == "name" and leaf.text not in local_bound \
                        and self.name_kind.get(leaf.text) == "variable":
                    self.writes.append(Write(var=leaf.text, form="unchanged", rhs=None,
                                             opdef=opdef, module=module, line=leaf.line))
            return

        if kind == "opdef":
            params = node.kid("params")
            if params is not None:
                for leaf in params.walk():
                    if leaf.kind == "name":
                        local_bound.add(leaf.text)

        if kind in ("binder", "lambda"):
            for var in node.kids_in("var", "param"):
                for leaf in var.walk():
                    if leaf.kind == "name":
                        local_bound.add(leaf.text)
            for role in ("domain", "body"):
                child = node.kid(role) if kind == "lambda" else None
                if kind == "binder":
                    child = node.kid("domain")
                if child is not None:
                    self._walk(child, opdef, module, mode, bound, in_rhs)
            if kind == "lambda":
                body = node.kid("body")
                if body is not None:
                    self._walk(body, opdef, module, mode, local_bound, in_rhs)
            else:
                sibling = node.parent
                if sibling is not None:
                    for other in sibling.kids:
                        if other is node:
                            continue
                        if other.role in ("pred", "body"):
                            self._walk(other, opdef, module, mode, local_bound, in_rhs)
                return
            return

        if kind == "let":
            for definition in node.kids_in("def"):
                self._walk(definition, opdef, module, mode, local_bound, in_rhs)
                if definition.kind == "opdef":
                    local_bound.add(definition.text)
            body = node.kid("body")
            if body is not None:
                self._walk(body, opdef, module, mode, local_bound, in_rhs)
            return

        if kind == "stutter":
            subscript = node.kid("subscript")
            action = node.kid("action")
            # ``[Next]_vars`` mentions every variable only to say "unchanged";
            # that is structural, not a semantic read, so it is not recorded.
            if action is not None:
                self._walk(action, opdef, module, mode, local_bound, in_rhs)
            if subscript is not None:
                self.notes.append(f"stutter subscript ignored in {opdef}")
            return

        for child in node.kids:
            self._walk(child, opdef, module, mode, local_bound, in_rhs)

    def _detect_liveness(self) -> None:
        cfg = self.ctx.cfg
        self.temporal_properties = list(cfg.properties)
        visited: set[str] = set()
        for name in list(cfg.properties) + list(cfg.invariants):
            if name:
                self._scan_temporal(name, depth=0, visited=visited)
        if cfg.specification:
            self._scan_temporal(cfg.specification, depth=0, visited=visited)
        self.liveness = self.has_fairness or self.has_eventuality
        if cfg.properties and not self.liveness:
            self._add_reason(
                "the configuration checks temporal PROPERTIES ("
                + ", ".join(cfg.properties) + ") but every definition reachable "
                "from them is safety shaped ([]P and [A]_v), which TLC's symmetry "
                "reduction preserves")

    def _scan_temporal(self, name: str, depth: int, visited: set[str]) -> None:
        """Follow a checked property through calls and INSTANCE references.

        A property such as ``PROPERTIES SimpleAllocator`` may resolve to
        ``SimpleAllocator == Simple!SimpleAllocator``: the temporal operator lives
        in another module.  Stopping at the syntactic body would conclude "safety"
        and emit a symmetry reduction that is unsound for that property -- which is
        exactly what happened on AllocatorRefinement before this routine existed.
        """
        key = name.split("!")[-1]
        if not key or key in visited or depth > 4:
            return
        visited.add(key)
        body = self.definition_body(name)
        if body is None:
            self.has_eventuality = True
            self._add_reason(f"checked property {name} cannot be resolved to a "
                             "definition, so its safety-only status is unknown")
            return
        for node in body.walk():
            if node.kind == "fair":
                self.has_fairness = True
                self._add_reason(f"{name} assumes fairness ({node.text})")
            elif node.kind == "prefix" and node.text in EVENTUALITY_PREFIX:
                self.has_eventuality = True
                self._add_reason(f"{name} contains the eventuality operator {node.text}")
            elif node.kind == "infix" and node.text in EVENTUALITY_INFIX:
                self.has_eventuality = True
                self._add_reason(f"{name} contains the leads-to operator {node.text}")
            elif node.kind == "bang":
                left, right = node.kid("left"), node.kid("right")
                if left is not None and right is not None:
                    module = self.alias_module.get(left.text, left.text)
                    for candidate in (f"{module}!{right.text}", right.text):
                        if candidate in self.ctx.opdefs:
                            self._scan_temporal(candidate, depth + 1, visited)
                            break
                    else:
                        self.has_eventuality = True
                        self._add_reason(f"{name} references {left.text}!{right.text}, "
                                         "which cannot be resolved")
            elif node.kind == "name" and node.text in self.ctx.opdefs                     and node.role in ("head", "action", "operand", "lhs", "rhs", "body")                     and node.text not in visited:
                self._scan_temporal(node.text, depth + 1, visited)

    def _add_reason(self, reason: str) -> None:
        if reason not in self.liveness_reasons:
            self.liveness_reasons.append(reason)

    # -- queries used by the analyses ---------------------------------------
    def variables_read_in(self, mode: str) -> set[str]:
        return {r.name for r in self.reads
                if r.mode == mode and self.name_kind.get(r.name) == "variable"}

    def variables_written(self) -> set[str]:
        return {w.var for w in self.writes}

    def writes_of(self, var: str) -> list[Write]:
        return [w for w in self.writes if w.var == var]

    def reads_of(self, name: str) -> list[Read]:
        return [r for r in self.reads if r.name == name]

    def to_dict(self) -> dict:
        return {
            "module": self.ctx.module_name,
            "constants": sorted(self.ctx.constants),
            "variables": list(self.ctx.variables),
            "init": self.init_name,
            "next": self.next_name,
            "reachable_definitions": len(self.reachable),
            "writes": len(self.writes),
            "reads": len(self.reads),
            "invariants": self.invariant_names,
            "properties": self.property_names,
            "liveness": self.liveness,
            "liveness_reasons": self.liveness_reasons,
            "unresolved_names": dict(self.unresolved.most_common(10)),
            "instance_aliases": self.alias_module,
            "notes": self.notes[:10],
        }


def flatten_conjunction(node: N) -> list[N]:
    """Top-level conjuncts of a bulleted or inline conjunction."""
    if node.kind == "infix" and node.text == "\\land":
        return flatten_conjunction(node.kid("lhs")) + flatten_conjunction(node.kid("rhs"))
    return [node]


def _guess(opdefs: dict[str, N], names: tuple[str, ...]) -> str | None:
    for name in names:
        if name in opdefs:
            return name
    return None


def load_program(spec_dir: Path, module: str, cfg: Path,
                 support_dirs: list[Path] | None = None) -> SpecProgram:
    from ..context import load_context
    return SpecProgram.build(load_context(spec_dir, module, cfg, support_dirs))
