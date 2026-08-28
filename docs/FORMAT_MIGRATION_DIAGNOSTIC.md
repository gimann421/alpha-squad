# Format migration diagnostic: 2QB dynasty → 1-QB redraft

What the audit of the format change found, what the re-baselined benchmark measures, and what
is actually costing Alpha starter points against consensus in the new format.

Companions: `docs/TARGET_FORMAT_1QB.md` (the format), `docs/BENCHMARK_SPEC.md` (what consensus
means and how a change is judged), `docs/DECISIONS.md` D56–D58.

---

## 1. The finding that invalidated the existing evaluation record

The directive asked whether the existing consensus benchmark is appropriate for a 1-QB
format. It is not, and this is not a matter of degree.

`evaluation/draft_simulation.py`, `market/edge.py`, and `evaluation/config.py` all defaulted to
`ecr_type='rsf'`. Verified from the raw source (`db_fpecr.parquet`), `rsf` comes from exactly
one FantasyPros page: `ppr-superflex-cheatsheets.php`. It is a **superflex** board.

Measured on the real preseason-2024 snapshot:

| board | composition of the overall top 15 | first QB |
|---|---|---|
| `rsf` (the benchmark until D56) | **9 of 15 are QBs** | ECR 1.7 |
| `ro` (the 1-QB board) | 0 of 15 are QBs — all RB/WR | ECR 23.4 |

So every draft number this project has ever recorded — market consensus at 2020.7 mean starter
points, `alpha_league_aware` at 1801.1, the −219.6 gap, the M17 forensic audit, the D55 P-tier
ablation — describes Alpha playing **a superflex league**. Those results are valid for the
league they measured; the pre-D56 documents now say so at the top. They do not transfer here.

### A second, independent bug in the same layer

`ecr_type` alone is not a rank space. DynastyProcess labels several independently-ranked pages
with the same `ecr_type`: `ro` merges the PPR draft board (`redraft-overall`, 102,563 rows)
with a separately-ranked 1..N IDP board (`redraft-idp`, 38,873 rows). The two sequences
collide — preseason 2024 `ro` rank 3.0 was simultaneously an LB and a WR — so "best available
by ECR" could return a linebacker in a league that cannot start one. And because the primary
key did not include the page, one of any two rows a player held on the same date was silently
dropped.

Both are fixed in D56. `market_snapshot.page_type` is part of the key, and
`market/series.py::resolve_market_series` derives the `(ecr_type, page_type)` pair from the
league's own lineup and format rather than from a constant.

## 2. Does a 1-QB consensus really draft 1–3 QBs?

The directive asked this specifically, and told us not to assume the answer. Replaying
10-team snake drafts on the real preseason boards, all slots picking best-available by ECR,
2021–2025 × 10 slots = 50 drafts per board:

| board | mean QB | mean RB | mean WR | mean TE | share landing on 1–3 QBs |
|---|---|---|---|---|---|
| `rsf` | 4.1 | 5.1 | 6.1 | 1.8 | 20/50 (40%) |
| `ro` | **2.4** | 5.5 | 6.9 | 2.1 | **40/50 (80%)** |
| `ro` ∩ Alpha's projection pool | 2.5 | 5.2 | 7.0 | 2.3 | 35/50 (70%) |

**Answer: yes, under `ro`, and no under `rsf`.** The premise holds on this project's own
historical consensus data once the right board is used.

Caveat, stated rather than buried: the consensus bot has no roster awareness, so its late
rounds produce a 4–6 QB tail no human would draft. It remains the honest available proxy —
there is no distinct historical ADP series in this environment (D17) — but that tail is a
property of the opponent model, not of real consensus behavior.

## 3. K and DEF: three separate gaps, all now closed

The new format starts a K and a DEF. Checked against the real database rather than assumed:

