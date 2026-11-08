# SymView lab benchmarks

Seven small hand-written TLA+ models whose ground truth is known *by
construction*.  They are the reference answers for the soundness measurements
(RQ3): for every model we know whether a SYMMETRY reduction over a set of model
values is sound, which variables are genuine history variables that a VIEW may
drop, and whether a liveness property is being checked.

Machine-readable version: [`ground_truth.yaml`](ground_truth.yaml).

Every model was validated with TLC2 Version 2.16 (`tools/tla2tools-1.7.1.jar`),
Java 8, `-workers 2`, three processes (`Proc = {p1,p2,p3}`) or `N = 3`.  All ten
configurations report

```
Model checking completed. No error has been found.
```

## Measured state counts

`distinct` is TLC's `N distinct states found`; `generated` is the matching
`N states generated` figure.  "Reduced" is the run with the tool-generated
wrapper module (`<Model>Symm.tla`) plus `<Model>_symm.cfg`.

| model        | unreduced generated / distinct | reduced generated / distinct | reduction used      |
|--------------|-------------------------------|------------------------------|---------------------|
| `LabLock`    | 49 / **20**                   | 19 / **7**                   | `SYMMETRY`          |
| `LabLog`     | 694 / **289**                 | 19 / **7**                   | `SYMMETRY` + `VIEW` |
| `LabLeader`  | 45 / **20**                   | –                            | none shipped        |
| `LabOrdered` | 9 / **8**                     | –                            | none shipped        |
| `LabChoose`  | 44 / **20**                   | –                            | none shipped        |
| `LabLive`    | 100 / **54**                  | 31 / **16**                  | `SYMMETRY`          |
| `LabAuxRead` | 149 / **54**                  | –                            | none shipped        |

`LabLog` is the interesting pair: dropping the append-only variable `log`
collapses 289 distinct states to the same 7 that `LabLock` has, i.e. the view
removes exactly the state blow-up that the history variable causes.  Measured
separately (throwaway configs, not part of the benchmark): `VIEW` alone on
`LabLog` gives 49 generated / 20 distinct — identical to unreduced `LabLock`,
which is what "the log is irrelevant to the protocol" means — and symmetry alone
takes those 20 down to 7.

For `LabLive` the numbers are the states of the behaviour graph; TLC checked
4 branches of temporal properties in both runs (216 total distinct states
unreduced, 64 reduced).

## How to re-run

TLC writes a `states/` directory next to the spec, so **never run it inside
`benchmarks/`** — copy the model to a scratch directory first.

```bash
# from the project root
JAR="$(pwd)/tools/tla2tools-1.7.1.jar"
SCRATCH=/tmp/symview-lab
mkdir -p "$SCRATCH"

for m in LabLock LabLog LabLeader LabOrdered LabChoose LabLive LabAuxRead; do
  rm -rf "$SCRATCH/$m" && cp -r "benchmarks/lab/$m" "$SCRATCH/$m"
  ( cd "$SCRATCH/$m" \
    && java -cp "$JAR" tlc2.TLC -workers 2 -config "$m.cfg" "$m.tla" )
done

# reduced runs (models 1, 2 and 6)
for m in LabLock LabLog LabLive; do
  ( cd "$SCRATCH/$m" \
    && java -cp "$JAR" tlc2.TLC -workers 2 -config "${m}_symm.cfg" "${m}Symm.tla" )
done
```

The literal command used for each model (Windows / Git Bash, run from inside a
scratch copy of the model directory):

