"""The resolved context of one TLC model: modules, constants, variables, config.

The analysis needs a *flattened* view of a specification: the constants and
variables declared anywhere in the ``EXTENDS`` chain, the operator definitions
that a checked invariant expands to, and the concrete values TLC will actually
use for the constants.  This module builds exactly that, and records everything
it could not resolve so that the caller can refuse to certify a reduction
instead of guessing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .astnodes import N
from .lex import tokenize
from .parse_cfg import TlaConfig, parse_config_file
from .parse_tla import Parser, parse_file
from .tlc import PROBE_MARKER, TlcBudget, TlcResult, prepare_workdir, probe_constants
from .values import UnknownV, Val, value_from_ast

STANDARD_MODULES = {
    "Naturals", "Integers", "Sequences", "FiniteSets", "TLC", "Reals",
    "RealTime", "Randomization", "Bags", "Toolbox", "TLAPS",
}


@dataclass
class ConstInfo:
    name: str
    arity: int = 0
    declared_in: str = ""
    assignment_form: str = ""
    assignment_text: str = ""
    value: Val | None = None
    value_text: str = ""
    value_source: str = ""       # "tlc-probe" | "unresolved"


@dataclass
class SpecContext:
    spec_dir: Path
    module_name: str
    cfg_path: Path
    cfg: TlaConfig
    root_ast: N
    modules: dict[str, N] = field(default_factory=dict)
    module_files: dict[str, str] = field(default_factory=dict)
    module_tokens: dict[str, list] = field(default_factory=dict)
    unresolved_modules: list[str] = field(default_factory=list)
    builtin_modules: list[str] = field(default_factory=list)
    constants: dict[str, ConstInfo] = field(default_factory=dict)
    variables: list[str] = field(default_factory=list)
    opdefs: dict[str, N] = field(default_factory=dict)
    opdef_module: dict[str, str] = field(default_factory=dict)
    instances: list[N] = field(default_factory=list)
    assumes: list[N] = field(default_factory=list)
    theorems: list[N] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    parse_stats: dict = field(default_factory=dict)

    # -- queries -------------------------------------------------------------
    def operator_names(self) -> set[str]:
        return set(self.opdefs)

    def constant_names(self, arity_zero_only: bool = True) -> list[str]:
        return [name for name, info in self.constants.items()
                if not arity_zero_only or info.arity == 0]

    def definition_of(self, name: str) -> N | None:
        target = name.split("!")[-1]
        return self.opdefs.get(name) or self.opdefs.get(target)

    def checked_property_defs(self) -> list[tuple[str, N | None]]:
        out = []
        for name in self.cfg.invariants + self.cfg.properties:
            out.append((name, self.definition_of(name)))
        return out

    def to_dict(self) -> dict:
        return {
            "spec_dir": str(self.spec_dir),
            "module_name": self.module_name,
            "cfg_path": str(self.cfg_path),
            "modules": sorted(self.modules),
            "module_files": self.module_files,
            "unresolved_modules": self.unresolved_modules,
            "builtin_modules": self.builtin_modules,
            "constants": {k: {"arity": v.arity, "declared_in": v.declared_in,
                              "assignment_form": v.assignment_form,
                              "assignment_text": v.assignment_text,
                              "value_text": v.value_text or v.value.render() if v.value else "",
                              "value_kind": v.value.kind if v.value else None,
                              "value_source": v.value_source}
                          for k, v in self.constants.items()},
            "variables": self.variables,
            "instances": [i.text for i in self.instances],
            "opdefs": len(self.opdefs),
            "notes": self.notes,
            "parse_stats": self.parse_stats,
            "cfg": self.cfg.to_dict(),
        }


def load_context(spec_dir: Path, module_name: str, cfg_path: Path,
                 support_dirs: list[Path] | None = None) -> SpecContext:
    spec_dir = Path(spec_dir)
    cfg_path = Path(cfg_path)
    cfg = parse_config_file(cfg_path)
    spec_file = spec_dir / f"{module_name}.tla"
    root_ast, lex, stats = parse_file(spec_file)
    ctx = SpecContext(spec_dir=spec_dir, module_name=module_name, cfg_path=cfg_path,
                      cfg=cfg, root_ast=root_ast, parse_stats=stats)
    if not spec_file.exists():
        ctx.notes.append(f"missing specification file {spec_file}")
        return ctx

    module = _module_node(root_ast)
    if module is None:
        ctx.notes.append("no module found in specification file")
        return ctx
    ctx.modules[module_name] = module
    ctx.module_files[module_name] = str(spec_file)
    ctx.module_tokens[module_name] = lex.tokens
    _absorb(ctx, module, module_name)

    pending = [name.text for unit in module.kids_in("unit")
               if unit.kind == "extends" for name in unit.kids_in("module")]
    pending += _instance_targets(module)
    seen = {module_name}
    while pending:
        name = pending.pop(0)
        if name in seen:
            continue
        seen.add(name)
        if name in STANDARD_MODULES:
            ctx.builtin_modules.append(name)
            continue
        path = _find_module(spec_dir, name, support_dirs or [])
        if path is None:
            ctx.unresolved_modules.append(name)
            continue
        ast, sub_lex, sub_stats = parse_file(path)
        sub = _module_node(ast)
        if sub is None:
            ctx.unresolved_modules.append(name)
            continue
        ctx.modules[name] = sub
        ctx.module_files[name] = str(path)
        ctx.module_tokens[name] = sub_lex.tokens
        _absorb(ctx, sub, name)
        pending += [e.text for unit in sub.kids_in("unit")
                    if unit.kind == "extends" for e in unit.kids_in("module")]
        pending += _instance_targets(sub)

    _apply_config(ctx)
    return ctx


def _module_node(file_ast: N) -> N | None:
    modules = file_ast.kids_in("module")
    return modules[0] if modules else None


def _instance_targets(module: N) -> list[str]:
    """Modules named by ``INSTANCE``, so that ``Alias!Op`` can be resolved."""
    targets: list[str] = []
    for unit in module.kids_in("unit"):
        if unit.kind == "instance" and unit.text:
            targets.append(unit.text.split("!")[0])
        elif unit.kind == "opdef":
            body = unit.kid("body")
            if body is not None and body.kind == "instance" and body.text:
                targets.append(body.text.split("!")[0])
    return targets


def _find_module(spec_dir: Path, name: str, support_dirs: list[Path]) -> Path | None:
    candidates = [spec_dir / f"{name}.tla"]
    candidates += [Path(d) / f"{name}.tla" for d in support_dirs]
    candidates += [Path(d) / "community" / f"{name}.tla" for d in support_dirs]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _absorb(ctx: SpecContext, module: N, module_name: str) -> None:
    for unit in module.kids_in("unit"):
        if unit.kind == "constant-decl":
            for name_node in unit.kids_in("name"):
                arity = 0
                if name_node.note.startswith("operator-arity-"):
                    arity = int(name_node.note.rsplit("-", 1)[-1])
                elif name_node.note == "operator":
                    arity = 1
                info = ctx.constants.setdefault(
                    name_node.text,
                    ConstInfo(name=name_node.text, arity=arity, declared_in=module_name))
                info.arity = max(info.arity, arity)
        elif unit.kind == "variable-decl":
            for name_node in unit.kids_in("name"):
                if name_node.text not in ctx.variables:
                    ctx.variables.append(name_node.text)
        elif unit.kind == "opdef":
            if unit.text and unit.text not in ctx.opdefs:
                ctx.opdefs[unit.text] = unit
                ctx.opdef_module[unit.text] = module_name
            if module_name != ctx.module_name:
                ctx.opdefs.setdefault(f"{module_name}!{unit.text}", unit)
        elif unit.kind == "assume":
            ctx.assumes.append(unit)
        elif unit.kind == "theorem":
            ctx.theorems.append(unit)
        elif unit.kind == "instance":
            ctx.instances.append(unit)
        elif unit.kind == "local":
            inner = unit.kid("unit")
            if inner is not None:
                ctx.notes.append(f"LOCAL unit in {module_name}: {inner.kind}")


def _apply_config(ctx: SpecContext) -> None:
    for name, assignment in ctx.cfg.constants.items():
        info = ctx.constants.setdefault(ConstInfo(name=name).name,
                                        ConstInfo(name=name, declared_in="<config>"))
        info.assignment_form = assignment.form
        info.assignment_text = assignment.value_text
    for name in ctx.cfg.constants:
        if name not in ctx.constants:
            ctx.notes.append(f"configuration assigns undeclared constant {name}")
    for name in ctx.cfg.variables:
        if name not in ctx.variables:
            ctx.variables.append(name)


# -- TLC constant probe ------------------------------------------------------
def build_probe(module_name: str, constants: list[str]) -> tuple[str, str]:
    """Return ``(probe_module_name, probe_module_text)``.

    Each constant gets its own ``ASSUME`` so that one unprintable value cannot
    hide the others.  ``PrintT`` returns TRUE, so the assumptions hold and TLC
    evaluates them immediately after ``Starting...``.
    """
    probe_name = f"{module_name}_SVProbe"
    lines = [
        f"---- MODULE {probe_name} ----",
        f"EXTENDS {module_name}, TLC",
        "",
    ]
    for index, name in enumerate(constants):
        lines.append(f"ASSUME SVProbe{index} == "
                     f'PrintT(<<"{PROBE_MARKER}", "{name}", {name}>>)')
    lines.append("=====================================================================")
    return probe_name, "\n".join(lines) + "\n"


def parse_value_text(text: str) -> Val:
    """Parse one concrete value exactly as TLC printed it."""
    text = text.strip()
    if not text:
        return UnknownV("empty")
    tokens = tokenize(text).tokens
    try:
        node = Parser(tokens).parse_expr()
    except Exception as exc:  # never fatal: an unparsable value is simply unknown
        return UnknownV(f"{text[:120]} ({type(exc).__name__})")
    return value_from_ast(node)


def probe_constant_values(ctx: SpecContext, workdir: Path, budget: TlcBudget,
                          support_dirs: list[Path] | None = None,
                          log_dir: Path | None = None,
                          max_constants: int = 60) -> TlcResult:
    """Fill ``ctx.constants[*].value`` using TLC's own evaluator."""
    declared = [name for name in ctx.constant_names(arity_zero_only=True)
                if ctx.constants[name].declared_in not in ("<config>", "")]
    names = declared[:max_constants]
    if len(declared) > max_constants:
        ctx.notes.append(f"constant probe truncated to {max_constants} constants")
    # Constants that only exist in the configuration (plain model values such as
    # ``v1 = v1``) are not declared in any module, so referencing them from the
    # probe module would make SANY reject the whole probe.  Their value is the
    # literal in the configuration, which is read directly.
    for name, info in ctx.constants.items():
        if info.declared_in == "<config>" and info.assignment_form == "="                 and info.assignment_text and info.value is None:
            info.value = parse_value_text(info.assignment_text)
            info.value_text = info.assignment_text
            info.value_source = "config-literal"
    prepare_workdir(ctx.spec_dir, workdir, support_dirs=support_dirs)
    probe_name, probe_text = build_probe(ctx.module_name, names)
    (Path(workdir) / f"{probe_name}.tla").write_text(probe_text, encoding="utf-8")
    (Path(workdir) / f"{probe_name}.cfg").write_text(
        ctx.cfg_path.read_text(encoding="utf-8", errors="replace"), encoding="utf-8")
    values, result = probe_constants(workdir, ctx.module_name,
                                     ctx.cfg_path.stem, names, budget,
                                     probe_name, probe_name, log_dir=log_dir)
    for name in names:
        info = ctx.constants.get(name)
        if info is None:
            continue
        if name in values:
            info.value_text = values[name]
            info.value = parse_value_text(values[name])
            info.value_source = "tlc-probe"
        else:
            info.value = UnknownV("not-printed")
            info.value_source = "unresolved"
    return result
