# W8 — Pre-registration: where does ECR's top-of-board advantage come from?

**Status: PRE-REGISTERED, NOT EXECUTED.** Committed before any ECR-vs-Alpha decomposition, bucket
comparison, pair comparison or counterfactual was computed. The audit in §2 records **coverage
facts only**. No quantity comparing ECR with Alpha was computed to write it.

Authority: `docs/weekly/W5_TOPBOARD_FORENSICS.md` (§17 usage/conversion split, exact regret),
`docs/weekly/W7_OPPORTUNITY_RESULTS.md` (the Class A opportunity forecast), `CLAUDE.md`. Decision
record: `docs/DECISIONS.md` D116.

> **No change below after seeing results without a dated amendment here.**

---

## 1. The question

The fact that ECR beats Alpha at the top of the board is already established (W2–W7). It is
**not** re-asked here. On positional capture@10:

| | RB | WR | TE |
|---|---:|---:|---:|
| ECR lead over Alpha | +0.023 | +0.032 | +0.026 |

The W8 question:

> **In the player-weeks where ECR does better than Alpha, what kind of mistake is ECR avoiding?**

There are three candidate answers.

**A. Information.** ECR anticipates this week's **opportunity** better than any provably-pre-Friday
information can. Examples: late injury and practice news, role changes, depth-chart moves.

**B. Efficiency.** ECR does not know more about opportunity. It is better at anticipating which
players will turn their opportunity into unusually many or few points.

**W.** A third answer, pre-registered because the decomposition in §5 exposes it. ECR's top of the
board carries more **forecastable** opportunity. Alpha had that information but weighted it
worse. This is neither A nor B, and it is reported separately so it cannot be mistaken for
either.

This is a **diagnostic association**, not a causal claim. **ECR is an instrument here, never a
feature.** It trains, calibrates, tunes and selects nothing.

---

## 2. Audit — facts established before any comparison

### 2.1 Reproduction first

W5, W6 (with its board-agreement file) and W7 are re-run from their committed instruments and
diffed against their committed results before any W8 quantity is computed. If any of them fails
to reproduce, W8 stops. The results are recorded in the results document §0.

### 2.2 The established definitions W8 reuses — nothing is invented

| quantity | definition | established in |
|---|---|---|
| **usage-expected points** `x` | ffopportunity `total_fantasy_points_exp` for the week; Half-PPR subtracts `0.5 × receptions_exp` | W5 §17 (`ORACLE_USAGE`), `context.load_usage_points` |
| **conversion** `c` | `pts − x`: points scored beyond what the usage was worth ("touchdowns and efficiency") | W5 §17 |
| **Class A opportunity forecast** `f` | W7's primary forecast `M_NEW` of `T_XFP`: ridge on Alpha's 11 features plus the 9 Class A features, walk-forward `[2015, S−1]`. Half-PPR uses W7's `T_XFP_HALF`. | W7 §3, `opportunity.walk_forward` |
| **opportunity surprise** `s` | `x − f`: the part of this week's opportunity that provably-pre-Friday information did not forecast | this phase; follows directly from the two rows above |
| **exact per-player regret** | `pts_i × (1[i in board A's top-k] − 1[i in board B's top-k])` sums **exactly** to the capture difference | W5 `regret.py` |
| **the evaluated universe, cutoff, ECR series, FLEX board** | unchanged from W3–W7 | W2–W7 |

### 2.3 Coverage — measured

There is **no usage row for 520 RB / 933 WR / 449 TE** evaluated player-weeks (8.8–9.9%).
**Every one of them has exactly zero targets and zero carries.** The same holds for all 5,957
such rows in the full 2015–2025 panel. Their mean realized score is 0.00–0.06 points.

ffopportunity simply publishes no row for a player with no opportunity. For these rows, **`x = 0`
is the recorded fact, not an imputation.** A validity gate (G8) re-verifies it on every run.

In the top-of-board region (§4), uncovered rows number 1 (RB), 3 (WR) and 13 (TE). All are
zero-opportunity weeks.

---

## 3. The decomposition

For every evaluated player-week `i`:

    pts_i = x_i + c_i = f_i + s_i + c_i

