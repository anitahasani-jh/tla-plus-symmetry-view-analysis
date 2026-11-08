---------------------------- MODULE LabLogSymm -----------------------------
\* Wrapper module for the symmetry- and view-reduced run of LabLog, i.e. the
\* shape of module the SymView tool generates.  `log` is a history variable, so
\* the view keeps only `owner` and `pending`.
EXTENDS LabLog, TLC

\* All permutations of the symmetric set of model values.
SymViewPerms == Permutations(Proc)

\* The variables retained by the view: the history variable `log` is dropped.
SymViewView == <<owner, pending>>

=============================================================================
