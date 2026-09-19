"""Weekly-ranking research instruments (W-phase program, `docs/weekly/`).

**Research only.** Nothing in this package is imported by any production path -- not the API,
not the CLI, not `league/`, not `models/`. It exists so the empirical claims in
`docs/weekly/W1_FOUNDATION_AUDIT.md` are reproducible rather than asserted, which is the
lesson D92 recorded when D88-D90's runner turned out never to have been committed.

The weekly program asks a different question from the draft program (D86-D108): *given only
what was known at a stated cutoff, how well did a system order players by their fantasy
production for the upcoming week?* It reuses this repository's data, identity and provenance
machinery unchanged, and reuses its methodology only where the methodology actually transfers
-- see `docs/weekly/W1_FOUNDATION_AUDIT.md` §"Shared vs draft-specific vs weekly-specific"."""
