# D116 — Did Alpha's survival / opportunity-cost system know which player would disappear first?

**Headline: yes, and it was mostly right. The survival model ranks which of the two players the
opponent field takes first correctly on 87.5% of decisive pairs (target) and 93.0% (dynasty).
Mostly it said that *Alpha's own* player would go first, and it was correct. So on D115's
"sequencing" picks, Alpha's order was usually right for availability. The regret on those picks
is not an ordering loss. The oracle's player there is someone Alpha ranks about #125 on its own
board, projects at 58% of Alpha's pick, never takes at the next pick (0 of 151), and who then
beats his projection by about +160 points. The loss sits in the value base, which is upstream of
survival and opportunity cost.**

**No production change. No weight tuned, no survival model fitted, and no realized outcome used
as a feature. Nothing ships.** `src/alpha_squad/` is byte-identical to HEAD `e02fcf7` (tree
`55e763e8…`).

---

## 1. Plain-English conclusion

D115 defined "pure sequencing" regret (C1 ∧ C2) as picks where the oracle's player O survived to
Alpha's next pick, and where Alpha's own player A would also have survived had Alpha taken O
first. The implied story is: Alpha had the right two players and took them in the wrong order.
D116 tested that story against Alpha's own ex-ante state. The story does not hold.

1. **The survival model knew who would go first.** Under the real opponent field, the lower
   survival probability was removed first on **84 of 96** decisive target pairs and **66 of 71**
   dynasty pairs. It agrees with the market rank the field actually drafts by on 93–95% of pairs.
   On the complementary picks, where exactly one of the two players did not reach Alpha's next
   pick (C1 XOR C2), it is **86% / 96%** right at the decision horizon itself.
2. **What it knew was mostly "take A first".** Under the opponent field, A was removed before O
   on **94 of 124** decisive target pairs (76%) and **67 of 113** in dynasty (59%). Survival
   pointed at O on only **33 of 151** / **38 of 155** picks.
3. **At the next-pick horizon the order did not matter, by construction.** On C1 ∧ C2 both
   players reach Alpha's next pick, so the ideal survival forecast is "both safe". The measured
   next-pick availability gap is **0.000** on every pick. The survival model's mean forecast was
   0.87–0.89, so it was slightly *too pessimistic* here (ECE 0.13 / 0.11). It did not miss a
   threat.
4. **The "wrong order" never gets corrected, because Alpha does not want O.** Alpha took O at its
   next pick on **0 of 151** target picks (1 of 155 in dynasty). At that next pick O's median rank
   on Alpha's own board is **127** (dynasty 146). O ended up with an opponent (71) or was still
   undrafted at Alpha's last pick (78). Going the other way, had Alpha taken O first, the shipped
   engine *would* have taken A at the next pick on **113 of 151** picks. "Both obtainable" is
   true; "the order was the mistake" is not.
5. **Who O is, ex ante:** Alpha's median rank of O *at the pick* is **125**. O's projection is
   **108.6** against A's **188.2**. O's value base is ≤ 0 (at or below replacement) on **82 of
   151** picks. The market ranks O a median **57** picks after the current pick, against 26 for
   A. The market also thought O would last, and it was right. Hindsight only: O then scored
   **+163.5** over projection, while A scored −25.6 under his.
6. **The information is lost before survival or opportunity cost ever act.** In the factored
   score, the additive value term favours A on **100%** of decomposable pairs (mean log ratio
   +0.79, about 2.2×; value-base gap **+129 points**). The survival multiplier can move a score by
   at most log 1.3 = 0.26. Setting survival to neutral would have flipped **0 of 151** picks
   (1 of 155 in dynasty). Setting opportunity cost to neutral would have flipped **0**. The
   *risk* (confidence) multiplier is the second-largest term against O (+0.35 mean log, pointing
   at A on 62 of 69 pairs). It discounts exactly the uncertain players who turn out to be the
   oracle's picks.

