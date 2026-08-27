# Draft Engine Controlled Experiments

Companion to `docs/DRAFT_ENGINE_FORENSIC_AUDIT.md`. All experiments here use
`src/alpha_squad/evaluation/draft_forensics.py` — a diagnostic-only module, separate from both
production `league/draft.py` and the official benchmark harness (`evaluation/draft_simulation.py`,
behind `docs/DECISIONS.md` D54's already-reported results). Nothing here changes production
behavior; every number is a measurement, not a tuning target. Per the phase's own explicit
instruction, this document reports which mechanism fixes which failure, not which tier "wins."

## Methodology

**Design.** One team (the "team in question") drafts under a fixed scoring tier from a given
draft slot; the other 9 slots always draft by real historical market consensus — the same fixed
opponent field, snake-draft loop, and outcome scoring `evaluation/draft_simulation.py` already
uses (`_market_consensus_pick`, `_snake_overall_pick`, `_next_pick_overall`, `_actual_points_for`
are imported and reused, not reimplemented, so any difference between tiers is attributable to the
scoring formula alone).

**Data — three distinct samples, sized for what each is trying to answer, not identical:**
- The full 8-tier ablation grid (§ "Full grid" below) covers all 5 real seasons the official
  benchmark uses (2021-2025) × all 10 draft slots × all 8 tiers — 400 drafts. Tier H alone costs
  ~37s/draft (it calls the real, unmodified production `recommend_draft_pick`, which re-queries
  the database per candidate per pick), so this is the largest grid tractable in this phase, not
  a deliberately narrowed one.
- The baseline sanity checks (§ below) use a smaller, explicitly 3-season subset (2021/2023/2025)
  × all 10 slots × 3 non-Alpha strategies — 90 drafts — since their purpose is a qualitative
  check (does the simulator ever produce a pathological roster under a rational strategy) not a
  precise aggregate effect size.
- The single-slot deep dive (§ below) is exactly the one already-traced pathological example
  (2021, draft slot 1) run under all 8 tiers, chosen specifically because its full pick-by-pick
  mechanism is already understood from `docs/DRAFT_ENGINE_FORENSIC_AUDIT.md` §4 — it illustrates
  *why* a tier does or doesn't help, which the aggregate grid alone cannot show.

All 10 draft slots are covered in
every sampled season, so no single slot's luck drives a tier's apparent result.

**Tiers (A-H), each adding exactly one term on top of the previous tier's score:**

| Tier | Adds | Formula (on top of the previous tier) |
|---|---|---|
| A | raw player value only | `score = projection` |
| B | + current roster fit | `score = VORP × fit_mult(current need)` |
| C | + current positional scarcity | `× (0.7 + 0.6 × scarcity_norm[pos])` — `positional_scarcity()` is a real production function (`league/replacement.py`) already used by the waiver engine but never by the draft engine (forensic audit §2) |
| D | + analytical future scarcity | `× (1.3 − 0.6 × expected_survival_rate[pos])`, where `expected_survival_rate` aggregates the same per-player Uniform(ecr_best, ecr_worst) survival model `next_pick_survival_probability` already uses for one candidate, applied across the whole position |
| E | + roster feasibility | `× 0.1` once this position's drafted count reaches a league-config-derived cap (`starting slots + ⌈bench_size / n_positions⌉`) — a hard floor, not `roster_fit_multiplier`'s soft [0.7, 1.3] bound |
| F | + explicit opportunity cost | `+ max(0, best_available_VORP[pos] − expected_best_VORP[pos]_at_next_pick)`, priced in points, not a multiplier |
| G | + opponent-behavior simulation | replaces D's analytical estimate with a literal replay: step `_market_consensus_pick` forward the real number of opponent picks before this team's next turn, using the actual known opponent strategy, and multiply by 1.3 if the position empties in that replay |
| H | the real, unmodified `recommend_draft_pick` | production code, called directly, unmodified |

D and G are mechanically related by construction in this specific simulated environment: the
*only* source of positional depletion between two of the team-in-question's picks is the other 9
(real, market-consensus) opponents, so "future scarcity" and "opponent depletion" describe the
same underlying event here. D estimates it analytically (fast, statistical); G computes it by
literally replaying the known opponent strategy (slower, exact for this simulation's specific
opponent model). This is stated plainly rather than presented as two independent mechanisms that
happen to agree.

## Baseline sanity checks (directive §14-15)

Before trusting any ablation result, the simulator itself has to be shown sane independent of
Alpha. `homogeneous_league_draft` drafts **all 10 slots** under one identical real strategy (not
the 1-vs-9 fixed-opponent design), removing the fixed-opponent-field confound entirely.

No separate ADP series exists in this environment (`docs/EVALUATION_LIMITATIONS.md`, D17) — real
preseason FantasyPros-mirrored ECR (`market_consensus`) is the closest available substitute and
is what "ADP vs ADP" / "ECR vs ECR" mean below.

| Strategy (all 10 slots) | Seasons | QB=0 | RB=0 | WR=0 | TE=0 |
|---|---|---|---|---|---|
| market_consensus ("ECR vs ECR") | 2021/2023/2025 | 0/30 | **0/30** | 0/30 | 6/30 |
| raw_value ("simple value vs itself") | 2021/2023/2025 | 1/30 | **0/30** | 0/30 | 4/30 |
| vorp ("simple VORP vs itself") | 2021/2023/2025 | 0/30 | **0/30** | 0/30 | 4/30 |

**RB is never zero in 90 real homogeneous-league trials under any baseline strategy.** TE goes to
zero at a real rate under every strategy including bare VORP — consistent with "punt/stream TE," a
legitimate, well-known real fantasy strategy given TE's shallow one-dedicated-slot demand, not a
simulator defect. Per the directive's own decision rule (§14): baseline strategies produce
realistic rosters; **the simulator is validated as sound.**

## Pathological draft analysis (directive §7)

Full pick-by-pick machine-readable traces: `reports/draft_decision_trace.json`
(`2021_slot1_tierH`, `2025_slot1_tierH`), produced by `evaluation/draft_forensics.py`'s tier-H
path, confirmed to reproduce the exact roster the official benchmark records for the same
season/slot. Full narrative analysis in `docs/DRAFT_ENGINE_FORENSIC_AUDIT.md` §4; the short
version: **both traced drafts are effectively decided by the team's first 1-2 picks.** RB is a
live, competitive top-5 candidate at pick #1 in both cases (VORP 103.1 in 2021; present but
outscored in 2025) and falls out of the top 5 entirely by the team's second turn (pick #20),
not reappearing until the position is already below replacement level. This is not a multi-round
feedback loop — it is a near-immediate, largely irreversible loss of position.

