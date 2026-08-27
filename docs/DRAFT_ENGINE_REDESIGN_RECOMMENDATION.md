# Draft Engine Redesign Recommendation

> **STATUS: IMPLEMENTED (M18 / `docs/DECISIONS.md` D55) — with one substantive correction.**
>
> The mechanism recommended here (continuous, points-denominated positional opportunity cost
> fed by a G-style opponent replay) shipped and is measured at **+112.9 mean starter points**
> on the official benchmark. But the specific *formula* proposed below —
> `production + opp_cost` — was found, on verifying it against the source, to have **never been
> measured**: Experiment F is `vorp × fit × scarcity × future × [feasibility] + opp_cost`, which
> includes `positional_scarcity` (proven harmful) and excludes production's `risk`/`survival`
> terms. A new pre-registered P-tier ablation was run to close that gap, and what shipped is
> the integrated form `(VORP + opp_cost) × fit × risk × survival × [cap]`, which measured
> better than the raw additive form proposed here. See D55 for the full account.
>
> The rest of this document is preserved as written during the diagnostic phase.

Not implemented in this phase — a diagnostic phase's output, per explicit instruction. Grounded
in `docs/DRAFT_ENGINE_FORENSIC_AUDIT.md` (root cause) and `docs/DRAFT_CONTROLLED_EXPERIMENTS.md`
(what actually moved the needle when tested, not assumed).

## Root cause (restated from the forensic audit)