| model | unreduced | reduced |
|-------|-----------|---------|
| `LabLock`    | `java -cp "C:/Users/emiroow/Documents/Qoder/2026-11-05/7a734d68/symview/tools/tla2tools-1.7.1.jar" tlc2.TLC -workers 2 -config LabLock.cfg LabLock.tla`       | `... -config LabLock_symm.cfg LabLockSymm.tla` |
| `LabLog`     | `java -cp "…/tools/tla2tools-1.7.1.jar" tlc2.TLC -workers 2 -config LabLog.cfg LabLog.tla`       | `... -config LabLog_symm.cfg LabLogSymm.tla` |
| `LabLeader`  | `java -cp "…/tools/tla2tools-1.7.1.jar" tlc2.TLC -workers 2 -config LabLeader.cfg LabLeader.tla` | – |
| `LabOrdered` | `java -cp "…/tools/tla2tools-1.7.1.jar" tlc2.TLC -workers 2 -config LabOrdered.cfg LabOrdered.tla` | – |
| `LabChoose`  | `java -cp "…/tools/tla2tools-1.7.1.jar" tlc2.TLC -workers 2 -config LabChoose.cfg LabChoose.tla` | – |
| `LabLive`    | `java -cp "…/tools/tla2tools-1.7.1.jar" tlc2.TLC -workers 2 -config LabLive.cfg LabLive.tla`     | `... -config LabLive_symm.cfg LabLiveSymm.tla` |
| `LabAuxRead` | `java -cp "…/tools/tla2tools-1.7.1.jar" tlc2.TLC -workers 2 -config LabAuxRead.cfg LabAuxRead.tla` | – |

## The models

### 1. `LabLock` — symmetry is sound, no history variables

Three symmetric processes compete for one lock (`owner`, `pending`) with
`Request` / `Grant` / `Release`.  Every occurrence of `Proc` is a symmetric use
(bounded quantification, set membership, set union/difference), and there is no
auxiliary variable at all.

*Exercises:* the positive case of the symmetry analysis (`candidate: Proc`,
`verdict: sound`) and the empty-answer case of the view analysis
(`expected_history: []`).  Invariants: `TypeOK`, `MutualExclusion`,
`NoPendingOwner`.

### 2. `LabLog` — symmetry is sound, `log` is a history variable

Byte-for-byte the protocol of `LabLock`, except that every action also appends
`<<p, kind>>` to `log`.  `log` is read only inside its own primed assignment; no
guard, no other assignment and no invariant (other than `TypeOK`) mentions it.

*Exercises:* the view analysis must propose `expected_history: [log]`, and the
combined `SYMMETRY` + `VIEW` reduction must be accepted.  Note that TLC still
evaluates invariants on the full state, so `TypeOK`'s `log \in Seq(LogEntry)`
conjunct keeps working in the reduced run.

`log` is truncated to its last `LogBound = 3` entries by `TruncLog`.  Without
that bound the log would grow forever and the state space would be infinite.
The bound is a *total* `IF` inside `log`'s own assignment, so it never affects
the enabledness of an action nor the value of any other variable.

### 3. `LabLeader` — symmetry must be rejected (distinguished element)

`LabLock` plus `CONSTANT Leader` with `Leader = p1` in the `.cfg`; `Grant`
implements leader priority (`p = Leader \/ Leader \notin pending`).  The
specification mentions a *fixed* member of `Proc`, so a permutation that moves
`Leader` is not a symmetry.

*Exercises:* the negative case driven by the configuration file — the tool may
propose `Proc`, but must answer `verdict: unsound`.  The model itself checks
clean, so a false "sound" answer is not masked by an error.

### 4. `LabOrdered` — no symmetry candidate at all

A token ring whose processes are the *integers* `1..N`: the successor is
`(p % N) + 1`, the running sum is `(msg + p) % N`, and `DoneIsPrefix` compares
identifiers with `<`.  There is no set of model values in the configuration
(only `N = 3`), so there is nothing to permute.

*Exercises:* the `verdict: none` / `candidate: null` answer, and the detection
of order comparison and arithmetic on process identity as a symmetry breaker.

### 5. `LabChoose` — symmetry must be rejected (non-equivariant choice)

`LabLock` in which the beneficiary of the grant is picked with
`LET c == CHOOSE q \in Proc : q \in pending IN …`.  Nothing in the configuration
distinguishes a process, so a purely configuration-driven analysis would call
this symmetric; the `CHOOSE` over the symmetric set breaks permutation
equivariance.

*Exercises:* the negative case that can only be found by reading the
next-state relation — `verdict: unsound` with
`reason: choose-over-symmetric-set`.

### 6. `LabLive` — symmetric, but a liveness property is checked

Three symmetric processes each request the lock once, hold it and retire
(`done`).  `Spec == Init /\ [][Next]_vars /\ WF_vars(Next)` and the `.cfg` uses
the `PROPERTY` keyword for