## Ablation results

### Single-slot deep dive (2021, draft slot 1 — the traced pathological example)

| Tier | Total pts | Starter pts | Position counts | RB count |
|---|---|---|---|---|
| A (raw value) | 2761.5 | 1201.8 | QB 12, WR 5 | **0** |
| B (+ current fit) | 2799.5 | 1588.0 | QB 7, WR 7, TE 3 | **0** |
| C (+ current scarcity) | 2676.0 | 1475.8 | QB 9, WR 6, TE 2 | **0** |
| D (+ future scarcity, analytical) | 2769.7 | 1404.0 | QB 10, WR 6, TE 1 | **0** |
| E (+ feasibility cap) | 2795.0 | 1578.5 | QB 7, WR 6, TE 4 | **0** |
| F (+ opportunity cost) | 2676.2 | 1723.9 | QB 7, WR 6, TE 3 | **1** |
| G (+ opponent replay) | 3110.2 | 1254.2 | QB 11, WR 5, TE 1 | **0** |
| H (real production engine) | 2829.8 | 1676.9 | QB 6, WR 7, TE 4 | **0** |

**Every tier through E still produces zero RB for this specific draft.** Only F — explicit,
points-denominated opportunity cost — recovers any RB at all, and even then only one (still short
of the league's 2 starting RB slots). G, despite modeling opponent behavior directly rather than
analytically, does *not* recover RB here, and in fact stacks QB even harder (11) than the current
production engine (H, 6) — a genuinely counter-intuitive result addressed below rather than
smoothed over.

### Full grid (5 seasons × 10 slots × 8 tiers, 400 real drafts)

Raw data: `reports/draft_forensics_experiment_results.json`. Pooled across all 5 seasons and 10
slots (n=50 per tier):

| Tier | Mean total pts | Mean starter pts | RB=0 rate | QB=0 | TE=0 | Avg. concentration index |
|---|---|---|---|---|---|---|
| A (raw value) | 2760.6 | 1433.6 | **40/50 (80%)** | 0/50 | 20/50 | 0.468 |
| B (+ current fit) | 2791.7 | 1733.7 | 10/50 (20%) | 5/50 | 0/50 | 0.368 |
| C (+ current scarcity) | 2739.4 | 1610.1 | 16/50 (32%) | 5/50 | 0/50 | 0.385 |
| D (+ future scarcity, analytical) | 2756.3 | 1599.5 | 16/50 (32%) | 4/50 | 0/50 | 0.393 |
| E (+ feasibility cap) | 2723.4 | 1654.5 | 7/50 (14%) | 4/50 | 0/50 | 0.344 |
| F (+ opportunity cost) | 2733.8 | **1789.1** | **2/50 (4%)** | 0/50 | 0/50 | 0.320 |
| G (+ opponent replay) | 2837.8 | 1682.7 | 18/50 (36%) | 4/50 | 3/50 | 0.403 |
| H (real production engine) | 2606.6 | 1688.2 | 10/50 (20%) | 0/50 | 0/50 | 0.345 |

**This resolves the forensic audit's open "does the RB-specific pattern generalize" question,
precisely rather than by extrapolating from the single traced slot: yes, but concentrated, not
uniform.** The real production engine (H) zeros RB in exactly **10 of 10 draft slots in the real
2021 season and 0 of 10 in every one of 2022, 2023, 2024, and 2025.** This is not a rare,
single-slot fluke (§4's traced example was one of ten identically-failing 2021 slots) nor a
constant, every-season failure — it is a real, season-specific pathology, concentrated the year
the underlying real RB market apparently ran hottest and fastest relative to Alpha's VORP
valuations that year specifically. *Why 2021 specifically* is not established here (`UNKNOWN`,
carried into the forensic audit) — investigating the real 2021 RB market/VORP data in detail was
out of this phase's scope once the mechanism (not the trigger season) was the diagnostic target.

**F is confirmed, at full scale, as the standout mechanism** — its 4% RB=0 rate is a fifth of
the production engine's own 20%, and its mean starter points (1789.1) is the *highest of any
tier including H* (1688.2), beating H in 4 of the 5 real seasons (all but 2023, where H's
1813.3 edges F's 1728.8). This is not a uniform win — reported as found, not smoothed into "F is
strictly better."

**A genuinely important, real, counter-intuitive finding that changes what should be
recommended: naively adding `positional_scarcity()` makes things *worse*, not better.**
Tiers C, D, E, F, and G all inherit the same scarcity-adjusted base score (`vorp × fit_mult ×
(0.7 + 0.6×scarcity_norm[pos])`) before adding their own further term — and C alone, with
nothing else changed from B, raises the RB=0 rate from 20% to 32%. Querying the real
`positional_scarcity()` values directly explains why: in real 2021 and 2023 data, **QB scores
the *highest* scarcity of any position (`scarcity_norm=1.0`) and RB one of the *lowest*
(0.16–0.26)**:

| Season | RB scarcity (raw / normalized) | WR | QB | TE |
|---|---|---|---|---|
| 2021 | 40.2 / 0.26 | 45.6 / 0.45 | 60.7 / **1.00** | 33.2 / 0.00 |
| 2023 | 36.3 / 0.16 | 62.1 / 0.49 | 102.2 / **1.00** | 23.5 / 0.00 |
| 2025 | 45.2 / 0.62 | 60.4 / 1.00 | 57.9 / 0.94 | 20.7 / 0.00 |

`positional_scarcity()`'s real definition — mean starter value minus replacement level — measures
*value concentration at the top of a position*, not the popular fantasy-strategy sense of "RB
scarcity" (touch concentration and injury risk making a comparable *replacement* hard to find
quickly mid-draft). A 2-dedicated-QB-slot league with no QB-eligible FLEX slot has a small,
elite top tier scoring far above a low replacement floor, which this metric reads as "QB is the
scarce position" — precisely reinforcing the QB-stacking side of the same pathology this whole
investigation started from. **Adding this specific signal, in its current form, to the draft
engine would make the documented QB-stacking problem worse, not better — a real, tested finding,
not an assumption, and a direct reason the redesign recommendation does not propose adding it.**
F's improvement is therefore more impressive than it first appears: it overcomes this same
QB-favoring headwind (F inherits the identical scarcity multiplier C does) through its
additive opportunity-cost term alone.

## Why did G (opponent simulation) not outperform F (explicit opportunity cost)?

This was not the expected result going in, and is reported as found rather than adjusted after
the fact. G's opponent-depletion multiplier is binary (1.3× if the replay shows the position empties
before the next pick, else 1.0×) — coarser than F's continuous, points-denominated cost. A
position that is merely *getting worse* rather than *disappearing outright* by the next pick gets
no credit under G but a real, proportional bonus under F. Since real positional decline is
typically gradual (a position's 4th-best remaining player is usually only somewhat worse than its
3rd-best, not catastrophically so, until very late), F's continuous pricing captures the everyday
case G's binary trigger misses. This suggests the *shape* of an opportunity-cost signal (continuous
vs. threshold) matters as much as *whether* one exists at all — a specific, testable design
implication carried into `docs/DRAFT_ENGINE_REDESIGN_RECOMMENDATION.md`.

