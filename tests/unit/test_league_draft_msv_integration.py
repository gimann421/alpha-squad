"""Integration tests for marginal starter value in production `recommend_draft_pick`
(docs/DECISIONS.md D60).

The M-tier ablation (5 seasons x 10 slots x 4 tiers, `evaluation/draft_forensics.py`) measured
that replacing VORP with marginal starter value as the score's value base (tier M3) beat the
shipped formula on every axis the pre-registered rule checked: mean starter points (+109.6,
+5.8%), win rate (37/50 vs the control), and per-season consistency (4 of 5 seasons). It was
also the only tier that fixed a real defect visible in the others -- production was drafting
~3.8 kickers and ~2.3 defenses per 16-round draft, because VORP prices a bench K/DST against
positional replacement level with no knowledge that neither has flex eligibility. These tests
cover the production integration, not the ablation itself (that lives in
`test_marginal_starter_value.py`).
"""

from __future__ import annotations

import duckdb
import pytest

from alpha_squad.league.context import LeagueContext
from alpha_squad.league.draft import recommend_draft_pick
from alpha_squad.models.uncertainty.run import MODEL_VERSION as UNCERTAINTY_MODEL_VERSION
from alpha_squad.storage.db import init_db

SEASON = 2025


@pytest.fixture
def con():
    connection = duckdb.connect(":memory:")
    init_db(connection)
    yield connection
    connection.close()


def _league(**overrides) -> LeagueContext:
    base = dict(
        league_id="t",
        format="redraft",
        teams=10,
        scoring={"ppr": True},
        lineup={"QB": 1, "RB": 2, "WR": 2, "TE": 1, "FLEX": 2, "K": 1, "DEF": 1},
        roster={"bench": 6, "roster_size": 16},
    )
    base.update(overrides)
    return LeagueContext(**base)


def _seed(con, player_id, position, points, confidence=0.8, ecr_rank=1.0):
    con.execute(
        """
        INSERT INTO uncertainty_predictions
            (prediction_id, player_id, season, position, model_version, feature_version,
             point_prediction, top12_prob, top24_prob, confidence, calibration_season,
             predicted_at)
        VALUES (?, ?, ?, ?, ?, 'test_v1', ?, 0.2, 0.4, ?, ?, current_timestamp)
        """,
        [f"p_{player_id}", player_id, SEASON, position, UNCERTAINTY_MODEL_VERSION,
         points, confidence, SEASON - 1],
    )
    con.execute(
        "INSERT INTO market_snapshot (player_id, scrape_date, ecr_type, position, ecr_rank, "
        "page_type) VALUES (?, ?, 'ro', ?, ?, 'redraft-overall')",
        [player_id, f"{SEASON}-08-01", position, ecr_rank],
    )


class TestBackwardCompatibility:
    def test_omitting_roster_player_ids_falls_back_to_vorp(self, con):
        """The exact D55 formula for callers that only know position counts -- some API/agent
        callers do not track individual picks. No behavior change for them."""
        _seed(con, "rb1", "RB", 300.0, ecr_rank=1.0)
        _seed(con, "rb2", "RB", 250.0, ecr_rank=2.0)
        without = recommend_draft_pick(con, _league(), SEASON, [], {"rb1", "rb2"})
        with_none = recommend_draft_pick(
            con, _league(), SEASON, [], {"rb1", "rb2"}, roster_player_ids=None
        )
        assert without.recommendation == with_none.recommendation
        assert without.candidates[0].score == pytest.approx(with_none.candidates[0].score)

    def test_a_known_empty_roster_differs_from_an_unknown_one(self, con):
        """`roster_player_ids=[]` (a KNOWN empty roster) activates marginal starter value;
        omitting the argument (an UNKNOWN roster) falls back to VORP. These are genuinely
        different calls, not two spellings of the same thing -- VORP is priced against
        league-wide replacement level, MSV against an empty lineup, and nothing forces them
        to agree."""
        _seed(con, "rb1", "RB", 300.0, ecr_rank=1.0)
        unknown = recommend_draft_pick(con, _league(), SEASON, [], {"rb1"})
        known_empty = recommend_draft_pick(
            con, _league(), SEASON, [], {"rb1"}, roster_player_ids=[]
        )
        # The structural difference, not a numeric coincidence: MSV is simply not computed
        # (and not offered as a reason) when the roster is unknown, VORP alone drives the
        # score; it IS computed, and disclosed, once the roster is known -- even empty.
        assert unknown.candidates[0].marginal_starter_value is None
        assert known_empty.candidates[0].marginal_starter_value is not None


