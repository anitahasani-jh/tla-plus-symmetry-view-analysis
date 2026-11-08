"""End-to-end pipeline: analyse a model, generate artifacts, run the arms.

This is the single code path used by the command line tool and by the experiment
harness, so a number in the report can always be traced back to
``analyze_model`` + ``run_arm`` on a pinned model.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

from .analysis.history import analyze_history
from .analysis.program import SpecProgram
from .analysis.symmetry import analyze_symmetry
from .codegen import GeneratedArtifacts, generate, strip_reduction_directives
from .context import load_context, probe_constant_values
from .tlc import TlcBudget, TlcResult, prepare_workdir, run_tlc
from .util import write_json


@dataclass
class ModelSpec:
    model_id: str
    spec_dir: Path
    module: str
    config: Path
    family: str = ""
    source: str = ""
    notes: str = ""

    @classmethod
    def from_dict(cls, data: dict, root: Path) -> "ModelSpec":
        spec_dir = Path(data["spec_dir"])
        if not spec_dir.is_absolute():
            spec_dir = Path(root) / spec_dir
        config = Path(data["config"])
        if not config.is_absolute():
            config = spec_dir / config.name if (spec_dir / config.name).exists() else Path(root) / config
        return cls(model_id=data.get("model_id") or data["module"],
                   spec_dir=spec_dir, module=data["module"], config=config,
                   family=data.get("family", ""), source=data.get("source", ""),
                   notes=data.get("notes", ""))

    def to_dict(self) -> dict:
        return {"model_id": self.model_id, "spec_dir": str(self.spec_dir),
                "module": self.module, "config": str(self.config),
                "family": self.family, "source": self.source, "notes": self.notes}


@dataclass
class AnalysisResult:
    model: ModelSpec
    context: dict
    program: dict
    symmetry: dict
    history: dict
    artifacts: GeneratedArtifacts
    probe: dict
    analysis_seconds: float
    notes: list[str] = field(default_factory=list)
    program_obj: SpecProgram | None = field(default=None, repr=False)

    def to_dict(self) -> dict:
        return {"model": self.model.to_dict(), "context": self.context,
                "program": self.program, "symmetry": self.symmetry,
                "history": self.history, "artifacts": self.artifacts.to_dict(),
                "probe": self.probe, "analysis_seconds": self.analysis_seconds,
                "notes": self.notes}


def analyze_model(model: ModelSpec, budget: TlcBudget,
                  support_dirs: list[Path], workroot: Path,
                  allow_liveness: bool = False, version: str = "1.0.0",
                  skip_probe: bool = False) -> AnalysisResult:
    started = time.perf_counter()
    ctx = load_context(model.spec_dir, model.module, model.config,
                       support_dirs=support_dirs)
    probe_info: dict = {}
    if not skip_probe:
        workdir = Path(workroot) / model.model_id / "probe"
        probe = probe_constant_values(ctx, workdir, budget, support_dirs=support_dirs,
                                      log_dir=Path(workroot) / model.model_id / "logs")
        probe_info = {"verdict": probe.verdict, "seconds": probe.wall_seconds,
                      "constants": {name: (info.value_text or "")
                                    for name, info in ctx.constants.items()},
                      "error_lines": probe.error_lines[:5]}
    program = SpecProgram.build(ctx)
    symmetry = analyze_symmetry(program)
    history = analyze_history(program)
    artifacts = generate(program, symmetry, history, allow_liveness=allow_liveness,
                         version=version)
    elapsed = round(time.perf_counter() - started, 3)
    return AnalysisResult(model=model, context=ctx.to_dict(), program=program.to_dict(),
                          symmetry=symmetry.to_dict(), history=history.to_dict(),
                          artifacts=artifacts, probe=probe_info,
                          analysis_seconds=elapsed, notes=artifacts.notes,
                          program_obj=program)


def arm_plan(model: ModelSpec, artifacts: GeneratedArtifacts) -> dict[str, dict]:
    """Which module and configuration file each arm uses.

    Every arm runs the generated wrapper (which merely EXTENDS the original) so
    that the four arms differ only in their configuration directive.  ``direct``
    runs the untouched original module and is the control that shows the wrapper
    is transparent.
    """
    base_text, _ = strip_reduction_directives(
        model.config.read_text(encoding="utf-8", errors="replace"))
    plan: dict[str, dict] = {
        "direct": {"module": model.module, "config_name": f"{model.module}_sv_direct",
                   "config_text": base_text},
    }
    if artifacts.applicable.get("manual"):
        # The author's configuration refers to operators of the original module
        # (``SYMMETRY PaxosSymmetry``), so it runs the original module and does
        # not need the wrapper -- which matters when SymView proposed nothing.
        plan["manual"] = {"module": model.module,
                          "config_name": f"{model.module}_sv_manual",
                          "config_text": artifacts.configs["manual"]}
    if not artifacts.wrapper_text:
        plan["plain"] = {"module": model.module,
                         "config_name": f"{model.module}_sv_plain",
                         "config_text": base_text}
        return plan
    for arm in ("plain", "symmetry", "view", "both"):
        if not artifacts.applicable.get(arm):
            continue
        plan[arm] = {"module": artifacts.wrapper_module,
                     "config_name": f"{model.module}_sv_{arm}",
                     "config_text": artifacts.configs[arm]}
    return plan


def run_arm(model: ModelSpec, arm: str, artifacts: GeneratedArtifacts,
            budget: TlcBudget, support_dirs: list[Path], workroot: Path,
            timeout_s: int | None = None, log_dir: Path | None = None,
            overlay: dict[str, str] | None = None, tag: str = "") -> TlcResult:
    plan = arm_plan(model, artifacts).get(arm)
    if plan is None:
        result = TlcResult(label=f"{model.model_id}:{arm}", module=model.module,
                           verdict="not-applicable")
        result.error_lines.append(f"arm {arm} is not applicable to this model")
        return result
    workdir = Path(workroot) / model.model_id / f"{arm}{tag}"
    extra = dict(artifacts.files)
    extra.update(overlay or {})
    extra[f"{plan['config_name']}.cfg"] = plan["config_text"]
    prepare_workdir(model.spec_dir, workdir, support_dirs=support_dirs,
                    extra_files=extra)
    local_budget = TlcBudget(jar=budget.jar, java=budget.java,
                             community_jar=budget.community_jar,
                             workers=budget.workers, heap_mb=budget.heap_mb,
                             timeout_s=timeout_s or budget.timeout_s,
                             extra_jvm=list(budget.extra_jvm),
                             extra_tlc=list(budget.extra_tlc))
    return run_tlc(workdir, plan["module"], plan["config_name"], local_budget,
                   label=f"{model.model_id}__{arm}",
                   log_dir=log_dir or (Path(workroot) / model.model_id / "logs"))


def save_analysis(result: AnalysisResult, path: Path) -> Path:
    write_json(Path(path), result.to_dict())
    return Path(path)
