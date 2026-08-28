# Evaluation Plan

The empirical-validation phase's methodology, fixed here before results were examined
(docs/DECISIONS.md D54). Companion documents: `docs/ALPHA_VS_BASELINES_EVALUATION.md` (the
results), `docs/EVALUATION_LIMITATIONS.md` (what can't be measured here and why).

## The question this phase answers

Not "does the system work" (M1-M15 already established that) but: **does Alpha's
intelligence actually produce better fantasy-football decisions than strong, reasonable
alternatives, and where does it not?** Every sub-question below has a real, checkable answer
in this codebase's real data -- not a demo, not an assumption.

## Principle: this evaluation is adversarial by construction

Every comparison in this phase reuses the exact same scoring harness for Alpha and for every
baseline (`models/evaluate.py::evaluate_and_record` for point predictions and classification;
the same real `player_season_stats`/`edge_validation_results` tables for backtests). No
baseline is deliberately weakened, and no threshold or methodology choice was revisited after
seeing an unfavorable result -- see `docs/EVALUATION_LIMITATIONS.md`'s "methodology
commitments" section for the specific commitments this rules out.

## Framework: `src/alpha_squad/evaluation/`

A new package, not a set of one-off scripts, so every analysis here reruns unchanged after a
future model update:

| Module | Question it answers | Reuses |
|---|---|---|
| `config.py` | Versioned config stamped into every report/JSON artifact | -- |
| `projection_benchmark.py` | Does Alpha's player intelligence beat baselines A/B/C? | `evaluation_results` (M4/M5, already computed) |
| `market_inefficiency.py` | Does disagreement magnitude/confidence/evidence predict outcome? | `edge_snapshot`, `market/edge.py`'s walk-forward market-implied-points curve |
| `draft_simulation.py` | Draft evaluation + league-aware-vs-generic + roster-aware, in one engine | `recommend_draft_pick` (M10), `load_season_projections` (M6/M7), real preseason market consensus |
| `waiver_evaluation.py` | Waiver/FAAB value discovery (preseason proxy -- see limitations) | `load_season_projections`, `previous_year_baseline` |
| `rookie_benchmark.py` | Rookie evaluation vs. draft-capital and market-ECR baselines, by round tier | `rookie_predictions` (M7), two new walk-forward baselines |
| `dynasty_validation.py` | Do pick-value/age-curve heuristics match real outcomes? | real `players.draft_round`/`birth_date`, `player_season_stats` |
| `trade_evaluation.py` | What trade-recommendation quality claims are/aren't supported | `edge_validation_results` (the signal `recommend_dynasty_trade`'s action reads) |
| `failure_analysis.py` | Concrete named misses, not just aggregate stats | `edge_snapshot`, `rookie_predictions`, real outcomes |

Every module is also a CLI command (`alpha-squad evaluate <name>`), writing a markdown report
under `reports/` (gitignored, reproducible) plus, where the result is a structured list rather
than a one-off table, a persisted DuckDB table (`draft_simulation_results`) so later analysis
doesn't require re-running an expensive simulation.

## Sub-questions and how each is answered

1. **Does Alpha's player intelligence outperform simple baselines?** `evaluate
   projection-benchmark` -- previous-year, weighted-2yr, ECR-implied vs. Alpha's season-level
   Ridge/CatBoost/XGBoost, over the real season-intersection window, by position.
2. **Does Alpha outperform market consensus?** The same report's ECR-implied baseline row IS
   this comparison (ECR-implied is the market-consensus baseline, D16/D17).
3. **Does Alpha's EDGE signal identify useful market discrepancies?** `evaluate
   market-inefficiency` -- five-tier disagreement-magnitude stratification, testing whether
   `mean_signed_edge` actually increases from "agrees with market" to "evidence-backed
   disagreement."
4. **Does league-aware decision-making improve decisions over generic rankings?** `evaluate
   draft-simulation` -- `alpha_league_aware` vs. `alpha_bpa` (identical Alpha predictions, only
   roster context/VORP differ) isolates exactly this variable.
5. **Do Alpha's draft recommendations outperform reasonable alternatives?** The same report --
   `alpha_league_aware` vs. `market_consensus`/`generic_prior_year`.
6. **Do Alpha's waiver/FAAB recommendations create useful value?** `evaluate waiver-tier` --
   see limitations for what this can and can't claim.
7. **Does Alpha's trade/roster intelligence improve decisions?** `evaluate trade-evidence`
   (trade) + the draft simulation's `starter_points` metric (roster construction quality,
   real optimal-lineup value from a real drafted roster).
8. **Where does Alpha fail?** `evaluate failure-analysis` -- concrete named misses.
9. **Where is evidence insufficient to claim an advantage?** `docs/EVALUATION_LIMITATIONS.md`,
   and every report's own "reading this honestly" / sample-size section.

## Reproducing this phase's results

```
alpha-squad evaluate projection-benchmark --season-start 2020 --season-end 2025
alpha-squad evaluate market-inefficiency --season-start 2022 --season-end 2025
alpha-squad evaluate draft-simulation --season-start 2021 --season-end 2025
alpha-squad evaluate waiver-tier --season-start 2020 --season-end 2025
alpha-squad evaluate rookie-benchmark --draft-class-start 2019 --draft-class-end 2024
alpha-squad evaluate dynasty-heuristics --draft-year-end 2023
alpha-squad evaluate trade-evidence --season-start 2022 --season-end 2025
alpha-squad evaluate failure-analysis
```

Each requires the upstream pipeline it reads from to have already been run (`features build`,
`train uncertainty`, `train rookie`, `edge build`/`edge validate`, `market build-dynasty-values`
as applicable) -- these commands only evaluate already-computed intelligence, they don't
regenerate it.

## What "done" means for this phase

Not "the framework runs." Every report must state its real n, its real season/class window,
and an honest reading of whether the result is a confident claim or an inconclusive one. A
report that only shows Alpha winning, with no failure analysis and no stated limitation, has
not met this phase's bar regardless of whether the code executes without error.
