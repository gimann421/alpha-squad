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

<!-- SECTIONS 6-9 ARE FILLED FROM MEASURED RUNS AND ARE APPENDED BELOW. -->
