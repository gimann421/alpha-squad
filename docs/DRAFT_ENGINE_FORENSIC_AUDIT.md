# Draft Engine Forensic Audit

Diagnostic phase, per an explicit directive not to redesign the draft engine before understanding
*why* it produces unrealistic rosters. Companion documents: `docs/DRAFT_CONTROLLED_EXPERIMENTS.md`
(the ablation results this audit's hypotheses are tested against) and
`docs/DRAFT_ENGINE_REDESIGN_RECOMMENDATION.md` (what to build next, not built in this phase).
`reports/draft_decision_trace.json` holds the full machine-readable pick-by-pick trace for the
two pathological drafts analyzed in §4.

This document compares documentation to actual code throughout, rather than assuming
`PRODUCT_SPEC.md`/`ACCEPTANCE_CRITERIA.md`/`CLAUDE_CODE_LEAD_PROMPT.md` accurately describe what
is implemented. Several places where they diverge turn out to matter.

## 1. The actual draft objective, traced end to end

`league/draft.py::recommend_draft_pick` is the entire production decision. Quoting the real code
(not a paraphrase):

```python
projections, positions = load_season_projections(con, season)          # PLAYER DATA + PROJECTION
vorp = marginal_value_over_replacement(league, projections, positions)  # REPLACEMENT VALUE + VORP
needs = roster_need(league, roster_positions)                           # ROSTER FIT (need side)

for player_id in available_player_ids:
    pos = positions[player_id]
    confidence = _confidence_for(con, player_id, season)                 # CONFIDENCE
    survival = next_pick_survival_probability(con, player_id,
                   next_pick_overall, season, ecr_type)                  # SURVIVAL
    fit_mult = roster_fit_multiplier(needs.get(pos, 0.0))                # ROSTER FIT (multiplier)
    risk_mult = confidence if confidence is not None else 0.7
    survival_mult = 1.0 if survival is None else (1.0 + 0.3 * (1.0 - survival))
    score = vorp[player_id] * fit_mult * risk_mult * survival_mult       # FINAL SCORE

candidates.sort(key=lambda c: (-c.score, c.player_id))
best = candidates[0]                                                     # PICK
```

`load_season_projections` (`league/replacement.py`) reads `uncertainty_predictions.point_prediction`
for established players (M6's walk-forward model) and backfills true rookies from
`rookie_predictions.predicted_rookie_points` (M7) when a player has no M6 row — this part is
correctly leakage-safe and already validated in `docs/ALPHA_VS_BASELINES_EVALUATION.md` §1.

**What increases a player's score:** higher VORP (points above that position's replacement
level); a roster need for that position (`fit_mult` up to 1.3×); high model confidence (`risk_mult`
up to ~1.0, since confidence is a 0-1 probability, never a boost above 1.0); low probability of
surviving to the next pick (`survival_mult` up to 1.3× when `survival≈0`).

**What decreases it:** low VORP; a saturated position (`fit_mult` down to 0.7×, see §3 for exactly
how weakly this engages in practice); low model confidence (`risk_mult` floors at 0.7 when
confidence is `None`); near-certain survival to the next pick (`survival_mult`→1.0, never below
1.0 — waiting is never explicitly penalized, only failing to wait is explicitly rewarded).

**How future picks affect it:** only through `survival_mult`, and only for the ONE candidate
being scored right now — there is no representation of "if I don't take an RB now, the RB
position specifically will be worse in general by my next turn." Survival asks "will *this
player* still be there," never "will *a player this good at this position* still be there."

**How bench vs. starter value is treated:** not distinguished at all inside the score. VORP is
computed once per player against a position's `replacement_level` (itself computed from
`compute_league_starters`, which does correctly do real starter/flex/bench allocation) — but the
*pick score* never asks whether the specific player being scored would actually start on the
roster being built. A player scored to fill an already-saturated position contributes to
`total_roster_points` even though real bench points a team never starts are worth nothing in
real scoring. This directly explains the recurring split in `docs/ALPHA_VS_BASELINES_EVALUATION.md`
§4 between total-points and starter-points shortfalls.

