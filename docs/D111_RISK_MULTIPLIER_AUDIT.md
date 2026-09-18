# D111 — Risk multiplier audit and ablation

Diagnostic phase. No production change, no retraining, no new feature, no change to the scoring
formula, no PR, nothing merged. `models/` `73b408e9`, `league/` `d4cfd00e`, unchanged.
Window 2021–2025. Vintage `d2955868…` (the D109 rebuild), the same board D110 ran against.

---

## Pre-registration of the Part 5 ablation

**Committed before the ablation ran** (`b96b88a`). Parts 1–4 are diagnostics and their results were
known when this was written — that is the order the phase brief specifies. What is fixed here is the
ablation's design, its metrics and its guards, none of which was re-selected after an arm result was
seen. Results are appended below; nothing in this section was edited afterwards.

### The arm

    risk_mult = 1.0     for every evaluable candidate

and nothing else. Same Y1 projections, same board, same marginal starter value, same draft-aware
VORP, same opportunity cost, same roster fit, same survival, same capacity cap, same opponent
field, same seasons, same continuation. The risk formula is not altered in any other way; it is
removed from the product.

### How it is applied without touching production code

`league/draft.py` computes `risk_mult = confidence if confidence is not None else 0.7`, reading
`confidence` from `uncertainty_predictions` by `(player_id, season, model_version)`. Setting that
column to 1.0 in an isolated database copy therefore yields `risk_mult == 1.0` exactly.

**The complication this design must handle.** About a quarter of the projection universe has no
uncertainty row at all — every DST (32/season), most kickers (~44/season) and ~100 rookies — and
those candidates take the hardcoded **0.7** fallback instead of a model output. Setting only the
existing rows to 1.0 would not ablate risk; it would silently re-weight skill players against
K/DST/rookies. The ablation therefore also **inserts** a row for each projection-universe player
that lacks one, carrying that player's exact projection and position, so that
`load_season_projections` returns a byte-identical board while `_confidence_for` returns 1.0 for
everyone.

**Two guards, which abort the run rather than report:**

1. the assembled `board_hash` for every season is **unchanged** from control — proving the
   projections did not move, so this is an ablation of risk alone; and
2. every player in the projection universe returns `confidence == 1.0`.

### Metrics

**Primary:** whole-draft realized starter points, per `(season, slot)`, differenced against control
on the same `(season, slot)`. Inference unit is the **season cluster** (n=5, t(4) = 2.776), per
D88's finding that the detection floor is bound by seasons and slots cannot lower it.

**Secondary / diagnostic, never primary:** weekly realized value under
`draft_oracle.py::WEEKLY_NO_FORESIGHT`; a cross-format run on `legacy_2qb_dynasty`, the repo's
designated second format; rounds 1–3 realized value; positional composition and first-RB round.

**Explicitly not primary:** arm-relative pick regret (D105/D106 — it goes non-monotone when the arm
changes the oracle comparison), and the number of decisions changed. *Drafting more RBs is not a
result.* Only realized draft value decides the primary conclusion.

### Population and power

Target format: 5 seasons × 10 slots = **50 paired drafts** per arm (D110 ran 4 slots; D111 has only
two arms, so the full slate is affordable and is used). Cross-format: 5 seasons × 4 slots.
Power is re-derived empirically on this vintage and reported against D109's ≈177 points/draft
reference, with the result stated as powered or underpowered **before** the null is interpreted.

### Pre-committed interpretation rule

A result counts as a real effect only if the season-cluster 95% interval excludes zero. If it does
not, the phase reports the effect as undetected and states whether the experiment had the power to
have seen ~177 points/draft. No replacement risk formula is selected in this phase under any
outcome; Part 9 is diagnostic only.

Runners: `scripts/research/d111_risk_audit.py`, `d111_risk_leverage.py`, `d111_ablation.py`,
committed before the ablation ran.

---

# Results

*Appended after the ablation ran. The pre-registration above is unchanged.*

## BOTTOM LINE

