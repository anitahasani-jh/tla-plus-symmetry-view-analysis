# Tools and baselines: verification record

Project: SymView -- static symmetry and view suggestions for TLC.
Record date: 2026-11-06.  Author: the SymView authors.

This document is the pre-implementation tool check required by the course
guide.  It records **what was actually executed or downloaded**, what was only
read, and how each item is used in the study.  The table below was opened before
implementation and updated with the status observed on 2026-11-06; section 4
marks explicitly which claims are backed by execution.  It deliberately separates
the one model checker that produced numbers (TLC) from the optional symbolic
baseline that was **not** executed (Apalache) and from the literature that
supplies the definitions (symmetry, views, history variables).

Availability was checked from this machine with

```sh
curl -sSI -L -o /dev/null -w '%{http_code}\n' <URL>
```

(HEAD, redirects followed).  For one asset that rejects HEAD the status of the
equivalent GET is given explicitly.  Publisher sites (ACM, Springer, HAL) front
their pages with bot protection; a 403/303 there means "automated request
blocked or redirected", not "resource does not exist".  The statuses below are
the ones observed during this check and are reported verbatim.  Check IDs A1-A22
are used in the main table.

**Decision.**  Proceed with TLC 2.16 as the only executed checker.  Apalache is
out of scope for execution and is reported as not run; the symmetry and
auxiliary-variable literature supplies definitions, not measurements.

## 1. Tools and baselines

