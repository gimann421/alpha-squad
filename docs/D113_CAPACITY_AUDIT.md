# D113 — Does the positional-capacity mechanism cost realized draft value?

**Verdict: C — CAPACITY IS NOT COSTING REALIZED DRAFT VALUE. It is doing a small amount of
GOOD, and it is close to inert on the primary objective. Close the hypothesis.**

Removing the capacity penalty entirely, from the real production decision path, changes realized
season-long starter value by **+0.8 points per draft in `target_league`** (95% CI [−46.1, +47.7],
1 of 5 seasons better) and **+0.9 in `dynasty_1qb`** (CI [−14.6, +16.4]). In the 2-QB negative
control it is **−25.1** (CI [−43.1, −7.2], **worse in 5 of 5 seasons**, t = −3.89) — i.e. removing
capacity *hurts*. On the weekly objective the sign is negative in every format
(−22.6 / −5.1 / −40.1 no-foresight; −60.4 / +0.4 / −60.1 hindsight).

**Capacity has exactly the leverage D112 measured and almost none of the value.** It fires at
**31.0%** of target-format pick states, changes **13.1%** of all picks, and moves the objective by
less than one point per draft. Every changed pick is in **rounds 11–16**; the effect on rounds 1–6
is **identically zero, in all three formats**.

**No production change. No new capacity rule. No weight tuned. No PR. Nothing merged.**
`src/alpha_squad/` is byte-identical to D108.

> **Record gap, stated up front.** This repository contains no D109, D110, D111 or D112 — the
> branch tip before D113 is `b82d2cf` (D108), and `docs/PROJECT_STATE.md` still reads "D109 not
> started". The D112 findings in D113's brief were therefore taken as given and, where cheaply
> checkable, **re-measured here rather than assumed**; §4 reports that they reproduce. The
> "D111 ECR effect" likewise has no record, so §11 compares against **D104's** measured ECR
> effect, which is the ECR number this repository actually holds. See §14.

---

## 1. The exact research question

> Does Alpha's current positional-capacity logic cause meaningful loss of realized draft value,
> particularly late in the draft?

D112 established **leverage**: capacity fires often late, holds Alpha at ~2 kickers, and changes a
meaningful fraction of late picks. Leverage is not value. D113 measures value, and treats "many
picks changed" as evidence of neither harm nor benefit.

---

## 2. What capacity actually is today (questions 1–3)

### 2.1 Which positions have explicit capacity limits

Every position the league can start, and only those. The cap is
`league/roster.py::positional_capacity` — `startable_slots(pos) + max(1, round(bench_size ×
startable_share(pos)))` — derived from the league config alone, never hardcoded per position.
`positional_feasibility_cap` is an alias of it (asserted by `test_league_capacity.py`).

| format | startable slots | **positional capacity (the cap)** | Σ cap | roster_size |
|---|---|---|---|---|
| `target_league` (1QB redraft) | QB 1, RB 4, WR 4, TE 3, K 1, DST 1 | **QB 2, RB 6, WR 6, TE 4, K 2, DST 2** | 22 | 16 |
| `dynasty_1qb` | identical | **identical** | 22 | 16 |
| `legacy_2qb_dynasty` | QB 2, RB 4, WR 4, TE 3 | **QB 3, RB 6, WR 6, TE 5** | 20 | 17 |

Σ cap (22) exceeds `roster_size` (16), so the caps are never *jointly* binding — only individually.

### 2.2 When the penalty activates

One line in `league/draft.py::recommend_draft_pick` (and its mirror in the counterfactual
harness):

```python
cap = positional_feasibility_cap(league, pos)
if cap > 0 and have_at_position[pos] >= cap:
    score *= OVER_CAP_VALUE_MULTIPLIER          # 0.1
```

Three properties matter and are not obvious from the name:

1. **It is count-based and hard, not tapered.** The body *at* the cap is unpenalised; the next one
   is penalised in full. There is no onset curve. (Pinned by
   `tests/unit/test_d113_capacity_audit.py::test_the_penalty_is_hard_rather_than_tapered`.)
2. **It is applied last**, after `roster_fit × confidence × survival`, to the finished score.
3. **It is not a prohibition.** A 0.1× score can still be the highest score on the board, and in
   production it sometimes is — see §5.4.

### 2.3 How large the penalty is