Top-k points capture is `Σ_{i in top-k} pts_i / D_k`, where `D_k` is the best possible top-k
total and is identical for every board in a week. So the ECR-minus-Alpha capture gap splits
**exactly** into three pieces:

    G  = capture_ECR − capture_ALPHA
       = G_F + G_S + G_C,

    G_F = (Σ_{ECR top-k} f − Σ_{ALPHA top-k} f) / D_k   ECR's top holds more forecastable opportunity   -> W
    G_S = (Σ_{ECR top-k} s − Σ_{ALPHA top-k} s) / D_k   ECR's top got more unforecast opportunity       -> A
    G_C = (Σ_{ECR top-k} c − Σ_{ALPHA top-k} c) / D_k   ECR's top converted opportunity better          -> B

Only players in one board's top-k and not the other's contribute. The identity holds to floating
point in every week, and that is a gate (G8), not an assumption.

**Why `G_S` is the information piece and `G_F` is not.** `f` uses only information that provably
existed before Friday, and W7 showed Alpha already holds 84–86% of it. If ECR's top-k has more
*forecastable* opportunity, Alpha could have seen it. Only opportunity that **no** provably
pre-Friday information forecast can indicate information Alpha does not have.

**The luck caveat.** `s` and `c` also contain pure chance: in-game injuries, game script,
touchdown variance. Chance is independent of which board ranked a player where. It widens the
weekly spread of `G_S` and `G_C` but does not shift their means. A component whose CI excludes
zero is therefore evidence of anticipation, not luck.

---

## 4. Scope

| | |
|---|---|
| positions | **RB and WR primary**; TE is the comparison group (W5 found no cliff there); FLEX in §9 |
| **top-of-board region** | players ranked in the **top 20 on either** Alpha's or ECR's positional board. The selection uses pre-game ranks only, never outcomes |
| depths | capture decomposition at **k = 5, 10, 20**, **primary k = 10**. FLEX at 10 and 25 |
| scoring | Full PPR primary; Half-PPR replication only |
| weeks | the same 79 weeks, 2021–2025, the same Friday cutoff, universe and ECR series as W3–W7 |

---

## 5. Buckets and pair types — fixed now

### 5.1 Opportunity surprise, per player-week

**Thresholds.** Terciles of `|s|` computed **per position** over all top-region player-weeks
pooled across the 79 weeks. These are computed from `s` alone, never from any board comparison.

**Primary buckets:**

- **CLOSE:** `|s|` in the bottom tercile.
- **MODERATE:** `|s|` in the middle tercile.
- **LARGE:** `|s|` in the top tercile.

**Signed:** LARGE is split into **LARGE_UP** (`s > 0`) and **LARGE_DOWN** (`s < 0`).

### 5.2 Efficiency surprise, per player-week

Terciles of `c` per position, over the same pooled top-region player-weeks: **LOW / MID / HIGH**.

`c` is conversion relative to league-average conversion of that usage, which is what `x`
encodes. No player-specific "expected conversion" exists in W5 or W7, and none is invented.

### 5.3 Pair types for pairwise accuracy

All pairs are taken within the top region. A pair counts only if the two realized scores differ,
which is `metrics.pairwise_accuracy`'s existing rule.

| type | definition | what it isolates |
|---|---|---|
| **CLOSE** | **both** players' opportunity was CLOSE to forecast | the brief's §8 efficiency test: neither player's usage surprised |
| **SURPRISE** | **at least one** player's surprise was LARGE | the pairs where unforecast opportunity could decide the order |
| **MATCHED** | the two players' **realized** usage-expected points differ by no more than the bottom tercile of `|x_i − x_j|` over all top-region pairs (per position, pooled) | the order is decided by conversion; **perfect opportunity knowledge could not help here** |

---

## 6. Instruments

**P1 — the capture decomposition (§3).** `G`, `G_F`, `G_S` and `G_C` per week at k = 5, 10 and
20, each averaged over weeks with a bootstrap CI. Shares are point estimates (`G_S / G`, etc.),
with a descriptive bootstrap CI of the ratio of means.

**P2 — top-region pairwise accuracy by pair type.** For each pair type, ECR's accuracy minus
Alpha's, per week:

- `Ω`: all pairs
- `Ω_close`
- `Ω_surp`
- `Ω_match`
- `Ω_surp − Ω_close`: a per-week difference

