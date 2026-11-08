# SymView

**Automatic symmetry detection and view abstraction for TLA+ / TLC.**

> Repository: <https://github.com/emiroow/symview-tla-symmetry-view> · release `v1.0.0`
> Persian report: [`docs/report_fa.md`](docs/report_fa.md) · soundness: [`docs/soundness_report_fa.md`](docs/soundness_report_fa.md)
> Slides: [`docs/slides/index.html`](docs/slides/index.html) · progress report: [`docs/progress_report_fa.md`](docs/progress_report_fa.md)

SymView reads a TLA+ specification together with its TLC configuration, decides
which constants form a sound symmetry set and which variables are pure history,
and emits the corresponding `SYMMETRY` and `VIEW` directives — or refuses, with a
written reason, when it cannot prove the reduction sound.

It never edits the specification. It generates a wrapper module that `EXTENDS`
the original and one configuration per experimental arm, then runs TLC and
records every state count, every timeout and every violation.

```
   .tla + .cfg ──► parser (AST, 100% token coverage)
                      │
   TLC constant probe ─┴─► exact values of the model values
                      │
        symmetry analysis (S1–S5) ──► candidate + verdict + reason
        history analysis  (influence graph) ──► droppable variables + view
                      │
                      └─► <Module>_SymView.tla + per-arm .cfg ──► TLC runs
```

---

## Quick start

```bash
bash setup.sh                     # dependencies + TLC check + smoke test
export PYTHONPATH=src             # or install the package with: pip install -e .
python -m symview analyze \
    --spec-dir benchmarks/public/transaction_commit \
    --module TCommit --config TCommit.cfg
```

```
SYMMETRY
  [ACCEPT] RM = {r1, r2, r3}  (group order 6)
           - RM is used only through permutation-equivariant operators and no
             other constant distinguishes its elements
  selected: RM
VIEW
  verdict   : none
  retained  : rmState
```

Run the arms through TLC:

```bash
python -m symview report \
    --spec-dir benchmarks/lab/LabLog --module LabLog --config LabLog.cfg \
    --arms direct plain symmetry view both
```

Full reproduction of the study:

```bash
bash run_all.sh --quick      # a few minutes
bash run_all.sh --full       # every repeat and every mutant
```

---

## What "sound" means here

A candidate constant `C` is accepted only if all of the following hold. The full
argument, including the proofs and the pitfalls, is in
[`docs/soundness_report_fa.md`](docs/soundness_report_fa.md).

| Test | Question | Nature |
|---|---|---|
| S1 | Does `C` evaluate (in TLC) to a set of at least two model values? | exact |
| S2 | Is every *other* constant's value invariant under permutations of `C`? | exact — adjacent transpositions generate the symmetric group, so `k-1` checks decide `k!` cases |
| S3 | Does any checked invariant/property name an individual element of `C`? | exact |
| S4 | Does any value containing an element of `C` reach a non-equivariant operator (`<`, arithmetic, `CHOOSE`, `Any`, `SortSeq`, `ToString`, …)? | conservative taint analysis, inter-procedural, record-field sensitive |
| S5 | Are all modules resolved and all operators on the taint path classified? | otherwise the verdict is **unknown**, never "probably fine" |

A variable is dropped from the view only when it is not observable, cannot reach
an observable variable in the influence graph, and does not occur in any guard —
i.e. when the projection is a bisimulation. Variables read by a *checked*
invariant are retained, even if the read is only a type annotation, because TLC
evaluates invariants on generated states and does not expand view-merged states.

Temporal properties are treated separately: `[]P` and `[A]_v` are safety and do
not block a reduction, while fairness or `<>` / `~>` produce a liveness warning
and, by default, no `SYMMETRY` is emitted.

---

## Results

Every number in the report is produced by a script from `results/raw/**`:

| Artefact | What it shows |
|---|---|
| `analysis/output/tables/rq1_reduction.md` | state/time reduction per model |
| `analysis/output/tables/rq2_violation_preservation.md` | injected bugs re-detected under each reduction |
| `analysis/output/tables/rq3_soundness.md` | candidates proposed / accepted / rejected, with reasons |
| `analysis/output/tables/rq4_ablation.md` | symmetry vs. view vs. both |
| `analysis/output/tables/ground_truth.md` | tool verdicts vs. authored ground truth |
| `analysis/output/numbers.json` | every headline number used by the report |
| `docs/report_fa.md` | the Persian technical report (generated) |

Narrative summary, limitations and threats to validity: [`docs/report_fa.md`](docs/report_fa.md)
(Persian) and [`docs/soundness_report_fa.md`](docs/soundness_report_fa.md).

---

## Repository layout

```
src/symview/            the tool
  lex.py  parse_tla.py  parse_cfg.py   TLA+ and .cfg front end
  operators.py         operator table generated from SANY's own table
  context.py           module resolution + TLC constant probe
  values.py            concrete values, permutation invariance
  analysis/            program.py, equivariance.py, symmetry.py, history.py
  codegen.py  pipeline.py  tlc.py  mutate.py  cli.py
benchmarks/
  public/              pinned public specifications (MIT, provenance hashed)
  lab/                 hand-written models with authored ground truth
  support/             TLAPS stub + community modules (documented)
  fetch_public_specs.py
config/                corpus.yaml (pre-registration), subset.yaml, experiment.yaml
experiments/           parser robustness, subset selection, study, survey
results/raw/           every run, timeout and crash, as JSON + logs
analysis/              make_tables.py, make_figures.py, make_report.py, notebook
docs/                  Persian report, soundness report, tool verification, log
tests/                 ground-truth, parser, operator table
tools/                 tla2tools-1.7.1.jar (MIT)
```

---

## Reproducibility

* The corpus is pinned by commit and every file is hashed in
  `benchmarks/PROVENANCE.json`; `python benchmarks/fetch_public_specs.py --verify`
  re-checks it.
* The evaluated subset is frozen **before** any SymView result is inspected, by
  the criterion written in `config/corpus.yaml` and applied by
  `experiments/select_subset.py`. Exclusions are recorded with their reason.
* One budget for every arm: `config/experiment.yaml` (timeout, workers, heap).
* Mutants are generated from a fixed seed and are kept only if the unreduced
  baseline detects them.
* `results/raw/` keeps failures too: a timeout is a result.
* Every table and every number in the report is regenerated by
  `analysis/make_tables.py`; nothing is typed by hand.

Tool versions actually used are recorded in `results/raw/environment.json` and in
[`docs/tools_verification.md`](docs/tools_verification.md).

---

## Known limitations

* Unclassified operators (custom community modules) produce an `unknown` verdict
  and therefore no reduction.
* Parameterised `INSTANCE` is resolved for names, not flattened semantically.
* Liveness plus symmetry is refused by default (see the soundness report for the
  reasoning and for the evidence that this is a real pitfall).
* The taint analysis is an over-approximation: it may reject a sound symmetry,
  never accept an unsound one.

---

## Licence and attribution

SymView is MIT licensed (see `LICENSE`). It redistributes `tla2tools.jar` and
specifications from `tlaplus/Examples` (both MIT); see `NOTICE` and
`benchmarks/PROVENANCE.json`. The proof-only `TLAPS.tla` stub is documented in
`benchmarks/support/README.md`.
