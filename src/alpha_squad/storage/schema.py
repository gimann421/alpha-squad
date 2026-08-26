"""DuckDB schema, grown milestone by milestone. Each milestone appends its DDL to ALL_DDL
rather than replacing earlier statements; `init_db()` applies all of them with
CREATE TABLE IF NOT EXISTS, so re-running it is always safe and idempotent."""

from __future__ import annotations

M1_SNAPSHOTS_DDL = [
    """
    CREATE TABLE IF NOT EXISTS snapshot_registry (
        snapshot_id VARCHAR PRIMARY KEY,
        source VARCHAR NOT NULL,
        dataset VARCHAR NOT NULL,
        captured_at TIMESTAMP NOT NULL,
        url VARCHAR NOT NULL,
        local_path VARCHAR NOT NULL,
        sha256 VARCHAR NOT NULL,
        rows BIGINT,
        columns_json VARCHAR,
        params_json VARCHAR,
        created_at TIMESTAMP NOT NULL DEFAULT current_timestamp
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS source_health_log (
        checked_at TIMESTAMP NOT NULL,
        source VARCHAR NOT NULL,
        dataset VARCHAR NOT NULL,
        status VARCHAR NOT NULL,
        detail VARCHAR
    )
    """,
]

M2_IDENTITY_DDL = [
    """
    CREATE TABLE IF NOT EXISTS players (
        player_id VARCHAR PRIMARY KEY,
        gsis_id VARCHAR UNIQUE NOT NULL,
        display_name VARCHAR,
        first_name VARCHAR,
        last_name VARCHAR,
        position VARCHAR,
        position_group VARCHAR,
        birth_date DATE,
        college_name VARCHAR,
        draft_year INTEGER,
        draft_round INTEGER,
        draft_pick INTEGER,
        draft_team VARCHAR,
        rookie_season INTEGER,
        last_season INTEGER,
        status VARCHAR,
        source_snapshot_id VARCHAR,
        created_at TIMESTAMP NOT NULL DEFAULT current_timestamp
    )
    """,
    # (id_type, id_value) is PRIMARY KEY: one external ID can belong to exactly one
    # canonical player. Build code must detect collisions and quarantine them into
    # identity_exceptions *before* insert (see identity/canonical.py) rather than relying
    # on this constraint to fail the whole build — but the constraint stays as a hard
    # backstop against a build-code bug silently corrupting the crosswalk.
    """
    CREATE TABLE IF NOT EXISTS player_id_map (
        id_type VARCHAR NOT NULL,
        id_value VARCHAR NOT NULL,
        player_id VARCHAR NOT NULL REFERENCES players(player_id),
        source VARCHAR NOT NULL,
        source_snapshot_id VARCHAR,
        created_at TIMESTAMP NOT NULL DEFAULT current_timestamp,
        PRIMARY KEY (id_type, id_value)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS player_college_bridge (
        player_id VARCHAR PRIMARY KEY REFERENCES players(player_id),
        cfb_player_id VARCHAR,
        cfb_id VARCHAR,
        source_snapshot_id VARCHAR,
        created_at TIMESTAMP NOT NULL DEFAULT current_timestamp
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS identity_exceptions (
        exception_id VARCHAR PRIMARY KEY,
        exception_type VARCHAR NOT NULL,
        status VARCHAR NOT NULL DEFAULT 'PENDING',
        subject VARCHAR NOT NULL,
        detail_json VARCHAR NOT NULL,
        detected_at TIMESTAMP NOT NULL,
        resolved_at TIMESTAMP,
        resolution_note VARCHAR
    )
    """,
]

