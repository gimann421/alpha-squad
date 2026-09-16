# D108 — Draft-Choice Research Program Closeout (D86–D107)

**Start here.** This is the entry point for anyone picking up the draft question after D108. It
states what was investigated, what was established, what was *not* established, and the exact
conditions under which the question should be reopened.

*Consolidation/audit only. No production draft logic, no `models/`, no `league/`, nothing fitted, no
new experiment, no new ranking source, no Y1 tuning, no PR, nothing merged, no D109.*

---

## 0. The north star, and the discipline it imposes

> **Maximize the value of each individual draft pick** — the best available option given the current
> roster and the remaining player pool, at the beginning, middle **and end** of the draft.

Three categories, which four phases of this program conflated and D102/D104 separated again:

| | category | examples | status |
|---|---|---|---|
| **A** | **Projection/model metrics** | MAE, RMSE, Spearman, AUC, top-6 and top-decile identification | **Diagnostic only.** None is established to be monotone in pick quality — D101 proved they are not even monotone in *each other* (AUC and Spearman rank Y3 first; top-6 hit rate ranks Y1 first) |
| **B** | **The actual product objective** | realized value of the draft's choices, by draft phase | **The target.** Measured as realized starter points under `season_long` and `weekly_no_foresight` |
| **C** | **Bounding diagnostics** | `ORACLE_Y1`, pick-level regret | **Bounds, not targets.** ORACLE_Y1 needs hindsight; regret is a one-step lower-bound instrument and is *arm-relative* |

**A projection metric earns attention only when it demonstrates a downstream draft-value
improvement.** D100 → D104 is the worked counterexample: raw preseason ECR beat M6 on all three
identification metrics (2.75 vs 1.95 of 6, AUC 0.9253 vs 0.8990, ρ 0.7895 vs 0.7670) and then failed
to produce better draft picks (+77.3 target / **−132.1** dynasty, both below the detection floor,
sign flipping across formats, and *worse* at pick-level regret by +5.0).

---

## 1. The canonical conclusion

> **Within the 2021–2025 evaluation population, the two shipped 1-QB roster configurations, the
> information sources tested, and the decision rules tested, no alternative decision-rule or
> preseason-ranking intervention demonstrated a reliably measurable improvement in realized draft
> value over Y1 above the instrument's detection floor of 172–250 points.**

### What this does NOT say

It does not say Y1 is optimal. It does not say Y1 is globally optimal. It does not say the draft is
solved. It does not say projections do not matter. It does not say no possible improvement exists.
It does not say the decision layer cannot be improved. It does not say ECR is useless. It does not
say future projection work is pointless.

### What must travel with it, permanently

- **`ORACLE_Y1` (+795.3 target / +717.0 dynasty, 5/5 seasons) is a hindsight information gap, not an
  achievable improvement.** It replaces projections with realized points. It is an upper bound on
  nothing reachable.
- **The best tested real preseason ranking did not convert its identification advantage into
  demonstrated draft value.** That is a finding about transfer, not about ECR's quality.
- **The decision-shaped residual (~86–113 points per draft) sits below the detection floor.** It is
  a residual under one definition — "the oracle's player scored no more and still won" — not "the
  decision-rule headroom".
- **The ranking-sensitivity ladder demonstrates thresholded robustness, not optimality.** It is
  **degradation-only** (no improvement-side rung), it **holds each position's value multiset fixed**
  (so it tests within-position *ordering* and says nothing about projection *magnitudes*), and it
  was run against **one** real alternative source.
- **The plateau is conditional on the tested environment** — these seasons, these two league
  configurations, these sources, this instrument's resolution.
- **92–96% of pick divergences are "the oracle's player simply scored more", and that share is
  unattributable.** It conflates bad information with unavoidable variance, and no instrument in
  this repository separates them. **No part of it may be quoted as projection error.**

---

## 2. Phase ledger, D86–D107

`Prod?` = changed production (`league/`, `models/`). Every row is NO; `models/` has stood at
`73b408e9` and `league/` at `d4cfd00e` since before D85.