A **90% multiplicative reduction** of the finished score (`OVER_CAP_VALUE_MULTIPLIER = 0.1`). It
stacks with a *second*, softer mechanism that shares capacity's vocabulary and is **not** the
primary arm here: `roster_need`'s depth target is `startable_slots`, past which
`roster_fit_multiplier` floors at 0.7. A third kicker in the target format therefore carries
`0.7 × 0.1 = 0.07×`.

### 2.4 One arithmetic property, raised and then measured to be inert

The multiplier is applied to a **signed** score, so a candidate already scored below zero is moved
*toward* zero — promoted, not penalised, relative to other negative-scored candidates. Across the
**2,450 pick states** in this study the penalty touched **85,960 candidate scorings, 31,780 of
them (37.0%) negative**, so the inversion is real and common at the candidate level.

**It never changes a pick.** The control's top-scoring candidate was negative at **0 of 2,450**
pick states in all three formats, so the promotion never reaches the argmax. This was a D113
hypothesis and the data rejects it; it is recorded here so it does not have to be re-raised.

---

## 3. The counterfactual, and why it is the smallest defensible one

| arm | definition | fields changed vs production |
|---|---|---|
| **C** control | `ScoringVariant.control()` | none |
| **T1** primary | `use_cap_multiplier=False` | **exactly one**: the cap penalty forced to 1.0 |
| **T2** secondary | `+ use_fit_multiplier=False` | two: cap **and** its soft sibling |

Both booleans already existed in the committed harness (`evaluation/decision_counterfactuals.py`,
D83/D86). **D113 wrote no scoring code and invented no capacity rule.** A test asserts that T1
differs from the control in exactly the one field, that no arm defers a position or overrides
demand, and that with nothing over cap the two arms score every candidate identically.

Population, fixed before any run: **seasons 2021–2025** (2020 refused — D95/D96), **slots 1–10**,
three formats, fair `market_consensus_roster_aware` opponents. 50 paired drafts per format per
arm — 450 free-running drafts in total — plus 2,450 matched pick states. The independent unit is the
**season** (k = 5); CIs use t_crit = 2.776, D104's convention.

`legacy_2qb_dynasty` is in the grid as a **structural negative control**: it has no K and no DEF
slot and its board (`dsf`) carries no kickers or defenses at all, so capacity there can bind only
on QB/RB/WR/TE. If the capacity effect were a K/DST effect it would have to vanish there.

---

## 4. Validity checks, all passed before any margin was read

**(a) The control IS the production decision path.** 30 complete drafts (490 pick states) were
played twice — once with every pick made by the real `league/draft.py::recommend_draft_pick`, once
by the control arm — across all three formats and all five seasons. **All 30 rosters identical,
player for player, in draft order.** (`--mode parity`.) `assert_control_reproduces_production`
additionally checks scores, not just the choice.

**(b) Removing the cap does not produce illegal rosters.** Mean unfilled mandatory slots is
**0.000 in every arm and every format**; no draft in any arm left a starting slot empty. The
pre-registered invalidity stop therefore does **not** fire, and no legality rule was invented.

**(c) D112's reported behaviour reproduces.** D112 reported "approximately 2.00–2.06 kickers
despite a capacity of 2". Measured here on the shipped engine: **K = 2.00 exactly in
`target_league`, 2.06 in `dynasty_1qb`** — the stated range, both endpoints. D112's "capacity
penalties fire frequently in rounds 12–16" also reproduces (94.8% of R12–16 states, §5.3).

**(d) Board vintage — a real discrepancy, recorded rather than smoothed over.** This from-source
rebuild lands on combined board vintage `0d52543044fe99d6…`, **not** the
`ca3e2d8af6aa8920…` that every phase from D97 to D108 recorded. The projection layer moved
(`compute_board_vintage` hashes `load_season_projections`, i.e. model output, not the ECR board).
**This does not weaken any D113 contrast** — both arms read the same board within this run, and
the pairing is exact — but it does mean cross-phase *magnitude* comparisons (§11) are approximate.
Per-(series, season) market-board hashes are recorded in every artifact's `provenance` block so a
later phase can tell a board move from a model move.

---

## 5. A. Pick-level changes caused by capacity (questions 4, 6, 7, 8)

Measured at **matched states**: the draft is played by the control and never forks, and at every
one of our pick states the board is additionally scored under T1 and T2. Every comparison is
therefore from an identical starting state.