M3_FEATURES_DDL = [
    # Derived from pbp (nflverse publishes no separate schedules/games release tag —
    # verified). One row per game with its real calendar date, the anchor for every
    # as-of/leakage check downstream.
    """
    CREATE TABLE IF NOT EXISTS games (
        game_id VARCHAR PRIMARY KEY,
        season INTEGER NOT NULL,
        week INTEGER NOT NULL,
        game_type VARCHAR,
        game_date DATE NOT NULL,
        home_team VARCHAR,
        away_team VARCHAR,
        source_snapshot_id VARCHAR
    )
    """,
    # Normalized weekly outcomes, identity-joined once here rather than re-joined ad hoc by
    # every feature query. This is the ground truth a model is trained to predict, and also
    # the raw material lag features are computed from.
    """
    CREATE TABLE IF NOT EXISTS player_week_stats (
        player_id VARCHAR NOT NULL REFERENCES players(player_id),
        season INTEGER NOT NULL,
        week INTEGER NOT NULL,
        game_id VARCHAR NOT NULL REFERENCES games(game_id),
        game_date DATE NOT NULL,
        team VARCHAR,
        position VARCHAR,
        targets DOUBLE,
        carries DOUBLE,
        receptions DOUBLE,
        target_share DOUBLE,
        air_yards_share DOUBLE,
        passing_yards DOUBLE,
        passing_tds DOUBLE,
        passing_interceptions DOUBLE,
        rushing_yards DOUBLE,
        rushing_tds DOUBLE,
        receiving_yards DOUBLE,
        receiving_tds DOUBLE,
        offense_snap_pct DOUBLE,
        fantasy_points DOUBLE,
        fantasy_points_ppr DOUBLE,
        source_snapshot_id VARCHAR,
        PRIMARY KEY (player_id, season, week)
    )
    """,
    # The engineered, leakage-safe feature panel: every non-target column here is computed
    # from strictly-prior games via a SQL window frame (ROWS BETWEEN N PRECEDING AND
    # 1 PRECEDING), so a row cannot see its own or a future week's outcome by construction.
    # target_fantasy_points_ppr is this week's real outcome and must never be read back in
    # as a feature for the same row — enforced by tests/leakage/test_target_isolation.py.
    """
    CREATE TABLE IF NOT EXISTS player_week_features (
        player_id VARCHAR NOT NULL,
        season INTEGER NOT NULL,
        week INTEGER NOT NULL,
        game_date DATE NOT NULL,
        position VARCHAR,
        games_played_prior INTEGER,
        fp_ppr_avg_last3 DOUBLE,
        fp_ppr_avg_season_to_date DOUBLE,
        targets_avg_last3 DOUBLE,
        carries_avg_last3 DOUBLE,
        receptions_avg_last3 DOUBLE,
        target_share_avg_last3 DOUBLE,
        snap_pct_avg_last3 DOUBLE,
        target_fantasy_points_ppr DOUBLE,
        feature_version VARCHAR NOT NULL,
        built_at TIMESTAMP NOT NULL,
        PRIMARY KEY (player_id, season, week)
    )
    """,
]

M4_BASELINES_DDL = [
    # Season-level aggregate of player_week_stats. Real games only (never fabricated for a
    # season a player didn't play), which is exactly what makes "did this player have a
    # season S-1" the natural gate for previous-year-style baselines.
    """
    CREATE TABLE IF NOT EXISTS player_season_stats (
        player_id VARCHAR NOT NULL,
        season INTEGER NOT NULL,
        position VARCHAR,
        games_played INTEGER NOT NULL,
        total_fantasy_points_ppr DOUBLE NOT NULL,
        ppr_points_per_game DOUBLE NOT NULL,
        total_targets DOUBLE,
        total_carries DOUBLE,
        total_receptions DOUBLE,
        PRIMARY KEY (player_id, season)
    )
    """,
    # Normalized market consensus rank, identity-joined via fantasypros_id (verified 93.8%
    # coverage on ecr_type='ro' — see docs/DECISIONS.md D16). M8 extends this table with the
    # 2QB-aware ecr_type series and dynasty values; M4 only needs 'ro' for a general-purpose
    # ECR-implied baseline.
    """
    CREATE TABLE IF NOT EXISTS market_snapshot (
        player_id VARCHAR NOT NULL,
        scrape_date DATE NOT NULL,
        ecr_type VARCHAR NOT NULL,
        position VARCHAR,
        ecr_rank DOUBLE NOT NULL,
        ecr_best DOUBLE,
        ecr_worst DOUBLE,
        source_snapshot_id VARCHAR,
        -- 'dynastyprocess' (default): DynastyProcess's fp_ecr_history mirror, the real
        -- historical time series backtesting/EDGE depend on (D3/D16/D21). 'fantasypros_live'
        -- (D38): today-only captures from the live FantasyPros API, accumulated forward from
        -- 2026-08-23 -- a separate, provenance-tagged series, never blended into the
        -- DynastyProcess-sourced rows, so no existing leakage-safety guarantee changes.
        source VARCHAR NOT NULL DEFAULT 'dynastyprocess',
        PRIMARY KEY (player_id, scrape_date, ecr_type, source)
    )
    """,
    # One row per (baseline/model, position, season, player) prediction, so the evaluation
    # harness has a single uniform surface regardless of which baseline or model produced it.
    """
    CREATE TABLE IF NOT EXISTS projection_snapshot (
        model_name VARCHAR NOT NULL,
        player_id VARCHAR NOT NULL,
        season INTEGER NOT NULL,
        position VARCHAR,
        predicted_points DOUBLE NOT NULL,
        built_at TIMESTAMP NOT NULL,
        PRIMARY KEY (model_name, player_id, season)
    )
    """,
    # position='ALL' is the cross-position rollup row (not NULL, so it stays usable in the
    # composite key). Every baseline (M4) and later model (M5+) reports through the same
    # table so results are directly, queryably comparable.
    """
    CREATE TABLE IF NOT EXISTS evaluation_results (
        model_name VARCHAR NOT NULL,
        season INTEGER NOT NULL,
        position VARCHAR NOT NULL,
        n INTEGER NOT NULL,
        mae DOUBLE,
        rmse DOUBLE,
        r2 DOUBLE,
        spearman DOUBLE,
        top12_hit_rate DOUBLE,
        top24_hit_rate DOUBLE,
        tier_accuracy DOUBLE,
        evaluated_at TIMESTAMP NOT NULL,
        PRIMARY KEY (model_name, season, position)
    )
    """,
]