**Verdict against the brief's four options: none of A–D describes these picks. The nearest is
A: the survival model is directionally right, with miscalibrated magnitude in its middle range.
It is not D.** The engine does not discard a survival signal that pointed at O, because the signal
mostly pointed at A and was right to. **The answer to the most important question is YES, it
knew. But the information needed to avoid this regret is not availability information, so the
brief's "If YES" branch (look for where the survival signal is lost) finds nothing to recover.**

---

## 2. Primary deliverable — `target_league` (PRIMARY), `dynasty_1qb` (replication)

All accuracies are pairwise "which of A and O disappears first". The truth is **H2**: from the
pre-pick state, the real opponent field drafts on while Alpha passes, so neither player is removed
by Alpha (§4). Accuracy counts only decisive pairs; ties and undefined calls are reported
separately. The 95% intervals are season-clustered t with k = 5 (pooled Wilson in brackets). The
MDE is t_crit × SE.

| Metric | `target_league` | `dynasty_1qb` |
|---|---|---|
| Sequencing-regret picks (C1 ∧ C2) | **151** of 286 non-final picks with O ≠ A | **155** of 298 |
| Share of total regret | **48.1%** (D115 on its vintage: 47.3%) | **46.5%** (D115: 52.2%) |
| Survival ranking accuracy (H2) | **87.5%** (84/96), CI [74, 98]%, MDE ±12.3pp, Wilson [79, 93]% | **93.0%** (66/71), CI [85, 101]%, MDE ±8.0pp, Wilson [85, 97]% |
| Survival multiplier ranking accuracy | 87.5%, identical (no survival value is None in this population) | 93.0%, identical |
| Opportunity-cost ranking accuracy | **14.3%** (2/14), CI [−38, 95]%, which is **unresolved** | **37.5%** (3/8), unresolved |
| Combined-score ranking accuracy | **75.8%** (94/124), CI [57, 91]%. It always says "A first", so this is simply the A-first base rate | **59.3%** (67/113), CI [43, 77]% |
| Replay-implied survival (per player) | undefined: 145/151 tie. The replay says **both survive**, which is exactly the H1 truth | 151/155 tie, same reading |
| Market rank (REFERENCE: the field's own order) | 93.5% (116/124) | 92.0% (104/113) |
| Tie rate: survival / OC / score | **19.2%** / 88.7% / 0% | **41.3%** / 91.6% / 0% |
| H2 truth ties (neither player ever drafted) | 27 / 151 | 42 / 155 |
| Calibration error (H1, this population; truth = 1 for all) | ECE **0.133**, Brier 0.040. Mean S 0.867 vs 1.000 observed | ECE **0.111**, Brier 0.041. Mean S 0.889 vs 1.000 |
| Calibration error (context: Alpha top-30, 8,700 player-states) | ECE 0.058, Brier 0.074 | ECE 0.043, Brier 0.046 |
| Mean predicted survival gap S_O − S_A | **+0.088** (\|gap\| 0.150): O judged safer | **+0.054** (\|gap\| 0.142) |
| Mean actual availability difference, next pick (H1) | **0.000** by construction | **0.000** |
| Mean actual removal gap, opponent picks (H2, O − A) | **+9.4** (median \|gap\| 10): O went later | **+3.3** (median \|gap\| 9) |
| Opportunity-cost gap OC_O − OC_A vs actual positional drop | +0.72 predicted vs +0.79 actual (static VORP). Realized-points drop, HINDSIGHT: −0.09 | +0.46 vs +0.76; HINDSIGHT −0.07 |
| Mean actual regret on the population | **140.2**/pick. Season-clustered 135.3, CI [82.6, 188.0], MDE 52.7 | **126.8**/pick; 126.3, CI [94.2, 158.5], MDE 32.1 |
| Alpha took O at its next pick | **0 / 151** | **1 / 155** |
| Shipped engine takes A next if it had taken O now | **113 / 151** | **110 / 155** |

**Reading the survival row honestly.** 87.5% is high, but the market rank alone gets 93.5% on the
same pairs. That is expected: the backtest's opponent field literally drafts by market rank. This
is the *most favourable possible* environment for an ECR-based survival model. The survival
model's residual error against the field is its Uniform(ecr_best, ecr_worst) shape. It is not an
information deficit.

### 2.1 Where each signal works and fails (H2 accuracy on C1 ∧ C2, `target_league`)

"S→O" counts picks where survival pointed at O. "O next" counts picks where Alpha took O at its
next pick.

| group | n | % of total regret | S acc | S decisive | S→O | OC acc (decisive) | score acc | O first (H2) | O next |
|---|---|---|---|---|---|---|---|---|---|
| **O = RB** | 70 | 22.2% | 84% | 45 | 20 | 33% (3) | 73% | 15 | 0 |
| **O = WR** | 52 | 18.9% | 91% | 32 | 6 | 9% (11) | 80% | 9 | 0 |
| O = TE | 16 | 4.1% | 86% | 14 | 7 | — | 64% | 5 | 0 |
| O = QB | 12 | 2.8% | 100% | 5 | 0 | — | 100% | 0 | 0 |
| O = DST | 1 | 0.1% | — | 0 | 0 | — | 0% | 1 | 0 |
| cross-position | 112 | 35.2% | 83% | 69 | 28 | 14% (14) | 73% | 25 | 0 |
| same-position | 39 | 12.9% | **100%** | 27 | 5 | tie by construction | 83% | 5 | 0 |
| R1–6 | 42 | 16.6% | 92% | 37 | 7 | 100% (2) | 79% | 9 | 0 |
| R7–11 | 55 | 16.9% | 92% | 39 | 18 | 0% (11) | 67% | 18 | 0 |
| **R12–16** | 54 | 14.6% | **70%** | 20 | 8 | 0% (1) | 89% | 3 | 0 |
| 2021 | 37 | 14.5% | 95% | 19 | 5 | 14% (7) | 72% | 8 | 0 |
| 2022 | 22 | 4.7% | 73% | 11 | 3 | 100% (1) | 59% | 7 | 0 |
| 2023 | 31 | 10.4% | 79% | 19 | 6 | 0% (5) | 96% | 1 | 0 |
| 2024 | 32 | 12.8% | 88% | 25 | 11 | — | 73% | 7 | 0 |
| 2025 | 29 | 5.7% | 95% | 22 | 8 | 0% (1) | 71% | 7 | 0 |
| regret T1 (low) | 51 | 8.2% | 86% | 35 | 11 | 0% (2) | 74% | 11 | 0 |
| regret T2 | 50 | 15.1% | 88% | 25 | 8 | 0% (7) | 84% | 6 | 0 |
| **regret T3 (high)** | 50 | 24.8% | 89% | 36 | 14 | 40% (5) | 70% | 13 | 0 |

Per-round tables (1–15; round 16 is always final) are in the runner output and in
`d116_summary.json`. Every round has n ≤ 16, so they are descriptive only. The one sub-50% cell,
round 14 (38%, 8 decisive), sits inside the late phase's known weakness.

**`dynasty_1qb` (replication).** By oracle position, survival is 88–95% everywhere (RB 95%, 39
decisive). By phase it is 92% / 92% / 100%; late-phase dynasty has only 9 decisive pairs. By
season it is 88–100%. By regret tercile it is 96% / 100% / 86%. The combined score is weaker in
dynasty R1–6 (44%), because O goes first there (29 of 52), but survival still gets 92% of those
pairs right. Alpha took O next on 1 of 155.

**Where it works:** same-position pairs (100% / 94%), early and middle rounds, QB and WR, and every
regret tercile including the highest. **Where it fails:** late rounds in target (70%, 20 decisive).
There, survival probabilities collapse to 1.0 for both players (ties), and the few decisive calls
are between deep sleepers whose ECR ranges are wide. Opportunity cost is almost always a tie on
this population (89–92%); where it is decisive it is not usable (14% / 37.5%, intervals spanning
everything). That is expected. OC prices the drop in a position's best VORP *by the next pick*,
and on C1 ∧ C2 nothing relevant drops by the next pick.

**The structure is not averaged away, because there is almost none to average:** the survival
signal is uniformly good. What varies by group is only how often O was the one at risk.

### 2.2 The contrast that shows survival working where it matters: C1 XOR C2

These are picks where exactly one of the two players failed to reach Alpha's next pick
(target: 88 picks, 30.2% of regret; dynasty: 103 picks, 34.6%). Here the next-pick horizon itself
is decisive:

| signal | target (H1) | dynasty (H1) |
|---|---|---|
| survival | **86.2%** (75/87), CI [77, 99]% | **96.1%** (99/103), CI [87, 105]% |
| opportunity cost | 80.6% (29/36) | 88.2% (45/51) |
| replay-implied survival | **100%** (79/79) | **100%** (97/97) |
| combined score | 71.6% (63/88) | 81.6% (84/103) |
| market rank (reference) | 98.9% | 99.0% |

**Production's own opponent replay is a perfect next-pick availability predictor in this
backtest.** It is used only as a positional maximum inside opportunity cost, and its per-player
membership is discarded. That is true, but it matters little: the Uniform-range survival model is
already right 86–96% of the time here. The replay is exact only because the backtest opponents
*are* the replay's model. The 100% is a property of the instrument, not evidence that it would
hold against real drafters.

---

## 3. Where the information is lost

The shipped L0 score factors exactly as
`score = (value_base + OC) × fit × risk × survival_mult × feasibility`. The factorisation is
*checked*, not assumed: every candidate's implied value_base must match the value_base the engine
itself writes into `CandidateScore.reasons` (checked on every candidate at every state; a mismatch
raises). log(score_A / score_O) then splits by term. This is possible where both additive terms
are positive: **69 of 151** target picks and 85 of 155 dynasty picks. On the rest, O's additive
value is ≤ 0, meaning Alpha rates O at or below replacement, which is itself the answer.

| term | points at O | points at A | mean log(A/O) — target | dynasty |
|---|---|---|---|---|
| **additive (value base + OC)** | **0** | **69** | **+0.794** | **+1.275** |
| risk (model confidence) | 6 | 62 | **+0.348** | +0.302 |
| survival multiplier | 22 | 39 | +0.011 | +0.015 |
| roster fit | 18 | 20 | −0.001 | −0.012 |
| feasibility | 0 | 0 | 0 | 0 |

* **Survival → final pick: nothing is lost.** Where survival favoured O (22 decomposable pairs,
  target), its term was −0.043 against a total gap of +1.50. It was outweighed about 35 to 1.
  Setting survival to neutral flips **0** picks (dynasty 1). Only 18.8% (14.1%) of pairs have a
  total gap smaller than the multiplier's *maximum possible* swing, log 1.3.
* **Opportunity cost → final pick: nothing is lost.** The mean OC gap is 0.7 points against a
  129-point value-base gap. Setting it to neutral flips **0** picks in either format. D97's
  "calibrated but understated by 20–65%" reproduces in direction here (predicted +0.72 vs actual
  +0.79 VORP-drop gap). At this magnitude, even a 3× correction could not flip one of these
  picks.
* **Where it IS lost:** the value base (projection-derived) and, second, the confidence
  multiplier. Both are ex-ante statements that O is worth less than A. The market held the same
  view: O's market rank lags A's by 31 picks in target.

---

## 4. Definitions, stated so they can be checked

* **Population:** D115's C1 ∧ C2, read from D115's committed artifacts. It was re-produced on this
  vintage by D115's unmodified runner (`--mode regret`, `--mode timing`). Pairs with O = A carry
  C2 = None and are excluded, as in D115.
* **Ex-ante signals:** read from the shipped engine's `CandidateScore` at the pre-pick state.
  D115's `replay_states` is re-walked, and `_pick_by_tier(SHIPPED_TIER)` is re-asked at each
  state. The runner raises unless it reproduces the replay's pick, and unless the D115 row's
  Alpha pick matches. The one-step counterfactual is checked against D115's C2 on every pick; a
  disagreement raises.
* **H1 (next pick):** S_O = C1, S_A = C2. On C1 ∧ C2 this is a tie for every pick, so the H1
  ranking there is undefined and only H1 calibration is reported.
* **H2 (which disappears first):** from the pre-pick state, Alpha passes on every remaining turn
  and `roster_aware_market_pick` drafts for the same opponent rosters. The pick at which each of
  A and O is removed is recorded; a player never removed is censored at the end of the draft.
  H2 is symmetric in A and O and is never an input to a prediction.
* **Actual positional drop:** the same clamped `max(0, best now) − max(0, best at next turn)`
  form that production prices. It is applied to the real next-pick pool *with A put back*, so the
  drop is the opponents' alone. Units are static VORP, as in D97. A realized-points version is
  labelled HINDSIGHT.

---

## 5. How much of the regret is addressable

Shares of **total** per-format regret (target 44,027; dynasty 42,218):

| | target | dynasty |
|---|---|---|
| **Potentially addressable** (C1 ∧ C2) | **48.1%** | **46.5%** |
| …on picks where **survival pointed at O** | **10.9%** (33 picks) | **9.9%** (38) |
| …where survival pointed at O **and** O really went first (H2) | **7.7%** (22) | **6.9%** (26) |
| …where opportunity cost pointed at O | 4.4% | 2.5% |
| …where the replay pointed at O | 0.2% | 0.3% |
| …where **any** existing availability signal pointed at O | **15.4%** | **11.8%** |
| **Unexplained by any availability signal** | **32.7%** | **34.8%** |

**Even the 7.7% is not "supported" in the sense of recoverable.** On all 22 of those picks
(26 in dynasty), O was still on the board at Alpha's next pick (C1), and Alpha passed on him
again. The survival signal was right, and acting on it would not have been needed. The binding
constraint was valuation at both picks. **On this evidence, the share of D115's sequencing regret
that the existing survival / opportunity-cost system could have addressed is effectively zero.
What remains, about 47% of total regret, is valuation information: Alpha, and the market, did not
rate O.** That matches D115's other finding, that perfect information recovers 73.5% while no
preseason arm recovers anything.

---

## 6. Survival-model calibration (context population)

The context population is every player in Alpha's top 30 at every non-final state, excluding
Alpha's own pick (its H1 truth is counterfactual). Target: 8,700 player-states; dynasty the same.
Brier 0.074 / 0.046, ECE 0.058 / 0.043. The reliability curve is **S-shaped**. Forecasts of
0.15–0.45 are too optimistic (observed 0.00–0.12 target, 0.05–0.22 dynasty). Forecasts of
0.70–0.90 are too pessimistic (observed 0.84–0.96). This is the Uniform(ecr_best, ecr_worst)
shape meeting an opponent field that drafts deterministically by the *mean* rank. It is a
magnitude miscalibration, not a ranking failure, and it is the "A" in the brief's taxonomy. No
player at S = 0 survived (0/63 target; 1/234 dynasty). 94 of 4,509 players at S = 1 were gone.

One small data-contract observation, not acted on. `load_season_static`'s ECR-dispersion query
is scoped to `ecr_type` only, not `page_type`. In the market-rank top 200 this reaches another
page for **1** player (2025 target) and 0 elsewhere; for that player the series rank still falls
inside the range. That is immaterial here, but it is recorded because D56 says `ecr_type` alone
is not a rank space.

---

## 7. What D116 does NOT establish

1. **Real-draft availability.** Every accuracy here is measured against a deterministic
   market-rank opponent field. Against human drafters the survival model and the replay would
   both be less accurate, and the field's own ordering would no longer be a near-perfect oracle.
2. **That the value-base loss is fixable.** D116 locates the loss; it does not show that any
   preseason signal could have rated O higher. D115 already found that no existing arm does.
3. **Vintage transfer.** This run is on board vintage **`f0022601…`**, not D113–D115's
   `0d525430…` (§8). The C1 ∧ C2 share reproduces (48.1% vs 47.3%, target), but dynasty moves
   (46.5% vs 52.2%). Every D116 number is internally consistent on one vintage, and D115's
   published numbers are quoted, never mixed in.
4. **Two 1-QB formats only.** Nothing here is established for `legacy_2qb_dynasty`.

---

## 8. Recommended next research question (exactly one)

> **Does Alpha's existing uncertainty output (M6's p90 / top-24 probability, already on the
> board and already produced ex ante) rank the C1 ∧ C2 oracle players above Alpha's own picks at
> those states? In other words, is the upside information present but discounted by the point
> projection and the confidence (risk) multiplier?**