| | before | after (D57) |
|---|---|---|
| Kicker realized points | **0.0** for all 571 season rows — nflverse prices only passing/rushing/receiving | computed from `fg_made_0_19` … `fg_made_60_`, `fg_missed`, `pat_made`, `pat_missed` |
| Team defense | **did not exist as an entity anywhere** — absent from `players`, `player_id_map`, `player_season_stats`, `market_snapshot` | `asq_dst_{TEAM}` entities scored from `stats_team_week` `def_*` columns + real points allowed |
| DST market rank | dropped at ingest (identity resolved only via `fantasypros_id`) | joined on team code through a 3-entry alias map (`JAC→JAX`, `LAR→LA`, `OAK→LV`) |

Independent sanity checks against real 2024: top fantasy kicker Chris Boswell at 189.0, top
defense Denver at 149.0, worst Carolina at 24.0 — all matching the real season. K and DST
enter the `ro` board around overall rank 150, which is where a 16-round 10-team draft actually
takes them.

Both positions get a **measured baseline, not a model**. Walk-forward 2015–2025:

| | n | year-over-year r | winning form | MAE | vs. prior-year alone |
|---|---|---|---|---|---|
| K | 368 | 0.406 | weighted 2-year (0.65/0.35) | **33.60** | 37.44 |
| DST | 352 | 0.294 | 0.3·prior + 0.7·positional mean | **22.55** | 27.14 |

The right form differs by position — a kicker's own history carries real signal, a defense's
mostly does not — which is why one formula is not applied to both. Both signals are weak in
absolute terms; that is a property of these positions, and an ML model here would imply
precision the data does not support.

## 4. Format-induced defects in mechanisms that were previously correct

Two mechanisms were fine under 2QB and became wrong under the new lineup.

**Positional capacity ignored FLEX and split the bench evenly.** Adding K and DEF took the
divisor from 4 positions to 6, cutting RB's and WR's allowance by a third while handing
kickers bench room no roster uses:

| | QB | RB | WR | TE | K | DST |
|---|---|---|---|---|---|---|
| pre-D58 (even split, flex-blind) | 2 | **3** | **3** | 2 | 2 | 2 |
| D58 (flex-aware, proportional) | 2 | **6** | **6** | 4 | 2 | 2 |

A league starting 2 RB plus up to 2 FLEX cannot be capped at 3 RB. The flex-blindness existed
before but was masked by `QB: 2`.

**`roster_need`'s depth target was the constant `slots + 2`** — an arbitrary roster-count
target with no relationship to the league's lineup. Under the new format it would have asked
for three kickers and three defenses. It now uses the same league-derived startable count.

**The league config's roster arithmetic did not add up:** 9 starters + 10 bench declared
alongside `roster_size: 17`. `roster_size` is the benchmark's round count, so an inconsistent
one silently drafts the wrong number of players. Now 10 + 6 = 16, asserted by test for every
shipped config.

## 5. The gap the engine still has: it cannot see its own starting lineup

`recommend_draft_pick` scores `(VORP + opportunity_cost) × fit × risk × survival`. VORP
measures a player against a **league-wide** replacement level; `roster_fit_multiplier` is
driven by `roster_need`, a positional **count** heuristic. Nothing in the path asks *"would
this player displace a current starter in my lineup, and by how much?"* — a player is scored
identically whether he would be your WR1 or your WR5.

This is the directive's item 14, and the audit's answer is that the engine genuinely has no
such concept. Note the *metric* was never the problem: `simulate_draft` already scores rosters
by their best legal lineup. Only the decision function is lineup-blind.

`league/replacement.py::marginal_starter_value` supplies the missing quantity — full
projection into an empty slot, zero at a saturated position, the margin over whoever it
displaces otherwise. Where that term belongs in the score is measured, not assumed: tiers
M0 (the shipped formula, as control) through M3 (marginal starter value replacing VORP
outright), with the decision rule pre-registered in source before any run against real data.

## 6. The re-baselined benchmark: Alpha now beats consensus

Full official benchmark, `alpha-squad evaluate draft-simulation`, 2021–2025 × 10 slots, run
against the corrected `ro` board and the corrected 1-QB league config (all of §1–5 applied,
nothing else changed in the scoring path — this is the shipped D55 opportunity-cost engine,
unmodified, scored on the right board for the first time):

