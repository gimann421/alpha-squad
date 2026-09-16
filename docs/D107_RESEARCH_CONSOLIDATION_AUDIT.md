# D107 — Final Research Consolidation Audit (D86–D106)

*Audit only. No production logic changed, no model changed, nothing in `league/` changed, nothing
fitted, no new sensitivity or projection experiment, no 2026, no new ranking source, no Y1 tuning,
no PR, nothing merged.* The only commands run against the repository were read-only: the test
suite, `ruff`, `git`, a read-only `compute_board_vintage`, a read-only re-aggregation of the
D100–D106 result artifacts, and the **existing** `d103_pick_regret.py --mode parity` check (§5
check 8), which opens the database read-only and writes only to a scratch directory.

Board vintage verified live at
`ca3e2d8af6aa892067c7450095a1c992087f613141e3b36b89b12928713d5f99`.

**Index against the twelve required report items:** 1 executive conclusion → §1 · 2 phase ledger →
§3 · 3 claim ledger → §3b · 4 north-star evidence audit → §4 · 5 instrument/data-contract audit →
§5 · 6 D103–D106 conclusion audit → §6 · 7 production-vs-research audit → §8 · 8 merge-stack
inventory → §9 · 9 canonical state of the draft problem → §10 · 10 recommended disposition → §11 ·
11 what would justify reopening → §12 · 12 repository status → §13. §2 carries the corrections this
audit makes and §7 the ECR-interpretation audit; the appendix lists exactly what was re-derived and
from which artifact.

---

## 1. Executive conclusion

**The D86–D106 program is internally consistent enough to consolidate, and two statements in the
written record are too strong and are corrected here.** Neither correction changes a verdict.

Everything I could re-derive from the retained result artifacts reproduced **exactly** — D100's
identification table, D101's four arms and both G6 readings, D103's regret-by-phase and
ORACLE_Y1 cells, D104's decomposition and regret arm, D105's ladder (value, divergence, validity,
regret), and D106's weekly ladder, including the seed-to-seed SD statistic each phase quoted. The
production trees are byte-identical to `origin/main` (`models/` `73b408e9`, `league/`
`d4cfd00e`). 1427 tests pass, 44 deselected, `ruff` clean; the working tree was clean at the start
of this audit and carries only this report and its two log entries at the end of it.

**What the program actually established, stated at the strength the evidence supports:**

1. **A pick-level measurement exists and is now pinned.** `draft_oracle.audit_draft` measures
   `regret(p) = max_c V(c) − V(alpha's pick)` at real pick states with a structurally enforced
   information boundary, and the rollout policy is now *tested* to be production rather than
   asserted to be.
2. **Perfect information, with the decision rule held at Y1, is worth +795.3 (target) / +717.0
   (dynasty) realized starter points, 5/5 seasons in both formats.** That is a ceiling requiring
   hindsight, not a target.
3. **The best real preseason ranking available in this repository recovers ≤10% of that in one
   format and is negative in the other** (+77.3 / −132.1 season-long; +48.4 / −202.4 weekly), and
   both are below the instrument's 172–250 point detection floor.
4. **The value surface is a plateau in ranking quality, under both objectives, and it is
   bounded.** Changing 88% of picks costs ~30–85 points (unresolvable); destroying the ordering
   entirely costs 566–721 points (5/5 seasons, CI excluding zero). The environment is
   *thresholded*, not indifferent.
5. **No decision-rule change has ever been shown to help.** Y1's *entire* scoring apparatus is
   worth +213.8 against an MDE of 179.4; the pick-level decision-shaped residual is ~86–113
   points per draft against a floor of 172–250.

**What the program did NOT establish, and must not be read as:**

- Not "the draft is solved." Regret at each pick is large in absolute terms (134.8 season-long,
  107.4 weekly) and, normalised by the dispersion actually available on the slate, Y1 captures a
  **smaller** share of the available value late than early (§4.B / §6.2) — the opposite of the
  impression the absolute table leaves.
- Not "Y1 is optimal." Nothing here compares Y1 to an optimum. It compares Y1 to degraded copies
  of itself, to one alternative ranking, and to a hindsight ceiling.
- Not "there is no possible improvement." Every candidate ever proposed has a plausible effect
  inside the 25-to-250-point band this instrument cannot resolve. That band is *invisible*, not
  *empty*.
- Not "projections don't matter." Destroying the projection ordering costs 566–721 points. The
  ladder tests **degradation only**, holds each position's **value multiset fixed**, and was run
  against **one** real alternative source. The improvement direction, a second source, and any
  change to projection *magnitudes* rather than order are all untested.

**Disposition: A — consolidate and close the draft-investigation branch, preserving Y1 as the
production baseline** (§11), on the pre-registered stopping rule rather than on a demonstrated
absence of effect. The reopening conditions are specific and are stated in §12.

---

## 2. Corrections this audit makes to the written record

Both were found by re-aggregating the phases' own retained artifacts. Neither changes a verdict.
Per the phase brief they are **reported, not silently repaired**.

### C1 — D103's "0% of rounds 1–5 in both formats" is false for `dynasty_1qb`

`docs/D103_PICK_LEVEL_OBJECTIVE.md` §C and the `DECISIONS.md` D103 §3 entry state that Alpha's
pick equals the oracle's in **0% of rounds 1–5 in both formats**, and that "the only rounds with
any hits at all are 6–8 and 11".

Re-derived from `d103_regret_season_long_weekly_no_foresight.json` (the artifact the report was
written from):

| format / objective | rounds 1–5 agreement | per-round hits |
|---|---|---|
| target / season_long | **0.0%** ✓ | — |
| target / weekly | **0.0%** ✓ | — |
| dynasty / season_long | **5.0%** ✗ | rd 1 5%, rd 2 15%, rd 4 5%, rd 7 5% |
| dynasty / weekly | **9.0%** ✗ | rounds 2–5 |

The claim is true for `target_league` only. The overall agreement range quoted as "2.2–4.7%"
should read **1.9–4.7%** (dynasty season-long is 1.9%). **The headline — regret is concentrated
early in absolute points — is unaffected**; the early-vs-late figures (181.5 vs 107.4 target,
181.1 vs 107.0 dynasty) reproduce exactly.

### C2 — D104's "first divergence: round 1, in 20/20 drafts" overstates

`docs/D104_ECR_FLOOR.md` §5 and `DECISIONS.md` D104 §4 record the ECR arm's first divergence from
Y1 as "round 1, in 20/20 drafts" in both formats. Re-derived from `d104_divergence.json`:

| format | first-divergence round histogram | round 1 | ≤ round 2 | ≤ round 5 |
|---|---|---|---|---|
| target_league | {1: 11, 2: 5, 3: 3, 5: 1} | **11/20** | 16/20 | **20/20** |
| dynasty_1qb | {1: 11, 2: 5, 3: 1, 4: 2, 5: 1} | **11/20** | 16/20 | **20/20** |

The correct statement is: **every one of the 20 drafts diverges, and every one within the first
five rounds; the first divergence is round 1 in 11 of 20.** The substantive point — ECR changes
picks from the very top of the draft, in every draft, and realized value still barely moves —
survives intact. The picks-changed figures (183/320 = 57.2% target, 206/320 = 64.4% dynasty) and
the phase splits reproduce exactly.

### Not a correction, but a reframing the record should carry

See §4.B and §6.2: **absolute regret is concentrated early; regret as a share of the dispersion
available at the pick is concentrated LATE.** This is derivable from the existing D103 artifact
(which already stores `spread` per pick) with no new run, and it materially changes how "regret
is concentrated EARLY" should be read.

---

## 3. D86–D106 phase ledger

Columns: **Prod** = production code (`league/`, `models/`) changed; **Res** = research /
instrumentation code changed; **2020** = depends on the contaminated 2020 board; **NS** =
relevance to the north-star ("at every individual draft pick, select the best available option
given the current roster and remaining player pool").

---

### D86 — What should Alpha optimize at all?

- **Experiment.** (a) Scored Alpha's own drafted rosters under season-long vs weekly no-foresight;
  (b) measured draftable-player availability 2021–2025; (c) built the **pick-level oracle** over
  320 real pick states; (d) ran candidate O1 (`E[weekly msv] + 1.0·daVORP`) at 5 seasons × 4 slots
  × 2 formats.
- **Prod** NO (`league/`, `models/` byte-identical). **Res** YES — added `evaluation/draft_oracle.py`,
  `evaluation/weekly_objective.py`, `evaluation/objective_candidates.py`, O-tier wiring, 46 tests.
- **Result.** The incumbent objective prices the bench at exactly zero, while **17.8% of realized
  points (358.5)** arrive through the bench and a bench player starts in **16.2 of 17 weeks**.
  Oracle: Alpha regret **116.2**, a random pick from the same slate 122.3, best-by-projection
  144.6 — Alpha captures **~5%** of the random-to-perfect gap, and `Spearman(engine score, final
  roster value) = −0.033`. The **structural** residual (oracle's player scored no more and still
  won) is **16/320 = 5%, ≈90 points per draft**, against a ~128-point MDE. O1: target +52.9
  CI [−8.3, +114.0]; legacy +1.6.
- **Verdict.** DO NOT SHIP.
- **Still valid?** The *instrument concepts* and the *structural residual* are valid — the residual
  was independently replicated at ~91 pts/draft on a different slot set in D103. **The O1 draft
  numbers are NOT reproducible** (D92 §5: the runner was never committed).
- **Superseded.** O1's headline superseded by D93's restatement in D96 §3 (+7.0 target / +30.7
  dynasty on 2021–2025, both CIs spanning zero).
- **Retractions.** None of its own.
- **2020** NO (ran 2021–2025). **NS** HIGH — it created the pick-level metric.
- **Canonical:** the oracle/regret definition; bench share 17.8%; structural residual ~90/draft;
  `Spearman(score, roster value) = −0.033`; replacement-level validation; and **"there is no
  transaction history in this database."** NOT canonical: any O1 effect size.

### D87 — Is a candidate shortlist a free speed-up?

- **Experiment.** O1 with top-K shortlists (K=10, 40) vs O1-FULL over 592 real pick states.
- **Prod** NO. **Res** YES (research-only `shortlist_k` parameter, 5 tests).
- **Result.** K=10 changes 10.3% of target decisions — **0/140 in rounds 1–7, 33/180 (18.3%) in
  rounds 8–16**, i.e. unfaithful exactly where O1's mechanism operates. All 33 substitute K/DST for
  skill players, because **the shortlist is ranked by Y1**, the engine whose K/DST over-valuation
  O1 exists to correct. Margins are non-monotonic in K (+62.3 / +41.9 / +52.9).
- **Verdict.** DO NOT SHIP. **2020** NO. **NS** LOW (methodology).
- **Canonical:** the *lesson* — a shortlist must be validated against the full board for the
  **behaviour** under test, not merely the selected player, and must not be ranked by the engine
  whose pathology the expensive objective corrects. Effect sizes: not canonical (D92).

### D88 — Does O1 replicate, and can slots resolve it?

- **Experiment.** Same arm, 4 → 10 slots, full board.
- **Prod** NO. **Res** YES. **Result.** Target +50.5 CI [−5.5, +106.6], 4/5 seasons improved;
  legacy −2.3. **The decisive finding: the MDE floors at ~56 no matter how many slots are added,
  against an effect of ~50.5. The binding constraint is SEASONS, not slots.**
- **Verdict.** B — promising but unresolved. **2020** NO. **NS** MEDIUM.
- **Self-corrected.** D89 §6 found D88's slot-sensitivity arithmetic wrong (it added
  within-variance to an SD that already contained it); the true 5-season infinite-slot floor is
  **51.1**, not 56.0. D88's conclusion is unaffected and slightly strengthened.
- **Canonical:** **the structural conclusion — seasons bind, slots cannot help.** It has governed
  every power statement since and is the root of D97's 172–250 floor. Effect sizes: not canonical.

### D89 — Do six seasons resolve O1?

- **Experiment.** Add 2020 → 6 seasons × 10 slots, pre-registered.
- **Prod** NO. **Res** YES (`EXCLUDED_SEASONS` keyed by `(format, season)`, `EmptyMarketBoardError`).
- **Result.** Target **+49.0 CI [+6.5, +91.5]**, 9/9 in-format gates pass, **G7 fails** (sign
  differs from legacy). Two data defects found: target 2020's board is `redraft-offense` not
  `redraft-overall` (the default returned an **empty** board and the fair opponents would have
  drafted **alphabetically**); legacy 2020 has no preseason board at all.
- **Verdict.** B. **2020** **YES — and this is the phase that introduced the contamination.**
- **Still valid?** **NO on two independent counts:** every 2020 cell is against a different market
  series (D95/D96), and the numbers are not reproducible (D92 §5).
- **Canonical:** the `EmptyMarketBoardError` guard; the FLEX exact-tie characterization tests; the
  correction to D88's arithmetic. NOT canonical: **+49.0**, which six phases went on to cite.

### D90 — Does the mechanism generalise to a third format?

- **Experiment.** O1 unchanged on `dynasty_1qb` (the only other series with K/DST rows), 120 drafts.
- **Prod** NO. **Res** YES. **Result.** Mechanism reproduces (kickers 2.40 → 2.00, 0 capacity
  breaches vs Y1's 24); magnitude does not (+20.8 CI [−30.8, +72.3], below the 25.0 economic
  threshold, MDE 51.5). **Both superflex boards carry zero kickers and zero defenses** — so legacy
  was never a weak test of O1's mechanism, it was not a test at all.
