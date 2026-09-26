# D121 — Value term vs survival urgency in the perfect-projection wrong-position gap

**Headline: it is mainly the value term, not survival urgency.** In the early-round (R1–6) states
where the corrected perfect-projection rule takes an RB but the per-pick oracle wanted a WR or a
QB, the value term (MSV + DA-VORP) *itself* prefers the RB in **16 of 23** target states and
**9 of 15** dynasty states. That carries **66% / 60%** of this population's regret. Survival
urgency alone overturns a value term that was pointing the right way in only **3 of 23** and
**1 of 15** states (**15% / 11%** of the regret).

The one mechanism that is reproducible *and* distinguishable is **RB → QB**, where the value term
prefers the RB in **6 of 7 states in both formats**. There, the RB's MSV is its full projection
because the RB slot is empty (7/7). The QB's MSV is only an *upgrade* margin because a QB is
already rostered (6/7). So MSV favours the RB by **+75 (target) / +132 (dynasty)** points although
the QB scored 97 / 40 points *more*. DA-VORP adds a further push, from a QB replacement level
**129 / 88 points** higher than the RB's.

**No component meets the pre-registered bar for a rule-experiment candidate.** Neutralising any
single one gives no CI that excludes zero; the population is 23 + 15 states. **Diagnostic only;
nothing ships.**

`src/alpha_squad/` byte-identical (tree `55e763e8…`).

---

## Executive conclusion

* **Q1 — Does the value term rank Alpha's RB above the oracle's WR/QB when one-step roster value
  says the oracle's player is better? Yes, in most of these states.** Value prefers the RB while
  one-step value prefers the oracle in **13 of 23** target states (**962** of 1,320 primary regret,
  73%). In dynasty it is **9 of 15** (**820** of 1,357, 60%). Counting all states where value
  prefers the RB, it is 16 / 23 and 9 / 15. The disagreement is **near-unanimous for RB → QB** (6/7
  both formats) and **mixed for RB → WR** (10/16 target, 3/8 dynasty).
* **Q2 — Does survival urgency cause additional wrong-position decisions beyond the value term?
  Rarely, on its own.**
  * **Survival alone:** where the value term prefers the oracle but the rule still picks the RB
    (target 7 states, dynasty 6), neutralising only survival flips **3 of 7** and **1 of 6**. On
    those states that recovers **+193** and **+151** points (43% / 28% of their regret), and
    +31 / +104 on the weekly objective.
  * **Survival as a reinforcer:** where the value term already prefers the RB, survival pushes
    the same way in **10 of 16** / **6 of 9**.
  * **Survival across the whole population:** neutralising it gives +10.0 pts/state, CI [−11.5,
    +34.3], MDE 22.9 (target). That is not resolved.
* **Q3 — How much of the ~13% residual is attributable to each?** This population carries **23.1%**
  (target) and **25.2%** (dynasty) of ARM 4's regret, i.e. **~3.0% / 3.2% of all per-pick regret**.
  Within it, per the pre-registered classes:

| attribution | target: states / regret / % of population | dynasty | % of ARM 4 regret (target / dynasty) |
|---|---|---|---|
| **value term prefers the RB** (classes 1, 2-other, 2-survival) | **16 / 873 / 66%** | **9 / 820 / 60%** | **15.3% / 15.2%** |
| of which **survival is the largest amplifier** (class 2-survival) | 4 / 621 / 47% | 1 / 231 / 17% | 10.9% / 4.3% |
| **correct value overturned by survival alone** (class 3) | **3 / 193 / 15%** | **1 / 151 / 11%** | **3.4% / 2.8%** |
| correct value overturned by roster fit alone (class 4) | 0 | 1 / 86 / 6% | 0 / 1.6% |
| **combination** (no single component flips it) (class 5) | 4 / 254 / 19% | 4 / 300 / 22% | 4.5% / 5.6% |

  Under the pre-registered A–G mapping, **B (survival)** includes class 2-survival. On that
  mapping B carries 62% (target) of the population, because survival is the largest *amplifier* in
  four high-regret states. **But in those four states the value term itself already prefers the
  RB, and neutralising survival alone flips none of them.** The strict survival share, where
  removing survival alone changes the answer, is class 3: 15% / 11%. Both readings are reported;
  the strict one is the defensible one.
* **Q4 — Next question (§8).** In the RB → QB states, does MSV's empty-slot construction overvalue
  the RB relative to the starter the continuation would otherwise field in that slot?

