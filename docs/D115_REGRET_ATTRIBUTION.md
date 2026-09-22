# D115 — Where does Alpha's ~135 points of per-pick oracle regret go?

**Headline: it is not a valuation problem and it is not mostly a positional-preference problem.
Roughly half of the measured regret is SEQUENCING — at 47% of the regret (target format) Alpha
could have had BOTH its own player and the oracle's, in either order, and simply took them in the
wrong one. Of what remains, the dominant axis is information, not decision rule: perfect
information recovers 73.5% of the regret, while every preseason-available arm in the repository
recovers between −0.3% and +2.7%, all with intervals spanning zero.**

**No production change. No new model, feature, weight or arm. No tuning. Nothing ships.**
`src/alpha_squad/` is byte-identical to D108.

---

## 1. Plain-English conclusion

At the average production pick Alpha leaves **142.4** realized starter points on the table in
`target_league` and **127.0** in `dynasty_1qb` (D103 published 134.8 on the older vintage — this
reproduces it). Splitting that by what kind of mistake it was:

* **Wrong position, not wrong player.** 74% of the regret sits on picks where the oracle's best
  player was at a *different* position from Alpha's. Only 26% is "right position, worse player".
* **But most of that is not really a positional disagreement.** On **60%** of picks, had Alpha
  taken the oracle's player, its *own* pick would still have been on the board at its next turn —
  and on **71%** of picks the reverse also holds. **Both conditions hold simultaneously on picks
  carrying 47.3% of all regret**: the two players were not in competition at all, and the entire
  loss is ordering.
* **What is left is an information gap, not a rule gap.** The full-information arm (`ORACLE_Y1`)
  recovers **73.5%** of the per-pick regret. Destroying Y1's within-position ordering entirely
  (`L4`, a uniform permutation) costs only **−23.4**. So Y1's ordering is worth about 23 points
  above random while perfect information is worth about 105 above Y1 — Y1 has captured roughly
  **18%** of the available within-position ordering information, and no existing arm moves that.
* **Early picks are the most expensive per pick** (R1–6: 170.4/pick, 45% of all regret; rounds
  1–3 alone: 176.5/pick) but regret is **broadly distributed, not a few disasters**: gini 0.31,
  median 131 against a mean of 142, and the worst 1% of picks hold only 2.6% of the total.
* **WR is the single largest positional source** (33% of regret in target, 40% in dynasty), and
  **WR→RB is the largest single cross-position flow** (45 picks, 7,699 points; 47 picks, 8,002 in
  dynasty) — Alpha took a receiver where the oracle wanted a back.

---

## 2. "Where the ~135 points/pick goes" — the ranked attribution table

D103's grid, unchanged: 2021–2025 × slots (1, 4, 7, 10) × 16 rounds × both 1-QB formats.
**320 audited picks per format, 20 drafts each, mean slate 21.7 / 21.3 candidates.**

### 2.1 Which "regret" — a definitional correction

The brief defines regret as `oracle player realized value − Alpha player realized value`. **That
is not the quantity the ~135 figure measures.** D103's regret — the one that equals ~135 — is a
roster-value quantity under a common continuation:

    regret(s) = V(rollout after the oracle's pick) − V(rollout after Alpha's pick)

Both are reported here; every attribution table is built on the roster form, and a test pins that.