**Whether positional need is forward-looking or reactive:** entirely reactive. `roster_need`
reads only the roster already drafted (`roster_positions`, i.e., this team's own picks so far).
Nothing in the score anticipates that a position's remaining depth will change before this team's
next turn, except the one-player `survival_mult` above.

**Whether other teams' behavior affects the score:** not directly. `available_player_ids` reflects
who has already been drafted by everyone (so the *candidate pool* shrinks correctly), but nothing
in the scoring formula reasons about *what the other 9 teams are about to do next*.

## 2. A real, load-bearing documentation-vs-code gap: positional scarcity

`PRODUCT_SPEC.md` ("League optimizer... must calculate... positional scarcity") and
`ACCEPTANCE_CRITERIA.md` ("Positional scarcity is calculated") both name positional scarcity as a
required, distinct calculation — separate from "marginal points over replacement" (VORP), which
both documents list as its own separate bullet. The codebase has exactly this: a `positional_scarcity()`
function in `league/replacement.py` distinct from `marginal_value_over_replacement()`, computing
"mean value of that position's actual starters minus its replacement level" — the classic
value-based-drafting scarcity read.

**It is real, tested, and used — by the waiver engine.** `grep` confirms `positional_scarcity` is
imported and consulted by `league/waiver.py::recommend_waiver_pickup` (feeds `competing_bid_likelihood`)
and by `league/roster_intelligence.py` (a My-Team display field). **It is never imported by
`league/draft.py`.** `recommend_draft_pick`'s score never consults it. The acceptance criterion
"positional scarcity is calculated" is technically true — the function exists and is exercised
elsewhere — but the actual DRAFT decision, the one place in the whole system where a position's
scarcity most obviously matters, does not use it. This is Experiment C's exact subject (§ see
`docs/DRAFT_CONTROLLED_EXPERIMENTS.md`).

## 3. A second real gap: `roster_need`'s depth target ignores the league's own bench size

`league/roster.py::roster_need` computes `depth_target = slots + 2` — a hardcoded constant "a
little bench depth beyond the starting slots is healthy," applied identically to every position
regardless of league configuration. `LeagueContext.bench_size` (a real property reading
`league.roster["bench"]`, currently `10` for `target_league.yaml`) is **never referenced by
`roster_need` or anywhere else in production code** (confirmed: `grep -rn "bench_size"` returns
only its own definition). The hardcoded `+2` has no relationship to the league's actual declared
bench size, and is applied the same way whether the league carries a 3-man bench or a 20-man one.

A related, smaller inconsistency in the league config itself, found while checking this:
`target_league.yaml` declares `lineup` totaling 9 starting slots (`QB:2, RB:2, WR:2, TE:1, FLEX:2`)
and `roster.bench: 10` (9 + 10 = 19), but `roster.roster_size: 17` — two fewer than the starters-plus-bench
sum would imply. This predates this phase (D7) and is noted here because §8's feasibility-cap
experiment (Experiment E) derives its cap from `bench_size`, and this inconsistency means that
derivation is currently working from a bench figure the roster's own total size can't actually
accommodate in full. Not fixed in this diagnostic phase (see the redesign recommendation for
scope).

## 4. Pathological draft analysis: when did it become doomed?

Full traces: `reports/draft_decision_trace.json` (keys `2021_slot1_tierH`, `2025_slot1_tierH`),
generated by replaying the real, unmodified `recommend_draft_pick` pick-by-pick via
`evaluation/draft_forensics.py`'s tier-H path (confirmed to reproduce the exact same roster the
official `alpha-squad evaluate draft-simulation` benchmark records for the same season/slot).

### 2021, draft slot 1 — final roster: 6 QB / 7 WR / 4 TE / **0 RB**

| Pick (overall) | Selected | Best RB in top-5 candidates |
|---|---|---|
| 1 | TE (VORP 127.5) | RB present, VORP 103.1 (2nd-highest, not selected) |
| 20 (round 2) | WR | **none in top 5** |
| 21–140 (rounds 3–14) | QB/WR/TE mix | **none in top 5, every single pick** |
| 160 (round 16) | WR | RB reappears, VORP **−135.4** (below replacement) |
| 161 (round 17) | TE | RB again, VORP −135.4 (runner-up, not selected) |

**The draft was not doomed by a slow-building feedback loop over many rounds. It was doomed by
pick #20 — this team's *second* selection.** A real, viable RB (VORP 103.1, the second-best
candidate) was on the board at pick #1 and passed over for a TE. By pick #20, nineteen other
picks (all real, by the 9 real market-consensus opponents) had already happened elsewhere in the
draft, and RB had already fallen out of the top 5 candidates entirely — it does not reappear
until round 16, by which point every remaining RB is worse than replacement level. Between pick 1
and pick 20 there was no second chance: the position was gone before this team's own cadence gave
it another look.

### 2025, draft slot 1 — final roster: 3 QB / 9 WR / 2 RB / 3 TE

