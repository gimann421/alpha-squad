# Fantasy Football ML/AI — Definitive Product Specification

## Status
Authoritative implementation package for Claude Code autonomous build.

## Source of truth
This document consolidates the previously approved project requirements. It preserves the original product goal: build a transparent, reproducible fantasy-football intelligence system that finds market inefficiencies rather than merely copying expert rankings.

### Core outputs
The system must ultimately support:
- redraft preseason projections/rankings
- dynasty rookie rankings
- dynasty overall rankings
- in-season rest-of-season rankings
- player projection ranges and probabilities
- model-vs-market EDGE scores
- evidence explaining outliers
- draft recommendations
- waiver/FAAB recommendations
- dynasty/roster decisions
- league-specific recommendations

## Product principle
Do not build one giant black-box model. Combine:
1. historical/statistical ML
2. opportunity/team-environment modeling
3. rookie prospect modeling
4. market consensus
5. current information
6. uncertainty/risk modeling

The higher-value objective is identifying players whose expected fantasy value materially differs from market price.

## Universal player intelligence vs league decision engine
These are separate layers.

### Universal player intelligence
Produces league-independent:
- projections
- rankings
- uncertainty
- top-X probabilities
- rookie probabilities
- market comparison
- evidence-backed player signals

### League-specific decision engine
Consumes universal intelligence plus:
- scoring
- roster settings
- number of teams
- lineup requirements
- roster
- draft position/state
- available players
- opponents
- FAAB
- waiver rules
- future picks
- league type

It produces:
- best pick and alternatives
- roster-fit value
- positional scarcity/replacement value
- waiver/FAAB recommendations
- trade/hold/buy/sell recommendations

A player's universal value must not be retrained specifically for one league.

## Modeling
Established players: separate QB/RB/WR/TE models. Initial stack:
- previous-season baseline
- weighted 2-year baseline
- regularized linear model
- CatBoost
- XGBoost challenger
- opportunity model
- team environment model

Rookies are a separate model because they lack NFL production. Features include:
- draft round/pick/draft capital
- age
- college production and market share
- breakout age
- efficiency
- athletic testing
- conference/competition
- NFL team/environment
- depth chart/veteran competition
- current camp/preseason information

Targets:
- fantasy relevance probability
- rookie-year production
- top-12/top-24 probability
- dynasty trajectory
- 2-year production
- career relevance where supportable

## Market
Track and weight:
- FantasyPros ECR
- FantasyPros ADP
- Sleeper market signals
- dynasty ADP where available
- KTC as a separate dynasty signal
- expert rankings weighted by demonstrated accuracy

Do not treat any market source as truth.

## EDGE
For each player calculate:
- model rank
- weighted market rank
- rank edge
- projected-points edge
- probability edge
- evidence score
- confidence
- action: BUY/HOLD/SELL/WATCH

Raw rank difference is not sufficient. A strong signal requires model discrepancy, market discrepancy, supporting evidence, and reasonable confidence.

## Evidence
Strong:
- official depth-chart promotion
- repeated first-team usage
- actual snap/route/target data
- injury creating clear opportunity
- roster transaction
- repeated practice usage

Medium:
- repeated beat observations
- coach comments
- one strong practice

Weak:
- one highlight
- generic praise
- social media
- speculative fantasy commentary

Current information updates the prior; it does not automatically override it.

## Uncertainty
Every player should have:
- p10
- p25
- median
- p75
- p90
- confidence
- top-X probabilities

Use conformal prediction or another calibrated interval method.

## Simulation
Eventually support team-season simulations:
1. plays
2. pass/rush split
3. points
4. player opportunity
5. efficiency
6. player outcomes

Support correlated outcomes, QB/WR stacks, team scoring uncertainty, floor/ceiling.

## League optimizer
The existing target league is:
- 10 teams
- 2 QB
- 2 RB
- 2 WR
- 1 TE
- 2 FLEX

The architecture must support arbitrary league settings, while being able to represent this league exactly.

The optimizer must calculate:
- replacement level
- positional scarcity
- marginal points over replacement
- roster construction
- future value
- expected value of a pick
- probability a player survives to the next pick
- roster fit
- risk-adjusted value

Waiver/FAAB should incorporate:
- meaningful-role probability
- expected fantasy value
- dynasty value
- value-spike probability
- roster fit
- replacement player
- competing-bid likelihood
- FAAB budget/rules

## Data
Core:
- nflverse
- FantasyPros API
- CollegeFootballData
- Sleeper API
- official NFL/team current information

Do not make v1 depend on:
- direct PFR scraping
- paywalled proprietary rankings
- proprietary PFF grades
- raw proprietary NGS
- paid scouting databases
- undocumented endpoints

Respect API terms and licensing. Never fabricate unavailable data.

## Historical integrity
Every market/evidence/projection record must preserve captured_at/effective date where available. Historical prediction must use only information available on the prediction date.

Never use random train/test splits for primary time-series evaluation.

## Canonical identity
Never join production data on name alone. Maintain explicit source-ID mappings and an exception queue for ambiguity.

## Data model
DuckDB initially; Parquet for large datasets. Required logical entities:
- players
- player_ids
- nfl_player_season
- team_season
- college_player_season
- combine
- market_snapshot
- projection_snapshot
- evidence_events
- model_prediction
- edge_snapshot

## Data quality
Fail loudly on:
- duplicate IDs
- bad mappings
- impossible values
- missing required identity
- fantasy/team reconciliation failures
- invalid share/rank bounds
- stale timestamps

Do not silently turn missing data into zero unless zero is semantically correct.

## Evaluation
Track:
- MAE
- RMSE
- R²
- Spearman
- Kendall
- top-12/top-24 hit rates
- tier accuracy
- Brier score
- calibration
- BUY/SELL performance
- points above market expectation
- simulated draft ROI where possible
- FAAB ROI where possible

Every model must be compared against:
- previous-year baseline
- weighted historical baseline
- FantasyPros ECR
- FantasyPros projection
- ADP-implied value where appropriate

If ML does not beat an appropriate baseline out of sample, do not hide it and do not declare the model superior.

## Research memory/provenance
Persist:
- player signal history
- projection changes and reasons
- expert rankings and accuracy
- model versions/performance/calibration/failures
- source reliability
- evidence provenance

Every major recommendation must be traceable to data/model/evidence versions.

## Interface/application
The existing requirements prioritize a reproducible data/model pipeline before UI. Once the validated core exists, implement an application/interface that exposes the required product capabilities rather than inventing a separate generic dashboard:
- player rankings/projections
- EDGE and evidence
- rookie evaluation
- draft decision support
- league context
- waiver/FAAB recommendations
- roster-aware decisions
- explanation of recommendation changes
- provenance/last-updated state

The exact UI technology may be chosen by Claude Code after inspecting the repository and environment, unless an existing project constraint requires otherwise.

## Non-goals
- do not optimize for model complexity
- do not make one analyst the authority
- do not build around unavailable proprietary data
- do not overreact to camp hype
- do not claim completion because a scaffold or demo runs
