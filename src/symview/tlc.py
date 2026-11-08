"""TLC invocation, output parsing and the constant probe.

Every number SymView reports about a model comes from a real TLC run recorded
here: the raw stdout is kept, the parsed fields are stored as JSON, and the
budget (workers, heap, timeout) is fixed by the caller so that all experimental
arms are comparable.

Two TLC behaviours drove the design:

* ``SYMMETRY`` requires an operator whose value is a *set of permutations*, and
  ``VIEW`` requires a *zero-argument* operator, so a reduction can only be
  attached through a generated wrapper module -- the original specification is
  never modified.
* module-level ``ASSUME``s are evaluated right after ``Starting...`` and before
  the initial states are computed.  Printing constant values from an ``ASSUME``
  and terminating TLC as soon as the markers appear therefore yields the exact
  constant values, at parse cost only, even for models that are far too large to
  check.  This is how SymView obtains ground truth about the model values
  instead of guessing them from the configuration text.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

PROBE_MARKER = "#SVCONST"

RE_VERSION = re.compile(r"TLC2 Version ([0-9.]+) of (.+?) \(rev: (\w+)\)")
RE_HEADER = re.compile(r"with (\d+) workers on (\d+) cores with (\d+)MB heap")
RE_SEED = re.compile(r"and seed (-?\d+)")
RE_STATES = re.compile(r"(\d+) states generated, (\d+) distinct states found, "
                       r"(\d+) states left on queue")
RE_DEPTH = re.compile(r"The depth of the complete state graph search is (\d+)")
RE_OUTDEGREE = re.compile(r"The average outdegree of the complete state graph is "
                          r"([\d.]+) \(minimum is ([\d.]+), the maximum ([\d.]+) "
                          r"and the 95th percentile is ([\d.]+)\)")
RE_FINISHED = re.compile(r"Finished in (\d+)s at")
RE_INIT_STATES = re.compile(r"Finished computing initial states: (\d+) distinct")
RE_INVARIANT_VIOLATED = re.compile(r"Error: Invariant (\S+) is violated")
RE_PROPERTY_VIOLATED = re.compile(r"Error: (?:Temporal property|Property) (\S+) is violated")
RE_TEMPORAL_VIOLATED = re.compile(r"Error: Temporal properties were violated")
RE_PROPERTY_NAME = re.compile(r"Property (\S+) is violated")
RE_DEADLOCK = re.compile(r"Error: Deadlock reached")
RE_PARSE_FAILED = re.compile(r"Parsing or semantic analysis failed")
RE_EXCEPTION = re.compile(r"TLC threw an unexpected exception")
RE_OK = re.compile(r"Model checking completed\. No error has been found")
RE_FINGERPRINT = re.compile(r"calculated \(optimistic\):\s+val = ([\d.E+-]+)")
RE_ASSUMPTION_FAILED = re.compile(r"Error: Assumption (.+?) (?:is false|evaluated to FALSE)")
RE_STATE_LINE = re.compile(r"^State (\d+): (.*)$")


@dataclass
class TlcBudget:
    """Fixed resource budget.  Identical for every arm of an experiment."""

    jar: Path
    java: str = "java"
    community_jar: Path | None = None
    workers: int = 2
    heap_mb: int = 2048
    timeout_s: int = 120
    extra_jvm: list[str] = field(default_factory=list)
    extra_tlc: list[str] = field(default_factory=list)

    def classpath(self) -> str:
        parts = [str(self.jar)]
        if self.community_jar and Path(self.community_jar).exists():
            parts.append(str(self.community_jar))
        return os.pathsep.join(parts)

    def command(self, module: str, config: str | None) -> list[str]:
        cmd = [self.java, f"-Xmx{self.heap_mb}m", *self.extra_jvm,
               "-cp", self.classpath(), "tlc2.TLC",
               "-workers", str(self.workers), *self.extra_tlc]
        if config:
            cmd += ["-config", config]
        cmd.append(module)
        return cmd

    def to_dict(self) -> dict:
        return {"jar": str(self.jar), "java": self.java,
                "community_jar": str(self.community_jar) if self.community_jar else None,
                "workers": self.workers, "heap_mb": self.heap_mb,
                "timeout_s": self.timeout_s, "extra_jvm": self.extra_jvm,
                "extra_tlc": self.extra_tlc}


@dataclass
class TlcResult:
    label: str = ""
    module: str = ""
    config: str = ""
    workdir: str = ""
    command: list[str] = field(default_factory=list)
    returncode: int | None = None
    verdict: str = "unknown"
    wall_seconds: float | None = None
    tlc_seconds: int | None = None
    tlc_version: str = ""
    tlc_revision: str = ""
    seed: int | None = None
    workers: int | None = None
    cores: int | None = None
    heap_mb: int | None = None
    states_generated: int | None = None
    distinct_states: int | None = None
    queue_remaining: int | None = None
    initial_states: int | None = None
    depth: int | None = None
    outdegree_avg: float | None = None
    fingerprint_collision: str | None = None
    violated_invariants: list[str] = field(default_factory=list)
    violated_properties: list[str] = field(default_factory=list)
    deadlock: bool = False
    error_lines: list[str] = field(default_factory=list)
    symmetry_lines: list[str] = field(default_factory=list)
    trace: list[str] = field(default_factory=list)
    timed_out: bool = False
    stdout_chars: int = 0
    log_path: str = ""

    @property
    def completed(self) -> bool:
        return self.verdict in ("ok", "violation", "deadlock")

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}


def prepare_workdir(spec_dir: Path, dest: Path,
                    support_dirs: list[Path] | None = None,
                    extra_files: dict[str, str] | None = None,
                    clean: bool = True) -> Path:
    """Assemble a scratch directory TLC can run in.

    The specification directory is copied (never modified in place), the support
    modules are added, and generated files are written on top.
    """
    dest = Path(dest)
    if clean and dest.exists():
        shutil.rmtree(dest, ignore_errors=True)
    dest.mkdir(parents=True, exist_ok=True)
    for source in [Path(spec_dir), *(support_dirs or [])]:
        if not source.exists():
            continue
        for path in sorted(source.rglob("*")):
            if path.is_file() and path.suffix in (".tla", ".cfg"):
                target = dest / path.relative_to(source).name
                if not target.exists():
                    shutil.copy2(path, target)
    for name, text in (extra_files or {}).items():
        (dest / name).write_text(text, encoding="utf-8")
    return dest


def parse_output(text: str, result: TlcResult) -> TlcResult:
    result.stdout_chars = len(text)
    version = RE_VERSION.search(text)
    if version:
        result.tlc_version, result.tlc_revision = version.group(1), version.group(3)
    header = RE_HEADER.search(text)
    if header:
        result.workers, result.cores, result.heap_mb = (int(header.group(1)),
                                                        int(header.group(2)),
                                                        int(header.group(3)))
    seed = RE_SEED.search(text)
    if seed:
        result.seed = int(seed.group(1))
    states = RE_STATES.search(text)
    if states:
        result.states_generated = int(states.group(1))
        result.distinct_states = int(states.group(2))
        result.queue_remaining = int(states.group(3))
    init_states = RE_INIT_STATES.search(text)
    if init_states:
        result.initial_states = int(init_states.group(1))
    depth = RE_DEPTH.search(text)
    if depth:
        result.depth = int(depth.group(1))
    outdegree = RE_OUTDEGREE.search(text)
    if outdegree:
        result.outdegree_avg = float(outdegree.group(1))
    finished = RE_FINISHED.search(text)
    if finished:
        result.tlc_seconds = int(finished.group(1))
    fingerprint = RE_FINGERPRINT.search(text)
    if fingerprint:
        result.fingerprint_collision = fingerprint.group(1)
    result.violated_invariants = sorted(set(RE_INVARIANT_VIOLATED.findall(text)))
    result.violated_properties = sorted(set(RE_PROPERTY_VIOLATED.findall(text)))
    if RE_TEMPORAL_VIOLATED.search(text) and not result.violated_properties:
        # TLC 2.16 prints the plural form plus a counter-example; the violated
        # property name is only in the headline of some versions, so it is
        # recorded as a generic temporal violation.
        result.violated_properties = ["<temporal property>"]
    result.deadlock = bool(RE_DEADLOCK.search(text))
    result.symmetry_lines = [line.strip() for line in text.splitlines()
                             if "ymmetr" in line][:20]

    lines = text.splitlines()
    result.error_lines = [line.strip() for line in lines if line.startswith("Error")][:20]
    trace: list[str] = []
    in_trace = False
    for line in lines:
        if RE_STATE_LINE.match(line):
            in_trace = True
        elif in_trace and (line.startswith("Error") or line.startswith("Finished")
                           or "states generated" in line):
            in_trace = False
        if in_trace and len(trace) < 400:
            trace.append(line)
    result.trace = trace

    if result.violated_invariants or result.violated_properties:
        result.verdict = "violation"
    elif result.deadlock:
        result.verdict = "deadlock"
    elif RE_OK.search(text):
        result.verdict = "ok"
    elif RE_PARSE_FAILED.search(text):
        result.verdict = "parse-error"
    elif RE_EXCEPTION.search(text):
        result.verdict = "crash"
    elif result.error_lines:
        result.verdict = "error"
    return result


def run_tlc(workdir: Path, module: str, config: str | None, budget: TlcBudget,
            label: str = "", log_dir: Path | None = None) -> TlcResult:
    """Run one TLC model check inside ``workdir`` and parse its report."""
    workdir = Path(workdir)
    command = budget.command(f"{module}.tla", f"{config}.cfg" if config else None)
    result = TlcResult(label=label, module=module, config=config or "",
                       workdir=str(workdir), command=command)
    started = time.perf_counter()
    stdout_chunks: list[str] = []
    try:
        process = subprocess.run(command, cwd=str(workdir), capture_output=True,
                                 text=True, encoding="utf-8", errors="replace",
                                 timeout=budget.timeout_s)
        result.returncode = process.returncode
        stdout_chunks.append(process.stdout or "")
        if process.stderr:
            stdout_chunks.append("\n--- stderr ---\n" + process.stderr)
    except subprocess.TimeoutExpired as exc:
        result.timed_out = True
        result.verdict = "timeout"
        stdout_chunks.append(exc.stdout.decode("utf-8", "replace")
                             if isinstance(exc.stdout, bytes) else (exc.stdout or ""))
        stdout_chunks.append(f"\n--- killed after {budget.timeout_s}s ---\n")
    result.wall_seconds = round(time.perf_counter() - started, 3)

    text = "".join(stdout_chunks)
    if not result.timed_out:
        parse_output(text, result)
    if log_dir is not None:
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = Path(log_dir) / f"{label or module}.log"
        log_path.write_text(text, encoding="utf-8")
        result.log_path = str(log_path)
    return result


def probe_constants(workdir: Path, module: str, config: str, constants: list[str],
                    budget: TlcBudget, probe_module: str, probe_config: str,
                    log_dir: Path | None = None) -> tuple[dict[str, str], TlcResult]:
    """Print the concrete value of every zero-arity constant, then stop TLC.

    Returns a mapping from constant name to the *text* TLC printed for its value
    (parsing that text into a value model is done by :mod:`symview.consteval`).
    """
    command = budget.command(f"{probe_module}.tla", f"{probe_config}.cfg")
    result = TlcResult(label=f"{module}:probe", module=probe_module, config=probe_config,
                       workdir=str(workdir), command=command)
    wanted = set(constants)
    values: dict[str, str] = {}
    lines: list[str] = []
    started = time.perf_counter()
    try:
        process = subprocess.Popen(command, cwd=str(workdir), stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, text=True,
                                   encoding="utf-8", errors="replace")
        deadline = started + budget.timeout_s
        assert process.stdout is not None
        for line in process.stdout:
            lines.append(line)
            if PROBE_MARKER in line:
                name, value = _split_probe_line(line)
                if name is not None:
                    values[name] = value
            if wanted and wanted.issubset(values.keys()):
                break
            if time.perf_counter() > deadline:
                result.timed_out = True
                break
        process.kill()
        process.wait(timeout=30)
        result.returncode = process.returncode
    except (OSError, subprocess.SubprocessError) as exc:
        result.error_lines.append(f"probe failed: {exc}")
        result.verdict = "crash"
    result.wall_seconds = round(time.perf_counter() - started, 3)
    text = "".join(lines)
    parse_output(text, result)
    if result.timed_out:
        result.verdict = "timeout"
    elif not values:
        result.verdict = result.verdict if result.verdict != "unknown" else "error"
    else:
        result.verdict = "probe-ok"
    if log_dir is not None:
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = Path(log_dir) / f"{module}-probe.log"
        log_path.write_text(text, encoding="utf-8")
        result.log_path = str(log_path)
    return values, result


def _split_probe_line(line: str) -> tuple[str | None, str]:
    """``<<"#SVCONST", "Acceptor", {a1}>>`` -> ``("Acceptor", "{a1}")``."""
    text = line.strip()
    start = text.find(PROBE_MARKER)
    if start < 0:
        return None, ""
    text = text[start + len(PROBE_MARKER):]
    match = re.match(r'\s*",\s*"([^"]+)"\s*,\s*(.*?)>>\s*$', text, re.S)
    if not match:
        return None, ""
    return match.group(1), match.group(2).strip()


def save_result(result: TlcResult, path: Path, extra: dict | None = None) -> Path:
    payload = result.to_dict()
    if extra:
        payload["meta"] = extra
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                          encoding="utf-8")
    return Path(path)
