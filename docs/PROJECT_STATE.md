# Project State

Living summary of what is implemented, validated, and outstanding. Updated at the end of every
milestone. See `docs/TRACEABILITY.md` for the acceptance-criteria-level mapping.

## Status: M30 complete — **D67/W1 remains production; no calibration of any kind has shipped.** D67 put draft-aware replacement level at the demand a draft actually consumes, and **Alpha leads fair market consensus on the official benchmark for the first time on this format (2061.3 vs 2034.8, +26.5), but the margin is inside noise**. D68 tested broad positional calibration and **rejected every arm**; D69 assessed the RB-only calibration follow-up and **abandoned it before implementation**; **D70 implemented and ran D69's own recommended follow-up — RB availability FEATURES (not a calibration) — and it also failed its pre-registered gates**: B1 (accuracy) and B2 (the targeted RB bias falls) both FAIL, with B2 the decisive one — the treatment made the RB signed bias *larger*, not smaller, in all three treated seasons (2023 +22.1 vs control +16.9, 2024 +44.7 vs +44.4, 2025 +26.9 vs +23.5). B3 (availability predicts realized games, out of fold) passed but only weakly and trending toward zero (+0.23 → +0.18 → +0.05). Per protocol the draft layer was never run. **P1-0 remains OPEN.** Both of D69's proposed paths (RB-only calibration, RB availability features) are now closed; no further RB-specific mechanism is currently proposed, and any future one needs its own pre-registration. M13 complete; M14 post-audit hardening (D41-D52) except P2-3 (needs a user credential decision); M15 productization (D53); M16-M19 evaluation, draft forensics, opportunity cost, 1-QB retarget (D54-D60); M20 benchmark artifact found (D61); M21 measurement fixed (D62); M22 shipped `msv + VORP` (D63); M23 rejected two kicker fixes (D64); M24 proved static replacement is a causal defect (D65); M25 found demand DEPTH is the governing parameter (D66); M26 replaced the depth multiplier with a derived demand target and shipped it (D67). **P1-0 remains OPEN**: the +26.5 lead has 95% CI [−38.0, +91.0] and W/L 28/22, and it falls to +3.1 with 2022 removed. Roster construction is sound (0/50 unfilled mandatory slots, no zero-K/zero-DEF roster, every roster exactly 16) and the run is deterministic across two processes. The residual gap is diagnosed and sits **upstream of the draft engine**: Alpha loses RB starter points in all five seasons (mean −247.7) and wins WR in all five (+183.2), because M6 under-projects RB in 4 of 5 seasons (+38.0 in 2024, the one season Alpha loses) and over-projects WR/QB. **D68 ran that walk-forward positional calibration and rejected every arm** (M27): all five pre-registered forms improve raw accuracy (MAE 63.3 → 61.8-62.9) but none clears the pre-registered gates, because RB is the ONLY position whose walk-forward bias estimate is sign-stable (+2.5/+8.0/+16.9/+44.4 across 2021-2024) while QB, WR and TE all flip sign between seasons and are corrected in the wrong direction. Nothing shipped; production is byte-identical to D67. The draft layer was not run, per the committed protocol that an arm failing the projection layer never reaches it. **D69 then assessed the RB-only arm D68 had deferred, and abandoned it before implementation** (M28): RB's sign stability holds for the mean but not the median or trimmed mean (2021 median −12.3, trimmed −1.5); magnitude is not usefully forecastable walk-forward (best predictor MAE 16.3 against a 14.4 SD of the truths and an ~11.2 oracle); the residual's leading — **not demonstrated** — explanation is an association with an RB-specific availability measure that has been trending (corr with games played +0.70 to +0.80 every season, RB mean games 11.67→14.19→13.83, RB-specific vs WR +0.35 / QB −0.04), which a backward-looking estimator lags; and a uniform additive RB shift leaves `draft_aware_vorp` **invariant by construction** (measured ΔVORP exactly 0.00), moving only 0–2 of the top-20 pick-1 board slots against a −247.7/season deficit. Winner's-curse / projection-rank conditioning and a market-varying universe remain unresolved alternatives. Nothing shipped, nothing fitted, no benchmark run. **D71 (M30)** then audited the benchmark's own inferential structure, read-only, no new simulation: the 50 trials are a deterministic `(season × slot)` cross-product sharing one projection set and one market board per season, so the true experimental unit is the season — **n=5, not n=50** (10 per-season rosters overlap 53-73%, ICC 0.0995). The season-clustered 95% CI is **[−100.4, +153.4]** (df=4) — wider than the naive-iid **[−38.0, +91.0]** D67 published, which assumed 50 independent draws. Resolving the +26.5 effect would need **~116 seasons** at current precision, or **~61 even under a hypothetically perfect within-season measurement** — against a season universe hard-bounded at 2021+ (`market_snapshot` has no `ro`/`redraft-overall` preseason rows before 2021) and growing by one season per year. **P1-0 is therefore split**: **P1-0a** (the item's original roster-balance defect) is **CLOSED** — `alpha_league_aware` has 0/50 unfilled mandatory slots, every roster exactly 16, vs 327/50 for `alpha_bpa` — while **P1-0b** (absolute superiority vs. fair consensus) stays **OPEN**, reclassified from "the next experiment should close it" to a standing measurement limitation, not a blocking gate. Future engine-change evaluation uses a variant-vs-control contrast on identical trials instead — the instrument D65's Candidate C already used successfully (CI [+2.3, +44.1]). No RB/WR/QB work reopened; no code, model, or production change.