The `risk` multiplier is not measuring risk, and this is provable rather than statistical: the
conformal interval width is a **per-(season, position) constant** — 20 of 20 cells have exactly
one distinct value — so `confidence` is a deterministic, strictly increasing function of the
player's own projection and carries no player-specific uncertainty at all. It is therefore a third
projection-magnitude term wearing a risk label, and empirically it is *inverted*: higher confidence
goes with **larger** absolute error at every position. It has real leverage — 21% of production
pick states select a different player once it is removed — but removing it entirely
(`risk_mult = 1.0`, everything else frozen) produced **no detectable change in realized draft
value** in either format, and both nulls are powered. The deeper problem sits upstream: **every**
uncertainty quantity the model emits is a monotone transform of the point prediction, so no
principled risk term can be built downstream of it.

## WHAT RISK IS DOING

- `p10`/`p90` are the point prediction plus **calibration-residual quantiles fit once per
  (season, position)** — so `p90 − p10` is identical for every player in that cell.
- `confidence = clip(1 − W(season, position) / (2·|projection|), 0, 1)`, and
  `league/draft.py` multiplies the whole value base by it. Bounded above by 1.0, so it can **only
  ever reduce** a score, never raise one.
- Within a position-season it is the projection re-expressed: Spearman(confidence, projection)
  ≥ 0.83 in all 20 cells, and exactly 1.0 before clipping ties.
- Typical values in the rounds 1–3 contention set: **RB 0.604, WR 0.719, QB 0.722, TE 0.753** —
  so risk removes 21–35% of the winning score, unevenly by position.
- It collapses to **exactly zero** past roughly ECR 160 (27% of ECR 161–250, 78% beyond, 100% of
  unranked players). Inside the 160 players a draft actually consumes it is almost never zero, but
  the players still *available* in the last rounds are exactly that population.
- About **a quarter of the pool has no uncertainty row at all** — every DST, most kickers, ~100
  rookies a season — and silently takes a hardcoded **0.7** fallback. In the late rounds that is
  not a tie-break against a zeroed skill player; it is a rout, and it is a plausible mechanism for
  the long-documented round-9 kicker.

## IS RISK ACTUALLY MEASURING RISK?

- **No, and it cannot be.** With the width held constant per cell, conditioning on the projection
  leaves confidence with zero variance. The partial association is zero by construction.
- **The sign is wrong.** Spearman(confidence, |error|) is **positive** at every position
  (QB +0.18, RB +0.31, WR +0.25, TE +0.29). A working risk measure needs it clearly negative.
- **It marks down the under-projected.** Signed-error correlation is positive at QB/WR/TE, and
  projection-quintile bias runs −33.2 (lowest) to +20.6 (highest) — the multiplier discounts
  exactly the players the model already under-projects, compounding the D109 bias.
- The intervals themselves are mildly optimistic: **74% mean coverage against a nominal 80%**.
- **This supersedes a D110 reading.** D110 reported relative error falling as confidence rises and
  called it real signal. Both quantities divide by the projection, so that relationship is
  mechanical; the absolute-error test above is the honest one, and it inverts the conclusion.

## DOES IT HURT THE DRAFT?

**No detectable effect, in either format, with adequate power to have seen one.**

| | control | risk_off | Δ | 95% CI (season) | seasons | MDE | verdict |
|---|---|---|---|---|---|---|---|
| **Target (1-QB PPR), 50 drafts** | 2010.9 | 2037.6 | **+26.7** | [−112.9, +166.4] | 2W/3L | 139.6 | powered null |
| 2-QB dynasty, 20 drafts | 2106.8 | 2159.5 | +52.7 | [−70.3, +175.7] | 3W/2L | 123.0 | powered null |
| Target, weekly objective | — | — | +49.0 | [−80.7, +178.7] | 3W/2L | — | null |
| 2-QB dynasty, weekly | — | — | +28.5 | [−104.0, +161.0] | 2W/3L | — | null |

Both positive point estimates are **single-season artifacts, and not even the same season**:
the target format's +26.7 becomes **−22.9** once 2024 is removed; the dynasty format's +52.7
becomes **+11.1** once 2021 is removed. Zero unfilled mandatory starting slots in either arm.