| phase | question | experiment / instrument | primary metric | result | verdict | Prod? | authoritative? | corrected / retracted by |
|---|---|---|---|---|---|---|---|---|
| **D86** | What should Alpha optimize at all? | built `draft_oracle.py` + `weekly_objective.py`; 320 real pick states; candidate O1 | realized starter points; pick regret | bench priced at zero while **17.8%** of realized points come through it; regret 116.2 vs random 122.3; structural residual **16/320 ≈ 90 pts/draft**; O1 target +52.9 | DO NOT SHIP | NO | **partly** | draft numbers **not reproducible** (D92 §5); the O-tier control **was never production** (D93/D94) — so the K/DST mechanism is an artifact. The oracle definition, 17.8%, the ~90-point residual and "no transaction history exists" survive |
| **D87** | Is a candidate shortlist a free speed-up? | O1 with top-K shortlists, 592 pick states | decision-agreement rate | K=10 changes 10.3% of decisions — **0/140 in rounds 1–7, 18.3% in rounds 8–16**; the shortlist is ranked by Y1 and re-imports its K/DST bias | DO NOT SHIP | NO | **method only** | effect sizes not reproducible (D92) |
| **D88** | Does O1 replicate; can slots resolve it? | 4 → 10 slots, full board | paired realized value; MDE | +50.5; **MDE floors at ~56 regardless of slots — seasons bind, not slots** | B | NO | **yes, for the power finding** | its own arithmetic corrected in D89 §6 (floor 51.1); effect sizes not reproducible |
| **D89** | Do six seasons resolve O1? | add 2020 → 6 seasons × 10 slots | paired realized value | **+49.0 CI [+6.5, +91.5]**, 9/9 in-format gates, G7 fails; found two 2020 board defects; added `EmptyMarketBoardError` | B | NO | **NO** | **2020 was never a legal season** (D95/D96) **and** the numbers are not reproducible (D92). Only the guard and the D88 correction survive |
| **D90** | Does the mechanism generalise to a third format? | O1 on `dynasty_1qb`, 120 drafts | paired realized value | mechanism reproduces, magnitude does not (+20.8, CI spans zero); **both superflex boards carry 0 K and 0 DST rows** | B | NO | **board facts only** | 2020-contaminated + not reproducible; the K/DST mechanism itself is an artifact (D93) |
| **D91** | Where does O1's advantage come from? | Track A arithmetic; ablations A1–A3 | decomposition | headline "the board vintage moved" **wrong**; but Y1's bench spread is **0.48 points across six candidates**, availability is inert, and RB closes by algebra | diagnosis | NO | **partly** | headline **RETRACTED by D92 §1** (a counting error). §3, A2's exact reproduction, the slot-count mechanism and §7's algebra stand |
| **D92** | Is the board mutable; is the instrument trustworthy? | four upstream vintages hashed; seed sweep; full retrain | board identity | **17/17 board-seasons identical** with a positive control; the real defect is that **D88/D89/D90 ran from an uncommitted script** | E | NO | **YES, entirely** | — |
| **D93** | Is the O-tier control actually production? | parity of `O0` vs `recommend_draft_pick`; repaired grid | production parity; paired value | **`O0` reproduced production in 0 of 24 cells.** Repaired: target +3.8, dynasty +27.1. **ΔnK −0.67 → −0.03 — the K/DST mechanism was an artifact** | REJECT O1 | NO | **YES** — restated on the legal window in **D96 §3** | its own 6-season headline superseded by D96 §3. **Record is ORPHANED — see §3** |
| **D94** | What survives, measured through production? | 60 paired cells via tier `H`; component ablation | production parity | `O0` unrepaired **0/60**; repaired **50/50**. D85's 5.34×/8.10× **VALID**; D91's degeneracy **VALID**; **every O-tier number in D86–D92 INVALID** | DO NOT SHIP | NO | **YES** | its own exact-tie non-determinism claim **RETRACTED** (D96 §8) — the bug was in D94's own replica. **Record is ORPHANED — see §3** |
| **D95** | Why does every 2020 cell diverge? | traced upstream `fp_page` labels | data contract | **no shipped series has a preseason board before 2021**; an empty board silently turned "best by consensus" into "first alphabetically" | SHIP the contract | **NO** (it is in `market/`, not `league/`/`models/`; 64 real `recommend_draft_pick` calls byte-identical) | **YES** | — |
| **D96** | Does the benchmark match the contract? | window narrowed; runner guard; D93 restated | benchmark config | **2021–2025**; D93 restated (target **+7.0**, dynasty **+30.7**, both CIs spanning zero); D93's repair merged; D94's tie claim retracted | cleanup | NO | **YES** | — |
| **D97** | Where is the engine leaving value? | NAIVE / PROD / ORACLE decomposition | realized roster value | `PROD−NAIVE` **+213.8** vs MDE 179.4; `ORACLE−PROD` +784.6; top-6 identification 23–40%; **MDE 172–250 and cannot be lowered** | close the decision-layer investigation | NO | **YES for the floor, the bias table, the components** | **`ORACLE−PROD` is not clean projection headroom** — it confounds information and rule (D102 §5; identified as ORACLE_Y1 in D103 §6) |
| **D98** | Is the D56 concern live in the feature path? | traced the executed subquery; measured IDP share | feature-value equality | **IDP share 0.0% every season; 0 differing values incl. live 2026**; the naive fix destroys 2020's feature (366 → 0) | FALSE ALARM, close it | NO | **YES** | — |
| **D99** | Can per-position calibration improve identification? | re-ran D68's pre-registered X0–X4 | within-position top-6 overlap | **structurally impossible** — a monotone map cannot reorder within a position: X1/X2/X4 **0/30** cells, X3 1/30 | REJECT | NO | **YES — it is algebra** | — |
| **D100** | Do M6's own features already separate the top 6? | feature-only rankings + retrained negative control | top-6 overlap, AUC, Spearman | **M6 1.950 vs raw ECR 2.750**; 11W/8T/1L; `prior_games` anti-signal (0.00 at RB every season); no comparison survives Bonferroni | B | NO | **as a diagnostic only** | value-relevance **retired by D104 §6** — identification did not transfer to picks |
| **D101** | Do the registered arms beat Y1 on identification? | re-ran Y0–Y3 unchanged + identification | top-6 hit rate, with the seven gates | **D78's "Y3 passes all seven gates" does NOT reproduce — Y3 fails G6 at WR**; Y1 best on hit rate (0.3750); AUC/Spearman disagree | DO NOT SHIP; **Y1 re-selected** | NO | **YES** | it corrects **D78**; cause of the non-reproduction unresolved (pre-D78 DB gone) |
| **D102** | Is the research objective itself right? | definition phase; no code | — | the pick-level metric **already existed** (D86) and was scored with the objective D86 disproved; `ORACLE_Y1` named as the missing 2×2 cell; **hierarchy fixed: projection metrics are DIAGNOSTIC** | definition | NO | **YES for the hierarchy and the ORACLE_Y1 design** | **two of its own claims refuted by D103** — late regret is not degenerate (107.4), and the hedging interaction is ~−11, not large |
| **D103** | What is pick quality, by draft phase? | `audit_draft` with a selectable objective; `L0 == H` pinned | **pick-level regret** + realized value | regret **181.5 early / 107.4 late** (target SL); weekly **reduces** regret everywhere; structural residual **~91/draft**; **ORACLE_Y1 +795.3 / +717.0** | D — NOT CONFIRMED | NO (instrument only) | **YES** | "0% of rounds 1–5 in both formats" is **target-only** (D107 §2 C1, re-verified D108); absolute-vs-normalised reframing added in D107 §4.B |
| **D104** | Does the best real preseason ranking help? | `ecr_ordered_static` — ECR order, Y1's own values, multiset preserved | realized draft value | **+77.3 / −132.1**, both below the floor, **sign flips**; 57–64% of picks change; pick regret **worse** by +5.0 | B — SMALL / UNCERTAIN | NO (**no `src/` change at all**) | **YES for the null and for §6's transfer finding** | "first divergence round 1 in 20/20" → **11/20** (D107 §2 C2); **"the problem is NOT projections" too strong** (D107 §6.1); **"the objective is FLAT" retracted in D105 §6** |
| **D105** | Is the objective actually sensitive? | α-ladder of within-position scrambles, value multiset fixed | realized draft value | **thresholded, not flat**: 88% of picks change for **−46.5**; a full scramble costs **−565.8** (5/5, CI excludes zero); **ECR moves predictive ρ by +0.024** vs a smallest rung of −0.035 | B — ROBUST | NO (**no `src/` change at all**) | **YES** | retracts D104's flatness hypothesis; its own ±0.5 requirement is labelled an **extrapolation** |
| **D106** | Does the plateau survive the weekly objective? | same ladder, `weekly_no_foresight` | realized draft value | **H1 in both formats**; weekly makes the threshold **sharper** (endpoint +9.8% / +14.1%); **ECR gets worse** (+48.4 / −202.4) | H1; stop the branch | NO (one argparse constraint in a research script) | **YES** | its **matched regret ladder self-invalidated** — non-monotone and contradicting the value curve, because scrambling degrades the *oracle* too. **Regret must not compare arms drafting from different boards** |
| **D107** | Does the record hold up? | re-derivation from every retained artifact; 14 instrument checks | reproduction | **everything reproduced exactly**; 14/14 checks pass; **two corrections issued**; 640/640 L0-vs-`H` parity | consolidate | NO (**no `src/` change at all**) | **YES** | D108 found it **missed the orphaned D93/D94 record** and did not run `ruff format --check` |