### 5.1 How often it fires, and how often it changes anything

| format | pick states | penalty fires | **pick changed (T1)** | fires but pick UNCHANGED | T2 changed |
|---|---|---|---|---|---|
| `target_league` | 800 | **248 (31.0%)** | **105 (13.1%)** | **143 (17.9%)** | 199 (24.9%) |
| `dynasty_1qb` | 800 | 201 (25.1%) | 44 (5.5%) | 157 (19.6%) | 150 (18.8%) |
| `legacy_2qb_dynasty` | 850 | 338 (39.8%) | 200 (23.5%) | 138 (16.2%) | 302 (35.5%) |

### 5.2 Question 6 — changed *because of* capacity vs merely scored lower

**Every single changed pick is a state where the penalty fires** (105/105 in `target_league`,
44/44, 200/200). There is no leakage: T1 and the control are identical wherever no position is
over cap, by construction and in fact. So the attribution is exact.

Of the states where the penalty fires, the pick is **unchanged** in **143/248 = 57.7%**
(`target_league`), 157/201 = 78.1% (`dynasty_1qb`), 138/338 = 40.8% (`legacy`). In those states
capacity is pure bookkeeping: it lowers a score without altering a decision.

### 5.3 Question 7 — does capacity ever affect rounds 1–6? **No.**

| format | R1–6 | R7–11 | R12–16 |
|---|---|---|---|
| `target_league` fires | **0 / 300 (0.0%)** | 11 / 250 (4.4%) | 237 / 250 (94.8%) |
| `target_league` picks changed | **0 (0.00%)** | 8 (3.20%) | 97 (38.80%) |
| `dynasty_1qb` fires | **0 / 300** | 4 / 250 (1.6%) | 197 / 250 (78.8%) |
| `dynasty_1qb` picks changed | **0** | 0 | 44 (17.60%) |
| `legacy_2qb_dynasty` fires | **0 / 300** | 53 / 250 (21.2%) | 235 / 250 (94.0%) |
| `legacy_2qb_dynasty` picks changed | **0** | 20 (8.00%) | 154 (61.60%) |

The earliest round at which the penalty fires at all is **round 11** in both 1-QB formats and
round 8 in the 2-QB format. The earliest **changed** pick is round 11 / 12 / 10. In the
free-running drafts the mean first divergence is round **13.5 / 13.6 / 12.7**, minimum 11 / 12 /
10. Capacity is a pure endgame mechanism.

### 5.4 Question 8 — is it a K/DST mechanism? **No: it is mostly a QB mechanism.**

Positions over cap when the penalty fires (counting firing states, a state can have several):

| format | QB | K | WR | DST | TE | RB |
|---|---|---|---|---|---|---|
| `target_league` | **229** | 95 | 3 | 16 | 6 | 0 |
| `dynasty_1qb` | **186** | 57 | 62 | 5 | 1 | 0 |
| `legacy_2qb_dynasty` | **322** | — | 203 | — | 2 | 0 |

In the 1-QB target format the binding cap is overwhelmingly **QB (cap 2)**, then K (cap 2). RB and
WR (cap 6) are never reached. And the cap is not absolute: production drafted an over-cap body
anyway at **10 / 8 / 35** states (all QB in the target format), which is exactly why the shipped
engine sits at 2.08 QB and 2.00 K rather than at a hard 2.00 / 2.00.

---

## 6. G/H. By phase and by position — where the changed picks go

Position flow at T1's changed picks (`target_league`, 105 changed picks):

| position | control took | T1 took | net realized points of the changed bodies |
|---|---|---|---|
| **QB** | 0 | **70** | **+16 198.7** |
| K | 17 | 35 | +1 127.0 |
| TE | 30 | 0 | −3 638.5 |
| DST | 23 | 0 | −2 619.0 |
| RB | 18 | 0 | −2 125.2 |
| WR | 17 | 0 | −2 003.1 |

Read plainly: **capacity's whole job, in the target format, is stopping the engine from spending
rounds 12–16 on a third quarterback.** Without it, 70 of 105 changed picks become QBs.

Roster composition (mean over 50 drafts per arm):