## WHAT CHANGED IN ROUNDS 1–3?

- 33% of all picks change; **27% of rounds 1–3** picks change.
- First RB moves from round **4.38 → 3.54**; roster RB count 3.16 → 3.68, DST 1.50 → **1.28**.
- Modal opening shifts `WR-WR-QB` → `WR-QB-WR`.
- Held at a fixed pick state, **21% of 350 audited states flip**, 61% of them a position change —
  concentrated in round 6 (44%), round 5 (28%) and rounds 1–2 (22% each).
- Concrete flips (same state, with risk → without): 2023 pick #10 Amon-Ra St. Brown
  (WR, 259 pts × 0.76) → **Mahomes** (QB, 371 × 0.71); 2022 pick #5 Kyler Murray
  (QB, 355 × 0.77) → **Derrick Henry** (RB, 249 × 0.71). Risk favours whichever position has the
  smaller residual spread relative to its projection scale — an unintended positional
  re-weighting, not a player judgement.
- **Risk is not the cause of the early WR/QB lean.** Removing it moves the first RB by less than a
  round and *lowers* rounds 1–3 realized value slightly. Outcome E is rejected.

## WHY DID VALUE CHANGE?

- It essentially didn't — but where it moved, it moved **late**: rounds 1–3 **−5.9**, rounds 4–6
  −7.8, **rounds 7–10 +53.1**, rounds 11–16 +1.8.
- The effect is a handful of drafts: the 5 largest contribute **+2055 against a net +1336**, i.e.
  the other 45 are net negative.
- The three biggest gains (2024 slots 1–3, +548/+548/+400) have **identical first three picks** in
  both arms. Whatever happened there happened after round 3.
- Consistent with the mechanism: the multiplier's real bite is where it is most unequal — the
  mid-to-late rounds, where skill players decay toward zero confidence while K/DST hold 0.7.

## RISK MULTIPLIER — CAN IT BE REPLACED?

Diagnostic only; nothing selected, nothing shipped.

**No, not from what the model currently emits.** Spearman against the point prediction, within
(season, position): `p10`, `p25`, `median`, `p75`, `p90` all **exactly 1.0000**; `top12_prob`
0.91–0.99; `top24_prob` 0.97–0.99. The uncertainty model is **homoscedastic** — it produces one
interval shape per position-season and slides it up and down with the projection. Every candidate
replacement in the phase brief (position-relative scale, magnitude-independent, absolute, calibrated
empirical) would be built from these outputs and would therefore still be a function of the
projection. A genuine risk term requires the **uncertainty model itself** to emit per-player
interval widths.

## RECOMMENDATION

Do not ship anything from this phase. The multiplier is demonstrably mislabelled and mildly
perverse, but removing it is value-neutral under a powered test in two formats, so this is a
**correctness and interpretability problem, not a performance one**, and it does not justify a
production change on its own — particularly since the 0.7 fallback it depends on is currently
doing unmeasured work keeping K/DST timing sane. The next phase should go **upstream**: establish
whether player-level (heteroscedastic) uncertainty is estimable at all from the existing feature
panel. If it is not, then `risk` should eventually be retired rather than reformulated, and that
retirement should be bundled with the roster-legality constraint the decision-layer report already
identified — because the 0.7 fallback and the legality guarantee are currently the same mechanism.

---

# Evidence and methodology

## The structural result (Part 1)

`models/uncertainty/conformal.py::apply_quantiles` returns `point_prediction + residual_quantile`,
with `fit_conformal_quantiles` called once per calibration season per position. Measured widths
(`p90 − p10`), one distinct value per cell in 20 of 20:

| season | QB | RB | WR | TE |
|---|---|---|---|---|
| 2021 | 195.4 | 162.3 | 143.6 | 106.2 |
| 2022 | 161.8 | 143.3 | 141.3 | 92.5 |
| 2023 | 215.2 | 139.1 | 126.6 | 70.7 |
| 2024 | 189.8 | 149.2 | 107.6 | 75.1 |
| 2025 | 158.4 | 143.0 | 132.7 | 94.5 |

