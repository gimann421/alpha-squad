"""Draft-aware replacement level in the shipped engine (docs/DECISIONS.md D67).

Until D67 `league/draft.py` computed VORP once from the full season pool, so the replacement
level a pick was scored against was numerically identical at pick 1 and pick 160 -- measured on
real 2022 data at round 13 it sat +178.2 too high for QB and +69.1 for WR but only +2.2 for K,
i.e. the engine was under-valuing everyone except kickers. These tests pin the fix, and pin the
two properties that make its demand target derived rather than tuned.
"""

from __future__ import annotations

import duckdb
import pytest

from alpha_squad.league.context import LeagueContext, load_league_context
from alpha_squad.league.draft import recommend_draft_pick
from alpha_squad.league.replacement import demand_boundary_replacement, market_draft_demand
from alpha_squad.models.uncertainty.run import MODEL_VERSION as UNCERTAINTY_MODEL_VERSION
from alpha_squad.storage.db import init_db

TARGET_LEAGUE = "src/alpha_squad/config/league_configs/target_league.yaml"
LEGACY_LEAGUE = "src/alpha_squad/config/league_configs/legacy_2qb_dynasty.yaml"
SEASON = 2024


def _pool(n: int = 60) -> tuple[dict[str, float], dict[str, str]]:
    """Strictly decreasing projections per position, so the identity of the replacement-level
    player is unambiguous at every demand boundary."""
    projections: dict[str, float] = {}
    positions: dict[str, str] = {}
    for pos in ("QB", "RB", "WR", "TE", "K", "DST"):
        for i in range(n):
            pid = f"{pos}_{i:03d}"
            projections[pid] = 400.0 - i
            positions[pid] = pos
    return projections, positions


def _board(projections, positions) -> dict[str, tuple[str, float]]:
    return {
        pid: (positions[pid], float(rank))
        for rank, pid in enumerate(sorted(projections, key=lambda p: -projections[p]), 1)
    }


class TestDemandTarget:
    def test_it_sums_to_the_picks_the_draft_actually_makes(self):
        """The structural anchor, and the reason there is no depth parameter to tune: a draft
        makes exactly `teams x roster_size` picks, so per-team demand must sum to roster_size --
        not the lineup size (10), not `startable_slots` (14), not `positional_capacity` (22)."""
        league = load_league_context(TARGET_LEAGUE)
        projections, positions = _pool()
        demand = market_draft_demand(league, _board(projections, positions), projections, positions)
        assert sum(demand.values()) == pytest.approx(float(league.roster["roster_size"]))

    def test_it_adapts_to_the_league_format(self):
        """The claim that this is derived rather than hardcoded, made falsifiable: a 2QB league
        must demand more QBs per team than a 1QB league, from the configs alone."""
        projections, positions = _pool()
        board = _board(projections, positions)
        one_qb = market_draft_demand(
            load_league_context(TARGET_LEAGUE), board, projections, positions
        )
        two_qb = market_draft_demand(
            load_league_context(LEGACY_LEAGUE), board, projections, positions
        )
        assert two_qb["QB"] > one_qb["QB"]

    def test_a_position_the_board_omits_keeps_its_starting_requirement(self):
        """The real `ro` board carries zero kickers in its top 160 in every season 2021-2025, so
        demand must not collapse to zero for a position the lineup still starts."""
        league = load_league_context(TARGET_LEAGUE)
        projections, positions = _pool()
        board = {p: v for p, v in _board(projections, positions).items() if positions[p] != "K"}
        assert market_draft_demand(league, board, projections, positions)["K"] >= 1