class TestMarginalStarterValueChangesTheRecommendation:
    def test_the_flip_the_m_tier_ablation_is_named_for(self, con):
        """Deterministic synthetic scenario, numbers verified against the real code (not
        hand-derived). A minimal RB/WR/FLEX league: the roster already holds the best two
        RBs (filling the dedicated RB slot and the FLEX slot), and the WR dedicated slot is
        still empty. `rb_c` is a real, positive-VORP RB league-wide (there is deep bench
        competition below him) but cannot improve THIS roster -- both slots he could fill are
        already held by better players. `wr_a` has lower league-wide VORP but would fill the
        still-empty WR slot outright. VORP alone takes `rb_c` (his league-wide scarcity is
        real); marginal starter value correctly prefers `wr_a`, who would actually start."""
        league = LeagueContext(
            league_id="msv_flip",
            format="redraft",
            teams=10,
            scoring={"ppr": True},
            lineup={"RB": 1, "WR": 1, "FLEX": 1},
            roster={"bench": 4, "roster_size": 7},
        )
        _seed(con, "rb_a", "RB", 300.0, ecr_rank=1.0)
        _seed(con, "rb_b", "RB", 250.0, ecr_rank=2.0)
        _seed(con, "rb_c", "RB", 240.0, ecr_rank=3.0)  # worse than rb_b: can't improve roster
        for i in range(4, 30):
            _seed(con, f"rb_x{i}", "RB", 240.0 - i * 3, ecr_rank=float(i))
        _seed(con, "wr_a", "WR", 150.0, ecr_rank=2.0)
        for i in range(2, 15):
            _seed(con, f"wr_x{i}", "WR", 150.0 - i * 5, ecr_rank=float(i + 1))

        roster = ["rb_a", "rb_b"]
        available = {"rb_c", "wr_a"}

        without_msv = recommend_draft_pick(con, league, SEASON, ["RB", "RB"], available)
        assert without_msv.recommendation == "rb_c"

        with_msv = recommend_draft_pick(
            con, league, SEASON, ["RB", "RB"], available, roster_player_ids=roster
        )
        assert with_msv.recommendation == "wr_a"
        msv_rb_c = next(c for c in with_msv.candidates if c.player_id == "rb_c")
        assert msv_rb_c.marginal_starter_value == pytest.approx(0.0)

    def test_reasons_disclose_marginal_starter_value_when_active(self, con):
        _seed(con, "rb1", "RB", 300.0, ecr_rank=1.0)
        rec = recommend_draft_pick(
            con, _league(), SEASON, [], {"rb1"}, roster_player_ids=[]
        )
        assert any("marginal starter value" in r for r in rec.reasons)

    def test_reasons_omit_it_when_falling_back_to_vorp(self, con):
        _seed(con, "rb1", "RB", 300.0, ecr_rank=1.0)
        rec = recommend_draft_pick(con, _league(), SEASON, [], {"rb1"})
        assert not any("marginal starter value" in r for r in rec.reasons)


class TestKickerDefenseHoardingIsFixed:
    """The defect the M-tier ablation surfaced: with VORP as the value base, production
    drafted a mean 3.78 kickers and 2.26 defenses across a 16-round draft, because a bench K
    or DST still scores positive VORP despite having zero chance of ever starting (K/DEF have
    no flex eligibility, so a second one's marginal starter value is deterministically 0 once
    the first fills the slot)."""

    def test_a_second_kicker_no_better_than_the_first_has_zero_marginal_starter_value(self, con):
        """A candidate WORSE than the roster's current kicker cannot improve the lineup at
        all (K has no flex eligibility), so his marginal starter value is exactly zero --
        unlike VORP, which still prices him against league-wide replacement level."""
        _seed(con, "k1", "K", 130.0, ecr_rank=1.0)
        _seed(con, "k2", "K", 125.0, ecr_rank=2.0)
        rec = recommend_draft_pick(
            con, _league(), SEASON, ["K"], {"k2"}, roster_player_ids=["k1"]
        )
        msv = next(c for c in rec.candidates if c.player_id == "k2").marginal_starter_value
        assert msv == pytest.approx(0.0)

    def test_a_second_kicker_scores_below_a_startable_skill_player(self, con):
        _seed(con, "k1", "K", 130.0, ecr_rank=1.0)
        _seed(con, "k2", "K", 125.0, ecr_rank=2.0)  # worse than the roster's own kicker
        _seed(con, "wr1", "WR", 150.0, ecr_rank=3.0)  # would start (empty WR dedicated slots)
        for i in range(2, 20):
            _seed(con, f"wr_x{i}", "WR", 150.0 - i * 3, ecr_rank=float(i + 2))

        rec = recommend_draft_pick(
            con, _league(), SEASON, ["K"], {"k2", "wr1"}, roster_player_ids=["k1"]
        )
        assert rec.recommendation == "wr1"

    def test_a_better_second_kicker_correctly_upgrades_the_lineup(self, con):
        """The complement: MSV is not "the roster already has one, so zero" -- it correctly
        recognizes when a NEW candidate would replace a WEAKER starter, same as any other
        position. This is the intended behavior, not a loophole."""
        _seed(con, "k1", "K", 130.0, ecr_rank=1.0)
        _seed(con, "k2", "K", 200.0, ecr_rank=2.0)  # meaningfully better
        rec = recommend_draft_pick(
            con, _league(), SEASON, ["K"], {"k2"}, roster_player_ids=["k1"]
        )
        msv = next(c for c in rec.candidates if c.player_id == "k2").marginal_starter_value
        assert msv == pytest.approx(70.0)  # 200 - 130: the upgrade over the current starter