---

## 3. What D108 found that D107 did not

### 3.1 The D93/D94 record is orphaned, and it retracts a D86–D92 headline

`claude/o1-advantage-attribution-azp7k7` holds **8 commits not in HEAD** (`40b30ef…d94786c`) carrying
`docs/D93_O1_REPLICATION_POWER.md` (763 lines), a `## D93` entry, a `## D94` entry and a
PROJECT_STATE M45 block. Their **code** reached `main` — the dispatch repair and the market contract
were re-landed by D95 (`91325d2`) and D96 (`9851eb4`), verified identical — but the **writing never
did**, which is why `DECISIONS.md` jumps D92 → D95. D107 noticed the missing entries; it did not
find that the record still exists.

That gap hides a retraction. D93's Phase 0 found tier `O0` — documented as "the shipped Y1 engine,
byte-identical to L0/Q0/Z0" — reproduced production in **0 of 24 cells** (D94: **0 of 60**), because
`_pick_by_tier`'s draft-aware dispatch omitted `O_TIERS`. **Every O-tier number in D86–D92, control
and candidate alike, was measured against a control that was never production**, and the K/DST
mechanism those phases describe was substantially an artifact: ΔnK **−0.67 → −0.03** on repair,
capacity breaches 62 → 2, production already drafting to kicker capacity.