M5_ESTABLISHED_ML_DDL = [
    """
    CREATE TABLE IF NOT EXISTS team_week_stats (
        team VARCHAR NOT NULL,
        season INTEGER NOT NULL,
        week INTEGER NOT NULL,
        game_id VARCHAR NOT NULL,
        game_date DATE NOT NULL,
        plays DOUBLE,
        pass_rate DOUBLE,
        passing_epa DOUBLE,
        rushing_epa DOUBLE,
        source_snapshot_id VARCHAR,
        PRIMARY KEY (team, season, week)
    )
    """,
    # Leakage-safe by construction, same as player_week_features (window frames excluding
    # the current/future rows) — see features/team.py.
    """
    CREATE TABLE IF NOT EXISTS team_week_features (
        team VARCHAR NOT NULL,
        season INTEGER NOT NULL,
        week INTEGER NOT NULL,
        game_date DATE NOT NULL,
        team_plays_avg_last3 DOUBLE,
        team_pass_rate_avg_last3 DOUBLE,
        team_epa_avg_last3 DOUBLE,
        PRIMARY KEY (team, season, week)
    )
    """,
    # Model version/provenance tracking (ARCHITECTURE.md §7/§10). validated=false bars a
    # model from being a default decision source until evaluation confirms it beats the
    # relevant baseline out of sample (ARCHITECTURE.md §12).
    """
    CREATE TABLE IF NOT EXISTS model_registry (
        model_name VARCHAR NOT NULL,
        position VARCHAR NOT NULL,
        version VARCHAR NOT NULL,
        feature_version VARCHAR NOT NULL,
        training_season_start INTEGER,
        training_season_end INTEGER,
        trained_at TIMESTAMP NOT NULL,
        validated BOOLEAN NOT NULL DEFAULT false,
        notes VARCHAR,
        PRIMARY KEY (model_name, position, version)
    )
    """,
]

# Extends the M3 player_week_features panel with the team-environment lag features M5's
# team-environment model needs. Additive/nullable, so existing rows and leakage guarantees
# for the original columns are untouched.
M5_PANEL_EXTENSION_DDL = [
    "ALTER TABLE player_week_features ADD COLUMN IF NOT EXISTS team VARCHAR",
    "ALTER TABLE player_week_features ADD COLUMN IF NOT EXISTS team_plays_avg_last3 DOUBLE",
    "ALTER TABLE player_week_features ADD COLUMN IF NOT EXISTS team_pass_rate_avg_last3 DOUBLE",
    "ALTER TABLE player_week_features ADD COLUMN IF NOT EXISTS team_epa_avg_last3 DOUBLE",
]