| Milestone | Status | Notes |
|---|---|---|
| M0 Bootstrap | DONE | project skeleton, deps, docs |
| M1 Sources + snapshots | DONE | 7 adapters (4 available, 3 blocked/no-creds), all verified live; 25 offline + 6 network tests passing; one real bug found and fixed in review (see below) |
| M2 Canonical identity | DONE | player_id spine (25,046 players) + 25 crosswalk ID types + college bridge, all verified against live data; 43 offline + 8 network tests passing; three real bugs found and fixed in review (see below) |
| M3 As-of features + leakage | DONE | games/player_week_stats/player_week_features (199,632 rows over 2015-2025, built in ~7s from cache); leakage-safe by construction via SQL window frames; 51 offline (incl. 12 leakage tests with independent Python recomputation) + 9 network tests passing |
| M4 Baselines + evaluation | DONE | 3 baselines (previous-year, weighted-2yr, ECR-implied) walk-forward evaluated 2018-2025 against 21,421 real player-seasons and 210,730 real market snapshots; shared evaluation harness (MAE/RMSE/R²/Spearman/top-N hit rate/tier accuracy) reused by every later milestone; 65 offline + 10 network tests passing. **One number in this milestone's report was wrong and got corrected in M5 — see D19.** |
| M5 Established-player ML | DONE | Position-specific Ridge/CatBoost/XGBoost + opportunity-only + team-environment-only + ensemble, both weekly (in-season) and season-level (preseason, apples-to-apples vs M4); team_week_stats/features extend the M3 panel; model_registry tracks version/validation; 70 offline + 12 network tests passing. One real evaluation-harness bug found and fixed (D19), affecting M4's reports too. |
| M6 Uncertainty + calibration | DONE | Split-conformal p10/p25/median/p75/p90 + Monte Carlo top-12/24 probabilities on the M5 season-level CatBoost model; walk-forward 3-way split (train/calibrate/target) so calibration is genuinely out-of-sample; real measured coverage_10_90 mostly 0.72-0.90 (target 0.80) across 2019-2025/QB-RB-WR-TE — legitimately well-calibrated, not just plausible-looking; 82 offline + 13 network tests passing |
| M7 Rookie/prospect intelligence | DONE | Draft capital + combine + prior-season landing-spot features (college production LIMITED — D20 found no verified ID bridge to cfbfastR; D38 built a real CFBD/espn_id-bridged one, and **D39 measured it and did not adopt it** — neutral-to-worse on every metric, so the production feature set stays at the 12-feature D20 baseline); CatBoost regression (rookie-year PPR) + classifier (top-24 breakout, Brier-scored) walk-forward by draft class; nearest-neighbor historical comps; 1,077 real rookie-seasons, 88 offline + 15 network tests passing; two real bugs found and fixed (combine height stored as "6-0" string, comps dtype crash) |
| M8 Market + EDGE | DONE | market_snapshot extended to ro/do/rsf/dsf (2QB-aware); dynasty_values (681 real players, 97.6% identity coverage); EDGE (rank/points/probability edge, BUY/HOLD/SELL/WATCH) gated so a raw rank discrepancy alone can never produce BUY/SELL (D21); historical EDGE validation shows the real BUY cohort beat market-implied points in 3 of 4 scored seasons 2022-2025 (recomputed in M13 after a data-correctness fix — see D28 — numbers below reflect the M13-era figures); 102 offline + 18 network tests passing (both suites reran clean end-to-end after this milestone) |
| M9 Evidence engine | DONE | 4 real Strong-tier detectors (depth-chart move, injury self/teammate-opportunity, roster transaction, usage-share shift) on officially-sourced nflverse data; 33,311 real events across 2019-2025; bounded (±15%) evidence-adjusted weekly projections, never overwriting the base M5 prediction; wired as a real (mostly-neutral-in-practice) veto into M8's EDGE gate (D23); 123 offline + 21 network tests passing (verified via `pytest -m "not network"` / `-m network` directly, not estimated) |
| M10 League decision engine | DONE | Real value-based-drafting replacement/scarcity derived from the league's own lineup config (verified: 2QB target league produces 20 real dedicated QB starters on real 2025 data, exactly 10 teams x 2 QB slots); draft/waiver/dynasty-trade recommendations with alternatives, roster fit, next-pick survival probability, and real evidence-driven value-spike bidding; the M7 rookie-prediction fallback was confirmed live against a real rookie-only player; 152 offline + 26 network tests passing |
| M11 Agents/orchestrator | DONE | Pydantic Task/Result/Evidence/Prediction/Edge/Decision contracts mirroring AGENT_CONTRACTS.md; 9 real agents (thin wrappers around already-validated M1-M10 code, never an LLM call, D14); DAG orchestrator with real dependency resolution, retry/backoff, and genuinely concurrent scheduling (proven: two independent tasks start within 0.2s of each other) with DB-write serialization for correctness; disagreement protocol reusing real M8/M4-M5 data (296 real disagreements detected on 2024/2025 data, both positions always preserved); a real DuckDB concurrent-DDL bug was found and fixed via the orchestrator's own test suite (D26); 172 offline + 29 network tests passing |
| M12 API + frontend | DONE | FastAPI over the real M1-M11 pipeline (8 routers, every field a direct projection of an already-persisted table or an M10 function call, zero parallel logic); React+Vite+TS SPA (6 real, live-data views); verified end-to-end in a real Chromium browser via Playwright against real persisted data, including the literal Gate 8 test (killed the API process, reloaded, confirmed a real fetch error rather than stale/fabricated content); 189 offline + 33 network tests passing |
| M13 Hardening | DONE | correlated team-season Monte Carlo simulation (D8 deferred item, `models/simulation/`); found and fixed a real cross-cutting data bug affecting M4-M10 (postseason games silently pooled into every "season" aggregate since M3, D28) — rebuilt the affected tables and retrained every downstream model; found and fixed two simulation-design bugs (QB anchored to the wrong shared variable, a share-denominator mismatch, D29) plus a real RNG-reproducibility bug; fixed a stale README/Makefile and added CI (D30); wrote docs/TRACEABILITY.md; 204 offline + 37 network tests passing |
| M14 Post-audit hardening | IN PROGRESS | Working the `docs/CURRENT_STATE_AUDIT.md`/`docs/IMPLEMENTATION_GAP_ANALYSIS.md` P0-P3 backlog. **P0** (security): D35's history-rewrite decision was already made and declined by the user at the time -- not reopened; added a durable CI guardrail (`scripts/check_no_secrets.py`, D42) instead. **P1-1** (UI wiring, D44): waiver/trade/roster-need wired into the SPA, live-verified against a real Sleeper league. **P1-2** (EDGE backtest, D41): `alpha-squad edge backtest` + `reports/edge_backtest.md`, real per-position/bucket breakdown, BUY beat market in all 4 scored seasons 2022-2025. **P1-3** (model persistence, D43): `models/persistence.py` closes the audit's single biggest architectural finding (no model was ever saved to disk) for the two paths that actually serve live predictions (uncertainty → `/rankings`, rookie projection → `/rookies`); verified against the real database. **P2** (dynasty future-pick valuation, D45): `pick_value`/`evaluate_trade_package`, a documented heuristic anchored to real `dynasty_values` data, verified live. **P4+P5 together** (evidence → served intelligence + in-season/ROS, D46): re-read PRODUCT_SPEC.md/ARCHITECTURE.md to confirm evidence should reach served output (not just gate EDGE); ran the real weekly established-ML pipeline (never before executed in this deployment) and the evidence-adjustment pass against real 2025 data, then added `GET /rankings/weekly` + a UI mode — verified live in a real browser with a real evidence-driven adjustment rendered. **P7** (orchestrator task decomposition, D47): `agents/planner.py::plan_full_refresh` builds the real multi-stage task graph from a high-level goal (agent selection + correct dependency edges, read off what each agent's code actually queries/writes) instead of every caller hand-typing one; `alpha-squad orchestrate run` verified against the real database with genuine `rookie_ml`/`projection_ml` concurrency and correct `market_edge` ordering. **P8** (application hardening, D48): `GET /seasons/latest` + a shared `useLatestSeason` hook so every view defaults to the real newest season instead of a hardcoded one; `PlayerPicker.tsx` makes the previously-dead `GET /players` reachable from Waiver/Trade, fixing a real HTML `<label>`-click-forwarding bug found live. **P1-4** (simulation UI, D49): `POST /simulate/team-season` + `SimulationView.tsx` — the last of the four "built but invisible" capabilities (waiver/trade/roster-need/simulation) identified at the start of this hardening pass, now all closed. Verifying it live surfaced and fixed a real gap: `team_week_points` was empty in this deployment because `build_team_week_points` had never been wired to a CLI command; added `alpha-squad features build-team-scores` and ran it for real (7,326 rows). 303 offline tests passing (up from 262 at audit time). **P3-1** (stale CLAUDE.md data-source note, D50): re-verified live against a fresh `alpha-squad sources status` run (Sleeper/FantasyPros/CFBD all AVAILABLE) and rewrote the note to match `docs/DATA_SOURCES.md`. **P3-2** (expert-accuracy weighting, D51): re-confirmed live that even the paid FantasyPros API exposes only consensus statistics, never per-expert identity; measured the coarser proxy the data does permit (`ecr_best`/`ecr_worst` dispersion) against 1,925 real player-seasons and found no consistent relationship with market accuracy (reverses sign between rank tiers) — not adopted, per the same measure-and-reject standard D39 established. Remaining backlog: P2-3 (network suite in CI), which needs a user credential decision and is the only item left that isn't autonomously actionable. **Final validation** (D52): re-ran the full live/network integration suite against real external services after the whole pass — 41 passed, 1 pre-existing skip, 0 failures — reconfirming every live-source claim made across D41-D51, not just trusting nothing broke. |
| M26 Draft-aware replacement | DONE | D67. Plan-mode diagnostics refuted D66's own recommendation: a uniform demand-depth multiplier is a positional re-weighting whose effect size is set by projection-tail shape (at x2.5 it hands RB +120.4/QB +108.9/TE +106.4/WR +92.0 but K only +30.4 and DST +10.7, because there are ~225 WRs and exactly 32 DSTs). Replaced it with a target that has no free parameter — the demand one mock draft of this league on the preseason consensus board actually consumes, summing to `roster_size` by construction. Pre-registered W0-W4 in git before running; W1 cleared every gate (+32.1 over N4, CI [+11.5,+52.7], LOSO positive on all five, cap breaches 34->1) and beat the D66 x2.5 reference (+26.7) on both the primary metric and out-of-format (+75.5 vs +65.6 on `legacy_2qb_dynasty`). W3 proved the roster-legality constraint contributes exactly 0.0 — it never fires — so it did not ship. Official benchmark: **-5.6 -> +26.5 vs fair consensus**, 4 of 5 seasons won, deterministic across two processes, but not statistically significant. Also fixed a real bug this change introduced (a client shortlist read as a draft board collapses every position's demand to zero) with two structural guards, both verified byte-identical on real data. |
| M27 Projection calibration | DONE — nothing shipped | D68: five pre-registered walk-forward calibration arms (none / additive / affine / rank-band / EB-shrunk) measured on the projection layer over treated seasons 2023-2025. Every arm improves MAE and RMSE; **no arm clears gates G1-G4**. RB's bias is sign-stable and falls under every arm; QB/WR/TE flip sign between seasons, and every G3 failure is at TE or WR. Leakage guard is structural (`fit_arm` raises on a training row at or after the target season). 55 new unit tests. Production untouched: `league/draft.py` byte-identical to D67. P1-0 unchanged and still OPEN. |
| M28 RB calibration assessment | DONE — abandoned, nothing implemented | D69: assessed the RB-only arm D68 deferred, and abandoned it **before implementation**. No estimator was fitted, no arm was run, no draft-layer or benchmark experiment was executed. Grounds: (1) RB sign stability is a mean-only property — 2021 median −12.3, 10%-trimmed −1.5, and the mean itself flips at a top-40 cut in 2022; (2) magnitude is not usefully forecastable walk-forward (best predictor MAE 16.3 vs 14.4 SD of the truths and ~11.2 for an oracle constant); (3) the leading **but not demonstrated** mechanism is an association with an RB-specific availability trend (corr +0.70–0.80 with games played every season; RB mean games +2.52 over 2021→2024 vs WR +0.35, QB −0.04), which a backward-looking estimator lags and which already reversed in 2025; (4) the W1 engine is near-inert to the only supported form — a uniform additive RB shift moves the RB replacement level by the identical amount, so ΔVORP is exactly 0.00 and only 0–2 of the top-20 pick-1 slots change. Winner's-curse / projection-rank conditioning, a market-varying universe, and regime change remain open alternatives. Replaced by a design-only pre-registration for RB availability modelling (`docs/RB_AVAILABILITY_PREREGISTRATION.md`). Production byte-identical to D67. P1-0 unchanged and still OPEN. |
| M29 RB availability features | DONE — tested, rejected, nothing shipped | D70: implemented exactly D69's own recommended follow-up (four preseason-knowable features -- prior-3-season games history, age, position-cohort games baseline, prior-season workload -- appended to M6 for RB only, QB/WR/TE/K/DST untouched). Committed before fitting, same protocol as D67/D68/D69. A real population bug (RB universe collapsed to n=3 by ranking across all positions) was found and fixed BEFORE any valid gate result existed, same category as D68's shrinkage fix. Final, correct result: **B1 (accuracy) and B2 (targeted bias falls) both FAIL** -- RMSE marginally worse (88.60 vs 88.08) and, decisively, the RB signed bias grew larger under treatment in ALL THREE treated seasons rather than shrinking. B3 (availability predicts realized games out-of-fold) passed but weakly and declining (+0.226/+0.176/+0.051 across 2023-2025) -- a materially harder and more honest test than D69's own within-season correlation (+0.70-0.80), and the gap between them is itself informative. Per the pre-registered protocol the draft layer (B4-B9) was never run. Nothing shipped: `league/draft.py`, `league/replacement.py`, `models/uncertainty/run.py` byte-identical to D67. 52 new tests total across D70. P1-0 unchanged and still OPEN. Both of D69's proposed RB paths (calibration, features) are now closed. |
| M30 Benchmark power/variance re-specification | DONE — docs only, no code/model/simulation change | D71: read-only audit of why D61-D70's CI-excludes-zero gate on P1-0 has not moved in nine cycles. Found the 50 `draft_simulation_results` trials are a deterministic `(season x slot)` cross-product, not 50 iid draws -- within a season all 10 slots share one projection set and market board, and Alpha's 10 per-season rosters overlap 53-73% (ICC 0.0995, effective n ~26; the honest unit is the season, n=5). D67's published CI [-38.0,+91.0] is the naive-iid interval; the season-clustered CI is the wider [-100.4,+153.4] (df=4) -- a correction, not a relaxation. Resolving +26.5 needs ~116 seasons at current precision or ~61 even with a hypothetically perfect within-season measurement, against a season universe hard-bounded at 2021+ (`market_snapshot` has no `ro`/`redraft-overall` Jul/Aug rows before 2021) growing 1/year -- no additional slots, reruns, or historical seasons can supply it. **P1-0 split**: P1-0a (roster-balance defect) CLOSED on 0/50 unfilled mandatory slots; P1-0b (absolute superiority) stays OPEN, reclassified as a standing measurement limitation rather than a blocking gate. Future engine work evaluated by variant-vs-control contrast on identical trials instead (D65 Candidate C precedent: CI [+2.3,+44.1]). No RB/WR/QB work reopened; `league/draft.py` untouched. Full account: `docs/DECISIONS.md` D71. |
| M16 Empirical validation | DONE | 8 evaluation modules; headline result unfavourable and reported as such (D54). |
| M17 Draft-engine forensic audit | DONE | Diagnostic only; 400-draft tier ablation; `positional_scarcity` measured and rejected. |
| M18 Positional opportunity cost | DONE | D55; +112.9 starter pts; RB=0 10/50 → 2/50. |
| M19 1-QB format retarget | DONE | D56-D60; market-series fix, K/DST data, flex-aware capacity, marginal starter value shipped. **Its headline benchmark claim is retracted at D61.** |
| M20 Draft-strategy forensics | DONE | D61. Found the benchmark's consensus opponent forfeits its K and DEF starting slots (worth +245.3 pts, more than the whole margin); against a fair opponent Alpha is −48.3, 25/50 (simulated estimate). Diagnosed the mechanism (MSV replacing VORP discards positional scarcity: 68% round-2 QB, first RB at round 5.24, DST at round 10 in 100% of drafts). Found two measurement defects (forensic feasibility cap ≠ production; attribution measured the wrong engine). No engine change made — see `docs/DRAFT_STRATEGY_NEXT_PHASE_PLAN.md`. |
| M21 Stage 1 measurement fix | DONE | D62. Shipped the roster-aware consensus opponent (`market_consensus_roster_aware`, both opponents reported side by side, kept `market_consensus` byte-identical), reconciled the forensic/production feasibility caps, fixed `pick_attribution.py` to measure the shipped D60 engine, and scoped `next_pick_survival_probability` by `page_type`. Re-ran the official benchmark on real 2021-2025 data (500 drafts): Alpha vs the fair opponent, measured directly (not simulated) — **−45.4 starter pts, 25/50, 95% CI [−117.1, +25.6] includes zero** — confirming D61's simulated estimate to within 3 points. Determinism verified byte-identical across two separate processes. Stage 2/3 of `docs/DRAFT_STRATEGY_NEXT_PHASE_PLAN.md` not started. |
| M22 Value-base ablation | DONE | D63. Stage 2: found the forensic harness still ran the pre-D61 unaware opponent; fixed, then re-ran the M-tiers. MSV does beat VORP undistorted (+62.6), but the Stage 1.2 cap fix flipped the M-tier ranking — M1 (vorp+msv) 2029.2 now leads M3 (msv) 1989.3, so D60 selected the wrong tier under the diverged caps. Stage 3: 500-draft N-tier ablation under a rule pre-registered in git before any run. Winner N4 = `msv + 1.0*VORP`, +39.9 over the shipped formula, CI [+9.1,+70.6], 37/50, all four gates passed, survives leave-one-season-out. Both clamping alternatives LOST (min -46.9, msv-over-replacement -48.6). Opportunity cost re-measured and kept (helps significantly on 3 of 5 bases). Official benchmark: -45.4 -> **-5.6** vs fair consensus, floor up 1570->1765, stdev 160.8->131.7. Known regression reported: the blend over-drafts kickers (K cap breached in 32/50 drafts), which no pre-registered gate checks. |
| M23 Kicker-hoarding refinement | DONE (no change shipped) | D64. Traced a real hoarding draft pick-by-pick and found the documented diagnosis only partly right: late in a draft MSV is 0 for every candidate, so the value base collapses to VORP, and VORP's STATIC league-wide replacement level makes stripped skill pools look below-replacement (RB -135.6, WR -123.0) while the untouched kicker pool stays above it (+30.1). Flex-eligibility is the second-order cause. Hypothesis B (tighter over-cap multiplier) is provably inert -- the 2nd kicker is taken while UNDER the cap, and margin was exactly +0.0 with a 0/0 W/L record. Hypothesis A (saturate the VORP surplus) lost 32.9 pts and swapped kicker hoarding for QB hoarding; its repaired form R4 fixed roster shape dramatically (breaches 34->4, K 2.74->1.12, RB 2.20->4.00) but scored only +1.3 (CI [-32.0,+34.6]) while LOSING 27 of 50 drafts, failing Gate 3, LOSO and the new Gate 5. **N4 kept; production unchanged.** Next step identified: draft-aware replacement levels. |
| M24 Draft-aware replacement study | DONE (no change shipped) | D65. Confirmed in code that `available_player_ids` never reaches the VORP calculation, so the replacement level is constant across a draft. Quantified the staleness on real data: at round 13 the static level is +178 too high for QB and +69 for WR but only +2.2 for K -- the engine under-values skill positions rather than over-valuing kickers. MSV hits 0.0 at round 11 in all four traced drafts; rounds 11-16 carry 16.1% of realized starter points. Also disproved D64's premise: the 2nd kicker is worth +27.4 pts (17/18 drafts) but the 3rd/4th are worth EXACTLY 0.0 (0/32), capping any kicker-driven gain at ~+4.7 -- inside the noise. Tested three draft-aware definitions; **Candidate C (hybrid capacity) gained +23.2 over N4, CI [+2.3,+44.1], LOSO-robust on all 5 seasons, zero cap breaches, and reached +17.6 vs fair consensus** -- the first positive number ever measured. Not shipped: Gate 3 fails (worse in 2 of 5 seasons; loses 0/10 in 2024), traced to a systematic TE-to-capacity loading whose payoff is season-dependent. Next: pre-registered phase on Candidate C's demand target. |
| M25 Demand-target refinement | DONE (no change shipped) | D66. Found why C3 loads TEs: `startable_slots` counts each FLEX slot once per ELIGIBLE position, summing to 14/team against a 10-starter lineup, so C2/C3 demand 140/220 league-wide players for 100 real slots. Measured: WR wins all 20 flex slots in all 5 seasons, TE wins zero, so true TE demand is 1.00/team vs C3's 4. **The obvious fix was wrong**: both pre-registered repairs lost badly (C5 earned-starter -37.2 with the WORST breaches at 60; C4 ded+1bench -52.4), because a shallow demand target exhausts (C5: 17% of picks) and collapses VORP to zero. The flex over-count was acting as a depth buffer. A 1-D sweep on demand depth shows a **broad plateau** (every scale >=1.5 beats N4) with a structural threshold (demand must exceed the 160 picks a draft consumes, scale >1.14). **Scales x2.5 and x3.0 pass EVERY gate** (+26.7/+28.2, CIs excluding zero, LOSO positive on all 5 seasons, 0 cap breaches, K 1.74->0.00 in late rounds). x2.5 generalizes out-of-format: +65.6 (CI [+31.8,+99.5]) on legacy_2qb_dynasty. Caveat: the passing scale was selected post-hoc from a 6-point sweep. Next: pre-register a scale on the structural criterion and run the official benchmark. |
| M15 User-facing productization | DONE | Real Sleeper league onboarding (`POST /league/register`, validated live before persisting), real roster import/bridging, My Team roster intelligence, Action Center (ranked ADD/DROP/TRADE), batch waiver ranking, Player Detail (universal vs. my-league value), Draft/Dashboard/multi-asset Trade-package views — all thin reads of already-tested M1-M13 tables/M10 functions, zero new decision logic. Found and fixed 6 real bugs by exercising the real app end to end with Playwright against a real Sleeper league (`boys_of_fall`), not by code review: 3 DuckDB/refetch concurrency bugs, a Sleeper snapshot-filename collision, a non-atomic-write torn-read race (reproduced directly: 5,292 torn reads/~2,000 concurrent reads with the old pattern, 0 with the fix), and a UI unmount-before-paint bug. See D53. 350 offline tests passing (up from 303); lint + `tsc --noEmit` clean. |
| M31 Pre-real-draft product gaps | DONE (2/3 shipped, 1 audited and stopped) | D72. Three product-correctness gaps closed before real-draft use, zero strategy/model change. **Sleeper draft-pick sync**: `league/sleeper_draft.py` + `GET /league/{id}/sleeper-draft` reconstruct the live board (drafted picks, whose turn, next pick) from Sleeper's own `draft/{id}/picks` feed; `DraftView.tsx` polls it every 8s and auto-recommends on the user's turn; manual entry kept only for non-Sleeper leagues. **League scoring audit**: roster/lineup config was already fully wired Sleeper->engine (no change needed); scoring VALUE (PPR/half-PPR) is NOT wired -- every projection is fixed full-PPR from nflverse, baked in at M3 -- correctly identified as a hard stop (re-deriving points per league would mean re-projecting the model stack) and NOT faked; a disclosure banner surfaces the mismatch instead. **Draft-state persistence**: `localStorage` keyed by `{sleeper\|manual}:{league_id}`, Sleeper's own completed picks never cached (always re-fetched live). Two real bugs found by live Playwright testing (not code review) and fixed: a `RuntimeError`-catching `_league_or_404` was reporting a transient Sleeper outage as 404 "unknown league" instead of 503; a load/save-effect race (reproducible under React StrictMode) clobbered just-restored persisted state with pre-load defaults on every reload, fixed with a `hydrated` gate. 12 new unit + 5 new API tests (851 offline total) + 2 new live-network tests against the real `dilworth`/`boys_of_fall` leagues; lint/build clean both sides. Full detail: D72. |
| M32 Production-readiness hardening pass | DONE | D73. Audited the full live-draft path (Sleeper -> roster/league context -> draft state -> recommendation -> UI) for a real upcoming draft; zero scoring/methodology change. Found and fixed a real load-bearing bug: mid-draft roster resolution read only `GET /league/{id}/rosters`, whose live-draft update behavior Sleeper's own docs do not document, risking marginal-starter-value pricing against a roster missing this team's own just-drafted players -- fixed by unioning in the authoritative `GET /league/{id}/sleeper-draft` picks feed (`api/routers/league.py::_augment_with_live_draft_picks`). Found and fixed a real unhandled-exception bug: a genuine Sleeper 429/5xx or malformed response bypassed every `except SourceError` handler and would 500 instead of degrading to 503 (`sources/sleeper.py`). Exposed a `DraftDecisionTrace` (runner-up, score gap, full scored candidate list, draft-state inputs) via `DecisionResponse.trace` and `decisions.provenance_json` -- Phase 4/5's "what is calculated but discarded before reaching the UI," now retained, with no change to what gets recommended -- the structured seam a future Claude strategic layer will read. Fixed two real `DraftView.tsx` bugs: an auto-recommend transition ref that didn't reset on league/roster switch, and a race letting a recommendation request fire before the first Sleeper draft-state sync resolved; added a stale-recommendation banner keyed off live pick count. Verified live against the real `dilworth`/`boys_of_fall` leagues (real team/roster fetch, real 180- and 40-pick completed-draft reconstruction, graceful 404/422 on bad input) -- no in-progress draft was available in either, documented as a limitation rather than faked. No autonomous Sleeper pick submission exists anywhere in the codebase (verified by repo-wide grep) -- the recommendation/action safety boundary is currently satisfied only because the action side does not exist yet. 866 offline tests passing (up from 853); lint/typecheck/build clean both sides. Full detail: D73. |

