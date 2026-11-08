---------------------------- MODULE LabLockSymm ----------------------------
\* Wrapper module for the symmetry-reduced run of LabLock.  This is exactly the
\* shape of module that the SymView tool generates: it EXTENDS the root module
\* plus TLC and defines a zero-argument permutation-set operator and a
\* zero-argument view operator that the .cfg can refer to by name.
EXTENDS LabLock, TLC

\* All permutations of the symmetric set of model values.
SymViewPerms == Permutations(Proc)

\* The variables retained by the view.  LabLock has no auxiliary variable, so
\* nothing is dropped.
SymViewView == <<owner, pending>>

=============================================================================