| Ref | Tool / baseline | Paper or reference | Repository / artifact | Pinned version used here | Licence | Verified availability | Role in this study |
|---|---|---|---|---|---|---|---|
| R1 | TLC (tla2tools.jar) | Y. Yu, P. Manolios, L. Lamport, "Model Checking TLA+ Specifications", CHARME 1999. DOI 10.1007/3-540-48153-2_6 (page range: verify) | https://github.com/tlaplus/tlaplus; release v1.7.1 | `tla2tools-1.7.1.jar`, TLC2 Version 2.16 of 31 December 2020, SHA-256 `d532ba31aafe17afba1130f92410d9257454ff7393d1eb2fe032f0c07f352da5` | MIT | A1 200 (paper PDF), A2 200 (Springer), A3 200 (repo), A4 200 (release), A5 HEAD 302 / GET 200 (jar asset) | The only model checker executed: unreduced control, wrapper control, SYMMETRY, VIEW, both, and mutant replay. Every state count and time in the report comes from this jar. |
| R2 | TLA+ language reference / "Specifying Systems" | L. Lamport, *Specifying Systems: The TLA+ Language and Tools for Hardware and Software Engineers*, Addison-Wesley, 2002. TLC tools manual for SYMMETRY/VIEW | https://lamport.azurewebsites.net/tla/book.html; TLC manual https://lamport.azurewebsites.net/tla/current-tools.pdf | Book PDF edition dated 2008-02-08 (`book-02-08-08.pdf`); TLC manual as retrieved 2026-11-06 | Book: Addison-Wesley copyright, free PDF, **not redistributed**. Manual: TLA+ project documentation (MIT repository) | A6 200 (book page), A7 200 (book PDF), A8 200 (TLC tools manual) | Defines the language fragment the parser must understand and the exact meaning of `SYMMETRY` (a set of permutations) and `VIEW` (a zero-argument operator) that the code generator must emit. |
| R3 | Apalache (optional symbolic baseline) | I. Konnov, J. Kukovec, T.-H. Tran, "TLA+ Model Checking Made Symbolic", Proc. ACM Program. Lang. 3(OOPSLA), Article 123, 2019. DOI 10.1145/3360549 | https://apalache-mc.org/; https://github.com/apalache-mc/apalache | **None -- not installed and not executed** | Apache-2.0 | A9 200 (site), A10 200 (repo), A11 403 (ACM DOI; automated access blocked), A12 403 (HAL copy, HEAD) | Reported as the optional symbolic baseline **that was not run**. Reason: it requires JDK 17 and its own distribution (it is not a drop-in TLC replacement), so executing it would add a second, separately configured toolchain and its bounded-checking results would not be comparable to TLC's exhaustive state counts. No Apalache number appears in this project. |
| R4 | Symmetry reduction (theory) | E. A. Emerson, A. P. Sistla, "Symmetry and Model Checking", CAV 1993; journal version in Formal Methods in System Design 9(1-2), 1996. DOI 10.1007/BF00625970; CAV DOI 10.1007/3-540-56922-7_38 | Publisher only (no repository) | 1993 conference paper / 1996 journal version (page ranges: verify) | Publisher copyright; cited, not redistributed | A13 200 (CAV PDF), A14 200 (FMSD article) | Supplies the quotient-state argument: a permutation group acting on the state graph lets symmetric states be identified, but only if the specification and the checked property are equivariant. SymView's acceptance test is a conservative check of that condition. |
| R5 | Permutation-based symmetry | C. N. Ip, D. L. Dill, "Better Verification Through Symmetry", Formal Methods in System Design 9(1-2):41-75, 1996. DOI 10.1007/BF00625968 | Publisher only | 1996 journal version | Publisher copyright; cited, not redistributed | A15 200 | Explains symmetry as a set of permutations and the use of canonical representatives. This is why the generated configuration uses `Permutations(S)` rather than a bare set: TLC 2.16 rejects a bare set with "must specify a set of permutations". |
| R6 | Auxiliary / history variables | S. Owicki, D. Gries, "An Axiomatic Proof Technique for Parallel Programs I", Acta Informatica 6:319-340, 1976. DOI 10.1007/BF00268134 | Publisher only | 1976 | Publisher copyright; cited, not redistributed | A16 200 | Background for the VIEW side: a variable that only records history and is never read by a guard or by another variable's assignment can be removed from the state without changing the observable behaviour, provided no checked property reads it. |
| R7 | TLA+ views and history variables | L. Lamport, *Specifying Systems* (2002), discussion of views/history variables (section number: verify); TLC tools manual, VIEW | https://lamport.azurewebsites.net/tla/book.html; https://lamport.azurewebsites.net/tla/current-tools.pdf | 2008 PDF edition; manual retrieved 2026-11-06 | Book: Addison-Wesley copyright, not redistributed | A6 200, A7 200, A8 200 (same checks as R2) | Fixes the operational definition used by the tool: `VIEW` is a state abstraction evaluated by TLC, and a history variable is auxiliary only if nothing checked observes it. SymView refuses a view when a checked invariant reads the candidate variable. |
| R8 | `tlaplus/Examples` corpus | Not a paper; public specification corpus | https://github.com/tlaplus/Examples/tree/ca168055339d5cbcee95b7eefcb97c1ee59f9914 | Commit `ca168055339d5cbcee95b7eefcb97c1ee59f9914`; 562 fetched files; hashes in `benchmarks/PROVENANCE.json` | MIT; upstream licence kept at `benchmarks/public/_licenses/tlaplus--Examples.md` | A17 200 | The public benchmark pool. Models are selected by the pre-registered P1-P5 criterion in `config/corpus.yaml`; only the frozen subset is evaluated. |
| R9 | Community modules | Not a paper; support library | https://github.com/tlaplus/CommunityModules | Sources extracted from release `202609120237`; 34 `.tla` files under `benchmarks/support/community/` | MIT | A18 200 (repo), A19 200 (LICENSE) | Support modules for corpus specifications that `EXTENDS` a community module. The jar is kept disabled in `tools/community-disabled/`: its Java overrides are compiled against a newer TLC and break TLC 2.16 (see the experiment log). |
| R10 | `TLAPS.tla` proof-only module | Not a paper; proof language support | https://github.com/tlaplus/tlaplus, path `tlatools/org.lamport.tlatools/test-model/VoteProof/TLAPS.tla` | `tlaplus/tlaplus` tag `v1.7.1` (same release as the jar); shipped file is byte-identical (SHA-256 `720a31f61573f1d925f66c75982b3b539b7bd5b25753b7e233cbf48456b4ada7`) | MIT (same as the TLA+ tools repository) | A20 200 (repo), A21 200 (TLAPS.tla at v1.7.1), A22 200 (LICENSE) | Unmodified proof-only module. TLC parses proof steps but never evaluates them, so it lets SANY resolve names mentioned inside proofs without affecting any model-checking result. The one project-authored proof stub is `FiniteSetTheorems.tla` (see `benchmarks/support/README.md`). |