## Roster feasibility vs. fantasy value (directive §9)

Tracked as explicitly separate metrics throughout (`roster_feasibility_metrics`): position counts,
starting-requirement comparison, zero-drafted-starting-positions, positions over a league-derived
feasibility cap, max single-position share, and a Herfindahl-style concentration index — none of
these are fantasy-value numbers, and none were derived from "what looks realistic" rather than the
league's own structural settings (`league.dedicated_slots()`, `league.bench_size`). The single-slot
table above already shows the two dimensions diverge: tier G has the *highest* total points (3110.2)
of any tier in this draft but is *not* more feasible (QB 11, RB 0) — high fantasy value and poor
roster construction are demonstrated as genuinely separable outcomes, not merely a hypothesis.

## Conclusions

1. The simulator is valid (baseline sanity checks, RB never zero in 90 trials under 3
   independent non-Alpha strategies).
2. The player projection model is not the cause (`docs/ALPHA_VS_BASELINES_EVALUATION.md` §1;
   the pick-1 trace shows the RB was correctly valued and simply outscored by the formula, not
   mis-projected).
3. At full scale (400 real drafts, all 5 seasons, all 10 slots), the real production engine (H)
   zeros RB in exactly 10 of 10 slots in 2021 and 0 of 10 in every other season — a real,
   season-concentrated pathology, not a single-slot fluke or a uniform every-season failure.
4. Layering in current scarcity (C), analytical future scarcity (D), or a hard feasibility cap
   (E) does not recover the neglected position at scale either — C, D, and G all made the RB=0
   rate *worse* than plain roster-fit (B) alone (32%, 32%, 36% vs. 20%), because
   `positional_scarcity()`, as currently defined, rates QB as more "scarce" than RB in this
   league's real data and reinforces the QB-stacking side of the same pathology rather than
   fixing the RB side. This is a genuine, tested, counter-intuitive finding, not smoothed over.
5. Explicit, points-denominated opportunity cost (F) is the only tier that both reduces RB=0
   substantially (4% vs. H's 20%) and improves mean starter points above the real production
   engine (1789.1 vs. 1688.2, beating H in 4 of 5 seasons) — while still inheriting the same
   QB-favoring scarcity multiplier every other tier from C onward carries, making its
   improvement the more notable for having overcome that headwind rather than avoided it.