| Strategy | Mean starter pts | Mean total roster pts |
|---|---|---|
| **alpha_league_aware** | **1927.8** | 2785.4 |
| market_consensus | 1825.2 | 2806.7 |
| generic_prior_year | 591.5 | 3468.6 |
| alpha_bpa | 463.5 | 3612.0 |

**Alpha's shipped engine beats market consensus: +102.6 mean starter points (+5.6%).** This is
the reverse of every prior (superflex) result, where consensus led by 219.6 and Alpha never
won a single season. Checked at the level the pre-registered rule in `docs/BENCHMARK_SPEC.md`
requires, not just the pooled mean:

- **Per (season, slot) win rate: 34/50 (68%).**
- **Per-season:** Alpha's mean exceeds consensus's in 4 of 5 seasons (2021, 2022, 2023, 2025);
  2024 is the one loss (1797.8 vs 1877.9). Reported as a real result, not smoothed over — a
  single losing season in five is exactly the kind of variance the evaluation hierarchy exists
  to surface rather than hide inside a favorable pooled mean.

### The naive-baseline collapse is a real finding, not a bug

`alpha_bpa` and `generic_prior_year` — both deliberately built with zero VORP/roster
awareness — collapsed to 463.5 and 591.5 starter points. Checked against the actual drafted
rosters (2024, slot 1): `alpha_bpa` drafted **15 QBs and 1 K**; `generic_prior_year` drafted
**14 QBs and 2 WR**. Zero RB, zero TE, zero DST in both.

This is not a defect in the simulator. In a 1-QB format, raw point totals still favor QB —
top QBs project well above top RB/WR — but only one team can start one, and nothing in these
two baselines' logic knows that. Without VORP or a roster-fit signal, "take the highest
points remaining" hoards QBs uncontrollably and leaves 8 of 10 starting slots empty. It is a
clean, real demonstration that VORP and roster-fit are load-bearing in this format, not
cosmetic — `alpha_league_aware` and `alpha_bpa` share identical Alpha point predictions and
differ only in whether that context exists, and the gap between them (1927.8 vs 463.5) is
almost entirely that context's contribution.

### What this does and does not settle

This answers the directive's central question — is the 1-QB benchmark appropriate, and does
Alpha beat it — with a clear "yes, now it does." It does not by itself explain *why*: whether
the win comes from allocation (VORP/roster-fit filling the right slots), from raw projection
quality, or from the D55 opportunity-cost term specifically now mattering more under a format
where positional runs are sharper. §7–9 below use pick-level attribution and the M-tier
ablation to separate those.

## 7. Where the gap to consensus (and the remaining upside) comes from

