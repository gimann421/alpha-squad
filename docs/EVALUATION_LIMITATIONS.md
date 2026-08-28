# Evaluation Limitations

Companion to `docs/EVALUATION_PLAN.md` and `docs/ALPHA_VS_BASELINES_EVALUATION.md`. Every
limitation below was found by checking what data this environment actually has before
building an analysis around it, not discovered after the fact as an excuse for a weak result.
Per CLAUDE.md and the empirical-validation directive: identify the limitation, quantify it
where possible, use the strongest defensible evaluation given it, and label the result
LIMITED rather than silently narrowing scope or fabricating missing history.

## Data windows (checked against the live database, docs/DECISIONS.md D54)

| Table / signal | Real coverage | Why it can't be widened without fabricating |
|---|---|---|
| `uncertainty_predictions` (M6, walk-forward season-level projections) | 2021-2025 | Requires a prior season of features to train on; the pipeline has only been run for these target seasons in this deployment. |
| `edge_snapshot` (M8 EDGE) | 2022-2025 (`rsf`) | Built on top of `uncertainty_predictions` + market data; inherits its window. |
| `rookie_predictions` / rookie classification | 2019-2025 draft classes | M7's walk-forward rookie pipeline range. |
| `evaluation_results` (baselines + Alpha season-level ML) | 2019-2025 (baselines), 2020-2025 (Alpha `ml_season_*`) | Real walk-forward run history; the intersection of the two is what `evaluate projection-benchmark` reports. |
| `weekly_projection_snapshot` (Alpha's own weekly, in-season predictions) | **2025 only** | D46 was the first real run of the weekly established-ML pipeline against this deployment's data. A genuine multi-season weekly (in-season/waiver-relevant) backtest does not exist yet. |
| `market_snapshot` (ECR/dynasty market consensus) | 2019-2026 (various `ecr_type`) | Real historical mirror (DynastyProcess) plus live captures from 2026-08-23 forward. |
| `dynasty_values` | **one current snapshot only** (2026-08-21) | No historical dynasty-value time series is retained -- each build overwrites the prior snapshot. A real "did this player's dynasty value actually decay the way the age curve predicts, over time" study is not buildable from this table; see the pick-value/age-curve validation below for the workaround. |
| Sleeper real per-team roster/transaction history | **two current live leagues only** | No historical (past-season) roster or add/drop/FAAB-bid log for any league is reachable in this environment -- Sleeper's API serves the current state of leagues this project has access to, not multi-year transaction history for arbitrary past leagues. |

## What this rules out, specifically

**A true historical FAAB-bidding backtest (directive section 8, in full).** Bid efficiency,
opportunity cost, and competing-bid likelihood all need a real log of who was actually
available, what was actually bid, and by whom, week by week, in real past leagues. That does
not exist here. `evaluation/waiver_evaluation.py` builds the strongest defensible substitute:
a preseason waiver-tier value-discovery proxy using six real seasons of walk-forward Alpha
predictions, explicitly labeled as not a FAAB simulation. See its module docstring for the
full reasoning.

**A multi-season in-season/weekly waiver backtest.** Alpha's own weekly predictions
(`weekly_projection_snapshot`) only exist for 2025 -- one season is not a walk-forward
backtest. The waiver-tier proxy above uses the season-level model instead specifically to get
six real seasons rather than one.

**FantasyPros point projections (directive section 6, Baseline D) as a historical baseline.**
`sources/fantasypros.py`'s `projections` dataset is real and reachable (AVAILABLE, D37), but
`market_snapshot`'s own schema comment records why it can't retroactively benchmark past
seasons: live FantasyPros captures only accumulate forward from 2026-08-23 (D38). There is no
season where both a real FantasyPros point projection AND a completed real season outcome
exist to score against. Not included in `evaluate projection-benchmark`'s comparison table for
this reason -- the report states this explicitly rather than silently omitting the row.

**A genuine ADP series (directive section 6, Baseline E; section 7's ADP-based draft
strategy).** No ADP product was ever ingested in this environment (D17) -- FantasyPros ADP
access was not part of the sources this project's environment reaches. `market_snapshot`'s
ECR-implied series is the documented substitute throughout this project (D16/D17), reused here
for the same reason: it is the closest real market-ranking signal actually available, not
because it is equivalent to ADP.

**A causal trade-outcome study (directive section 15).** "Did accepting this recommended
trade actually improve the roster" needs real historical trade transaction logs across
multiple seasons of real leagues. Not available. `evaluation/trade_evaluation.py` instead
states plainly what a trade recommendation's action *does* inherit real validation from (the
same EDGE signal `market/edge.py` already backtests) and what it doesn't (the heuristic value
numbers, separately checked in `evaluation/dynasty_validation.py`).

**A rookie-specific ECR/ADP product.** No such product was separately ingested. The rookie
benchmark's "market ECR" baseline reuses the real dynasty ECR (`market_snapshot`, `ecr_type='do'`)
filtered to that player's own rookie season -- a genuine real market signal for rookies, not a
fabricated rookie-only series.

## Known confounds in analyses that ARE built

**Age-curve validation (`evaluation/dynasty_validation.py`) has real survivorship bias.** A
player who declines sharply typically leaves the league -- and this dataset -- rather than
posting a bad season in it. The "still active at age 33" cohort in the age-curve table is a
selected group of unusually durable players, not a random sample of every player who was ever
33. A flatter-than-expected empirical decline at older ages is consistent with the heuristic
being wrong, but equally consistent with this selection effect. The report states this; it
does not adjudicate between the two explanations.

**The draft simulation's opponent field is a simplification.** Nine of ten league slots
always draft by real preseason market consensus (best-ECR-available). Real human opponents in
a real draft do not all behave identically -- some reach for need, some hoard upside, some
follow their own private rankings. Fixing the opponent field is what makes the team-in-question
comparison controlled (see `evaluation/draft_simulation.py`'s module docstring), but it means
the *absolute* roster-point numbers in that report describe "against a market-consensus-only
field," not "against a real live draft room."

**Small samples throughout.** Rookie draft classes have roughly 10-25 skill-position players
with meaningful usage; a round tier within one position within one class can be single digits.
The draft simulation has at most 5 seasons x 10 slots = 50 trials per strategy. Every report
this phase produces states its real n and warns against treating any single cell as a
confident claim on its own -- see each report's own "reading this honestly" section.

## Methodology commitments (directive section 24)

- Every threshold used to bucket a continuous signal (market-inefficiency tiers, waiver-tier
  rostered-cutoff) was fixed in the module's source code before that module was run against
  real outcomes -- see `docs/DECISIONS.md` D54 for the commit history establishing this.
- No evaluation method was changed after seeing an unfavorable result. Where D54 records a
  methodology decision made *because* of something learned while building (e.g. widening a
  season window, fixing a real bug), that is documented as such, distinct from tuning a metric
  to move a result.
- Every baseline this phase adds (draft-capital rookie baseline, rookie market-ECR baseline)
  writes through the exact same shared harness (`models/evaluate.py`) Alpha's own models use --
  no separate, more forgiving scoring path exists for baselines or for Alpha.
