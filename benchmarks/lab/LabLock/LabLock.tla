----------------------------- MODULE LabLock ------------------------------
\* Lab model 1 -- the minimal symmetric mutual-exclusion kernel.
\*
\* N symmetric processes (the model values of CONSTANT Proc) compete for a
\* single lock held by `owner` (a process, or the distinguished value None).
\* `pending` is the set of processes that have asked for the lock and are
\* waiting for it.  The module contains NO history/auxiliary variables, so the
\* ground truth for the view analysis is the empty set, and every use of Proc
\* is symmetric, so the ground truth for the symmetry analysis is "sound".
EXTENDS TLC

CONSTANTS Proc, None

ASSUME NoneAssume == None \notin Proc

VARIABLES owner, pending

vars == <<owner, pending>>

TypeOK ==
    /\ owner \in Proc \cup {None}
    /\ pending \subseteq Proc

Init ==
    /\ owner = None
    /\ pending = {}

\* p asks for the lock.
Request(p) ==
    /\ p \notin pending
    /\ owner # p
    /\ pending' = pending \cup {p}
    /\ UNCHANGED owner

\* The lock is handed to a waiting process.
Grant(p) ==
    /\ owner = None
    /\ p \in pending
    /\ owner' = p
    /\ pending' = pending \ {p}

\* p gives the lock back.
Release(p) ==
    /\ owner = p
    /\ owner' = None
    /\ UNCHANGED pending

Next ==
    \E p \in Proc : Request(p) \/ Grant(p) \/ Release(p)

Spec ==
    Init /\ [][Next]_vars

\* --- invariants ----------------------------------------------------------

\* The processes that currently hold the lock.
Holders == {p \in Proc : owner = p}

\* At most one process owns the lock.
MutualExclusion == \A p, q \in Holders : p = q

\* Nobody can own the lock and wait for it at the same time.
NoPendingOwner == ~\E p \in Proc : (p \in pending) /\ (owner = p)

=============================================================================