A week with no pair of a type drops out of that statistic only.

**P3 — what ECR's disagreements anticipate (supporting, not in the verdict).** In the region,
`d_i = rank_ALPHA,i − rank_ECR,i` (positive means ECR likes the player more). Per week, compute
the Spearman correlation of `d` with each of `s`, `c` and `f`.

- If ECR's upgrades get more unforecast usage, `ρ(d, s) > 0`.
- If they convert better, `ρ(d, c) > 0`.
- If they carry more forecastable usage, `ρ(d, f) > 0`.

**Bucket tables (§4/§6 of the brief; descriptive).** For each opportunity bucket, signed bucket
and efficiency bucket:

- (a) the exact capture@10 and capture@20 attribution: the part of `G` carried by that bucket's
  players; the buckets sum to `G`.
- (b) per-player-week pairwise concordance, ECR minus Alpha. This is the share of that player's
  region pairs each board orders correctly, averaged within the bucket per week, then over weeks.
- (c) each board's own concordance.

Each bucket's share of `G` is shown next to its share of the swapped players, so over- and
under-representation are visible.

**The counterfactual (§7 of the brief).** Four boards:

- **A** — `CF_A`, current Alpha.
- **B** — `ALPHA_ORACLE_OPP`: production's CatBoost, hyperparameters, MAE loss and walk-forward,
  plus one added feature, the week's own realized `x`. This is Class D, a diagnostic ceiling and
  never deployable.
- **B₀** — W5's `ORACLE_USAGE`, for reference.
- **C** — ECR.

Metrics are capture@5, @10 and @20 and Spearman. Reported contrasts: B−A, C−A, C−B, and
`(B−A)/(C−A)`.

**How B is read — fixed now, because the naive reading is biased.** B knows every player's usage
surprise, including in-game injuries and game script that nobody knows on Friday. W5 measured
that knowledge at +0.18 to +0.20 capture@10 over Alpha, **six to eight times ECR's entire lead**.
So B will close the ECR gap *whether or not* ECR's lead has anything to do with opportunity, and
"the gap disappears under perfect opportunity" would be read into it regardless of the truth.

**B is therefore reported, but it does not enter the verdict.** The brief's question — how much of
ECR's lead would survive if Alpha knew the opportunity — is answered directly by:

- **`G_C`:** the part of the capture gap that is not opportunity at all.
- **`Ω_match`:** ECR's edge on pairs where realized opportunity was equal, which is exactly where
  perfect opportunity knowledge cannot help.

**Player-level analysis (§9 of the brief; descriptive, no inference claimed).** For each
(player, season, position) with at least 4 top-region weeks, take the mean disagreement `d`.

- **ECR-FAVORED:** the top decile of mean `d` within the position.
- **ALPHA-FAVORED:** the bottom decile.

The two groups are compared on:

- mean `s`, `c` and `f`
- recent usage (`targets_avg_last3 + carries_avg_last3`)
- history (`games_played_prior`)
- role stability (`opp_sd_last3`)
- team environment (`team_plays_avg_last3`, `team_pass_rate_avg_last3`, `team_epa_avg_last3`)
- whose ranking was closer to the realized rank

**Repeat hits** are the weeks a player finished in the realized top 10 while in one board's top
10 but not the other's. They are counted per player, and the 15 players with the largest net
ECR-only hits are profiled on the same variables. Player names are for display only; ids are the
keys.

**FLEX.** The same P1 decomposition at k = 10 and 25, and P2 over the FLEX top-25-on-either
region. Each player uses their **own position's** surprise and pair thresholds. The FLEX boards
are W4–W7's existing ones; no FLEX model is built.

---

## 7. Interpretation — fixed now

A **precondition** applies at each position.

- **Pair route:** `Ω > 0` with a CI excluding zero.
- **Capture route:** `G > 0` with a CI excluding zero.

A route whose precondition fails is unavailable. If both fail, the position's verdict is
**NO GAP TO EXPLAIN**.

**INFORMATION is supported** if either route holds:

- **Route I-1 (conditional):**
  - `Ω_surp − Ω_close > 0` with a CI excluding zero ("materially larger during surprises"), **and**
  - `Ω_close ≤ ½ Ω` ("substantially smaller when close").