Same signature: pick #1 took the best QB (VORP 148.7); RB does not appear in the top 5 at any of
this team's picks through pick #41 (round 5), reappearing only at pick #60 (round 6, VORP 46.9,
already well off its pick-1-era value). Two RBs eventually get drafted late — a *less* severe
version of the same failure than 2021's zero, but the same mechanism: RB is not competitive at
this team's early picks and is gone or diminished by the time it would organically become
"needed" under `roster_need`'s reactive definition.

**Answering the directive's central question directly: the draft is doomed within the first one
to two of the team-in-question's own picks, not by a multi-round feedback loop.** This rules out
one plausible-sounding hypothesis before it was ever tested against real data: that pathology
*builds* gradually as `roster_fit_multiplier`'s weak saturation penalty (docs/DECISIONS.md D54)
lets a hot position snowball turn after turn. That mechanism is real and does make the *QB*-side
of these rosters worse (see D54), but it is not what causes the *RB* zero — RB never gets hot and
snowballed *into*; it simply disappears from consideration almost immediately and never has a
realistic chance to be corrected later, because nothing in the score represents "this position
depletes fast, secure it now" at the one moment (pick 1-2) when it would have mattered.

## 5. Is the simulator itself valid?

Directive §14-15's mandatory check. `evaluation/draft_forensics.py::homogeneous_league_draft`
drafts **all 10 slots** under one identical strategy (not the 1-vs-9-fixed-opponent design used
everywhere else in this codebase), removing any fixed-opponent-field confound entirely, for three
independent, real, non-Alpha strategies: `market_consensus` (real preseason ECR — the closest
real substitute to ADP in this environment, no separate ADP series exists, D17), `raw_value`
(highest raw projected points, no VORP), and `vorp` (VORP, no roster context at all — literally
Experiment A run league-wide).

90 total homogeneous drafts (3 strategies × 3 seasons [2021/2023/2025] × 10 slots), counting how
many of the 10 slots end up with **zero** players at a position with a real starting requirement:

| Strategy | Seasons | QB=0 | RB=0 | WR=0 | TE=0 |
|---|---|---|---|---|---|
| market_consensus | 2021/2023/2025 | 0/30 | **0/30** | 0/30 | 6/30 |
| raw_value | 2021/2023/2025 | 1/30 | **0/30** | 0/30 | 4/30 |
| vorp | 2021/2023/2025 | 0/30 | **0/30** | 0/30 | 4/30 |

**RB is never zero, in any of 90 trials, under any of the three baseline strategies.** TE goes to
zero at a real, non-trivial rate under every strategy including VORP alone — consistent with the
well-known real fantasy-strategy pattern of deliberately "punting" or "streaming" TE, a
legitimate choice given TE's shallow-per-team demand (1 dedicated slot vs. QB/RB/WR's 2) rather
than a simulator defect. QB going to zero once (raw_value, 2025) is a single data point, not
pursued further here given n=1.

**Conclusion, directly per the directive's own decision rule: baseline strategies produce
realistic rosters (RB is always represented; the only real gap, TE, matches known real strategy);
Alpha does not (RB=0 in both inspected pathological drafts). The simulator is not broken. This is
Alpha's decision logic.**

## 6. Root cause classification

### ROOT CAUSE
- **`recommend_draft_pick`'s score has no representation of *positional* opportunity cost or
  forward-looking scarcity — only a single-player survival probability.** Directly demonstrated
  in §4: RB disappears from serious consideration within the team's first 1-2 picks in both
  pathological examples, and nothing in the score would have flagged "this position specifically
  empties out fast, weight it up now" at the one point it mattered. Confirmed as load-bearing at
  full scale, not just the two traced examples, by the controlled experiments in
  `docs/DRAFT_ENGINE_FORENSIC_AUDIT.md`'s companion document: across 400 real drafts (5 seasons ×
  10 slots × 8 tiers), the real production engine zeros RB in 10/50 trials (concentrated entirely
  in the real 2021 season, 10/10 slots that year); adding an explicit, points-denominated
  opportunity-cost term (Experiment F) cuts that to 2/50 — the only tier tested that both reduces
  the failure rate substantially and improves mean starter points above the current production
  engine.

### CONTRIBUTING FACTOR
- **`roster_need`'s same-position saturation penalty was too weak to prevent runaway stacking of
  a position that *is* getting drafted** (docs/DECISIONS.md D54; partially fixed — a 7th QB in a
  2-QB league cost only 6% before the fix, now hits the 0.7 floor immediately past a full bench).
  This makes *already-hot* positions worse but is not what causes RB — a position that never gets
  hot in the first place — to disappear.
