# W2 — Pre-registration: the ECR-alone weekly benchmark and the noise floor

**Status: PRE-REGISTERED, NOT EXECUTED.** Committed before any weekly ranking metric has been
computed for any system. At the time of writing, no comparative weekly result exists anywhere in
this repository — W1 measured data availability only and deliberately ran no comparison.

Authority: `docs/weekly/W1_FOUNDATION_AUDIT.md` (the audit this rests on), `CLAUDE.md`,
`PRODUCT_SPEC.md`. Decision record: `docs/DECISIONS.md` D109.

> **Changing anything below after seeing a result requires an explicit, dated amendment in this
> file stating what changed and why it was necessary.** This is the rule D70's pre-registration
> stated and honoured when its own gates failed, and the rule D106 followed. It is not optional.

---

## 1. The question, and why it is this one

> **How strong is the ECR-alone weekly benchmark, and what is the noise floor of the primary
> comparison?**

W2 measures **one system**: ECR alone. It builds no Alpha model, runs no comparison and
declares no winner. Those are W3.

**Why.** Without a noise floor, no later comparison is interpretable — a Δρ of 0.01 is either
decisive or meaningless depending on a number nobody has computed. The draft program's most
useful single quantity turned out to be its 172–250 point detection floor, and it was computed
*late*, after phases had been spent on effects that sat below it (D108 §4.1). W2 pays that cost
first. Measuring ECR alone also cannot be tuned toward a result, because no Alpha system is
touched.

**This is not a metric-fishing phase.** The metric suite is fixed in §8 below, before any of it
is computed.

---

## 2. Hypotheses and decision rules, fixed now

W2 is primarily descriptive, but it has two pre-registered decision rules whose outcomes change
what W3 is allowed to be.

**R1 — Is the instrument usable at all?**

| outcome | criterion | consequence |
|---|---|---|
| **usable** | the primary metric's per-week paired SD yields an MDE (§9) that is **smaller than the ECR-vs-trivial-baseline gap** (§7.2) | W3 proceeds as designed |
| **underpowered** | the MDE is **larger** than that gap | W3 may not run a three-system comparison on this instrument; the phase becomes "find a more sensitive instrument or more weeks" |

Rationale: if the instrument cannot even resolve the distance between ECR and a trivial
baseline, it certainly cannot resolve ECR vs Alpha, and running that comparison would generate a
null that means nothing.

**R2 — Is ECR's strength depth-uniform?**

| outcome | criterion | consequence |
|---|---|---|
| **uniform** | ECR's advantage over the trivial baseline, expressed in per-depth MDE units, varies by **< 2×** across k ∈ {10, 25, 50, full} | W3 targets overall ranking quality |
| **depth-dependent** | it varies by **≥ 2×** | W3 must target the depth where the headroom is, and say so explicitly |

Rationale: the brief's warning that top-10 performance does not represent the product. 2× is
chosen as the threshold because it is the point at which a single pooled number stops describing
both ends of the board — it is a judgement, fixed here rather than after seeing the spread.

**There is no hypothesis of the form "ECR is good" or "ECR is beatable".** W1's standing
instruction applies: do not assume Alpha should beat ECR; do not assume it should lose.

---

## 3. Population