M6_UNCERTAINTY_DDL = [
    # Mirrors AGENT_CONTRACTS.md's "Prediction contract" fields (p10/p25/median/p75/p90,
    # top12_prob/top24_prob, confidence, model_version, feature_version).
    """
    CREATE TABLE IF NOT EXISTS uncertainty_predictions (
        prediction_id VARCHAR PRIMARY KEY,
        player_id VARCHAR NOT NULL,
        season INTEGER NOT NULL,
        position VARCHAR NOT NULL,
        model_version VARCHAR NOT NULL,
        feature_version VARCHAR NOT NULL,
        point_prediction DOUBLE NOT NULL,
        p10 DOUBLE,
        p25 DOUBLE,
        median DOUBLE,
        p75 DOUBLE,
        p90 DOUBLE,
        top12_prob DOUBLE,
        top24_prob DOUBLE,
        confidence DOUBLE,
        calibration_season INTEGER NOT NULL,
        predicted_at TIMESTAMP NOT NULL,
        UNIQUE (player_id, season, model_version)
    )
    """,
    # Out-of-sample empirical coverage — did the [p10,p90]/[p25,p75] intervals actually
    # contain that fraction of real outcomes? Published per PRODUCT_SPEC.md's "measure
    # calibration" / "do not present false precision" requirement.
    """
    CREATE TABLE IF NOT EXISTS calibration_diagnostics (
        model_version VARCHAR NOT NULL,
        season INTEGER NOT NULL,
        position VARCHAR NOT NULL,
        n INTEGER NOT NULL,
        coverage_10_90 DOUBLE,
        coverage_25_75 DOUBLE,
        mean_interval_width_10_90 DOUBLE,
        evaluated_at TIMESTAMP NOT NULL,
        PRIMARY KEY (model_version, season, position)
    )
    """,
]

M7_ROOKIE_DDL = [
    # Combine carries no gsis_id (verified in M2) — bridged via pfr_id -> player_id_map,
    # same pattern as M3's snap counts.
    """
    CREATE TABLE IF NOT EXISTS combine_results (
        player_id VARCHAR PRIMARY KEY,
        draft_year INTEGER,
        position VARCHAR,
        forty DOUBLE,
        bench DOUBLE,
        vertical DOUBLE,
        broad_jump DOUBLE,
        cone DOUBLE,
        shuttle DOUBLE,
        height DOUBLE,
        weight DOUBLE,
        school VARCHAR,
        source_snapshot_id VARCHAR
    )
    """,
    # College production via CFBD, bridged by espn_id (docs/DECISIONS.md D38 -- verified
    # against real data: CFBD's collegeAthleteId/player_usage.id/recruiting_players.athleteId
    # are the same numeric ID as DynastyProcess's espn_id, no fuzzy matching, superseding
    # D20's "no verified ID bridge" finding for cfbfastR-data's different ID namespace).
    """
    CREATE TABLE IF NOT EXISTS college_usage (
        player_id VARCHAR NOT NULL,
        season INTEGER NOT NULL,
        usage_overall DOUBLE,
        usage_pass DOUBLE,
        usage_rush DOUBLE,
        source_snapshot_id VARCHAR,
        PRIMARY KEY (player_id, season)
    )
    """,
    # Draft capital + combine + landing spot are the v1 rookie feature set (D20); college
    # usage share (D38) extends it -- final college season only (rookie_season - 1), same
    # never-the-rookie's-own-season leakage rule as landing_team_prior_pass_rate.
    """
    CREATE TABLE IF NOT EXISTS rookie_features (
        player_id VARCHAR PRIMARY KEY,
        draft_class INTEGER NOT NULL,
        position VARCHAR NOT NULL,
        draft_round INTEGER,
        draft_pick INTEGER,
        forty DOUBLE,
        bench DOUBLE,
        vertical DOUBLE,
        broad_jump DOUBLE,
        cone DOUBLE,
        shuttle DOUBLE,
        height DOUBLE,
        weight DOUBLE,
        landing_team_prior_pass_rate DOUBLE,
        landing_team_prior_plays DOUBLE,
        college_usage_overall DOUBLE,
        college_usage_pass DOUBLE,
        college_usage_rush DOUBLE,
        rookie_year_ppr_points DOUBLE NOT NULL,
        rookie_year_games INTEGER,
        breakout_top24 BOOLEAN NOT NULL,
        built_at TIMESTAMP NOT NULL
    )
    """,
    # Same feature columns as rookie_features, deliberately WITHOUT the outcome columns: this
    # holds a draft class whose NFL season hasn't been played, so there is nothing to label it
    # with (D40). Separate from rookie_features so an unlabeled row can never be picked up as
    # training data -- rookie_features stays the labeled training set by construction.
    """
    CREATE TABLE IF NOT EXISTS rookie_projection_features (
        player_id VARCHAR PRIMARY KEY,
        draft_class INTEGER NOT NULL,
        position VARCHAR NOT NULL,
        draft_round INTEGER,
        draft_pick INTEGER,
        forty DOUBLE,
        bench DOUBLE,
        vertical DOUBLE,
        broad_jump DOUBLE,
        cone DOUBLE,
        shuttle DOUBLE,
        height DOUBLE,
        weight DOUBLE,
        landing_team_prior_pass_rate DOUBLE,
        landing_team_prior_plays DOUBLE,
        college_usage_overall DOUBLE,
        college_usage_pass DOUBLE,
        college_usage_rush DOUBLE,
        built_at TIMESTAMP NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS rookie_predictions (
        prediction_id VARCHAR PRIMARY KEY,
        player_id VARCHAR NOT NULL,
        draft_class INTEGER NOT NULL,
        position VARCHAR NOT NULL,
        model_version VARCHAR NOT NULL,
        predicted_rookie_points DOUBLE,
        breakout_probability DOUBLE,
        predicted_at TIMESTAMP NOT NULL,
        UNIQUE (player_id, draft_class, model_version)
    )
    """,
    # Generic classification scoring surface (rookie breakout classifier now; anything
    # binary-labeled later reuses it rather than getting bolted onto the regression-shaped
    # evaluation_results table).
    """
    CREATE TABLE IF NOT EXISTS classification_results (
        model_name VARCHAR NOT NULL,
        cohort INTEGER NOT NULL,
        position VARCHAR NOT NULL,
        n INTEGER NOT NULL,
        brier_score DOUBLE,
        accuracy DOUBLE,
        base_rate DOUBLE,
        evaluated_at TIMESTAMP NOT NULL,
        PRIMARY KEY (model_name, cohort, position)
    )
    """,
]

