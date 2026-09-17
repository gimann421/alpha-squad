# D109 — Projection and early-draft decision audit

**Forensic diagnostic, not an optimization attempt.** No production change, no model retraining, no
new feature, no calibration, no decision-rule change, no PR, nothing merged. `models/` stands at
`73b408e9`, `league/` at `d4cfd00e`, both byte-identical to their state at D108. Working tree clean.

Window: **2021–2025**, the valid backtest population. 2026 is used nowhere.

---

## Bottom line

Alpha spends rounds 1–3 on receivers and quarterbacks and almost never takes a running back — 15%
of its first 150 picks are RBs, against 53% for the hindsight oracle, and its *first* RB arrives at
median round 6. The reason is not the opportunity-cost term that D81 identified on the 2026 board;
on the 2021–2025 boards that term is nearly equal across RB/WR/TE and does not discriminate. It is
that Y1 simply scores receivers higher than backs, and the D63 value base counts that projection
**twice** — `msv == projection` in **150 of 150** early picks, so the value base is literally
`2 × projection − replacement` at every pick in rounds 1–3. Y1's projections are visibly and
systematically wrong in a position-dependent way: it has never once projected a running back above
**249.1** points in five seasons, while 41 real RB seasons cleared 250 and 18 cleared 300. But the
individual decisions are mostly *robust* to that error — the median early pick needs the whole elite
RB cell to gain **90** points before it changes, against a measured under-projection of about **42**.
The honest verdict is that all three problems are real, and the information problem is the biggest:
even when Alpha picks the right position it still leaves ~132 points of regret on the table, and
when it misses, the oracle's player sits a median **22nd** on its own board.

## What Alpha does

- **Round 1:** WR 56%, QB 24%, RB 20%. **Round 2:** WR 40%, QB 38%, TE 20%, **RB 2%** (1 of 50).
  **Round 3:** WR 46%, QB 32%, RB 22%.
- **Modal opening is `WR-WR-QB` (28%).** No draft in 50 opened with two running backs.
- **First RB: mean round 4.38, median round 6.0.** First WR round 1.80, first QB round 2.20.
- Strongly board-dependent, not a hardcoded lean: **2021 took no WR at all in round 1** (QB 4, RB 6),
  while **2023 and 2024 took WR at all ten round-1 slots**. The consensus board itself flipped from
  RB-heavy (9 of the ECR top 15 in 2021–22) to WR-heavy (10 of 15 in 2023/2025).
- It does respond to its own roster: after `WR-WR` it takes a QB in **14 of 14** cases.
- Full 16 rounds: QB 1.88, RB 3.16, WR 5.38, TE 2.08, K 2.00, DST 1.50 — 3.5 roster spots on K/DST
  in a league that starts one of each.

## Why

- **The double count is universal here, not occasional.** `msv == projection` in **150/150** early
  picks, because a ≤2-player roster leaves every lineup slot open. So the value base is
  `2 × projection − replacement`, and a projection error is worth **twice** a replacement-level
  error in the comparison.
- **Round 1, mean terms:** WR scores **595.3**, RB **425.1**, QB **418.0**. WR's edge over RB comes
  from projection (287.0 vs 243.1, doubled to +87.8), partly given back by replacement level
  (WR 111.4 vs RB 84.1), then **amplified multiplicatively**: risk 0.79 vs 0.68 and survival
  1.27 vs 1.19 hand WR a further ~24%.
- **The `risk` multiplier is a quiet, systematic RB penalty.** It is the uncertainty model's
  confidence; RBs carry wider intervals, so they are scored down ~16% relative to WRs at exactly
  the picks where upside is what you are buying.
- **Opportunity cost does NOT drive this on the valid window.** Round 1 means are RB 14.1, WR 17.9,
  TE 19.2 — near-parity. D81's headline 22× asymmetry (WR 72.3 vs RB 3.3) is a **2026-board
  property and does not generalise**; it should not be quoted for 2021–2025.
- **QB is a separate mechanism.** Its replacement is drawn at the *consumption* boundary (~QB20–25,
  mean level **207.4**) in a league that starts ten quarterbacks, and its opportunity cost is
  **0.0** in round 1. At the snake turn, where every opportunity cost is zero by construction, QB
  takes **10 of 15** picks (67%) versus 27% elsewhere — the doubled raw projection decides it.

## Projection problems

