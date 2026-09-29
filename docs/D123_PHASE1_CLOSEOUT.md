# D123 — Phase 1 research closeout and handoff (D103–D122)

**Read this first if you are starting the next phase in a new session.** It is the authoritative
end state of the draft-decision research program D103–D122. It is written so you do **not** need
the individual phase reports to know what was learned, what is closed, and what not to repeat.
Every figure below was checked against the committed record (`docs/DECISIONS.md` and the phase
reports). Figures come from different board vintages; §3 explains why they must not be mixed.

**Bottom line.** Phase 1 did **not** find a credible path to improving Alpha's individual-pick
value.

* Most of the gap between Alpha and a hindsight per-pick oracle is **information about how
  players' seasons turn out**.
* **No preseason information Alpha stores, or that was tested, recovers a measurable part of it.**
* The decision rule's remaining share under perfect information is **~13%** of the oracle gap.
  Every single-component explanation of that 13% was tested and closed.
* **Closeout decision: NO-GO — current evidence does not justify another experiment.**

D123 is documentation only. It ran no experiment and built no model, feature, rule or arm.
`src/alpha_squad/` is byte-identical to D122 and to `origin/main`.

---

## 1. Orientation for a new session

### 1.1 Alpha's objective

> **Maximize the realized value of each individual draft pick**, from the first pick to the last,
> accounting for the current roster, the remaining pool, league settings, scarcity, timing and
> downstream consequences.

What realized value means in the record:

* It is measured as **realized starter points of the final roster**.
* The per-pick form is D103's one-step roster value: take a candidate, finish the draft with the
  shipped policy, score the roster.
* It is scored under two objectives: season-long (`SEASON_LONG`) and weekly no-foresight lineups
  (`WEEKLY_NO_FORESIGHT`).

**Projection accuracy, top-N hit rates and "the player scored more" are proxies, and Phase 1
showed repeatedly that they do not transfer to pick value.**

* D104: ECR identifies better players (D100) but does not produce better picks.
* D113: +133.9 realized player points per draft converted to +0.8 starter points.
* D114: ECR changes convert at 10.9% from raw points to roster value.

### 1.2 Production baseline

| item | value |
|---|---|
| projections | **Y1** = M6 `uncertainty_catboost_v2` (D78: point model trains through S−1; the conformal interval model does not) + M7 rookies |
| decision engine | `league/draft.py::recommend_draft_pick`, research tier `L0` / `H` (`evaluation/draft_oracle.py::SHIPPED_TIER = "L0"`) |
| L0 score | `(MSV + 1.0·DA-VORP + opp_cost) · fit · risk · survival · capacity`; argmax with a `player_id` tie key; **no roster-legality restriction inside L0** (D112) |
| parity | L0 vs production `H`: **640 / 640** pick states, both 1-QB formats (D107 §4, D108 §3) |
| default format | 10-team 1-QB redraft PPR `target_league`; `dynasty_1qb` is the second shipped 1-QB format; `legacy_2qb_dynasty` stays registered |

### 1.3 Production safety state (verified for D123)

| check | value |
|---|---|
| branch / HEAD before D123 | `claude/survival-opportunity-cost-attribution-d6c7yp` @ `e939943e` (D122) |
| `src/alpha_squad` tree | **`55e763e8a80af908a2c2bcc0ae66753c16b629fc`** — identical at D120, D121, D122, D123 and on `origin/main` (`e02fcf75`) |
| research commits ahead of `origin/main` | 7 (D116–D122) + D123; all research/docs/tests only |
| production behaviour changed anywhere in D103–D123 | **No.** The only `src/` file ever touched was `evaluation/draft_oracle.py` in D103, a research instrument that no production path imports. |

### 1.4 Valid historical period

* **Seasons 2021–2025 only (k = 5 season clusters).**
* **2020** is excluded because it has no preseason market board (D89). The code refuses it: an
  empty board raises `MissingMarketBoardError` / `EmptyMarketBoardError`.
* **2026** is excluded from every backtest; it is the season being drafted.
* The season is the unit of replication. Slots cannot lower the detection floor (D88) and seeds
  cannot either (D92).

### 1.5 Board-vintage caveat — do not mix numbers across vintages

`board_vintage.py` hashes the ECR board and the assembled projections, **but not the nflverse
feature panel** the projections are trained from (D109 §1). A from-source rebuild can therefore
move every projection-dependent number. The program ran on five vintages:

| vintage (combined) | phases | note |
|---|---|---|
| `ca3e2d8a…` | D97–D108 (incl. D103–D106 below) | the "historical" figures |
| `d2955868…` | D109, D110, D111 (risk) | unmerged branch `claude/projection-early-draft-audit-jlv8ui` |
| `63076e2e…` | D111 (ECR), D112 | unmerged branch `claude/ecr-incremental-draft-value-1zcj94` |
| `0d52543044fe99d6…` | D113, D114, D115 | on `origin/main` |
| **`f00226015095534f22e1311c8fa1b4823d66e0679ef6fa8f1817500209dce89f`** | **D116–D122, current (re-verified for D123)** | this branch |

**Rules that follow:**

* Within a phase, arms are paired on one vintage, so its contrasts are valid.
* Across phases, point estimates move. D114 re-ran D104 on a new vintage: +77.3 became +64.5 and
  −132.1 became −153.9; every sign and verdict survived.
* Quote a figure **with its vintage**, or re-run it.

### 1.6 Where the records physically are

**This branch holds** D103–D108 and D113–D122: entries in `docs/DECISIONS.md`, reports in
`docs/D1xx_*.md`, runners in `scripts/research/`.

**Not on this branch** (unmerged, but real and committed on origin):