M8_MARKET_EDGE_DDL = [
    # Current dynasty value snapshot from DynastyProcess's values-players.csv (verified
    # 97.6% fantasypros_id coverage — docs/DECISIONS.md D21). Not a time series like
    # market_snapshot: this file is re-scraped in place, so one row per player, replaced
    # on each `market build-dynasty-values` run rather than accumulated.
    """
    CREATE TABLE IF NOT EXISTS dynasty_values (
        player_id VARCHAR PRIMARY KEY,
        scrape_date DATE,
        team VARCHAR,
        age DOUBLE,
        ecr_pos DOUBLE,
        ecr_1qb DOUBLE,
        ecr_2qb DOUBLE,
        value_1qb DOUBLE,
        value_2qb DOUBLE,
        source_snapshot_id VARCHAR,
        updated_at TIMESTAMP NOT NULL
    )
    """,
    # Mirrors AGENT_CONTRACTS.md's Edge contract. ecr_type is part of the key because
    # rank/points/probability edge are only meaningful against a specific,
    # horizon-matched market series (D21: 'rsf' redraft-superflex for this single-season
    # model; a dynasty-horizon variant using dsf/dynasty_values is future M10 scope).
    """
    CREATE TABLE IF NOT EXISTS edge_snapshot (
        edge_id VARCHAR PRIMARY KEY,
        player_id VARCHAR NOT NULL,
        season INTEGER NOT NULL,
        position VARCHAR NOT NULL,
        ecr_type VARCHAR NOT NULL,
        model_version VARCHAR NOT NULL,
        model_rank INTEGER NOT NULL,
        market_rank INTEGER NOT NULL,
        rank_edge INTEGER NOT NULL,
        projected_points_edge DOUBLE,
        probability_edge DOUBLE,
        evidence_score DOUBLE NOT NULL,
        confidence DOUBLE,
        action VARCHAR NOT NULL,
        reasons_json VARCHAR NOT NULL,
        prediction_id VARCHAR,
        built_at TIMESTAMP NOT NULL,
        UNIQUE (player_id, season, ecr_type, model_version)
    )
    """,
    # Answers ACCEPTANCE_CRITERIA.md's "Historical EDGE performance is evaluated": for each
    # action cohort (BUY/SELL/HOLD/WATCH), did real outcomes actually beat what the market
    # implied at the time? Published either way, per CLAUDE.md's no-hidden-failure rule.
    """
    CREATE TABLE IF NOT EXISTS edge_validation_results (
        model_version VARCHAR NOT NULL,
        ecr_type VARCHAR NOT NULL,
        season INTEGER NOT NULL,
        action VARCHAR NOT NULL,
        n INTEGER NOT NULL,
        mean_actual_points DOUBLE,
        mean_market_implied_points DOUBLE,
        mean_outperformance_vs_market DOUBLE,
        evaluated_at TIMESTAMP NOT NULL,
        PRIMARY KEY (model_version, ecr_type, season, action)
    )
    """,
]

