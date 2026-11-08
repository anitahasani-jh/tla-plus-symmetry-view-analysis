# Experiment log

Lab-notebook record for SymView, 2026-11-05/06.  Times are local; each entry
keeps the observation, the action and the lesson.  Numbers here were produced by
the commands shown, not typed from memory; the raw JSON is under `results/raw/`.

## 2026-11-05

### 16:40 -- Corpus fetch
Ran `python benchmarks/fetch_public_specs.py`: 563 files downloaded, 0 failures
(562 from `tlaplus/Examples` at `ca168055339d5cbcee95b7eefcb97c1ee59f9914`,
plus `ongardie/raft.tla` at `6ecbdbcf1bcd`).  Every file is hashed in
`benchmarks/PROVENANCE.json`.
Learned: pinning the commit and hashing the bytes is what makes "we evaluated
the public models" checkable; a branch name would not.

### 18:05 -- Parser bug 1: function application was missing
On real specs, `f[x]` was not parsed as an application; the `[` fell into the
bracket classifier and produced `unknown` nodes (coverage stayed high, meaning
the token was swallowed without semantics).  Added a postfix `apply` node with
argument parsing after any expression and re-ran over the corpus.
Learned: token coverage alone does not prove understanding; a node can cover
tokens and still have the wrong shape, so the lab tests must check verdicts.

### 19:20 -- Parser bug 2: `[x \in S |-> e]` read as a record
`[x \in S |-> e]` was classified as a record because the classifier returned on
the first `|->` before noticing the binder.  Fixed `classify_bracket` to track
`seen_binder` (`\in` / `\subseteq` at depth 1) and return `funcc`; records
(`[a |-> b]`), record sets (`[f : S]`), function sets and EXCEPT brackets are now
distinguished separately.
Learned: in TLA+ the same bracket token means four different things; the
disambiguator is the binder, not the arrow.

### 20:10 -- Parser bug 3: `Inv!2` bang paths
Proof-carrying specs use `Inv!2` to name a proof step.  The lexer produced `!`
but the expression parser had no postfix rule, so the rest of the line became a
fallback.  Added a `bang` node with a name/number target; unresolved targets are
still reported as `bang-target` (7 in the current corpus).
Learned: a tool that claims to parse proof-carrying modules must at least scan
proof terms without losing the enclosing definition.

### 21:00 -- Parser bug 4: over-eager unit-start lookahead
`at_unit_start` treated any `NAME/OP/PUNCT ... ==` as the start of a new unit,
so an expression inside a definition could be cut in half and the remainder
re-parsed as a definition.  Restricted the heuristic to reliable unit starts
(`reliable_only`, depth-aware `at_def_start`) and kept the aggressive form only
where a new unit is actually expected.
Learned: the remaining 7,293 `unexpected-unit-start` fallbacks are proof and
structured text (mostly `BPConProof.tla`), not the models we reduce; measure the
residue instead of claiming a perfect parser.

## 2026-11-06

### 09:30 -- The dataclass `__eq__` bug
Every permutation-invariance test failed: `{a1, a2}` compared unequal to
`{a2, a1}`.  The value classes were plain frozen dataclasses, so the generated
`__eq__` compared the `items` tuple positionally.  Fixed by `@dataclass(...,
eq=False)` on every `Val` subclass and routing equality/hashing through
`Val.key()` (sets compare as sets, sequences as sequences).
Learned: for semantic values, equality must be defined by meaning, not by the
Python field order; this one bug made the tool reject every symmetric model.

### 10:15 -- The `Class-Path` trap
TLC 2.16 died with `NoClassDefFoundError: tlc2/value/impl/KSubsetValue` only
when a CommunityModules.jar was present.  The jar manifest contains
`Class-Path: CommunityModules.jar`, and the JVM resolves that relative to the
directory of `tla2tools-1.7.1.jar`.  Moved the community jar to
`tools/community-disabled/`, keep `tools/` with exactly one jar, and made
`setup.sh` refuse to continue if `tools/CommunityModules.jar` exists.
Learned: a jar is not self-contained when its manifest names a sibling; the
directory layout is part of the toolchain.

### 10:45 -- CommunityModules incompatibility
The modern community build registers Java overrides for `Cardinality`, `SUBSET`
and `Permutations` compiled against a newer TLC; TLC 2.16 cannot load them even
though the `.tla` sources are compatible.  Extracted the 34 plain `.tla` modules
into `benchmarks/support/community/` and left the jar disabled.
Learned: matching the `.tla` API is not enough; Java overrides bind the
community jar to one TLC version, so version the jar and the checker together.

### 11:30 -- Proof-only theorem modules
Several public specs `EXTENDS` modules such as `TLAPS` and
`FiniteSetTheorems` that ship with TLAPS, not TLC.  TLC parses proof steps but
never evaluates them, so the only blocker is SANY name resolution.  Vendored
`TLAPS.tla` unmodified from the TLA+ tools repository (MIT) and authored
`FiniteSetTheorems.tla`, which declares the three referenced names as `TRUE`.
Learned: a proof-only stub is safe only if it contains no model-checking
definition and every use is inside a proof; document that boundary explicitly.

### 12:10 -- TLC as a constant evaluator
Instead of guessing constant values from the `.cfg`, SymView appends one
module-level `ASSUME` per constant that calls `PrintT(<<marker, name, value>>)`,
runs TLC, and terminates as soon as the markers appear.  TLC evaluates module
`ASSUME`s after "Starting..." and before computing initial states, so the probe
returns exact values in about 1 s even for models too large to check.
Learned: the model checker's own evaluator is the most trustworthy parser of
constant expressions; a static evaluator would have to re-implement TLA+.

### 12:35 -- Reference measurement: TCommit
`python -m symview report --spec-dir benchmarks/public/transaction_commit
--module TCommit --config TCommit.cfg --arms direct plain symmetry`
gave: direct 94 generated / 34 distinct (1.46 s), plain 94 / 34 (1.44 s),
symmetry 37 / 13 (1.30 s), all verdict `ok`; the proposal was
`SYMMETRY RM = {r1, r2, r3}` (group order 6) and no view.  This is the smoke
benchmark used in setup and documentation.
Learned: the wrapper is transparent (direct = plain), and symmetry cuts distinct
states from 34 to 13 (61.8%) on the smallest honest transaction-commit model.

### 13:20 -- Ground truth and parser robustness
`python tests/test_lab_ground_truth.py` reports 8/8 PASS over the eight lab
models; `python experiments/parser_robustness.py` reports 346 `.tla` files, 0
crashes, 100% token coverage and 271 files with no fallback node.
Learned: soundness needs negative cases (LabLeader's distinguished element,
LabChoose's `CHOOSE`, LabOrdered's ordered identifiers), not just examples where
the reduction fires; coverage is necessary but not sufficient evidence.
