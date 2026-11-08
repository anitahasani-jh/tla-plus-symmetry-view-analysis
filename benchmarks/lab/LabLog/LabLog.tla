----------------------------- MODULE LabLog -------------------------------
\* Lab model 2 -- LabLock plus a pure history variable.
\*
\* The protocol is byte-for-byte the one of LabLock, except that every action
\* also appends an entry to `log`.  The variable `log`
\*   o is only ever written by its own primed assignment,
\*   o is never read by a guard (no action's enabling condition mentions it),
\*   o is never read by another variable's assignment,
\*   o is never read by an invariant other than TypeOK.
\* Hence the ground truth for the view analysis is [log]: `log` may be dropped.
\*
\* `log` is truncated to its last LogBound entries.  Without that bound the log
\* would grow forever and the state space would be infinite.  The bound is a
\* total IF inside log's own assignment, so it never influences the enabledness
\* of an action nor any other variable.
EXTENDS TLC, Sequences, Naturals

CONSTANTS Proc, None

ASSUME NoneAssume == None \notin Proc

VARIABLES owner, pending, log

vars == <<owner, pending, log>>

\* The alphabet of the log and the number of entries that are retained.
LogKind == {"request", "grant", "release"}

LogEntry == Proc \times LogKind

LogBound == 3

TruncLog(s) ==
    IF Len(s) > LogBound
        THEN SubSeq(s, Len(s) - LogBound + 1, Len(s))
        ELSE s

TypeOK ==
    /\ owner \in Proc \cup {None}
    /\ pending \subseteq Proc
    /\ log \in Seq(LogEntry)

Init ==
    /\ owner = None
    /\ pending = {}
    /\ log = << >>

Request(p) ==
    /\ p \notin pending
    /\ owner # p
    /\ pending' = pending \cup {p}
    /\ log' = TruncLog(Append(log, <<p, "request">>))
    /\ UNCHANGED owner

Grant(p) ==
    /\ owner = None
    /\ p \in pending
    /\ owner' = p
    /\ pending' = pending \ {p}
    /\ log' = TruncLog(Append(log, <<p, "grant">>))

Release(p) ==
    /\ owner = p
    /\ owner' = None
    /\ log' = TruncLog(Append(log, <<p, "release">>))
    /\ UNCHANGED pending

Next ==
    \E p \in Proc : Request(p) \/ Grant(p) \/ Release(p)

Spec ==
    Init /\ [][Next]_vars

\* --- invariants ----------------------------------------------------------
\* None of them mentions `log` (except the type invariant), which is what makes
\* `log` droppable from a view.

Holders == {p \in Proc : owner = p}

MutualExclusion == \A p, q \in Holders : p = q

NoPendingOwner == ~\E p \in Proc : (p \in pending) /\ (owner = p)

=============================================================================