M9_EVIDENCE_DDL = [
    # Mirrors AGENT_CONTRACTS.md's Evidence contract. strength/strength_label both stored:
    # strength_label is PRODUCT_SPEC.md's qualitative STRONG/MEDIUM/WEAK taxonomy (D22),
    # strength is the numeric 0-1 field the contract itself uses, derived deterministically
    # from the label. direction is -1/0/+1 (bearish/neutral/bullish for the player named).
    """
    CREATE TABLE IF NOT EXISTS evidence_events (
        event_id VARCHAR PRIMARY KEY,
        player_id VARCHAR NOT NULL,
        season INTEGER NOT NULL,
        week INTEGER NOT NULL,
        event_date DATE NOT NULL,
        captured_at TIMESTAMP NOT NULL,
        event_type VARCHAR NOT NULL,
        source VARCHAR NOT NULL,
        source_url VARCHAR,
        strength_label VARCHAR NOT NULL,
        strength DOUBLE NOT NULL,
        direction INTEGER NOT NULL,
        structured_impact_json VARCHAR NOT NULL,
        summary VARCHAR NOT NULL,
        source_snapshot_id VARCHAR
    )
    """,
    # Weekly established-ML predictions were computed in M5 but only ever aggregated into a
    # season total and discarded (models/established/train.py). Evidence is an inherently
    # weekly signal (a depth-chart move in week 4 should adjust week 5's projection, not
    # retroactively the season total), so this persists the real, already-computed
    # `ml_catboost` weekly predictions M5 was throwing away, giving M9 a real base to adjust.
    """
    CREATE TABLE IF NOT EXISTS weekly_projection_snapshot (
        player_id VARCHAR NOT NULL,
        season INTEGER NOT NULL,
        week INTEGER NOT NULL,
        model_name VARCHAR NOT NULL,
        position VARCHAR,
        predicted_points DOUBLE NOT NULL,
        built_at TIMESTAMP NOT NULL,
        PRIMARY KEY (model_name, player_id, season, week)
    )
    """,
    # The bounded, explainable adjustment (ARCHITECTURE.md: "evidence never directly
    # overwrites model output"). This table only ever reads weekly_projection_snapshot and
    # writes a separate derived row here -- the base model prediction is never mutated.
    """
    CREATE TABLE IF NOT EXISTS projection_deltas (
        delta_id VARCHAR PRIMARY KEY,
        player_id VARCHAR NOT NULL,
        season INTEGER NOT NULL,
        week INTEGER NOT NULL,
        base_model_name VARCHAR NOT NULL,
        base_value DOUBLE NOT NULL,
        adjusted_value DOUBLE NOT NULL,
        adjustment_pct DOUBLE NOT NULL,
        evidence_score DOUBLE NOT NULL,
        reason VARCHAR NOT NULL,
        evidence_ids_json VARCHAR NOT NULL,
        built_at TIMESTAMP NOT NULL,
        UNIQUE (player_id, season, week, base_model_name)
    )
    """,
]

M10_LEAGUE_DDL = [
    # Mirrors AGENT_CONTRACTS.md's Decision contract. One row per recommendation actually
    # requested (persisted by the CLI layer, not by the pure recommendation functions
    # themselves -- league/draft.py, waiver.py, trade.py stay side-effect-free and testable),
    # giving every draft/waiver/trade call the same traceability M4-M9's outputs already have.
    """
    CREATE TABLE IF NOT EXISTS decisions (
        decision_id VARCHAR PRIMARY KEY,
        decision_type VARCHAR NOT NULL,
        league_id VARCHAR NOT NULL,
        season INTEGER NOT NULL,
        recommendation VARCHAR NOT NULL,
        alternatives_json VARCHAR NOT NULL,
        expected_value DOUBLE,
        confidence DOUBLE,
        reasons_json VARCHAR NOT NULL,
        provenance_json VARCHAR NOT NULL,
        built_at TIMESTAMP NOT NULL
    )
    """,
]