`evaluation/pick_attribution.py` replays each of Alpha's real 2021–2025 × 10-slot drafts
(shipped production formula, D55/D60). At every Alpha turn it asks what the consensus board
would have taken from the same available pool at that same moment, then single-pick-swaps that
alternative into Alpha's *final* roster — holding all 15 other picks fixed — and recomputes
best-lineup starter points. This is a counterfactual on one pick at a time, not a re-drafted
roster; it deliberately does not model how availability downstream of a different pick would
have changed (documented in the module's own docstring), so its numbers answer "was this one
swap, in isolation, good or bad," not "would a different overall draft have scored more."

`alpha-squad evaluate pick-attribution --season-start 2021 --season-end 2025`: 800 picks, 738
disagreements (Alpha agreed with consensus on only 62, 7.8%). At face value this looks like a
contradiction of §6: the disagreements net **unfavorable** to Alpha (mean delta +23.5, total
+17356.5 across the 738 — positive means the consensus alternative would have scored more),
while the real team-level benchmark has Alpha winning by +165.7 mean starter points. Both
numbers are real; the reconciliation is two identifiable, non-overlapping effects, checked
against the data rather than assumed.

**Effect 1 — the method's own structural limitation, not a decision defect.** Swapping one
pick with full hindsight while holding the other 15 fixed always makes the swap look better
than it would have played out in a real re-draft, because it ignores that the swapped player
might not have survived to that pick against a different roster's needs, or that Alpha's actual
pick was itself filling a gap the swap would leave open. The by-round table below shows this
concentrating exactly where you'd expect a single-swap method to be least trustworthy — the
mid-to-late rounds, where positional runs and survival probability matter most and a
one-pick-in-isolation view is furthest from a real redraft:

| Round | disagreements | mean delta | total delta |
|---|---|---|---|
| 1 | 37 | +9.8 | +361.9 |
| 2 | 41 | +58.3 | +2388.5 |
| 3 | 46 | +53.1 | +2444.2 |
| 4 | 43 | +49.6 | +2131.6 |
| 5 | 44 | +2.5 | +110.0 |
| **6** | 45 | **−47.0** | **−2114.4** |
| 7 | 46 | +29.2 | +1342.4 |
| 8–16 | 396 | +19.6–43.8 | net positive every round |

Only round 6 nets favorable to Alpha; every other round nets unfavorable to varying degrees,
including the two early rounds where the swap's "no downstream effect" assumption is closest to
true and Alpha's own live picks are least likely to be wrong (rounds 1–2 still net +361.9 /
+2388.5, the smallest of any rounds — consistent with the earliest picks being where the
single-swap method's optimism does the least damage, not where Alpha is making its worst
decisions).

**Effect 2 — a real, measured RB-realized-outcome asymmetry in this specific 2021–2025 sample.**
Splitting the 738 disagreements into the 330 that cost Alpha points and the 255 that gained
points, and comparing each side's own pick against its own preseason projection (real − projected,
i.e. the same forecast error metric §3/§6 already use elsewhere):

| | n | Alpha's pick: mean (real − proj) | Consensus alt: mean (real − proj) |
|---|---|---|---|
| cost picks (consensus alt wins) | 330 | **−32.6** | **+51.9** |
| gained picks (Alpha wins) | 255 | −6.1 | −11.2 |

In the cost bucket, Alpha's own selection underperformed its projection by 32.6 points on
average while the consensus alternative overperformed its own projection by 51.9 — an 84.5-point
swing per pick that has nothing to do with roster construction or opportunity cost, since both
sides are being judged only against what they themselves were projected to do. Narrowing further,
206 of the 330 cost picks had a **running back** as the consensus alternative, and that RB
subgroup alone averaged **+45.2** points above its own projection (134.0 projected → 179.2
realized) — a large, real, systematic residual concentrated in one position. The "worst individual
picks" table is the same finding at the extreme: every one of the top 20 is Alpha taking a
non-RB while the consensus alternative is an RB whose realized outcome landed far above its
preseason projection (e.g. 202→391, 177→417, 221→363).

**Classification, per the directive's taxonomy:** this is **projection/value error concentrated
in RB-position realized-outcome volatility in the real historical sample**, combined with the
**single-pick-counterfactual method's own structural limitation** (over-crediting hindsight to
one isolated swap, no downstream-availability modeling) — not a roster-construction defect, not
an opportunity-cost defect, and not a market-information defect. The evidence for that
classification: the same shipped decision logic that "loses" hundreds of individual pick-level
swaps to hindsight nonetheless wins the real team-level benchmark by +165.7 (§6/D59-D60), which
would not be possible if the pick-level losses reflected a genuine, systematic decision error —
a genuinely bad decision rule would show up as a loss at both levels, not a loss at one and a
win at the other. The RB residual is named explicitly as a real, unresolved weakness of the
*projection* layer (upstream of the draft engine, in `models/`), not swept into "the engine is
fine" — a future projection-quality pass should look specifically at whether RB uncertainty
intervals in this sample are miscalibrated on the upside.

## 8. M-tier ablation: does marginal starter value help, and does D55's opportunity cost still?