The reasoning: D116 puts the loss in the value base, and the risk multiplier is the second-largest
term against O (+0.35 log). O is systematically the *uncertain, lower-projected* player who
breaks out (+163 over projection). If the interval model already sees that upside, the problem is
how the score *uses* uncertainty, which is attribution-testable with no new model. If it does
not, the loss is in the projection itself, and D115's "information, not rule" finding is
confirmed from a second direction. The survival model should not be the next target: it already
ranks availability correctly, and improving it cannot reach this regret.

---

## 9. Reproducibility, provenance and what changed

```bash
make ingest identity college-usage features team-scores market train   # from-source rebuild
uv run python scripts/research/d115_regret_attribution.py --mode regret --leagues target_league --out <t>
uv run python scripts/research/d115_regret_attribution.py --mode timing --leagues target_league --out <t>
uv run python scripts/research/d115_regret_attribution.py --mode regret --leagues dynasty_1qb   --out <d>
uv run python scripts/research/d115_regret_attribution.py --mode timing --leagues dynasty_1qb   --out <d>
uv run python scripts/research/d116_survival_attribution.py --mode measure --in <t> --in <d> --out <o>
uv run python scripts/research/d116_survival_attribution.py --mode report  --out <o>
uv run pytest tests/unit/test_d116_survival_attribution.py
```