M11_AGENTS_DDL = [
    # Every column the orchestrator needs to reconstruct a full run from state alone (the
    # M11 gate: no chat transcript required) -- see agents/state.py::reconstruct_run.
    """
    CREATE TABLE IF NOT EXISTS agent_tasks (
        task_id VARCHAR PRIMARY KEY,
        run_id VARCHAR NOT NULL,
        agent VARCHAR NOT NULL,
        objective VARCHAR NOT NULL,
        priority VARCHAR NOT NULL,
        depends_on_json VARCHAR NOT NULL,
        params_json VARCHAR NOT NULL,
        status VARCHAR NOT NULL,
        attempt INTEGER NOT NULL DEFAULT 0,
        created_at TIMESTAMP NOT NULL,
        started_at TIMESTAMP,
        finished_at TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS agent_results (
        task_id VARCHAR PRIMARY KEY REFERENCES agent_tasks(task_id),
        agent VARCHAR NOT NULL,
        status VARCHAR NOT NULL,
        confidence DOUBLE,
        findings_json VARCHAR NOT NULL,
        artifacts_json VARCHAR NOT NULL,
        tests_json VARCHAR NOT NULL,
        risks_json VARCHAR NOT NULL,
        open_questions_json VARCHAR NOT NULL,
        recommended_next_action VARCHAR,
        recorded_at TIMESTAMP NOT NULL
    )
    """,
    # Mirrors AGENT_CONTRACTS.md's orchestrator conflict protocol: every disagreement
    # preserves BOTH positions (majority and minority) -- the minority is never discarded,
    # only marked as resolved-against.
    """
    CREATE TABLE IF NOT EXISTS agent_disagreements (
        disagreement_id VARCHAR PRIMARY KEY,
        run_id VARCHAR,
        disagreement_type VARCHAR NOT NULL,
        subject VARCHAR NOT NULL,
        season INTEGER,
        majority_position VARCHAR NOT NULL,
        majority_value DOUBLE,
        minority_position VARCHAR NOT NULL,
        minority_value DOUBLE,
        critique VARCHAR NOT NULL,
        resolution VARCHAR NOT NULL,
        resolved_by VARCHAR NOT NULL,
        detected_at TIMESTAMP NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS milestones (
        milestone VARCHAR NOT NULL,
        run_id VARCHAR NOT NULL,
        status VARCHAR NOT NULL,
        started_at TIMESTAMP,
        completed_at TIMESTAMP,
        notes VARCHAR,
        PRIMARY KEY (milestone, run_id)
    )
    """,
]

M13_SIMULATION_DDL = [
    # Real final team scores, derived from nflverse pbp's running score columns (max per
    # game_id, unpivoted to one row per team). Not folded into team_week_stats/features.py's
    # existing pipeline (M5's already-validated team-environment model) -- a separate,
    # self-contained table this module owns, so nothing already built is touched.
    """
    CREATE TABLE IF NOT EXISTS team_week_points (
        team VARCHAR NOT NULL,
        season INTEGER NOT NULL,
        week INTEGER NOT NULL,
        game_id VARCHAR NOT NULL,
        points DOUBLE NOT NULL,
        opponent_points DOUBLE,
        source_snapshot_id VARCHAR,
        PRIMARY KEY (team, season, week)
    )
    """,
    # One row per (team, season) simulation run's summary -- the per-player detail is large
    # (n_simulations x players) and reported directly rather than persisted row-by-row.
    """
    CREATE TABLE IF NOT EXISTS team_simulation_runs (
        run_id VARCHAR PRIMARY KEY,
        team VARCHAR NOT NULL,
        season INTEGER NOT NULL,
        n_simulations INTEGER NOT NULL,
        seed INTEGER NOT NULL,
        mean_team_points DOUBLE,
        std_team_points DOUBLE,
        qb_wr1_correlation DOUBLE,
        same_position_correlation DOUBLE,
        built_at TIMESTAMP NOT NULL
    )
    """,
]

# Runtime-registered leagues (the "Connect League" onboarding flow) -- config/league_configs/
# registry.yaml stays the curated, hand-edited set; this table is for leagues a user connects
# through the running app itself, without editing a file on the server. Only `source='sleeper'`
# is supported here (the onboarding flow validates a real, reachable Sleeper league before
# inserting) -- a `source='yaml'` entry inherently needs a config file to exist, so it stays a
# hand-edit-the-registry operation.
M14_PRODUCTIZATION_DDL: list[str] = [
    """
    CREATE TABLE IF NOT EXISTS registered_leagues (
        league_id VARCHAR PRIMARY KEY,
        source VARCHAR NOT NULL,
        sleeper_league_id VARCHAR,
        display_name VARCHAR,
        created_at TIMESTAMP NOT NULL DEFAULT current_timestamp
    )
    """,
]

# D54: the empirical-validation phase. One row per simulated historical draft
# (season, strategy, draft_slot) -- see evaluation/draft_simulation.py's module docstring for
# why draft_slot is a dimension (every real slot drafts under every strategy, so no single
# lucky/unlucky slot drives an apparent result) and why only the drafted_player_ids plus the
# two real-outcome-scored metrics are persisted (the raw per-pick reasoning is reproducible on
# demand from the same walk-forward inputs; persisting it here would just be a second,
# driftable copy).
M16_EVALUATION_DDL = [
    """
    CREATE TABLE IF NOT EXISTS draft_simulation_results (
        season INTEGER NOT NULL,
        strategy VARCHAR NOT NULL,
        draft_slot INTEGER NOT NULL,
        drafted_player_ids_json VARCHAR NOT NULL,
        total_roster_points DOUBLE NOT NULL,
        starter_points DOUBLE NOT NULL,
        framework_version VARCHAR NOT NULL,
        evaluated_at TIMESTAMP NOT NULL,
        PRIMARY KEY (season, strategy, draft_slot, framework_version)
    )
    """,
]