class TestReplacementFollowsTheBoard:
    def test_the_level_falls_as_the_position_is_drafted(self):
        """The D65 defect itself, pinned so it cannot return."""
        league = load_league_context(TARGET_LEAGUE)
        projections, positions = _pool()
        demand = market_draft_demand(league, _board(projections, positions), projections, positions)
        full = demand_boundary_replacement(league, set(projections), projections, positions, demand)
        depleted_pool = {p for p in projections if not (positions[p] == "WR" and int(p[3:]) < 40)}
        depleted = demand_boundary_replacement(
            league, depleted_pool, projections, positions, demand
        )
        assert depleted["WR"] < full["WR"]

    def test_it_prices_the_boundary_player_not_the_best_available(self):
        """If replacement collapsed to the best available, every surplus at that position would
        be <= 0 and the position would go invisible to the value term."""
        league = load_league_context(TARGET_LEAGUE)
        projections, positions = _pool()
        levels = demand_boundary_replacement(
            league, set(projections), projections, positions, {"WR": 5.0}
        )
        assert levels["WR"] == pytest.approx(projections["WR_050"])

    def test_satisfied_demand_prices_the_surplus_at_zero(self):
        """The other end: once the league has absorbed everyone it needs at a position, one more
        body there really is worth no surplus."""
        league = load_league_context(TARGET_LEAGUE)
        projections, positions = _pool()
        available = {p for p in projections if not (positions[p] == "K" and int(p[2:]) < 20)}
        levels = demand_boundary_replacement(league, available, projections, positions, {"K": 1.0})
        best_k = max(projections[p] for p in available if positions[p] == "K")
        assert levels["K"] == pytest.approx(best_k)


def _seed(con, player_id, position, points, ecr_rank):
    con.execute(
        """
        INSERT INTO uncertainty_predictions
            (prediction_id, player_id, season, position, model_version, feature_version,
             point_prediction, top12_prob, top24_prob, confidence, calibration_season,
             predicted_at)
        VALUES (?, ?, ?, ?, ?, 'test_v1', ?, 0.2, 0.4, 0.8, ?, current_timestamp)
        """,
        [
            f"p_{player_id}",
            player_id,
            SEASON,
            position,
            UNCERTAINTY_MODEL_VERSION,
            points,
            SEASON - 1,
        ],
    )
    con.execute(
        "INSERT INTO market_snapshot (player_id, scrape_date, ecr_type, position, ecr_rank, "
        "page_type) VALUES (?, ?, 'ro', ?, ?, 'redraft-overall')",
        [player_id, f"{SEASON}-08-01", position, ecr_rank],
    )


class TestTheEngineConsultsTheBoard:
    @pytest.fixture
    def con(self):
        connection = duckdb.connect(":memory:")
        init_db(connection)
        for pos in ("QB", "RB", "WR", "TE", "K", "DST"):
            for i in range(40):
                _seed(connection, f"{pos.lower()}_{i:03d}", pos, 400.0 - i, float(i + 1))
        yield connection
        connection.close()

    @staticmethod
    def _league() -> LeagueContext:
        return LeagueContext(
            league_id="t",
            format="redraft",
            teams=10,
            scoring={"ppr": True},
            lineup={"QB": 1, "RB": 2, "WR": 2, "TE": 1, "FLEX": 2, "K": 1, "DEF": 1},
            roster={"bench": 6, "roster_size": 16},
        )

    def test_the_same_candidate_is_valued_differently_on_a_thinner_board(self, con):
        """End to end through `recommend_draft_pick`: if the draft-aware level did not reach the
        score, these two would be identical -- which is exactly what production did before D67."""
        league = self._league()
        everyone = {
            r[0] for r in con.execute("SELECT player_id FROM uncertainty_predictions").fetchall()
        }
        thin = {p for p in everyone if not p.startswith("wr_")} | {"wr_000"}
        full_score = next(
            c
            for c in recommend_draft_pick(con, league, SEASON, [], everyone, top_n=300).candidates
            if c.player_id == "wr_000"
        ).score
        thin_score = next(
            c
            for c in recommend_draft_pick(con, league, SEASON, [], thin, top_n=300).candidates
            if c.player_id == "wr_000"
        ).score
        assert full_score != thin_score

    def test_the_recommendation_still_explains_both_replacement_levels(self, con):
        """A user-facing reason that quoted only the draft-aware number would silently change
        what "VORP" has meant in every previously published figure."""
        league = self._league()
        everyone = {
            r[0] for r in con.execute("SELECT player_id FROM uncertainty_predictions").fetchall()
        }
        rec = recommend_draft_pick(con, league, SEASON, [], everyone, top_n=1)
        assert any("still on the board" in r for r in rec.candidates[0].reasons)
        assert any("season-long VORP" in r for r in rec.candidates[0].reasons)