---

## 1. Reproduction (stop condition)

| check | result |
|---|---|
| states re-walked (D115 replay) | **640** (320 per format) |
| ARM 4 pick recomputed = D120's stored ARM 4 pick | **640 / 640** |
| ARM 4 one-step value recomputed = D120's stored value (1e-6) | every included state |
| oracle one-step value recomputed = D115's stored value (1e-6) | every included state |
| re-ranking from factors reproduces the engine's pick | every included state (asserted) |
| exact value_base (MSV + projection − draft-aware level) = engine-implied value_base | every candidate on every included board (1e-6; 0.051 where confidence 0 hides it) |

The "oracle" is D115/D120's per-pick oracle (the slate maximiser whose regret D120 decomposed),
not the ORACLE_Y1 arm. The rule is D120's ARM 4: perfect projections, recomputed replacement
levels, and confidence recomputed with M6's own formula. L0 has no legality restriction and the
VORP weight is 1.0; both are asserted, and both are what make the re-ranking exact.

## 2. Population

| | target | dynasty |
|---|---|---|
| **PRIMARY RB → WR** (R1–6) | 16 states, regret 1,089 | 8 states, regret 901 |
| **PRIMARY RB → QB** (R1–6) | 7 states, regret 231 | 7 states, regret 456 |
| primary total | **23 / 1,320 = 23.1%** of ARM 4 regret | **15 / 1,357 = 25.2%** |
| CONTEXT (reverse: WR → RB, QB → RB) | 7 / 926 = 16.2% | 9 / 814 = 15.1% |

**Small samples.** Seasons are uneven. Target: 2 / 7 / 8 / 4 / 2 states in 2021–2025. Dynasty:
1 / 8 / 6 / 0 / 0. Dynasty therefore has only three seasons with any primary state, and its
season-clustered intervals are correspondingly wide.

## 3. Q1 — value term vs one-step roster value (the 2×2)

`target_league`, primary, season-long one-step:

| | one-step prefers ORACLE | one-step prefers RB | one-step tie |
|---|---|---|---|
| **value prefers RB** | **13 (57%)** · regret **962** · score gap +151 · value gap +87 · one-step gap −74 | 1 · −89 | 2 · 0 |
| **value prefers ORACLE** | 7 (30%) · regret 447 · score gap +79 · value gap −33 · one-step gap −64 | 0 | 0 |

`dynasty_1qb`: **value prefers RB / one-step prefers oracle: 9 (60%), regret 820**, score gap +291,
value gap +179, one-step gap −91. Value prefers oracle: 6 (40%), 537.

One-step value prefers the oracle *by construction* wherever the RB is inside the oracle's slate,
since the oracle is the slate maximiser. The 3 target cells outside that column are RB picks
outside the slate. **Under the weekly objective, where the oracle is not the maximiser, the
disagreement roughly halves:** value prefers RB / weekly prefers oracle falls to 7 (target) and 5
(dynasty), and weekly prefers the RB in 7 and 4 of the value-prefers-RB states. Part of the RB→WR
"error" depends on the season-long objective.

## 4. Value-term decomposition (MSV vs DA-VORP)

| primary flow | n | projection gap RB − O | **MSV** prefers RB | MSV gap | MSV = projection (RB / O) | **DA-VORP** prefers RB | DA-VORP gap | level gap (O − RB) | value_base prefers RB | regret |
|---|---|---|---|---|---|---|---|---|---|---|
| target RB → QB | 7 | **−96.7** | **6** | **+75.2** | **7 / 1** | 6 | +31.9 | **+128.6** | **6** | 231 |
| target RB → WR | 16 | +14.4 | 10 | +14.4 | 16 / 16 | 14 | +31.7 | +17.2 | 10 | 1,089 |
| dynasty RB → QB | 7 | **−39.8** | **6** | **+132.1** | **7 / 1** | 7 | +48.5 | **+88.2** | **6** | 456 |
| dynasty RB → WR | 8 | +2.7 | 3 | +2.7 | 8 / 8 | 7 | +20.0 | +17.3 | 3 | 901 |

On the whole primary population (target / dynasty):
* MSV disagrees with one-step value on 15 / 9 states (regret 962 / 820).
* DA-VORP disagrees on 21 / 14 states (1,196 / 1,206). It prefers the RB almost always, because
  RB's draft-aware level is lower.
* value_base disagrees on 15 / 9 states (962 / 820).