Worked example, real 2024 RBs — the width column is the tell:

| player | proj | p10 | p90 | width | confidence | realized |
|---|---|---|---|---|---|---|
| Breece Hall | 227.3 | 177.9 | 327.1 | 149.2 | 0.672 | 240.9 |
| Jahmyr Gibbs | 216.1 | 166.6 | 315.9 | 149.2 | 0.655 | **362.9** |
| Josh Jacobs | 157.6 | 108.2 | 257.4 | 149.2 | 0.527 | **293.1** |
| James Cook | 144.8 | 95.3 | 244.6 | 149.2 | 0.485 | 266.7 |

Jacobs and Cook are discounted 47–52% relative to nothing about Jacobs or Cook — only about how
many points the model happened to project for them. Both then outscored Hall.

## The RB-versus-WR gap, decomposed (Part 3)

Inside ECR ≤ 36: RB confidence 0.604 (width 148.2, projection 195.9), WR 0.719 (129.2, 234.4).
Gap **+0.115**. Holding RB's projection and giving it WR's width closes **58%**; holding RB's width
and giving it WR's projection closes **70%** (they overlap because the terms interact). The answer
to the phase brief's question is **D, a combination** — but the material point is that *both*
channels are position-level, and the projection channel is the one D109 showed to be biased low at
RB, so the multiplier compounds that bias rather than hedging it.

## Ablation mechanics and guards (Part 5)

Applied by setting `uncertainty_predictions.confidence = 1.0` in an isolated database copy, and
**inserting 857 rows** for the projection-universe players that had none (every DST, most kickers,
~100 rookies per season) at their exact projections — otherwise the "ablation" would have been a
re-weighting of skill players against K/DST. Both pre-registered guards passed on every shard:
every season's `board_hash` unchanged, and every candidate returning `confidence == 1.0`.

**Cross-instrument integrity:** D111's control reproduces D110's control on **20 of 20** overlapping
`(season, slot)` cells, exactly. Vintage `d2955868…` throughout; not comparable with pre-D109
figures (D109 §0 — the nflverse panel was restated upstream).

## Where the zero cliff sits

| ECR band | n | mean confidence | % at exactly 0 |
|---|---|---|---|
| 1–36 | 166 | 0.678 | 0% |
| 37–80 | 193 | 0.603 | 1% |
| 81–120 | 160 | 0.521 | 4% |
| 121–160 | 150 | 0.431 | 2% |
| 161–250 | 285 | 0.249 | 27% |
| 251+ | 828 | 0.046 | 78% |
| unranked | 472 | 0.000 | 100% |

## Challenging the hypothesis (Part 10)

- **A (removing risk materially helps)** — rejected. Powered null in both formats; the positive
  point estimates are different single seasons in each.
- **B (removing risk materially hurts)** — rejected, same evidence.
- **C (changes many decisions, no value effect)** — **supported.** 33% of picks, 27% of rounds 1–3,
  21% of fixed-state selections, no detectable value change.
- **D (mathematically ugly but useful in practice)** — **not excluded** for one narrow purpose: the
  0.7 fallback keeps K/DST competitive against zero-confidence skill players late, and DST count
  fell 1.50 → 1.28 under the ablation without any unfilled slot. Untested as a legality mechanism.
- **E (risk is responsible for the WR/RB behaviour)** — **rejected.** First RB moves 4.38 → 3.54
  and rounds 1–3 value falls slightly.
- **F (the uncertainty estimates are the deeper problem)** — **supported, and it is the headline.**
- **G (underpowered)** — **rejected for the primary comparison.** MDE 139.6 (target) and 123.0
  (dynasty) against D109's ~177 reference.

## Repository state

1427 tests pass, 44 deselected. `ruff check` and `ruff format --check` on `src tests` clean.
`models/` `73b408e9` and `league/` `d4cfd00e` unchanged. Added this document and five
`scripts/research/d111_*.py` runners. **No `src/` change of any kind.** Nothing merged, no PR.