`recommend_draft_pick`'s score has no representation of *positional* opportunity cost or
forward-looking scarcity — only a single-candidate survival probability. Demonstrated, not
inferred: in both fully-traced pathological drafts, a real, viable RB was a live top-5 candidate
at pick #1 and fell out of consideration entirely by the team's second pick, before any
same-position saturation penalty (the mechanism already fixed once this phase, D54) was even
relevant, since RB was never being over-drafted — it was never being drafted at all. At full
scale (400 real drafts, 5 seasons × 10 slots × 8 tiers), the current production engine zeros RB
in 10/50 trials, concentrated entirely in the real 2021 season (10/10 slots that year, 0/10 in
every other season). Layering in current positional scarcity, analytical future scarcity, or a
hard feasibility cap did not recover the neglected position — current and future positional
scarcity in particular made it *worse* (RB=0 rate rose to 32%, because `positional_scarcity()`
rates QB, not RB, as the scarce position in this league's real data). Only an explicit,
points-denominated opportunity-cost term recovered it substantially (RB=0 down to 2/50) and,
unlike every other tier tested, also improved mean starter points above the current production
engine (1789.1 vs. 1688.2, beating it in 4 of 5 real seasons).

## Proposed fix: an explicit, per-position opportunity-cost term, continuously priced

Add a term to `recommend_draft_pick`'s score equal to Experiment F's construction:

```
opportunity_cost(position) = max(0, best_available_VORP[position] - expected_best_VORP[position]_at_my_next_pick)
score = vorp[player] * fit_mult * risk_mult * survival_mult + opportunity_cost(positions[player])
```

`expected_best_VORP[position]_at_my_next_pick` should be estimated the way Experiment G computed
it exactly (a literal replay of the known real market-consensus-style opponent behavior between
now and the next pick), not Experiment D's analytical approximation — the controlled experiments
found G's *mechanism* (agent-based replay) is the more faithful one, but its *binary* trigger
(1.3× only if the position empties completely) is too coarse; F's *continuous, points-based*
pricing captured the everyday case (a position quietly getting worse, not just vanishing) that G's
threshold missed. The recommendation is therefore F's pricing shape combined with a G-style
opponent replay as its input, not either experiment's exact implementation as tested — the
controlled experiments isolated which *properties* of a fix matter, not a finished formula to
copy verbatim.

## Why this, and not something more sophisticated

The forensic audit's directive explicitly warns against reaching for a complicated solution
because it sounds sophisticated. Considered and set aside:

- **Full Monte Carlo lookahead / dynamic programming over the whole remaining draft.** Would
  address the same root cause (forward-looking value) at far higher implementation and runtime
  cost, and the controlled experiments never demonstrated that the *simple* opponent-replay
  signal (already available, already computed for tier G) is insufficient — only that its
  *binary* framing was too coarse. Escalating to full-draft optimization before establishing that
  a much cheaper continuous-pricing fix is inadequate would be solving a problem not yet shown to
  exist.
- **A hard positional cap enforced at the roster-construction level (e.g., "never draft a 3rd
  bench RB before every position has 1").** Rejected for the same reason arbitrary positional caps
  were explicitly ruled out by this phase's own directive: it would happen to produce a more
  "normal-looking" roster without addressing why RB specifically disappears, and would need
  separate hand-tuning for every league configuration rather than being derived from the league's
  own settings the way `_feasibility_cap` (Experiment E) already is.
- **Discard VORP and rebuild positional value from scratch.** Ruled out directly: §1 of
  `docs/ALPHA_VS_BASELINES_EVALUATION.md` shows the underlying player-value model beats every
  baseline on MAE at every position, and the forensic audit's pick-1 trace shows VORP correctly
  identified the passed-over RB as valuable (VORP 103.1, 2nd-best candidate) — the value layer is
  not the problem.
- **Add `positional_scarcity` (Experiment C), with or without a forward-looking term.** Tested
  directly at full scale (400 real drafts) and actively rejected, not merely found insufficient:
  adding it *raised* the RB=0 rate from 20% (current production engine) to 32% — worse than
  doing nothing. Real data explains why: `positional_scarcity()` ("mean starter value minus
  replacement level") rates QB as the most scarce position in real 2021/2023 data and RB as one
  of the least, the opposite of the popular fantasy-strategy sense of "RB scarcity," and
  reinforces the QB-stacking side of the same pathology rather than fixing the RB side
  (`docs/DRAFT_CONTROLLED_EXPERIMENTS.md`). **This function should not be added to the draft
  engine in its current form.** The proposed fix below does not use it.

## Complexity

Moderate, not high. `_future_position_pool_after_market_consensus`-equivalent logic already
exists and was exercised across the full controlled-experiment grid without correctness issues;
porting it into `recommend_draft_pick` mainly means: (a) computing, once per pick (not once per
candidate — the opponent replay is positional, not per-player, so it can be computed once per
distinct position among the candidates, not once per candidate), the expected best-available
VORP at each position after replaying the known opponent model forward to the team's next pick;
(b) adding the resulting per-position opportunity-cost term to the score, applied directly to
the *existing* production formula (`vorp × fit_mult × risk_mult × survival_mult`) — deliberately
*not* layering in `positional_scarcity` first, per the finding above. No new data sources, no
new model, no new database tables.

## Expected benefits

Directly targets the demonstrated failure mode (RB disappearing at the team's first 1-2 picks)
rather than a proxy for it. Measured at full scale (400 real drafts), this mechanism reduces the
RB=0 rate from 20% to 4% and is the only tested tier that improves mean starter points above the
current production engine (1789.1 vs. 1688.2 pooled). It is not a complete fix — 2/50 trials
still zero RB, and F loses to the current engine outright in 1 of 5 real seasons (2023) — so this
should be framed to stakeholders as a demonstrated, substantial, measured improvement, not a
guaranteed complete one, and should still be re-verified against the official benchmark
(`alpha-squad evaluate draft-simulation`) rather than assumed to transfer unchanged from this
diagnostic harness's numbers.

## Risks

- **Not yet verified as sufficient at full scale.** The ablation grid (`docs/DRAFT_CONTROLLED_EXPERIMENTS.md`)
  covers all 5 of the official benchmark's real seasons and every draft slot, but each tier
  tested exactly one addition in isolation, by design, to isolate causes — a combined
  C+F-shaped tier (positional scarcity plus explicit opportunity cost together) has not been
  run at all. The *combined* effect is `UNKNOWN` per the forensic audit's own classification and
  must be measured, not assumed, before claiming the fix works.
- **A continuous opportunity-cost term changes the score's scale.** Unlike the existing
  multiplicative terms (all bounded, e.g. [0.7, 1.3]), an additive points-denominated term has no
  natural ceiling; a pathological input (e.g., a position with exactly one player and enormous
  variance in its ecr_best/ecr_worst dispersion) could dominate the score unpredictably. Needs an
  explicit bound or a documented, deliberate reason it does not need one, decided with real data
  in hand rather than assumed safe.
- **Opponent replay assumes the same "9 real market-consensus opponents" model this whole
  evaluation phase already uses and discloses as a simplification** (`docs/EVALUATION_LIMITATIONS.md`).
  A live production draft has real, unknown, non-market-consensus human opponents; the *replay*
  is only as good as that assumption, same limitation the existing `survival_mult` term already
  carries today.

## Tests required before shipping

- Regression test proving a position that would otherwise disappear (constructed the way
  `test_league.py`'s existing `TestRosterNeed`/`TestNextPickSurvivalProbability` tests construct
  synthetic scenarios) is now selected when its opportunity cost is large, using a synthetic
  roster/market state, not real historical data (keeps the test fast and deterministic).
- A re-run of `alpha-squad evaluate draft-simulation` (the official benchmark, not this phase's
  diagnostic harness) across the full 2021-2025 window, compared against the numbers already on
  record in `docs/ALPHA_VS_BASELINES_EVALUATION.md` §4 and `docs/DECISIONS.md` D54 — the same
  verify-with-a-real-rerun discipline already established for the saturation-penalty fix.
- A repeat of this phase's own pick-by-pick replay (`draft_decision_trace.json`-style) for the
  same two pathological slots (2021/2025, slot 1), confirming RB is now a live candidate at the
  team's early picks, not just that the final roster count improved — the aggregate metric alone
  was shown in this phase to hide exactly this kind of mechanism-level detail.
- Determinism check: re-run twice in separate processes and confirm byte-identical results,
  matching the discipline already required of `evaluation/draft_simulation.py` after D54 found a
  real hash-randomization bug in the existing harness's tie-breaking.
