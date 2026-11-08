--------------------------- MODULE FiniteSetTheorems ---------------------------
(***************************************************************************)
(* Project-authored STUB, not an upstream file.                            *)
(*                                                                         *)
(* Several public specifications EXTENDS proof-only theorem modules that   *)
(* are distributed with TLAPS rather than with TLC.  TLC parses proof      *)
(* steps but never evaluates them, so the only thing that blocks model     *)
(* checking is SANY's name resolution.  This stub declares exactly the     *)
(* names the benchmark corpus references in `BY ...` proof steps, each     *)
(* defined as TRUE.  See benchmarks/support/README.md for the derivation   *)
(* and for the evidence that every use is inside a proof.                  *)
(***************************************************************************)
EXTENDS Naturals, Integers, FiniteSets, Sequences, TLC

FS_EmptySet == TRUE

FS_Singleton == TRUE

ExpandENABLED == TRUE

================================================================================
