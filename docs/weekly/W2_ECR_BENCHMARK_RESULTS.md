# W2 — The ECR-alone weekly benchmark, and its noise floor

**Status: COMPLETE.** Run exactly as pre-registered in `docs/weekly/W2_PREREGISTRATION.md`
(including amendment A1, which was written and committed *before* any metric was computed).

*One system measured: the published FantasyPros consensus. **No Alpha model was built, fitted
or compared.** No production change.*

Provenance: `db_fpecr.parquet` sha256 `e270d790…5db9a5` (identical to the vintage W1 measured —
a first, small immutability check), crosswalk `36016b92…b19ca4`, 79 weeks, 2021–2025, Full PPR.
Results JSON: `reports/weekly/w2_results.json`.

---

## 1. Headline

**ECR is a strong, remarkably stable ranker in the middle of the board and a weak one at the
very top — and the gap between those two statements is the biggest single finding of this
phase.**

On the FLEX board, across 79 weeks:

| what | value |
|---|---|
| Spearman ρ vs realized points | **0.682** (SD across weeks **0.041**) |
| pairwise ordering accuracy | **75.3%** |
| decisive-pair accuracy (≥3 pts apart) | **81.2%** |
| **top-10 precision** | **0.26** — ECR names ~2.6 of the actual top 10 |
| **top-10 points captured** | **0.637** — but those names collect 64% of the achievable points |

