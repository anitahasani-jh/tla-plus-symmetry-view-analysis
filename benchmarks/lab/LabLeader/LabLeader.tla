---------------------------- MODULE LabLeader -----------------------------
\* Lab model 3 -- a symmetric-looking protocol whose configuration singles out
\* one element of Proc.
\*
\* Structurally this is LabLock, but there is an extra CONSTANT Leader and the
\* .cfg assigns Leader = p1, i.e. one member of the "symmetric" set Proc is
\* distinguished.  The protocol uses it: a waiting process may be granted the
\* lock only if it is the leader or the leader is not waiting (leader
\* priority).  A permutation of Proc that moves Leader to another process is
\* therefore NOT a symmetry of the specification, and the ground truth is that
\* a symmetry candidate over Proc must be REJECTED (verdict: unsound).
\*
\* The model itself is clean: all invariants hold and no deadlock is reachable.
EXTENDS TLC

CONSTANTS Proc, None, Leader

ASSUME NoneAssume == None \notin Proc
ASSUME LeaderAssume == Leader \in Proc

VARIABLES owner, pending

vars == <<owner, pending>>

TypeOK ==
    /\ owner \in Proc \cup {None}
    /\ pending \subseteq Proc

Init ==
    /\ owner = None
    /\ pending = {}

Request(p) ==
    /\ p \notin pending
    /\ owner # p
    /\ pending' = pending \cup {p}
    /\ UNCHANGED owner

\* Leader priority: a non-leader may only be served while the leader waits not.
Grant(p) ==
    /\ owner = None
    /\ p \in pending
    /\ (p = Leader \/ Leader \notin pending)
    /\ owner' = p
    /\ pending' = pending \ {p}

Release(p) ==
    /\ owner = p
    /\ owner' = None
    /\ UNCHANGED pending

Next ==
    \E p \in Proc : Request(p) \/ Grant(p) \/ Release(p)

Spec ==
    Init /\ [][Next]_vars

\* --- invariants ----------------------------------------------------------

Holders == {p \in Proc : owner = p}

MutualExclusion == \A p, q \in Holders : p = q

NoPendingOwner == ~\E p \in Proc : (p \in pending) /\ (owner = p)

=============================================================================