| phase(s) | branch |
|---|---|
| **D109** projection/early-draft audit, **D110** magnitude sensitivity, **D111** risk multiplier | `origin/claude/projection-early-draft-audit-jlv8ui` (`9510fec`, `9c5c34c`, `aa6b752`) |
| **D111** ECR incremental value, **D112** early feasibility | `origin/claude/ecr-incremental-draft-value-1zcj94` (`f274ddc`, `76a2b38`) |

* **ID collisions:**
  * Two different "D111"s exist on those two branches.
  * A separate **weekly-ranking program** reuses IDs **D109–D114 as W1–W6**
    (`origin/claude/dreamy-albattani-efvroj`). It is **not** part of this draft program.
  * Its W1 data audit is cited in §8 because it bears on the information question.
* **What D113 already recorded:** "no D109–D112 in this repository". That was true of that branch.
  Those records do exist on the branches above, and they are incorporated here, labelled by
  branch and vintage.

---

## 2. Phase 1 inventory (D103–D122)

"Not demonstrated" means the effect was not detected at the resolution available. It does not mean
the effect was shown to be impossible. Figures are labelled with their vintage by §1.5.

| ID | Question | What was tested | Result | Effect on realized pick value | Status | Why |
|---|---|---|---|---|---|---|
| **D103** | Where is per-pick regret, and how much is information vs the rule? | `audit_draft` per-pick oracle (slate maximiser, common continuation), 640 picks; `ORACLE_Y1` = realized points into Y1's rule | Regret 134.8/pick target, 141.8 dynasty (ca3e2d8a), largest early; 92–96% of divergences = oracle's player simply scored more; ORACLE_Y1 **+795.3 / +717.0 per draft**, rule effect under oracle info ≈ −11 | Measurement only | **CLOSED** (instrument) | Reproduced D107/D108; weekly objective *reduces* regret everywhere |
| **D104** | Does the best real preseason ranking (FP ECR) improve drafts? | Y1's own values re-assigned in ECR order (multiset preserved) | +77.3 [−44.1, +198.6] target, **−132.1** dynasty; 57–64% of picks change | Not demonstrated; sign flips by format | **CLOSED** | Below floor; strengthened negative under weekly (D106) and per pick (D114) |
| **D105** | Is the value surface flat in ranking quality? | Within-position scramble ladder α 0→1 | **Thresholded**: α=0.5 changes 88% of picks for −46.5; α=1 costs **−565.8** | Ordering matters only for large degradations | **CLOSED** | Degradation-only; holds value multiset fixed (says nothing about magnitudes) |
| **D106** | Is the plateau objective-specific? | D105 ladder under weekly scoring | Persists (H1), sharper threshold; ECR worse under weekly (+48.4 / −202.4) | — | **CLOSED** | Stopping rule met |
| **D107** | Does the D86–D106 record reproduce? | Independent re-aggregation | Reproduces; 2 over-strong statements corrected; "projections don't matter" too strong | — | **CLOSED** | Audit |
| **D108** | Program closeout D86–D107 | Record topology | Found orphaned D93/D94 (retracting D86–D92's O-tier control); lint fixed | — | **CLOSED** | Audit |
| **D109** *(branch)* | What does Alpha do in rounds 1–3, and why? | Forensic audit, 150 early states (d2955868) | RB projection **scale** defect (never > 249.1); `msv == projection` in 150/150 early picks (value base = 2×proj − repl); positional component ≈ +58.9/pick ≈ +177/draft, inside the 172–250 floor | Not demonstrated | **CLOSED** as diagnosis | Addressed by D110/D111; no lever cleared resolution |
| **D110** *(branch)* | Is cross-position projection magnitude a value lever? | Per-position multipliers, 14 arms, 280 drafts | Decisions move a lot (first RB rd 4.35 → 1.80); **value does not** (powered null in 8/9 arms); `qb_110` **−39.3 [−59.0, −19.7]** (harm) | None; raising QB harms | **CLOSED** | Powered null; RB gain was one season (2024) and came from rounds 4+ |
| **D111** risk *(branch)* | Is the `risk` multiplier a useful risk measure? | Algebra + ablation (`confidence = 1`) | `confidence` is a deterministic function of the projection (per-season-position constant width); ablation +26.7 [−112.9, +166.4] target, +52.7 2-QB — powered nulls, single-season artifacts | None | **CLOSED** (current multiplier) | 33% of picks change, no value; the defect is upstream (no player-level uncertainty) |
| **D111** ECR *(branch)* | Does ECR *added to* Y1 (rank consensus) add value? | Borda board/decision consensus, w = 0.5 (63076e2e) | +21.4 / +80.1 / **+88.9 [+5.5, +172.2]** / +72.1: all positive, all below the floor; early +, late −; the only resolved effect (+241 / +215) is a benchmark roster-legality artifact (D112) | Not demonstrated | **CLOSED** as a major intervention | D114 bounds ECR per pick at ±13 with format sign flip; draft-level adoption formally unresolved |
| **D112** *(branch)* | Does Alpha have an early roster-feasibility problem? | Feasibility-slack audit, 1,600 picks | Legality binds **0 / 1,600**; min live slack 5; D111's +241 = ECR-alone drafter forfeiting K/DST | None | **CLOSED** | Deterministic proof; the proposed counterfactual is not definable |
| **D113** | Does positional capacity cost value? | Cap removal, 450 drafts + matched states (0d525430) | +0.8 / +0.9 / **−25.1 [−43.1, −7.2]** (2-QB worse); own MDE 15.5–46.9 | None; capacity mildly protective | **CLOSED** | Effect bounded, not merely undetected |
| **D114** | Is matched-state pairing a power multiplier? Is ECR a per-pick signal? | One-step vs free-run estimators | Pairing tightness came from an inert treatment; ECR one-step **+1.32 [−12.1, +14.7]** / −4.69; one-step MDE ≈ 13 pts/pick; D97's PROD-vs-NAIVE unreconstructible | None | **CLOSED** | Establishes per-pick resolution (~13) |
| **D115** | Where does the ~135-pt per-pick regret live? | 640-pick attribution; existing arms one-step | 74% wrong position; **47% "sequencing"** (C1∧C2); preseason arms recover −3.2% to +2.7%; ORACLE_Y1 73.5% / 69.6% | Attribution | **CLOSED** | No preseason arm recovers anything |
| **D116** | Is the "sequencing" regret an ordering loss? | Survival ranking on 151/155 C1∧C2 pairs (f0022601) | Survival correct **87.5% / 93.0%**; Alpha took the oracle's player at its next pick **0/151**; neutralising survival or opportunity cost flips 0 | None | **CLOSED** | It is valuation lost in the value base, not timing |
| **D117** | Does Alpha hold suppressed upside information? | All M6 outputs on the pairs | **M6 has no player-level uncertainty** (p10/p90 = projection + per-season-position constant); oracle's player beat his own p90 in 105/117 | None | **CLOSED** | Nothing exists to be suppressed |
| **D118** | Is player-specific upside predictable preseason? | Walk-forward ridge, 12 pre-registered features | Market-vs-model disagreement ρ **+0.27** OOS (all seasons); **≥ 95% of error variance unpredictable**; flips 3/28 pairs; decision gain CI spans 0 | Not demonstrated | **CLOSED** via D119 | Predictable ≠ decision-useful |
| **D119** | Is the D118 correction detectable? | Frozen treatment; power calculation | **8% power** at the smallest interesting effect (3.58 pts/pick); MDE 21.2 | Not tested (NO-GO) | **CLOSED** | Underpowered, not refuted |
| **D120** | With perfect projections, what stops Alpha? | ORACLE_Y1 instrument audit, ARM 1–4 | Stale `confidence` caused 14.4 / 12.8 pp of the "27%" residual; stale replacement levels 0; **corrected recovery 87.0% / 87.2%**; decision residual **13.0% / 12.8%** (17.8 [4.8, 30.9] / 16.8 [2.1, 31.6] pts/pick) | Ceiling measurement | **CLOSED** (measurement) | Residual located: 74% R1–6, 87–92% wrong position |
| **D121** | Value term or survival urgency in that residual? | Attribution on R1–6 RB→WR/QB (23 / 15 states) | Value-led 66% / 60%; survival alone 15% / 11%; no neutralisation CI excludes 0 | None | **CLOSED** | No component meets the candidate bar |
| **D122** | Does MSV over-credit empty slots vs the continuation? | Leave-one-out continuation-aware MSV (pre-registered), pairwise "otherwise" (amendment) | Leave-one-out does not remove the RB advantage; its re-rank moves 0 RB→QB picks and costs dynasty **−5.9 [−11.4, −0.4]**/state over R1–6; pairwise ≈ one-step by construction; RB→QB = 3 decisions, all 2022 | None; harm in dynasty | **CLOSED** | No actionable MSV defect |

---

## 3. Final Alpha diagnosis

### 3.1 How much of Alpha's regret is attributable to player-value / projection information?

**Most of it, ~87%, but almost none of that is reachable with preseason information.**

The per-pick evidence (f0022601 unless stated):

* Giving Alpha's unchanged rule **perfect season-long projections**, with the derived confidence
  recomputed consistently (D120 ARM 4), recovers **87.0%** (target) and **87.2%** (dynasty) of
  the per-pick oracle's advantage.
* At the draft level, perfect information is worth **+795.3 / +717.0** points per draft (D103,
  ca3e2d8a); D114 re-measured it at +783.6 / +726.9 (0d525430).
* **92–96%** of Alpha-vs-oracle divergences are the oracle's player simply scoring more (D103).
  * The oracle's player sits at a median rank **73** on Alpha's own board (D103).
  * On the sequencing pairs he is Alpha's **#125** (D116).
  * He beat his own p90 in **105 of 117** cases (D117).

That "information" is **realized outcome knowledge**. D103 §7 records the limit: the
"scored more" share **conflates bad information with unavoidable variance**. Nothing in Phase 1
separates the two, so none of the ~87% may be called "projection error".

**Reachable with preseason information: ~0% measured.**

* Every preseason-available arm recovers **−3.2% to +2.7%** of per-pick regret, with every
  interval spanning zero and signs disagreeing across formats (D115). The arms were ECR ordering,
  D99's calibration arms and the ECR per-pick signal.
* Y1 sits ~23 pts/pick above a random within-position scramble and ~105 below perfect ordering
  (D115, 0d525430). That is roughly 18–21% of the within-position ordering information available.
* On stored information, **≥ 95% of projection-error variance is unpredictable out of sample**
  (D118).

### 3.2 How much remains after correcting the D120 stale-confidence artifact?

Three different quantities have been called "the residual". Keep them apart.

| quantity | target | dynasty | meaning |
|---|---|---|---|
| **Old instrument's measured residual** (ORACLE_Y1 as committed; D115 on 0d525430: 73.5% / 69.6% recovery; D118/D120 on f0022601: 72.7% / 74.4%) | **27.3%** | **25.6%** | A correct measurement *of that arm*. The arm kept M6's `confidence` computed from the OLD projection, so it was not a consistent perfect-projection arm. Not overwritten. |
| of which: stale-confidence instrument artifact | 14.4 pp (53%) | 12.8 pp (50%) | Paired effect +19.8 [+8.8, +30.7] / +16.9 [+9.7, +24.2] pts/pick |
| of which: stale replacement levels | 0 pp | 0 pp | 0 of 640 picks change |
| **Corrected residual = genuine decision-rule residual** (1 − R(ARM 4)) | **13.0%** = 17.8 [4.8, 30.9] pts/pick | **12.8%** = 16.8 [2.1, 31.6] | What the Y1 rule leaves with consistent perfect projections |

The corrected residual and the decision-rule residual are the same number here. ARM 4F (a full
static rebuild) picks identically to ARM 4 at all 640 states, so no other stale input remains.

### 3.3 What the corrected perfect-projection experiment tells us

**It establishes:**

1. **The rule is not the main limitation.** With consistent perfect projections, L0 captures ~87%
   of what a hindsight per-pick maximiser captures.
2. **The residual is localised.**
   * 74% is in rounds 1–6.
   * 87% (target) / 92% (dynasty) is wrong-position.
   * The largest flows are RB→WR and RB→QB (D120).
   * 44% overlaps the C1∧C2 "both players were available" overlay.

**It does not establish:**

* **That the 13% is reachable.** It is measured against a hindsight oracle that scores every
  candidate with realized outcomes.
* **That a different rule would capture it under *real* projections.** There the rule acts on
  much noisier values, and D105 shows the value surface is flat to large decision changes.
* **Why the residual exists.** D121 and D122 tested the obvious single-component explanations and
  closed them (§4).

**It is not an upper bound on anything achievable.** ORACLE_Y1 and ARM 4 need realized outcomes.

### 3.4 Parts of the decision engine investigated without a production-worthy improvement

| component | phases | finding |
|---|---|---|
| value base (MSV + DA-VORP) | D85, D97 (value bases), D109, D110, D121, D122 | MSV double-counts projection early (D109); leave-one-out continuation-aware MSV does not fix ranking and its re-rank hurts dynasty (D122) |
| cross-position magnitude | D110 | Decisions move, value does not (powered null); QB up is a harm |
| risk multiplier (`confidence`) | D110, D111, D117, D120 | Not a risk measure; ablation null; relevant only as an instrument defect under perfect projections |
| survival urgency | D97, D116, D121 | Directionally right; neutralising flips ~0; survival alone 15% / 11% of the R1–6 residual |
| positional opportunity cost | D109, D116, D121 | Near-parity early; neutralising flips 0 |
| roster fit | D121 | +6.5 [−3.5, +13.0], unresolved |
| capacity ceiling | D112, D113 | Late-round only; removing it is neutral or harmful |
| roster legality / early feasibility | D112 | Never binding (0 / 1,600) |
| scoring objective | D103, D106 | Weekly objective reduces regret and sharpens the plateau; no hidden late value |
| ranking source (ECR) | D104, D111, D114 | Per pick ±13, sign flips by format |

### 3.5 Information-limited, architecture-limited, or greedy vs hindsight?

**Information-limited.** This is the strongest evidence, and it applies to *outcome* information.

* Perfect projections into the unchanged rule close ~87% of the per-pick gap (D120) and are worth
  +717 to +795 per draft (D103).
* Destroying Y1's ordering costs 566–721 (D105/D106), so ordering does real work.
* But no preseason information tested moves within-position predictive quality by more than
  ~+0.024 Spearman (ECR, D105). D105 estimates a resolvable effect needs about **±0.5**.
* ≥ 95% of error variance is unpredictable from stored inputs (D118).
* **So: information-limited, with no known preseason source of the missing information.**

**Decision-architecture-limited: weak evidence, bounded.**

* The rule residual under perfect information is ~13% (≈ 17–18 pts/pick). Its CIs have lower
  bounds of 4.8 / 2.1, so it is real but not large.
* It is concentrated in a few early RB-vs-WR/QB states.
* **No single component explains it** (D121). The one continuation-aware valuation that exists
  exactly in the machinery made dynasty worse (D122).
* Under real, noisy projections the rule sits on a plateau: 88% of picks can change for ~46
  points (D105). A better rule acting on the same noisy values has little surface to exploit.

**Partly an unavoidable consequence of drafting before outcomes versus a hindsight oracle: strong
supporting evidence.**

* The oracle is itself one-step: a slate maximiser with a common continuation.
* Its advantage is almost entirely **knowing who breaks out**: 92–96% "scored more" (D103), and
  tail outcomes beyond p90 (D117).
* Normalised by the dispersion available at each pick, Alpha's regret is 0.6–0.9 of the slate
  spread. That is close to what an uninformed draw gives: D86 measured random 122.3 vs Alpha 116.2
  (D107 §3).
* The per-pick oracle is not an achievable target. It is a ruler.

### 3.6 What we do NOT know

1. **How the "oracle's player scored more" 92–96% splits** between knowable-but-unused
   information and irreducible variance. No Phase 1 instrument can separate them (D103 §7; D107
   reopen criterion 4).
2. **Whether time-sensitive preseason role information** — depth charts, camp injuries, role
   changes — would predict within-position error beyond the market. It is **not stored and was
   never tested**. D118's null is explicitly scoped to the stored information set.
3. **Whether the ~13% rule residual is reachable by any policy that cannot see outcomes**, and
   what fraction of it survives under real projections.
4. **Whether improvement-direction effects are symmetric** to D105's degradation ladder. Only
   degradation was measured; the only improvement anchor, ORACLE_Y1, changes values, not order.
5. **Anything outside 2021–2025 at k = 5.** Every draft-level interval is season-bound. D107
   estimated the floor falls from ~172 toward ~130 at k = 7.
6. **How much of the cross-vintage movement is nflverse restatement.** The panel is not hashed
   (D109 §1).

---

## 4. Closed hypotheses — do not reopen without the stated evidence

A null that was not statistically conclusive is **not** by itself grounds to reopen. Each row names
what would legitimately reopen it.

### Projection calibration

* **Tested:** D68 (X1–X4: per-position additive/affine/rank-band/empirical-Bayes, walk-forward),
  D69 (RB-only, abandoned pre-implementation), D99 (identification), D115 one-step (X2/X3 recover
  +1.0% / −0.3% target).
* **Showed:** every arm improved MAE and failed its gates (G3/G4 at WR/TE). Top-6 identification
  cannot improve (D99). Draft-level recovery ≈ 0.
* **Uncertain:** a calibration that changes magnitudes jointly with a consistent `confidence`.
* **Reopen only if:** a pre-screened calibration moves within-position predictive Spearman vs
  realized by far more than +0.024 (D105 harness) **and** passes D68's gates.

### Elite-RB projection shape

* **Tested:** D80 (four pre-registered fixes), D109 (RB never projected > 249.1; bias −41.5 at
  ECR ≤ 30), D110 (RB magnitude arms).
* **Showed:** the under-projection is real, but all four fixes failed. Raising RB magnitude moves
  first-RB round sharply with **no** value gain (powered null). The apparent gain was one season,
  2024, and came from rounds 4+.
* **Uncertain:** whether a shape fix plus consistent risk would behave differently. D110 §5 bounds
  that interaction at ~4% relative.
* **Reopen only if:** a shape fix clears D80's gates **and** an existing-harness free-run draft
  test shows a gain in more than one season.

### Cross-position projection magnitude

* **Tested:** D110 (14 arms, 280 drafts, powered to ~177/draft).
* **Showed:** decisions are highly sensitive; value is not. `qb_110` is a resolved harm (−39.3).
* **Uncertain:** only the joint magnitude-and-risk variant.
* **Reopen only if:** new seasons (k ≥ 7) lower the floor below D110's observed point estimates.

### Risk multiplier

* **Tested:** D111 (algebra + ablation, 2 formats), D117 (all M6 outputs), D120 (stale-risk
  artifact).
* **Showed:** it is not a risk measure (a function of the projection). Ablating it changes 33% of
  picks and no value (powered null).
* **Uncertain:** whether a genuine player-level uncertainty measure could help. That is D111's open
  question, and the model cannot currently produce one.
* **Reopen only if:** a player-level uncertainty estimate is shown to predict absolute error out of
  sample beyond the (season, position) constant. D118 found stored inputs explain ≤ 5% of error
  variance.

### ECR replacement

* **Tested:** D104, D105/D106 (on-ladder placement), D114 (one-step).
* **Showed:** +77.3 / −132.1 per draft; per pick +1.32 [−12.1, +14.7] / −4.69; the sign flips by
  format; worse under weekly.
* **Uncertain:** draft-level adoption is formally unresolved (target CI admits +148).
* **Reopen only if:** k ≥ 7 seasons, or a ranking source pre-screened to move predictive Spearman
  materially more than ECR.

### ECR blending as a major decision intervention

* **Tested:** D111-ECR (Borda board/decision consensus), D118/D119 (market-vs-model correction).
* **Showed:** all four positive but below the floor. Early rounds +, late rounds −. Per pick
  bounded ±13 (D114). The D118 correction has 8% power (D119).
* **Uncertain:** a small positive draft-level effect cannot be excluded.
* **Reopen only if:** k ≥ 7 seasons, **and** the pre-registered effect is above the then-current
  one-step MDE.

### Early roster feasibility

* **Tested:** D112 (1,600 picks).
* **Showed:** binding 0 / 1,600. The ECR-alone +241 / +215 was a benchmark artifact.
* **Uncertain:** nothing material.
* **Reopen only if:** a format change makes live slack reach 0 in real drafts.

### Capacity

* **Tested:** D112, D113 (ablation, 3 formats, matched states).
* **Showed:** late-round only; neutral in 1-QB formats; −25.1 in 2-QB (capacity helps).
* **Uncertain:** none at this resolution; the effect is bounded (MDE 15.5–46.9).
* **Reopen only if:** a new format where caps bind in rounds 1–10.

### Survival urgency as the primary explanation

* **Tested:** D97, D116, D121 (with neutralisation arms).
* **Showed:** ranking accuracy 87.5% / 93.0%. Alpha never took the oracle's player at the next
  pick (0/151). Survival alone overturns a correct value term in 3/23 and 1/15 residual states.
  Neutralising it gives +10.0 [−11.5, +34.3].
* **Uncertain:** S-shaped magnitude miscalibration exists (D116), but is not decision-relevant.
* **Reopen only if:** a residual population where survival alone, not value, carries the choice
  in a majority of seasons.

### Opportunity cost as the primary explanation

* **Tested:** D109, D116, D121.
* **Showed:** near-parity across positions early on 2021–2025 (D81's asymmetry was a 2026-board
  property). Neutralising it flips 0 (D116). Shapley share ~10%.
* **Uncertain:** nothing material.
* **Reopen only if:** the same evidence standard as survival.

### Stored upside / uncertainty

* **Tested:** D117, D118.
* **Showed:** M6 holds **no player-level uncertainty**. Market disagreement predicts error
  (ρ +0.27) but not decisions.
* **Uncertain:** information Alpha does not store (§5, §8).
* **Reopen only if:** new, timestamped inputs are added. Stored inputs are exhausted.

### Market-vs-model correction

* **Tested:** D118 (predictability), D119 (power).
* **Showed:** NO-GO at 8% power. The realistic effect is ~1–3 pts/pick against an MDE of ~21.
* **Uncertain:** it was not run, so it is not refuted.
* **Reopen only if:** k grows enough that the power calculation clears 0.8 at the pre-registered
  smallest interesting effect.

### Empty-slot MSV over-crediting

* **Tested:** D109 (msv = projection early), D121 (RB→QB mechanism), D122.
* **Showed:** MSV's empty-slot credit is arithmetically mostly value the continuation would supply
  otherwise — **for both players in a pair**. No exact continuation-aware quantity fixes the
  ranking. RB→QB is three 2022 decisions; in target, 3/7 are sequencing, and the weekly objective
  prefers the RB in 5/7. **Not a confirmed production bug.**
* **Uncertain:** only through a new, pre-registered valuation algorithm.
* **Reopen only if:** RB→QB states from more than one season, **and** a decision-time "otherwise"
  valuation defined for every candidate.

### Continuation-aware MSV

* **Tested:** D122 (leave-one-out, pre-registered; pairwise, amendment).
* **Showed:** leave-one-out prefers the RB 7/7 (target RB→QB). Its re-rank moves no primary pick to
  the oracle and costs dynasty −5.9 [−11.4, −0.4] per state. The pairwise measure equals one-step
  value minus spillover by construction.
* **Uncertain:** none that existing machinery can address.
* **Reopen only if:** a re-rank passes the decision-relevance test in both formats without
  reverse-direction losses.

**Closed earlier, and to be treated the same way** (pre-D103, recorded in D97/D107/D108):

* the nine alternative value bases (D85);
* the O-tier "kicker hoarding" story, retracted by D93/D96;
* a third scoring objective chosen because two produced nulls (D106 §7);
* a NAIVE arm (never existed; D114).

---

## 5. What remains open — only genuinely unresolved questions

**A. Information questions**

* **A1. Split of the 92–96% "scored more" (§3.6-1).** Everything else depends on it. **No
  instrument exists.**
* **A2. Time-sensitive preseason role information** (§8). Untested because it is not stored.

**B. Decision-architecture questions**

* **B1. Reachability of the ~13% rule residual** by a policy that cannot see outcomes. It is
  measured and localised, but has no candidate mechanism after D121/D122.

**C. Data-quality / timestamp questions**

* **C1. The nflverse panel is not hashed by `board_vintage.py`.** Projection-dependent figures move
  across rebuilds (§1.5). This is a production-code instrument gap. Fixing it is a production
  change and was not made.
* **C2. Point-in-time recoverability of role signals.** The injury file keeps one final row per
  player-week, with `date_modified` = last edit (weekly W1 audit). Depth charts are verified in
  this repository only for 2025–2026. No trustworthy pre-draft snapshot of either is known to exist
  (§8).

**D. Measurement questions**

* **D1. Season clusters are the binding constraint.** k = 5 caps free-run resolution near
  ~94–260/draft. One-step resolves ~13/pick, which is ~10% of mean per-pick regret. Only new
  seasons move this (D88, D92, D107, D114).
* **D2. Improvement-side symmetry of the D105 ladder** (§3.6-4).

Not listed as open, deliberately: another value base, another objective, another ranking blend,
another multiplier ablation, another feasibility or capacity variant. These are closed in §4.

---

## 6. Decision-architecture assessment (conceptual only; nothing implemented)

Two facts bound every architecture here:

* Under **perfect** projections, the whole gap a better rule could close is ~13% (≈ 17–18
  pts/pick, CI lower bounds 4.8 / 2.1).
* Under **real** projections, D105 shows most decision changes are value-neutral.

| architecture | Phase 1 evidence for it | enough justification for future research? |
|---|---|---|
| **Multi-pick lookahead** | D115's 47% "sequencing" looked like an opportunity; D116 showed it is valuation, not ordering (0/151; survival already right 87–93%) | **No.** The evidence that motivated it was re-attributed to information. |
| **Expected future roster value** | D122's leave-one-out continuation-aware MSV is the closest existing form; it hurt dynasty (−5.9/state) | **No.** The one exact instance was harmful. |
| **Counterfactual continuation** | D122 pairwise "otherwise" ≈ one-step value by construction; needs a hindsight-free reference for every candidate | **No.** It is not definable without a new algorithm, and there is no evidence its gain would exceed ~13% × (real/perfect information ratio). |
| **Opponent-aware planning** | Survival/availability already ~90% right (D116); opponents are a fixed ECR field in the benchmark | **No.** Timing is not where regret lives. |
| **Flex-aware future roster value** | D122: WR replacement enters via FLEX in every state; flex already in the allocator (MSV, one-step scoring) | **No.** It changes which measure favours whom, not realized value. |
| **Dynamic positional scarcity** | Draft-aware replacement levels are already in production (DA-VORP); stale static levels had **0** effect (D120 ARM 2) | **No.** |
| **Draft-state value (vs isolated candidate score)** | The only framing that could address the 13%; no Phase 1 result isolates a mechanism for it; D105 says the value surface is flat to large decision changes | **Not yet.** It would need an evaluation that does not grade against a hindsight oracle, and a reason to expect > 13 pts/pick under *real* projections. Neither exists. |

**Recommendation: no architecture research on current evidence.** A complex planner is not
justified by being theoretically better. Its ceiling under perfect information is ~13% of the
oracle gap, and under real information the ceiling is unmeasured and likely smaller.

---

## 7. What NOT to repeat

1. **Do not score pick changes at player level.** "The changed pick scored more" is repeatedly
   uncorrelated with roster value: D104, D111 (+10.9 player vs +7.2 roster), D113 (0.6%
   conversion), D114 (10.9%). Use one-step roster value (D103/D114) or free-run roster value.
2. **Do not grade arms by regret against their own oracle.** It is arm-relative and produced a
   false "improvement" in D106 §6.
3. **Do not treat the 172–250 "floor" as universal.** Report each contrast's own MDE, slots moved
   and first-divergence round (D114).
4. **Do not buy power with slots or seeds.** Only seasons add clusters (D88, D92).
5. **Do not quote the old ~27% ORACLE_Y1 residual as the rule residual.** It is 13% (D120).
6. **Do not describe MSV as a confirmed bug** (D122), and **do not state "projections don't
   matter"** (D107), "the objective is flat" (retracted D105), "Y1 is optimal", or "the draft is
   solved" (D108 forbidden overclaims).
7. **Do not mix vintages** (§1.5), and do not claim a projection experiment reproduces from the
   board hash alone (D109 §1).
8. **Do not use `dynasty_values`** (single 2026-09-18 snapshot, future leakage), nflverse injury
   rows filtered by `date_modified` as if they were point-in-time, or `games.csv` spread/weather as
   pre-game information (closing/realized values; W1).
9. **Do not reopen a §4 hypothesis because its null was not statistically conclusive.** Use the
   reopen criteria.

---

## 8. New-information audit: time-sensitive role information (audit only)

Nothing was collected, built or run. For each signal, the table says whether it is plausibly large
enough, whether it is historically recoverable with a trustworthy pre-draft timestamp, whether it
can be leakage-free, and whether Phase 1 tested an equivalent.

| signal | could it change ordering enough? | recoverable with trustworthy pre-draft timestamp? | leakage-free? | tested before? |
|---|---|---|---|---|
| **Depth-chart / starting-role changes** | Plausibly. The oracle's players are breakouts outside Alpha's and the market's top ranks (median rank 73 / #125; beat p90 105/117), which role changes could explain. **Unmeasured.** | **Not established.** nflverse `depth_charts` coverage verified in this repo only for 2025–2026 (`DATA_SOURCES.md`). Historical depth charts, where they exist, are in-season game-week charts; an August snapshot is not known to exist. | Only with a verified point-in-time snapshot. | **No.** Not stored. |
| **Injury / availability changes** (camp, preseason) | Plausibly for individual players; D86 puts 17.8% of realized points in bench / availability effects. | **No, as stored.** One final row per player-week; `date_modified` is the last edit (4,818 of 6,213 on Friday, 2024). Filtering to a cutoff creates a missingness bias that flatters any injury-using system (W1 §2). Regular-season only; no training-camp record. | Not with this source. | **No.** |
| **Teammate injuries / departures** | Plausibly (vacated targets/carries). | Roster moves are dated (weekly rosters 1999–2026; transactions not stored). Injury component inherits the injury-file problem. | Partially: departures are dated; injuries are not. | **No.** |
| **Preseason usage** (preseason snaps / targets) | Weak prior; preseason usage is sparse for starters. | Not verified: `snap_counts` 2012+ is stored; whether preseason games are included is unverified. | Yes, if preseason rows exist. | **No.** D118 used **S−1 regular-season** snap/target share (CI spans 0). |
| **Coaching / scheme changes** | Plausibly, but slow-moving and largely known before the market forms. | Dated by season (head-coach changes are public, pre-season). | Yes. | **No.** |
| **Market movement** (ECR trajectory Jun → draft) | The market already absorbs public role news; its level is in D118/D119. Movement is a proxy for role news. | **Yes.** `market_snapshot` / DynastyProcess `db_fpecr` has **15–20 dated scrapes per June–September**, 2021–2025, with `scrape_date`. | Yes, with as-of joins (the existing contract). | **Partly.** D104/D111/D114 used a single Jul/Aug board (per pick ±13); D118's market-vs-model gap ρ +0.27 but decision-useless (D119). **Trajectory never tested.** |

**Assessment.**

1. **Could it matter?** Possibly — it targets exactly the breakouts that dominate regret. But no
   Phase 1 number bounds its size.
   * The market already prices public role news. Market-derived signals, the only role proxy
     tested, are bounded per pick at ±13 (D114) or decision-useless (D118/D119).
   * To be resolvable it would need to move within-position predictive Spearman by roughly the
     amount D105 identified (~±0.5), against ECR's +0.024. **No evidence suggests any role signal
     comes close.**
2. **Historically recoverable?**
   * **Market movement: yes.**
   * **Depth charts and camp injuries: not established.** The known sources are final-state or
     in-season.
3. **Leakage-free?** Only market movement and dated roster/coaching changes, as currently known.
4. **Previously tested?** Only as the market level (D104, D111, D114, D118). The trajectory, and
   every non-market role signal, is untested.
5. **Data a legitimate experiment would need:**
   * **(a)** point-in-time pre-draft snapshots, with a verifiable capture timestamp, of depth
     charts and injury/practice status for 2021–2025. Their existence must be proven first. If
     they are forward-only, the experiment needs several future seasons to reach even k = 5.
   * **(b)** the existing dated ECR scrapes for any market-movement arm.
   * **(c)** a pre-registered walk-forward error model, one-step evaluation (D114) and a power
     calculation (D119-style) **before** any run.

**Conclusion:** the information direction is the only one the evidence points at in principle. But
its historical data is not known to exist with trustworthy timestamps. The one recoverable piece,
market movement, sits in a signal family whose level has already been shown to be decision-useless
at this resolution. **This does not justify an experiment now.**

---

## 9. Phase 1 bottom line

### WHAT WE KNOW

* **Alpha's per-pick regret against a hindsight oracle is dominated by outcome information.** With
  perfect projections the unchanged rule captures **~87%** of the oracle's per-pick advantage (D120).
* **The genuine decision-rule residual is ~13%** (≈ 17–18 pts/pick), not the ~27% the old
  instrument reported. Half of that was a stale-confidence artifact (D120).
* **The value surface is thresholded.** Y1's ordering does real work (566–721 lost when fully
  scrambled), but most decision changes are value-neutral (88% of picks change for ~46 points,
  D105/D106).
