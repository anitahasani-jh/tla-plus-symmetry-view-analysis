# Support modules

TLC resolves `EXTENDS`/`INSTANCE` modules from the directory of the root module
first, so anything a public specification needs and TLC does not ship has to be
available next to it. The experiment runner copies this directory into every run
directory, and the corpus itself is never modified.

## `TLAPS.tla` and `FiniteSetTheorems.tla` — proof-only stubs

Many public specifications contain a TLAPS proof and therefore `EXTENDS TLAPS`.
TLAPS is distributed with the proof system, not with TLC. TLC parses proof steps
but never evaluates them, so the only thing that blocks model checking is SANY's
name resolution.

* `TLAPS.tla` is the upstream file from
  `tlaplus/tlaplus/tlatools/org.lamport.tlatools/test-model/VoteProof/TLAPS.tla`
  (MIT), vendored unmodified.
* `FiniteSetTheorems.tla` is **authored by this project**. It defines exactly the
  names the corpus references from `BY ...` proof steps — `FS_EmptySet`,
  `FS_Singleton` and `ExpandENABLED` — each as `TRUE`. The list was derived
  mechanically: run TLC, collect `Unknown operator: ...`, add the name, repeat.
  Every use in the corpus is inside a proof step (`grep -n "FS_EmptySet"`), and
  TLC ignores proof steps, so these definitions cannot change a model check.

If a specification needs an operator that is genuinely *evaluated* (not only
cited in a proof), the stub is not enough and the model is excluded by the
probe with the recorded reason.

## `community/` — community modules

`community/*.tla` are extracted unmodified from the official
`CommunityModules.jar` shipped at the pinned `tlaplus/tlaplus` commit (MIT).
They are provided as plain `.tla` files on purpose:

> `tla2tools-1.7.1.jar` declares `Class-Path: CommunityModules.jar` in its
> manifest, and the JVM resolves that relative to the jar's own directory. A
> **newer** `CommunityModules.jar` placed next to `tla2tools.jar` makes TLC 2.16
> abort with `NoClassDefFoundError: tlc2/value/impl/KSubsetValue`, because the
> bundled `tlc2/overrides` classes target a newer TLC. The jar is therefore kept
> out of `tools/`, and only the pure TLA+ modules are used.

Consequence: models whose specification calls a community operator that depends
on a Java override (e.g. `Bitwise`, `CSV`, `Json`, `GraphViz`) fail the probe and
are excluded with the reason recorded in `config/subset.yaml`. On a JDK 17 setup
with `tla2tools-1.8.0` the matching jar can be added to the classpath instead;
`config/tools.yaml` documents the two profiles.
