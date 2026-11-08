----------------------------- MODULE LabLive ------------------------------
\* Lab model 6 -- symmetric processes plus a genuine liveness property.
\*
\* Every process eventually asks for the lock, holds it once and retires; `done`
\* is the set of processes that have finished.  The specification contains the
\* fairness assumption WF_vars(Next) and the .cfg checks temporal properties
\* with the PROPERTY keyword:
\*   Termination        == <>(done = Proc)
\*   OwnerLeadsToFinish == \A p \in Proc : (owner = p) ~> (p \in done)
\* Both hold, and TLC verifies them with the shipped configuration.  The state
\* done = Proc is the intended terminal state of the protocol and has no enabled
\* action, so both .cfg files set CHECK_DEADLOCK FALSE.
\*
\* Ground truth: the symmetry reduction over Proc is sound for the safety
\* invariants (all uses of Proc are symmetric), but the tool must WARN that a
\* temporal/liveness property is being checked, because symmetry reduction
\* interacts with fairness and with liveness proof obligations.
EXTENDS TLC

CONSTANTS Proc, None

ASSUME NoneAssume == None \notin Proc

VARIABLES owner, pending, done

vars == <<owner, pending, done>>

TypeOK ==
    /\ owner \in Proc \cup {None}
    /\ pending \subseteq Proc
    /\ done \subseteq Proc

Init ==
    /\ owner = None
    /\ pending = {}
    /\ done = {}

\* p asks for the lock.  A process asks at most once: after it has finished it
\* retires for good.  (This restriction is what makes WF_vars(Next) strong
\* enough to imply Termination.)
Request(p) ==
    /\ p \notin done
    /\ p \notin pending
    /\ owner # p
    /\ pending' = pending \cup {p}
    /\ UNCHANGED <<owner, done>>

\* The lock is handed to a waiting process.
Grant(p) ==
    /\ owner = None
    /\ p \in pending
    /\ owner' = p
    /\ pending' = pending \ {p}
    /\ UNCHANGED done

\* p leaves the critical section for good.
Finish(p) ==
    /\ owner = p
    /\ owner' = None
    /\ done' = done \cup {p}
    /\ UNCHANGED pending

Next ==
    \E p \in Proc : Request(p) \/ Grant(p) \/ Finish(p)

Spec ==
    Init /\ [][Next]_vars /\ WF_vars(Next)

\* --- safety invariants ---------------------------------------------------

Holders == {p \in Proc : owner = p}

MutualExclusion == \A p, q \in Holders : p = q

NoPendingOwner == ~\E p \in Proc : (p \in pending) /\ (owner = p)

\* --- temporal properties -------------------------------------------------

\* Everybody eventually finishes.
Termination == <>(done = Proc)

\* Whoever owns the lock eventually finishes with it.
OwnerLeadsToFinish == \A p \in Proc : (owner = p) ~> (p \in done)

=============================================================================
