# D117 — Does Alpha already know about the hidden breakout players?

**Headline: no. Alpha's uncertainty model does not contain player-specific upside information,
so there is nothing for the scoring formula to suppress. M6's intervals are
`point + one constant per (season, position)`. Within a position-season, p10/p90/width/upside
are identical offsets from the projection, top-12/top-24 probabilities are the projection's rank
up to Monte Carlo noise, and `confidence` is an exact deterministic function of the projection.
On the D115/D116 sequencing pairs, no uncertainty output separates the oracle's player from
Alpha's as an individual (1 same-position case in 69, and that one is Monte Carlo noise). The
oracle's player loses because every piece of information Alpha holds says he is worse. The next
research problem is whether player-level upside is *knowable at all*, not how to weight it.**

**No production change, no weight tuned, no feature or model created, no draft strategy run.
Nothing ships.** `src/alpha_squad/` is byte-identical (tree `55e763e8…`).

---

## 1. Plain-English conclusion

1. **The shipped uncertainty model has no player-level uncertainty, by construction.** M6 adds
   the same signed residual quantiles to every player at a position in a season. Measured on the
   full 2021–2025 table (20 position-seasons, 2,271 player-seasons):
   * the standard deviation of `p90 − point` is at most **1.8e-14** in any position-season, and
     of `p10 − point` at most 8.3e-15;
   * `confidence` equals `1 − (p90−p10) / (2·point)`, clipped to [0, 1], to **0.0** error;
   * `top24` contradicts the projection's order on 3,685 of 145,417 within-position pairs
     (2.5%), all consistent with the 2,000-draw Monte Carlo noise.

   So, *within a position*, p90, top-24 probability and confidence can never rank two players
   differently from the projection. They carry no information the projection does not.
