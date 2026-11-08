----------------------------- MODULE LabAuxRead ----------------------------
\* Lab model 7 -- a variable that LOOKS like a log but is actually read.
\*
\* `seen` is written by Request (every process that asks is recorded) and reset
\* by Recycle, so a purely syntactic "write-only variable" heuristic would flag
\* it as a history variable.  It is not one:
\*   o the guard of Request reads it (`\E q \in Proc : q \notin seen`),
\*   o the guard of Recycle reads it (`seen = Proc`),
\*   o the invariants PendingSeen and OwnerSeen read it.
\* Dropping `seen` from a view would therefore change the semantics, and the
\* ground truth for the view analysis is the empty set of history variables.
EXTENDS TLC

CONSTANTS Proc, None

ASSUME NoneAssume == None \notin Proc

VARIABLES owner, pending, seen

vars == <<owner, pending, seen>>

TypeOK ==
    /\ owner \in Proc \cup {None}
    /\ pending \subseteq Proc
    /\ seen \subseteq Proc

Init ==
    /\ owner = None
    /\ pending = {}
    /\ seen = {}

\* p asks for the lock; a request is only possible while the current round is
\* still open, i.e. while some process has not been seen yet.  The guard reads
\* `seen`.
Request(p) ==
    /\ \E q \in Proc : q \notin seen
    /\ p \notin pending
    /\ owner # p
    /\ pending' = pending \cup {p}
    /\ seen' = seen \cup {p}
    /\ UNCHANGED owner

Grant(p) ==
    /\ owner = None
    /\ p \in pending
    /\ owner' = p
    /\ pending' = pending \ {p}
    /\ UNCHANGED seen

Release(p) ==
    /\ owner = p
    /\ owner' = None
    /\ UNCHANGED <<pending, seen>>

\* Everybody has been seen and the lock is free: close the round and forget.
\* The guard reads `seen`.
Recycle ==
    /\ seen = Proc
    /\ owner = None
    /\ pending = {}
    /\ seen' = {}
    /\ UNCHANGED <<owner, pending>>

Next ==
    (\E p \in Proc : Request(p) \/ Grant(p) \/ Release(p)) \/ Recycle

Spec ==
    Init /\ [][Next]_vars

\* --- invariants ----------------------------------------------------------

Holders == {p \in Proc : owner = p}

MutualExclusion == \A p, q \in Holders : p = q

\* Both of the following read `seen`, so `seen` cannot be dropped from a view.
PendingSeen == pending \subseteq seen

OwnerSeen == (owner # None) => (owner \in seen)

=============================================================================