| format | arm | QB | RB | WR | TE | K | DST |
|---|---|---|---|---|---|---|---|
| `target_league` | **C** | 2.08 | 3.22 | 4.96 | 2.38 | **2.00** | 1.36 |
| | T1 | **3.12** | 2.82 | 4.80 | 1.86 | 2.34 | 1.06 |
| | T2 | 3.14 | 2.48 | 5.26 | 1.52 | 2.60 | 1.00 |
| `dynasty_1qb` | **C** | 1.94 | 3.32 | 5.58 | 2.00 | **2.06** | 1.10 |
| | T1 | 2.14 | 3.14 | 5.62 | 1.84 | 2.26 | 1.00 |
| `legacy_2qb_dynasty` | **C** | 3.18 | 4.30 | 6.48 | 3.04 | — | — |
| | T1 | **4.44** | 3.38 | 7.26 | 1.92 | — | — |

---

## 7. B. Realized value of the changed picks — and why this number is a trap

| format | changed picks | mean realized Δ per changed pick | per-draft sum | 95% CI |
|---|---|---|---|---|
| `target_league` | 105 | **+66.1** | **+133.9** | [−60.7, +328.5] |
| `dynasty_1qb` | 44 | +89.1 | +150.8 | [−60.3, +361.9] |
| `legacy_2qb_dynasty` | 200 | −29.4 | −117.7 | [−465.7, +230.3] |

Taken alone this says removing capacity buys **+134 points of realized player value per draft** in
the target format. **It does not, and this is the single most important methodological result in
D113.**

Those +16 198.7 realized points that T1 gains at QB are points scored by **third quarterbacks in a
one-QB league**. They accrue to the roster and never enter a starting lineup. The same substitution
that adds +133.9 points of raw realized value adds **+0.8 points of realized starter value**
(§8) — a conversion rate of **0.6%**.

The instrument that detects this directly is already in the objective family: `total_roster_points`
**rises** when capacity is removed (**+93.8** target, **+56.0** dynasty_1qb, 5 of 5 seasons) while
`season_long` starter value does not move. Starter share of roster points falls from 0.743 to
0.718 (target) and 0.735 to 0.722 (`dynasty_1qb`).

**"Capacity changes many picks" and "the changed picks scored more points" are both true and
neither is evidence that removing capacity is an improvement.** This is exactly the confusion the
brief warned against, and `total_roster_points` is the metric that manufactures it.

---

## 8. C/D/E/F. Final roster realized value — the answer to the research question

50 paired free-running drafts per format per arm. Positive = **removing capacity is better**.

### `target_league` — the primary format

| objective | T1 − C | 95% CI | t | own MDE | seasons | drafts |
|---|---|---|---|---|---|---|
| **D. season-long starter points (PRIMARY)** | **+0.8** | [−46.1, +47.7] | 0.05 | 46.9 | 1W/3L | 8W/28T/14L |
| E. weekly, no foresight | −22.6 | [−92.8, +47.5] | −0.90 | 70.2 | 2W/3L | 12W/9T/29L |
| E. weekly, hindsight | −60.4 | [−153.5, +32.7] | −1.80 | 93.1 | **0W/5L** | 4W/9T/37L |
| bench contribution | −32.2 | [−121.2, +56.9] | −1.00 | 89.1 | 1W/4L | 14W/9T/27L |
| total roster points | **+93.8** | [−37.0, +224.6] | 1.99 | 130.8 | 3W/2L | 26W/9T/15L |

Season-long by season: 2021 −44, 2022 +61, 2023 +0, 2024 −5, 2025 −8.
T2 (cap + fit removed): season-long **−20.6** [−82.2, +40.9]; weekly hindsight **−99.9**
[−208.8, +9.0], 0W/5L.

### `dynasty_1qb`

| objective | T1 − C | 95% CI | t | own MDE | seasons | drafts |
|---|---|---|---|---|---|---|
| **season-long (PRIMARY)** | **+0.9** | [−14.6, +16.4] | 0.16 | 15.5 | 2W/3L | 8W/30T/12L |
| weekly, no foresight | −5.1 | [−27.2, +16.9] | −0.64 | 22.0 | 1W/4L | 6W/26T/18L |
| weekly, hindsight | +0.4 | [−20.6, +21.4] | 0.05 | 21.0 | 3W/2L | 16W/25T/9L |
| total roster points | +56.0 | [−12.6, +124.5] | 2.26 | 68.6 | **5W/0L** | 23W/25T/2L |