* **No preseason information tested or stored recovers a measurable share of regret.** Arms recover
  −3.2% to +2.7% (D115). ≥ 95% of error variance is unpredictable from stored inputs (D118).
* **Proxy metrics do not transfer to pick value.** Better identification, higher player points and
  more changed picks have each failed to move roster value.

### WHAT WE RULED OUT / CLOSED

* Projection calibration, elite-RB shape fixes and cross-position magnitude as value levers
  (D68/D69/D80/D99/D110).
* The risk multiplier as a meaningful risk measure or a value lever (D111/D117).
* ECR replacement and ECR blending as major decision interventions (D104/D111/D114).
* Early roster feasibility (never binding) and capacity (neutral or protective) (D112/D113).
* Survival urgency and opportunity cost as primary explanations (D116/D121).
* Stored upside/uncertainty as suppressed information (D117). The market-vs-model correction was
  underpowered (D118/D119).
* Empty-slot MSV over-crediting and continuation-aware MSV as actionable rule defects (D121/D122).
* Lookahead/sequencing as an ordering loss: the "sequencing" regret is valuation (D116).

### WHAT REMAINS UNKNOWN

* How much of the "oracle's player scored more" regret was knowable preseason at all, versus
  irreducible variance.
* Whether time-sensitive role information exists historically with trustworthy pre-draft
  timestamps, and whether it would predict within-position error beyond the market.