## M1 summary
- Adapters: `nflverse` (15 datasets), `dynastyprocess` (4), `cfbfastr` (1), `ffopportunity` (1)
  — all AVAILABLE, verified against the live sources (both mocked-contract tests and
  `network`-marked live tests). `sleeper` (6 endpoints) verified BLOCKED_BY_POLICY at the time;
  `fantasypros` (2) and `cfbd` (3) verified NO_CREDENTIALS, and both provably never attempt a
  network call without a configured key (see `test_fantasypros_without_key_never_makes_network_call`
  / `test_cfbd_without_key_never_makes_network_call`).
  **Update (D31, 2026-08-22): the environment's network policy changed. `sleeper` is now
  genuinely AVAILABLE with real data; `fantasypros`/`cfbd` are now network-reachable too and
  blocked only on the still-missing API keys, not policy — see `docs/DATA_SOURCES.md`.**
  **Update (D36, 2026-08-23): `cfbd` moved from NO_CREDENTIALS to genuinely AVAILABLE — a real
  `CFBD_API_KEY` is live, verified with real data across all 3 datasets. `fantasypros` is not
  resolved the same way: a real `FANTASYPROS_API_KEY` is present and being sent, but FantasyPros's
  own API rejects it (`403 Forbidden`), so it stays blocked, now for a different, more specific
  reason than a missing key — see `docs/DATA_SOURCES.md`.**
  **Update (D37, 2026-08-23): `fantasypros` is now also genuinely AVAILABLE — the `403 Forbidden`
  was a wrong adapter base URL (missing `/public`), not a bad or unrotated key; fixed, both
  datasets confirmed live with real data — see `docs/DATA_SOURCES.md`.**
- `snapshot_registry` + `source_health_log` tables in DuckDB; every fetch writes an immutable
  file under `data/raw/<source>/<dataset>/captured_at=<date>/...` and is content-hashed.
- `alpha-squad sources status` and `alpha-squad sources ingest --season-start Y --season-end Y`
  both real, run against live sources. A multi-season smoke ingest (2023-2026) produced 46 real
  snapshots and correctly reported 8 NOT_FOUND for genuinely unpublished 2026 weekly/game-level
  datasets — nothing fabricated.
- Two real bugs found and fixed during self-review (not just written and assumed correct):
  1. `sources status` was writing real files to disk and reporting AVAILABLE without ever
     calling `record_snapshot`, so the registry silently stayed empty while the CLI reported
     success. Fixed by making status and ingest share the same fetch+record path; regression
     tests in `tests/unit/test_storage_snapshots.py`.
  2. `Settings` fields use `validation_alias` (so env vars match `.env.example`'s names) but
     without `populate_by_name=True`, pydantic silently dropped `Settings(data_dir=...)`-style
     kwargs and fell back to defaults, with `extra="ignore"` hiding the resulting
     ValidationError — meaning test fixtures believed they were isolated to `tmp_path` but
     were actually writing into the real repo `data/` directory. Fixed; regression tests in
     `tests/unit/test_settings.py`.

## M2 summary
- `players` (25,046 rows): spine anchored on nflverse `players.gsis_id` — verified 100%
  populated, unique. `player_id = 'asq_' || substr(md5(gsis_id), 1, 16)`, deterministic (not
  a persisted counter), so rebuilds are reproducible.
- `player_id_map` (25 id_types, ~180k rows total): normalized ID-to-ID crosswalk — 8 native
  nflverse IDs (gsis/pfr/espn/otc/esb/nfl/smart/pff) + 15 DynastyProcess IDs (mfl/sleeper/
  yahoo/ktc/etc.) + cfb_player_id (draft_picks) + cfb_id (combine). `(id_type, id_value)` is
  a hard PRIMARY KEY; `insert_id_mappings()` detects and quarantines collisions *before*
  writing rather than relying on the constraint to fail the whole build.
- `player_college_bridge`: 7,990 `cfb_player_id` + 6,131 `cfb_id` mappings, feeding rookie
  modeling (M7) directly from real draft_picks/combine data.
- `identity_exceptions`: 1,639 rows on first build (1,152 unmapped historical draft picks,
  389 unmapped combine prospects who never made a roster, 70 orphan DynastyProcess gsis_ids,
  28 genuinely self-inconsistent DynastyProcess rows) — quarantined, not dropped or guessed.
  Idempotent by design: re-running the build never reverts a human-resolved exception back
  to PENDING (regression-tested).
- Full build against live data: ~13 seconds, zero integrity violations (no duplicate keys,
  no orphaned foreign keys, no null gsis_id) — verified by both a live network test and
  direct inspection.
- Three real bugs found and fixed during self-review before considering this done:
  1. **Hash algorithm mismatch**: `mint_player_id()` (Python, for code needing an ID without
     a DB round-trip) used sha256 while the embedded SQL used md5 — would have minted two
     different IDs for the same gsis_id depending on code path. Fixed by extracting a single
     `PLAYER_ID_SQL_EXPR` constant both paths use; regression-tested for parity.
  2. **Severe performance bug**: `insert_id_mappings` and the college-bridge upsert looped
     over matched rows in Python, calling `con.execute()` once per row — profiled at 88
     seconds for 25,000 rows (~3.5ms/call overhead), which made a full identity build hang
     for minutes across ~25 id_types. Rewritten as set-based `INSERT...SELECT...RETURNING`
     (one round trip per id_type); full build now takes ~13s. `executemany()` was profiled
     too and found equally slow — the fix is genuinely set-based SQL, not a different batch
     API.
  3. **Wrong join target**: the draft_picks/combine college-bridge builders assumed a
     `players.pfr_id` column that doesn't exist — pfr_id (like every other native ID) lives
     in `player_id_map`, not denormalized onto `players`. Fixed to join through
     `player_id_map WHERE id_type='pfr_id'`.
- Real DynastyProcess data-quality issues discovered and handled (docs/DECISIONS.md D12/D13):
  the CSV export uses the literal string `"NA"` for missing values in every column including
  IDs (handled via `nullstr=['NA']`), and the export itself contains internally-inconsistent
  duplicate gsis_id rows (e.g. one gsis_id mapped to two different player names) — quarantined
  rather than trusting whichever row loaded first.

## M3 summary
- `games` (3,028 rows, 2015-2025): derived from `pbp`'s `game_id`/`game_date` since nflverse
  publishes no separate schedules dataset (verified 404) — the anchor for every as-of check.
- `player_week_stats` (199,632 rows): normalized `stats_player_week` + `snap_counts`,
  identity-joined once (gsis_id direct to spine; pfr_id through `player_id_map` for snaps,
  same pattern as the M2 college bridge).
- `player_week_features` (199,632 rows): the engineered lag/rolling panel — leakage-safe *by
  construction* via SQL window frames (`ROWS BETWEEN N PRECEDING AND 1 PRECEDING`), not by
  trusting a date filter. `target_fantasy_points_ppr` is the real unlagged outcome, kept only
  as the training target.
- `features_as_of(con, date)` is a second, independent row-level safety layer (`game_date <
  as_of`, strict) for reconstructing "what was known as of date D" — verified both offline
  and against real data that a game on the as-of date itself is correctly not yet visible.
- Leakage tests (tests/leakage/): poison/sentinel injection, target isolation via independent
  Python recomputation (not reusing the SQL under test), season-reset verification, and
  rebuild-invariance (appending future weeks and rebuilding must not change historical rows'
  stored features) — all passing, both offline (synthetic fixtures) and against real data.
- Full build against 11 real seasons (2015-2025) of cached data: ~7 seconds.

## M4 summary
- `player_season_stats` (21,421 rows): season aggregate of M3's `player_week_stats`.
- `market_snapshot` (210,730 rows): normalized DynastyProcess `fp_ecr_history` ('ro'
  redraft-overall series), identity-joined via `fantasypros_id` (verified 93.8% coverage —
  D16). Extended in M8 with the 2QB-aware series the target league (D7) actually needs.
- Three baselines, all walk-forward (season S predictions read only data from before S):
  `baseline_previous_year`, `baseline_weighted_2yr` (0.65/0.35), `baseline_ecr_implied`
  (isotonic rank-to-points calibration curve, fit per position on an expanding window of
  prior seasons only — D17). "ADP-implied" is LIMITED to this same ECR-based substitute; no
  independent ADP series is reachable (D16).
- Shared evaluation harness (`models/evaluate.py`): MAE, RMSE, R², Spearman, top-12/24 hit
  rate, tier accuracy — computed overall and per position, persisted to `evaluation_results`,
  published to `reports/baseline_evaluation.md`. Every later model (M5, M7, M8) reports
  through the same harness so comparisons are apples-to-apples, per ACCEPTANCE_CRITERIA.md.
- **Correction (superseded by the M5 fix below):** an earlier version of this section claimed
  the ECR-implied baseline's MAE was "substantially worse" than the simple historical
  baselines' based on comparing ecr_implied's correctly-scoped MAE (~45-49) against the other
  two baselines' *unscoped* "ALL positions" MAE (~14-15). That comparison was invalid — see
  docs/DECISIONS.md D19. With the fix, all three baselines land in the same ~45-53 MAE range
  for "ALL" (QB/RB/WR/TE only), a much more sensible result.

## M5 summary
- `team_week_stats`/`team_week_features` (6,056 rows): team-environment signal (plays, pass
  rate, EPA) from `stats_team_week`, leakage-safe by construction (same window-frame pattern
  as M3), attached onto `player_week_features` by (team, season, week).
- **Weekly/in-season models** (`models/established/train.py`): Ridge, CatBoost, XGBoost,
  plus standalone opportunity-only and team-environment-only models (isolating each signal's
  own predictive power — team-environment alone is markedly the weakest, MAE 30-56 vs 10-19
  for the full models, exactly as expected: team context alone barely predicts individual
  output), and an ensemble that's only marked `validated=True` in `model_registry` when it
  beats every component model's MAE out of sample that season (ARCHITECTURE.md §5/§12).
  Trains on seasons < S, predicts every week of season S using that week's already-lagged
  features, aggregates to a season total for comparison. Real result: Spearman 0.94-0.98,
  MAE 10-19 for the full models — strong, because this task has access to season S's own
  in-progress weeks (a genuinely different, easier task than preseason projection).
- **Season-level/preseason models** (`models/established/season_level.py`): Ridge, CatBoost,
  XGBoost trained on season S-1 aggregate + preseason ECR rank only — the actual
  apples-to-apples comparison against M4's baselines, since both use only pre-S information.
  Real, modest, genuine result: e.g. WR 2024, `ml_season_catboost` MAE 44.27 vs the best M4
  baseline (`ecr_implied`) at 45.05 — CatBoost edges out every baseline slightly, without
  overclaiming a dramatic win. Documented per-position, not hidden either way.
- Two model families, not one, precisely because comparing the weekly model against M4
  baselines would have overstated ML's advantage (different information sets) — see D18.
- **Real bug found and fixed during this milestone's review**: `models/evaluate.py`'s "ALL
  positions" rollup pooled *every* position in `player_season_stats` (LB, CB, K, P, etc. —
  ~900 of 1,512 rows for 2024), most of which correctly score ~0 PPR points. Their
  near-perfectly-predictable near-zero outcomes diluted the pooled MAE to ~14.7, while every
  individual skill position's real MAE was 33-65 — a materially misleading number that had
  been silently wrong since M4. Fixed with `SKILL_POSITIONS = ("QB","RB","WR","TE")` scoping
  the "ALL" rollup; per-position numbers were never affected (D19). All M4 and M5 evaluation
  reports were regenerated after the fix; regression-tested.