### `legacy_2qb_dynasty` — the negative control, and the one resolved effect

| objective | T1 − C | 95% CI | t | own MDE | seasons | drafts |
|---|---|---|---|---|---|---|
| **season-long (PRIMARY)** | **−25.1** | **[−43.1, −7.2]** | **−3.89** | 17.9 | **0W/5L** | 4W/13T/33L |
| weekly, no foresight | −40.1 | [−87.2, +6.9] | −2.37 | 47.1 | 1W/4L | 8W/6T/36L |
| weekly, hindsight | **−60.1** | **[−92.1, −28.1]** | −5.22 | 32.0 | **0W/5L** | 6W/3T/41L |
| bench contribution | **−44.2** | **[−78.7, −9.8]** | −3.56 | 34.5 | **0W/5L** | — |
| total roster points | +3.4 | [−62.4, +69.1] | 0.14 | 65.8 | 2W/3L | 23W/3T/24L |

By season: 2021 −32, 2022 −26, 2023 −6, 2024 −44, 2025 −17. **Removing capacity is worse in every
season, at every objective that prices the lineup, in the one format where capacity cannot touch
K or DST at all.**

**F. The dynasty objective is reported separately from the target objective throughout and is
never pooled with it.** The two dynasty formats disagree in magnitude (`dynasty_1qb` +0.9,
`legacy_2qb_dynasty` −25.1) and that disagreement is informative: the difference between them is
the 2-QB lineup, which is where QB capacity does real work.

### I. Wins and losses

Capacity changes **nothing at all** in a large share of drafts: rosters are identical in
**9/50** (`target_league`), **25/50** (`dynasty_1qb`), **0/50** (`legacy`), and mean players
differing is **1.64 / 0.70 / 2.60 of 16**. Where it does change something, it is a coin flip in
the 1-QB formats and a consistent loss for the treatment in the 2-QB one.

---

## 9. J/K. Confidence intervals and the practical detection floor

The pre-registered rule quoted D97's floor of **172–250 points** for a draft-level contrast.
Applied mechanically, **every contrast in §8 is below it and classifies as UNRESOLVED**, and the
pre-registered consequence — *close capacity as a current research priority* — fires.

**But the honest reading is stronger than the rule required, and it should be recorded as such.**
D97's 172–250 band was derived from contrasts (`PROD − NAIVE`, `ORACLE − PROD`) whose per-season
differences have SDs of 138–201. **A capacity contrast is a different object**: T1 and the control
share 14.4 of 16 picks, so the paired difference has a between-season SD of **12.5–37.8 points**, and
this contrast's own minimum detectable effect at k = 5 is:

| format | own MDE, season-long | D97's quoted floor |
|---|---|---|
| `target_league` | **46.9** | 172–179 |
| `dynasty_1qb` | **15.5** | 210–250 |
| `legacy_2qb_dynasty` | **17.9** | — |

So D113 does not merely fail to detect a capacity effect. **It bounds it.** At 95% confidence the
capacity mechanism is worth between −47.7 and +46.1 points per draft in the target format and
between −16.4 and +14.6 in `dynasty_1qb`. An effect the size of the 172-point floor is **excluded**,
not undetected. The 25-point economic threshold sits *inside* the target-format interval, so
"economically meaningful but invisible" remains possible there; in `dynasty_1qb` even that is
excluded.

The one contrast that **resolves** (CI excluding zero, 0W/5L, t = −3.89) is
`legacy_2qb_dynasty` at −25.1: capacity is worth about **+25 points per draft** there, just at the
economic threshold and an order of magnitude below the detection floor.

---

## 10. What capacity is actually doing today — the mechanism, in one paragraph

In the 1-QB target format, capacity is a **round-11-onward QB brake**. It fires on 229 QB states
and 95 K states out of 800; it never fires before round 11; it changes 13% of picks, all of them
late; and what it prevents is the engine spending its last five picks on a third quarterback whose
points cannot reach the lineup. Its effect on realized **starter** value is +0.8 ± 47 points per
draft — i.e. it costs nothing and buys nothing measurable, because the picks it redirects are
low-leverage endgame picks in both directions. In a 2-QB lineup the same brake is worth a small,
reliable **+25 points**, because there the redirected picks reach a real flex/QB2 slot. The
"kicker" framing is a red herring: K is the *second* position the cap binds on, and the K counts
(2.00 / 2.06) are a symptom of a cap that is a soft 0.1× multiplier rather than a prohibition, not
of a cap that is wrong.