- **Route I-2 (counterfactual):**
  - `G_S ≥ ⅓ G`, **and**
  - `G_S` has a CI excluding zero, positive ("perfect opportunity information would remove a
    meaningful portion, *and that portion is information Alpha does not have*").

**EFFICIENCY is supported** if both hold:

- **E-1:** `Ω_close > 0` with a CI excluding zero, **and** `Ω_close ≥ ½ Ω` ("ECR retains a
  meaningful advantage when opportunity is close to forecast").
- **E-2:** either of:
  - `G_C ≥ ½ G` with `G_C`'s CI excluding zero, positive; **or**
  - `Ω_match > 0` with a CI excluding zero **and** `Ω_match ≥ ½ Ω`.

  Either one means perfect opportunity knowledge would leave most of ECR's advantage intact.

**Verdict at a position:**

| holds | verdict |
|---|---|
| both | **MIXED** |
| INFORMATION only | **INFORMATION** |
| EFFICIENCY only | **EFFICIENCY** |
| neither | **INCONCLUSIVE** |

I-1 and E-1 are mutually exclusive by construction. MIXED can only arise through I-2 together
with EFFICIENCY.

**The W flag** — known-opportunity weighting — is raised when `G_F ≥ ⅓ G` with a CI excluding
zero, positive. It is reported next to the verdict and never replaces it.

**Overall verdict, from RB and WR:**

- they agree: that verdict;
- one is INCONCLUSIVE or NO GAP: the other's verdict, stated as position-specific;
- INFORMATION at one and EFFICIENCY at the other, or MIXED at either: **MIXED**.

TE and FLEX get their own verdicts by the same rule. They are reported and do not change the
overall verdict.

**Recommendation mapping (the brief's §19):**

| overall verdict | direction |
|---|---|
| INFORMATION | A — acquire timestamped external information |
| EFFICIENCY | B — investigate efficiency/performance prediction |
| MIXED | C — both |
| INCONCLUSIVE | D — stop this line |

One exception: if the verdict is INCONCLUSIVE and the W flag is raised at RB or WR, the
recommendation states that the gap lies in **how Alpha uses information it already has**, which
is neither A nor B. It says so rather than forcing one of the four.

---

## 8. Statistics

- **Paired within week; the week is the unit (n = 79).** Players are never treated as independent
  observations.
- Bootstrap CIs resample weeks: 10,000 resamples, seeds 0–9 (`noise.paired_difference`).
- Each result reports its MDE (the CI half-width), the Wilcoxon signed-rank p, and the count of
  weeks with a positive vs negative value.
- A mechanism is declared only on a CI excluding zero **and** the share thresholds in §7. An
  effect inside its own MDE supports nothing.
- The player-level analysis is descriptive and carries no inferential claim.

---

## 9. Robustness — fixed now

1. **Leave-one-season-out** and **per-season**: `G`, `G_F`, `G_S` and `G_C` at capture@10; `Ω`,
   `Ω_close`, `Ω_surp − Ω_close` and `Ω_match`.
2. **Half-PPR:** a full replication, using Half-PPR `x`, `f`, `c`, ECR series and points. It
   never selects.
3. **Bucket-boundary sensitivity** for P2:
   - a median split (CLOSE means both players are below the median `|s|`; SURPRISE means at least
     one is above it);
   - quintile extremes (CLOSE means both are in the bottom quintile; SURPRISE means at least one
     is in the top quintile);
   - relative surprise `|s| / max(f, 1)` terciles.
4. **Opportunity-metric sensitivity:** P2 with surprise measured in **targets + carries**, i.e.
   W7's `M_NEW` forecast of `T_OPP`.
5. **Depth sensitivity:** P1 at k = 5 and 20; P2 on a top-10-on-either and a top-30-on-either
   region.
6. **One position:** verdicts are per position by construction.

**A conclusion is called robust** if its supporting route holds in at least 4 of 5 LOSO folds,
in Half-PPR, and under at least 3 of the 4 sensitivity variants in items 3–4. Robustness is
reported; it does not change the pre-registered verdict.

---

## 10. Validity and leakage gates — all must pass before any result is read

| gate | check |
|---|---|
| **G1** | **Parity.** `CF_A` is production's stored predictions exactly, and `ALPHA_ORACLE_OPP` with no added feature reproduces them exactly. |
| **G2** | **Forecast is pre-Friday.** The W8 forecast `f` equals W7's `M_NEW` exactly: its per-week W7 metrics re-derive to the committed values. W7's physical-redaction test re-runs and moves 0 predictor values. |
| **G3** | **Actual opportunity is outcome only.** Realized `x`, `s`, `c` and points enter no board except the two declared Class D boards (`ALPHA_ORACLE_OPP`, `ORACLE_USAGE`). This is a static check of the runner, plus proof that `f` is unchanged when realized `x` is perturbed. |
| **G4** | **ECR is not in Alpha.** No ECR/market column in Alpha's training frame or features; `CF_A` is byte-identical to production's stored predictions. |
| **G5** | **No post-Friday news.** No injury, news, Vegas or current-week depth source is referenced by the W8 runner. |
| **G6** | **No realized game information in predictors.** Covered by G2 and G3. |
| **G7** | **Walk-forward.** No training frame for `f` or `ALPHA_ORACLE_OPP` contains the season it predicts. |
| **G8** | **Joins and identity.** No duplicate (player, season, week) keys. Every universe player has exactly one `f` and one `x`, and every missing usage row is verified zero-opportunity. `G = G_F + G_S + G_C` holds to 1e-9 in every week and depth. The bucket attributions sum to `G`. The boards share one universe. |
| **G9** | **Friday cutoff and universe.** The universe is identical to W7's (week, position, player) set, and it has 0 kicked-off players. |
| **G10** | **Determinism.** The runner is byte-identical on a repeat run. |
| **G11** | **Upstream.** W5, W6 and W7 reproduce exactly (§2.1). |

**If any gate fails: stop, fix, re-run the affected analysis, document it, and only then read
results.**

---

## 11. A priori predictions, recorded before any result

1. **RB:** `G_S` is the largest of the three pieces, at least ⅓ of `G` and significant. RB usage
   is the most news-driven (committees, injuries).
2. **WR:** `G_C` is the largest piece. WR conversion (quarterback, depth of target, talent) is
   where expert judgement should matter.
3. `G_F` is small (< ⅓ `G`) at RB and WR. W7 showed Alpha already uses forecastable opportunity
   about as well as possible.
4. `Ω_close` is positive at both positions. It is below ½ `Ω` at RB and at least ½ `Ω` at WR.
5. **B (`ALPHA_ORACLE_OPP`) beats ECR by at least +0.10 capture@10 at every position.** The naive
   counterfactual "closes" the gap, uninformatively (§6).
6. `ρ(d, s) > 0` at RB, significant; weaker at WR. `ρ(d, c) > 0` at WR.
7. TE: INCONCLUSIVE (smaller gap, noisier).
8. **Overall verdict: MIXED**, with INFORMATION at RB and EFFICIENCY at WR.
9. FLEX: MIXED.
10. **Player level:** ECR-favored players have positive mean `s`, more volatile roles (higher
    `opp_sd_last3`) and shorter histories than Alpha-favored players.

If the results contradict these, the results win and the contradiction is reported prominently.

---

## 12. What W8 may NOT do

- Add ECR to Alpha, or train, calibrate or tune anything with it.
- Change production or any file under `models/`, `league/`, `api/`, `cli.py`, `market/`,
  `features/`, `identity/`, `ingest/`, `sources/`.
- Acquire injury, news, Vegas or other external data.
- Attempt to improve Alpha.
- Change a bucket, threshold, region or rule after seeing results.
- Present `ALPHA_ORACLE_OPP` as deployable.
- Choose the explanation by which result is more interesting.

---

## 13. Amendments

### A1 — pre-results clarification (2026-09-23, before any W8 result was read)

**The FLEX MATCHED threshold.** §6 says each FLEX player carries "their own position's surprise
and pair thresholds". A **pair** threshold is ambiguous for a cross-position pair, because the pair
has no single position. W8 therefore takes the FLEX MATCHED cut as the bottom tercile of
`|x_i − x_j|` pooled over **FLEX top-region pairs**. Per-player quantities (the CLOSE and SURPRISE
cut points) still use each player's own position, as written.

This was decided while writing the instrument, before the runner had produced any output. No
positional quantity and no verdict rule changes.