2. **On the sequencing pairs, no existing signal identifies the oracle's player.** Target, 151
   pairs:
   * **same-position pairs (39):** projection, p90, p90-over-replacement, top-12 and confidence
     all favour O **0 times**. top-24 favours O once (0.9665 vs 0.97, two near-certain top-24
     QBs, which is Monte Carlo noise).
   * **cross-position pairs:** the only departures come from position-level constants (RB's
     residual spread is wider than WR's) or from comparing *within-position* top-N probabilities
     across positions. Put p90 on the scale the engine decides on (p90 minus the engine's own
     replacement level) and it disagrees with the projection in O's favour **2** times and in A's
     favour **2** times (dynasty: 5 vs 4). Sign test p = 1.0.
3. **The oracle's player was beyond the model's own upside, not hidden inside it.** O beat his
   *own p90* in **105 of 117** target cases (135 of 146 dynasty). The information set gave these
   outcomes less than a 10% chance. That was not a mis-weighted signal: it was a tail event the
   model had no player-specific way to see.
4. **The value term is the gap; risk is second and nearly never decisive.** In an exact Shapley
   split of the shipped score gap (A − O, mean +98 points), **value** carries **81%** (79% in
   dynasty), and favours A on 151 of 151 pairs. **Risk (confidence)** carries **19%** (21%).
   Everything else is within ±2%. Setting risk to neutral lets O win **1** of 151 (2 of 155).
5. **The risk multiplier is using the wrong information, but it is not suppressing upside.**
   `confidence` is not a risk measure. Since the interval width is one constant per
   position-season, it is a convex transform of the projection, so the projection is counted a
   second time. It zeroes the whole score of **53%** of M6 player-seasons (1,209 of 2,271),
   including **26** of the 151 target oracle players. Among market-draftable players (ECR ≤ 200),
   the players it penalises most beat their projection on average: confidence = 0 gives +43.2
   points (74% beat), CI [+35.6, +51.7]; confidence in [.25, .5) gives +19.6, CI [+3.5, +35.8];
   confidence ≥ .75 gives −31.3. The multiplier therefore compounds a projection-level bias. But
   it contains no upside information to suppress, and on these pairs it changes at most 2
   decisions.

**Decision rule applied: rule 1.** Existing upside/uncertainty measures do not distinguish O from
A. The current information set lacks the needed signal. No fix is proposed.

---

## 2. Pairwise ranking table — how often each signal ranks O above A

Accuracy is the share of decisive pairs where the signal favours O. O is the hindsight-better
player on every pair, so "favours O" is a hindsight label. The 95% CI is season-clustered t
(k = 5); pooled Wilson is also shown. "undef." means either player lacks the output (K/DST and
rookies have no M6 row).

### `target_league` (PRIMARY) — 151 pairs

| signal | favours O | Wilson | season CI | MDE | ties | undef. | mean gap A − O |
|---|---|---|---|---|---|---|---|
| **point projection** | **3.3%** (5/151) | [1, 8]% | [−5, 14]% | ±9.8pp | 0 | 0 | **+79.6** pts |
| projection − replacement | 3.3% (5/151) | [1, 8]% | [−2, 9]% | ±5.9pp | 0 | 0 | +79.6 |
| **p90** | **7.0%** (5/71) | [3, 15]% | [−6, 22]% | ±14pp | 0 | 80 | +75.8 |
| p90 − replacement | 5.6% (4/71) | [2, 14]% | [−4, 17]% | ±10pp | 0 | 80 | +59.1 |
| p10 / median | 4.2% (3/71) | — | [−8, 16]% | — | 0 | 80 | +77.1 / +78.5 |
| **top-24 probability** | **15.5%** (11/71) | [9, 26]% | [2, 32]% | ±15pp | 0 | 80 | +0.32 |
| top-12 probability | 12.7% (9/71) | [7, 22]% | [3, 25]% | ±11pp | 0 | 80 | +0.25 |
| **confidence** (M6) | **8.5%** (6/71) | [4, 17]% | [−3, 20]% | ±11pp | 0 | 80 | +0.24 |
| risk multiplier as applied | 10.4% (14/134) | [6, 17]% | [1, 23]% | ±11pp | 17 | 0 | +0.25 |
| width p90 − p10 (position-constant) | 56.5% (26/46) | [42, 70]% | [36, 78]% | ±21pp | 25 | 80 | −1.3 |
| upside p90 − point (position-constant) | 76.1% (35/46) | [62, 86]% | [57, 100]% | ±21pp | 25 | 80 | −5.3 |
| rookie breakout probability | 25% (1/4) | — | — | — | 0 | 147 | +0.38 |
| ECR rank (context) | 27.8% (42/151) | [21, 35]% | [23, 34]% | ±5pp | 0 | 0 | O ranked 36 later |

### `dynasty_1qb` (replication) — 155 pairs

| signal | favours O | season CI | ties | undef. | mean gap A − O |
|---|---|---|---|---|---|
| point projection | 11.0% (17/155) | [1, 20]% | 0 | 0 | +65.6 |
| projection − replacement | 5.2% (8/155) | [−2, 14]% | 0 | 0 | +72.5 |
| p90 | 8.9% (9/101) | [−2, 19]% | 0 | 54 | +69.1 |
| p90 − replacement | 8.9% (9/101) | [−2, 22]% | 0 | 54 | +57.0 |
| top-24 probability | 15.8% (16/101) | [−5, 43]% | 0 | 54 | +0.33 |
| confidence | 8.9% (9/101) | [−4, 26]% | 0 | 54 | +0.19 |
| risk multiplier as applied | 8.7% (13/150) | [−8, 30]% | 5 | 0 | +0.22 |
| width / upside (position-constant) | 54.8% / 64.4% (of 73) | wide | 28 | 54 | +1.2 / −4.6 |
| rookie breakout probability | undefined (no rookie on both sides) | — | 0 | 155 | — |
| ECR rank (context) | 51.0% (79/155) | [24, 72]% | 0 | 0 | −5.0 |

### A and B — does p90 or top-24 rank O above A more often than the projection does?

A paired comparison on the same pairs. "Signal favours O, projection favours A" is counted
against the reverse.

| comparison | target: signal-only / projection-only | sign test p | dynasty | p |
|---|---|---|---|---|
| p90 vs projection | 2 / 0 | 0.50 | 3 / 0 | 0.25 |
| **p90 − repl. vs projection − repl.** (the decision scale) | **2 / 2** | **1.00** | **5 / 4** | **1.00** |
| top-24 vs projection | 8 / 0 | 0.008 | 11 / 1 | 0.006 |
| confidence vs projection | 3 / 0 | 0.25 | 6 / 3 | 0.51 |
| **same-position only: any of the above** | **0 / 0** (top-24: 1 / 0) | — | **0 / 0** | — |

**The top-24 result looks significant and is not information.** In target, 7 of its 8 departures
are cross-position and the eighth is the same-position Monte Carlo case. In dynasty, all 11 are
cross-position. They come from comparing a *within-position* rank probability across positions:
"70% to be a top-24 TE" and "40% to be a top-24 WR" are not on a common value scale. On the
decision scale (p90 minus replacement) the departures cancel exactly.

### C and D — does any uncertainty signal identify the breakout player?

| | target | dynasty |
|---|---|---|
| ANY uncertainty output favours O while the projection favours A | 39 pairs | 50 |
| …excluding the two position-constant outputs (width, upside) | **12** | **15** |
| …of which same-position, where a player-level signal would have to show | **1** (Monte Carlo noise) | **0** |

Breakdown of the 12 target pairs: RB→TE top-N 3, WR→RB top-N 3, QB→WR p90-over-replacement 2,
WR→RB p90 2, rookie breakout probability 1, and the same-position QB→QB top-24 noise case 1.
**Every one is a position-level artifact or noise.** The rookie model's `breakout_probability`
is defined on both sides of only 4 target pairs (0 dynasty) and is not read by the draft engine
at all.

### E — concentration

These are favours-O rates in `target_league`. The pattern is the same in every cut: no
uncertainty column beats the projection column in any group except where a cross-position
top-24 artifact appears.

| group | n | % of regret | proj | proj−repl | p90 | p90−repl | top24 | conf | risk | ECR |
|---|---|---|---|---|---|---|---|---|---|---|
| O = RB | 70 | 22.2% | 1% | 0% | 7% | 7% | 14% | 0% | 9% | 33% |
| O = WR | 52 | 18.9% | 2% | 10% | 0% | 9% | 0% | 0% | 5% | 19% |
| O = TE | 16 | 4.1% | 0% | 0% | 0% | 0% | 30% | 30% | 23% | 50% |
| O = QB | 12 | 2.8% | 25% | 0% | 33% | 0% | 44% | 33% | 25% | 0% |
| R1–6 | 42 | 16.6% | 7% | 10% | 15% | 12% | 30% | 18% | 15% | 21% |
| R7–11 | 55 | 16.9% | 4% | 2% | 0% | 0% | 6% | 0% | 7% | 40% |
| R12–16 | 54 | 14.6% | 0% | 0% | 0% | 0% | 0% | 0% | 11% | 20% |
| O proj rank 1–12 | 26 | 9.2% | 12% | 15% | 22% | 17% | 39% | 26% | 24% | 46% |
| O proj rank 13–24 | 15 | 4.4% | 7% | 7% | 0% | 0% | 10% | 0% | 0% | 47% |
| O proj rank 25–48 | 28 | 7.6% | 4% | 0% | 0% | 0% | 8% | 0% | 0% | 43% |
| **O proj rank 49+** | **82** | **26.9%** | 0% | 0% | 0% | 0% | 0% | 0% | 12% | 13% |
| O ECR 1–50 | 13 | 5.4% | 0% | 31% | 8% | 23% | 8% | 0% | 0% | 54% |
| O ECR 51–100 | 30 | 11.1% | 13% | 3% | 16% | 4% | 32% | 20% | 17% | 20% |
| O ECR 101–150 | 31 | 9.9% | 3% | 0% | 0% | 0% | 25% | 12% | 4% | 74% |
| **O ECR 151+** | **77** | **21.7%** | 0% | 0% | 0% | 0% | 0% | 0% | 13% | 8% |
| 2021 / 22 / 23 / 24 / 25 | 37/22/31/32/29 | 14.5/4.7/10.4/12.8/5.7% | 0/18/0/0/3% | 8/9/0/0/0% | 0/21/0/20/0% | 5/7/0/20/0% | 0/29/27/10/20% | 0/21/9/0/13% | 0/14/13/24/7% | 24/32/23/31/31% |

**Where the regret concentrates, the information is absent.** Over half of it (26.9% of total
regret, 82 pairs) comes from O's projected 49th or worse *at his position*. Of that, 21.7% comes
from O's the market ranks outside its top 150, where every model output favours O **0%** of the
time. The per-round cells (n ≤ 16) are in `d117_summary.json` and are descriptive only.

### F — against the realized outcome (HINDSIGHT; never an input)

| | target | dynasty |
|---|---|---|
| mean projection A / O | 188.2 / **108.6** | 202.0 / 136.4 |
| mean realized A / O | 162.6 / **272.1** | 175.5 / 290.2 |
| **O realized above his own p90** | **105 / 117** (90%) | **135 / 146** (92%) |

**Selection control.** This separates "a signal that tracks variance" from "a signal that tracks
value". Across every established player on the board, not the hindsight-selected pairs: within
each (season, position), the correlation of the *signed* residual with p90 is **identical** to its
correlation with the point projection (−0.075 all players; −0.155 at ECR ≤ 200). That is expected,
because p90 *is* the point projection plus a constant. The one player-specific dispersion signal
Alpha stores is the market's `ecr_worst − ecr_best`. Holding the projection fixed, it predicts
the signed residual at **−0.24**, CI [−0.39, −0.08], among ECR ≤ 200. Wider market disagreement
means a *worse* outcome than projected, not a better one. It does not predict the absolute
residual (−0.04, CI spans 0). **Nothing Alpha holds marks upside.**

---

## 3. Score-component decomposition, A vs O (exact Shapley over the shipped formula)

`score = (value_base + opp_cost) × fit × risk × survival × capacity`. Each factor's contribution
is its average marginal effect of switching from O's value to A's, over all 64 coalitions. The
contributions sum to the gap exactly (asserted per pair). The factorisation is checked against
the engine's own logged value_base. Where a zero confidence has zeroed the score, value_base is
read from that log.

| factor | target: mean pts | share | favours A / O | neutralise → O wins | dynasty: share | neutralise → O wins |
|---|---|---|---|---|---|---|
| **value** (value base) | **+79.7** | **81.3%** | 151 / 0 | n/a | **79.1%** | n/a |
| **risk** (confidence) | **+18.7** | **19.1%** | 95 / 39 | **1** | **21.2%** | **2** |
| survival | +1.5 | 1.5% | 76 / 46 | 0 | 2.1% | 1 |
| opportunity cost | −0.5 | −0.5% | 4 / 13 | 0 | −0.2% | 0 |
| roster fit | −0.9 | −0.9% | 49 / 47 | 0 | −1.9% | 0 |
| capacity | −0.5 | −0.5% | 0 / 5 | 0 | −0.4% | 0 |
| **total gap** | **+98.1** | 100% | | | (+106.3) | |

The risk inputs behind that row: **26** target O's (7 in dynasty) have confidence exactly 0, which
zeroes their whole score. **34** O's (9) are on the 0.7 fallback (rookies and one DST). No A has
confidence 0; 63 A's (50) are on the fallback (K, DST, rookies).

---

## 4. Is the risk multiplier suppressing useful upside information?

**No, because it has none to suppress. It is using the wrong information, as the brief's rule 3
asks us to distinguish.**

* **What it is.** `confidence = clip(1 − W_pos,season / (2·projection), 0, 1)`. Since W is
  constant within a position-season, confidence is a monotone function of the projection alone.
  Multiplying the score by it counts the projection twice. It is a documented heuristic ("not a
  probability", `models/uncertainty/conformal.py`), and D117 confirms it contains no
  player-specific risk.
* **Is the penalty justified?** Among market-draftable players (ECR ≤ 200, 797 player-seasons),
  mean realized minus projection by confidence bucket:

| confidence | n | mean projection | mean realized | signed residual | season CI | beat projection | \|residual\| |
|---|---|---|---|---|---|---|---|
| 0 (score zeroed) | 23 | 64.4 | 107.6 | **+43.2** | [+35.6, +51.7] | 74% | 64.2 |
| (0, .25) | 76 | 87.6 | 97.6 | +10.0 | [−16.7, +34.6] | 50% | 50.7 |
| [.25, .5) | 194 | 118.7 | 138.3 | **+19.6** | [+3.5, +35.8] | 58% | 57.3 |
| [.5, .75) | 454 | 197.9 | 195.7 | −2.2 | [−12.0, +7.4] | 46% | 59.5 |
| [.75, 1] | 50 | 256.9 | 225.7 | **−31.3** | [−83.6, +2.9] | 34% | 69.6 |

  The penalty points the wrong way for the draftable pool: low-confidence (low-projection)
  players are *under*-projected on average, and the top bucket is over-projected. Absolute error
  does *not* rise as confidence falls, so the multiplier is not even tracking noise. Across all
  established players (2,271), the confidence-0 bucket beats projection by only +4.5 [+2.7, +6.2].
  The effect is concentrated among the players the market considers draftable, which is exactly
  the decision population.
* **Does it matter here?** Barely. It accounts for 19–21% of the A-vs-O score gap, but
  neutralising it changes **1 of 151** (2 of 155) decisions. The value term alone favours A on
  every pair.

**This does not meet the bar for a production change.** Neither does it clearly support a
separate controlled experiment *from this population*. A controlled test of the risk term would
need evidence from all picks, not the 1–2 it moves here. The observation is recorded; nothing is
proposed.

---

## 5. How much of D115/D116's regret is addressable by information already inside Alpha?

Share of **total** per-format regret (target 44,027; dynasty 42,218):

| | target | dynasty |
|---|---|---|
| sequencing population (C1 ∧ C2) | 48.1% | 46.5% |
| any M6 / rookie output favours O while the projection favours A | 11.4% (39) | 15.3% (50) |
| …excluding the position-constant width/upside | 4.5% (12) | 4.9% (15) |
| …that is player-level, i.e. same-position | **~0%** (1 pair, Monte Carlo noise) | **0%** |
| p90-over-replacement favours O (the decision scale) | 2.1% | 3.6% |
| risk-neutralised: O would outscore A | 0.4% (1) | 0.6% (2) |

**Addressable by existing player-level upside information: effectively zero.** The 2–5% that
cross-position artifacts touch is balanced by the pairs where the same artifacts favour A (the
2 vs 2 and 5 vs 4 discordance). Treating it as recoverable would be treating position-level
variance as player knowledge.

---

## 6. What D117 does NOT establish

1. **That player-level upside is unknowable.** Only that *Alpha's current information set*
   contains none. M6 was never built to carry it.
2. **That the confidence multiplier is harmless in general.** Only that it moves ≤ 2 of these
   306 decisions. Its projection-level bias among draftable players is real (§4) and unexplored
   outside this population.
3. **Real-draft transfer.** Same caveat as D116: opponents are the deterministic market-rank
   field.
4. **Vintage.** Board vintage `f0022601…`, the same as D116 and different from D113–D115's
   `0d525430…` (see D116 §9).

---

## 7. Recommended next research question (exactly one)

> **Is player-specific upside knowable preseason at all? Walk-forward, using only information
> Alpha already stores, is the size or upper tail of M6's out-of-sample residual predictable
> *beyond the (season, position) constant*, and would such a prediction rank the C1 ∧ C2 oracle
> players above Alpha's picks more often than chance on the same-position pairs?**

This is the largest remaining information gap. The value/projection term carries ~80% of the
score gap. The oracle's player finishes above his own p90 about 90% of the time. The model
assigns every player at a position the same uncertainty. The one player-specific dispersion
signal already stored (the market's ECR range) points the wrong way. If residual size is not
predictable walk-forward, the D115 sequencing regret is irreducible tail luck for this
information set, and the programme should stop spending phases on it. If it is predictable, that
becomes the first evidence that justifies a pre-registered model phase.

---

## 8. Reproducibility, provenance and what changed

```bash
# D116's artifact (d116_pairs.json) is the input; see docs/D116_SURVIVAL_ATTRIBUTION.md §9
uv run python scripts/research/d117_upside_audit.py --mode measure --d116 <d116 out> --out <o>
uv run python scripts/research/d117_upside_audit.py --mode report  --out <o>
uv run pytest tests/unit/test_d117_upside_audit.py
```

| item | value |
|---|---|
| HEAD at run time | `b01a03ee6f8accb579d089c0089212c34ff9df1a` (D116) |
| `src/alpha_squad` tree / working copy dirty | `55e763e8a80af908a2c2bcc0ae66753c16b629fc` / **False** |
| board vintage, combined 2021–2025 | `f00226015095534f22e1311c8fa1b4823d66e0679ef6fa8f1817500209dce89f` (**= D116's**; checked by the runner) |
| per season | 2021 `79599ffa…` 2022 `43f0e968…` 2023 `aa73cd3f…` 2024 `7873284c…` 2025 `0b344c7e…` |
| upstream board / idmap sha256 | `e270d790…` / `36016b92…` |
| uncertainty model / rookie model | `uncertainty_catboost_v2` / `rookie_features_v1` |
| input: D116 `d116_pairs.json` sha256 | `56dbb1427705d44f04402e4aad0199dc90b4d9f32f8bf3134d4a1a74cd0b9ce6` |
| D117 `d117_measured.json` / `d117_summary.json` sha256 | `e1d332d9…` / `cc47e7ea…` |
| population | 151 target + 155 dynasty C1 ∧ C2 pairs, each re-walked and its pick reproduced |
| selection control | 2,271 established player-seasons, 797 of them at ECR ≤ 200 (`target_league`'s series) |

**One defect found and fixed before any result was read.** The first report run scored ~1e-14
floating-point differences in M6's per-position interval offsets as preferences. That produced
"width favours O 80%" on *same-position* pairs, where the width is identical by construction.
Pairwise calls now treat values within 1e-9 (relative) as a tie, and
`test_float_noise_is_a_tie_regression` pins it.

**A second defect, in an earlier phase's guard, found and fixed.** After a routine `git fetch`,
`tests/unit/test_d114_matched_state.py::test_no_naive_arm_exists_in_the_checkout` failed. It
searched `git log --all`, so it matched `ab18fc2`, a commit on an *unmerged* remote branch
(`claude/ecr-incremental-draft-value-1zcj94`) whose D111 arm label `ECR_ALONE_NAIVE` contains the
substring. That commit is not D97's arm and not in HEAD's history. The guard's verdict depended on
which refs a clone had fetched. It is scoped to HEAD now, matching its name and docstring ("in the
checkout"), with the regression recorded in the docstring. This is a test-only change.

**Files changed by D117 — research only:**

| file | status |
|---|---|
| `scripts/research/d117_upside_audit.py` | **new**: measure / report runner |
| `tests/unit/test_d117_upside_audit.py` | **new**: 34 tests |
| `docs/D117_UPSIDE_AUDIT.md` | **new**: this report |
| `tests/unit/test_d114_matched_state.py` | **fixed**: history guard scoped to HEAD (see above) |
| `docs/DECISIONS.md`, `docs/PROJECT_STATE.md` | appended |
| `src/alpha_squad/**` | **unchanged** |