Notes on the table:

* R1 is the only row that produced measurements.  The pinned digest was
  recomputed from the shipped file and from a fresh download of the release
  asset; both are `d532ba31...f352da5`.
* R3 is an **optional baseline that was not executed**.  It is listed so that
  the report can state honestly that a symbolic comparison is out of scope,
  rather than silently omitting it.  No Apalache command, version or result is
  claimed anywhere.
* R8 contains one file that is not MIT: `ongardie/raft.tla`, whose header
  states CC BY 4.0.  It is redistributed unmodified with attribution in
  `NOTICE`; `config/corpus.yaml` currently records that source as MIT and should
  be reconciled.  This does not affect the licence of the `tlaplus/Examples`
  files.
* Page ranges and section numbers that could not be checked against the
  publisher's metadata are marked "verify"; no DOI or page number was invented.

## 2. Availability checks (raw status)

Command: `curl -sSI -L -o /dev/null -w '%{http_code}' <URL>`, run on 2026-11-06.

| ID | URL | Status | Note |
|---|---|---|---|
| A1 | https://lamport.azurewebsites.net/pubs/yuanyu-model-checking.pdf | 200 | TLC paper, author copy |
| A2 | https://link.springer.com/chapter/10.1007/3-540-48153-2_6 | 200 | Publisher chapter (a later retry returned a 303 consent redirect) |
| A3 | https://github.com/tlaplus/tlaplus | 200 | TLA+ tools repository |
| A4 | https://github.com/tlaplus/tlaplus/releases/tag/v1.7.1 | 200 | Release tag |
| A5 | https://github.com/tlaplus/tlaplus/releases/download/v1.7.1/tla2tools.jar | HEAD 302, GET 200 | Redirect to the release asset; the downloaded file has the pinned SHA-256 |
| A6 | https://lamport.azurewebsites.net/tla/book.html | 200 | Specifying Systems page |
| A7 | https://lamport.azurewebsites.net/tla/book-02-08-08.pdf | 200 | Book PDF (2008-02-08 edition) |
| A8 | https://lamport.azurewebsites.net/tla/current-tools.pdf | 200 | TLC tools manual (SYMMETRY/VIEW) |
| A9 | https://apalache-mc.org/ | 200 | Apalache project site |
| A10 | https://github.com/apalache-mc/apalache | 200 | Apalache repository (not installed) |
| A11 | https://dl.acm.org/doi/10.1145/3360549 | 403 | ACM blocks automated requests; DOI/title taken from the publisher record found in the search |
| A12 | https://hal.science/hal-02280888v1/document | 403 | HAL blocks HEAD; not needed for the study |
| A13 | https://link.springer.com/content/pdf/10.1007/3-540-56922-7_38.pdf | 200 | Emerson & Sistla, CAV 1993 |
| A14 | https://link.springer.com/article/10.1007/BF00625970 | 200 | Emerson & Sistla, FMSD 1996 |
| A15 | https://link.springer.com/article/10.1007/BF00625968 | 200 | Ip & Dill, FMSD 1996 |
| A16 | https://link.springer.com/article/10.1007/BF00268134 | 200 | Owicki & Gries, Acta Informatica 1976 |
| A17 | https://github.com/tlaplus/Examples/tree/ca168055339d5cbcee95b7eefcb97c1ee59f9914 | 200 | Pinned corpus commit |
| A18 | https://github.com/tlaplus/CommunityModules | 200 | Community modules repository |
| A19 | https://raw.githubusercontent.com/tlaplus/CommunityModules/master/LICENSE | 200 | MIT licence text |
| A20 | https://github.com/tlaplus/tlaplus | 200 | TLA+ tools repository |
| A21 | https://raw.githubusercontent.com/tlaplus/tlaplus/v1.7.1/tlatools/org.lamport.tlatools/test-model/VoteProof/TLAPS.tla | 200 | Upstream proof-only TLAPS module at tag v1.7.1; byte-identical to the shipped file |
| A22 | https://raw.githubusercontent.com/tlaplus/tlaplus/v1.7.1/LICENSE | 200 | MIT licence text for the TLA+ tools repository at tag v1.7.1 |