| format | PRIMARY `regret_roster` | 95% CI | MDE | SECONDARY `regret_raw` (the brief's formula) | roster / raw |
|---|---|---|---|---|---|
| `target_league` | **142.4**/pick, total 45,558 | [+88.8, +195.9] | 53.6 | 117.1/pick, total 37,484 | 1.22 |
| `dynasty_1qb` | **127.0**/pick, total 40,638 | [+82.5, +171.5] | 44.5 | 129.7/pick, total 41,493 | 0.98 |

Worth noting against D114: there, the raw metric *overstated* value by 9× (conversion 0.109),
because ECR's changed picks were bench bodies. Here the two agree to within ±22%, because the
oracle's choice is a player who actually enters the lineup. **The raw metric is not always wrong —
it is unreliable, and which way it errs depends on whether the substituted player starts.**

### 2.2 The ranked table — `target_league` (PRIMARY)

A and B are disjoint and exhaustive. C is an **overlay**, not a fourth bucket, because timing
genuinely overlaps both; its intersection with A and B is stated rather than forced.

| rank | source | picks | % picks | total regret | per pick | **% of regret** | 95% CI on the share |
|---|---|---|---|---|---|---|---|
| **1** | **B — WRONG POSITION** | 228 | 71.2% | 33,776 | 148.1 | **74.1%** | [63.0, 85.5]% |
| **2** | **A — WRONG PLAYER, RIGHT POSITION** | 92 | 28.8% | 11,783 | 128.1 | **25.9%** | [14.5, 37.0]% |
| — | D — unclassified | 0 | 0.0% | 0 | — | 0.0% | — |

| overlay (cross-cuts A and B) | picks | % of non-final picks | **% of regret** | overlap A | overlap B |
|---|---|---|---|---|---|
| **C1** oracle's player survives to my next pick | 214 | 71.3% | **68.2%** | 53 | 161 |
| **C2** my player survives if I take the oracle's | 180 | 60.0% | **56.3%** | 41 | 139 |
| **C1 ∧ C2 — pure sequencing, nothing contested** | **156** | **52.0%** | **47.3%** | — | — |

`dynasty_1qb`: B 74.6% [67.3, 82.5], A 25.4% [17.5, 32.7]; C1 75.4%, C2 58.2%,
**C1 ∧ C2 = 52.2% of regret**. The pattern replicates in both formats.

**C2 was measured wrong on the first pass and is corrected here.** The naive form — "is Alpha's
own player in the pool at the next pick" — is vacuously False at every pick in every draft,
because Alpha removed him by drafting him; it returned 0 of 300 and measured nothing. C2 is now
the counterfactual: *had Alpha taken the oracle's player, would its own choice have survived the
real opponent sequence to Alpha's next turn?* A regression test pins the corrected form.

---

## 3. Breakdown by position and round

### 3.1 By position Alpha actually drafted (`target_league`)

| position | picks | total regret | per pick | **% of regret** | A% | B% |
|---|---|---|---|---|---|---|
| **WR** | 99 | 15,119 | 152.7 | **33.2%** | 42% | 58% |
| RB | 66 | 8,159 | 123.6 | 17.9% | 54% | 46% |
| QB | 42 | 6,980 | **166.2** | 15.3% | 9% | 91% |
| TE | 46 | 6,739 | 146.5 | 14.8% | 7% | 93% |
| K | 40 | 5,049 | 126.2 | 11.1% | 0% | 100% |
| DST | 27 | 3,512 | 130.1 | 7.7% | 0% | 100% |

`dynasty_1qb` agrees on the ranking: WR 39.9%, RB 20.0%, QB 14.9% (159.1/pick), TE 10.3%,
K 10.1%, DST 4.9%.

Read carefully: **K and DST regret is 100% category B in both formats** — the oracle never wants a
different kicker, it wants a different *position*. That is a restatement of D113's finding that
the late-round K/DST picks are low-leverage, now with a price attached (18.8% of all regret in
target, 15.0% in dynasty).

### 3.2 By round and phase (`target_league`)

| phase (brief's) | picks | total | per pick | % of regret | A% | B% |
|---|---|---|---|---|---|---|
| **R1–6** | 120 | 20,449 | **170.4** | **44.9%** | 35% | 65% |
| R7–11 | 100 | 12,988 | 129.9 | 28.5% | 22% | 78% |
| R12–16 | 100 | 12,121 | 121.2 | 26.6% | 14% | 86% |

D103's own split, for comparability: EARLY 1–5 **173.8**/pick (38.1%), MIDDLE 6–10 135.4 (29.7%),
LATE 11–16 122.0 (32.1%) — **D103's "regret is concentrated EARLY" reproduces.**

Per round, the most expensive are **R2 (188.5), R1 (177.9), R5 (171.5), R4 (167.7), R3 (163.1)**;
the cheapest are R7 (113.1) and R13 (116.2). The A-share falls monotonically with phase (35% →
22% → 14%): **early mistakes are more often "the right position, the wrong player"; late mistakes
are almost entirely positional.**

### 3.3 Rounds 1–3 specifically (highest leverage)

| format | picks | per pick | % of all regret | 95% CI | category A share |
|---|---|---|---|---|---|
| `target_league` | 60 | **176.5** | 23.2% | [+117.2, +235.8] | 22.0% |
| `dynasty_1qb` | 60 | **178.2** | 26.3% | [+83.3, +273.1] | 22.6% |

The first three rounds are 18.75% of picks and carry 23–26% of the regret — expensive per pick,
but **not** where most of the total sits. Three-quarters of the regret is in rounds 4–16.

### 3.4 RB/WR/TE cross-position mistakes

| flow (Alpha took → oracle wanted) | `target_league` n / regret | `dynasty_1qb` n / regret |
|---|---|---|
| **WR → RB** | **45 / 7,699** | **47 / 8,002** |
| TE → RB | 21 / 2,918 | 12 / 1,368 |
| RB → WR | 18 / 2,761 | 15 / 2,275 |
| TE → WR | 15 / 2,691 | 7 / 950 |
| RB → TE | 7 / 925 | 4 / 461 |
| WR → TE | 4 / 438 | 13 / 1,604 |
| **all RB/WR/TE cross** | **110 picks, 38.3% of regret** | **98 picks, 36.1% of regret** |

The flex triangle alone accounts for over a third of all regret, and it is **asymmetric**: Alpha
takes a WR where the oracle wants an RB about 2.5× more often than the reverse, in both formats.

### 3.5 Concentration — broad, not a few disasters

| | `target_league` | `dynasty_1qb` |
|---|---|---|
| gini | 0.308 | 0.312 |
| median vs mean | 131.0 vs 142.4 | 106.9 vs 127.0 |
| top 1% of picks | 2.6% of regret | 3.0% |
| top 5% | 11.8% | 13.5% |
| top 10% | 21.3% | 23.6% |
| top 25% | 44.7% | 45.7% |
| picks above 2× mean | 21 of 320 | 25 of 320 |
| picks below D114's 13.4-point resolution | **13 of 320** | 10 of 320 |

**Regret is broadly distributed.** There is no small set of catastrophic misses to fix; the top
decile holds about a fifth. Only ~4% of picks are near-optimal.

### 3.6 Component associations — CORRELATION ONLY

Every component correlates with round, and regret varies strongly by round, so the raw
correlation is largely a round effect wearing a component's name. Within-round means are reported
beside it, and **none of this is causal evidence**.

| component | `target` raw r | `target` within-round r | `dynasty` raw r | `dynasty` within-round r |
|---|---|---|---|---|
| projection | 0.240 | **0.108** | 0.356 | 0.035 |
| marginal starter value | 0.241 | −0.052 | 0.403 | −0.041 |
| score | 0.248 | −0.018 | 0.371 | −0.203 |
| vorp | 0.226 | −0.053 | 0.314 | −0.157 |
| confidence (risk multiplier) | 0.270 | **0.175** | 0.161 | −0.154 |
| roster fit / roster need | 0.034 | −0.187 | 0.181 | −0.114 |
| opportunity cost | 0.143 | −0.030 | −0.034 | −0.117 |
| survival probability | −0.095 | 0.021 | −0.106 | 0.058 |

**Every raw correlation collapses or reverses once round is held fixed, and the two formats
disagree in sign on five of eight components.** No component is implicated. The one mildly
consistent residual is `projection` (+0.11 / +0.04): picks on higher-projected players carry
slightly more regret within a round — which is what "the top of the board is where the mistakes
are expensive" looks like, not evidence that the projection term is at fault.

---

## 4. Existing-arm regret recovery

Each arm is asked, at every one of Alpha's own pick states, what it would pick; the substitution
is valued by one rollout under the **same** shipped continuation on **Y1's** board. Recovery is
`mean(delta) / mean(regret_roster)`. Arms' boards are used only to *choose*, never to *score*.

### `target_league` — denominator 142.4 points/pick

| arm | % picks changed | delta/pick | 95% CI | MDE | **recovery** | seasons |
|---|---|---|---|---|---|---|
| **Y1** (null check) | 0.0% | **0.00** | — | — | 0.0% | — |
| FP_ECR_Y1 | 55.9% | +1.88 | [−8.8, +12.6] | 10.70 | **1.3%** | 2+/3− |
| X2 (affine calibration) | 11.6% | +1.44 | [−7.5, +10.4] | 8.92 | **1.0%** | 2+/1− |
| X3 (rank-band calibration) | 8.8% | −0.47 | [−4.3, +3.3] | 3.81 | −0.3% | 1+/2− |
| L1 (ladder α=0.25) | 70.0% | +3.80 | [−11.9, +19.5] | 15.66 | 2.7% | 2+/3− |
| L2 (α=0.50) | 87.2% | −4.81 | [−8.8, −0.9] | 3.96 | −3.4% | 0+/5− |
| L3 (α=0.75) | 87.2% | +4.30 | [−12.4, +21.0] | 16.72 | 3.0% | 3+/2− |
| L4 (α=1.00, uniform permutation) | 98.1% | **−23.40** | [−42.1, −4.7] | 18.67 | −16.4% | 0+/5− |
| **ORACLE_Y1** (full information) | 92.2% | **+104.65** | [+52.6, +156.7] | 52.02 | **73.5%** | **5+/0−** |

### `dynasty_1qb` — denominator 127.0 points/pick

| arm | % changed | delta/pick | 95% CI | recovery | seasons |
|---|---|---|---|---|---|
| Y1 | 0.0% | 0.00 | — | 0.0% | — |
| FP_ECR_Y1 | 68.8% | −4.03 | [−14.8, +6.7] | −3.2% | 1+/4− |
| X2 | 15.0% | +3.40 | [−5.2, +12.0] | 2.7% | 2+/1− |
| X3 | 12.5% | +1.92 | [−3.1, +7.0] | 1.5% | 2+/1− |
| L1 | 71.9% | −13.21 | [−26.4, +0.0] | −10.4% | 0+/5− |
| L2 | 84.7% | −6.26 | [−17.4, +4.9] | −4.9% | 1+/4− |
| L3 | 89.7% | −13.52 | [−32.5, +5.5] | −10.6% | 1+/4− |
| L4 | 98.1% | **−27.58** | [−47.2, −7.9] | −21.7% | 0+/5− |
| **ORACLE_Y1** | 93.8% | **+88.35** | [+50.1, +126.6] | **69.6%** | **5+/0−** |

**Reading these.**

1. **The Y1 null arm returns exactly 0.00 in both formats**, which is the harness validation: the
   runner raises if it does not.
2. **No preseason-available arm recovers anything.** ECR, X2 and X3 all sit between −3.2% and
   +2.7% with intervals spanning zero, and the signs disagree across formats. D114's ECR figure
   (+1.32/pick) reproduces here as +1.88 on a different grid — consistent.
3. **The ladder is a downside bound, and it is a shallow one.** Scrambling Y1's within-position
   ordering completely costs only −23.4 / −27.6. Combined with `ORACLE_Y1`'s +104.7 / +88.4:
   **Y1 sits about 23 points above random ordering and about 105 points below perfect ordering, so
   it has captured roughly 18% of the within-position information available** (21% in dynasty).
   L1–L3 are non-monotone and mostly noise, which is expected — a single seed at k = 5.
4. **ORACLE_Y1 does not recover 100%** (73.5% / 69.6%) because it is the Y1 *rule* reading
   realized points, while the per-pick oracle is an unconstrained slate maximiser. The ~27% gap is
   what the *rule* discards even under perfect information.

---

## 5. What remains unexplained

1. **The 26% of regret in category A has no identified cause.** It is within-position player
   selection, no existing arm moves it, and the component associations do not implicate any term.
2. **ORACLE_Y1's residual 27%** — value that perfect information plus the Y1 rule still cannot
   reach — is unattributed. It is a *rule* residual by construction, but D115 did not decompose it.
3. **Whether the sequencing finding is actionable is NOT established.** C1 ∧ C2 says both players
   were obtainable in either order; it does **not** say a policy exists that could pick the order
   correctly *ex ante*. The oracle knows outcomes; a real drafter does not. D115 measures the size
   of the prize, not its reachability.
4. **Both formats are 1-QB with identical lineups.** Nothing here is established for the 2-QB
   format, which D113 showed behaves differently.
5. **The vintage is not D103's.** This run is `0d525430…`; D103/D104/D105 recorded `ca3e2d8a…`.
   Mean regret reproduces at 142.4 against D103's published 134.8, which is close but not
   identical; every cross-phase comparison here is labelled accordingly.
6. **k = 5 seasons.** The share intervals are ±11 percentage points wide; the A/B split is
   resolved, the finer cuts (per-round, per-flow) are descriptive.

---

## 6. Recommended next research question

The largest **well-supported** source is not a position or a round — it is the sequencing finding,
because it is the only one that is both large (47% of regret) and mechanically specific.

> **Is any part of the C1 ∧ C2 sequencing regret reachable by a policy that cannot see outcomes?**
>
> On picks carrying 47.3% of the measured regret, Alpha and the oracle wanted two different
> players and *both were obtainable* — the loss is purely which came first. The question is
> whether the ordering can be decided from preseason-available information. The repository already
> contains the instrument (`league/opportunity_cost.py`'s survival term and opponent replay are
> exactly a "will he last" model, and D97 measured them as calibrated-but-understated:
> corr 0.73–0.88, magnitude understated 20–65%, moving 9% of picks). The measurement is: at each
> C1 ∧ C2 pick, does Alpha's own survival estimate already rank the two players' availability
> correctly, and how much of the 47% would a policy that acted on it have captured?
>
> This is attribution, not optimisation: it asks whether the information needed to fix the
> ordering was already on the board, before anyone proposes changing a term.

Two explicitly lower-priority follow-ups, recorded so they are not lost: decomposing
`ORACLE_Y1`'s 27% rule residual, and the WR→RB asymmetry (2.5:1 in both formats, 7,699/8,002
points) — the latter is a *description* of a bias whose cause is not established, and D97's
per-position projection bias table (QB +65.2, WR +35.3, TE +35.2) is the obvious place it would
come from.

**Nothing here is a ship candidate.** Every preseason-available arm recovers ~0% of this regret,
and D115 proposes no new one.

---

## 7. Tests, provenance and what changed

```bash
uv run python scripts/research/d115_regret_attribution.py --mode audit  --out <dir>
uv run python scripts/research/d115_regret_attribution.py --mode regret --out <dir>   # ~54 min
uv run python scripts/research/d115_regret_attribution.py --mode timing --out <dir>
uv run python scripts/research/d115_regret_attribution.py --mode arms   --out <dir>   # ~14 min
uv run python scripts/research/d115_regret_attribution.py --mode report --out <dir>
uv run pytest tests/unit/test_d115_regret_attribution.py
```

| item | value |
|---|---|
| HEAD at run time | `aa2e85821c98d40de37b475c68592c68fe208379` (D114) |
| board vintage, combined 2021–2025 | `0d52543044fe99d6d03a7592190c070bde36a6f465041e2304acdab5b35891e0` |
| per season | 2021 `40a000b3…` 2022 `139658bf…` 2023 `5f64d6c1…` 2024 `6bea3ee6…` 2025 `e7a115a3…` |
| matches D103/D104/D105's `ca3e2d8a…` | **NO** |
| upstream board / idmap sha256 | `e270d790…` / `36016b92…` |
| uncertainty model / shipped tier / objective | `uncertainty_catboost_v2` / `L0` / `season_long` |
| opponent field | `market_consensus_roster_aware` |
| grid | 2 formats × 5 seasons × 4 slots × 16 rounds = **640 audited picks**, ~13,900 rollouts |

**Files changed by D115 — research only:**

| file | status |
|---|---|
| `scripts/research/d115_regret_attribution.py` | **new** — audit, regret, timing, arms, report |
| `tests/unit/test_d115_regret_attribution.py` | **new** — 52 tests |
| `docs/D115_REGRET_ATTRIBUTION.md` | **new** — this report |
| `tests/unit/test_d114_matched_state.py` | **fixed** — see below |
| `docs/DECISIONS.md`, `docs/PROJECT_STATE.md` | appended |
| `src/alpha_squad/**` | **unchanged — byte-identical to D108** |

### Two defects found and fixed during D115

1. **D114's NAIVE guard broke itself on commit.** `test_no_naive_arm_exists_in_the_checkout`
   searched every `*.py` in history for the string "NAIVE". D114's own runner and test discuss
   NAIVE's absence in prose, so committing D114 made the guard match itself. It passed in D114
   only because those files were still uncommitted when the suite ran. The guard now excludes the
   files whose purpose is to document the absence, and asserts each exclusion still contains the
   string — so a stale exclusion is itself a failure.
2. **D115's first C2 was vacuous.** "Is Alpha's own player in the pool at the next pick" is
   necessarily False, because Alpha drafted him; it measured 0 of 300 picks. Replaced with the
   counterfactual in §2.2, with a regression test.