**The MSV "empty slot = full projection" property, tested as the brief asks:**
* **RB → QB (both formats, 6 of 7 each).** The RB fills an empty slot, so its MSV is its full
  projection. The QB arrives when a QB is already rostered, so its MSV is only the upgrade over
  the current starter. MSV therefore prefers the RB by +75 / +132 even though the QB scored 97 /
  40 more points, and one-step roster value prefers the QB. **This is a ranking disagreement the
  construction produces**, in a population of 7 + 7 states. It is not yet called a defect: its
  materiality (4.0% / 8.5% of ARM 4 regret) and its mechanism (the slot the continuation would
  otherwise fill) are untested (§8).
* **RB → WR.** Both slots are empty (16/16, 8/8), so MSV simply equals projection and prefers
  whichever player scored more. There the RB often *did* score more (+14.4 target). The oracle
  still prefers the WR because of what the continuation builds afterwards: a roster-construction
  effect, not a quality misjudgement.

## 5. Neutralisation arms (one component at a time, whole board re-ranked; primary population)

"Pair → O" means the pairwise order flips toward the oracle. "New = O" means the whole-board re-rank
picks the oracle's player. Δ is realized one-step value vs ARM 4, per state. CI is season-clustered;
the MDE is its half-width. "Recovered" is Σ Δ as a share of ARM 4's total regret.

**`target_league`** (23 states):

| neutralised | picks changed | pair → O | new = O | new = other | improved / worsened | Δ / state | season CI | MDE | weekly Δ / state | recovered |
|---|---|---|---|---|---|---|---|---|---|---|
| survival | 5 | 3 | 3 | 2 | 4 / 1 | **+10.0** | [−11.5, +34.3] | 22.9 | −5.8 [−25.1, +13.5] | +4.0% |
| roster fit | 4 | 2 | 2 | 2 | 3 / 1 | +6.5 | [−3.5, +13.0] | 8.2 | +3.6 [−3.0, +10.2] | +2.6% |
| opportunity cost | 3 | 1 | 1 | 2 | 2 / 1 | +3.2 | [−13.8, +29.0] | 21.4 | −6.4 [−22.5, +9.7] | +1.3% |
| risk | 2 | 1 | 1 | 1 | 1 / 1 | +1.0 | [−17.5, +11.8] | 14.6 | −2.1 | +0.4% |
| capacity | 0 | 0 | 0 | 0 | — | 0 | — | — | 0 | 0 |

**`dynasty_1qb`** (15 states, 3 seasons):

| neutralised | changed | pair → O | new = O | Δ / state | season CI | weekly Δ | recovered |
|---|---|---|---|---|---|---|---|
| survival | 2 | 1 | 1 | +10.1 | [−166, +266] | +31.5 | +2.8% |
| opportunity cost | 1 | 0 | 0 | +7.0 | [−19.4, +31.1] | +1.0 | +2.0% |
| roster fit | 2 | 1 | 1 | +5.7 | [−15.7, +25.2] | +1.5 | +1.6% |
| risk | 1 | 0 | 0 | −0.1 | [−0.3, +0.2] | +0.1 | 0.0% |
| capacity | 0 | 0 | 0 | 0 | — | 0 | 0 |

**No neutralisation has an interval excluding zero in either format.** Survival changes the most
picks and has the largest point estimate, but its weekly effect is negative in target. A changed
pick is not evidence of value, and none of these is.

**Exact Shapley share of the RB − oracle score gap, primary population:**

| factor | target | dynasty |
|---|---|---|
| value | 42.8% | 45.4% |
| roster fit | 22.1% | 22.6% |
| survival | 21.3% | 23.5% |
| opportunity cost | 11.3% | 9.6% |
| risk | 2.5% | −1.0% |
| capacity | 0 | 0 |

## 6. Score-gap classes, and the oracle-aligned counterfactual

The classes are in the executive conclusion. By round (target), rounds 4 and 5 hold most of the
regret (7 states each; 537 and 460). **Every round-4 state is value-led** (7/7). Survival-alone
flips happen only in rounds 1–2. By season, **2022 is 7/7 class 1 in target and 5/8 in dynasty**,
so the value-led pattern is concentrated in one season in both formats. Full tables are in
`d121_summary.json`.