| | |
|---|---|
| **seasons** | **2021, 2022, 2023, 2024, 2025** |
| **excluded** | **2020** (partial coverage, weeks 6–16 only, and 10 of its 11 boards are Thursday vintages — a different information set); **2026** (in progress; the draft program's standing prohibition on using 2026 applies for the same reason) |
| **weeks** | the **79** REG weeks with a canonical board (W1 §4.3): 2021 w1–17 · 2022 w2–17 · 2023 w2–17 · 2024 w4–17 · 2025 w2–17 |
| **never** | week 18 (no board in any season, and not a fantasy week); postseason |

The covered-week list is **fixed by this document**. A week missing from it is out of scope and
may not be filled by substituting another vintage. A week present in it may not be dropped after
the fact without an amendment.

---

## 4. Snapshot and cutoff

**One snapshot per week: the canonical Friday board** — the latest weekly board strictly before
that week's first Sunday game, within a 7-day lead window
(`evaluation/weekly/snapshots.py::canonical_snapshots`).

**Cutoff rule.** A system may use only information whose timestamp is at or before the snapshot
date. Concretely, at the week-*w* cutoff:

| allowed | forbidden |
|---|---|
| all player-weeks in seasons < *S*, and weeks < *w* of season *S* | any week-*w* outcome |
| the week-*w* schedule and opponent | week-*w* snaps, stats, or team scores |
| injury rows with `date_modified <= cutoff` | injury rows modified after the cutoff |
| the week-*w* canonical ECR board | any later ECR vintage, including a revision |
| depth chart / roster for week *w* (assumption-flagged, W1 §6.2) | `games.csv` spread/total/moneyline (untimestamped, effectively closing) |
| | `games.csv` temp/wind (realized game conditions) |

The daily Tue–Sun cadence is **out of scope for historical evaluation**, for the two independent
reasons in W1 §3.1 (ECR has one vintage per week; the injury file cannot be rewound past its
last edit without introducing a healthiness bias). It remains a forward-only product capability.

---

## 5. Player eligibility — the universe

Applied in this order, identically for every system, because it defines the *question* and not
any system's answer:

1. Start from the week's canonical board for the relevant series.
2. **Drop every player whose week-*w* game kicked off before the snapshot date** (the
   Thursday-night rule — W1 §4.6: 78 of 90 boards carry such rows, 6.0% of rows).
3. Drop rows that do not resolve to a canonical `player_id` (W1 §4.7: <1%, ~0% in the top 24).
   DST resolves by team code through `FANTASYPROS_TEAM_ALIASES`, never by name.
4. For FLEX: drop QB rows (and any stray non-RB/WR/TE row).
5. Re-rank the survivors densely, 1..N, ties broken by `player_id` for determinism.

**Invalid-cell rule.** A (season, week, position) cell is **invalid and excluded** if, after the
above, it has **fewer than 10 ranked players with a realized outcome**. Invalid cells are
reported by count and never silently dropped. The threshold is fixed here, before any cell has
been counted.

---

## 6. Ground truth and scoring

`points(r) = fantasy_points_ppr − (1 − r) × receptions`, verified as an exact identity over
stored columns (W1 §5.1: max abs diff 0.0 across 5,864 player-weeks; two independent half-PPR
routes agree to 0.0).

| format | r | role in W2 |
|---|---|---|
| **Full PPR** | 1.0 | **primary** — the only format with an ECR benchmark |
| **Half PPR** | 0.5 | **secondary** — reported for the same boards, labelled explicitly as *scored against a full-PPR-ranked board*; never called "the Half-PPR ECR benchmark" |

A player with no `player_week_stats` row **did not play**. He is absent, never imputed to 0.0.
This is what keeps §10's two evaluation concepts separable.

Positions: QB, RB, WR, TE, K, DST. No IDP. K and DST ground truth is computed
(`features/kicking_defense.py`) and requires `make features` to have run in the D78 order.

FLEX = **RB, WR, TE**.

---

## 7. Systems measured in W2

### 7.1 ECR-alone (the object of study)

The canonical Friday board, as constructed in §5. Per position (QB/RB/WR/TE/K/DST) from the
dedicated weekly series, and FLEX reconstructed from `wsf/weekly-op` with QBs removed
(W1 §4.5 — a superflex board, with measured within-position support and an unverified
cross-position calibration).

### 7.2 Two reference baselines (to give ECR's strength a scale)

ECR's metric values mean nothing in isolation. Two deliberately simple, fully-specified
references bracket them. **Neither is "Alpha".** Both are fixed here:

| ref | definition |
|---|---|
| **B0 — trivial** | rank by the player's **season-to-date PPG through week *w*−1**; players with no prior game in season *S* rank last, ties by `player_id`. Uses only the most obvious information a user already has. |
| **B1 — prior-season** | rank by **season *S*−1 PPG**; no *S*−1 games ⇒ last. A pure no-current-information reference. |

Their role is the denominator in R1 and R2: "how much better is ECR than the obvious thing", in
units the noise floor can be compared against. They are not candidates for the product and no
claim of the form "Alpha beat B0" will be made in any later phase.

**Not in W2:** any Alpha model, any ECR-as-a-feature system, any fitted model of any kind.

---

## 8. Metric suite — fixed before any computation

Computed per (season, week, position) and per (season, week, FLEX), then aggregated **over
weeks**, never pooled over player-weeks (§9).

| # | metric | definition | user need |
|---|---|---|---|
| M1 | **Spearman ρ** | predicted rank vs realized-points rank, active players | "is the list ordered sensibly at all" |
| M2 | **NDCG@k**, k ∈ {10, 25, 50} | gain = realized points, clipped at 0 | "the top of the list is what I act on" |
| M3 | **Top-k hit rate**, k ∈ {10, 25, 50} | \|predicted top-k ∩ realized top-k\| / k | "did it find the right players to consider" |
| M4 | **Pairwise ordering accuracy** | share of correctly-ordered active pairs | ordering, unweighted |
| M5 | **Decisive-pair accuracy** | M4 restricted to pairs with realized \|Δpoints\| ≥ 3.0 | **"which of these two do I start"** — the literal act |
| M6 | **MAE / RMSE** | vs realized points, active only | supporting diagnostic; required for cross-position FLEX comparability |
| M7 | **Decile calibration** | mean predicted vs mean realized by predicted decile | "16.8 should mean 16.8" |

**M1–M5 are ranking metrics; M6–M7 are diagnostics.** Ranking quality is the primary product
objective (brief §3); point accuracy is a supporting measure and will not be reported as if it
were the product.

**ECR has no point prediction**, so M6/M7 are computed for B0/B1 and for later Alpha systems
only; for ECR they are recorded as N/A rather than manufactured from a rank-to-points map. Doing
otherwise would invent a quantity ECR does not publish.

**The 3.0-point threshold in M5** is fixed now as roughly the scale at which a fantasy manager's
start/sit choice stops being a coin flip. It is a judgement; it is pre-registered rather than
chosen after seeing which threshold flatters anything.

**No composite score.** A system strong at the top and one strong deep serve different products
(shallow-league start/sit vs waiver research). Collapsing them destroys the distinction before it
is measured (brief; and D101's finding that projection metrics are not monotone in each other).

---

## 9. Aggregation, statistics and the noise floor

**The unit of replication is the week (n = 79), not the player-week.** Player-weeks within a
week share the slate, the injury news, the weather and the same ECR vintage; treating ~30,000
player-weeks as independent would overstate precision by roughly an order of magnitude and is
the single most likely way to manufacture a false result in this program.

- Each metric is computed **within** a (season, week, position/FLEX) cell.
- Systems are compared **paired within week** (same week, same universe, both systems).
- Reported: mean of the per-week paired difference, its SD, and a **95% bootstrap CI over weeks**
  (10,000 resamples, seeds **0–9** fixed here, resampling **weeks** as the unit).
- Seasons are reported separately as well as pooled, because a result that only exists in one
  season is a season effect (the draft program's D91 found exactly that: 94% of an effect in one
  season).

**Noise floor / MDE.** For each primary metric: MDE = the smallest per-week mean paired
difference that the 95% bootstrap CI over 79 weeks would exclude zero for, given the observed
per-week paired SD. Computed in W2 **from ECR vs B0/B1 only** — no Alpha system is involved, so
the floor cannot be tuned.

**Minimum meaningful effect.** Deliberately **not fixed as a number now.** W1 §12 (U4) states
why: the per-week variance does not yet exist, and inventing a threshold from nothing would
manufacture precision the data has not supplied. W2's own output is what makes it stateable, and
the **amendment that sets it must be committed before W3 runs any comparison.** Stating it here
as a placeholder would be worse than leaving it open.

**Stopping rule.** W2 computes the suite over all 79 weeks exactly once. There is no interim
look, no early stop, and no re-run with a changed universe. If a bug is found, the fix and the
re-run are recorded as an amendment with the reason.

---

## 10. Production forecast vs availability

Kept separate (W1 §8; brief §9). W2 reports both, never a product of the two.

- **A — production forecast.** All metrics in §8, computed **only over players who played**.
- **B — availability.** Per week and depth band, the share of ranked players with a realized row
  (W1 measured 72.6% for the 2024 FLEX universe). W2 **reports this descriptively and does not
  select an availability metric** — selecting one is a W3 pre-registration item, because it only
  becomes a modelling target once a system exists that predicts it.

Rationale for not multiplying: injury already enters production through workload, snaps, role and
efficiency; multiplying by P(play) double-counts it.

---

## 11. Leakage protections

1. Universe constructed by `evaluation/weekly/snapshots.py`, whose rules are pinned by
   `tests/leakage/test_weekly_snapshot_cutoff.py` (15 adversarial tests).
2. Already-played exclusion applied **before ranking**, not at scoring time — a test asserts the
   distinction, because applying it after leaves every depth cutoff contaminated.
3. Only the canonical board vintage is read; a later revision is never substituted.
4. Injury rows filtered on `date_modified <= cutoff`.
5. Class-D sources (Vegas, weather, week-*w* stats/snaps) are not read by any W2 code path.
6. The existing `player_week_features` panel's window frames already exclude the current and
   future rows, pinned by `tests/leakage/test_player_week_features_leakage.py`.
7. Source vintages hashed and recorded in the run's JSON output.

---

## 12. Reproducibility

| | |
|---|---|
| runner | `scripts/research/w2_ecr_baseline.py` (to be written by W2) |
| instruments | `src/alpha_squad/evaluation/weekly/` |
| base commit | the W1 commit on `claude/dreamy-albattani-efvroj` |
| ECR vintage | **must be re-hashed and compared against** `e270d790165a6c304e5854145332fe9da3caacab3a61e1efea280b57cc5db9a5`; a mismatch is reported, not silently accepted |
| immutability | **unverified for the weekly series.** D92 established it for the *draft* series only. W2 must check whether historical weekly rows change between vintages, and say so. |
| dependencies | no update as part of W2 |
| gates | `make test`, `make lint` (both halves — D108 §3) |

---

## 13. What W2 may NOT do

- Build, fit or tune any Alpha weekly model.
- Run any three-system comparison.
- Change production code: `models/`, `league/`, `api/`, `cli.py`, configs, `market/consensus.py`.
- Add a metric after seeing a result, or drop one that looks unflattering.
- Fill a missing week with another vintage.
- Quote the draft program's **172–250 detection floor** — a different instrument entirely
  (W1 §10.3).
- Declare Alpha better or worse than ECR at anything.

---

## 14. Amendments

### A1 — 2026-09-19, before execution: the FLEX and Half-PPR findings are corrected at source

**Trigger.** W1.1 re-investigated W1's claim that "no 1-QB weekly overall/FLEX board exists"
and found it was a statement about the **DynastyProcess mirror**, not about FantasyPros.
FantasyPros publishes a regular weekly FLEX board and serves it historically through its
official API, which this repository has a configured key for and had never queried for weekly
rankings. Full audit: `docs/weekly/W11_FANTASYPROS_FLEX_AUDIT.md`.

**This amendment is written before any W2 metric has been computed.** No result influenced it.

**What changes:**

1. **§7.1 gains a second, independent ECR artifact.** The FLEX benchmark is now measured two
   ways, and they are never pooled because their vintages differ:

   | | primary (depth) | validation (truth) |
   |---|---|---|
   | source | DynastyProcess `db_fpecr` mirror | FantasyPros API `position=FLX` |
   | board | **reconstructed** — superflex minus QBs | the **real** published FLEX board |
   | vintage | **Friday** (pre-Sunday, post-TNF) | **Sunday ~12:59 ET**, frozen at kickoff |
   | depth | full board (300–450 players) | **top 10 only** (`public_api_limited`, `limit=10`) |
   | coverage | 79 weeks, 2021–2025 | 18 weeks (2021) + spot weeks; quota-limited |

2. **A new pre-registered analysis: reconstruction validation.** Before the headline benchmark
   is interpreted, measure how closely the mirror reconstruction's top 10 matches the real
   FLEX top 10, on the weeks where both exist. Decision rule, fixed now:

   | outcome | criterion | consequence |
   |---|---|---|
   | **reconstruction sound** | median top-10 overlap **≥ 0.70** | full-depth results stand as FLEX results |
   | **reconstruction weak** | median overlap **< 0.70** | full-depth results are reported as a **superflex-derived proxy**, not as FLEX, and the FLEX claim is restricted to top-10 |

   0.70 is fixed here, before measurement. It is chosen as the point at which 7 of 10 names
   agree — below that the two boards are describing meaningfully different player sets.
   **The comparison confounds two things** (reconstruction error and a two-day vintage gap) and
   cannot separate them at scale; the single week where the API served both `FLX` and `OP`
   (2023 wk8, both scorings) isolates the reconstruction component alone and is reported
   separately as a one-week sanity bound, never as an estimate.

3. **§6's Half-PPR status changes from "does not exist" to "exists, not accessible at depth".**
   FantasyPros serves `scoring=HALF` historically for every position and for FLEX. The
   configured key returns only the top 10, so a full-depth Half-PPR benchmark remains
   unavailable — a **licensing/tier** limit, not a data-availability one. Half-PPR stays
   secondary for W2, and no Half-PPR ECR is approximated from Full-PPR.

4. **§7.2's reference baselines are unchanged** (B0 season-to-date PPG, B1 prior-season PPG),
   and remain the scale against which ECR's strength and the noise floor are read.

**What does NOT change:** the population (§3, 79 weeks, 2021–2025), the Friday cutoff for the
primary benchmark (§4), the universe rules (§5), the ground truth (§6), the metric suite (§8,
already frozen in `evaluation/weekly/metrics.py` with hand-computed tests), the aggregation and
noise-floor method (§9), and every prohibition in §13.

**Access-control note.** The 10-row cap and the request quota are access controls on a paid
third-party API. They are reported as limits, not worked around; no scraping of FantasyPros web
pages was performed or will be (CLAUDE.md: "Never bypass access controls").