# M15+ DDL is appended here as later milestones are implemented.
ALL_DDL: list[str] = [
    *M1_SNAPSHOTS_DDL,
    *M2_IDENTITY_DDL,
    *M3_FEATURES_DDL,
    *M4_BASELINES_DDL,
    *M5_ESTABLISHED_ML_DDL,
    *M5_PANEL_EXTENSION_DDL,
    *M6_UNCERTAINTY_DDL,
    *M7_ROOKIE_DDL,
    *M8_MARKET_EDGE_DDL,
    *M9_EVIDENCE_DDL,
    *M10_LEAGUE_DDL,
    *M11_AGENTS_DDL,
    *M13_SIMULATION_DDL,
    *M14_PRODUCTIZATION_DDL,
    *M16_EVALUATION_DDL,
]

# ---------------------------------------------------------------------------
# Migrations
#
# Every statement above is CREATE TABLE IF NOT EXISTS, which is idempotent for *new* tables
# but silently does nothing to a table that already exists -- including when this file adds a
# column to it. That gap shipped a real bug in D38: `rookie_features.college_usage_*` and
# `market_snapshot.source` were added to the DDL and verified only against fresh in-memory
# test databases, so on any pre-existing database `features build` hard-crashed with
# `BinderException: Referenced update column college_usage_overall not found in table` and
# `market capture-live-fantasypros` would have failed the same way. Found by running the real
# pipeline against a real database for the first time (D39).
#
# ADD COLUMN IF NOT EXISTS is itself idempotent in DuckDB (verified), so these are safe to
# re-run on every init_db, same contract as the CREATE statements.
ADD_COLUMN_MIGRATIONS = [
    "ALTER TABLE rookie_features ADD COLUMN IF NOT EXISTS college_usage_overall DOUBLE",
    "ALTER TABLE rookie_features ADD COLUMN IF NOT EXISTS college_usage_pass DOUBLE",
    "ALTER TABLE rookie_features ADD COLUMN IF NOT EXISTS college_usage_rush DOUBLE",
    # D43: model artifact persistence (models/persistence.py) -- where a fitted model was
    # saved to disk, and (for models like uncertainty whose serving story needs more than the
    # point prediction) the calibration residuals needed to reconstruct quantiles/probabilities
    # without retraining. Both nullable: most model_registry rows predate persistence and have
    # neither, which is fine -- absence just means "no persisted artifact for this row yet."
    "ALTER TABLE model_registry ADD COLUMN IF NOT EXISTS artifact_path VARCHAR",
    "ALTER TABLE model_registry ADD COLUMN IF NOT EXISTS calibration_residuals_json VARCHAR",
]

# market_snapshot needs more than an added column: D38 also widened its PRIMARY KEY to include
# `source`, and DuckDB cannot ALTER a primary key in place. The table is fully reproducible
# from stored snapshots (`alpha-squad market build`), so a pre-D38 table is rebuilt with the
# current schema and its existing rows carried over tagged as 'dynastyprocess' -- which is
# exactly what they are, since that was the only writer before D38.
MARKET_SNAPSHOT_REBUILD = """
ALTER TABLE market_snapshot RENAME TO market_snapshot_pre_d38;
CREATE TABLE market_snapshot (
    player_id VARCHAR NOT NULL,
    scrape_date DATE NOT NULL,
    ecr_type VARCHAR NOT NULL,
    position VARCHAR,
    ecr_rank DOUBLE NOT NULL,
    ecr_best DOUBLE,
    ecr_worst DOUBLE,
    source_snapshot_id VARCHAR,
    source VARCHAR NOT NULL DEFAULT 'dynastyprocess',
    PRIMARY KEY (player_id, scrape_date, ecr_type, source)
);
INSERT INTO market_snapshot
    (player_id, scrape_date, ecr_type, position, ecr_rank, ecr_best, ecr_worst,
     source_snapshot_id, source)
SELECT player_id, scrape_date, ecr_type, position, ecr_rank, ecr_best, ecr_worst,
       source_snapshot_id, 'dynastyprocess'
FROM market_snapshot_pre_d38;
DROP TABLE market_snapshot_pre_d38;
"""
