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
        PRIMARY KEY (player_id, scrape_date, ecr_type)
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
    # College production is not included here — no verified ID bridge to cfbfastR-data
    # exists (docs/DECISIONS.md D20). Draft capital + combine + landing spot are the v1
    # rookie feature set; all cleanly identity-linked, no fuzzy matching.
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
        rookie_year_ppr_points DOUBLE NOT NULL,
        rookie_year_games INTEGER,
        breakout_top24 BOOLEAN NOT NULL,
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

# M10+ DDL is appended here as later milestones are implemented.
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
]