Runtime: D115 regret about 23 minutes per format (both formats in parallel); D116 measure about 1
minute.

| item | value |
|---|---|
| HEAD at run time | `e02fcf751e61d77ee227c6c1f2bb5b2809819493` (D115 merge) |
| `src/alpha_squad` tree at HEAD / working copy dirty | `55e763e8a80af908a2c2bcc0ae66753c16b629fc` / **False** |
| board vintage, combined 2021–2025 | **`f00226015095534f22e1311c8fa1b4823d66e0679ef6fa8f1817500209dce89f`** |
| per season | 2021 `79599ffa…` 2022 `43f0e968…` 2023 `aa73cd3f…` 2024 `7873284c…` 2025 `0b344c7e…` |
| matches D113–D115's `0d525430…` | **NO**: projection layer moved. The upstream board and id map are identical |
| upstream board / idmap sha256 | `e270d790165a6c30…` / `36016b9239e3e7da…` (**same as D115**) |
| retraining determinism | `make train` re-run in-container reproduces `f0022601…` exactly |
| uncertainty model / tier / objective / opponent | `uncertainty_catboost_v2` / `L0` / `season_long` / `market_consensus_roster_aware` |
| catboost / numpy / pandas | 1.2.10 / 2.5.2 / 3.0.5 |
| D115 artifacts, sha256 (target regret / timing) | `6d395458…` / `a8b44df6…` |
| D115 artifacts, sha256 (dynasty regret / timing) | `ee4921c5…` / `72308875…` |
| D116 artifacts, sha256 (pairs / summary) | `56dbb142…` / `e287f477…` |
| grid | 2 formats × 5 seasons × 4 slots × 16 rounds = 640 audited picks. 584 non-final pairs with O ≠ A |

**Why the vintage moved.** The same inputs D115 recorded (upstream ECR board and id map) hash
identically. Retraining in this container is bit-deterministic. So the difference is upstream
nflverse content or environment between sessions. The board D115 measured cannot be
reconstructed here without inventing it, so D116 re-ran D115's own instrument on this vintage
instead of mixing the two.

**Files changed by D116 — research only:**

| file | status |
|---|---|
| `scripts/research/d116_survival_attribution.py` | **new**: measure / report runner |
| `tests/unit/test_d116_survival_attribution.py` | **new**: 43 tests |
| `docs/D116_SURVIVAL_ATTRIBUTION.md` | **new**: this report |
| `docs/DECISIONS.md`, `docs/PROJECT_STATE.md` | appended |
| `src/alpha_squad/**` | **unchanged** |