---

## 11. Magnitude comparison with the ECR effect

| lever | format | effect on realized starter value | 95% CI | seasons | verdict |
|---|---|---|---|---|---|
| **ECR ordering** (D104 `Y1 → FP_ECR_Y1`) | `target_league` | **+77.3** | [−44.1, +198.6] | 5W/0L | below floor |
| | `dynasty_1qb` | **−132.1** | [−371.1, +107.0] | 1W/4L | below floor, negative |
| **Capacity removal** (D113 `T1 − C`) | `target_league` | **+0.8** | [−46.1, +47.7] | 1W/3L | bounded, ~zero |
| | `dynasty_1qb` | **+0.9** | [−14.6, +16.4] | 2W/3L | bounded, ~zero |
| | `legacy_2qb_dynasty` | **−25.1** | [−43.1, −7.2] | 0W/5L | resolved, capacity HELPS |

**The capacity lever is roughly two orders of magnitude smaller than the ECR lever** on the target
format's point estimate (+0.8 vs +77.3), and D104 already judged ECR too small to act on. Capacity
is therefore not a candidate for the "small improvements that eventually compound" portfolio: it
has no positive effect to compound, and in one of three formats its removal is a reliable loss.
The comparison is directional only — see §4(d) on the vintage difference, and §14 on the missing
D111 record.

---

## 12. What this does NOT establish

1. **It does not say the cap's value is 0.1 or its level is right.** T1 removes the mechanism; it
   does not sweep the multiplier or the capacity formula. A differently-shaped cap could in
   principle do better; D113 gives no reason to look, because the whole mechanism is worth ~0.
2. **It does not license removing capacity.** T1 is worse on the weekly objective in every format
   and resolved-worse in the 2-QB format, and it raises cap breaches from 10 to 41 drafts
   (target). Removal is neutral-to-harmful, not beneficial.
3. **It says nothing about in-season decisions.** There is no transaction history in this database
   (D86 §6). A late-round body's real option value is realised on waivers, which this benchmark
   cannot see at all — so the weekly-objective losses are a **lower** bound on what capacity
   protects.
4. **The 25-point economic threshold is inside the target-format interval.** "Small but real" is
   not excluded there; "as large as the detection floor" is.
5. **The board vintage differs from D97–D108** (§4d), so §11's cross-phase comparison is
   directional rather than exact.

---

## 13. Decision-rule application, and the answers asked for

| question | answer |
|---|---|
| Plain-English conclusion | Capacity is not costing realized draft value. It is a late-draft QB brake that is close to inert in 1-QB formats and mildly protective in 2-QB. |
| Is it costing realized value? | **No.** +0.8 / +0.9 / −25.1 per draft for *removing* it; the only resolved effect says removal **hurts**. |
| Worth further research? | **No.** Its whole effect is bounded inside ±47 points; there is no headroom to recover. |
| Change anything in production? | **NO.** No ship-quality gate is met, and none is close. |

The pre-registered rule's first branch fires: effect below 172 → UNRESOLVED-or-null → **close
capacity as a current research priority and move on.** §9 strengthens that from "unresolved" to
"bounded near zero". The hypothesis that capacity costs late-draft value is **closed**.

---

## 14. Recommended next research question

**Not another decision-rule ablation.** D97 measured Y1's *entire* decision apparatus at +213.8
against its own MDE of 179.4, and D113 has now measured one of that apparatus's named components
at +0.8 ± 47. The pattern from D97 → D104 → D105 → D113 is consistent: **individual decision-layer
mechanisms are each worth a few points, and the floor for detecting them is ~172 only because the
contrasts previously chosen had huge between-season variance.**

D113's own methodology suggests the more useful next question, and it is a *measurement* question
rather than a mechanism question:

> **Which decision-layer contrasts are actually paired tightly enough to be resolvable, and what
> is the real power frontier of this benchmark?**
>
> D113's capacity contrast has an own-MDE of **15.5–46.9 points**, four to sixteen times finer
> than the 172–250 band the program has treated as a hard floor since D97 — because the arms share
> most of their picks. D107 §G names "the 25-to-250-point blind band" as the program's single
> largest unresolved issue and asserts the floor "cannot be lowered". **D113 is a
> counterexample to that assertion for tightly-paired contrasts**, and the question of which
> candidates admit such a pairing is worth one phase of work, because it would decide whether the
> blind band is a property of the data or of the contrast design.

