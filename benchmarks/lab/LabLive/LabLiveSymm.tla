---------------------------- MODULE LabLiveSymm ----------------------------
\* Wrapper module for the symmetry-reduced run of LabLive, i.e. the shape of
\* module the SymView tool generates.  LabLive has no auxiliary variable, so the
\* view retains all three variables and only SYMMETRY is used.
EXTENDS LabLive, TLC

\* All permutations of the symmetric set of model values.
SymViewPerms == Permutations(Proc)

\* The variables retained by the view.
SymViewView == <<owner, pending, done>>

=============================================================================