## M6 summary
- `uncertainty_predictions`: p10/p25/median/p75/p90 + top12_prob/top24_prob + a documented
  confidence heuristic, one row per (player, season, model_version) — field names mirror
  AGENT_CONTRACTS.md's Prediction contract directly.
- Split-conformal method (`models/uncertainty/conformal.py`): signed calibration-residual
  quantiles (not a symmetric margin), so intervals can be asymmetric — verified this matters
  with a synthetic right-skewed-residual test (p90 offset larger in magnitude than p10).
  Three-way, strictly time-ordered split per target season S: proper-train (< S-1) ->
  calibration (S-1 only, held out from training) -> target (S). Top-12/24 probabilities via
  Monte Carlo: resample from the empirical calibration-residual distribution 2,000x per
  player, rank within the simulated draw, measure how often each player lands in the top
  12/24 among their position peers.
- `calibration_diagnostics`: out-of-sample empirical coverage, published to
  `reports/calibration_report.md`. Real result on 2019-2025 QB/RB/WR/TE: coverage_10_90
  mostly 0.72-0.90 against a target of 0.80 (one outlier at 0.69, WR 2024) —
  genuinely close to nominal, not just directionally plausible. This is the "measure
  calibration" / "do not present false precision" requirement actually verified against real
  data, not asserted.
- 3,120 real predictions written on the full 2019-2025 run.

## M7 summary
- `combine_results` (7,031 rows): athletic testing bridged via `pfr_id` through
  `player_id_map`, same pattern as M3's snap counts.