- **Verdict.** B. **2020** YES (6-season window). **NS** MEDIUM.
- **Canonical:** the board-composition table (`rsf`/`dsf` have 0 K and 0 DST rows) — a data fact,
  still true, and the reason `legacy_2qb_dynasty` cannot exercise any K/DST mechanism. It also
  correctly *declined* to claim its post-hoc monotone trend, and D91 showed that caution was right
  (ρ +0.994 → −0.397 on a re-derivation).

### D91 — Where does O1's advantage come from?

- **Experiment.** Track A exact arithmetic on committed aggregates; Track B rebuild + ablations
  A1/A2/A3 (input overrides only).
- **Prod** NO (`src/` byte-identical to `origin/main`). **Res** one read-only diagnostic script.
- **Headline RETRACTED by D92.** "The +49 does not survive a market-board refresh" rested on a
  counting error: D89 counted market-ranked players *inside the projected board*; D91 counted every
  `market_rank` entry. There was only ever **one board**.
- **What survives, and is canonical:**
  - **Y1's marginal-value degeneracy.** On a roster with all ten starting slots full, Y1's entire
    spread across six #20-at-position bench candidates is **0.48 points** (RB 0.00, WR 0.48, TE/QB/K/DST
    0.00) against O1's 6.13–105.10. Rounds 11–16 carry no marginal-lineup signal and fall through
    to `daVORP`.
  - **Ablation P1 holds exactly**: A2 (rates ≡ 1.0) reproduces O0 on all 60 rosters, max |Δ| = 0.0.
  - **Availability data is nearly inert**; what carries O1's behaviour is `1 − rate^slots` with a
    common rate, i.e. **startable-slot count** — a property of the lineup, needing no injury data.
  - **The RB question closed by algebra.** At an empty roster O1's term reduces to
    `rate(position) × projection`, a positive per-position rescale of Y1's — and a positive rescale
    cannot reorder a board. O1 was never *capable* of changing pick #1 at any projection error.
  - **The brief's seven-category additive accounting cannot be produced**, with the reason for each
    category.
  - **P3 was not tested — a registered design error, recorded rather than reinterpreted.**
- **NOT canonical:** the vintage story, the "between-board natural experiment" (r = +0.601), D91 §9
  and §12. **2020** YES for Track B's grid. **NS** HIGH for the degeneracy finding.

### D92 — Is the historical board mutable, and is the instrument trustworthy?

- **Experiment.** Materialised four real upstream vintages (2026-07-03/08-28/09-04/09-11) and
  hashed the `(player, position, rank)` map the draft consumes; `PYTHONHASHSEED` sweep; full
  retrain reproduction.
- **Prod** NO. **Res** YES — added `evaluation/board_vintage.py` and `scripts/d92_paired_grid.py`,
  20 tests.
- **Result.** **17/17 historical board-seasons IDENTICAL across all four vintages**, with a positive
  control (the live 2026 season *does* move: 95 players added, 478 of 482 common ranks changed).
  Determinism holds across seeds; retraining reproduces the board bit-identically in all seven
  seasons. **The real irreproducibility is that D88/D89/D90 each ran their grid from a script that
  was never committed** — identical inputs, deterministic transformation, different outputs.
- **Consequence, and it is the most consequential sentence in the program:** **D86–D90's published
  draft-layer numbers, the +49.0 included, are not reproducible and must not be quoted as
  measurements of this system.**
- **Verdict.** E — fix the instrumentation, leave production alone.
- **2020** N/A. **NS** HIGH (it is why any later number can be believed).
- **Canonical:** all of it.

### D93 — the O-tier dispatch defect *(no standalone decision record)*

- **Experiment.** Corrected grid after finding that `_pick_by_tier`'s draft-aware replacement chain
  **omitted `O_TIERS`**, so the control silently reverted to the D65-era static replacement level
  while claiming to be the shipped engine.
- **Prod** NO. **Res** YES (12 lines in `evaluation/`, merged in D96 §5 with a guard asserting every
  tier in `DRAFT_AWARE_REPLACEMENT_TIERS` receives a draft-aware level).
- **Result, restated on the legal window in D96 §3** (this is the authoritative form):
  target **+7.0** CI [−54.1, +68.2], MDE 61.2, 3/5 seasons worse; dynasty **+30.7** CI [−13.9,
  +75.2], MDE 44.6. Both CIs span zero; dynasty's +30.7 is above the 25.0 economic threshold but
  **below its own MDE**, which is "formally unresolvable", not "an effect exists".
- **Superseded.** D93's own six-season headline (+3.8 / +27.1) is superseded by the restatement.
- **2020** YES for the original; **NO** for the restatement. **NS** MEDIUM.
- **Documentation gap, flagged:** D93 and D94 have **no `## D93` / `## D94` entries in
  `DECISIONS.md`** — both are recorded only inside D95's context note and D96 §3/§5/§8. The
  substance is preserved; the append-only log's numbering is not contiguous. Worth noting before
  the record is called canonical.

### D94 — production parity and the tie-break claim

- **Prod** NO. **Res** an ablation replica.
- **Result, and its RETRACTION (D96 §8).** D94 reported exact-tie non-determinism in production.
  **Retracted:** `league/draft.py:427` sorts `(-c.score, c.player_id)` and the forensics replicas do
  the same; D54 already fixed and pinned this. The non-determinism was in **D94's own ablation
  replica**, which used a bare `max()`.
- **Canonical:** the retraction, and the cross-format parity gap it left open (closed in D96 §4).
- **2020** partly. **NS** LOW→MEDIUM (it is an instrument-trust item).

### D95 — the empty preseason market board

- **Experiment.** Traced the upstream `fp_page` labels; measured that **no shipped series has a
  preseason (Jul/Aug) board before 2021**, for all four series at once.