**Oracle-aligned value (pairwise, mechanical):** set the oracle player's value_base to the RB's
plus the one-step roster-value gap, keep every multiplier, and re-compare. The oracle wins in
**6 of 23** (target; 542 regret, 41%) and **6 of 15** (dynasty; 517, 38%). **So in ~60–74% of these
states, even a value term that agreed with one-step roster value would still pick the RB**,
because the multiplier stack (survival, fit, opportunity cost) favours him by more than the
value gap. The value term is the leading cause, but it is not a sufficient one.

## 7. Structural vs information interpretation

| category | where the regret sits (target / dynasty, share of primary) | candidate for rule experimentation? |
|---|---|---|
| **A value construction** | 66% / 60% (value prefers RB) | **Not yet.** The RB→QB sub-mechanism is reproducible (6/7 in both formats) and distinguishable (MSV empty-slot vs upgrade margin; QB level gap), and it is associated with 231 / 456 regret. But the pre-registered bar also needs a paired CI on an intervention, and the value term was not neutralised by design. |
| **B survival** | strict 15% / 11%; including amplification 62% / 28% | **No.** CI spans zero, the weekly sign is negative in target, and few states are involved. |
| C opportunity cost | 0 / 0 as a sole cause | No |
| D roster fit | 0 / 6% | No |
| E risk | 0 / 0 | No |
| F capacity | 0 / 0 | No: inert in rounds 1–6 |
| G combination | 19% / 22% | Unresolved |

**Nothing is called fixable.** The one mechanism that clears two of the three pre-registered
criteria is RB → QB value construction. The next phase should test its third criterion.

## 8. The single most justified next research question

> **In the rounds 1–6 RB → QB states, does MSV's "empty slot = full projection" construction
> overvalue the RB relative to the starter the shipped continuation would otherwise field in that
> RB slot? Is the RB's true marginal roster value (RB now minus the RB the continuation starts if
> he is passed over) smaller than the QB's upgrade margin, as one-step value says?**

This is the only reproducible, distinguishable mechanism D121 found. It can be answered by
attribution on existing machinery: the same states, D115's rollout extended to return the
continuation's roster, and D117's factors. It needs no new model, information or weights. It is
also the sharp form of the MSV double-count question the brief raised: measure the value MSV
*assumes* the empty slot is worth against the value the continuation actually loses. D120 found
QB-wanted states are the one place perfect projections did not help (target 52.6 → 51.8
pts/pick). That points the same way.

---

## 9. Reproducibility, provenance and what changed

```bash
R=scripts/research/d121_value_vs_survival.py
uv run python $R --mode measure --leagues target_league --d115 <d115 t> --d120 <d120 out> --out <o>
uv run python $R --mode measure --leagues dynasty_1qb   --d115 <d115 d> --d120 <d120 out> --out <o>
uv run python $R --mode report  --out <o>
uv run pytest tests/unit/test_d121_value_vs_survival.py
```

| item | value |
|---|---|
| branch | `claude/survival-opportunity-cost-attribution-d6c7yp` |
| HEAD at run time | `2c8a78f821cc18bb4cb45ad2aaf63231277f6392` (D120) |
| `src/alpha_squad` tree / dirty | `55e763e8a80af908a2c2bcc0ae66753c16b629fc` / **False** |
| board vintage | `f00226015095534f22e1311c8fa1b4823d66e0679ef6fa8f1817500209dce89f` (= D116–D120; checked) |
| per season | 2021 `79599ffa…` 2022 `43f0e968…` 2023 `aa73cd3f…` 2024 `7873284c…` 2025 `0b344c7e…` |
| upstream board / idmap | `e270d790…` / `36016b92…` |
| models / tier | `uncertainty_catboost_v2`, `rookie_features_v1` / `L0` |
| inputs: D120 arms (target / dynasty) | `f032a3d1…` / `258d3b5f…` |
| inputs: D115 regret / timing / arms (target) | `6d395458…` / `a8b44df6…` / `b259beba…` |
| inputs: D115 regret / timing / arms (dynasty) | `ee4921c5…` / `72308875…` / `72c5d74c…` |
| outputs `d121_measured_target_league` / `_dynasty_1qb` / `d121_summary` | `6ea623de…` / `236c565c…` / `3f73bf56…` |

**Files changed — research only:** `scripts/research/d121_value_vs_survival.py` (new),
`tests/unit/test_d121_value_vs_survival.py` (new, 25 tests), `docs/D121_VALUE_VS_SURVIVAL.md`
(new), `docs/DECISIONS.md` and `docs/PROJECT_STATE.md` (appended). `src/alpha_squad/**` unchanged.
