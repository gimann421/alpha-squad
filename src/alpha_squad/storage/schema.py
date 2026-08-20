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

# M4+ DDL is appended here as later milestones are implemented.
ALL_DDL: list[str] = [
    *M1_SNAPSHOTS_DDL,
    *M2_IDENTITY_DDL,
    *M3_FEATURES_DDL,
]