The two top-10 numbers are the phase's most important result. A naïve reading of precision
("ECR gets the top 10 three-quarters wrong") and a naïve reading of capture ("ECR gets
two-thirds of the value") describe the same ranking. Both are true. Which one matters depends
on the product, and **W1's insistence on not collapsing them into one score is what made this
visible.**

---

## 2. The benchmark, by board

Per-week means over 79 weeks (2021–2025), Full PPR. SD is week-to-week.

| board | ρ | SD(ρ) | pairwise | decisive | prec@10 | cap@10 | prec@25 | cap@25 | prec@50 | cap@50 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **FLEX** | **0.682** | 0.041 | 0.753 | 0.812 | 0.260 | 0.637 | 0.394 | 0.689 | 0.544 | 0.760 |
| RB | 0.717 | 0.064 | 0.766 | 0.824 | 0.433 | 0.713 | 0.675 | 0.832 | 0.844 | 0.926 |
| WR | 0.666 | 0.061 | 0.748 | 0.800 | 0.349 | 0.672 | 0.536 | 0.759 | 0.709 | 0.842 |
| TE | 0.614 | 0.098 | 0.730 | 0.798 | 0.484 | 0.722 | 0.693 | 0.835 | 0.897 | 0.949 |
| QB | 0.493 | 0.155 | 0.678 | 0.712 | 0.551 | 0.809 | 0.906 | 0.942 | — | — |
| DST | 0.275 | 0.208 | 0.603 | 0.628 | 0.509 | 0.665 | 0.910 | 0.911 | — | — |
| **K** | **0.127** | 0.235 | 0.548 | 0.559 | 0.452 | 0.689 | 0.921 | 0.935 | — | — |

**Read this table by column, not by row.** Deep-pool ordering (ρ, pairwise) is best at RB and
worst at K; top-of-board identification (prec@10) is *worst at FLEX* and best at QB — because
FLEX ranks ~384 players against each other while QB ranks ~44.

Three things stand out:

- **K is close to noise.** ρ = 0.127 with SD 0.235; the 10th percentile week is **−0.173** —
  in one week in ten, the consensus kicker ranking is *worse than random*. Pairwise accuracy is
  54.8%, barely above a coin flip. This is not a criticism of FantasyPros; it is the signal
  that exists. D57 reached the same conclusion from the other direction when it made K and DST
  baselines rather than models (K year-over-year r = 0.41, DST r = 0.29).
- **DST is weak too** (ρ = 0.275, 10th-percentile week −0.044).
- **QB has the lowest ρ of the four skill positions (0.493) but the highest top-10 precision
  (0.551).** A small, well-understood pool: easy to identify the good ones, hard to order them.

---

## 3. The noise floor

**The unit of replication is the week (n = 79), not the player-week.** Player-weeks inside one
week share the slate, the injury news and the ECR vintage; treating ~30,000 of them as
independent would overstate precision by roughly an order of magnitude.

Every comparison is **paired within week** — same week, same player universe, both systems — so
the quantity is the per-week paired difference. **MDE** is the half-width of its 95% bootstrap
CI over weeks (10,000 resamples, seeds 0–9 fixed in the pre-registration): the smallest per-week
mean difference this instrument can resolve.

### 3.1 The answer, in the units a future phase needs

**FLEX, Full PPR, 79 weeks — the minimum detectable improvement over ECR:**

| metric | MDE (per-week mean difference) | for scale: ECR's own week-to-week SD |
|---|---:|---:|
| Spearman ρ | **± 0.018** | 0.041 |
| pairwise accuracy | **± 0.007** | 0.018 |
| decisive-pair accuracy | **± 0.008** | 0.021 |
| points captured @10 | **± 0.020** | 0.084 |
| points captured @25 | **± 0.015** | 0.064 |
| points captured @50 | **± 0.013** | 0.044 |
| precision @10 | **± 0.020** | 0.117 |

**So: a candidate system must beat ECR by more than ~0.018 Spearman, or ~2.0 points of top-10
capture, before the result is distinguishable from weekly noise.** Anything smaller is not a
small win — it is unmeasurable on this instrument, in either direction.

Per-position MDEs (Spearman): RB ±0.020, WR ±0.018, TE ±0.024, QB ±0.029, DST ±0.050,
K ±0.046. K and DST are the noisiest and therefore the hardest places to *prove* an improvement,
even though they are where ECR is weakest.

### 3.2 Why the paired design matters so much here

ECR's FLEX Spearman varies week to week with SD 0.041, but the *paired difference* against the
season-to-date baseline has SD 0.087 — and the MDE that falls out of 79 weeks is 0.018, about
**2.3× tighter than ECR's own weekly SD**. The shared weekly difficulty cancels. Comparing two
systems on unpaired weekly means would have inflated the floor by more than a factor of two and
made a real effect look unmeasurable.

**The draft program's 172–250 point detection floor is not quoted here and does not transfer.**
Different instrument, different unit, 5 season-clusters instead of 79 weeks.

---

## 4. How strong is ECR, really? — against two trivial references

ECR's absolute numbers mean nothing until something obvious is measured on the same universe.
Two pre-registered references, both using only prior information, both re-ranking **the exact
same players**:

- **B0** — season-to-date points per game through week *w*−1
- **B1** — prior-season points per game

**FLEX, ECR minus reference, per-week paired (all 79 weeks):**

| metric | vs B0 (season-to-date) | in MDE units | vs B1 (prior season) | in MDE units |
|---|---:|---:|---:|---:|
| Spearman | **+0.066** [+0.051, +0.088] | 3.6× | **+0.338** [+0.298, +0.381] | 8.1× |
| pairwise | +0.028 [+0.022, +0.036] | 4.0× | +0.129 [+0.115, +0.144] | 8.8× |
| decisive | +0.032 [+0.025, +0.042] | 3.9× | +0.157 [+0.138, +0.176] | 8.4× |
| capture@10 | +0.042 [+0.023, +0.062] | 2.1× | +0.141 [+0.105, +0.178] | 3.8× |
| capture@50 | +0.041 [+0.031, +0.056] | 3.3× | +0.148 [+0.115, +0.184] | 4.3× |

**Every single comparison excludes zero.** ECR beats both trivial references on every metric at
every depth for FLEX, RB, WR, TE, QB and DST.

**But look at the size of the ECR-over-B0 edge: +0.066 Spearman.** A simple average of a
player's points so far this season gets within 0.066 of a 50-expert consensus. That is the most
sobering number in this report, and it frames the whole Alpha question: the headroom between
"the obvious thing" and "the expert consensus" is **3.6 MDE units wide**. Whatever room exists
above ECR is plausibly of similar order — not the order of ECR-over-B1 (+0.338).

**The one exception is K**, where ECR beats B0 by only 1.3–1.7 MDE units and **fails to beat it
at all** at capture@25 (+0.002, CI crosses zero) and precision@10 (+0.030, CI crosses zero).
Expert consensus on kickers adds almost nothing over "who has scored most this season".

---

## 5. Pre-registered decision rules — both resolved

Thresholds fixed in `W2_PREREGISTRATION.md` §2 before any result existed; applied in code
(`evaluation/weekly/decision_rules.py`, under test), not by hand.

### R1 — is the instrument usable? → **USABLE**

Criterion: the ECR-over-trivial-baseline gap must exceed the MDE.

| board | gap/MDE range | verdict |
|---|---|---|
| FLEX | 2.13 – 4.00 | **USABLE** |
| RB / WR / TE | 1.58 – 3.99 | **USABLE** |
| QB | 1.59 – 3.46 | **USABLE** |
| DST | 1.74 – 4.07 | **USABLE** |
| K | 0.28 – 1.73 | USABLE, but marginal — capture@25 is 0.28× (unresolvable) |

**Consequence (pre-registered): W3 may proceed as designed.** The instrument can resolve
effects of the size that separate ECR from an obvious baseline, so it can resolve an Alpha
effect of that size.

### R2 — is ECR's strength depth-uniform? → **UNIFORM everywhere except K**

Criterion: the effect, in MDE units, must vary by < 2× across capture@{10, 25, 50}.

| board | @10 | @25 | @50 | spread | verdict |
|---|---:|---:|---:|---:|---|
| FLEX | 2.13 | 2.60 | 3.31 | 1.55× | **UNIFORM** |
| RB | 2.05 | 2.23 | 2.34 | 1.14× | UNIFORM |
| WR | 2.01 | 2.92 | 2.73 | 1.45× | UNIFORM |
| TE | 2.80 | 2.65 | 1.58 | 1.77× | UNIFORM |
| QB | 2.53 | 1.59 | — | 1.59× | UNIFORM |
| DST | 3.26 | 1.74 | — | 1.87× | UNIFORM |
| **K** | 1.73 | 0.28 | — | **6.10×** | **DEPTH-DEPENDENT** |

**Consequence (pre-registered): W3 targets overall ranking quality rather than one depth** —
except for K, where the consensus adds real value only at the very top and essentially none at
depth.

A caution on reading R2 as reassurance: uniform *in MDE units* is not the same as "ECR is
equally good at every depth". §2 shows precision@10 (0.26) is far below precision@50 (0.54) on
FLEX. R2 says ECR's *advantage over a trivial baseline* is similarly resolvable at each depth,
which is a statement about the instrument, not about where the product opportunity is.

---

## 6. The FLEX reconstruction, validated

Pre-registered A1 check, threshold **0.70 fixed before measuring**: does the mirror's
reconstructed FLEX top-10 match the **real** FantasyPros FLEX top-10?

| | |
|---|---|
| weeks with both artifacts | **19** |
| **median top-10 overlap** | **0.80** |
| mean / min / max | 0.85 / 0.70 / 1.00 |
| **verdict** | **`reconstruction_sound`** → full-depth results stand as FLEX results |

Every week met the threshold. The measurement **includes a two-day vintage gap** (mirror Friday
vs API Sunday), so 0.80 is a lower bound on reconstruction fidelity. The single week where both
the true FLEX and the superflex board were available at the *same* vintage (2023 wk8) had all
five non-QB players from the superflex top-10 present in the real FLEX top-10.

---

## 7. Availability — reported separately, never multiplied in

Share of ranked players who actually played, per board, over 79 weeks:

| board | mean | median | SD | min | mean ranked |
|---|---:|---:|---:|---:|---:|
| FLEX | 0.688 | 0.701 | 0.052 | 0.518 | 383.9 |
| QB | 0.718 | 0.756 | 0.119 | 0.419 | 43.6 |
| RB | 0.730 | 0.734 | 0.053 | 0.550 | 108.5 |
| WR | 0.759 | 0.762 | 0.046 | 0.594 | 157.4 |
| **TE** | **0.650** | 0.651 | 0.050 | 0.488 | 94.2 |
| K | 0.929 | 0.931 | 0.049 | 0.769 | 28.4 |
| **DST** | **0.998** | 1.000 | 0.011 | 0.923 | 27.7 |

A DST essentially always plays; a ranked TE plays two times in three. This is a real product
asymmetry and it is exactly why the pre-registration keeps availability apart from the
production forecast rather than folding P(play) into the projection.

---

## 8. Season variation

FLEX, ECR:

| season | weeks | ρ | capture@10 | precision@10 | availability |
|---|---:|---:|---:|---:|---:|
| 2021 | 17 | 0.662 | 0.616 | 0.229 | 0.686 |
| 2022 | 16 | 0.656 | 0.617 | 0.263 | 0.668 |
| 2023 | 16 | 0.696 | 0.633 | 0.288 | 0.658 |
| 2024 | 14 | 0.700 | 0.641 | 0.214 | 0.710 |
| 2025 | 16 | 0.703 | 0.680 | 0.300 | 0.720 |

ρ drifts up ~0.04 from 2021 to 2025 and capture@10 up ~0.064. **This is an observation, not a
finding**: five seasons is far too few to separate "ECR is improving" from "these seasons were
more predictable", and W2 pre-registered no test of it. It is flagged because a W3 that trains
on early seasons and tests on late ones would inherit the drift as an apparent effect.

---

## 9. Half-PPR (secondary)

The same full-PPR-ranked FLEX boards, scored against half-PPR outcomes. **This is not "the
half-PPR ECR benchmark"** — no such benchmark is obtainable at depth (W1.1 §5, §8).

| metric | Full PPR | Half PPR | Δ |
|---|---:|---:|---:|
| Spearman | 0.682 | 0.674 | −0.009 |
| pairwise | 0.753 | 0.750 | −0.003 |
| decisive | 0.812 | 0.814 | +0.002 |
| capture@10 | 0.637 | 0.615 | −0.022 |
| capture@50 | 0.760 | 0.745 | −0.015 |

Degradation is small — around or just above the MDE. **But that does not mean a half-PPR board
would be interchangeable.** At the same week and vintage, the real FLX PPR and FLX HALF top-10s
**share only 7 of 10 names** (W1.1 §8). The correct reading is: a full-PPR *ranking* loses
little when *scored* in half-PPR, while the half-PPR *product* is genuinely a different board.
Both facts are needed, and neither licenses approximating one from the other.

---

## 10. Scope and exclusion report

**Included: 79 of 90 regular-season weeks, 2021–2025.** 2021 w1–17 · 2022 w2–17 ·
2023 w2–17 · 2024 w4–17 · 2025 w2–17.

**Excluded: 11 weeks. Every exclusion is a missing ECR board.** None was caused by missing
player data, cutoff problems, scoring problems or data quality.

| weeks | n | reason |
|---|---:|---|
| 2021–2025 wk18 | 5 | No weekly ECR board exists in **any** season for week 18 (and week 18 is not a fantasy week in standard leagues) |
| 2022/2023/2024/2025 wk1 | 4 | Mirror capture gap — no board for that week |
| 2024 wk2, wk3 | 2 | Mirror capture gap |

**Descriptive comparison, included vs excluded** (outcome side only — there is no ECR to
compare on the excluded weeks):

| | weeks | RB/WR/TE players/wk | mean pts | SD pts | max pts |
|---|---:|---:|---:|---:|---:|
| included | 79 | 287.9 | 7.074 | 7.536 | 40.53 |
| excluded | 11 | 304.5 | 6.721 | 7.090 | 37.87 |

The excluded weeks are not outliers on outcome characteristics. **But the exclusions are
systematic, not random**, and that is a real limitation: **week 1 is absent in four of five
seasons**, and week 1 is the only week with *no current-season information at all*. Everything
in this report therefore describes ECR's strength **conditional on in-season data existing**.
Whether ECR's edge over a trivial baseline is larger or smaller in week 1 is untested and
untestable on this data. No selection-bias claim is made beyond that.

**Invalid cells: zero.** Every one of the 79 weeks × 7 boards had at least 10 evaluable
players, so the pre-registered invalid-cell rule never fired.

---

## 11. Limitations

1. **Friday vintage, not the Sunday-at-kickoff vintage users actually act on.** The full-depth
   benchmark is the mirror's Friday board. FantasyPros' own freeze is Sunday 12:59 ET. ECR
   measured here is therefore *weaker* than the ECR a user sees — the real product bar is
   higher than this report's numbers.
2. **FLEX is a validated reconstruction, not the published board** (median top-10 overlap
   0.80). Sound by the pre-registered rule, but not identical.
3. **No full-depth Half-PPR benchmark** — a licensing limit, not a data one.
4. **Week 1 is almost entirely absent** (§10).
5. **Five seasons** cannot separate the season drift in §8 from real improvement.
6. **ECR has no point projection**, so no point-accuracy metric is reported for it. That is
   correct, not a gap — but it means W3 cannot compare Alpha and ECR on calibration.
7. **Weekly-board immutability is still only weakly checked**: the W2 hash matched W1's, which
   is one observation, not a guarantee.
8. **Vegas and weather remain unusable historically** (W1 §6.5), capping any Alpha built
   against this instrument.

---

## 12. What this means for Alpha — and the recommended W3

### The question W3 should answer

> **Can Alpha, using only information available at the Friday cutoff and no ECR, beat the
> season-to-date baseline (B0) by more than ECR does — i.e. can it close or exceed the +0.066
> Spearman / +0.042 capture@10 gap that separates the consensus from the obvious thing?**

### Why this, and not "does Alpha beat ECR"

Because W2 just measured the size of the prize, and it is small. **ECR beats a plain
season-to-date average by +0.066 Spearman (3.6 MDE units).** That is the entire measured value
of a 50-expert consensus over arithmetic. Alpha's realistic target zone is that same order of
magnitude, and the MDE (±0.018) means the experiment needs to be designed around an effect of
roughly 0.02–0.07 Spearman — not the 0.3+ that separates ECR from a prior-season baseline.

Framing W3 as "beat B0 by more than ECR does" rather than "beat ECR" has three concrete
advantages, all of which follow from this phase's numbers:

1. **It is the same comparison, with more statistical power.** Both Alpha and ECR are compared
   to a common reference on identical weeks and universes, so the ECR-vs-Alpha contrast is
   recoverable *and* each arm's own effect is measurable against something stable.
2. **It keeps the absolute goal primary.** The north star is the best possible ranking, not
   beating ECR. A system that beats B0 by +0.05 while ECR beats it by +0.066 has *failed the
   product gate* but is still informative — it says Alpha recovers 75% of the consensus's edge
   from data alone, which is exactly what tells us whether adding ECR as a feature (System C)
   is likely to help.
3. **It sets the bar before the model exists**, which is the discipline that made W2 worth
   running at all.

### Where to point it — the evidence says the top of the board

**FLEX precision@10 is 0.26 while precision@50 is 0.54.** The consensus is *least* able to
identify the actual top 10 of a ~384-player FLEX pool, and top-10 capture (0.637) leaves the
most absolute room of any depth. That is where a user's FLEX decision actually happens, and it
is where the headroom is largest in absolute terms.

Two caveats that must travel with that recommendation:
- capture@10 is also the **noisiest** depth (SD 0.084, MDE ±0.020), so a top-10 improvement
  needs to be genuinely large to register.
- R2 found ECR's *advantage* is depth-uniform, so there is no evidence that ECR is
  *differentially* weak at the top relative to a trivial baseline. The top-of-board opportunity
  is an absolute-headroom argument, not a relative-weakness one.

### What W3 must not do

Chase K and DST. ECR is weakest there in absolute terms (ρ 0.127 and 0.275), which looks like
opportunity — but the MDEs are the widest in the study (±0.046, ±0.050), the signal is known to
be thin (D57: K r = 0.41, DST r = 0.29 year over year), and they are 2 of 10 starting slots. It
is the most statistically expensive place to look for the least product value.

Nor should it chase projection MAE. W2 deliberately computed no point-error metric for ECR, and
D101 already established that projection metrics are not monotone in each other, let alone in
decision quality. **An MAE improvement earns attention only when it moves one of the ranking
metrics above.**

---

## 13. Reproducing

```bash
make install
uv run alpha-squad sources ingest --season-start 2021 --season-end 2025
uv run alpha-squad identity build
uv run alpha-squad features build --season-start 2021 --season-end 2025
uv run python scripts/research/w2_ecr_benchmark.py --out reports/weekly/w2_results.json
uv run pytest tests/unit/test_weekly_*.py tests/leakage/
```
