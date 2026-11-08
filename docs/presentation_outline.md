# SymView -- 15-minute Go/No-Go talk

Target: 12 slides, about one minute per slide, leaving roughly three minutes
for questions.  Result bullets are placeholders until the full run finishes;
every one is marked `[from analysis/output/tables]` and must be filled from the
generated tables, never typed by hand.

---

## Slide 1 -- Title and ask

- SymView: static suggestions for `SYMMETRY` and `VIEW` in TLC configurations.
- Input: an unmodified TLA+ specification plus its `.cfg`; output: a wrapper
  module and one configuration per experimental arm.
- The decision requested today: Go/No-Go for the full evaluation described in
  the protocol.
- Headline evidence: TLC 2.16, a pinned public corpus, eight ground-truth lab
  models, and a reproducible one-command pipeline.

Speaker note: This is a tooling and measurement project, and the ask is a
Go/No-Go on running and reporting the full study, not a demo of a finished
product.

---

## Slide 2 -- The problem: state explosion is the default

- TLC is explicit-state: it enumerates reachable states, so redundant
  interleavings dominate the cost.
- Hand-written `SYMMETRY` and `VIEW` can shrink that graph, but they are easy to
  get subtly wrong and are rarely shipped with public models.
- Public benchmarks mostly provide an unreduced `.cfg`, so the reduction is
  invisible in the baseline.
- A wrong suggestion is worse than no suggestion: it can hide a real violation.

Speaker note: The motivation is not a faster checker but a trustworthy
suggestion layer on top of the checker everyone already uses.

---

## Slide 3 -- The two reductions SymView proposes

- `SYMMETRY`: a constant whose value is a set of model values, used only through
  permutation-equivariant operators; TLC is given `Permutations(S)`.
- `VIEW`: a state abstraction that drops auxiliary/history variables nobody
  checked observes; TLC is given a zero-argument operator.
- The original specification is never edited: a generated
  `<Module>_SymView.tla` extends it and defines `SymViewPerms` / `SymViewView`.
- One `.cfg` per arm (`direct`, `plain`, `symmetry`, `view`, `both`) isolates the
  effect of each directive.

Speaker note: The same wrapper mechanism gives us both reductions and a clean
control for the measurement.

---

## Slide 4 -- Why soundness is subtle

- Symmetry needs equivariance: non-equivariant operators (`CHOOSE`, `<`,
  `SortSeq`, ordered identifiers) silently break the quotient.
- The configuration can distinguish an element: `Leader = p1` makes `Proc`
  asymmetric even when the module text looks symmetric.
- `VIEW` can drop a history variable only if no checked invariant reads it;
  `TypeOK` is enough to make the drop unsound.
- Liveness and fairness interact with symmetry, and TLC merges states after the
  view, so a violation on a merged-away lineage can disappear.

Speaker note: Every one of these failure modes is represented by a lab model,
which is why the soundness claim is measured rather than asserted.

---

## Slide 5 -- Method

- Parse the module and its `.cfg`; recover constant values by asking TLC itself
  (`ASSUME` + `PrintT`, terminated early).
- Check whether each candidate constant is used only through operators that
  commute with permutations; reject on any non-equivariant or unknown use.
- Classify variables as observable, influential, or history-only, and refuse a
  view when a checked property reads the candidate.
- Emit the wrapper and arm configurations, run TLC under one fixed budget, and
  record states, distinct states and wall time from raw output.

Speaker note: The pipeline is static where it can be and uses TLC only for the
facts that static analysis cannot know.

---

## Slide 6 -- Architecture and evidence trail

- `src/symview/`: lexer/parser, cfg reader, constant probe, symmetry and history
  analyses, code generation, TLC runner.
- `benchmarks/public/`: pinned corpus with hashes; `benchmarks/lab/`: eight
  hand-written models with authored ground truth.
- `config/`: corpus, experiment protocol and the frozen subset; `experiments/`
  and `analysis/` turn runs into tables and figures.
- `results/raw/**` is the evidence: one JSON per arm, repeat and mutant;
  nothing in the report is typed by hand.

Speaker note: The repository layout mirrors the evaluation questions so that a
reviewer can trace any number back to a single JSON file.

---