- **`positional_scarcity` (§2) is computed but never consulted by the draft engine**, unlike the
  waiver engine, which does use it — but the full-scale ablation in
  `docs/DRAFT_CONTROLLED_EXPERIMENTS.md` found something more specific and more important than
  "it's missing": adding it, in its *current form*, makes the RB=0 rate *worse* (20%→32% of 400
  real drafts), because the metric ("mean starter value minus replacement level") rates QB as
  the most scarce position in real 2021/2023 data and RB as one of the least — the opposite of
  the popular fantasy-strategy sense of "RB scarcity." This is downgraded from "necessary
  supporting context for a fix" to a specific, tested caution: the *existing* function should
  not be added to the draft engine as-is; a genuinely useful positional-risk signal would need
  to measure something else (see the redesign recommendation).
- **`roster_need`'s depth target is a hardcoded constant unrelated to the league's real bench
  size** (§3). Makes the saturation-penalty fix's threshold arbitrary rather than principled, but
  is not itself what causes early-position abandonment.

### NOT A ROOT CAUSE (tested and ruled out)
- **The draft simulator's mechanics.** §5: baseline strategies never produce RB=0 across 90 real
  trials; the 9-opponent fixed-market-consensus field is a documented, disclosed simplification
  (`docs/EVALUATION_LIMITATIONS.md`) but does not itself manufacture the pathology.
- **VORP / replacement-level computed once per season rather than re-computed as players are
  drafted.** Initially suspected as a leakage-adjacent bug; on inspection this is standard
  value-based-drafting theory (replacement level represents the post-draft waiver floor, a
  property of the league's total structural demand, not of how far into a specific draft one
  particular team is) and every other production consumer (waiver, roster intelligence) relies on
  the same static-per-season computation without issue. Ruled out as a root cause of this specific
  pathology.
- **The player projection model.** `docs/ALPHA_VS_BASELINES_EVALUATION.md` §1 already shows
  `ml_season_catboost` beats every baseline on MAE at every position, including RB, over the real
  2021-2025 window — the same model whose outputs feed `load_season_projections` here. §4's
  pick-1 trace shows a real, viable RB (VORP 103.1, 2nd-best candidate) was correctly identified
  as valuable and simply outscored by a TE under the current formula, not mis-projected. Good
  predictions can and do still produce a bad draft decision (directive §18's explicit diagnostic
  question) — this is demonstrated, not assumed.
- **A same-position-only feedback loop as the primary explanation for the RB failure
  specifically** (see §4's closing paragraph) — real and demonstrated for QB-stacking, but not
  the mechanism behind RB disappearing, which happens before any stacking-driven saturation
  penalty would even be relevant to RB (RB is never drafted, so its own saturation term never
  engages).

### RESOLVED (was UNKNOWN prior to the full 400-draft grid)
- **Whether the RB-specific pattern generalizes across all 5 seasons × 10 slots, or is
  concentrated in a subset — resolved: concentrated, not uniform.** The real production engine
  (tier H) zeros RB in exactly 10 of 10 draft slots in the real 2021 season and 0 of 10 in every
  one of 2022, 2023, 2024, and 2025 (`docs/DRAFT_CONTROLLED_EXPERIMENTS.md`, full grid). This is
  neither a single-slot fluke (the traced §4 example was one of ten identically-failing 2021
  slots) nor an every-season constant — it is real, and specific to 2021's particular real RB
  market/VORP dynamics that season. *Why 2021 specifically* triggered it remains open (see
  below) — this phase diagnosed the mechanism, not the season-level trigger.

### UNKNOWN
- **Why 2021 specifically, and not 2022-2025, triggered the RB-disappearance mechanism.** The
  mechanism (§4, §6 root cause) is general — nothing in the score is season-specific — so 2021
  must have had some real, unexamined property (an unusually front-loaded real RB draft market,
  an unusual VORP distribution that season, or something else) that made the *conditions* for
  the failure line up, while 2022-2025 did not. Not investigated in this phase; a natural
  starting point for anyone pursuing this further, but out of scope for a mechanism-focused
  diagnostic phase.
- **Whether a combined fix (explicit opportunity cost, the standout single mechanism, plus the
  already-landed saturation-penalty fix, and explicitly *without* naively adding
  `positional_scarcity`, now shown to backfire) fully closes the gap to market consensus, or only
  reduces it further.** Not yet tested as a combined tier — the full grid confirms F (1789.1 mean
  starter pts) beats H (1688.2) but both still trail `market_consensus`'s pooled 2020.7
  (`docs/ALPHA_VS_BASELINES_EVALUATION.md` §4). `docs/DRAFT_ENGINE_REDESIGN_RECOMMENDATION.md`
  proposes but does not implement or measure this combination.