Forward pointers were added at the D86 entry head and at the D92 → D95 boundary. **Recommended:**
preserve that branch; a future hygiene pass may cherry-pick its three doc-only commits. D108 does
not merge.

### 3.2 A `make lint` regression the stack introduced

Every phase D98–D107 reported "ruff clean" having run `ruff check` alone. **`make lint` also runs
`ruff format --check src tests`** — and that half was never run. `origin/main` passes both; HEAD
failed with **4 files**, all created or modified by this stack. Fixed by running `ruff format` on
exactly those four; **each file's AST is identical before and after**, so nothing but whitespace
moved. No production file and no `scripts/` file (outside the gate's scope) was touched. The guard
already existed — it was simply not the command being run. **Future phases should run `make lint`.**

---

## 4. Reopening criteria

Reopen the draft-choice question only if **at least one** of these occurs. Each is checkable before
a phase is spent.

1. **Substantially more independent season clusters**, lowering the 172–250 detection floor. This is
   the only lever that moves it: slots provably cannot (D88), seeds provably cannot (D92). A
   calendar dependency, not a research one.
2. **A pre-screened information source** that materially changes within-position predictive
   ordering — measured against realized points with D105's existing validity harness **before** any
   draft run. The benchmark: ECR moved it by **+0.024**; the ladder's smallest resolvable rung is
   **−0.035**.
3. **A projection change that alters value magnitudes rather than merely reordering players.** No
   D99–D106 experiment spans this axis: D99 tested only monotone (non-reordering) maps, and
   D105/D106 hold each position's value multiset fixed. D97's +65.2 QB top-6 bias and D99's X2/X3
   arms live here.
4. **A method that identifies the ORACLE_Y1 "scored more" gap in a preseason-available way** —
   splitting the unattributable 92–96%.
5. **Failure of any instrument-integrity check**: the 14 checks in D107 §5, a drift of `models/` or
   `league/` off `73b408e9` / `d4cfd00e`, or a board vintage that no longer reproduces as
   `ca3e2d8a…`.
6. **Materially new draft/roster information.**
7. **Transaction/waiver history becoming available** — which is a **new total-roster-value
   question**, not a continuation of this draft-only one. Every conclusion here is about the draft.
   D86 §6 measured streaming optionality as real and largest at K/DST/TE and recorded that its
   magnitude cannot be sized without that data.

**Explicitly NOT grounds:** another value base; a Y4; a lookahead optimizer; a third scoring
objective chosen because the first two produced nulls; further projection-proxy work on MAE,
Spearman, AUC or top-6; or any use of 2026.

---

## 5. Repository state at closeout

| | |
|---|---|
| branch / HEAD | `d107-research-consolidation-audit` → the D108 commit on `d108-program-closeout` |
| `origin/main` | `277204f` — a **strict ancestor**, 0 commits ahead |
| stack shape | **linear, zero merge commits**; every per-phase remote branch is an exact ancestor of HEAD |
| `models/` | `73b408e9bd12daecdd6a2a875e48735319b66aef` — unchanged since before D85 |
| `league/` | `d4cfd00e31b949c79eda397824a7952bd31f8f9f` — unchanged since before D85 |
| only `src/` change in D98–D108 | `evaluation/draft_oracle.py` (D103's instrument; imported by no production path) |
| board vintage | `ca3e2d8af6aa892067c7450095a1c992087f613141e3b36b89b12928713d5f99` |
| tests | 1427 passed, 44 deselected |
| `ruff check src tests` | clean |
| `ruff format --check src tests` | **clean** (was 4 files failing before D108) |
| open PRs | **#23 only** — head `be7105c` is this stack's first commit and an ancestor of HEAD |
| merged in D108 | **nothing** |
| D109 | **not started** |
