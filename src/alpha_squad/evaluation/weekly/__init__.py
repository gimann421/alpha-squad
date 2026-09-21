"""Weekly-ranking research instruments (W-phase program, `docs/weekly/`).

**Research only.** Nothing in this package is imported by any production path -- not the API,
not the CLI, not `league/`, not `models/`. It exists so the empirical claims in
`docs/weekly/W1_FOUNDATION_AUDIT.md` are reproducible rather than asserted, which is the
lesson D92 recorded when D88-D90's runner turned out never to have been committed.

The weekly program asks a different question from the draft program (D86-D108): *given only
what was known at a stated cutoff, how well did a system order players by their fantasy
production for the upcoming week?* It reuses this repository's data, identity and provenance
machinery unchanged, and reuses its methodology only where the methodology actually transfers
-- see `docs/weekly/W1_FOUNDATION_AUDIT.md` §"Shared vs draft-specific vs weekly-specific".

Three modules added by W4 (`calibration.py`, `counterfactual.py`, `crosspos.py`) carry an extra
warning, because they are the easiest in this package to mistake for something shippable. The
counterfactual and oracle boards **use realized outcomes by design** -- they exist to bound what
fixing one half of a problem could possibly buy -- and the calibration transforms were built to
be *measured*, not adopted. W4 measured them and they failed
(`docs/weekly/W4_FLEX_FORENSICS_RESULTS.md`, D112). Nothing here is a production candidate.
"""