- **A hard, position-dependent ceiling.** Max Y1 projection 2021–2025: QB 371.4, WR 297.0, TE 265.3,
  **RB 249.1**. Y1 produced **zero** RB projections above 250 (41 real RB seasons cleared it, 18
  cleared 300) and **zero** non-QB projections above 300 (41 real non-QB seasons cleared it). QB is
  by contrast well calibrated at the top (33 projections >300 against 38 realized).
- **The error is in the cross-positional *gap*, and it grows.** Median projected-minus-realized
  WR−RB gap error: **+7.6** at ECR 1–12, **+34.7** at ECR 13–24, **+55.4** at ECR 25–36. At ECR
  13–36 Y1 says WR is ~18–38 points better; reality said RB was ~17 points better.
- Bias inside the rounds 1–3 contention set (ECR ≤ 30): **RB −41.5**, TE −17.0, WR −3.0, QB +13.9.
  This reproduces D97's bias *ordering* (QB ≫ WR > RB) on an independently rebuilt board.
- **Not all compression is a defect** — `E[max Y] > max E[Y]` is correct behaviour (D78), and the
  market shares much of the RB bias (D82: ECR's own RB top-10 bias +36.6 vs Alpha's +45.5). What is
  not defensible is that the shrinkage is **positionally asymmetric**: the RB scale tops out at 60%
  of the realized RB maximum while QB reaches 86%.

## What actually matters

- **Most early picks are robust to realistic projection error.** Raising every RB with ECR ≤ 36
  changes the pick in only **23%** of cases at +41.5 (the measured bias) and **34%** at +55.8. The
  median pick needs **+90**; round 1 needs **+120**.
- **But the aggregate allocation is right at the tipping point.** Across all 150 states the modal
  position flips from WR to RB at **Δ ≈ 40** (RB 52 vs WR 49) — essentially the measured bias. So
  the model is not wrong enough to change most individual picks, yet is wrong by just enough to
  change the *strategy* it implies.
- **Robustness is very uneven by season:** 2022's picks flip at a median **+20** (23 of 25 within
  +56); 2024's need **+120**. A single global conclusion about fragility would be wrong.
- **The decision-relevant headroom is small and sits at the detection floor.** Splitting regret:
  when Alpha takes the oracle's position but the wrong player it still loses **131.5** points; when
  it takes a different position it loses **190.4**. The part attributable to the *positional* call
  is **+58.9 per pick ≈ +176.6 per draft** — inside D97's 172–250 detection floor. That is why
  every phase D86–D107 returned a null: the effect is real and the instrument cannot resolve it.
- **Realized outcomes agree with the direction.** The round-1 WRs Alpha took missed their projection
  by **−65.5** on average (287.0 → 221.5); the round-1 RBs it took missed by **−6.0** (243.1 → 237.1).

## Recommendation