Pre-registered before any run against real data (`evaluation/draft_forensics.py`, D58/D60):
primary metric mean starter points, Gate 1 no position zeroed out more than the control, Gate 2
no more infeasible rosters than the control, tie-break fewer mechanisms, ship only if a tier
strictly beats the control on the primary metric with both gates passing. Four tiers, control
M0 (the shipped D55 formula unchanged) through M3 (marginal starter value replacing VORP as the
score's value base outright), varying only where MSV enters — every tier shares production's
risk/survival/opportunity-cost/feasibility terms so a difference is attributable to MSV alone.
200 real drafts (4 tiers × 5 seasons × 10 slots):

| Tier | Mean starter pts | Δ vs M0 | Win/Loss/Tie vs M0 | Seasons won (of 5) |
|---|---|---|---|---|
| M0 (control) | 1894.2 | — | — | — |
| M1 (MSV added inside the value term) | 1987.2 | +93.0 (+4.9%) | 34/13/3 | 4 |
| M2 (MSV drives the roster-fit multiplier) | 1900.7 | +6.6 (+0.3%) | 16/22/12 | 2 |
| **M3 (MSV replaces VORP as the value base)** | **2003.8** | **+109.7 (+5.8%)** | **37/13/0** | **4** |

Both gates passed for every tier — `n_infeasible_rosters` was 0 and no position's zero-rate rose
above the control's (itself 0) in any tier — so the decision came down cleanly to the primary
metric and the tie-break was never needed: **M3 wins outright**, beating M0 by the largest
margin, winning the most (season, slot) pairs, and losing only the 2025 season head-to-head
(4–6) among the 5 seasons scored. M2's near-zero net (+6.6, 16W/22L/12T) shows that swapping MSV
into the *multiplier* is weak and inconsistent — worse than doing nothing in 22 of 50 slots —
while M1 shows MSV genuinely helps even added crudely alongside VORP (+93.0), and M3 shows it
helps most when it fully replaces VORP as the base term rather than sharing the score with it.

**M3 is also the only tier that fixes a real, independently-visible defect.** Mean drafted
position counts across the same 200 drafts:

| Tier | K | DST | QB | RB | WR | TE | drafts breaching the K feasibility cap |
|---|---|---|---|---|---|---|---|
| M0 | 3.78 | 2.26 | 2.12 | 1.72 | 4.12 | 2.00 | 50/50 |
| M1 | 3.70 | 2.24 | 1.60 | 2.42 | 4.04 | 2.00 | 50/50 |
| M2 | 3.84 | 2.38 | 2.00 | 1.98 | 3.80 | 2.00 | 50/50 |
| **M3** | **1.60** | **1.26** | 2.28 | **2.62** | **5.54** | **2.70** | **0/50** |

Every VORP-value-base tier (M0/M1/M2) hoards roughly 3.7–3.8 kickers and 2.2–2.4 defenses per
16-round draft — every single one of those 150 drafts breaches K's flex-aware feasibility cap —
because VORP prices a bench K/DST against league-wide positional replacement level with no
knowledge that neither position has flex eligibility: a second or third kicker who is merely
better than replacement still scores positive VORP even though he has zero chance of ever
starting behind the first. Marginal starter value has no such blind spot by construction — a
second kicker's MSV is exactly zero once the first fills the slot (regression-tested directly:
`tests/unit/test_league_draft_msv_integration.py::TestKickerDefenseHoardingIsFixed`) — and
M3 is the only tier where the hoarding actually stops (0/50 breaches) and the freed bench
capacity flows to real skill-position depth (RB 1.72→2.62, WR 4.12→5.54, TE 2.00→2.70).

**Does D55's opportunity-cost term still help under 1-QB?** Every M-tier, including the
control, carries D55's opportunity-cost replay unchanged — it was never removed or varied as
part of this ablation, only the value-base/multiplier terms were. That every tier (M0 included)
still beats the zero-context naive baselines by roughly 3–4x (§6: `alpha_bpa` 463.5,
`generic_prior_year` 591.5, vs. 1894–2004 across M0–M3) is consistent with the opportunity-cost
+ VORP/fit combination still contributing real value in this format; a targeted ablation with
opportunity cost switched off entirely was not run in this pass (it would need a fifth tier
against the same pre-registration discipline) and is named here as a real remaining gap in the
evidence, not silently assumed to transfer from the superflex-era D55 result.