## Slide 7 -- RQ1: state and time reduction

- Compared arms: `direct` (original), `plain` (wrapper, no directive),
  `symmetry`, `view`, `both`.
- Metrics: generated states, distinct states, wall time, timeout count; median
  over repeats, same workers and heap for every arm.
- Expected shape: wrapper transparency (`direct` = `plain`), largest reduction
  from `both`, occasional overhead on tiny models.
- Result: median distinct-state reduction and median speed-up
  [from analysis/output/tables/rq1_reduction.md].
- Result: timeouts and models where the proposal does not apply
  [from analysis/output/tables/rq1_reduction.md].

Speaker note: The wrapper control is what makes the comparison causal rather
than a comparison of different specifications.

---

## Slide 8 -- RQ2: violation preservation on injected bugs

- Seeded mutants are generated from the parsed specification; a mutant is kept
  only if the unreduced baseline detects it.
- The same kept mutants are replayed under `symmetry`, `view` and `both`.
- The question: does a reduction lose a violation that the baseline found?
- Result: preservation rate per arm and the list of any lost violations
  [from analysis/output/tables/rq2_violation_preservation.md].
- A lost violation is a soundness incident, not a performance footnote.

Speaker note: Mutants give us bugs whose detection we can check exactly, which
is stronger than arguing that the reduction should preserve properties.

---

## Slide 9 -- RQ3: soundness and unsound-suggestion rate

- Eight lab models each isolate one decision: symmetric set, distinguished
  element, ordered identifiers, non-equivariant `CHOOSE`, history variable,
  history-looking variable, liveness, view-blocking invariant.
- The tool's accept/reject verdict is compared with the authored ground truth.
- Metrics: accepted candidates, rejected candidates, unsound acceptances,
  rejections with reasons (the conservative direction is visible).
- Result: 8/8 ground-truth agreement on the current build, with the reason
  distribution [from analysis/output/tables/rq3_soundness.md].
- Result: what the tool refused and why, including the view blocked by `TypeOK`
  [from analysis/output/tables/rq3_soundness.md].

Speaker note: The negative cases are the point of this slide: a tool that only
demonstrates successful reductions has not shown that it is sound.

---

## Slide 10 -- RQ4: ablation, symmetry versus view

- `plain` isolates wrapper overhead; `symmetry` and `view` isolate one reduction
  each; `both` measures the combination.
- Per model, report reduction relative to `plain` for distinct states and time.
- Result: median reduction by arm and the models where one arm is inapplicable
  [from analysis/output/tables/rq4_ablation.md].
- Result: whether the two reductions compose or overlap
  [from analysis/output/tables/rq4_ablation.md].

Speaker note: The ablation answers the practical question of which directive to
try first when a model has only one of the two structures.

---

## Slide 11 -- RQ5: coverage over the corpus

- How many fetched models ship a runnable `.cfg`, parse at 100% token coverage,
  and receive a certified symmetry set or view.
- Parser coverage is measured separately so that "no suggestion" can be
  distinguished from "not understood".
- Exclusions are recorded with reasons (missing config, baseline failure,
  timeout, no candidate).
- Result: coverage by family and the exclusion table
  [from analysis/output/tables/rq3_soundness.md] and
  [from analysis/output/tables/parser_robustness.md].
- Result: the false-positive/coverage trade-off on integer-indexed models
  [from analysis/output/tables/rq3_soundness.md].

Speaker note: Coverage is where a static tool is honest about its limits: a
refusal is a result, not a missing data point.

---

## Slide 12 -- Threats, limitations, and plan

- Timing noise on shared machines: medians over repeats, fixed workers/heap,
  no cross-machine claims.
- Mutant realism and authored ground truth are proxies; both are documented and
  the lab models are small by design.
- One checker version (TLC 2.16) and one corpus commit; Apalache is reported as
  not run, not as a comparison.
- Next: finish the full run, fill every placeholder from `analysis/output`,
  review the unsound-suggestion cases, and freeze the report tables.
- Decision requested: Go/No-Go for the full evaluation and the report.

Speaker note: The limitations are bounded and measurable, so the Go/No-Go
decision is about whether the current evidence is sufficient, not whether the
tool is perfect.