Do not change anything yet, and specifically do not "fix" the RB projections by inflation — D82/D83
already measured that adding features and shrinkage make the elite tail *worse*, and D81 showed the
elite-RB cell must reach ~350 (about 140 above the training data's own answer for that cell) before
the opening changes on a 2026 board. The finding that earns a next phase is narrower and new: the
one axis nothing in D99–D106 has tested is a change to projection **magnitudes** evaluated on
**realized draft value**, and this audit locates the effect precisely there — the aggregate
positional crossover (Δ≈40) coincides with the measured cross-positional bias (≈42). That phase
should be pre-registered as likely underpowered, because its own expected effect (~177 points per
draft) sits inside the instrument's 172–250 floor; if it is run, it should be run knowing that a
null is the most probable outcome and would not be informative. Separately, and cheaply, the
`risk` multiplier deserves a look on its own: it is a systematic 16% penalty on exactly the position
this audit finds under-projected, and no phase has ever isolated it.

---

# Evidence

## 0. Instrument integrity — one material non-reproduction, documented not worked around

`data/` is gitignored, so this phase rebuilt the entire pipeline from source in a fresh container
(`ingest` → `identity` → `college-usage` → `features` → `market` → `train`, all exit 0, K/DST rows
non-zero as the D78 guard requires).

| check | result |
|---|---|
| upstream board blob `sha256(db_fpecr.parquet)` | `a966176d…` — **identical to `D89_BOARD_SHA256`** |
| upstream identity map `sha256(db_playerids.csv)` | `0174ea89…` — **identical to `D89_IDMAP_SHA256`** |
| `BoardVintage.matches_d89()` | **True** |
| assembled board `combined_hash` | `d2955868…` — **D108 recorded `ca3e2d8a…`. DOES NOT MATCH** |
| training determinism, same container | full retrain reproduces `d2955868…` **bit-identically** |
| thread-count sensitivity (`OMP_NUM_THREADS=1` vs 4) | **identical hash** — not the cause |
| `ruff check` / `ruff format --check` | clean / clean (D108's `make lint` lesson applied) |
| `pytest` | **1427 passed, 44 deselected** — exactly D108's count |
| `models/` / `league/` tree | `73b408e9` / `d4cfd00e` — unchanged |

**Diagnosis.** The market board is byte-identical; training is deterministic in seed *and* thread
count; and the D101 training-row **counts** reproduce exactly (RB 2022 `n_train=549`, the figure
D101 published). What moved is the **values**. Re-running D101's committed script:

| quantity | D101 published | D109 replication |
|---|---|---|
| Y1 mean MAE | 40.638 | **40.544** (Δ 0.09, 0.2%) |
| Y1 top-6 hit rate | 0.3750 | **0.4062** |
| Y1 per-position hit rate | QB .375 RB .333 WR .333 TE .458 | QB .333 RB .375 WR .417 TE .500 |
| Y1 gate G6 | **PASS** | **FAIL at RB** |
| Y3 − Y1 (the phase's deciding contrast) | −0.0104 | **−0.0104** |
| Y0 WR top-decile bias, 2022 / 2023 | +15.97 / −2.01 | −5.14 / +8.41 |

So **continuous aggregates reproduce to ~0.2%, while discrete threshold metrics do not** — a
top-6 hit rate moves in steps of 0.167, and G6 is a threshold crossing on a statistic whose season
values span 2 to 61. The control arm Y0 moved too, which rules out anything arm-specific: the
nflverse-derived feature/target panel was **restated upstream** since D108's ingest.

**This is a real gap in the instrument, and it satisfies D108 reopening criterion 5.** `board_vintage.py`
hashes the DynastyProcess ECR board and the assembled projections, but **nothing hashes the
nflverse panel that the projections are trained on** — so "the board vintage reproduces" was never
sufficient to establish that a projection experiment reproduces. It also plausibly explains D101's
own unresolved non-reproduction of D78.

**Consequence for everything below, stated plainly:** every number in this report describes board
vintage `d2955868…`. Magnitudes and orderings over the 2136-player pool are trustworthy; any
single threshold-crossing claim is fragile. Nothing here should be restated as a D108-vintage number,
and D100–D108's published figures should not be quoted against this vintage without re-running them.

## 1. Y1 projection audit

Population: `load_season_projections` (the application's own loader, not a re-query), 2021–2025,
restricted to the 2136 QB/RB/WR/TE players carrying a real preseason ECR rank on the 1-QB `ro`
board — a projection for an undrafted body cannot change a draft decision.

**Bias by within-position projection rank** (positive = projected too high):

| band | QB | RB | WR | TE |
|---|---|---|---|---|
| 1–3 | +26.5 | **−19.6** | +11.3 | −2.1 |
| 4–6 | **+73.1** | **−46.5** | −0.1 | +21.8 |
| 7–12 | +26.5 | **−27.0** | **+29.3** | −6.9 |
| 13–24 | +0.0 | −17.7 | +16.4 | −10.3 |
| 25–48 | −7.2 | −7.5 | +3.1 | −5.8 |

Only **20%** of top-6-projected RBs beat their projection; **73%** of WRs ranked 7–12 failed theirs.

**The ceiling** (pooled 2021–2025):

| pos | max Y1 proj | max realized | Y1 > 250 | real > 250 | Y1 > 300 | real > 300 |
|---|---|---|---|---|---|---|
| QB | 371.4 | 430.4 | 66 | 68 | 33 | 38 |
| **RB** | **249.1** | 416.6 | **0** | **41** | **0** | **18** |
| WR | 297.0 | 439.5 | 24 | 49 | **0** | 20 |
| TE | 265.3 | 316.3 | 1 | 5 | 0 | 3 |

**Conditional on market rank** (median-based, so injury zeros cannot drive it):

| ECR band | med proj RB | med real RB | med proj WR | med real WR | projected gap | realized gap | **gap error** |
|---|---|---|---|---|---|---|---|
| 1–12 | 216.3 | 237.8 | 254.7 | 268.6 | +38.4 | +30.8 | **+7.6** |
| 13–24 | 215.4 | 246.5 | 233.1 | 229.4 | +17.7 | **−17.0** | **+34.7** |
| 25–36 | 190.0 | 204.5 | 227.9 | 187.1 | +37.9 | **−17.5** | **+55.4** |

Error distribution inside ECR ≤ 30 (n=142): mean |error| **69.8**, median 58.6, p90 149.4, sd 88.2.

Largest misses inside ECR ≤ 30 — under: McCaffrey 2025 (159.6 → 416.6), McCaffrey 2022 (123.3 →
356.4), Taylor 2021 (181.5 → 373.1). Over: Nabers 2025 (292.2 → 57.1), Chubb 2023 (222.0 → 23.1),
Hill 2025 (234.9 → 53.5).

## 2. What the production engine does at picks 1–30

Instrument: `evaluation/opening_audit.py::audit_opening`, which calls
`league/draft.py::recommend_draft_pick` itself and whose `decompose_candidate` **asserts** the
reassembled term-by-term score equals the production score to 1e-6. 5 seasons × 10 draft slots ×
3 audited rounds = **150 pick states**; because slot *s* picks at overall *s*, *21−s*, *20+s*, the
ten slots together cover **every one of overall picks 1–30, once per season** (asserted in the
merge step). `top_n` does not affect the recommendation — it only truncates the returned list.
A recorded state replayed through `recommend_draft_pick` reproduced its recorded pick exactly.

| | QB | RB | WR | TE |
|---|---|---|---|---|
| Round 1 | 12 (24%) | 10 (20%) | **28 (56%)** | 0 |
| Round 2 | 19 (38%) | **1 (2%)** | 20 (40%) | 10 (20%) |
| Round 3 | 16 (32%) | 11 (22%) | 23 (46%) | 0 |

By season (round 1): 2021 `QB4+RB6`, 2022 `QB6+RB4`, 2023 `WR10`, 2024 `WR10`, 2025 `QB2+WR8`.

Opening sequences: `WR-WR-QB` 14, `WR-QB-RB` 9, `RB-QB-WR` 5, `QB-TE-WR` 5, `WR-QB-WR` 5,
`QB-WR-WR` 4, `RB-TE-WR` 3, `RB-TE-QB` 2, `QB-WR-RB` 2, `QB-RB-WR` 1. **None contains two RBs.**

## 3. Score decomposition — why

Mean terms for the chosen player (`score = (msv + daVORP + oc) × fit × risk × surv × cap`):

| round | pos | n | proj | msv | daVORP | repl | oc | fit | risk | surv | **score** |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | QB | 12 | 354.6 | 354.6 | 147.2 | 207.4 | 0.0 | 1.10 | 0.76 | 1.00 | 418.0 |
| 1 | RB | 10 | 243.1 | 243.1 | 159.1 | 84.1 | 34.8 | 1.20 | 0.68 | 1.19 | 425.1 |
| 1 | **WR** | 28 | 287.0 | 287.0 | 175.7 | 111.4 | 31.7 | 1.20 | 0.79 | 1.27 | **595.3** |
| 2 | QB | 19 | 355.6 | 355.6 | 162.6 | 193.0 | 3.8 | 1.10 | 0.75 | 1.05 | 458.5 |
| 2 | TE | 10 | 242.1 | 242.1 | 132.7 | 109.4 | 77.1 | 1.10 | 0.78 | 1.21 | 470.7 |
| 3 | QB | 16 | 346.4 | 346.4 | 147.8 | 198.7 | 16.6 | 1.10 | 0.71 | 1.11 | 442.0 |

`msv == projection` in **150/150** chosen picks → the value base is `2 × projection − replacement`
throughout rounds 1–3.

Positional opportunity cost, mean of the best candidate at each position:

| round | QB | RB | WR | TE |
|---|---|---|---|---|
| 1 | 0.0 | 14.1 | 17.9 | 19.2 |
| 2 | 2.8 | 11.5 | 10.3 | **27.4** |
| 3 | 14.0 | 6.3 | 3.8 | 2.9 |

At the snake turn (`picks_until_next_turn == 0`, n=15) the mix is **QB 10, WR 4, RB 1**; elsewhere
(n=135) QB 37, WR 67, RB 21, TE 10.

Attribution by category, against the question "why does WR win":
**A (higher projected value)** is the primary driver — WR's projection edge, doubled.
**B (scarcity)** partly *offsets* it — RB's lower replacement level gives RB the better daVORP-per-point.
**E (risk/survival)** is a large and under-appreciated secondary driver (~24% multiplicative).
**D (opportunity cost)** is **not** a driver on this window, contrary to the 2026-board finding.
**G (board peculiarity)** is real and large — the ECR top 15 went from 9 RB / 5 WR in 2021–22 to
5 RB / 10 WR in 2025, and the round-1 position tracks it.

## 4. Counterfactual — how wrong would Y1 have to be?

**Methodological note, recorded rather than hidden.** The first pass computed an analytic flip
threshold from the decomposition (`d* = [(vb_C + oc_C) − (vb_A + oc_A)·m_A/m_C] / 2`). It **failed
production validation: 3 OK, 6 MISMATCH**, and every mismatch flipped *earlier* than predicted,
because lowering the chosen player's projection also lowers his position's opportunity cost (a max
over static VORP, and the chosen player is usually that position's leader). The analytic numbers
are **discarded, not reported**. What follows is measured end-to-end through
`recommend_draft_pick` against an isolated database copy, with the override verified to reach the
engine's own loader (D81's silent-no-op lesson) and `Δ=0` asserted to reproduce the recorded pick.

Pre-registered cell: every RB with preseason ECR ≤ 36 (11–16 players per season). The cell excludes
the replacement-level RB, so the shift moves both `msv` and `daVORP` rather than being cancelled.

Smallest Δ at which the production pick becomes an RB (n=128 non-RB states):

| round | n | flips ≤ 40 | ≤ 56 | ≤ 90 | never ≤160 | median Δ |
|---|---|---|---|---|---|---|
| 1 | 40 | 5 | 9 | 18 | 2 | **120** |
| 2 | 49 | 16 | 20 | 33 | 3 | 80 |
| 3 | 39 | 9 | 15 | 32 | 0 | 90 |
| **all** | **128** | **30 (23%)** | **44 (34%)** | **83 (65%)** | 5 (4%) | **90** |

By season: 2022 median **20** (23/25 within +56), 2023 70, 2021 90, 2025 90, 2024 **120**.

Aggregate position mix along the ladder (all 150 states):

| Δ | 0 | 10 | 20 | 30 | **40** | 55 | 70 | 90 | 120 | 160 |
|---|---|---|---|---|---|---|---|---|---|---|
| QB | 47 | 43 | 42 | 40 | 40 | 35 | 31 | 13 | 4 | 0 |
| RB | 22 | 27 | 37 | 43 | **52** | 66 | 76 | 105 | 132 | 145 |
| WR | 71 | 70 | 62 | 58 | **49** | 40 | 34 | 23 | 9 | 2 |

**RB overtakes WR as the modal early pick at Δ ≈ 40**, essentially the measured bias of 41.5.

Concrete cases (chosen WR vs the best RB on the board at that instant):

| season | pick | chosen | proj → real | best RB | proj → real |
|---|---|---|---|---|---|
| 2023 | 1 | CeeDee Lamb | 291.0 → 403.2 | McCaffrey | 247.9 → 391.3 |
| 2023 | 2–3 | Stefon Diggs | 280.3 → 273.8 | McCaffrey | 247.9 → **391.3** |
| 2024 | 1–4 | A.J. Brown | 297.0 → 216.9 | Breece Hall | 227.3 → 240.9 |

The 2023 Diggs case is the cleanest single illustration: Y1 put Diggs **+32.4** above McCaffrey;
realized, McCaffrey finished **+117.5** above Diggs — a 150-point cross-positional error, with
McCaffrey's 247.9 sitting within 1.2 points of the RB ceiling.

## 5. Roster construction

- First RB mean round **4.38**, median **6.0**, max 7. First WR 1.80, first QB 2.20.
- Concentration: 23 of 50 drafts put 2 of their first 3 picks at one position; none put 2 at RB.
- Conditioning is real and compounding: `WR-WR` → QB in **14/14**; `WR-QB` → RB 9, WR 5;
  `QB` alone → WR 6, TE 5, RB 1.
- Full roster mean: QB 1.88, RB 3.16, WR 5.38, TE 2.08, K 2.00, DST 1.50.
- Realized starter points by opening (observational, **confounded by slot and season**, n small):
  ≥2 WR **2019**, mixed **2004**, all-50 mean 2011, **sd 189**. No detectable difference.

## 6. Realized value

Instrument: `evaluation/draft_oracle.py::audit_draft` (D103's pick-level regret) with its existing
`rounds=(1,2,3)` argument, `season_long`, target format, 10 slots × 5 seasons.
`assert_no_realized_inputs_in_policy()` passed. D106's warning does not apply — that concerns
comparing arms drafting from *different* boards; this is one arm on its own board.

| round | n | mean regret | median | alpha == oracle |
|---|---|---|---|---|
| 1 | 50 | 191.0 | 169.4 | 6% |
| 2 | 50 | 155.8 | 134.6 | 2% |
| 3 | 50 | 157.2 | 146.9 | 2% |

| | Alpha | Oracle | diff |
|---|---|---|---|
| QB | 47 | 13 | **−34** |
| RB | **22** | **80** | **+58** |
| WR | 71 | 52 | −19 |
| TE | 10 | 5 | −5 |

Largest divergences: **WR→RB n=40, mean regret 200.9**; WR→WR 25 @ 152.1; QB→RB 20 @ 159.2;
RB→RB 18 @ 152.0. When Alpha misses, the oracle's player sits a **median 22nd** on Alpha's own
board, top-5 only **7%** of the time.

**Decomposition of regret** — right position/wrong player **131.5** (n=57) vs wrong position
**190.4** (n=93) → the positional component is **+58.9 per pick, +176.6 per draft**, against D97's
**172–250** detection floor.

*Two caveats that must travel with this.* The oracle needs hindsight, so "the oracle wanted RB 53%
of the time" is partly "RBs happened to produce the best outcomes in these five seasons" — 2024 is
an extreme case where the oracle's pick was an RB in **30 of 30** states. And the 131.5/190.4 split
is not a clean causal decomposition; the states where Alpha matched the oracle's position may
simply be easier. The reason it is still worth something is that it agrees in direction with the
§1 conditional-on-market-rank finding, which uses no hindsight at all.

## 7. Three problems, separated

**1 — PROJECTION PROBLEM. Real, and it is one of scale, not ordering.** Y1 cannot express an elite
running back: it has never projected one above 249.1 while 41 real RB seasons cleared 250. The
shrinkage is positionally asymmetric (RB reaches 60% of its realized maximum, QB 86%), which
distorts the *cross-positional* comparison that rounds 1–3 consist of, by +34.7 and +55.4 points in
the ECR 13–24 and 25–36 bands. Mechanism already documented in D82 §5A/5B: 5 training rows ≥350 at
RB, and a partial-dependence curve that peaks at ~246 and turns down.

**2 — DECISION-ENGINE PROBLEM. Real, and it amplifies problem 1.** The value base counts projection
twice in **150/150** early picks, so a positional scale error is worth double. The `risk` multiplier
adds a further systematic ~16% penalty to exactly the position that is under-projected. QB
replacement is drawn at a consumption boundary (207.4) that a 1-QB roster never starts, and at the
snake turn — where opportunity cost is zero by construction — that yields QB in 67% of picks. Note
this is *not* the D81 opportunity-cost mechanism, which does not reproduce on 2021–2025.

**3 — INFORMATION PROBLEM. Real, and on this evidence the largest.** Even when Alpha picks the
oracle's position it still loses **131.5** points, and the whole positional component is only
**+58.9** per pick. When it misses, the right player is a median 22nd on its board. D82 measured
that the market shares most of the RB bias (+36.6 vs +45.5), so the missing signal is not in the
consensus either, and D82/D83 measured that every added-feature and shrinkage arm made the elite
tail worse. Much of the remaining gap is unavoidable outcome variance that no preseason instrument
in this repository can separate — the 92–96% D108 flagged as unattributable.

**None of the three is dominant enough to make the other two ignorable, and the sum of what is
addressable (~177 points per draft) sits inside the instrument's detection floor.**

---

**PRODUCTION CHANGE: NO**

**NEXT PHASE:** Does a per-position **monotone** recalibration of Y1 — one that matches each
position's projected upper quantiles to its realized upper quantiles, and therefore cannot change
within-position ordering but does change cross-positional magnitudes — produce a measurable
improvement in realized draft value over Y1? This is the single axis D99–D106 never spanned (D99
tested such maps only on *identification*; D105/D106 hold each position's value multiset fixed),
and §4 locates the effect exactly there: the aggregate positional crossover (Δ≈40) coincides with
the measured cross-positional bias (≈42). It must be pre-registered as **probably underpowered** —
its own expected effect (~177/draft) is inside the 172–250 floor — so a null would not be
informative, and that should be decided before the phase is spent, not after.