class TestUnobservableBoundaryFallsBackToStatic:
    """Two guards for one root cause: `available_player_ids` is only a *board* when the caller
    means it as one. `POST /league/{id}/draft` accepts any set, and a shortlist read as a board
    would silently redefine replacement level. Neither guard fires during a real draft."""

    def test_a_demand_deeper_than_the_pool_omits_the_position(self):
        """Guard 1, inside `demand_boundary_replacement`: the boundary player does not exist, and
        clamping to the worst available would hand everyone else a large spurious surplus."""
        league = load_league_context(TARGET_LEAGUE)
        projections, positions = _pool()  # 130 per position
        levels = demand_boundary_replacement(
            league, set(projections), projections, positions, {"WR": 20.0, "RB": 4.64}
        )
        assert "WR" not in levels  # 10 x 20 = 200 demanded, 130 exist
        assert "RB" in levels  # 10 x 4.64 = 46, comfortably inside

    def test_a_full_board_keeps_every_position(self):
        league = load_league_context(TARGET_LEAGUE)
        projections, positions = _pool()
        demand = market_draft_demand(league, _board(projections, positions), projections, positions)
        levels = demand_boundary_replacement(
            league, set(projections), projections, positions, demand
        )
        assert set(levels) >= {"QB", "RB", "WR", "TE", "K", "DST"}

    def test_a_shortlist_would_exhaust_every_position_without_the_engine_guard(self):
        """Why guard 2 is needed, stated as the failure it prevents. Read as a board, a
        three-player shortlist says almost every player in the league is drafted, so every
        position's remaining demand is 0 and replacement collapses to the best player in the
        shortlist -- pricing the whole shortlist at zero surplus."""
        league = load_league_context(TARGET_LEAGUE)
        projections, positions = _pool()
        demand = market_draft_demand(league, _board(projections, positions), projections, positions)
        shortlist = {"WR_000", "WR_001", "RB_000"}
        levels = demand_boundary_replacement(league, shortlist, projections, positions, demand)
        assert levels["WR"] == pytest.approx(projections["WR_000"])  # best of the shortlist
        assert levels["RB"] == pytest.approx(projections["RB_000"])

    def test_the_engine_refuses_to_read_a_shortlist_as_a_board(self, tmp_path):
        """Guard 2: a draft removes at most `teams x roster_size` players, so a pool implying more
        than that cannot be a draft in progress -- the engine falls back to the season-long static
        level, and the shortlist keeps a real, ordered surplus instead of collapsing to zero."""
        con = duckdb.connect(str(tmp_path / "t.duckdb"))
        init_db(con)
        for pos in ("QB", "RB", "WR", "TE", "K", "DST"):
            for i in range(40):
                _seed(con, f"{pos.lower()}_{i:03d}", pos, 400.0 - i, float(i + 1))
        league = TestTheEngineConsultsTheBoard._league()
        shortlist = {"wr_000", "wr_001", "rb_000"}
        n_players = con.execute("SELECT count(*) FROM uncertainty_predictions").fetchone()[0]
        assert n_players - len(shortlist) > league.teams * league.roster["roster_size"]

        rec = recommend_draft_pick(con, league, SEASON, [], shortlist, top_n=10)
        scores = {c.player_id: c.score for c in rec.candidates}
        assert scores["wr_000"] > scores["wr_001"] > 0  # ordered, and not collapsed to zero
        # and the surplus quoted is the season-long one, i.e. the fallback really was taken
        assert all(f"VORP {c.vorp:+.1f} pts above" in c.reasons[0] for c in rec.candidates)