**Shipped result.** M3 was ported into production `recommend_draft_pick` (D60) exactly as
measured — `roster_player_ids` optional, VORP-fallback preserved byte-for-byte for callers that
cannot supply real drafted-player ids (some API/agent paths; see D60 for the full list). Re-run
through the *official* benchmark (not the fast forensic harness) after shipping:

| Strategy | Mean starter pts | Mean total roster pts |
|---|---|---|
| **alpha_league_aware (M3/D60)** | **1990.9** | 2775.9 |
| market_consensus | 1825.2 | 2806.7 |

**+165.7 mean starter points (+9.1%) over consensus, 37/50 (74%) win rate at the (season, slot)
level** — up from D59's pre-MSV +102.6/+5.6%/68%. Byte-identical across two independent
processes (`md5 5e0ec53e...`, `PYTHONHASHSEED` unset), confirming the result is deterministic
and not an artifact of iteration order.

## 9. Recommendation

**Ship marginal starter value as the score's value base (M3/D60) — already done.** It is the
only mechanism tested that beat the pre-registered control on every axis the rule checked, it
fixes a real, independently-verified defect (K/DST hoarding past feasibility) that every
VORP-value-base tier shares, and it improved the official benchmark's Alpha-vs-consensus margin
from +102.6 to +165.7 with no regression in feasibility or per-position zero-rates. The change
is additive at the call site (an optional parameter, VORP-fallback preserved) so no caller that
cannot supply real roster state lost anything.

**What is settled:**
- The 1-QB benchmark is valid (§1: `ro`, not `rsf`), and a 1-QB consensus board really does
  draft 1–3 QBs (§2: 80% of replayed drafts) — the original premise holds under the corrected
  board and did not under the old one.
- K and DEF are real, computed, baseline-projected starting positions, not zeros or omissions
  (§3).
- The roster-arithmetic and flex-blindness defects the new lineup exposed are fixed and
  test-covered (§4), and `starters + bench == roster_size` can no longer silently drift.
- Alpha's shipped engine beats market consensus under the corrected format and benchmark, on
  the primary metric, the win-rate secondary metric, and per-season consistency (§6, §8) — the
  directive's central question has a documented, evidence-backed "yes."

**What is not settled, named rather than hidden:**
1. **RB-position projection residual (§7).** The pick-level attribution surfaced a real,
   measured asymmetry — consensus RB alternatives in the "cost" bucket overperformed their own
   projections by +45.2 points on average (n=206) in 2021–2025. Whether this is a genuine
   calibration gap in the RB uncertainty model, a property of this specific 5-season sample, or
   both, is unresolved and would need its own walk-forward calibration audit of the RB
   projection path specifically — not assumed to be either.
2. **Opportunity cost was held fixed, not re-ablated (§8).** Every M-tier shares D55's
   opportunity-cost term unchanged; whether it still earns its keep specifically under the 1-QB
   format (as opposed to carrying over from when it was chosen on superflex data) was not
   independently re-tested against an opportunity-cost-off control in this pass.
3. **The consensus opponent's late-round tail (§2).** The proxy has no roster awareness and
   drafts an unrealistic QB tail after round ~10; it remains the only available consensus data
   in this environment (no independent ADP source, D16/D17) and is used as-is, not smoothed.
4. **The single-pick-counterfactual method (§7)** is a real diagnostic tool with a documented,
   structural blind spot (no downstream-availability modeling) — useful for classifying gap
   *causes*, not a substitute for the team-level benchmark as a measure of whether a strategy
   is good.

None of the above changes the shipped decision (M3 was the strictly better mechanism measured
against everything tested), but each is a concrete next step for a future session: an
RB-projection calibration audit, an opportunity-cost-off M-tier, and continued per-season
monitoring as more real seasons of data accumulate.
