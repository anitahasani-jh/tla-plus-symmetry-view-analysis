---------------------------- MODULE LabOrdered ----------------------------
\* Lab model 4 -- a token ring over ORDERED process identifiers.
\*
\* Here the "processes" are the integers 1..N, not uninterpreted model values:
\* the ring successor is computed with integer arithmetic, `(p % N) + 1`, the
\* running sum `msg` is computed with `+` and `%` on the identifier of the
\* process that takes its turn, and the invariant DoneIsPrefix compares
\* identifiers with `<`.  The configuration therefore contains no set of model
\* values at all, and no permutation of an identifier set is a symmetry of the
\* specification.  The ground truth for the symmetry analysis is verdict: none
\* (there is no candidate to propose, and any candidate over 1..N would have to
\* be rejected because process identity is used with order comparison and
\* arithmetic).
EXTENDS Integers

CONSTANT N

ASSUME NAssume == N \in Nat /\ N > 0

VARIABLES turn, done, msg

vars == <<turn, done, msg>>

TypeOK ==
    /\ turn \in 1..N
    /\ done \subseteq 1..N
    /\ msg \in 0..(N - 1)

Init ==
    /\ turn = 1
    /\ done = {}
    /\ msg = 0

\* The process that holds the token takes its turn and adds its identifier to
\* the running sum, modulo N.
Take(p) ==
    /\ turn = p
    /\ p \notin done
    /\ done' = done \cup {p}
    /\ msg' = (msg + p) % N
    /\ UNCHANGED turn

\* The process that holds the token passes it to its ring successor.  The
\* successor is computed with arithmetic on the identifier, which is what makes
\* the identifiers ordered rather than symmetric.
Pass(p) ==
    /\ turn = p
    /\ p \in done
    /\ turn' = (p % N) + 1
    /\ UNCHANGED <<done, msg>>

Next ==
    \E p \in 1..N : Take(p) \/ Pass(p)

Spec ==
    Init /\ [][Next]_vars

\* --- invariants ----------------------------------------------------------

TokenInRange == turn \in 1..N

MsgInRange == msg \in 0..(N - 1)

\* Turns are taken in increasing identifier order, so `done` is always a prefix
\* of 1..N.  This is a genuine property of the ring order and is falsified by
\* any non-trivial permutation of the identifiers.
DoneIsPrefix ==
    \A p \in done : \A q \in 1..N : (q < p) => (q \in done)

\* Once every process has taken its turn, the running sum equals 1+2+...+N
\* modulo N.  It is stated with an explicit sum over the ordered identifiers.
SumOnFullRing ==
    (done = 1..N) => (msg = ((N * (N + 1)) \div 2) % N)

=============================================================================