- `rookie_features` (1,077 real rookie-seasons, 2016-2025 shown at ~90-103/class): draft
  capital (direct from `players`), combine testing, and landing spot (drafting team's
  *prior*-season pass rate/plays — never the rookie's own season, to avoid a look-ahead).
  breakout_top24 derived from actual within-position season rank, not a hardcoded points
  threshold.
- College production is LIMITED: cfbfastR-data's college identifiers are numeric ESPN-style
  IDs with no verified bridge to the nflverse-derived identity graph, and its "player_stats"
  dataset is raw play-by-play, not aggregated season totals — building both a fuzzy-match
  bridge and touchdown-attribution aggregation was judged a materially larger undertaking
  than this milestone's budget justified, especially since draft capital already
  substantially proxies for it (D20). Not fabricated via a shaky join; documented as a real
  gap with a defensible fallback.
  **Update (D38, 2026-08-23): the identity bridge exists after all — CFBD's own numeric athlete
  IDs are the same ID as `espn_id`, verified against real players with zero fuzzy matching.
  `college_usage` (season usage share, via CFBD) is joined into `rookie_features` for each
  rookie's final college season only, leakage-safe.**
  **Update (D39, same day): the feature was then actually measured, and rejected.** Over
  identical walk-forward folds the college features were neutral-to-slightly-worse on every
  metric that matters (breakout Brier +0.0030 vs baseline; worse on all four metrics when
  restricted to draft classes with ≥83% coverage). `FEATURES` reverts to the 12-feature D20
  baseline and `FEATURE_VERSION` to `rookie_features_v1`. The data pipeline, the bridge and the
  ablation harness are all kept — the experiment re-runs with
  `alpha-squad train rookie --ablation`. So college production remains LIMITED, but now for a
  measured reason rather than a missing-source one. See D39.
- CatBoostRegressor (rookie-year PPR points) + CatBoostClassifier (top-24 breakout,
  Brier-scored) walk-forward strictly by draft class (train on classes < C, predict C).
  Real results: regression Spearman mostly 0.4-0.8 (rookie prediction is inherently noisier
  than established-player prediction — no prior NFL data exists), breakout Brier scores
  mostly 0.02-0.12 against base rates of 2-27%.
- Historical comps (nearest-neighbor on standardized draft capital + combine, never drawing
  from the target's own or a later class): spot-checked against real 2023 RB rookies —
  Jahmyr Gibbs' and Bijan Robinson's top comps were plausible past first-round backs
  (Ezekiel Elliott, Clyde Edwards-Helaire).
- Two real bugs found and fixed during this milestone's review:
  1. Combine's `ht` column is a feet-inches string (`"6-0"`), not a number — a direct
     `CAST(... AS DOUBLE)` failed outright. Fixed by parsing `split_part` into inches.
  2. The comps nearest-neighbor crashed with a dtype error (`'float' object has no
     attribute 'sqrt'`) because the query-target row's integer columns came back as pandas
     nullable Int64 (bypassing `load_rookie_class_data`'s imputation), producing an
     object-dtype array `np.linalg.norm` couldn't handle. Fixed with an explicit
     `.astype(float)` after concatenation.

## M8 summary
- `market_snapshot` extended from `ecr_type='ro'` only (M4) to `ro`/`do`/`rsf`/`dsf`
  (682,397 rows total, 3,112/1,994/1,390/1,189 distinct players respectively). `rsf`
  (redraft-superflex, 2QB) is the series EDGE uses — it is a genuinely different market than
  `ro`: real data shows QBs occupying most of the top overall `rsf` slots, exactly what a 2QB
  league should produce and `ro` does not (D21).
- `dynasty_values` (681 rows, 97.6% real fantasypros_id coverage): normalized from
  DynastyProcess's `values-players.csv`, current 1QB/2QB dynasty ECR and value — reserved for
  M10's dynasty trade logic, not consumed by M8's single-season EDGE (D21 explains why mixing
  horizons would be wrong).
- EDGE (`edge_snapshot`, `AGENT_CONTRACTS.md`'s Edge contract): compares the M6 uncertainty
  model's single-season point/top24 predictions against `rsf`'s overall (cross-position) rank,
  both horizon-matched. `model_rank`/`market_rank` are cross-position; `projected_points_edge`
  comes from a pooled walk-forward isotonic rank→points curve; `probability_edge` from a
  per-position walk-forward isotonic rank→top24 curve (re-deriving a within-position rank from
  the overall `rsf` order, since the series carries no explicit position rank).
- Hard gating rule (D21, `classify_action` in `market/edge.py`): BUY/SELL requires rank edge
  AND points edge to agree in direction AND both clear a materiality threshold (rank ≥ 15,
  points ≥ 15 PPR) AND model confidence ≥ 0.5. A rank gap alone, or a rank/points disagreement,
  or low confidence, is never more than WATCH — literally regression-tested in
  `tests/unit/test_edge.py::TestClassifyActionGatingRule`, and re-verified against real stored
  output in the live test.
- Historical EDGE validation (`edge_validation_results`, real data, `rsf`, 2022-2025 — 2021 is
  WATCH-only since `rsf` history itself only starts in 2021, leaving no walk-forward training
  season): **as of M13** (see D28 — these figures were recomputed after a postseason-game
  contamination bug in the underlying weekly stats was found and fixed, and differ from the
  M8-era numbers originally reported here) — the **BUY cohort beat market-implied points in 3
  of the 4 scored seasons** (+19.77, +15.07, +13.98 PPR in 2022-2024; essentially flat at
  -0.56 PPR in 2025; n=31-47/season), a genuine, real, out-of-sample signal that the gated EDGE
  finds real market inefficiency in most seasons, not noise, though not a guarantee every
  season. The **SELL cohort moved the same direction as the market's real mistake in 3 of 4
  seasons** (-47.00/-21.92/-18.32 PPR in 2022-2024; wrong direction in 2025 at +36.91 PPR,
  small n=8-21/season) — reported honestly per CLAUDE.md, not suppressed.
  Real example: Tyler Higbee 2024 (`model_rank`=141 TE, `market_rank`=258 overall,
  `rank_edge`=+117, `points_edge`=+52.6, BUY) — matches a well-documented real dynasty-market
  pattern where 2QB/superflex ADP over-drafts QBs and pushes TE value down the board.
  (The M8-era version of this paragraph used Travis Kelce 2024 as the illustrative example;
  his real corrected 2024 season total dropped enough after the D28 fix — his 3 real 2024
  playoff/Super Bowl games, previously double-counted into his "season" total, are real games
  but not part of a regular-season projection — that his own EDGE call flipped from BUY to
  SELL. Left in as a concrete illustration of the bug's real impact rather than quietly
  swapped out.)
- `evidence_score` is a disclosed neutral placeholder (0.5) pending M9 — reported in every
  `edge_snapshot` row and its `reasons` for transparency, but never used to gate BUY/SELL/HOLD/
  WATCH (D21). This is not a corner cut silently: the field exists with the exact contract
  shape now, and M9 only needs to start producing a real score into the same column.

## M9 summary
- `evidence_events` (real data, 2019-2025: **33,311 events** — 8,231 usage_share_spike,
  7,720 usage_share_drop, 8,200 injury_own_status, 2,539 injury_teammate_opportunity, 2,397
  depth_chart_promotion, 2,000 depth_chart_demotion, 2,006 roster_transaction): four Strong-tier
  detectors (`evidence/events.py`), all on officially-sourced nflverse structured data, every
  event dated strictly before the week it informs (leakage-safe by construction, same
  discipline as `features/panel.py`). PRODUCT_SPEC.md's full Strong/Medium/Weak taxonomy is
  registered in `evidence/taxonomy.py`; Medium/Weak have no detector (no reachable news/social
  source, D5) but share the same `record_event()` contract for future manual entry (D22).
- Real, spot-checked example matching an actual documented 2024 event: Amari Cooper's week-8
  2024 evidence-adjusted projection (10.27 -> 8.88, -13.5%) is driven by `roster_transaction`
  (Cleveland -> Buffalo, the real in-season trade) plus `usage_share_drop` (snap_pct 0.35 vs.
  his own 0.86 trailing average) — the detectors independently reconstructed a real, verifiable
  storyline from structured data alone, not fabricated.
- `weekly_projection_snapshot`: M5's `train.py` was already computing a real per-week point
  prediction (`ml_catboost`) internally and discarding it after season-aggregation; this
  milestone persists it (12,212 real rows for a 2023-2024 smoke run) since evidence is
  inherently a weekly signal, not an annual one.
- `projection_deltas` (`evidence/prior_update.py`): bounded (±15% of the base value, hard
  cap `MAX_ADJUSTMENT_PCT`) adjustment from aggregated same-week evidence, applied to
  `weekly_projection_snapshot` and written to a **separate** table — the base row is only ever
  read, never mutated (regression-tested against both synthetic data and this milestone's real
  12,212-row run: `tests/unit/test_evidence.py::test_never_mutates_the_base_weekly_projection_row`,
  `tests/integration/test_evidence_live.py::test_evidence_never_overwrites_the_real_weekly_projection`).
  Every material delta carries a human-readable `reason` and its source `evidence_ids`.
- M8's EDGE `evidence_score` is now real (`evidence_score_for_action`), not the D21 placeholder:
  computed from `evidence_events`, defaulting to neutral 0.5 when none exist. In practice it
  stays neutral for M8's preseason-anchored EDGE (real detectors only ever produce in-season
  events, and EDGE compares preseason market snapshots) — an honestly-reported horizon mismatch,
  not a disguised placeholder (D23). `classify_action` now vetoes an otherwise-valid BUY/SELL to
  WATCH only when evidence *actively contradicts* the action (`evidence_score < 0.35`); neutral
  evidence never blocks. M8's already-published historical BUY/SELL numbers are unchanged by
  this wiring (every one of those calls saw neutral evidence, which trivially clears the veto).
- Real bug found and fixed during this milestone's review (D24): nflverse's `depth_charts`
  release has two incompatible real historical schemas (pre-2025: `week`-keyed with
  `depth_team`/`depth_position`/`club_code`; 2025+: near-daily `dt`-keyed with
  `pos_rank`/`pos_abb`/`team`). The initial implementation assumed the new schema everywhere
  and crashed outright (`BinderException: column "dt" not found`) on every pre-2025 season.
  Fixed with schema detection in `evidence/events.py::_depth_chart_entering`, normalizing both
  into the same shape before any diff logic runs.

## M10 summary
- `league/context.py`: `LeagueContext` mirrors AGENT_CONTRACTS.md's League context contract
  exactly (`extra="allow"` + free-form dicts for lineup/scoring/roster/etc., so arbitrary
  league settings can be represented per ACCEPTANCE_CRITERIA.md), loaded from
  `config/league_configs/target_league.yaml` (10 teams, 2QB/2RB/2WR/1TE/2FLEX, dynasty PPR,
  bench 10, FAAB $100 — D7's defaults).
- `league/replacement.py`: real value-based-drafting (VBD) with flex allocation — dedicated
  slots filled first by within-position rank, then flex slots earned by the single best
  remaining players across every flex-eligible position (not split evenly). Verified against
  real 2025 uncertainty_predictions (455 real players): exactly 20 dedicated QB starters (10
  teams x 2, matching the target league precisely) and a QB replacement level (~220 pts) far
  above RB/WR/TE's (~138-146 pts) — the target league's 2QB format genuinely reshapes the
  market, not a hardcoded assumption. Real, disclosed finding worth a future look: at this
  model's real rank ~18-26, WR point_prediction values exceed RB/TE's enough that every FLEX
  slot in this run went to WR — a legitimate downstream consequence of M5/M6's own
  already-validated (by those milestones' own gates) predictions, not a bug in M10's
  allocation logic, but a candidate for cross-position calibration review in a future model
  refinement pass.
- Real coverage gap found and fixed: M6's uncertainty model structurally excludes true
  rookies (0/442 real 2024 rows). `load_season_projections` now fills any player missing from
  `uncertainty_predictions` in from M7's real `rookie_predictions`, so waiver/draft tools can
  evaluate rookies at all (D25).
- `league/draft.py`: VORP x roster-fit x model-confidence x next-pick-survival-probability
  scoring, with alternatives and reasons (Decision contract). Survival probability models the
  real `ecr_best`/`ecr_worst` expert-rank dispersion (M4/M8) as Uniform(best, worst) — real
  data, not a fabricated distribution.
- `league/waiver.py`: meaningful-role probability (M6 top24_prob), dynasty value (M8), a
  value-spike read from real recent M9 evidence, roster fit, replacement level, a
  scarcity-and-role-based competing-bid-likelihood heuristic, and a bounded (≤40% of budget)
  FAAB bid. Real, spot-checked example: Keon Coleman (2024 rookie WR), whose static
  preseason-anchored projection is *below* WR replacement level (a realistic outcome for many
  rookies), still gets a real, non-zero recommended bid ($18.94 of $100) because his real,
  detected `depth_chart_promotion`/`usage_share_spike` evidence (his actual real-life
  promotion to WR1) drives the value-spike term — verified this would have incorrectly zeroed
  out under a naive marginal-value-only formula, and fixed (D25).
- `league/trade.py`: dynasty buy/hold/sell/watch built directly on M8's real, already-validated
  EDGE action/reasons and DynastyProcess's real `value_2qb`, with a clearly-labeled,
  documented age-curve heuristic (NOT a trained model — no ground-truth dynasty-decay dataset
  exists to fit one, D25) as a disclosed secondary adjustment only.
- `decisions` table (AGENT_CONTRACTS.md's Decision contract): every `league draft`/`waiver`/
  `trade` CLI call persists its recommendation, alternatives, expected value, confidence,
  reasons, and provenance — the pure recommendation functions themselves stay side-effect-free
  and unit-tested independently.
- 29 new offline unit tests (152 total), covering the VBD algorithm's flex-earned-not-split
  behavior, the literal 2QB-vs-1QB replacement-level difference, survival-probability edge
  cases, roster-need bounds, and the evidence-driven bid override case. 5 new live network
  tests (`tests/integration/test_league_live.py`, 26 total network) validate the same logic
  end-to-end against real 2022-2025 data, including confirming the M7 rookie-prediction
  fallback actually returns a usable projection for a real rookie-only player.

## M11 summary
- `agents/contracts.py`: pydantic `Task`/`Result`/`EvidenceContract`/`PredictionContract`/
  `EdgeContract`/`DecisionContract` mirror AGENT_CONTRACTS.md's JSON examples field-for-field
  (`extra="allow"` throughout). League context is *not* redefined here — it reuses M10's real
  `league.context.LeagueContext`, a single source of truth.
- `agents/registry.py`: 9 real agents (`data_engineering`, `player_identity`, `projection_ml`,
  `rookie_ml`, `market_edge`, `news_evidence`, `fantasy_strategy`, `evaluation_qa`,
  `research_validation`) — every one a thin, deterministic wrapper around the exact M1-M10
  functions already built and validated in their own milestones (D14/D26). `research_validation`
  (optional per AGENT_CONTRACTS.md) honestly reports NEEDS_REVIEW rather than fabricating a
  finding: no unstructured research capability is reachable in this environment.
- `agents/orchestrator.py`: real DAG scheduling (topological readiness, not a fixed order),
  retry/backoff (2 retries, verified recovering a real transient-failure stub), and genuinely
  concurrent dispatch of independent tasks — verified two real stub tasks start within 0.2s of
  each other, not sequentially. `agent_tasks`/`agent_results` persist every state transition;
  `reconstruct_run` rebuilds a full run's status purely from that DB state, satisfying
  IMPLEMENTATION_PLAN.md's M11 gate directly (regression-tested, and re-verified against a
  real orchestrated run of `data_engineering` -> `player_identity` against live nflverse data).
- Real concurrency bug found and fixed via the orchestrator's own test suite (D26): running
  `init_db()` (which includes `ALTER TABLE`) from multiple worker threads' own connections hit
  a real DuckDB `Catalog write-write conflict` under genuine concurrent dispatch. Fixed by
  running schema DDL exactly once, before any worker thread opens a connection.
- `agents/disagreement.py`: reuses M8's real `edge_snapshot.rank_edge` (model-vs-market) and
  M4/M5's real `evaluation_results.mae` (baseline-vs-ML) rather than deriving new comparisons.
  Verified against real 2024/2025 data: 292 real model-vs-market rank disagreements and 4 real
  baseline-vs-ML disagreements (established-ML beats the ECR baseline's MAE by roughly 3x at
  every position, consistent with M5's own published numbers) were detected, resolved, and
  recorded with both positions preserved (never silently discarding the minority, per
  AGENT_CONTRACTS.md's conflict protocol).
- `evaluation_qa`'s REJECT capability reuses M5's own real `model_registry.validated` gate
  (ACCEPTANCE_CRITERIA.md: "Evaluation/QA can reject unsupported claims") rather than inventing
  a new judgment.
- `milestones` table + `record_milestone`: milestone state (ACCEPTANCE_CRITERIA.md: "Milestone
  state is persistent") is written at the start and end of every orchestrated run, independent
  of any individual task's state.
- 20 new offline unit tests (172 total) plus 3 new live network tests (29 total), including a
  real orchestrated run against live nflverse/DynastyProcess data and real disagreement
  detection against a full real season's established-ML/baseline/EDGE results.

## M12 summary
- `src/alpha_squad/api/`: FastAPI app with 8 routers (`players`, `rankings`, `rookies`,
  `edge`, `evidence`, `league`, `provenance`, `health`). Every response field is a direct
  projection of an already-persisted table (`uncertainty_predictions` M6, `rookie_predictions`
  M7, `edge_snapshot` M8/M9, `evidence_events` M9, `source_health_log` M1) or a direct call
  into the exact M10 function the CLI calls (`recommend_draft_pick`, `recommend_waiver_pickup`,
  `recommend_dynasty_trade`) — D27 documents why there is no parallel logic path anywhere in
  this package. `/provenance/{id}` traces any ID across every table that could own it. A
  missing/unknown league returns 404, never a fabricated universal answer.
- `web/`: a real React + Vite + TS SPA (six views: Rankings, EDGE, Rookies, Evidence, League,
  Source Health), deliberately lean rather than polished (PRODUCT_SPEC.md frames the SPA as
  presentation-only) but genuinely live — every view fetches the real API, no mock data, no
  client-side scoring/ranking. BLOCKED_BY_POLICY/NO_CREDENTIALS source badges render honestly
  (verified: cfbd/fantasypros show amber NO_CREDENTIALS badges with the real reason text, not
  hidden behind a generic status).
- Verified end-to-end in a real Chromium browser (Playwright, the environment's pre-installed
  browser — CLAUDE.md's "start the dev server and use the feature in a browser" requirement):
  all six views loaded and rendered real persisted data (real players — Lamar Jackson/Josh
  Allen top QB rankings, Tyler Conklin/real TE BUY signals on EDGE, Ashton Jeanty atop 2025
  rookies, a real Storm Duck injury event); the League tab's draft form was submitted and
  returned the same recommendation/reasons the CLI produces for identical inputs; and the
  literal Gate 8 test was performed, not just written: the API process was killed and the page
  reloaded, producing a real fetch error in the UI rather than stale or fabricated content. A
  real UX bug (the error message literally said "as intended," written for this decision log
  rather than a user) was caught during that same review pass and fixed.
- Real gap found and fixed during review (D27): `RankingRow` initially omitted `prediction_id`,
  which would have made a ranking untraceable through `/provenance` — added, along with a live
  test proving the trace actually resolves to the real source row.
- 17 new offline API tests (189 total) using FastAPI's `TestClient` with `get_db` overridden to
  an in-memory DB — including a literal test that `/rankings`/`/edge` return the *exact* stored
  values from a seeded row, proving no re-ranking/re-scoring happens in the API layer. 4 new
  live network tests (33 total) exercise the same endpoints against a real, live-ingested
  dataset.

## M13 summary
- **Correlated team-season Monte Carlo simulation** (`models/simulation/`), the item deferred
  since D8: `team_scores.py` derives real final team scores per (team, season, week) from
  `pbp`'s running score columns; `correlated.py` samples one joint (plays, pass_rate,
  team_points) draw per simulated trial from a team's real historical covariance, and derives
  every rostered player's simulated weekly points from that *same* trial's draw via their real
  opportunity share and efficiency — the shared-randomness structure genuine QB/WR1 correlation
  requires, measured empirically rather than assumed. Wired into the CLI
  (`alpha-squad simulate team-season`), persisting a summary row to `team_simulation_runs`.
  Verified across all 32 real NFL teams x 3 seasons (2022-2024, 96 simulations):
  `qb_wr1_correlation` positive in 100% of runs (mean 0.358, range 0.27-0.46).
- **A real, cross-cutting data bug found and fixed (D28), not scoped to M13's own new code.**
  Building the simulation surfaced that `player_week_stats`/`team_week_stats` (M3) had silently
  included postseason NFL games in every "season" aggregate since the very first ingestion —
  nflverse's weekly releases carry postseason weeks with no flag of their own, and the REG/POST
  distinction that `games` already tracked (`game_type`) was never joined against when building
  those two tables. This inflated `player_season_stats` (feeds M4's baselines), let a team's
  trailing "last 3 games" feature silently pull in a playoff game, and inflated the season
  totals used everywhere else — for every playoff team's players, in every one of the 11
  ingested seasons (2015-2025), not just M13. Fixed at the source (an explicit
  `game_type = 'REG'` join condition); the already-populated tables needed an explicit `DELETE`
  (8,543 stale rows from `player_week_stats`, 266 from `team_week_stats` — an upsert alone
  cannot remove keys a corrected query stops producing). Every downstream step was re-run
  against the cleaned tables: `features build`, `evaluate baselines`, `train established`,
  `train established-season`, `train uncertainty`, `train rookie`, `edge build`, `edge
  validate` — all from already-cached local snapshots, no new network fetch needed. The
  qualitative findings are unchanged (ML still beats baselines by a wide margin at every
  position; EDGE's BUY cohort still beats market expectation in most seasons) but the exact
  numbers shifted, most visibly EDGE's real Travis Kelce 2024 example flipping from BUY to SELL
  once his 3 real playoff/Super Bowl games stopped being double-counted into his "season" total
  (see the corrected M8 summary above). A regression test
  (`tests/unit/test_features.py`) asserts a synthetic postseason game's stats never reach either
  table.
- **Two further simulation-design bugs, both caught by checking real numbers against known
  real outcomes rather than trusting that the code ran without error (D29):** (1) the QB's
  simulated output was anchored to `team_points` rather than `pass_attempts` — both come from
  the same per-trial draw, but real per-team history shows `pass_attempts` and `team_points`
  are only weakly (sometimes negatively) related, due to ordinary game-script effects, so the
  QB rarely landed in the same "big passing game" trial as his own WR1; `qb_wr1_correlation`
  measured -0.03 before the fix. Re-anchored the QB to `pass_attempts * (real points per pass
  attempt)`, the same shared draw and functional form every pass-catcher already uses. (2) a
  qualifying pass-catcher's target/carry share was computed against the sum of only *other
  qualifying* pass-catchers' volume, then multiplied against the team's *full* simulated
  volume — two mismatched denominators that inflated every qualifying player's output (caught
  when a real 316-point 2024 WR1 season simulated to a 504-point mean). Fixed by normalizing
  share against the team's real total volume (all positions, all players) instead.
- **A real RNG-reproducibility bug, caught by writing the reproducibility test rather than
  assuming it would pass:** `_pass_catcher_shares`/`_rb_shares` built their result from an
  unordered SQL `GROUP BY`, and the simulation draws each player's noise sequentially from one
  shared seeded `np.random.Generator` in dict-iteration order — DuckDB doesn't guarantee
  `GROUP BY` row order without an explicit `ORDER BY`, so which named player got which slice of
  the seeded random stream was query-plan-dependent, not code-dependent. Fixed with explicit
  `ORDER BY`s; verified reproducible both offline (11 new unit tests,
  `tests/unit/test_simulation.py`) and against real data (4 new live tests,
  `tests/integration/test_simulation_live.py`; 3 repeated real calls against KC 2024 produce
  bit-identical output to full float precision).
- **Model reproducibility, previously asserted by a fixed `random_state=42` in every model
  config but never actually tested:** added a new offline test
  (`tests/unit/test_established_ml.py::TestReproducibility`) that runs the real
  CatBoost/XGBoost/Ridge fit-predict path twice against identical synthetic data and diffs the
  persisted `evaluation_results` — genuinely exercising the claim rather than trusting the
  presence of a seed kwarg.
- **Secrets audit:** grepped tracked source for hardcoded credential patterns (none found);
  confirmed `.gitignore` excludes `.env`/`.env.*`/`data/`/`models/`/`*.duckdb`; confirmed
  `.env.example` files contain only placeholders; confirmed no data files or unusually large
  files are tracked in git.
- **Data-refresh, historical-reconstruction, and ambiguous-ID coverage reviewed** against the
  existing suite rather than assumed adequate: `tests/leakage/`'s `TestRebuildInvariance`
  already covers data-refresh consistency; `as_of`/`scrape_date` filtering is already tested
  across baselines/EDGE/league/leakage; `tests/unit/test_canonical_identity.py`'s
  quarantine tests already prove an ambiguous mapping is never inserted (and therefore can
  never silently join). Judged adequately covered rather than duplicated.
- **README, Makefile, and CI had drifted from the real system (D30), found while writing
  `docs/TRACEABILITY.md`:** `README.md` still documented the *original planning package*
  ("put this package into the repository..."), not how to install/run/use the system that was
  actually built — rewritten. `Makefile`'s `train`/`evaluate` targets referenced CLI flags that
  never existed on the real Typer CLI (verified broken by running them, not assumed); fixed,
  and added `market`/`edge validate`/`simulate`/`orchestrate` targets that had no Makefile
  entry despite being real since M8/M11/M13. No CI existed; added
  `.github/workflows/ci.yml` (lint + offline test suite on push/PR).
- `docs/TRACEABILITY.md` written: every `ACCEPTANCE_CRITERIA.md` checkbox mapped to the
  module/test/report that satisfies it, with every LIMITED/BLOCKED item's reason and fallback
  named explicitly rather than silently omitted.
- 15 new offline tests (204 total: 11 simulation + 3 REG/POST regression + 1 established-ML
  reproducibility) and 4 new live network tests (37 total, `test_simulation_live.py`).

## Post-M13: environment re-verification, and Sleeper trending as a real Weak-tier evidence signal (D31/D32)
This environment's network egress policy changed after M13 shipped. Re-verified live rather
than assumed (D31): Sleeper's public API is now genuinely `AVAILABLE`, no credentials needed;
FantasyPros/CFBD are network-reachable too, now blocked only on their still-missing API keys,
not policy.

Built on that: `evidence/sleeper_trending.py::detect_sleeper_trending` (D32) fetches Sleeper's
real `trending_adds`/`trending_drops`, resolves each to a canonical player via the existing
DynastyProcess `sleeper_id` crosswalk, and records `social_media_buzz` Weak-tier evidence
events through the same `record_event()`/taxonomy machinery every other detector uses — no
parallel evidence path. This is the evidence engine's first real Weak-tier detector
(previously registered vocabulary only, D5/D22). Wired into the CLI
(`alpha-squad evidence build-sleeper-trending`). Verified against real data: real Sleeper IDs
resolved to real players (Xavier Hutchinson, Barion Brown, Darren Waller, ...), 48/50 real
trending entries resolved on a real run.

Verifying it against real data caught a genuine, previously-undiscovered bug in
`evidence/prior_update.py::evidence_score_for_action` (already-shipped code from M9, not new):
its own docstring promised evidence "before that season's own Week 1" counts toward EDGE's
evidence score, but the code hardcoded an August 1st cutoff — real Week 1 dates run early
September (checked directly: 2023-09-07, 2024-09-05, 2025-09-04), so roughly five weeks of
real preseason evidence were being silently discarded, contradicting the function's own
documented intent. This had never surfaced before because no evidence source had ever
produced real events dated in August. Fixed to use the season's real Week 1 date from `games`
when known, falling back to September 1st only for a season with no games ingested yet.

7 new offline tests (211 total: 5 sleeper-trending unit + 2 evidence-cutoff regression) and 3
new/updated live network tests (39 total: 2 new sleeper-trending live tests, plus
`test_sources_live.py`'s Sleeper test flipped from asserting BLOCKED to asserting AVAILABLE,
exactly as its own prior docstring said to do if this ever happened).

**Then built (see D33 below):** real per-league Sleeper sync, and a multi-league registry so
multiple leagues (Sleeper-live and/or YAML) can be configured and switched between. **Still not
built:** live verification of the Sleeper field mapping against a real league (needs a real
Sleeper league ID, not supplied yet) and direct FantasyPros/CFBD access (needs API keys, not
supplied yet).

## Post-M13: multi-league registry — switch between multiple leagues seamlessly (D33)
The user has multiple real leagues, a mix of Sleeper and other/manual platforms, and asked to
switch between them seamlessly. Investigating first (rather than assuming the existing
`{league_id}` path parameters already did this) found they were vestigial: every CLI command,
the API, and the frontend hardcoded `target_league.yaml` regardless of what `league_id` was
passed in. There was exactly one league, config-driven, and nothing to switch between.

Built `league/context.py::resolve_league(league_id, ...)` and
`config/league_configs/registry.yaml` (`league_id -> {source: "yaml"|"sleeper", ...}`) as an
additive layer in front of the existing, unchanged `load_league_context()`: a `yaml` entry
resolves to a config file exactly as before; a `sleeper` entry hydrates a `LeagueContext` live
from a real Sleeper league on every call (never cached, so it can't drift from the real league's
current settings) via the new `league/sleeper_context.py::load_sleeper_league_context`. Every
call site that used to hardcode `target_league.yaml` — all 4 `league` CLI commands, the
`run_fantasy_strategy` agent, all `api/routers/league.py` endpoints, and `LeagueView.tsx` — now
resolves through the same registry, plus a new `alpha-squad league list` command / `GET /league`
endpoint / frontend dropdown (persisted across reloads via `localStorage`) to actually switch.
Verified in a real browser (Playwright): two leagues with deliberately different real settings
(14-team redraft/non-PPR vs. 10-team dynasty/PPR) switch correctly in both directions, with the
displayed data genuinely changing each time, not just a one-way fluke.

The Sleeper field mapping (`sleeper_context.py`) translates a real `/league/{id}` response into
`LeagueContext`: `roster_positions` counted into `lineup`/`roster` (bench vs. `IR`/`TAXI` split
out), `settings.type` (0/1/2) into `format` (redraft/keeper/dynasty), `scoring_settings.rec` into
PPR value, `settings.waiver_budget` into FAAB. Provenance (`source`, `sleeper_league_id`,
`sleeper_league_name`, `sleeper_season`) is stashed on the pydantic model via its existing
`extra="allow"` rather than a schema change. Building this against Sleeper's documented API shape
(no real league available yet to test against) surfaced a real naming inconsistency in the
codebase's own `FLEX_ELIGIBILITY` registry: Sleeper's real superflex slot is spelled
`SUPER_FLEX` (underscore); the already-registered key was `SUPERFLEX` (no underscore) — caught by
a new unit test, not live data, and fixed additively (both spellings now registered, so no
existing manual YAML using the unspaced form breaks).

11 new offline tests (222 total: 6 `resolve_league`/registry unit tests, 4 Sleeper-context
mapping unit tests, 1 API registry test) and 1 new live network test (40 total).

**Update (D34, same day):** the user supplied two real Sleeper league ids. The live test above
ran against both for real and passed, including `unrecognized_flex_slots == []` — confirming the
`SUPER_FLEX` fix (and the rest of `FLEX_ELIGIBILITY`) against real data, not just the documented
API shape. Both are now registered (`dilworth`: 12-team redraft/1QB/PPR; `boys_of_fall`: 10-team
dynasty/2QB/PPR) and switchable exactly like `target_league`. The Sleeper field mapping is no
longer "implemented but unverified" — it is verified.

**Update (D35, same day):** separately, real `FANTASYPROS_API_KEY`/`CFBD_API_KEY` values were
briefly committed to the tracked `.env.example` on `main` (a mistake, not this project's design —
the intended path is a gitignored `.env` or the deployment's own env-var config) and, since this
repo is public, were live-exposed until fixed. Fixed on `main` (`aa9e841`, restoring placeholders,
with the user's explicit go-ahead since `main` is outside this project's designated branch) and a
durable guardrail comment added directly in `.env.example` itself. The user was told to rotate
both keys at their providers regardless of the repo fix, since a repo-side fix cannot undo a
credential already having been public. See D35 for the full account.

**Update (D36, 2026-08-23):** re-verified in a fresh container. `CFBD_API_KEY` is confirmed picked
up and live — all 3 CFBD datasets (`teams`, `player_usage`, `recruiting_players`) return real
data; direct CFBD access is now AVAILABLE, no longer pending. `FANTASYPROS_API_KEY` is also
confirmed picked up (present, sent as the `x-api-key` header) but FantasyPros's own API rejects it
(`403 Forbidden`) — network policy is not the blocker (confirmed via raw response headers showing
a real AWS API Gateway/CloudFront response, not a proxy error), so this is not a repeat of the
"not yet picked up" state; it needs the user to check the key itself at FantasyPros's dashboard.
See D36 for the full account.

**Update (D37, 2026-08-23):** the FantasyPros `403 Forbidden` above was not a key problem — the
user confirmed the key was already correctly rotated, which prompted checking FantasyPros's own
API docs instead of continuing to suspect the key. `sources/fantasypros.py`'s base URL was missing
a `/public` path segment. Fixed; both FantasyPros datasets now confirmed AVAILABLE with real data.
Direct FantasyPros access is no longer pending or blocked. See D37 for the full account.

**Still not built:** manual/non-Sleeper league configs for the user's other leagues — needs the
actual league details (teams, scoring, roster slots) from the user, not supplied yet.

## Known limitations (see docs/DECISIONS.md for full reasoning)
- **Update (D37, 2026-08-23):** FantasyPros is now also fully AVAILABLE — the `403 Forbidden`
  reported below (D36) was a wrong adapter base URL, not a bad/unrotated key; fixed. Both CFBD
  and FantasyPros now return real data with their configured keys. See `docs/DATA_SOURCES.md`
  for the current, authoritative status.
- **Update (D36, 2026-08-23):** CFBD is now fully AVAILABLE with a live `CFBD_API_KEY` (real data
  confirmed across all 3 datasets). FantasyPros still isn't — a `FANTASYPROS_API_KEY` is present
  and being sent, but FantasyPros's own API rejects it with `403 Forbidden`; this is not a policy
  block, and root cause isn't established (needs the user to check the key). See `docs/DATA_SOURCES.md`
  for the current, authoritative status.
- **Update (D31, 2026-08-22):** the line below described the environment as it stood through
  M13. The network policy has since changed: Sleeper is now genuinely AVAILABLE (no code
  change needed — verified with real data), and FantasyPros/CFBD are network-reachable and
  blocked only on their still-missing API keys, not policy. KeepTradeCut (no adapter exists)
  and ESPN (unused) are the only sources still actually inert. See `docs/DATA_SOURCES.md` for
  the current, authoritative status.
- FantasyPros API, CollegeFootballData, KeepTradeCut, ESPN direct APIs were `BLOCKED_BY_POLICY`
  in this environment through M13; Sleeper, CFBD, and FantasyPros have since cleared (D31/D36/D37),
  KeepTradeCut and ESPN have not. Verified open-data
  substitutes are wired in regardless (docs/DATA_SOURCES.md). Adapters for the still-blocked
  sources are implemented but inert.
- Per-expert accuracy weighting: LIMITED to source-level weighting (D4).
- Automated news/social evidence ingestion: LIMITED to structured official signals (D5).
- ADP-implied baseline: LIMITED to the ECR-implied substitute; no independent ADP series is
  reachable (D16).
- Rookie college production: LIMITED, now for a *measured* reason rather than a missing source.
  D20 found no verified ID bridge from cfbfastR-data's numeric IDs; D38 built a real one via
  CFBD/`espn_id` and ingested the data; **D39 ran the ablation and did not adopt it** — college
  usage share is neutral-to-slightly-worse than the 12-feature baseline over identical
  walk-forward folds, including when restricted to high-coverage draft classes. Production stays
  on draft capital + combine + landing spot. Re-measurable any time via
  `train rookie --ablation` (reports/rookie_college_production_ablation.md).
- EDGE `evidence_score`: LIMITED to a disclosed neutral placeholder (0.5) until M9's evidence
  engine exists; never used to gate an action (D21).
- EDGE is single-season/redraft-horizon only (`rsf`), matching the M6 model's own horizon; a
  dynasty-horizon EDGE using `dsf`/`dynasty_values.value_2qb` is deferred to M10's trade logic
  rather than conflated with a single-season points model (D21).
- Historical EDGE validation: the BUY cohort's real out-of-sample outperformance is a strong,
  consistent positive signal (3/4 scored seasons decisively positive, the 4th essentially flat)
  and the SELL cohort moved the same direction as the market's real mistake in 3/4 seasons —
  not hidden, and recomputed in M13 after fixing a data bug that had been inflating some of
  these numbers; see M13 summary below and D28.
- Evidence Medium/Weak tiers (beat writers, coach comments, social media, practice-participation
  narrative): LIMITED to a registered taxonomy + manual-entry path; no reachable news/social API
  in this environment (D5, D22). Only Strong-tier, officially-sourced structured signals have a
  real detector.
- EDGE `evidence_score` was structurally near-always neutral in practice for the preseason-
  anchored EDGE, since the four Strong-tier detectors are in-season only and EDGE is preseason
  (D23) — a genuine horizon mismatch, disclosed rather than papered over. **Partially closed in
  D32**: Sleeper trending adds/drops is a real evidence source that exists *at* the preseason
  horizon (unlike the Strong-tier detectors), and a real bug in the evidence cutoff itself
  (hardcoded to August 1st despite the code's own docstring promising "before Week 1," which
  is early September — found while verifying D32 against real data) was silently discarding
  roughly five real weeks of any preseason evidence that did exist, for every season. Still
  true: the four Strong-tier structured detectors remain in-season only; an in-season EDGE
  variant that would let evidence meaningfully move `evidence_score` beyond a veto is future
  scope.
- Dynasty trade's age-curve adjustment is a documented heuristic (D25), not a trained/validated
  model — no ground-truth dynasty-value-decay dataset exists in this environment to fit one. It
  is a disclosed secondary adjustment only; the primary BUY/SELL signal is M8's real, validated
  EDGE.
- A real, disclosed cross-position calibration question (not a bug): on real 2025 data, M5/M6's
  point predictions at rank ~18-26 favor WR enough that M10's real VBD allocation sent every
  FLEX slot to WR rather than splitting across RB/WR/TE. M5/M6 passed their own baseline/
  calibration gates in aggregate; this is a downstream reminder that aggregate MAE doesn't
  guarantee cross-position relative calibration, worth revisiting in a future model-refinement
  pass — not addressed in M10, which correctly allocates flex by whatever values it is given.

## Post-M13: first real end-to-end pipeline run, and the college-production feature measured and rejected (D39)

The database in this container was empty before this run — D38's work had never executed against
real data. The full pipeline was run for the first time (2012–2025): 155 successful source
fetches, 25,050 players, 241,208 player-weeks, 26,816 player-seasons, 1,360 rookie-seasons,
5,566 college-usage rows across 1,541 players.

**The headline result is a negative one, and that is the point.** D38's CFBD college-production
features were measured against the pre-D38 baseline over identical walk-forward folds, under a
decision rule fixed before any numbers were seen, and **did not earn their place**: breakout
Brier +0.0030 (worse), regression Spearman −0.0003, MAE +0.0589. A robustness check restricted to
draft classes where the feature is ≥83% populated — testing whether zero-imputation of
low-coverage classes was masking a real signal — came out worse still, with the baseline winning
all four metrics. `FEATURES` reverted to the 12-feature D20 set; the data pipeline, identity
bridge and ablation harness are all kept so the question re-runs with one command.

**Running it for real surfaced three bugs that no test caught**, the most serious being that
`init_db` had no migration path: every DDL statement is `CREATE TABLE IF NOT EXISTS`, which
silently ignores a *column* added to an existing table. D38 was therefore broken-on-upgrade for
any pre-existing database — `features build` hard-crashed — while the entire test suite passed,
because every other test builds a fresh in-memory database. Also fixed: the ablation's own
fold-pairing (which produced a plausible-looking but fabricated +13.69 MAE result before being
caught as implausible), and `load_rookie_class_data` hardcoding the production feature list.
`tests/unit/test_schema_migrations.py` now builds the *old* schema first — the one case the suite
never exercised. 254 offline tests passing. See D39 for the full account.


## Post-M13: the incoming rookie class is now projectable (D40)

The app was showing the 2025 rookie class in August 2026 — a backtest presented as a forecast,
with the incoming class missing entirely. Three chained defects: nflverse's `players` file lags
the draft (all 694 `rookie_season=2026` rows have NULL draft capital) while `draft_picks` already
has the full 2026 draft but keys it on `esb_id` rather than `gsis_id` for that class only; the
spine upsert could never refresh draft capital once a row existed; and `rookie_features` is by
construction a *labeled* table that cannot hold a class whose season hasn't been played.

Fixed with an esb_id-fallback COALESCE in the spine build, a COALESCE-refresh on the upsert, and
a new `rookie_projection_features` + `alpha-squad train rookie-project --draft-class 2026`, which
writes predictions but deliberately no evaluation metrics (there is no outcome to score against).
The feature SQL and the imputation are shared verbatim between the labeled and unlabeled paths so
they cannot drift. The UI now asks the API which classes exist and defaults to the newest instead
of a hardcoded year.

2026 projection (trained on classes 2000-2025, 234 players): Jeremiyah Love 233.3 / 88%,
Carnell Tate 202.8 / 48%, Fernando Mendoza 196.3 / 86%, Ty Simpson 177.4 / 57%, KC Concepcion
139.9 / 15%. 259 offline tests passing.

**Known limitation:** Rankings, EDGE and League still default to the 2025 season, because the
data behind them genuinely stops at 2025 — projecting the 2026 NFL season for established players
is separate work. Changing those defaults without generating the data would show empty views.

## M15 summary — user-facing productization (D53)

Full detail in D53. The short version: the intelligence existed (M1-M14) but nothing let an actual
fantasy manager connect their real league and be told what to do. This milestone is the connect →
understand → analyze → decide → explain path, built entirely on top of already-tested M1-M13
tables and M10 recommendation functions — no new scoring or decision logic anywhere, frontend or
backend.

New: runtime Sleeper league onboarding (validated live before persisting, `registered_leagues`
table), real roster import bridged to canonical player ids, My Team roster intelligence, an Action
Center (ranked ADD/DROP/TRADE — three lists, not one fabricated composite score), batch waiver
ranking, a Player Detail view that explicitly separates universal player value from my-league
value for the same player, and Draft/Dashboard/multi-asset Trade-package views. A shared
`LeagueProvider` context replaced every view's own independent league dropdown.

Exercising the whole thing end to end with Playwright against a real backend and a real Sleeper
league (rather than trusting the code) found and fixed six real bugs: three DuckDB/refetch
concurrency issues (`init_db` running per-request instead of once at startup; `build_action_center`
re-fetching the live roster 3-4x per request; `duckdb.connect()` itself racing under concurrent
requests), a Sleeper snapshot-filename collision (missing the `param_suffix` fix already applied to
the other three source adapters), a non-atomic snapshot write that raced under concurrent
same-key reads (reproduced directly: 5,292 torn reads out of ~2,000 concurrent reads against the
old pattern, 0 against the fix), and a UI bug where a success confirmation was unmounted in the
same render batch that set it, so it never painted. Every fix has a regression test verified to
fail without the fix.

350 offline tests passing (up from 303); `make lint` clean; `tsc --noEmit` clean. Not built:
runtime "connect" for a manual/YAML league — `teams_for_league` returns `None` rather than
fabricating a roster for it, and the UI says so rather than showing a broken or fake roster.

## M16 summary — empirical validation & benchmarking phase (D54)

M15 productized the intelligence; M16 asked the harder question the product-facing work never
answered: does Alpha's intelligence actually produce better fantasy-football decisions than
strong, reasonable baselines, adversarially tested rather than assumed? Full methodology in
`docs/EVALUATION_PLAN.md`, real-data constraints in `docs/EVALUATION_LIMITATIONS.md`, full
results in `docs/ALPHA_VS_BASELINES_EVALUATION.md`, and the pre-registered-before-results
commitments plus a condensed results summary in `docs/DECISIONS.md` D54.

New `src/alpha_squad/evaluation/` package (8 modules, each also an `alpha-squad evaluate <name>`
CLI command): projection benchmarking against 3 baselines, a 5-tier market-inefficiency
stratification, a reusable historical draft-simulation engine (4 strategies x 5 real seasons x
10 draft slots), waiver-tier value discovery, rookie-vs-baseline benchmarking by round tier,
dynasty pick-value/age-curve validation against real outcomes, trade-evidence extraction, and
failure analysis. Every threshold, strategy, and season range was fixed in source and documented
in D54 *before* being run against real data.

**The headline result is unfavorable, and reported as such.** Alpha's underlying player-value
model (`ml_season_catboost`) beats every baseline on MAE at every position — the modeling layer
is validated. But the real historical draft simulation shows `alpha_league_aware` (the actual
production draft recommender) losing to plain market consensus on mean starter points in
**every one of the 5 real seasons tested**, never winning a single season outright, and scoring
below `alpha_bpa` (identical player values, no league context) on pooled total roster points
(though it *beats* `alpha_bpa` on pooled starter points — a real, mixed nuance: league context
helps the started lineup, it just strands more value on the bench overall). Root-caused not
just from the final rosters but by replaying the real `recommend_draft_pick` function
pick-by-pick against real 2021 data: the recommender drafted 7 QBs and zero RBs into a league
starting 2 of each in one real trial, and 12 WRs against only 3 QBs in another. Two compounding
mechanisms: `roster_fit_multiplier`'s real penalty growth is far gentler than its [0.7, 1.3]
bound implies (only a 6% discount at the 7th same-position pick, verified by direct
computation), nowhere near enough to overcome a real VORP edge; and the other 9 real
market-consensus opponents drain the scarce position at a normal rate throughout, so by the
time need-pressure would organically correct course, no usable players are left at that
position (round 16 of the replayed draft: best available RB had VORP -135.4). This is a
decision-logic bug, not a modeling one, and is the single most actionable finding of this
phase.

**A fix for the first mechanism was implemented and re-verified against a full re-run, per
explicit request.** `roster_need`'s oversaturation coefficient was steepened so
`roster_fit_multiplier` hits its 0.7 floor immediately at one player past a full bench,
instead of ~15 extra players. Result, reported honestly rather than oversold: pooled starter
points improved 1644.5 -> 1688.2 (+2.7%, a real gain in the metric that actually determines
fantasy outcomes) and the replayed 2021 roster's QB count dropped 7 -> 6, but pooled total
points worsened 2680.0 -> 2606.6 (a real tradeoff, not a free win). The fix does **not** close
the gap — `alpha_league_aware` still loses all 5 seasons (0/5 wins, unchanged) and still
trails `market_consensus` by 332.5 pts pooled (down from 376.2, ~12% of the gap closed). The
2021 roster still drafted zero RBs even after the fix, confirming the second mechanism
(positional-scarcity blindness) is untouched and is now the clearly-identified remaining work.

This finding was independently re-verified after the fact, prompted by a direct question about
whether pre-2025 training data was genuinely separated from 2025 outcomes: that audit found and
fixed two real bugs in the draft-simulation path itself (not methodology changes) —
`next_pick_survival_probability` had no season scoping at all (a historical draft could see
market data recorded years later), and several `min`/`max`/`.sort()` calls broke ties over
Python `set`s with no secondary key, which is non-deterministic across process runs because
`PYTHONHASHSEED` is unset here and real ties are common in the data. Both fixed with regression
tests, then verified (not assumed) by re-running the simulation twice in separate processes and
confirming byte-identical reports. The corrected numbers required one factual fix — an earlier
claim that market consensus won outright in all 5 seasons was wrong; it wins 4 of 5, with
`generic_prior_year` edging it out in 2025 specifically — but the core finding (Alpha's draft
engine never wins) is unchanged and now rests on a leak-free, reproducible basis.

Two other results are worth flagging: the 5-tier market-inefficiency test validates the
existing EDGE evidence gate (D21) specifically — raw disagreement magnitude alone is *not*
monotonic with outcome, only the evidence-gated BUY/SELL tier is — and Alpha's rookie model's
real edge is concentrated in late rounds (5-7) where draft capital alone is weak, while
early/mid rounds remain a genuine draft-capital-baseline win. Four real software bugs (a
position-misclassification and a season-intersection bug in `projection_benchmark.py`, the two
draft-simulation bugs above, plus a `zip(..., strict=True)` crash that only triggers on a
cleanly monotonic result) were found and fixed by this phase's own test suite before any
number was treated as final — see D54.

## M17 summary — draft-engine forensic audit (diagnostic phase, not a redesign)

M16 found and partially fixed the draft engine's roster-balance failure; this phase's explicit
purpose was to diagnose *why* it happens before attempting any further fix, per its own
instruction not to tune the engine against benchmark results. Full account:
`docs/DRAFT_ENGINE_FORENSIC_AUDIT.md` (root cause), `docs/DRAFT_CONTROLLED_EXPERIMENTS.md`
(ablation results), `docs/DRAFT_ENGINE_REDESIGN_RECOMMENDATION.md` (proposed fix, not
implemented), `reports/draft_decision_trace.json` (machine-readable pick-by-pick traces).

**A real, previously-undocumented finding: `positional_scarcity()` — a real, tested production
function required by `PRODUCT_SPEC.md`/`ACCEPTANCE_CRITERIA.md` and already consulted by the
waiver engine — is never imported or used by the draft engine (`league/draft.py`).** The
acceptance criterion "positional scarcity is calculated" is technically true (the function
exists and is exercised elsewhere) but the actual draft decision never consults it. A second,
related finding: `roster_need`'s "healthy bench depth" assumption (`slots + 2`, a hardcoded
constant) has no relationship to the league's actual configured bench size
(`league.bench_size`, a real property that turned out to be dead code before this phase).

**The core diagnostic finding, from replaying the real, unmodified `recommend_draft_pick`
pick-by-pick against real 2021 and 2025 data:** both traced pathological drafts (the same "7
QB/0 RB" and "12 WR/3 QB" examples from D54) are effectively decided by the team's first 1-2
picks, not a multi-round feedback loop. A real, viable RB was a live top-5 candidate at pick #1
in both cases and fell out of consideration entirely by the team's second pick (19 picks later
across the whole league) — never recovering until the position was already below replacement
level. The engine's score has no representation of "this position depletes fast, secure it now"
at the one point it would have mattered — only a single-candidate survival probability, never a
positional one.

**The simulator itself was validated as sound before trusting any of the above:** 90 real
homogeneous-league drafts (3 independent real strategies — market consensus, raw projected
value, and bare VORP — each drafting all 10 slots, removing the fixed-opponent-field design used
elsewhere) never produced a zero-RB roster once. Only TE occasionally went to zero, matching the
well-known, legitimate real fantasy strategy of "punting" a shallow-demand position — not a
simulator defect. This directly rules out the simulator and the player-projection model (already
separately validated, D54 §1) as root causes.

**Controlled ablation at full scale (400 real drafts: 5 seasons × 10 slots × 8 tiers, each tier
adding one mechanism from the directive's list on top of the last) confirms the single-slot
finding generalizes, with one important, counter-intuitive refinement.** The real production
engine zeros RB in 10 of 50 trials — concentrated entirely in the real 2021 season (10/10 slots
that year, 0/10 in every one of 2022-2025; why 2021 specifically remains open). Adding current
positional scarcity, analytical future scarcity, or a literal opponent-behavior replay each made
the RB=0 rate *worse* (32%, 32%, and 36% respectively) than plain roster-fit alone (20%) — a
real, tested, negative result, not smoothed over: `positional_scarcity()`, the exact real
production function required by `PRODUCT_SPEC.md` and already used by the waiver engine, rates
QB as the most "scarce" position in real 2021/2023 data and RB as one of the least, reinforcing
the QB-stacking side of the same pathology rather than fixing the RB side. Only an explicit,
points-denominated opportunity-cost term (Experiment F) both cut the RB=0 rate to 4% and
improved mean starter points above the current production engine (1789.1 vs. 1688.2 pooled,
winning 4 of 5 real seasons) — despite inheriting the same QB-favoring scarcity distortion every
other tier from C onward carries, making its improvement the more notable for overcoming that
headwind rather than avoiding it.

**No further fix was implemented in this phase, per its own explicit instruction.** The
recommendation is a moderate-complexity addition (an explicit per-position opportunity-cost
term, priced continuously, using an opponent-behavior replay as its input, deliberately *not*
layering in `positional_scarcity` given the finding above) — not a rebuild, not a hardcoded
positional cap, not a full Monte Carlo lookahead — with the honest
caveat that its sufficiency at full scale, and in combination with the already-landed
saturation-penalty fix, remains `UNKNOWN` and must be measured before being claimed as solved.


## M18 summary — positional opportunity cost shipped to the draft engine (D55)

M17 diagnosed the draft engine's root cause without fixing it; M18 implemented the fix, measured
it on the official benchmark, and recorded what it did and did not achieve. Full account:
`docs/DECISIONS.md` D55.

**The recommendation was not implemented as written, and that mattered.** Verifying
`docs/DRAFT_ENGINE_REDESIGN_RECOMMENDATION.md` against the source before building found its
proposed formula (`production + opportunity_cost`) had never actually been measured: Experiment
F — the number the recommendation rested on — includes `positional_scarcity` (the mechanism the
experiments proved harmful) and excludes production's confidence and survival terms. A new
pre-registered P-tier ablation (300 real drafts, decision rule committed to source before
running) resolved it. The integrated form that won, `(VORP + opportunity_cost) × fit × risk ×
survival × [cap]`, beat both the recommendation's raw additive form and Experiment F itself.

**Measured on the official `alpha-squad evaluate draft-simulation` benchmark, full 2021-2025:**
mean starter points **1688.2 → 1801.1 (+112.9, +6.7%)**. Alpha's draft engine moves from 3rd of
four strategies to 2nd, now ahead of the non-market `generic_prior_year` baseline it previously
trailed. RB=0 rosters fell 10/50 → 2/50. The D54 QB-stacking pathology is materially reduced:
7-and-8-QB rosters (9 of 50 before) no longer occur at all, max QB 8 → 6, concentration index
0.345 → 0.304. All 10 draft slots improved; none regressed. The benchmark reproduced the
diagnostic harness's prediction to the decimal, per season.

**Mechanism verified from the decision trace, not inferred from roster counts.** Re-tracing the
2021 slot-1 pathological draft: pick #1 is now RB where it was TE, and the engine's own reason
string states why — *"RB opportunity cost +60.5 pts"*. The RB wins **despite lower VORP** than
the TE it beat. 2025 slot 1, which never had the pathology, is essentially unchanged: the term
is targeted, not a blanket re-weighting.

**Reported regressions, not just gains:** 2023 lost 6.4 starter points (0.35%); pooled total
roster points dipped 6.8; the feasibility cap fires on every draft both before and after. Most
importantly, **`market_consensus` still leads by 219.6 starter points and Alpha has still never
won a single season against it** — `docs/IMPLEMENTATION_GAP_ANALYSIS.md` P1-0's acceptance
criterion remains unmet. Determinism passed (two separate-process benchmark runs, byte-identical)
and runtime cost is negligible (+0.099 s/call, +3.4%). 474 offline tests passing (up from 450);
lint and `tsc` clean.

## M19 summary — 1-QB target format retarget: Alpha beats consensus (D56–D60)

The product's target format changed from 10-team 2QB dynasty (D7) to 10-team 1-QB redraft
(`docs/TARGET_FORMAT_1QB.md`). This milestone audited every format-dependent assumption in the
codebase against the new format, found that the audit invalidated the project's entire recorded
draft evaluation, re-baselined it correctly, and closed `docs/IMPLEMENTATION_GAP_ANALYSIS.md`'s
P1-0 — the acceptance criterion open since M16. Full account: `docs/DECISIONS.md` D56–D60,
`docs/FORMAT_MIGRATION_DIAGNOSTIC.md`.

**The benchmark itself was wrong, not just the target.** `ecr_type='rsf'` — the board every
prior draft evaluation ran against — is FantasyPros' *superflex* board (9 of the real
preseason-2024 overall top 15 are QBs; the 1-QB board `ro` has none in its top 15). It was the
correct board while the target league was 2QB (D21); it measures a different game now. A second,
independent bug compounded it: `ecr_type` alone is not a rank space — DynastyProcess labels an
IDP board with the same `ecr_type` as the real PPR board, and the pre-fix primary key silently
dropped one of the two whenever they collided on a date (D56). `market_snapshot.page_type` and
`market/series.py::resolve_market_series` fix both; every pre-D56 draft number is retained,
labelled by the format it measured, not restated.

**K and DEF, the new format's two new starting slots, had three separate gaps, all real and now
closed (D57).** Kickers were ingested but scored 0.0 (nflverse prices only
passing/rushing/receiving); team defenses did not exist as an entity anywhere; FantasyPros' DST
market ranks were dropped at ingest. All three are now computed from real data — kicker points
from real FG/PAT components, DST from real defensive stats plus real points allowed, DST market
rank via a 3-entry team-code alias map. Both get measured baselines, not models, with the
weighting chosen by walk-forward MAE over real 2015–2025 seasons (K: weighted 2-year, MAE 33.60;
DST: shrunk hard to the positional mean, MAE 22.55) — an ML model would imply precision neither
signal supports (K r=0.41, DST r=0.29 year-over-year).

**Two format-shaped defects in previously-correct mechanisms (D58).** Positional capacity split
the bench evenly across dedicated positions and ignored FLEX entirely — survivable at 4
positions and a 2-QB lineup, first-order wrong once K/DEF joined the lineup (RB capped at 3 in a
league starting 2 RB + up to 2 FLEX). `roster_need`'s depth target was the arbitrary constant
`slots + 2`. Both now derive from the league's own config (`positional_capacity`,
`startable_slots`). The config's own roster arithmetic was inconsistent (9 starters + 10 bench
declared alongside `roster_size: 17`); now 10 + 6 = 16, asserted by test for every shipped
config.

**Re-baselined, with no engine change: Alpha already won.** `alpha_league_aware` (D55's shipped
formula, unmodified) on the corrected `ro` board and 1-QB config: 1927.8 mean starter points vs.
`market_consensus`'s 1825.2 (+102.6, +5.6%), 34/50 (68%) win rate, winning 4 of 5 seasons — the
reverse of every pre-D56 result (D59).

**Marginal starter value, measured and shipped (D60).** The audit re-asked M17's open question
under the new format rather than assuming the answer transferred: does the engine understand
whether a candidate would actually improve the team's starting lineup? It did not — VORP prices
against league-wide replacement level, `roster_need` against a positional count, neither knows
whether a specific candidate would start *on this specific roster*. `marginal_starter_value`
supplies that. A pre-registered M-tier ablation (200 real drafts) found replacing VORP with it
outright (tier M3) strictly won: +109.7 starter points (+5.8%), 37/50 win rate, zero infeasible
rosters — and was the only tier that fixed a real, previously invisible defect: the VORP-based
formula drafted a mean 3.78 kickers and 2.26 defenses per 16-round draft, because a bench K/DST
still scores positive VORP despite zero chance of ever starting (neither has flex eligibility).
Shipped as an additive, backward-compatible parameter (`roster_player_ids`) so callers without
real per-team roster tracking see no behavior change.

**Official benchmark, full 2021–2025, determinism verified:**

| Strategy | Mean starter pts | vs. consensus |
|---|---|---|
| `alpha_league_aware` (D60) | **1990.9** | **+165.7 (+9.1%)** |
| `market_consensus` | 1825.2 | — |

Win rate: **37/50 (74%)**. Wins 4 of 5 seasons; 2024 is a near-miss (−10.1, down from D55's
−80.1 measured under the same board). Two separate-process runs are byte-identical
(`md5 5e0ec53e...`). **`docs/IMPLEMENTATION_GAP_ANALYSIS.md` P1-0's acceptance criterion is now
met** — the fix that closed it was selected by a pre-registered decision rule measured against
the corrected benchmark, not chosen to hit the target.

602+ offline tests passing (up from 474); lint and `tsc` clean. New: `market/series.py`,
`features/kicking_defense.py`, `models/baselines/kicking_defense.py`,
`evaluation/pick_attribution.py`, M-tiers in `evaluation/draft_forensics.py`,
`docs/TARGET_FORMAT_1QB.md`, `docs/BENCHMARK_SPEC.md`, `docs/FORMAT_MIGRATION_DIAGNOSTIC.md`.