Several transient network failures were observed during the checks (GitHub and
HAL connection timeouts, one Springer redirect).  They are not listed as
statuses above; the table records the status of the successful check, and
A11/A12 are genuinely blocked for automated clients.

## 3. Environment actually used

| Item | Observed value |
|---|---|
| Java | `java version "1.8.0_251"` (Oracle), reported by `java -version` |
| TLC | TLC2 Version 2.16 of 31 December 2020, revision from the shipped jar |
| Python | 3.14.6 on the development machine; the Docker image uses Python 3.11 |
| TLC jar manifest | `Class-Path: CommunityModules.jar` (read from `META-INF/MANIFEST.MF`) |
| Experiment budget | `config/experiment.yaml`: 2 workers, 2048 MB heap, 90 s timeout |

TLC needs Java 8 or newer.  The measured runs above used Java 8; JDK 17 is the
runtime in the Docker image (`default-jre-headless` on Debian bookworm) and is
reported as supported, but the numbers in this project were not re-measured on
JDK 17.

## 4. What was verified vs. assumed

### Executed (evidence exists in this repository)

* TLC 2.16, pinned by SHA-256, on the lab models and on the public reference
  model `transaction_commit/TCommit`: direct 94 generated / 34 distinct,
  plain 94 / 34, symmetry 37 / 13, all with verdict `ok`.
* Corpus fetch: 563 files downloaded (562 from `tlaplus/Examples` plus
  `raft.tla`), every file hashed in `benchmarks/PROVENANCE.json`; failures: 0.
* Parser robustness over 346 `.tla` files: 0 parser crashes, 100% token
  coverage, 271 files with no `unknown` fallback node
  (`analysis/output/tables/parser_robustness.md`).
* Ground truth on the 8 hand-written lab models: 8/8 pass
  (`tests/test_lab_ground_truth.py`).
* The TLC-as-constant-evaluator probe (module-level `ASSUME` + `PrintT`,
  terminated after the values are printed) was run on the models above.

### Cited only (not executed, not measured here)

* Apalache (R3): not installed, not run, no results claimed.
* TLC on JDK 17: the Docker image uses it, but this log's measurements are on
  Java 8.
* The symmetry and auxiliary-variable literature (R4-R7): used for definitions
  and soundness conditions; no theorem from those papers is re-proved or
  re-implemented verbatim, and their page ranges were not all checked.
* The `tlaplus/Examples` models outside the frozen subset: fetched and hashed,
  but not model-checked by the study.

### Assumed

* That `benchmarks/public` is the pinned upstream content.  This is supported
  by SHA-256 hashes, not by re-downloading every file at evaluation time.
* That the hand-authored lab ground truth is correct.  It is a reference
  authored with the models, not an independent oracle; the experiment log
  records the reasoning for each verdict.
* That repeated timing runs are comparable only within one machine and one
  budget.  The report uses medians and does not claim cross-machine portability.
* That a 403 from ACM/HAL means automated access was blocked.  The bibliographic
  data for those entries was cross-checked against publisher/search records, and
  uncertain fields are marked "verify".
