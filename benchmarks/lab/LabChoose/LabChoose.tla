---------------------------- MODULE LabChoose -----------------------------
\* Lab model 5 -- a symmetric protocol whose next-state relation is NOT
\* permutation equivariant.
\*
\* The processes are model values of CONSTANT Proc and nothing in the
\* configuration distinguishes one of them, so a symmetry analysis will propose
\* Proc as a candidate.  The proposal is nevertheless UNSOUND: the Grant action
\* picks its beneficiary with a Hilbert choice over the symmetric set,
\*     LET c == CHOOSE q \in Proc : q \in pending IN ...
\* CHOOSE is not required to commute with permutations of Proc, so applying a
\* permutation to a state and then taking a Grant step need not yield the same
\* result as taking the step and then permuting.  The ground truth is therefore
\* verdict: unsound.
\*
\* The model checks clean: all invariants hold and no deadlock is reachable.
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

Request(p) ==
    /\ p \notin pending
    /\ owner # p
    /\ pending' = pending \cup {p}
    /\ UNCHANGED owner

\* Non-equivariant choice over the symmetric set: TLC always picks the same
\* element of `pending`, regardless of how Proc is permuted.
Grant ==
    /\ owner = None
    /\ pending # {}
    /\ LET c == CHOOSE q \in Proc : q \in pending
       IN /\ owner' = c
          /\ pending' = pending \ {c}

Release(p) ==
    /\ owner = p
    /\ owner' = None
    /\ UNCHANGED pending

Next ==
    (\E p \in Proc : Request(p) \/ Release(p)) \/ Grant

Spec ==
    Init /\ [][Next]_vars

\* --- invariants ----------------------------------------------------------

Holders == {p \in Proc : owner = p}

MutualExclusion == \A p, q \in Holders : p = q

NoPendingOwner == ~\E p \in Proc : (p \in pending) /\ (owner = p)

=============================================================================