- **Prod** **YES — `market/series.py` (`first_preseason_season`, `covers`) and `market/edge.py`
  (`MissingMarketBoardError`).** Merged (PR #20).
- **Why it mattered.** With `market_rank` empty, `best_by_market_rank` scores every player
  `float("inf")` and falls through to its `player_id` tie-break: **"best available by consensus"
  silently becomes "first alphabetically"**, and every downstream number stays finite and looks
  successful.
- **Verified no-op for valid input:** 64 real `recommend_draft_pick` calls across 2024 and live
  2026 produce byte-identical output to 9 decimals. Option C (falling back to the pre-rename label)
  was deliberately rejected as a D56 series-definition change.
- **Verdict.** SHIP the contract. **2020** it is *about* 2020. **NS** HIGH (data contract).
- **Canonical:** all of it.

### D96 — instrument cleanup

- **Prod** NO (the changes are in `evaluation/`, `market/` having landed in D95). Merged (PR #21).
- **Result.** `BACKTEST_SEASONS` narrowed to **2021–2025**, asserted as a *property* over
  `ALL_SERIES` rather than as a literal; the `d92_paired_grid.py` bypass closed (it named a
  page_type explicitly, **which is exactly how every 2020 cell in D89–D93 came to exist**); D93
  restated; D93's dispatch repair merged; **D94's tie claim retracted**; the D56 feature-path issue
  recorded as open.
- **Honest direction of the correction, quoted because it is easy to invert:** dropping the
  contaminated cluster **cost power rather than buying confidence** (MDE 47.0 → 61.2 target,
  34.9 → 44.6 dynasty).
- **Cross-format production parity re-verified through tier `H`** (`recommend_draft_pick` itself):
  both formats 50/50.
- **Canonical:** all of it. **NS** HIGH.

### D97 — where is the draft engine leaving value?

- **Experiment.** Three arms on the identical draft differing only in the ranking key: `NAIVE`
  (classic VBD), `PROD` (Y1), `ORACLE` (realized points over realized replacement, NAIVE's rule).
- **Prod** NO. **Res** NO new experiment beyond the decomposition.
- **Result.** `PROD − NAIVE` **+213.8** CI [+34.4, +393.2] target, +35.7 CI [−174.3, +245.8]
  dynasty. `ORACLE − PROD` +784.6 / +704.6. Per-position bias of the projected top 6: **QB +65.2
  (5/5 seasons), WR +35.3, TE +35.2 (5/5), K +24.1 (5/5), RB +13.1, DST +4.5** — and that ranking
  *predicts the oracle's reallocation exactly*. Top-6 identification runs **23–40%** at every
  position; QB/TE/K capture **none** of the available surplus. **MDE 172–250 points and cannot be
  lowered** (5 season clusters hard-capped by the board contract; 10 slots by the league; seeds
  contribute zero).
- **Verdict.** Close the decision-layer investigation. **2020** NO. **NS** HIGH.
- **Later corrected (D102 §5, D103 §6).** `ORACLE − PROD` is **not** a clean projection-headroom
  quantity: `ORACLE` has perfect information *and* the NAIVE rule. The identified version is
  `ORACLE_Y1 − PROD` = **+795.3 / +717.0**, and the implied rule effect under certainty is ~−11/−12
  — so D97's reading was close to right, but **it was not identified when it was made**, and four
  phases proceeded on it.
- **Canonical:** the **172–250 floor**; the per-position bias table; the component-influence table;
  the opportunity-cost calibration (corr 0.73–0.88, magnitude understated 20–65%, moves 9% of
  picks); and the decisive framing that **Y1's entire decision apparatus is barely above its own
  MDE**. NOT canonical as stated: `ORACLE − PROD` as "projection headroom".

### D98 — is the D56 concern live in the projection feature path?

- **Experiment.** Traced `market_snapshot` → `season_level.py` subquery → `preseason_ecr_rank` →
  M6 → the drafted board; measured IDP contamination directly.
- **Prod** NO, deliberately. **Result. FALSE ALARM.** IDP share **0.0% in every season**; across
  2021–2026 exactly two players ever hold same-date rows on both pages and neither ever wins the
  tie-break. Corrected vs production feature: **0 differing values in any season, including live
  2026**, max |Δrank| 0.00. **The naive `page_type = 'redraft-overall'` fix would be a regression** —
  it destroys 2020's feature entirely (366 values → 0).
- **Verdict.** Close it; do not "fix" it. **2020** it protects 2020's training rows. **NS** LOW→MEDIUM.
- **Canonical:** the measurement, the refusal, and the two recorded latent fragilities (correctness
  is contingent on IDP-page players lacking offensive stat lines; `ORDER BY scrape_date DESC` has
  no deterministic tie-break — the D54 class, currently inert).

### D99 — can per-position calibration improve top-6 identification?

- **Experiment.** Re-ran `evaluation/projection_calibration.py`'s pre-registered arms X0–X4 (committed
  in **D68**, before any arm was fitted) with identification measured.
- **Prod** NO. **Result — structural, not statistical.** X1/X2/X4 apply a per-position map that is
  **monotone increasing in the projection**, and a monotone map cannot reorder within a position,
  so top-6-by-position is invariant: **X1 0/30, X2 0/30, X4 0/30 cells changed; X3 1/30.** Cross-
  position allocation *is* movable (X2/X3 push the first QB from overall rank 5.0 to 10.3/11.0
  against the oracle's 10.0) — reported honestly, but both arms were already rejected by D68's
  gates, and only **3 of 5 seasons are treatable**, giving MDE 343–360, larger than Y1's entire
  decision apparatus.
- **Verdict.** REJECT. **2020** NO. **NS** MEDIUM.
- **Canonical:** **the algebraic argument.** D97's identification failure is a *within-position
  ranking* failure; these calibrations rescale a position without reordering it. No amount of data
  changes that. Also canonical: K **cannot** be calibrated with existing infrastructure (D57
  excludes K/DST from all arms), so D97's "start with QB/TE/K" was only ever answerable for QB/TE.

### D100 — do M6's four features already separate the realized top 6?

- **Experiment.** Re-scored M6's own prediction set against feature-only rankings and a retrained
  negative control. No retraining of M6, no new feature, no draft run.
- **Prod** NO. **Res** YES (`scripts/research/d100_feature_signal.py` + 10 tests).
- **Result (re-verified exactly from `d100_rows.json` in this audit):**

  | method | top-6 overlap (of 6) | AUC | Spearman |
  |---|---|---|---|
  | M6 (incumbent) | **1.950** | 0.8990 | 0.7670 |
  | `U_ecr` (ECR rank raw, no fitting) | **2.750** | **0.9253** | **0.7895** |
  | `U_wtotal` | 2.600 | 0.8909 | 0.7344 |
  | `U_ppg` | 2.400 | 0.8850 | 0.6896 |
  | `U_games` | **0.900** | 0.7301 | 0.5591 |

  11W/8T/1L across 20 position-seasons; per-position WR +1.60 (4W/1T/0L), RB +0.80 (4W/1T/0L),
  TE +0.60, **QB +0.20 (1W/3T/1L)**. Negative control `D_gbm` null. Ceiling decomposition: 1.95
  found, **+0.80 extractable but not extracted (13%)**, +2.70 not in the features (45%), **+0.55
  structurally unreachable (9%)**. `prior_games` is anti-signal — **0.00 at RB in every one of the
  five seasons**. `corr(prior_ppg × prior_games, prior_weighted_total) = 0.972`.
- **Power, stated by the phase itself:** 14 methods compared, **no single comparison survives
  Bonferroni** (needs t ≈ 5.6; `U_ecr` has 3.00). 2023 is null at every position; dropping 2021
  cuts Δ from +3.20 to +2.50.
- **Verdict.** B — promising but unresolved. **2020** NO. **NS** LOW *as established later* — see
  D104.
- **Canonical:** the identification table **as a diagnostic only**; the closure of D69's
  availability/durability thread; the fact that **M6 has no K or DST model**, so D97's K
  identification failure is outside M6's scope entirely.

### D101 — re-run D78's Y0–Y3 with identification added

- **Prod** NO. **Res** YES (`d101_y_arm_identification.py` + 10 tests).
- **Result (re-verified exactly from `d101_rows.json`).** **D78's recorded "Y3 passes all seven
  gates" does not reproduce: Y3 FAILS G6 at WR.** Code drift ruled out (D79's commit is a
  default-preserving refactor); nondeterminism ruled out (three fits identical to nine decimals);
  data/library drift is the remaining explanation and the pre-D78 database is unrecoverable (D91).

  | arm | MAE | top6_hit_rate | AUC | Spearman | verdict now |
  |---|---|---|---|---|---|
  | Y0 | 41.983 | 0.3438 | 0.8912 | 0.7659 | control |
  | **Y1** | 40.638 | **0.3750** | 0.9029 | 0.7773 | **passes all seven** |
  | Y2 | 40.694 | 0.3229 | 0.8929 | 0.7721 | fails G6 (RB) |
  | Y3 | **39.411** | 0.3646 | **0.9053** | **0.7823** | **fails G6 (WR)** |

  Y3−Y1 = **−0.0104** (5W/6T/5L cells). **AUC/Spearman and hit rate disagree about Y3 vs Y1**, so
  G4's Spearman gate cannot be treated as a proxy for identification. G6's prose (`mean(|x|)`) and
  its code (`|mean(x)|`) are different statistics; I re-derived both readings and Y3 fails WR under
  each (24.644 vs Y0's 21.424, and 30.687 vs 29.407), so the ambiguity does not change the answer.
  Y2 falls back to its control in **all four cells of 2022**.
- **A harness defect found and fixed inside the phase:** season win/loss counts used a bare `> 0`,
  and 2024's cancelling cells average to `6.94e-18` — counted as a win. Fixed with an explicit
  tolerance plus a regression test carrying the real counts.
- **Verdict.** DO NOT SHIP; the D78 selection rule re-applied re-selects **Y1, already live**.
- **2020** NO (registered window 2022–2025). **NS** LOW→MEDIUM.
- **Canonical:** **"any future citation of 'Y3 passes all seven gates' must be re-derived, not
  quoted"**; the G6 prose/code discrepancy; the AUC-vs-hit-rate non-monotonicity.

### D102 — define the pick-level objective *(definition phase)*

- **Prod** NO. **Res** NO code at all. **Result.** The counterfactual best-pick metric **already
  existed** (D86's `draft_oracle.py`) with a correct, structurally pinned information boundary; its
  defect was the roster-value function. `test_l0_is_the_shipped_engine` compares L0 only to its
  sibling replicas — **the production-parity guarantee was asserted, not tested** — though L0 vs H
  agreed 240/240 on real pick states when checked. `ORACLE − PROD` identified as confounded, with
  `ORACLE_Y1` named as the missing 2×2 cell. Established the hierarchy: pick regret primary, roster
  value as validation, information quality demoted and conditional, **MAE/RMSE/Spearman/AUC/top-6
  all DIAGNOSTIC**.
- **TWO of its own claims were refuted by D103's data**, and both are recorded as refutations:
  (a) "season-long scoring makes late-pick regret near-degenerate by construction" — **wrong**
  (late regret is 107.4, 59% of the early figure; what season-long cannot see is *insurance* value,
  not late-pick value); (b) the expectation of a large negative Y1-hedging interaction under
  certainty — **wrong** (~−11 points, indistinguishable from zero).
- **Verdict.** Definition only; nothing ships. **2020** NO. **NS** HIGH.
- **Canonical:** the hierarchy, the `ORACLE_Y1` design, and the §7 challenge to D97–D101
  (**"D98–D101 never measured a draft pick"**; "resolvable was conflated with achievable").

### D103 — pick-level regret, phase-specific, with ORACLE_Y1

- **Prod** NO. **Res** YES — `evaluation/draft_oracle.py` (**the only `src/` file changed anywhere
  in the D98–D106 stack**), `scripts/research/d103_pick_regret.py`, and the
  `TestShippedTierIsProduction` / `TestObjectiveSelection` suites.
- **Result (all re-verified exactly from the artifact in this audit).**

  | format / objective | all | EARLY 1–5 | MIDDLE 6–10 | LATE 11–16 |
  |---|---|---|---|---|
  | target / season_long | **134.8** | **181.5** | 121.0 | 107.4 |
  | target / weekly | **107.4** | **162.5** | 89.1 | 76.7 |
  | dynasty / season_long | **141.8** | **181.1** | 144.2 | 107.0 |
  | dynasty / weekly | **103.1** | **147.6** | 98.1 | 70.2 |

  Worst round is **round 2 (198.3)**. WEEKLY − SEASONLONG: target **−27.4** CI [−53.8, −1.0], late
  −30.6 CI [−59.9, −1.3]; dynasty **−38.7** CI [−59.9, −17.5], late −36.8 CI [−62.9, −10.7].
  Attribution: **92–96%** of divergences are the oracle's player simply scoring more; the
  structural residual is **0.70 picks × 129.6 ≈ 91 pts/draft**, an independent replication of D86's
  ~90 on a different slot set. ORACLE_Y1: target 1983.6 → 2778.9 = **+795.3** CI [+579.1, +1011.4],
  **5/5**; dynasty 2094.9 → 2811.9 = **+717.0** CI [+432.8, +1001.3], **5/5**.
- **Verdict.** D — NOT CONFIRMED. The measurement is established; no decision-rule opportunity is.
- **2020** NO. **NS** HIGHEST — this is the north-star instrument.
- **Corrections this audit makes:** §2 C1. Also see §4.B for the normalised reading.
- **Canonical:** all of it, with C1 applied.

### D104 — the best available preseason ranking floor

- **Prod** NO — **no `src/` file changed at all.** **Res** YES (`d104_ecr_floor.py` + 14 tests).
- **Phase 0 rejected the repository's own ECR→value transform before any result**, on three
  measured grounds: `ecr_implied_baseline`'s isotonic step function leaves the 2023 RB top-24 with
  **4 distinct values (largest tie group 12)**, so the engine would pick **alphabetically** exactly
  in the rounds where regret is concentrated; it **hardcodes `ecr_type='ro'`**, a D56 violation that
  would feed the dynasty format the redraft board; and coverage is 66–75%.
- **Instrument used instead.** `ecr_ordered_static` permutes **Y1's own values** into preseason-ECR
  order within position. **The multiset of values per position is exactly Y1's**, asserted at
  runtime and pinned by a test that proves the guard can fire — so replacement levels, scarcity,
  consumption demand, the positional scale and the universe are all unchanged, and no tie is
  introduced. Only *which player holds which value* changes.
- **Result (re-verified exactly).** Y1 → FP_ECR_Y1: target **+77.3** CI [−44.1, +198.6], 5W/0T/0L;
  dynasty **−132.1** CI [−371.1, +107.0], 1W/0T/4L. Recovered fraction **+9.7% / −18.4%**. Both
  below the 172–250 floor → **UNRESOLVED by the stopping rule fixed in advance, the positive one
  included**. **The sign flips across formats**, which under the project's own G7 reasoning means
  no mechanism is demonstrated. Picks changed **183/320 (57.2%)** and **206/320 (64.4%)**.
  Pick-level regret: Y1 134.8 → FP_ECR_Y1 **139.8**, i.e. **slightly worse** (+5.0, t = 0.36),
  damage concentrated LATE (107.4 → 122.8).
- **Honest confound, reported by the phase:** holding K/DST fixed while re-assigning skill values
  changes skill players' standing against untouched K/DST baselines, producing RB→K 17, WR→K 14,
  TE→K 12 (target) and RB→DST 15 (dynasty). **FP_ECR_Y1 is therefore not a clean "ECR board" arm.**
- **Verdict.** B — small / uncertain. **2020** NO. **NS** HIGHEST.
- **Corrections this audit makes:** §2 C2.
- **Canonical:** the decomposition, the rejection of `ecr_implied_baseline` with its reasons, the
  57–64% divergence, and the phase's central distinction: **"FantasyPros identifies better players"
  ≠ "FantasyPros produces better draft picks."**
- **One claim to soften:** D104 §7's "the evidence now says the problem is NOT projections" is
  stronger than what was measured, and D105 §6 itself retracts the adjacent flatness hypothesis.
  See §6.

### D105 — is the draft objective actually sensitive?

- **Prod** NO — **no `src/` file changed at all.** **Res** YES (`d105_objective_sensitivity.py`
  + 21 tests, including one that starts a second interpreter to prove the seed stream is stable
  across processes).
- **Design.** Within position, re-order by `key(p) = (1−α)·rank_Y1(p) + α·rank_random(p)` and
  re-assign **Y1's own values** down that order. α = 0 reproduces Y1 exactly (pinned by test **and**
  confirmed end-to-end by 0.0% pick divergence); α = 1 is a uniform within-position permutation.
  Deliberately the **same machinery as D104**, so ECR and the scramble sit on one comparison.
  Seeds (0–4) pre-registered; **seeds are not clusters — seasons are (k=5)**.
- **Result (re-verified exactly, all four artifacts).**

  | arm | α | ρ vs Y1 | **ρ vs REALIZED** | **picks changed** | **value vs Y1 (target)** | seasons worse |
  |---|---|---|---|---|---|---|
  | L0 | 0.00 | 1.000 | **0.753** | **0.0%** | +0.0 | — |
  | L1 | 0.25 | 0.953 | 0.718 | **66.2%** | −41.1 [−148.8, +66.7] | 4/5 |
  | L2 | 0.50 | 0.699 | 0.527 | **88.4%** | **−46.5** [−192.8, +99.8] | 3/5 |
  | L3 | 0.75 | 0.294 | 0.242 | 90.6% | −115.0 [−330.8, +100.7] | 3/5 |
  | **L4** | 1.00 | 0.025 | **0.003** | **98.4%** | **−565.8 [−829.1, −302.6]** | **5/5** |
  | FP_ECR_Y1 | — | 0.931 | **0.777** | 57.2% | +77.3 [−44.1, +198.6] | 0/5 |

  Dynasty: L1 −39.5, L2 −60.0, L3 −217.7, **L4 −631.9 CI [−940.4, −323.4], 5/5**; divergence
  69.1 / 87.5 / 89.4 / 98.4%.
- **The decisive result.** At α = 0.50 the engine takes a different player at **seven of every
  eight picks, from pick 1**, and value moves **46.5 points** — below the floor and below the
  seed-to-seed SD of that same level (**159.9**, which I re-derived and which matches the "160" the
  report quotes). **The decision surface is steep; the value surface it sits on is flat.**
- **Retraction inside the phase.** D104's closing hypothesis that "the objective is flat" is
  **wrong** and is retracted: scrambling destroys 566–632 points. The correct, narrower statement is
  that the objective has a **broad robustness plateau and every ranking source tested lives inside
  it**. **ECR moves predictive Spearman by +0.024 — one-tenth of the smallest rung (−0.035).**
- **Verdict.** B — ROBUST. **2020** NO. **NS** HIGHEST.
- **Canonical:** all of it, including the stated limit that the ladder measures **degradation** and
  that symmetry in the improvement direction is **not established**.

### D106 — does the plateau survive the weekly objective?

- **Prod** NO. **Res** one argparse constraint (`choices=OBJECTIVES`), made **before** the run
  because `_play_draft` silently falls through to the season-long branch for an unrecognised
  objective — a typo would have produced a season-long run reported as weekly.
- **Design.** Everything identical to D105; only the realized-value objective changed. Two isolation
  properties newly pinned by test: the weekly lineup is set from **unperturbed** Y1 projections for
  every arm (so this measures draft quality, not lineup quality), and pick divergence is
  **objective-independent by construction** (`_pick_by_tier` has no objective parameter), so D105's
  divergence table carries over rather than being re-measured.
- **Rule fixed before any weekly number existed.** H0 (plateau is objective-specific) requires the
  α = 0.50 delta to clear **both** its seed SD **and** the 172–250 floor.
- **Result (re-verified exactly).**

  | α | target D105 | **target D106** | dynasty D105 | **dynasty D106** |
  |---|---|---|---|---|
  | 0.25 | −41.1 | −43.7 | −39.5 | −69.6 |
  | **0.50** | **−46.5** | **−30.6** | **−60.0** | **−84.3** |
  | 0.75 | −115.0 | −125.5 | −217.7 | −252.5 |
  | **1.00** | **−565.8** | **−621.0** | **−631.9** | **−721.3** |
  | FP_ECR_Y1 | +77.3 | **+48.4** | −132.1 | **−202.4** |
  | ORACLE_Y1 | +795.3 | +767.5 | +717.0 | +671.4 |

  At α = 0.50: target |−30.6| < seed SD **151.1** and < floor; dynasty |−84.3| < seed SD **124.9**
  and < floor. (I re-derived both SDs; they match the report's 151 and 125.) **Both H0 criteria
  fail → H1.** Baselines moved only −1.0% / +0.8%, so this is not a units artifact.
- **The phase's stated prior was half wrong, and says so.** Weekly compresses the *intermediate*
  region at target (plateau ratio 8.2% → 4.9%) but **amplifies the endpoint** (+9.8% target,
  +14.1% dynasty). **Weekly makes the threshold sharper, not shallower.**
- **ECR gets worse under the more faithful objective**: target +77.3 → +48.4 (0/5 → **2/5 seasons
  worse**); dynasty −132.1 → **−202.4**, now worse in **5/5**.
- **The matched regret ladder invalidated itself, and that is the most methodologically valuable
  result in the phase.** Weekly regret came back **non-monotone** (L0 96.8, L2 **73.2**, L4 154.5)
  and *contradicts* the value curve at α = 0.50, where regret falls while realized value also
  falls. This is the arm-relative artifact declared in the pre-registration, now **observed**: a
  scrambled board scrambles the **oracle's** rollouts too, so `max_c V(c)` degrades faster than
  `V(alpha's pick)`. The fingerprint is that the engine matches the oracle **more** often on a
  degraded board (4.4% → **8.1%**). Consequences: the pre-registered choice of absolute realized
  value as primary is vindicated by demonstration, and **no phase-level claim is made** from the
  weekly regret ladder — only the L0 → L4 direction survives.
- **Verdict.** H1; stop the sensitivity branch per the pre-registered rule.
- **2020** NO. **NS** HIGHEST.
- **Canonical:** all of it, including the self-invalidation, which is now the project's standing
  reason why **regret must not be used to compare arms that draft from different boards**.

---

## 3b. Claim ledger

Every claim the brief named, plus the ones a consolidation must not carry forward by accident.
**Status** is one of CANONICAL / CANONICAL-AS-DIAGNOSTIC / SUPERSEDED / RETRACTED / CORRECTED /
NOT-REPRODUCIBLE / UNRESOLVED.

| claim | origin | status | evidence | superseded / retracted by | canonical interpretation |
|---|---|---|---|---|---|
| A pick-level counterfactual oracle and `regret(p) = max_c V(c) − V(chosen)` exist and are the right pick-level metric | D86 | **CANONICAL** | `draft_oracle.py`; boundary enforced by `assert_no_realized_inputs_in_policy`; 320 real pick states | — | The north-star metric. Valid for **one policy on one board**; **not** additive across picks, and **not** comparable across arms that draft different boards (D106 §6) |
| Alpha's mean pick regret 116.2 vs random 122.3 vs best-by-projection 144.6; Alpha captures ~5% of the random-to-perfect gap; `Spearman(score, roster value) = −0.033` | D86 | **CANONICAL** | D86 §3 | — | Use as the reference point for what a "good" normalised regret is. It is why §4.B's 0.6–0.9 ratios are not by themselves a defect |
| The structural decision residual is ~5% of divergences, ~90 points per draft (**upper bound**), below the MDE | D86 | **CANONICAL, independently replicated** | D86 16/320 ≈ 90; D103 0.70 × 129.6 ≈ 91 on a **different slot set**; D103 range 86–113 | — | The best-supported statement about decision-rule headroom. Note it is a residual under one definition ("scored no more and still won"), not "the decision-rule headroom" |
| The incumbent season-long objective prices the bench at zero; 17.8% of realized points come from the bench; a bench player starts in 16.2 of 17 weeks | D86 | **CANONICAL** | D86 §1 | — | Why `WEEKLY_NO_FORESIGHT` exists. It does **not** follow that weekly reveals late value — D103 refuted that |
| **There is no transaction history in this database**; streaming optionality is real and largest at K/DST/TE and cannot be sized | D86 §6 | **CANONICAL** | D86 §6 | — | The reason every conclusion in this program is about the **draft** only |
| O1 is worth +52.9 / +50.5 / **+49.0** in the target format | D86 / D88 / D89 | **NOT REPRODUCIBLE** | D92 §5: identical inputs, deterministic transformation, different outputs ⇒ the runner differed, and it was never committed | D92 §5; restated by D96 §3 | **Must not be quoted as a measurement of this system.** The authoritative O1 numbers are D96 §3's +7.0 / +30.7 on 2021–2025 |
| The MDE floors at ~56 regardless of slots; the binding constraint is **seasons** | D88 | **CANONICAL** | variance decomposition; arithmetic corrected by D89 §6 to a 51.1 floor | arithmetic corrected in D89 §6 (conclusion strengthened) | Governs every power statement since; it is the root of D97's 172–250 floor |
| Y1's value base double-counts: `msv + daVORP = 2·proj − R_p`, amplifying by `1 + proj/(proj − R_p)` — **DST 8.10×, K 5.34×**, TE 3.36×, QB 3.15×, WR 2.61×, RB 2.59× — and at round 10 of a real draft all 60 top-ranked candidates were kickers | D84 | **CANONICAL — derived from algebra, not fitted** | the ranking reproduces the observed pathology ranking; `marginal_starter_value(c) = proj(c)` exactly whenever `c` fills an empty slot, measured across six positions and four roster states | — | The standing explanation for Y1's K/DST behaviour, and why D87's Y1-ranked shortlist re-imports it. **Ten reformulations (D85) failed to beat Y1 anyway** — the incoherence is real and nearly free |
| Economic valuation and roster legality are **already separate**; the legality constraint is an exact null | D85 | **CANONICAL** | the 2×2 gives interaction **+0.00** in all four formats and **zero infeasible rosters in all four arms**; L1 is an exact null | — | Refutes D84's "load-bearing" claim. Legality separation is closed as a direction |
| **Option G** — give `marginal_starter_value` a non-degenerate, startable-slot-aware value for players who cannot crack the lineup | D91 §8 | **NEVER IMPLEMENTED; superseded as a priority** | it needs no availability rates (A1), no weekly objective (73% is season-long-visible), no bye reasoning, no K/DST special-casing, and is closed-form | D91 itself ("instrument before objective"); **D97** then closed the decision-layer investigation on power | The smallest architectural change ever identified, and it remains un-run. It is not a reopening ground on its own: its plausible effect is a fraction of the ~86–113-point residual, well below the 172–250 floor |
| Y1's marginal value is **degenerate across the entire bench** — total spread 0.48 points across six #20-at-position candidates | D91 §3 | **CANONICAL** | `scripts/d91_msv_degeneracy.py`; Y1 RB 0.00 / WR 0.48 / TE,QB,K,DST 0.00 vs O1 6.13–105.10 | — | Rounds 11–16 carry no marginal-lineup signal and fall through to `daVORP`. Independent of the retracted vintage story |
| The market-board **vintage** changes historical results (+49.0 → +28.0) | D91 §2 | **RETRACTED** | D91 counted every `market_rank` entry; D89 counted market-ranked players **inside the projected board** | **D92 §1** | There was only ever **one board**. D91 §9, §12 and the r = +0.601 "between-board natural experiment" all fall with it |
| The historical ECR board is **immutable**: 17/17 board-seasons identical across four upstream vintages, with a positive control on live 2026 | D92 | **CANONICAL** | blobless upstream clone; per-season `(player, position, rank)` hashes | — | **No backtest over 2020–2025 can depend on board vintage.** Definitively excluded |
| Everything published before D92 is unreproducible | D92 §5 | **CANONICAL** | — | — | Applies to D86–D90 including the program's most-cited number |
| **D93 dispatch defect**: `_pick_by_tier`'s draft-aware chain omitted `O_TIERS`, so the "shipped engine" control silently reverted to the D65-era static replacement level | D93 | **CANONICAL; repaired and guarded** | repair merged in D96 §5; D96 verified by reverting the line — exactly the two D93 guard tests fail | — | A control that is not tested against production is not a control. The guard now asserts **every** tier in `DRAFT_AWARE_REPLACEMENT_TIERS` receives a draft-aware level |
| D93's six-season O1 headline (+3.8 target / +27.1 dynasty) | D93 | **SUPERSEDED** | 2020 cells were never legal | **D96 §3** | Authoritative: target **+7.0** CI [−54.1, +68.2] (MDE 61.2); dynasty **+30.7** CI [−13.9, +75.2] (MDE 44.6) — dynasty is above the economic threshold but **below its own MDE**, i.e. formally unresolvable |
| Production breaks exact ties non-deterministically | D94 | **RETRACTED** | `league/draft.py:427` sorts `(−score, player_id)`; D54 fixed and pinned it | **D96 §8** | The non-determinism was in **D94's own ablation replica**, which used a bare `max()`. Nothing live depends on the claim |
| **D95 empty-board contract**: no shipped series has a preseason board before 2021; an empty board silently turns "best available by consensus" into "first alphabetically" | D95 | **CANONICAL; shipped** | raw `fp_page` labels; `MissingMarketBoardError`; 64 real `recommend_draft_pick` calls byte-identical | — | The only production change in D85–D106. Option C (pre-rename label fallback) deliberately rejected as a D56 series redefinition |
| The valid historical evaluation window is **2021–2025** | D96 | **CANONICAL** | `BACKTEST_SEASONS`, asserted as a property over `ALL_SERIES` | — | Narrowing **cost power** (MDE 47.0 → 61.2 target) rather than buying confidence — the honest direction of the correction |
| `ORACLE − PROD` = +784.6 / +704.6 measures **projection headroom** | D97 | **CORRECTED** | it confounds information and rule: `ORACLE` has perfect information **and** the NAIVE rule | D102 §5, identified by D103 §6 | The identified quantity is `ORACLE_Y1 − PROD` = **+795.3 / +717.0**; the implied rule effect under certainty is ~−11/−12 (≈ zero). D97's reading was close to right but **was not identified when made** |
| **The detection floor is 172–250 points and cannot be lowered** | D97 §6 | **CANONICAL** | 5 season clusters (D95/D96), 10 slots (D88), seeds deterministic (D92) | — | The single most consequential constraint in the program. Y1's **entire** decision apparatus (+213.8) is barely above it |
| Per-position bias of the projected top 6: QB +65.2 (5/5), WR +35.3, TE +35.2 (5/5), K +24.1 (5/5), RB +13.1, DST +4.5 — and this ranking predicts the oracle's reallocation exactly | D97 §2 | **CANONICAL** | — | — | The mechanism behind production's first QB at round 2.1 vs the oracle's 7.1. A **magnitude/calibration** defect, and therefore outside the span of D105/D106's ordering ladder |
| `opportunity_cost` is calibrated, not broken (corr 0.73–0.88; understates magnitude 20–65%; moves 9% of picks) | D97 §5 | **CANONICAL** | 360 position-decisions replayed | — | Leave it alone; correcting the magnitude would be an arbitrary multiplier on a near-inert term |
| **D56 in the projection feature path is a false alarm** — IDP share 0.0% in every season; 0 differing feature values including live 2026; the naive fix destroys 2020's feature (366 → 0) | D98 | **CANONICAL** | row-by-row comparison against `preseason_page_type`'s resolution | — | Closed. Two latent fragilities recorded and deliberately left: correctness is contingent on IDP-page players lacking offensive stat lines; `ORDER BY scrape_date DESC` has no deterministic tie-break (D54 class, inert) |
| **Per-position calibration cannot improve within-position top-6 identification** | D99 | **CANONICAL — structural, not statistical** | X1/X2/X4 are monotone in the projection; 0/30, 0/30, 0/30 cells changed (X3 1/30) | — | Algebra, not a measurement: a monotone map cannot reorder within a position. Also canonical: **K cannot be calibrated at all** with existing infrastructure (D57 excludes K/DST) |
| Calibration *can* move cross-position allocation toward the oracle (X2/X3 push first-QB rank 5.0 → 10.3/11.0 against the oracle's 10.0) | D99 §3 | **UNRESOLVED** | rejected on D68's gates and on power (MDE 343–360 at k=3), **not** on the ordering ladder | — | The one live thread on the **magnitude** axis. D105/D106's nulls do not speak to it |
| **M6 is beaten at top-6 identification by its own raw input feature**: 1.950 vs `U_ecr` 2.750, AUC 0.8990 vs 0.9253, ρ 0.7670 vs 0.7895, 11W/8T/1L | D100 | **CANONICAL-AS-DIAGNOSTIC** | re-verified exactly in this audit from `d100_rows.json` | value-relevance retired by **D104 §6** | True as an identification fact; **it does not transfer to pick quality**. No single comparison survives Bonferroni; the pattern (0 losing seasons, null negative control) is the evidence, not any interval |
| `prior_games` / availability-durability carries identification signal | D69 | **CLOSED (negative)** | 0.90 of 6 pooled; **0.00 at RB in every season**; dilutes every aggregation it enters | **D100 §3** | Should not be the basis of a future arm |
| Feature-only ceiling: 1.95 found, **+0.80** extractable-not-extracted, +2.70 not in the features, **+0.55** structurally unreachable | D100 §4 | **CANONICAL-AS-DIAGNOSTIC** | LOSO diagnostic (2.65) does not beat the zero-parameter ECR rank (2.75) | — | A **feature-only diagnostic ceiling**, never an oracle |
| **"Y3 passes all seven gates"** | D78 | **DOES NOT REPRODUCE** | Y3 fails **G6 at WR** on the current snapshot; code drift and nondeterminism both ruled out; data/library drift unresolvable (pre-D78 DB gone) | **D101 §1** | **Any future citation must be re-derived, not quoted.** The D78 selection rule re-applied re-selects **Y1, already live** |
| G6 reads `mean(|signed bias|)` | D78 prose | **CORRECTED** | the code computes `|mean(x)|`; they differ wherever the sign flips across seasons (WR, TE) | D101 §2 | Y3 fails WR under **both** readings, so the ambiguity changes no verdict — but the discrepancy is real and is now on record |
| AUC / Spearman are a usable proxy for top-6 identification | implicit in D78's G4 | **REFUTED** | Y3 leads on AUC (0.9053) and Spearman (0.7823) while Y1 leads on hit rate (0.3750 vs 0.3646) | D100, **D101 §3** | Whole-pool statistics are dominated by the bulk; top-6 membership is a tail event. **G4's Spearman gate is not an identification gate** |
| "Season-long scoring makes late-pick regret near-degenerate by construction" | D102 §3 | **REFUTED by D103's own data** | late regret is **107.4**, 59% of the early figure; `compute_league_starters` allocates the best ten by season total, so a late pick who turns out well *does* enter the lineup | **D103 §4a** | What season-long cannot see is **insurance** value, not late-pick value as such |
| Y1's uncertainty machinery would be actively harmful under perfect information (a large negative interaction) | D102 §5 | **REFUTED** | the implied rule effect under certainty is ~−11/−12 | **D103 §6** | D97's reading of its residual as information-shaped was close to right |
| The pick-level metric already existed and the L0-is-production guarantee was **asserted, not tested** | D102 §2/§4 | **CANONICAL; now fixed** | `test_l0_is_the_shipped_engine` compared L0 only to siblings Q0/Z0; L0 vs H agreed 240/240 on real states when checked | pinned by D103's `TestShippedTierIsProduction` | The property held all along; only the guarantee was missing |
| The evaluation hierarchy: pick regret primary, roster value as validation, information quality demoted and conditional, **MAE/RMSE/Spearman/AUC/top-6 DIAGNOSTIC only** | D102 §8 | **CANONICAL** | — | — | The substantive result of the D98–D101 audit, and the standard D104 then vindicated empirically |
| **Regret is concentrated EARLY** (181.5 vs 107.4 target; 181.1 vs 107.0 dynasty); worst round is round 2 (198.3) | D103 §3 | **CANONICAL in absolute points; INCOMPLETE as a characterisation** | re-verified exactly | complemented by **D107 §4.B** | Normalised by the dispersion available at the pick the ordering **reverses** (0.614 early → 0.739 / 0.925 late). Both readings are correct; the record carried only the first |
| Alpha's pick equals the oracle's in 0% of rounds 1–5 **in both formats**; overall 2.2–4.7% | D103 §3 | **CORRECTED** | dynasty is 5.0% (season-long) and 9.0% (weekly); overall range is **1.9–4.7%** | **D107 §2 C1** | True for `target_league` only |
| **The weekly objective REDUCES regret everywhere** (−27.4 / −38.7) rather than revealing hidden late value | D103 §4b | **CANONICAL** | clustered CIs exclude zero in both formats | — | A weekly lineup adapts, so swapping one player moves the summed total less. Weekly remains the more faithful `U`; it makes every pick matter **less** |
| Perfect information with the rule held at Y1 is worth **+795.3 / +717.0**, 5/5 seasons | D103 §6 | **CANONICAL** | re-verified exactly; `oracle_static` boundary pinned by test | — | A **hindsight ceiling**, an upper bound on nothing achievable. Never to be used as evidence Y1 should change |
| 92–96% of divergences are "the oracle's player simply scored more" | D103 §5 | **CANONICAL, and explicitly unattributable** | — | — | **No share of it may be quoted as projection error**: it conflates bad information with unavoidable variance and this instrument cannot separate them |
| `ecr_implied_baseline` is a usable ECR→value transform | repo, pre-D104 | **REJECTED on measured grounds** | 2023 RB top-24 has 4 distinct values (largest tie group 12) → alphabetical picks in rounds 1–5; hardcodes `ecr_type='ro'` (a D56 violation for dynasty); 66–75% coverage | D104 §1 | Not usable as a draft board. `ecr_ordered_static` (value-multiset-preserving) is the correct instrument |
| **The best real preseason ranking recovers ≤10% of the oracle gap in one format and is negative in the other**: +77.3 / −132.1 season-long, +48.4 / −202.4 weekly | D104, strengthened D106 §5 | **CANONICAL** | re-verified exactly; both below the 172–250 floor; sign flips across formats | — | **Unresolved**, not zero — the positive one included. The arm is also confounded by holding K/DST fixed (RB→K 17, WR→K 14, TE→K 12) |
| ECR changes 57–64% of picks, first divergence **round 1 in 20/20 drafts** | D104 §5 | **CORRECTED** | histogram target {1:11, 2:5, 3:3, 5:1}; dynasty {1:11, 2:5, 3:1, 4:2, 5:1} | **D107 §2 C2** | **All 20 diverge, and all within five rounds; round 1 in 11 of 20.** The 57.2% / 64.4% figures reproduce exactly |
| **"FantasyPros identifies better players" ≠ "FantasyPros produces better draft picks"** | D104 §6 | **CANONICAL** | D100 established the former; D104 tested the latter directly and it did not follow | — | The clearest demonstration in the program that **projection proxy metrics do not transfer to pick quality**. It retires the D97 → D100 reasoning chain |
| "The draft objective is FLAT near Y1's operating point" | D104 §7 | **RETRACTED by its own author in D105 §6** | a full scramble costs 566–632 points | **D105 §6** | The objective has a **broad robustness plateau**, and it is **bounded** |
| "The evidence now says the problem is NOT projections" | D104 §7 | **TOO STRONG** | D105/D106 measure a 566–721-point cost to destroying the projection ordering | **D107 §6.1** | Defensible form: *"not the projection-quality differences available from the sources tested, at the resolution this instrument has."* |
| **The objective is THRESHOLDED**: 88% of picks change for −46.5 points; a full scramble costs −565.8 (5/5, CI excluding zero) | D105 | **CANONICAL** | re-verified exactly, including the seed SD (159.9 ≈ the quoted 160) | — | **The decision surface is steep; the value surface is flat — up to a threshold.** ECR moves predictive Spearman by **+0.024**; the smallest rung is **−0.035** |
| The ladder degrades **predictive** quality, not just agreement with Y1 (ρ vs realized 0.753 → 0.003) | D105 §2 | **CANONICAL** | `d105_validity.json`, re-verified | — | This is what makes the x-axis a measured quantity and lets ECR be placed on the same scale |
| The required ranking improvement is **±0.5** in predictive Spearman | D105 §7 | **EXTRAPOLATION, labelled as one** | the ladder measures **degradation**; symmetry is not established | — | Usable as a **pre-screen threshold**, not as a measurement. The only improvement-side anchor is ORACLE_Y1, which needs hindsight and changes values rather than order |
| **The plateau is objective-independent** (H1): at α = 0.50 the delta is below both its seed SD and the floor under **both** objectives, in **both** formats | D106 | **CANONICAL** | re-verified exactly, including seed SDs 151.1 and 124.9 | — | Weekly makes the threshold **sharper**, not shallower: the intermediate region compresses (8.2% → 4.9% at target) while the endpoint **amplifies** (+9.8% / +14.1%) |
| The matched **weekly regret ladder** (L0 96.8, L2 73.2, L4 154.5) | D106 §6 | **SELF-INVALIDATED, deliberately** | non-monotone and contradicts the value curve; the fingerprint is the engine matching the oracle **more** on a degraded board (4.4% → 8.1%) | declared in D106's own pre-registration, then observed | **Regret must not be used to compare arms that draft from different boards.** Only the L0 → L4 direction survives. **No phase-level claim is made** from it |
| "The projection/ranking sensitivity branch is CLOSED" | D106 §7 | **SUPPORTED ONLY AS A STOPPING RULE** | the pre-registered rule; not a demonstrated absence of effect | qualified by **D107 §6.1** | The branch stops because experiments **of this design** cannot resolve effects of the available size. Ranking quality demonstrably matters at the severe end |
| "Y1 is operating in a regime where neither better rankings nor a better decision rule can produce a **measurable** gain" | D106 §8 | **CANONICAL as written** | — | — | The word **measurable** is load-bearing and must survive every future quotation of this sentence |

---

## 4. North-star / pick-level evidence audit

> *"At every individual draft pick, select the best available option given the current roster and
> remaining player pool."*

### A. Can we measure whether one draft pick is better than another?

**Yes, with two stated boundaries.**

`draft_oracle.audit_draft` measures, at a real pick state `S_p`, the one-step oracle under a fixed
continuation policy:

```
V(c) = realized value of the final roster if I take c now and then play the
       REST of the draft exactly the way the shipped engine plays it
regret(p) = max_c V(c) − V(alpha's pick)
```

That is a close match to the north-star's own phrasing — "best available *given the current roster*"
and "continue playing as I actually will". Its information boundary is enforced structurally
(`assert_no_realized_inputs_in_policy` inspects the signatures of both `_pick_by_tier` and
`roster_aware_market_pick`), and as of D103 the rollout policy is **tested** to be production, not
merely asserted to be.

**Boundary 1 — regret is not additive.** Mean regret is 134.8 per pick over 16 picks = 2157 points,
larger than the entire roster it is measured on (1983.6). Each pick's regret holds the rest of the
policy fixed, so they overlap heavily. The whole-draft quantities are ORACLE_Y1 (+795.3) and the
structural residual (~91/draft), **not** any sum of pick regrets.

**Boundary 2 — regret is arm-relative, demonstrated not hypothesised.** D106 §6 showed that when
the *board* changes, the oracle's own rollouts change too, and regret can fall while realized value
also falls. **Regret is valid for measuring one policy on one board; it is invalid for ranking arms
that draft from different boards.** This was declared in advance and then observed, which is the
strongest form the finding could take.

### B. Does Y1 lose substantial realized value relative to an oracle at the pick level?

**Yes in absolute points — and the normalised picture is different from the one the record
currently conveys.**

Absolute (target, season-long): 134.8 mean regret, 181.5 early, 107.4 late; Alpha's pick equals the
oracle's in 2.2% of picks and **0% of rounds 1–5 in the target format** (see §2 C1 for dynasty).

The D103 artifact also stores the **candidate slate spread** at every pick. Normalising:

| phase | target SL regret | slate spread | **regret / spread** | dynasty SL ratio |
|---|---|---|---|---|
| EARLY 1–5 | 181.5 | 303.8 | **0.614** | 0.606 |
| MIDDLE 6–10 | 121.0 | 191.2 | 0.645 | 0.748 |
| LATE 11–16 | 107.4 | 141.8 | **0.739** | **0.925** |
| ALL | 134.8 | 207.8 | 0.671 | 0.770 |

Weekly is uniformly lower but has the same shape (target 0.566 → 0.567 → **0.640**).

**In absolute realized points the largest losses are early — that is true, reproduces exactly, and
is the right basis for deciding where points live. As a share of the dispersion actually available
at the pick, Y1 does best early and worst late.** Both readings are correct and they answer
different questions. The record currently carries only the first, and the phrase "regret is
concentrated EARLY, not late" invites the inference that late picks are being handled comparatively
well. They are not.

**The reading that is NOT supported:** that the late ratio is evidence of a decision defect. D86
measured a random pick from the same slate at 122.3 against Alpha's 116.2 — Alpha captures only
~5% of the random-to-perfect gap — so a ratio in the 0.6–0.9 range is close to what an uninformed
draw gives, at *every* phase. That is the same fact D105 states as "the value surface is flat":
late candidates are nearly indistinguishable in realized value, so a high normalised regret is
expected and is not by itself a defect. The part that would be a defect is the structural residual,
and that is 4.5–7.9%.

### C. How much of the gap is information versus decision-rule behaviour?

**Measured, with one honest limit that stops it being fully resolved.**

| quantity | target | dynasty | status |
|---|---|---|---|
| information value, rule held at Y1 (`ORACLE_Y1 − PROD`) | **+795.3** [+579.1, +1011.4] | **+717.0** [+432.8, +1001.3] | measured, 5/5 both |
| implied rule effect under certainty (vs D97's `ORACLE − PROD`) | ~−11 | ~−12 | cross-run (4 vs 10 slots); indistinguishable from zero |
| decision-shaped structural residual | ~91 /draft (SL), ~108 (WK) | ~86–113 /draft | **below the 172–250 floor** |
| oracle's player simply scored more | 95.5% (SL) / 92.9% (WK) | 95.2% / 92.1% | **cannot be attributed** |

**The limit, quoted because it is the single most important caveat in the program:** "scored more"
conflates bad information with unavoidable variance, and this instrument cannot separate them.
**No share of the 92–96% may be quoted as projection error.** D103 says this; it must survive
consolidation.

D102's expectation that Y1's uncertainty machinery (survival, confidence, opportunity cost) would
be actively harmful under certainty was **refuted** — the interaction is ~−11, not large. So D97's
reading of its residual as information-shaped was close to right, though it was not identified at
the time it was made.

### D. Is there evidence that changing the decision rule can recover a measurable amount?

**No. Repeatedly, across independent families, and with a power explanation for why.**

- Nine/ten value-base reformulations (D85) — all failed; the slope problem was structural.
- The weekly-objective candidate O1 (D86–D93), restated on the legal window: target **+7.0**
  CI [−54.1, +68.2] against MDE 61.2; dynasty **+30.7** CI [−13.9, +75.2] against MDE 44.6. Both
  CIs span zero; the claimed K/DST mechanism is ≈0 in both formats.
- Legality separation (D85/D94) — failed.
- D97's decomposition: **Y1's entire decision apparatus is worth +213.8 against an MDE of 179.4**
  in target, and +35.7 against 210.0 in dynasty. Any incremental refinement would have to be worth
  roughly as much as everything Y1 already does merely to be **detectable**.
- D103: the decision-shaped residual is ~86–113 points per draft against a 172–250 floor.

**This is the best-supported negative result in the program.** Note precisely what it says: *no
decision-rule change has been shown to produce a measurable gain on this instrument*, not *no
decision-rule change would help*.

### E. Is there evidence that changing the available preseason ranking/projection can recover a measurable amount?

**No, for everything tested — and "everything tested" is narrower than it sounds.**

Tested and rejected: per-position calibration (D99, structurally inert for within-position order);
the registered training-set arms Y0–Y3 (D101, Y1 re-selected); the FantasyPros consensus board
substituted into Y1's own value scale (D104, +77.3 / −132.1, both below the floor, sign flips
across formats, and *worse* at pick-level regret by +5.0); and the whole degradation ladder
(D105/D106).

**What "tested" does not cover, stated explicitly because the closure language elsewhere is
stronger than this:**

1. **One real alternative source.** n = 1. FantasyPros ECR is the only non-synthetic ranking ever
   put through the instrument.
2. **Degradation only.** The ladder runs α from 0 to 1, i.e. from Y1 to noise. **There is no
   improvement-side rung.** D105 §7 labels the ±0.5 requirement as an extrapolation by symmetry and
   says symmetry is not established. The only improvement-side anchor is ORACLE_Y1, which needs
   hindsight and changes values rather than order.
3. **The value multiset is held fixed at every rung.** The ladder can only change *which player
   holds which number*. It cannot test any change to the projected *magnitudes* — the spread at the
   top of the board, the cross-position calibration, the QB +65.2 / TE +35.2 / K +24.1 top-6 bias
   D97 measured. D99 tested the monotone slice of that axis and showed it cannot reorder within
   position; the non-monotone, cross-position slice (D99's X2/X3, which *do* move first-QB rank
   from 5.0 toward the oracle's 10.0) was rejected on D68's gates and on power (MDE 343–360 at
   k = 3), **not** on the ladder.
4. **The FP_ECR_Y1 arm is confounded** by holding K/DST fixed (RB→K 17, WR→K 14, TE→K 12 in target).
   D104 reports this. It means the one real source was tested through a slightly dirty channel.

### F. Does the conclusion survive changing the objective from season-long to weekly no-foresight?

**Yes, and it survives in a stronger form than expected.** D106 is H1 in both formats under a rule
fixed before any weekly number existed. The intermediate region compresses at target (plateau ratio
8.2% → 4.9%), the endpoint **amplifies** in both formats (+9.8% / +14.1%), and **ECR's result gets
worse, not better**, under the more faithful objective (0/5 → 2/5 seasons worse at target;
−132.1 → −202.4 and 5/5 worse at dynasty).

One precision the check-list wording deserves: the weekly objective is a **roster-value function
`U`, not a policy**, so it is *allowed* to see outcomes — and it does see one: which players
actually suited up that week. It does not see who scored well. The docstring states this
("a manager who knows who is available but not who will do well") and identifies it as the
**pessimistic bracket**, with the full-hindsight `weekly_lineup_points` as the optimistic one.
That is the correct architecture: the leakage constraint binds on the policy, and it is enforced
there.

### G. What remains unresolved?

1. **The 25-to-250-point blind band.** The economic threshold is 25 points; the detection floor is
   172–250 and **cannot be lowered** (5 season clusters hard-capped by the board contract; slots
   proven useless by D88; seeds deterministic by D92). **Every candidate this project has ever
   proposed has a plausible effect inside that band.** Nothing in D86–D106 distinguishes "no effect"
   from "an economically meaningful effect this instrument cannot see."
2. **The improvement direction of the ranking ladder** (§4.E limit 2).
3. **Projection magnitudes / cross-position calibration** (§4.E limit 3) — identified by D97's bias
   table and D99 §3, unresolvable at k = 3.
4. **The split of the 92–96% "scored more"** into bad information vs unavoidable variance.
5. **D78's Y3 non-reproduction** (D101 §1) — cause unresolvable; the pre-D78 database is gone.
6. **Everything before D92 is unreproducible** (uncommitted runners). The program's own most-cited
   number, +49.0, is in that set.
7. **In-season decisions are entirely unmeasured**, because **there is no transaction history in
   this database** (D86 §6). Streaming optionality is real and largest at K/DST/TE, and its
   magnitude cannot be pinned down without that data. Every conclusion above is about the **draft**.

### The four-way distinction the brief asked for

| | quantity | measured value | status |
|---|---|---|---|
| **Theoretical / oracle headroom** | `ORACLE_Y1 − PROD` | +795.3 / +717.0 | real, requires hindsight, **an upper bound on nothing achievable** |
| **Empirically reachable headroom** | best real preseason ranking | +77.3 / **−132.1** | sign flips; no mechanism demonstrated |
| **Measurable headroom** | anything ≥ the floor | **≥ 172–250 points** | nothing tested has reached it |
| **Demonstrated production improvement** | — | **none, in any phase from D85 to D106** | — |

**"An oracle gap exists" has never been, and is not here, used as evidence that Y1 should change.**

---

## 5. Instrument / data-contract audit

All fourteen checks, each verified against code, tests, or a live read-only run in this audit.

| # | check | result | evidence |
|---|---|---|---|
| 1 | benchmark seasons = 2021–2025 | **PASS** | `board_vintage.py:84` `BACKTEST_SEASONS = (2021,…,2025)`; pinned by `test_board_vintage.py:175`; all of `d103`/`d104`/`d105` import it rather than carrying a copy |
| 2 | 2020 is refused | **PASS** | `market/series.py:37,42` `first_preseason_season = 2021` + `covers()`; `market/edge.py:160` raises `MissingMarketBoardError`; `test_market_series.py:199` asserts `covers(2021)` and `not covers(2020)`; all four series refuse 2020 at once |
| 3 | empty market boards cannot silently degrade | **PASS** | two layers: `market/edge.py::MissingMarketBoardError` at the query (D95) and `draft_forensics.py:1080 EmptyMarketBoardError` / `assert_usable_market_board` at the opponent (D89), called at `draft_forensics.py:2231`; tests assert the message names "alphabetically" |
| 4 | O-tier production parity is enforced | **PASS** | `O_TIERS` is inside `DRAFT_AWARE_REPLACEMENT_TIERS` (`draft_forensics.py:781–790`), dispatched at `:1322`; the guard asserts **every** member receives a draft-aware level through `_pick_by_tier`; D96 verified by reverting the line — exactly the two D93 guard tests fail and nothing else |
| 5 | production uses deterministic tie-breaking | **PASS** | `league/draft.py:427` `candidates.sort(key=lambda c: (-c.score, c.player_id))`; D54 convention; re-asserted by D104's own substitution tests |
| 6 | no reliance remains on D94's retracted tie claim | **PASS** | retraction recorded in D96 §8; no live code or test depends on it; the only `PYTHONHASHSEED` reference left in `src/` is a `draft_simulation.py` comment documenting the *fixed* convention |
| 7 | parity is tested against `recommend_draft_pick` itself | **PASS** | `TestShippedTierIsProduction` (D103) walks whole drafts at every slot, comparing the **chosen player** against tier `H` — a direct pass-through to `recommend_draft_pick` — at every audited state, continuing on production's pick so a divergence cannot fork the state |
| 8 | both target and dynasty formats have parity evidence | **PASS, and closed explicitly in this audit** | **D96 §4**: `target_league` O0 matches production in all 50 covered cells (as do L0/Q0/Z0) and `dynasty_1qb` O0 matches in all 50 (L0 likewise). **New here:** re-running the existing read-only `--mode parity` over both formats gives **L0 vs `H` agreeing on 640 of 640 real pick states, 0 disagreements** (2021–2025 × slots {1,4,7,10} × 16 rounds × both formats) |
| 9 | D92 vintage remains reproducible | **PASS** | `compute_board_vintage` re-run read-only in this audit returns `ca3e2d8af6aa892067c7450095a1c992087f613141e3b36b89b12928713d5f99` over (2021–2025) — the exact hash `CLAUDE.md` and every phase from D97 on records |
| 10 | no 2026 leakage/check in the benchmark | **PASS** | `2026 ∉ BACKTEST_SEASONS`, asserted in `test_d104_ecr_floor.py:192`; `d103_pick_regret.py` contains **no** `2026` reference at all; `d101`/`d104`/`d105` explicitly `if season in (2020, 2026): continue`; every phase D98–D106 records "no 2026" |
| 11 | the weekly objective uses no future information | **PASS, with a precision** | `weekly_lineup_points_no_foresight` sets the lineup from **preseason projections** among that week's actual participants. It uses realized **availability** and no realized **performance**, is documented as "knows who is available but not who will do well", and is the **pessimistic bracket**. This is a roster-value function `U`, not a policy — the leakage constraint binds on the policy and is enforced there (check 12) |
| 12 | ORACLE_Y1 has the correct information boundary | **PASS** | `oracle_static` replaces **only** `projections` and the derived `vorp`; `market_rank`, `confidence`, `ecr_dispersion`, `consumption_demand` and `scarcity_*` are held, with the reason for each written into the docstring. Pinned by `TestOracleStaticScope`, plus a test that `oracle_static` is reachable from `run_oracle_y1` and **not** from `run_regret` |
| 13 | L0/H parity is actually tested now | **PASS** | as check 7. Before D103 it was asserted in a docstring and compared only to sibling replicas Q0/Z0 — a drift common to all three would have passed silently |
| 14 | `models/` and `league/` remain at the Y1 hashes | **PASS** | `models/` `73b408e9bd12daecdd6a2a875e48735319b66aef`, `league/` `d4cfd00e31b949c79eda397824a7952bd31f8f9f` — **byte-identical to `origin/main`** at HEAD |

**Nothing failed. The audit was not required to stop.**

Two things recorded rather than repaired, in line with the phase's instruction:

- **Check 8 nuance, now resolved.** The much-quoted **240/240** L0-vs-`recommend_draft_pick` figure
  (D102 §17.1, carried into D103) is a **`target_league`** number: 5 seasons × slots {1, 5, 10} ×
  16 rounds = 240. `d103_pick_regret.py --mode parity` has always iterated **both** formats; the
  dynasty count was simply never re-quoted alongside it. This audit ran it and the cross-format
  figure is **640/640, 0 disagreements** (addendum). Future citations should use that number rather
  than the target-only 240.
- **D98's two latent fragilities** remain open by deliberate decision: the ECR subquery's
  correctness is *contingent* on IDP-page players lacking offensive stat lines (zero occurrences in
  six seasons), and `ORDER BY scrape_date DESC` has no deterministic tie-break (ties exist but are
  always superseded). Both are inert today and both would be fixed by scoping the subquery to
  `preseason_page_type`'s resolution — provably a no-op on all six seasons, which is exactly why
  D98 declined to make it a standalone edit to `models/`.

---

## 6. D103–D106 conclusion audit

Each link in the stated chain, checked against the artifacts.

| # | stated conclusion | verdict | correction |
|---|---|---|---|
| 1 | D103 established valid pick-level regret measurement | **SUPPORTED** | add the arm-relative limit D106 later demonstrated (§4.A boundary 2) |
| 2 | Regret is concentrated early | **SUPPORTED in absolute points; INCOMPLETE as stated** | normalised by available slate dispersion the ordering **reverses** (§4.B). Also §2 C1: the "0% of rounds 1–5 in both formats" sub-claim is false for dynasty |
| 3 | ORACLE_Y1 produces a large information gap (~795 / ~717) | **SUPPORTED, verified exactly** | it requires hindsight and is an upper bound on nothing achievable — D103 §8 already says so; keep that attached |
| 4 | The decision-shaped residual is only ~86–113 pts/draft and below the floor | **SUPPORTED** | it is a residual under a *specific* definition ("oracle's player scored no more and still won"), and the complementary 92–96% is **unattributable**. It is not "the decision-rule headroom" |
| 5 | D104 showed substituting FantasyPros ECR does not improve realized draft value | **SUPPORTED, verified exactly** | precisely: it does not improve it **measurably**; +77.3 and −132.1 are both *unresolved*, not *zero*. The arm is also confounded by fixed K/DST. §2 C2 corrects the first-divergence figure |
| 6 | D105 showed the objective is thresholded rather than flat | **SUPPORTED, verified exactly** | this is a *retraction* of D104's own closing hypothesis and is correctly recorded as one |
| 7 | D106 reproduced the threshold/plateau under weekly no-foresight | **SUPPORTED, verified exactly** | and strengthened it: the endpoint amplifies, ECR worsens, H1 on a rule fixed in advance |
| 8 | **Therefore the projection/ranking sensitivity branch is closed** | **SUPPORTED ONLY AS A STOPPING RULE** | see below |
| 9 | No tested decision-rule modification has demonstrated sufficient improvement to justify changing Y1 | **SUPPORTED** | as written — "tested", "demonstrated", "sufficient". Keep all three words |

### 6.1 The one statement that needs its wording fixed

D106 §7 is careful — it has a whole subsection headed "what this must NOT be read as", and it says
"neither better rankings nor a better decision rule can produce a **measurable** gain". That is
defensible.

**The statement that is too strong is D104 §7's "the evidence now says the problem is NOT
projections."** D105 §6 already retracts the adjacent flatness hypothesis from the same section,
and D105/D106 then measured a 566–721-point cost to destroying the projection ordering. The
defensible version of D104 §7 is:

> *The evidence says the problem is not the projection-quality differences available from the
> sources tested, at the resolution this instrument has.*

**And the closure in statement 8 is a research-allocation decision, not a demonstrated absence of
effect.** The branch stops because further experiments *of this design* cannot resolve effects of
the size available — which is the pre-registered stopping rule, and a legitimate reason to stop.
It is not evidence that ranking quality is irrelevant; D105/D106 measure the opposite at the
severe end.

### 6.2 The reframing the record should carry

§4.B: **absolute regret is concentrated early; normalised regret is concentrated late.** Both
follow from the same artifact. The second is the reading that speaks directly to the north-star's
"the end of the draft", and the record currently does not carry it.

It is **not** evidence of a defect (§4.B, final paragraph). It is evidence that the late-draft
environment is one in which the available candidates are nearly indistinguishable in realized
value — which is the D105 plateau, seen per-phase.

---

## 7. The D104 / D105 / D106 interpretation — is "ECR doesn't work" the right conclusion?

**No. And the brief's proposed replacement is close but still needs two qualifiers.**

The brief proposes:

> "Within the tested information sources and perturbation range, ranking differences generally
> remain inside a region where the current draft environment/objective does not register a reliably
> measurable realized-value difference."

Clause by clause:

- *"Within the tested information sources"* — **necessary and supported.** n = 1 real source.
- *"and perturbation range"* — **supported but under-specified.** The range is
  **degradation-only**, α ∈ [0, 1] from Y1 to noise. There is no improvement-side rung.
- *"ranking differences **generally** remain inside a region"* — **"generally" is doing correct
  work.** The plateau is **bounded**: α = 1.00 sits outside it at −565.8 / −631.9 (season-long)
  and −621.0 / −721.3 (weekly), 5/5 seasons, CIs excluding zero.
- *"does not register a **reliably measurable** realized-value difference"* — **exactly right.**
  This is a statement about resolution at k = 5, not about absence.

**What the proposed wording omits and should not:** the ladder holds each position's **value
multiset fixed**, so every statement in it is about **within-position ordering** and none of it is
about projection **magnitudes**. That matters because D97's own diagnosis of where the value goes —
the projected top 6 at QB carrying +61.6 VORP and realizing −3.6 — is a magnitude/calibration
defect, and it lies outside this ladder's span entirely.

**The wording I can fully support:**

> Within the one real alternative preseason ranking tested (the FantasyPros consensus board,
> substituted into Y1's own value scale) and a degradation-only ladder of within-position
> re-orderings that hold each position's value multiset fixed, realized draft value did not move by
> a reliably measurable amount — under either the season-long or the weekly no-foresight objective,
> in either shipped 1-QB format — until the ordering was almost entirely destroyed. Beyond that
> point the objective is demonstrably **not** indifferent: a full within-position scramble costs
> 566–721 points, 5/5 seasons, with intervals excluding zero. What has **not** been tested is the
> improvement direction, any second real ranking source, or any change to projection magnitudes
> rather than order.

That is supported in every clause by artifacts I re-derived in this audit.

**And the specific thing D104 demonstrated, which is the most transferable result in the whole
program:** *"FantasyPros identifies better players" does not imply "FantasyPros produces better
draft picks."* D100 established the former on three metrics; D104 tested the latter directly and it
did not follow. This retires the D97 → D100 reasoning chain and is the project's clearest evidence
that **projection proxy metrics do not transfer to pick quality.**

---

## 8. Production change vs research record

### A. Legitimate production / instrumentation improvements

| item | phase | where | status |
|---|---|---|---|
| Market-series coverage window (`first_preseason_season`, `covers`) and `MissingMarketBoardError` | D95 | `market/series.py`, `market/edge.py` | **already on `main`** (PR #20); verified byte-identical output on 64 real `recommend_draft_pick` calls |
| `EmptyMarketBoardError` / `assert_usable_market_board` | D89 | `evaluation/draft_forensics.py` | already on `main` |
| `BACKTEST_SEASONS` = 2021–2025, asserted as a property over `ALL_SERIES`; runner guard; `d92_paired_grid` reads the contract | D96 | `evaluation/board_vintage.py`, `scripts/` | **already on `main`** (PR #21) |
| O-tier draft-aware dispatch repair + the guard over `DRAFT_AWARE_REPLACEMENT_TIERS` | D93, merged D96 | `evaluation/draft_forensics.py` | already on `main` |
| Board vintage instrument (`board_vintage.py`) and the committed paired-grid runner | D92 | `evaluation/`, `scripts/` | already on `main` (PR #18) |
| **Selectable roster-value objective on the oracle** (`SEASON_LONG` / `WEEKLY_NO_FORESIGHT`, `RosterScorer`, `make_roster_scorer`, `scorer=None` preserving D86 byte-for-byte) | **D103** | `evaluation/draft_oracle.py` | **in this stack** |
| **`TestShippedTierIsProduction`** — whole-draft L0-vs-`recommend_draft_pick` parity | **D103** | `tests/unit/test_draft_oracle.py` | **in this stack** |

The last two are the only items in the D98–D106 stack I classify as belonging to the canonical
instrument. The justification is **not** that the code is useful — it is that every regret number
the oracle has ever produced assumes `SHIPPED_TIER` is production, and that assumption was
documented-but-untested for the entire D86 lineage. A property every measurement depends on belongs
in the instrument with a test. The objective parameter qualifies on the same ground: D86 proved the
default objective prices the bench at zero, and leaving the oracle unable to express the alternative
means the instrument cannot measure the thing D86 itself identified.

**Boundary check, run in this audit:** nothing inside `src/` imports `evaluation/draft_oracle.py`
except the module itself — not `league/`, not `models/`, not `cli.py`. Its only importers anywhere
are the three D103–D105 research scripts and their three test modules. In the other direction,
`league/` and `models/` import nothing from `evaluation/` at all. The separation is clean both ways.

### B. Research-only changes and documentation

- `docs/D99_…` through `docs/D106_…` (7 reports), the `DECISIONS.md` entries D98–D106, and the
  `PROJECT_STATE.md` status blocks M50–M56.
- `scripts/research/d100_feature_signal.py`, `d101_y_arm_identification.py`, `d103_pick_regret.py`,
  `d104_ecr_floor.py`, `d105_objective_sensitivity.py`.
- `tests/unit/test_d100_…`, `test_d101_…`, `test_d103_…`, `test_d104_…`, `test_d105_…` — these test
  **research harnesses**, not production behaviour, and belong with the scripts.
- D106's `choices=OBJECTIVES` argparse constraint — in the research script, therefore research.
- Every annotation and retraction (D104's flatness hypothesis, D102's two refuted claims, D101's
  "must be re-derived, not quoted", D106's regret-ladder self-invalidation).

**Nothing in group B is proposed for production, and no research experiment is being reclassified
as production because its code turned out to be useful.**

---

## 9. Merge-stack inventory *(reported, not merged)*

*Measured at the state this audit examined — `d106-weekly-sensitivity` at `397e707`, before D107's
own documentation commit. That commit adds this report, one `DECISIONS.md` entry and one
`PROJECT_STATE.md` block, and changes no source file, so it takes the stack to 17 commits and 25
files while leaving every other row below unchanged.*

| | |
|---|---|
| current branch | `d106-weekly-sensitivity` |
| current HEAD | `397e707` — *D106: the matched regret ladder invalidates itself -- and vindicates the primary* |
| `origin/main` | `277204f` — *Merge pull request #22 from gimann421/d97-decision-layer-diagnostic* |
| merge-base | `277204f1e20d59e887e5d5e4144eaae3202a8e08` — **`origin/main` is a strict ancestor** |
| commits `main..HEAD` | **16** |
| merge commits in range | **0 — the stack is linear** |
| files changed | **22** (+7851 / −8) |
| `src/` files changed | **1** — `evaluation/draft_oracle.py` (+114 / −8) |
| `models/` tree | `73b408e9bd12daecdd6a2a875e48735319b66aef` — **identical to `origin/main`** |
| `league/` tree | `d4cfd00e31b949c79eda397824a7952bd31f8f9f` — **identical to `origin/main`** |
| tests | **1427 passed, 44 deselected**, 2 warnings, 164 s, exit 0 |
| ruff | **All checks passed** |
| working tree | clean at the start of this audit; carries only this report, the `DECISIONS.md` D107 entry and the `PROJECT_STATE.md` M57 block at the end of it |

### Commit → phase mapping

| commit | phase | scope |
|---|---|---|
| `be7105c` | D98 | docs only |
| `27cad65` | D99 | docs only |
| `7c9d022` | D100 | docs + research script + tests |
| `6d63a6a` | D101 | docs + research script + tests |
| `a4d191e` | D102 | docs only |
| `eae7e1b` | D103 (WIP) | **`src/alpha_squad/evaluation/draft_oracle.py`** + research script + tests |
| `c3463f8` | D103 | docs only |
| `58bd267` | D103 | docs only (corrects a stale PR-status line carried since D99) |
| `1fd33ee` | D104 | docs + research script + tests |
| `5fff08e` | D104 | docs only |
| `9319f44` | D105 (WIP) | research script + tests |
| `bdca704` | D105 | docs only |
| `9f45308` | D105 | docs only |
| `fee0806` | D106 | pre-registration doc + argparse constraint + tests |
| `bc633e1` | D106 | docs only |
| `397e707` | D106 | docs only |

**No commit contains unrelated changes.** Every commit is scoped to one phase, and the only commit
touching `src/` is `eae7e1b`, whose entire `src/` diff is the D103 instrument change.

**No phase accidentally modified production code.** Verified three ways: the tree hashes above;
`git diff --name-only origin/main..HEAD -- src/` returns exactly one file; and that file is in
`evaluation/`, which no production path imports.

### PR #23

**Still open.** Head `d98-ecr-feature-integrity` at `be7105c`, base `main` at `277204f`, opened
2026-09-14, title *"D98: the D56 concern in the projection feature path is a false alarm — close
it"*. It is the **only** open PR on the repository.

`be7105c` is the **first commit of this stack**, so merging the `d106-weekly-sensitivity` tip would
**naturally subsume PR #23** — its commit arrives as an ancestor and the PR would close as merged.
No PR was created or modified in this phase.

---

## 10. Canonical state of the draft problem

### 1. What is Y1?

The shipped draft objective in `league/draft.py::recommend_draft_pick`:

```
score = (msv + DRAFT_VORP_WEIGHT·daVORP + opportunity_cost) × fit × confidence × survival
        [× 0.1 if the position is over its lineup-derived cap]
candidates sorted by (−score, player_id)          # D54 determinism
```

`models/` `73b408e9`, `league/` `d4cfd00e`. It has been production throughout D85–D106 and has
never been modified by any of them.

### 2. What exactly have we established about its pick quality?

That it can be measured, at real pick states, against a one-step oracle under its own continuation
policy — and that the rollout used to measure it **is** production (now tested, not asserted).
Measured: mean regret 134.8 (season-long) / 107.4 (weekly) per pick in the target format; the
engine matches the oracle 2.2–4.7% of the time overall and 0% in rounds 1–5 of the target format.
Y1 captures roughly 5% of the random-to-perfect gap at a pick (D86), and `Spearman(engine score,
final roster value) = −0.033`.

### 3. Where does it lose value?

**In absolute points: early** — 181.5 in rounds 1–5 against 107.4 in rounds 11–16, worst at round 2
(198.3). **As a share of the dispersion available at the pick: late** — 0.614 early rising to 0.739
(target) and 0.925 (dynasty) late. Positionally, the loss is **cross-position** in 73–78% of
divergences, and the dominant signature is QB timing: production takes its first QB in round 2.1
where perfect foresight waits until 7.1, because the projected top-6 QBs realize **−3.6** VORP
against a projected +61.6 while the *actual* top 6 hold +69.7.

### 4. What is the size and nature of the oracle gap?

With the decision rule held at Y1 and only the projections replaced by realized points:
**+795.3 (target) / +717.0 (dynasty)** realized starter points, 5/5 seasons in both formats. It is
an **information** gap by construction — and it is a **hindsight ceiling**, not a target. The best
*real* preseason ranking available recovers ≤10% of it in one format and −18% in the other.

### 5. How much of that gap is attributable to the decision rule?

**A small, persistent, unresolvable amount.** The structural residual — picks where the oracle's
player scored *no more* and still won — is **4.5–7.9%** of divergences, ~**86–113 points per
draft**, against a detection floor of **172–250**. Independently replicated (D86 ~90, D103 ~91 on a
different slot set). The implied rule effect under perfect information is ~−11/−12, indistinguishable
from zero. **The complementary 92–96% cannot be attributed**, because "the oracle's player scored
more" conflates bad information with unavoidable variance and this instrument cannot separate them.

### 6. How much achievable projection/ranking headroom has been demonstrated?

**None above the floor.** The single best real preseason ranking in the repository, substituted into
Y1's own value scale: **+77.3 target / −132.1 dynasty** season-long, **+48.4 / −202.4** weekly. The
sign flips across formats. The identification advantage that motivated it (2.75 vs 1.95 of 6) did
not transfer. Per-position calibration is structurally incapable of reordering within a position.
The registered training-set arms re-select Y1.

### 7. What has been ruled out?

Ruled out as **mechanisms**, on positive evidence rather than repeated nulls:

- **Per-position monotone calibration** cannot change within-position top-6 identification —
  algebra, not a measurement (D99).
- **`prior_games` / availability-durability** carries no identification signal, and is 0.00 at RB in
  every season (D100) — D69's thread is closed.
- **The historical ECR board is immutable**, so no backtest over 2020–2025 can depend on board
  vintage (D92, 17/17 with a positive control).
- **O1 was never capable of changing pick #1** at any projection error: at an empty roster its term
  is a positive per-position rescale of Y1's, and a positive rescale cannot reorder (D91 §7).
- **A Y1-ranked shortlist re-imports Y1's own K/DST pathology** and cannot be used to cheapen an
  objective that exists to correct it (D87).
- **The superflex boards carry zero K and zero DST rows**, so `legacy_2qb_dynasty` cannot test any
  K/DST mechanism (D90).
- **Draft slots cannot buy statistical power**; seasons bind (D88).

### 8. What has NOT been ruled out?

- **Anything with an effect between ~25 and ~250 points.** That band is the instrument's blind spot
  and it contains every candidate ever proposed. It is *invisible*, not *empty*.
- **Ranking improvements in the untested direction**, since the ladder only degrades.
- **Changes to projection magnitudes / cross-position calibration** — D99's X2/X3 demonstrably move
  first-QB allocation toward the oracle (5.0 → 10.3/11.0 against the oracle's 10.0); they were
  rejected on D68's gates and on power at k = 3, not on the ordering ladder.
- **A second real ranking source.** n = 1.
- **Everything in-season.** No transaction history exists in this database, so waivers, streaming
  and trades are unmeasured, and D86 measured streaming optionality as real and largest at K/DST/TE.

### 9. What is the current strongest unresolved opportunity?

**Measured against the north-star — the value of an individual pick — the strongest unresolved
opportunity is not in the draft at all.** Inside the draft, both levers have been measured and both
sit below the floor: the decision-shaped residual at 86–113 points and the best available
information change at +77/−132. Outside it, the one decision family this project has never been
able to measure is the in-season one, and it is blocked by missing data rather than by a null
result.

Inside the draft, the strongest *remaining* question is the one the instrument cannot currently
answer rather than one it has answered negatively: **can the split between "bad information" and
"unavoidable variance" inside the 92–96% be identified at all?** Until it can, "projections or
variance?" is unresolved, and every estimate of achievable projection headroom is bounded below by
zero and above by a hindsight number.

### 10. What should happen next if we continue Alpha Squad?

Stated as what the evidence implies, not as a product ranking:

- **The draft-layer question should stop being re-asked with the same instrument.** Five season
  clusters cannot resolve the effects that remain, and D88 proved no amount of slots or seeds
  changes that.
- **The binding constraint on the draft question is calendar, not research.** Each additional
  realized season moves k, and with it the floor. Nothing else available moves it.
- **A pre-screen now exists and should gate any future ranking proposal.** D105's validity harness
  measures a candidate's within-position predictive Spearman against realized points *before* any
  draft run. ECR moves it by **+0.024**; the smallest resolvable ladder rung is **−0.035**. A source
  that does not move it materially cannot produce a resolvable draft effect and should not consume
  a phase.
- **If the program continues on decisions rather than on the draft**, the missing transaction
  history is the specific blocker, and acquiring it is a data question with a known answer shape —
  not another objective reformulation.

---

## 11. Recommended disposition of the D86–D106 branch

### **A — consolidate and close the draft-investigation branch; Y1 remains the production baseline.**

**Why A and not C (a methodological flaw requiring another measurement phase).** I looked for one.
The instrument passes all fourteen contract checks; the board vintage reproduces to the hash; the
production trees are untouched; every headline number I could re-derive from the retained artifacts
reproduced exactly; and the two errors I did find (§2) are reporting errors in the narrative that
change no verdict. The one methodological problem the program *did* surface — that regret is
arm-relative — was declared in advance, then observed, then acted on by keeping absolute realized
value as the primary outcome (D106 §6). That is a methodology working, not failing.

**Why A and not B (a specific unresolved draft experiment justified by existing evidence).** For B
to hold, some candidate would need a plausible effect **above** 172–250 points on 5 clusters. None
does:

| candidate | best available estimate of its effect | vs floor |
|---|---|---|
| a better decision rule | ≤ ~86–113 pts/draft (the entire structural residual) | **below** |
| the best real preseason ranking | +77.3 / −132.1 | **below** |
| per-position calibration | 0/30 identification cells; MDE 343–360 at k=3 | **below** |
| any registered training-set arm | Y1 is re-selected | **n/a** |
| an ordering improvement the size of ECR's | Δρ +0.024 against a smallest resolvable rung of −0.035 | **below** |

Running any of these again would produce another unresolved interval at a known cost. **Continuing
to experiment because the results are null is the error this program has spent six phases learning
to avoid.**

**What A means in practice.** Y1 stays production, unchanged and unmodified by any of D85–D106.
The D86–D106 record — with §2's corrections applied and §6/§7's wordings tightened — becomes the
canonical research record for the draft question. The instrument (§8.A) is the asset that survives
the branch.

**Merge disposition (recommendation only; nothing was merged and no PR was created).** The stack is
linear on `origin/main` with one `src/` file changed, all tests green and ruff clean, so merging
`d106-weekly-sensitivity` would land D98–D106 in one linear history and subsume PR #23. That is a
decision for the user, not for this phase.

---

## 12. What would justify reopening the draft investigation

Any **one** of these. Each is stated so it can be checked before a phase is spent, not after.

1. **More independent season clusters.** The floor is 172–250 at k = 5 and is set by the
   between-season SD and `t(k−1)`. Additional realized seasons are the only lever that moves it —
   slots cannot (D88), seeds cannot (D92). At k = 7 the `t` and `√k` terms alone take the target
   `ORACLE − PROD`-class floor from ~172 toward ~130. **This is a calendar dependency, not a
   research one.** When it arrives, the first thing to re-run is the D96 restatement of O1 and
   D104's ECR arm — both currently sit unresolved below the floor rather than refuted.

2. **A ranking source that clears the pre-screen.** A candidate must move **within-position
   predictive Spearman against realized points** by materially more than ECR's **+0.024**, measured
   with D105's existing validity harness **before** any draft run. The ladder's smallest resolvable
   rung is −0.035, and the extrapolated requirement to reach the 86–113-point scale is roughly
   ±0.5. A source failing this pre-screen cannot produce a resolvable effect and should not consume
   a phase.

3. **A projection change that alters magnitudes, not order.** Everything in D105/D106 holds each
   position's value multiset fixed, and everything in D99 is monotone within position. A proposal
   that changes cross-position *magnitudes* in a non-monotone way — the axis on which D99's X2/X3
   demonstrably moved first-QB allocation from rank 5.0 toward the oracle's 10.0 — is **outside the
   span of every experiment run in D99–D106**, and none of their nulls speak to it. It would need
   its own pre-registration and its own power statement.

4. **A way to identify the 92–96%.** If bad information can be separated from unavoidable variance
   inside "the oracle's player simply scored more", the achievable projection headroom becomes
   estimable for the first time, and the ceiling stops being a hindsight number. Today no
   instrument in this repository can do it.

5. **A defect found in the instrument itself.** Specifically: a failure of any of the fourteen
   checks in §5, a change to `models/` or `league/` away from `73b408e9` / `d4cfd00e`, or a board
   vintage that no longer reproduces as `ca3e2d8a…`. Any of these invalidates the numbers above and
   must be resolved before the record is cited again.

6. **Transaction history becoming available.** This does not reopen the *draft* question — it opens
   a different one. Every conclusion in this audit is about the draft. D86 §6 measured streaming
   optionality as real and largest at K/DST/TE, and recorded that its magnitude cannot be pinned
   down without transaction data. That remains true.

**Explicitly NOT grounds for reopening:** another value-base reformulation; a Y4; a lookahead
optimizer; a third scoring objective chosen because the first two produced nulls; further
projection-proxy work on MAE, Spearman, AUC or top-6; or any use of 2026.

---

## 13. Repository status

| | |
|---|---|
| branch | `d106-weekly-sensitivity` |
| HEAD | `397e707` |
| `origin/main` | `277204f` (strict ancestor; 16 commits behind HEAD, 0 ahead) |
| `models/` | `73b408e9bd12daecdd6a2a875e48735319b66aef` — unchanged |
| `league/` | `d4cfd00e31b949c79eda397824a7952bd31f8f9f` — unchanged |
| board vintage | `ca3e2d8af6aa892067c7450095a1c992087f613141e3b36b89b12928713d5f99`, re-derived read-only in this audit |
| tests | **1427 passed**, 44 deselected, exit 0 |
| ruff | clean |
| open PRs | **#23 only** (`d98-ecr-feature-integrity` → `main`); would be subsumed by merging this stack |
| merged in this phase | **nothing** |
| PRs created or modified in this phase | **none** |
| production code changed in this phase | **none** |
| source code changed in this phase | **none** |

---

## Addendum — the cross-format parity confirmation (check 8)

Check 8 **passes on the evidence that already existed** (D96 §4: both formats 50/50 against tier
`H`, plus `TestShippedTierIsProduction` on the offline fixture). The only gap was presentational —
the much-quoted 240/240 pick-state figure is `target_league`-only and had never been re-quoted for
dynasty.

To close that explicitly this audit re-ran the **existing, read-only** `d103_pick_regret.py --mode
parity` over both formats at the default slots (2021–2025 × {1, 4, 7, 10} × 16 rounds = 640 pick
states per the runner's own loop), comparing tier `L0` against tier `H` — a direct pass-through to
`recommend_draft_pick` — at every state.

**Result:**

```
PARITY: L0 vs H over 640 real pick states -- agree 640, DISAGREE 0
```

**640 of 640, zero disagreements, across `target_league` and `dynasty_1qb`.** Every one of the ten
format-seasons completed; the run took ~30 minutes and exited 0 against board vintage
`ca3e2d8a…`. The rollout policy the oracle uses **is** `recommend_draft_pick`, in both shipped
1-QB formats, at every real pick state the instrument reaches — not only at the 240 target-format
states previously quoted.

This is confirmation, not a dependency: check 8 was already carried by D96 §4 and by
`TestShippedTierIsProduction`. What it removes is the need to say "240/240 **in the target
format**" with a caveat attached — the cross-format number now exists.

---

## Appendix — what was re-derived in this audit, and from what

Every figure below was recomputed from the phase's own retained result artifact and compared
against the written record. **All matched unless a correction is noted in §2.**

| phase | artifact | quantities re-derived |
|---|---|---|
| D100 | `d100_rows.json`, `d100_reach.json` | all five methods' overlap / AUC / Spearman; 11W/8T/1L; per-position deltas; `U_games` 0.00 at RB in all five seasons; +0.55 structurally unreachable; mean season delta +3.20; 2023 null |
| D101 | `d101_rows.json` | Y0–Y3 top-6 hit rate, AUC, Spearman, MAE; Y2's four fallback cells; **both** G6 readings per arm and position; Y1−Y0 +0.0313 (7W/5T/4L); Y3−Y1 −0.0104 (5W/6T/5L) |
| D103 | `d103_regret_*.json`, `d103_oracle_y1.json` | regret by phase in both formats × both objectives; worst round 198.3; WEEKLY−SEASONLONG with clustered CIs; oracle-agreement rates (**→ correction C1**); ORACLE_Y1 +795.3 / +717.0 with CIs and 5/5; **regret ÷ slate spread by phase (new)** |
| D104 | `d104_decomposition_season_long.json`, `d104_divergence.json`, `d104_regret_season_long.json` | +77.3 / −132.1 with CIs and W/T/L; +9.7% / −18.4%; 183/320 and 206/320 with phase splits; position-swap counts; first-divergence histogram (**→ correction C2**); Y1 134.8 vs FP_ECR_Y1 139.8; the per-position damage (TE 119.2 → 140.0, K 113.4 → 123.2, DST 116.9 → 123.3) |
| D105 | `d105_value_season_long.json`, `d105_divergence.json`, `d105_validity.json`, `d105_regret_season_long.json` | the full value ladder with CIs and seasons-worse in both formats; **the seed-to-seed SD statistic (159.9 ≈ the quoted 160)**; divergence 0 / 66.2 / 88.4 / 90.6 / 98.4%; Spearman vs Y1 and vs realized at every rung; the regret ladder 126.2 / 137.3 / 228.4 |
| D106 | `d105_value_weekly_no_foresight.json`, `d105_regret_weekly_no_foresight.json` | the weekly value ladder in both formats; FP_ECR_Y1 +48.4 / −202.4; ORACLE_Y1 +767.5 / +671.4; **seed SDs 151.1 and 124.9 (≈ the quoted 151 and 125)**; the non-monotone regret ladder 96.8 / 73.2 / 154.5 and the 4.4% → 8.1% → 1.2% oracle-agreement fingerprint |