* Whether any outcome-blind policy can reach part of the ~13% rule residual.

### WHAT WOULD HAVE TO BE TRUE FOR ALPHA TO IMPROVE

All three of these:

1. **A new preseason information source that stores genuinely point-in-time data.** It must move
   **within-position predictive Spearman vs realized by an order of magnitude more than ECR's
   +0.024**, pre-screened with D105's harness, and pass D118-style walk-forward validation.
2. **Detection resolution to match.** Either the effect is large enough to clear one-step MDE
   (~13–21 pts/pick) at k = 5, or more completed seasons (k ≥ 7) lower the floor. A D119-style
   power calculation must clear 0.8 before any run.
3. **Scoring on realized roster value** (one-step and free-run), in both 1-QB formats, without
   format sign flips.

For the decision rule alone, a mechanism for the ~13% residual would have to be identified that:

* survives real (non-hindsight) projections;
* replicates across seasons;
* does not reproduce D122's reverse-direction losses.

Nothing in Phase 1 currently satisfies either set of conditions.

---

## 10. Next-phase candidates (at most three; not ranked)

| | 1. Point-in-time preseason role information | 2. Draft-state value / lookahead architecture | 3. Player-level (heteroscedastic) uncertainty |
|---|---|---|---|
| **label** | **CONDITIONAL** | **DO NOT TEST YET** | **DO NOT TEST YET** |
| hypothesis | Pre-draft role signals (depth chart, camp injury/practice status, role changes) predict within-position projection error beyond the market, enough to change picks | Scoring draft *states* rather than isolated candidates captures part of the ~13% perfect-information rule residual | A player-varying uncertainty estimate predicts absolute error and improves risk-aware picks |
| required data | Point-in-time depth charts and injury/practice reports with verifiable capture timestamps, 2021–2025 (existence unproven); existing dated ECR scrapes | Existing machinery only | New inputs; M6 and stored features cannot produce player-level width (D111/D117/D118) |
| timestamp / leakage requirement | Capture time ≤ each season's draft board date; **no** `date_modified` filtering of final-state files; walk-forward only | Policy must never see realized outcomes (`assert_no_realized_inputs_in_policy`) | Walk-forward; S−1 residuals only |
| decisions it could affect | Same-position and early cross-position picks where breakouts decide regret | R1–6 RB-vs-WR/QB states (D120) | Picks between similarly projected players |
| why Phase 1 did not answer it | Not stored; D118's null is scoped to stored information | D121/D122 tested single components, not an architecture | M6 has none; D118 showed stored inputs explain ≤ 5% of error variance |
| result that would justify proceeding | **First, a data audit (not an experiment):** proof that timestamped pre-draft snapshots exist for ≥ 5 seasons. Then a pre-screen showing a within-position Spearman gain far above +0.024, and a power calculation ≥ 0.8 | A concrete mechanism for the 13% that survives real projections, and an evaluation not graded against a hindsight oracle | Out-of-sample prediction of absolute error beyond the (season, position) constant, with a decision-level power calculation ≥ 0.8 |
| result that would kill it | No trustworthy historical point-in-time source (forward-only collection would need several future seasons); or a pre-screen gain comparable to ECR's | Any evidence the residual shrinks under real projections to below one-step MDE; D122-style reverse-direction losses | Stored or new inputs fail to predict error size (D118 already points this way) |
| evidence for the label | The only direction consistent with an information-limited problem, but its data is unverified and its nearest tested proxy (market) is null. **Conditional on the data audit.** | The ceiling is 13% under *perfect* information, its CI reaches 2–5 pts/pick, and the one exact instance hurt dynasty | No input known to carry the signal; three phases converge |

No candidate is labelled HIGH PRIORITY. None has evidence of an effect above the resolution of the
available instruments.

---

## 11. Closeout decision

**NO-GO — current evidence does not justify another experiment.**

Phase 1 established what limits Alpha:

* **Outcome information dominates**, and no preseason information available to the project
  recovers it measurably.
* **The decision rule's perfect-information residual is small (~13%)**, localised, and without a
  mechanism.

Candidate 1 is the only direction the evidence points toward, and it is **not an experiment that
can be run now**. Its prerequisite is proving that trustworthy historical point-in-time role data
exists. If a future session wants to revisit, that data-provenance audit is the only legitimate
first step, and it must be treated as a fresh decision, not as the start of an experiment.

Production is unchanged: **Y1 remains production.**
