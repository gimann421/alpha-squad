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

# M6+ DDL is appended here as later milestones are implemented.
ALL_DDL: list[str] = [
    *M1_SNAPSHOTS_DDL,
    *M2_IDENTITY_DDL,
    *M3_FEATURES_DDL,
    *M4_BASELINES_DDL,
    *M5_ESTABLISHED_ML_DDL,
    *M5_PANEL_EXTENSION_DDL,
]