A concrete, cheap first step: re-express D104's ECR arm and D97's `PROD − NAIVE` decomposition as
**matched-state** contrasts (score both arms at the *control's* states, never forking) and measure
whether their own-MDEs collapse the same way capacity's did. If they do, several closed
"unresolved" findings become resolvable without new seasons — which is the only lever D97 said was
unavailable.

Second priority, explicitly **lower**: the weekly objective is where every capacity signal in D113
is negative and where two contrasts resolve. If a small compounding portfolio is ever assembled,
the weekly objective — not season-long starter points — is the metric that can see the components.

---

## 15. Reproduction, provenance, and what changed

```bash
uv run python scripts/research/d113_capacity_audit.py --mode mechanism --out <dir>
uv run python scripts/research/d113_capacity_audit.py --mode parity  --slots 1-2 --out <dir>
uv run python scripts/research/d113_capacity_audit.py --mode matched --verify-control-every 0 --out <dir>
uv run python scripts/research/d113_capacity_audit.py --mode paired  --out <dir>
uv run python scripts/research/d113_capacity_audit.py --mode report  --out <dir>
uv run pytest tests/unit/test_d113_capacity_audit.py
```

| item | value |
|---|---|
| board vintage (combined, 2021–2025) | `0d52543044fe99d6d03a7592190c070bde36a6f465041e2304acdab5b35891e0` |
| per-season | 2021 `40a000b3…` 2022 `139658bf…` 2023 `5f64d6c1…` 2024 `6bea3ee6…` 2025 `e7a115a3…` |
| matches D97–D108's `ca3e2d8a…` | **NO** — see §4(d) |
| upstream board / idmap sha256 | `e270d790…` / `36016b92…` (rebuilt from source in this container) |
| opponent field | `market_consensus_roster_aware` |
| uncertainty model | `uncertainty_catboost_v2` |
| grid | 3 formats × 5 seasons × 10 slots × 3 arms = 450 free-running drafts; 2,450 matched pick states; 30 parity drafts (490 picks) |

**Files changed by D113 — research only:**

| file | status |
|---|---|
| `scripts/research/d113_capacity_audit.py` | **new** — the runner and the pre-registration |
| `tests/unit/test_d113_capacity_audit.py` | **new** — 26 tests pinning the arms and the rule |
| `docs/D113_CAPACITY_AUDIT.md` | **new** — this report |
| `docs/DECISIONS.md`, `docs/PROJECT_STATE.md` | appended |
| `src/alpha_squad/**` | **unchanged — byte-identical to D108** |

The runner is imported by no production path and opens the database read-only.

---

## Appendix — the D109–D112 record gap

D113's brief cites D112 findings. **This repository contains no record of D109, D110, D111 or
D112.** The branch tip before D113 is `b82d2cf` ("D108: program closeout"), `docs/PROJECT_STATE.md`
and `docs/DECISIONS.md` both end with "D109 not started", and there is no `docs/D109*`–`docs/D112*`
file and no such commit on any branch.

Consequences, stated rather than worked around:

* **D112's findings were treated as a hypothesis to re-measure, not as established fact.** The two
  that are cheaply checkable — the ~2.00–2.06 kicker count and frequent firing in rounds 12–16 —
  **both reproduce exactly** (§4c), which is good evidence D112 was measured on a comparably
  behaving engine. D112's "capacity changes a meaningful fraction of late picks" also reproduces
  (13.1% of all picks, 38.8% of R12–16 picks).
* **"The D111 ECR effect" has no record here.** §11 therefore compares against **D104**'s measured
  ECR effect (+77.3 target / −132.1 dynasty_1qb), which is the ECR result this repository holds.
  If D111 re-measured ECR and got a different number, §11's comparison should be re-read against
  it; the *conclusion* (capacity is far smaller than ECR, and ECR was already too small) is robust
  to any plausible D111 value, because D113's capacity effect is bounded inside ±47 points.
* Whoever holds the D109–D112 work should land it, for the same reason D92 exists: an uncommitted
  runner is why D88–D90 are unreproducible.