* `Termination == <>(done = Proc)`
* `OwnerLeadsToFinish == \A p \in Proc : (owner = p) ~> (p \in done)`

Both hold; TLC verifies them with the shipped configuration.  Because every
process asks at most once, `WF_vars(Next)` is strong enough to imply
`Termination` (requests cannot postpone `Finish` forever).  The state
`done = Proc` is the intended terminal state and has no enabled action, so both
configurations set `CHECK_DEADLOCK FALSE`.

*Exercises:* `expected_liveness_warning: true` — the tool must warn that a
temporal property (and a fairness assumption inside `Spec`) is being checked
before it proposes a symmetry reduction, even though the reduction is sound here.

### 7. `LabAuxRead` — a variable that looks like a log but is read

`LabLock` plus `seen`, the set of processes that have been observed in the
current round.  `seen` is written by `Request` and reset by `Recycle`, so a
"written-every-step, never-read-by-an-assignment" heuristic would flag it as a
history variable.  It is read by the guard of `Request`
(`\E q \in Proc : q \notin seen`), by the guard of `Recycle` (`seen = Proc`) and
by the invariants `PendingSeen` and `OwnerSeen`.

*Exercises:* the false-positive case of the view analysis —
`expected_history: []`.  Symmetry over `Proc` is nevertheless sound here; this
was sanity-checked with a throwaway wrapper (`Permutations(Proc)`,
50 generated / 16 distinct, no error) which is deliberately *not* part of the
benchmark, because models 3, 4, 5 and 7 ship a plain configuration only.

## Files

```
benchmarks/lab/
├── ground_truth.yaml          # machine-readable reference answers
├── README.md
├── LabLock/     LabLock.tla     LabLock.cfg     LabLockSymm.tla     LabLock_symm.cfg
├── LabLog/      LabLog.tla      LabLog.cfg      LabLogSymm.tla      LabLog_symm.cfg
├── LabLeader/   LabLeader.tla   LabLeader.cfg
├── LabOrdered/  LabOrdered.tla  LabOrdered.cfg
├── LabChoose/   LabChoose.tla   LabChoose.cfg
├── LabLive/     LabLive.tla     LabLive.cfg     LabLiveSymm.tla     LabLive_symm.cfg
└── LabAuxRead/  LabAuxRead.tla  LabAuxRead.cfg
```

The `<Model>Symm.tla` wrapper is exactly what the SymView tool generates: it
does `EXTENDS <Model>, TLC` and defines the zero-argument operators
`SymViewPerms == Permutations(Proc)` and `SymViewView == <<retained variables>>`,
which the `.cfg` then references as `SYMMETRY SymViewPerms` /
`VIEW SymViewView`.  The reduced runs therefore double as integration tests.

## Environment notes

* `SYMMETRY <op>` requires a *set of permutations*: `SYMMETRY Proc` (a bare set
  of model values) fails in TLC 2.16 with
  `The symmetry function Proc must specify a set of permutations.`  All
  configurations here use `Permutations(Proc)`.
* `VIEW <op>` requires a zero-argument operator whose value is a tuple of
  variables, e.g. `SymViewView == <<owner, pending>>`.
* The manifest of `tla2tools-1.7.1.jar` contains `Class-Path:
  CommunityModules.jar`, so any `CommunityModules.jar` sitting next to it is
  loaded automatically.  The modern CommunityModules build registers Java
  overrides for `Cardinality`, `SUBSET` and `Permutations` that are compiled
  against a newer TLC, which makes those operators die with
  `java.lang.NoClassDefFoundError: tlc2/value/impl/KSubsetValue` under TLC 2.16.
  In this checkout that jar lives in `tools/community-disabled/`, which is what
  makes the reduced runs work; if it is ever moved back next to
  `tla2tools-1.7.1.jar`, the `_symm.cfg` runs will fail for that reason and not
  because of the models.  The models additionally avoid `SUBSET` and
  `Cardinality` (e.g. `MutualExclusion == \A p, q \in Holders : p = q`), so the
  plain configurations keep working in either case.
* Only standard modules are used: `TLC`, `Sequences`, `Naturals`, `Integers`.
  No TLAPS, no community module.
