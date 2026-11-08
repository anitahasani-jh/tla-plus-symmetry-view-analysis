# CommunityModules.jar is deliberately NOT shipped here

TLC 2.16 (`tla2tools-1.7.1.jar`) declares `Class-Path: CommunityModules.jar` in
its manifest, and the JVM resolves that path **relative to the jar's directory**.
A newer `CommunityModules.jar` (the 2026 build) placed next to `tla2tools.jar`
makes TLC abort with

```
NoClassDefFoundError: tlc2/value/impl/KSubsetValue
```

because its `tlc2/overrides` classes target a newer TLC.  Reproducing that trap
is not useful, so the jar is not part of this package.

What is shipped instead: the **pure TLA+ modules** extracted from that exact jar
into `benchmarks/support/community/` (34 files), which is all SANY needs to
resolve `EXTENDS`/`INSTANCE` for the corpus.  Models that call a community
operator backed by a Java override (Bitwise, CSV, Json, GraphViz) are excluded by
the feasibility probe and the reason is recorded in `config/subset.yaml`.

To use the jar anyway, install a JDK 17 and `tla2tools-1.8.0`, then put the
matching `CommunityModules.jar` next to *that* jar (see `config/tools.yaml`,
profile `colab-jdk17`).
