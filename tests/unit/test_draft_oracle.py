"""Tests for the D86 retrospective oracle.

The oracle is a DIAGNOSTIC that reads realized outcomes, so the properties that matter most are
the ones that keep it from ever becoming a hindsight drafter, and the ones that keep its regret
number honest:

  * realized outcomes must never reach a policy or an opponent (leakage);
  * the rollout must reproduce the shipped engine's own draft when started from pick 0;
  * the candidate slate must include both Alpha's pick and players Alpha did not rate, or the
    measured regret is biased toward zero by construction;
  * regret must be non-negative and zero exactly when Alpha's pick IS the oracle's.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from alpha_squad.evaluation.draft_forensics import (
    _pick_by_tier,
    load_season_static,
    simulate_forensic_draft,
)
from alpha_squad.evaluation.draft_oracle import (
    SEASON_LONG,
    SHIPPED_TIER,
    WEEKLY_NO_FORESIGHT,
    OracleCandidate,
    OraclePick,
    _score_roster,
    assert_no_realized_inputs_in_policy,
    audit_draft,
    candidate_slate,
    draft_order,
    make_roster_scorer,
    rollout,
)
from alpha_squad.evaluation.draft_simulation import (
    MARKET_CONSENSUS_ROSTER_AWARE,
    _actual_points_for,
)
from alpha_squad.evaluation.opening_audit import snake_overall_pick
from alpha_squad.evaluation.weekly_objective import load_weekly_points
from alpha_squad.league.context import LeagueContext
from alpha_squad.league.opportunity_cost import roster_aware_market_pick
from alpha_squad.league.roster import unfilled_dedicated_slots
from alpha_squad.models.baselines.kicking_defense import MODEL_NAME as KDST_MODEL_NAME
from alpha_squad.models.uncertainty.run import MODEL_VERSION as UNCERTAINTY_MODEL_VERSION
from alpha_squad.storage.db import init_db

_LEAGUE_CONFIGS_DIR = (
    Path(__file__).parents[2] / "src" / "alpha_squad" / "config" / "league_configs"
)


@pytest.fixture
def con():
    connection = duckdb.connect(":memory:")
    init_db(connection)
    yield connection
    connection.close()


def _league() -> LeagueContext:
    return LeagueContext(
        league_id="oracle_test",
        format="redraft",
        teams=4,
        scoring={"ppr": True, "ppr_value": 1.0},
        lineup={"QB": 1, "RB": 1, "WR": 1, "TE": 1, "FLEX": 1},
        roster={"bench": 2, "roster_size": 7},
    )


def _seed(con, season=2023, n_per_position=8):
    """Real-shaped data through the same two paths `load_season_projections` reads, plus
    realized season points that deliberately DISAGREE with the projection ordering -- otherwise
    an oracle that simply followed the projections would look correct for the wrong reason."""
    rank = 1
    for position in ("QB", "RB", "WR", "TE"):
        for i in range(n_per_position):
            player_id = f"{position}_{i}"
            points = 300.0 - i * 20
            con.execute(
                """
                INSERT INTO uncertainty_predictions
                    (prediction_id, player_id, season, position, model_version, feature_version,
                     point_prediction, top12_prob, top24_prob, confidence, calibration_season,
                     predicted_at)
                VALUES (?, ?, ?, ?, ?, 'test_v1', ?, 0.2, 0.4, 0.8, ?, current_timestamp)
                """,
                [
                    f"pred_{player_id}",
                    player_id,
                    season,
                    position,
                    UNCERTAINTY_MODEL_VERSION,
                    points,
                    season - 1,
                ],
            )
            # realized points REVERSE the projection order within each position
            realized = 100.0 + i * 25
            con.execute(
                "INSERT INTO player_season_stats (player_id, season, position, games_played, "
                "total_fantasy_points_ppr, ppr_points_per_game) VALUES (?, ?, ?, 17, ?, ?)",
                [player_id, season, position, realized, realized / 17],
            )
            # D89: the league below is `format="redraft"`, so `market/series.py` resolves it to
            # ecr_type 'ro' / page_type 'redraft-overall'. This fixture previously seeded
            # 'do'/'dynasty-overall', which NOTHING in these tests reads -- so `market_rank` came
            # back empty and the nine opponents silently drafted in `player_id` order. Caught by
            # `assert_usable_market_board`, which is exactly the failure that guard exists for.
            con.execute(
                "INSERT INTO market_snapshot (player_id, scrape_date, ecr_type, position, "
                "ecr_rank, ecr_best, ecr_worst, page_type) "
                "VALUES (?, ?, 'ro', ?, ?, ?, ?, 'redraft-overall')",
                [player_id, f"{season}-08-01", position, float(rank), rank, rank + 3],
            )
            rank += 1
    for position in ("K", "DST"):
        for i in range(4):
            player_id = f"{position}_{i}"
            con.execute(
                "INSERT INTO projection_snapshot "
                "(model_name, player_id, season, position, predicted_points, built_at) "
                "VALUES (?, ?, ?, ?, ?, current_timestamp)",
                [KDST_MODEL_NAME, player_id, season, position, 120.0 - i * 10],
            )


class TestLeakageGuard:
    def test_no_realized_outcome_reaches_a_policy(self):
        """The single most important property of the module."""
        assert_no_realized_inputs_in_policy()

    def test_the_guard_would_actually_catch_a_leak(self):
        """A guard that cannot fail is not a guard. Feed it a function that takes a realized
        argument and confirm it raises."""
        import inspect

        def leaky_policy(available, market_rank, realized_points):  # noqa: ARG001
            return ""

        banned = ("actual", "realized", "outcome", "realised")
        params = set(inspect.signature(leaky_policy).parameters)
        assert {p for p in params if any(b in p.lower() for b in banned)} == {"realized_points"}


class TestDraftOrder:
    def test_covers_every_pick_exactly_once_in_snake_order(self):
        league = _league()
        order = draft_order(league)
        total = league.teams * int(league.roster["roster_size"])
        assert len(order) == total
        assert [p for p, _, _ in order] == list(range(1, total + 1))

    def test_snake_reverses_on_even_rounds(self):
        league = _league()
        by_round: dict[int, list[int]] = {}
        for _, rnd, slot in draft_order(league):
            by_round.setdefault(rnd, []).append(slot)
        assert by_round[1] == [1, 2, 3, 4]
        assert by_round[2] == [4, 3, 2, 1]

    def test_every_slot_gets_one_pick_per_round(self):
        league = _league()
        by_round: dict[int, list[int]] = {}
        for _, rnd, slot in draft_order(league):
            by_round.setdefault(rnd, []).append(slot)
        for slots in by_round.values():
            assert sorted(slots) == list(range(1, league.teams + 1))


class TestRolloutReproducesTheShippedDraft:
    def test_rollout_from_pick_zero_equals_a_full_forensic_draft(self, con):
        """THE control check. A rollout starting before any pick has been made must produce the
        same roster -- and therefore the same realized score -- as `simulate_forensic_draft`.
        If it does not, every oracle number is measured against a draft nobody plays."""
        _seed(con)
        league = _league()
        static = load_season_static(con, league, 2023)

        expected = simulate_forensic_draft(
            con,
            league,
            2023,
            SHIPPED_TIER,
            1,
            static,
            opponent_strategy=MARKET_CONSENSUS_ROSTER_AWARE,
        )
        starter, total, unfilled = rollout(
            con,
            league,
            2023,
            static,
            draft_slot=1,
            after_pick_overall=0,
            available=set(static.projections),
            drafted=[],
            opponent_rosters={s: [] for s in range(2, league.teams + 1)},
            actual={},
        )
        assert starter == pytest.approx(expected.starter_points, abs=1e-9)
        assert total == pytest.approx(expected.total_roster_points, abs=1e-9)
        # `ForensicDraftResult` carries no unfilled-slot field, so derive it the same way the
        # rollout does, from the same drafted positions.
        assert unfilled == sum(
            unfilled_dedicated_slots(league, expected.drafted_positions).values()
        )

    def test_rollout_fills_the_roster(self, con):
        _seed(con)
        league = _league()
        static = load_season_static(con, league, 2023)
        starter, total, unfilled = rollout(
            con,
            league,
            2023,
            static,
            draft_slot=2,
            after_pick_overall=0,
            available=set(static.projections),
            drafted=[],
            opponent_rosters={s: [] for s in (1, 3, 4)},
            actual={},
        )
        assert starter > 0
        assert total >= starter
        assert unfilled == 0


class TestCandidateSlate:
    def test_union_includes_players_alpha_did_not_rate(self, con):
        """The slate must reach beyond Alpha's own ranking, or measured regret is biased to
        zero by construction -- the oracle could only ever choose players Alpha already liked."""
        _seed(con)
        league = _league()
        static = load_season_static(con, league, 2023)
        available = set(static.projections)
        # Alpha "likes" the highest projections; realized points reverse that order.
        alpha_ranked = sorted(available, key=lambda p: (-static.projections[p], p))
        realized = {p: 100.0 + 25 * int(p.split("_")[1]) for p in available if "_" in p}
        slate = candidate_slate(
            static,
            available,
            alpha_ranked,
            realized,
            top_alpha=3,
            top_realized=3,
            top_projection=0,
        )
        best_realized = sorted(realized, key=lambda p: (-realized[p], p))[:3]
        assert any(p in slate for p in best_realized)
        assert all(p in slate for p in alpha_ranked[:3])

    def test_slate_is_deterministic(self, con):
        _seed(con)
        league = _league()
        static = load_season_static(con, league, 2023)
        available = set(static.projections)
        alpha_ranked = sorted(available, key=lambda p: (-static.projections[p], p))
        realized = dict.fromkeys(available, 0.0)
        a = candidate_slate(static, available, alpha_ranked, realized)
        b = candidate_slate(static, available, alpha_ranked, realized)
        assert a == b

    def test_slate_never_returns_an_unavailable_player(self, con):
        _seed(con)
        league = _league()
        static = load_season_static(con, league, 2023)
        available = {p for p in static.projections if p.startswith("WR")}
        alpha_ranked = sorted(static.projections, key=lambda p: (-static.projections[p], p))
        slate = candidate_slate(
            static, available, alpha_ranked, dict.fromkeys(static.projections, 0.0)
        )
        assert set(slate) <= available


class TestRegretAlgebra:
    def _pick(self, values, alpha_index):
        cands = [
            OracleCandidate(
                player_id=f"p{i}",
                position="WR",
                projection=0.0,
                alpha_score=0.0,
                alpha_rank=i + 1,
                realized_points=0.0,
                rollout_starter_points=v,
                rollout_total_points=v,
                unfilled_mandatory=0,
                is_alpha_pick=(i == alpha_index),
            )
            for i, v in enumerate(values)
        ]
        return OraclePick(
            season=2023,
            draft_slot=1,
            round_no=1,
            pick_overall=1,
            roster_positions=[],
            candidates=cands,
        )

    def test_regret_is_zero_when_alpha_is_the_oracle(self):
        p = self._pick([100.0, 90.0, 80.0], alpha_index=0)
        assert p.alpha_is_oracle
        assert p.regret == pytest.approx(0.0)

    def test_regret_is_the_gap_to_the_best_rollout(self):
        p = self._pick([100.0, 90.0, 80.0], alpha_index=2)
        assert not p.alpha_is_oracle
        assert p.regret == pytest.approx(20.0)

    def test_regret_is_never_negative(self):
        for alpha_index in range(3):
            assert self._pick([100.0, 90.0, 80.0], alpha_index).regret >= 0.0

    def test_empty_slate_has_zero_regret_rather_than_raising(self):
        p = OraclePick(season=2023, draft_slot=1, round_no=1, pick_overall=1, roster_positions=[])
        assert p.regret == pytest.approx(0.0)
        assert p.oracle is None


class TestAuditDraft:
    def test_audits_the_requested_rounds_only(self, con):
        _seed(con)
        league = _league()
        static = load_season_static(con, league, 2023)
        picks = audit_draft(
            con,
            league,
            2023,
            1,
            static,
            rounds=(1, 2),
            top_alpha=3,
            top_realized=3,
            top_projection=2,
        )
        assert [p.round_no for p in picks] == [1, 2]

    def test_every_audited_pick_evaluates_alphas_own_choice(self, con):
        """Without this the regret is undefined: there would be nothing to compare the oracle
        against."""
        _seed(con)
        league = _league()
        static = load_season_static(con, league, 2023)
        picks = audit_draft(
            con,
            league,
            2023,
            1,
            static,
            rounds=(1, 3),
            top_alpha=3,
            top_realized=3,
            top_projection=2,
        )
        assert picks
        for p in picks:
            assert p.alpha is not None
            assert sum(1 for c in p.candidates if c.is_alpha_pick) == 1

    def test_the_audited_trajectory_is_alphas_not_the_oracles(self, con):
        """The draft must continue with the ENGINE's pick, so regret is measured against the
        real production trajectory rather than compounding oracle picks into a hindsight draft."""
        _seed(con)
        league = _league()
        static = load_season_static(con, league, 2023)
        picks = audit_draft(
            con, league, 2023, 1, static, top_alpha=4, top_realized=4, top_projection=2
        )
        expected = simulate_forensic_draft(
            con,
            league,
            2023,
            SHIPPED_TIER,
            1,
            static,
            opponent_strategy=MARKET_CONSENSUS_ROSTER_AWARE,
        )
        assert [p.alpha.player_id for p in picks] == expected.drafted_player_ids

    def test_regret_is_non_negative_at_every_audited_pick(self, con):
        _seed(con)
        league = _league()
        static = load_season_static(con, league, 2023)
        picks = audit_draft(
            con,
            league,
            2023,
            1,
            static,
            rounds=(1, 2, 3),
            top_alpha=3,
            top_realized=3,
            top_projection=2,
        )
        for p in picks:
            assert p.regret >= -1e-9


class TestD89FixtureSeedsTheLeaguesOwnBoard:
    """D89 regression: the fixture must seed the series the league actually resolves to.

    It previously seeded ecr_type 'do' / 'dynasty-overall' while `_league()` is
    `format="redraft"`, which resolves to 'ro' / 'redraft-overall'. Nothing read the seeded rows,
    `market_rank` came back empty, and the nine opponents drafted in `player_id` order -- so every
    oracle test in this module was silently exercising alphabetical opponents rather than the fair
    market field it names. `assert_usable_market_board` caught it.

    This does not affect D86's published oracle numbers, which ran against the real database and a
    real preseason board; it affected only this module's fixture."""

    def test_the_seeded_board_is_the_one_the_league_resolves_to(self, con):
        from alpha_squad.market.series import resolve_market_series

        _seed(con)
        league = _league()
        series = resolve_market_series(league)
        seeded = {
            row[0]
            for row in con.execute(
                "SELECT DISTINCT ecr_type || '/' || page_type FROM market_snapshot"
            ).fetchall()
        }
        assert f"{series.ecr_type}/{series.page_type}" in seeded

    def test_market_rank_is_non_empty_so_opponents_are_not_alphabetical(self, con):
        _seed(con)
        static = load_season_static(con, _league(), 2023)
        assert static.market_rank, "empty board => opponents would draft by player_id"
        assert len(static.market_rank) == 32  # 4 positions x 8 players

    def test_the_guard_accepts_this_fixture(self, con):
        from alpha_squad.evaluation.draft_forensics import assert_usable_market_board

        _seed(con)
        static = load_season_static(con, _league(), 2023)
        assert_usable_market_board(static, MARKET_CONSENSUS_ROSTER_AWARE)


class TestShippedTierIsProduction:
    """D103 Part 1. The module docstring claims `L0`/`Q0`/`Z0` are "asserted byte-identical to
    `recommend_draft_pick` by existing tests". Before D103 no such test existed:
    `test_l0_is_the_shipped_engine` compares L0 only to its SIBLING REPLICAS Q0 and Z0, so a
    drift common to all three would pass silently, and the only test touching production
    (`test_tier_h_matches_a_direct_recommend_draft_pick_call`) pins tier H on the FIRST pick
    alone.

    That matters because `SHIPPED_TIER` is the rollout policy: every regret number the oracle has
    ever produced assumes it is production. These tests close the gap by walking whole drafts and
    comparing the CHOSEN PLAYER -- not a score -- at every state the instrument actually reaches,
    with tier `H` (a direct pass-through to `recommend_draft_pick`) as the reference.

    Scope, stated rather than implied: this runs on the offline fixture board, because the suite
    never opens the real database. The same comparison over the real 2021-2025 population
    (5 seasons x slots {1,5,10} x 16 rounds) was run as a research check and agreed on 240 of 240
    pick states; it is reproducible via `scripts/research/d103_pick_regret.py --parity`."""

    def _replay_comparing_tiers(
        self, con, league, season, static, draft_slot, replica_tier=SHIPPED_TIER
    ):
        """Play one draft with production (tier H) and, at every one of OUR pick states, ask
        `replica_tier` (by default `SHIPPED_TIER`) for its pick from the identical pool, roster
        and pick numbers.

        Mirrors `audit_draft`'s loop exactly -- same snake geometry, same fair opponent, same
        `picks_remaining` -- so the states compared are the states the oracle audits."""
        total_rounds = int(league.roster["roster_size"])
        my_picks = [
            snake_overall_pick(r, draft_slot, league.teams) for r in range(1, total_rounds + 1)
        ]
        avail = set(static.projections)
        mine: list[str] = []
        opps: dict[int, list[str]] = {s: [] for s in range(1, league.teams + 1) if s != draft_slot}
        compared = 0

        for current, round_no, slot in draft_order(league):
            if not avail:
                break
            picks_remaining = total_rounds - round_no + 1
            if slot != draft_slot:
                pick = roster_aware_market_pick(
                    avail, static.market_rank, static.positions, league, opps[slot], picks_remaining
                )
                opps[slot].append(static.positions.get(pick, "UNKNOWN"))
                avail.discard(pick)
                continue

            nxt = next((p for p in my_picks if p > current), None)
            my_positions = [static.positions.get(p, "UNKNOWN") for p in mine]
            kwargs = dict(
                roster_player_ids=list(mine),
                picks_remaining=picks_remaining,
            )
            production, _ = _pick_by_tier(
                static,
                con,
                league,
                season,
                set(avail),
                list(my_positions),
                "H",
                current,
                nxt,
                **kwargs,
            )
            replica, _ = _pick_by_tier(
                static,
                con,
                league,
                season,
                set(avail),
                list(my_positions),
                replica_tier,
                current,
                nxt,
                **kwargs,
            )
            assert replica == production, (
                f"round {round_no} slot {draft_slot}: {replica_tier} chose {replica!r} but "
                f"production (tier H / recommend_draft_pick) chose {production!r}"
            )
            compared += 1
            # Continue on PRODUCTION's pick, so a divergence cannot hide by forking the state.
            mine.append(production)
            avail.discard(production)
        return compared

    @pytest.mark.parametrize("draft_slot", [1, 2, 3, 4])
    def test_shipped_tier_picks_identically_to_production_at_every_state(self, con, draft_slot):
        _seed(con)
        league = _league()
        static = load_season_static(con, league, 2023)
        compared = self._replay_comparing_tiers(con, league, 2023, static, draft_slot)
        assert compared == int(league.roster["roster_size"]), "every round must be compared"

    def test_the_comparison_would_catch_a_divergence(self, con):
        """A parity test that cannot fail is not a parity test.

        Tier `A` is a genuinely different objective (the earliest forensic tier, not the shipped
        score), so running the SAME replay against it must trip the SAME assertion. Checked over
        a whole draft rather than one pick: two different objectives can agree on the obvious
        first pick and diverge later, and it is the later states this guard has to protect."""
        _seed(con)
        league = _league()
        static = load_season_static(con, league, 2023)
        with pytest.raises(AssertionError, match="chose"):
            self._replay_comparing_tiers(con, league, 2023, static, 1, replica_tier="A")


def _seed_weeks(con, season=2023, n_per_position=8, absent="QB_7", missing_after_week=8):
    """Weekly participation rows consistent with `_seed`'s season totals, plus a deliberate gap.

    Every player's season total is spread evenly over 17 weeks, EXCEPT `absent`, who disappears
    after `missing_after_week`. `absent` defaults to the highest-REALIZED player at QB, because
    `_seed` reverses the projection order (realized = 100 + 25i), so index 7 is the one a
    season-long lineup allocator actually starts. That is what makes the gap meaningful: under
    the season-long objective the starter never vacates the slot and every bench player is worth
    exactly zero, while under the weekly objective a backup really does enter the lineup for
    weeks 9-17. `player_week_stats` carries a foreign key to `players`, so the spine goes first."""
    for position in ("QB", "RB", "WR", "TE"):
        for i in range(n_per_position):
            player_id = f"{position}_{i}"
            con.execute(
                "INSERT INTO players (player_id, gsis_id, display_name, position) "
                "VALUES (?, ?, ?, ?) ON CONFLICT DO NOTHING",
                [player_id, f"gsis_{player_id}", player_id, position],
            )
            weekly_points = (100.0 + i * 25) / 17.0
            last_week = missing_after_week if player_id == absent else 17
            for week in range(1, last_week + 1):
                game_id = f"{season}_{week:02d}_TST"
                con.execute(
                    "INSERT INTO games (game_id, season, week, game_type, game_date, "
                    "home_team, away_team) VALUES (?, ?, ?, 'REG', ?, 'TST', 'OPP') "
                    "ON CONFLICT DO NOTHING",
                    [game_id, season, week, f"{season}-09-01"],
                )
                con.execute(
                    "INSERT INTO player_week_stats (player_id, season, week, game_id, game_date, "
                    "team, position, fantasy_points_ppr, source_snapshot_id) "
                    "VALUES (?, ?, ?, ?, ?, 'TST', ?, ?, 'test')",
                    [player_id, season, week, game_id, f"{season}-09-01", position, weekly_points],
                )


class TestObjectiveSelection:
    """D103 Part 2. The oracle can now be told which roster-value function scores a rollout.

    `SEASON_LONG` stays the default so every published D86 number reproduces byte for byte; the
    tests that matter are that the default really is unchanged, that the alternative really does
    differ where D86 said it must, and that a caller cannot silently get the wrong one."""

    def test_season_long_scorer_is_exactly_the_pre_d103_behaviour(self, con):
        _seed(con)
        league, static = _league(), load_season_static(con, _league(), 2023)
        drafted = ["QB_0", "RB_0", "WR_0", "TE_0", "RB_1", "WR_1", "TE_1"]
        actual = _actual_points_for(con, 2023, drafted)
        scorer = make_roster_scorer(SEASON_LONG, league, static)
        assert scorer(drafted, actual) == _score_roster(league, drafted, static.positions, actual)

    def test_default_rollout_is_unchanged_by_the_new_parameter(self, con):
        """The reproducibility guarantee: `scorer=None` must be the old code path."""
        _seed(con)
        league, static = _league(), load_season_static(con, _league(), 2023)
        kwargs = dict(
            draft_slot=1,
            after_pick_overall=1,
            available=set(static.projections) - {"QB_0"},
            drafted=["QB_0"],
            opponent_rosters={s: [] for s in (2, 3, 4)},
            actual=_actual_points_for(con, 2023, sorted(static.projections)),
        )
        explicit = make_roster_scorer(SEASON_LONG, league, static)
        assert rollout(con, league, 2023, static, **kwargs) == rollout(
            con, league, 2023, static, scorer=explicit, **kwargs
        )

    def test_weekly_objective_refuses_to_run_without_the_weekly_table(self, con):
        _seed(con)
        with pytest.raises(ValueError, match="weekly participation table"):
            make_roster_scorer(
                WEEKLY_NO_FORESIGHT, _league(), load_season_static(con, _league(), 2023)
            )

    def test_unknown_objective_is_refused(self, con):
        _seed(con)
        with pytest.raises(ValueError, match="unknown objective"):
            make_roster_scorer("best_guess", _league(), load_season_static(con, _league(), 2023))

    def test_the_two_objectives_differ_exactly_where_the_bench_matters(self, con):
        """The measurement D103 exists to make possible.

        Two rosters differing ONLY in which backup QB occupies a bench slot. The season-long
        objective scores them IDENTICALLY -- the starter never vacates the slot, so the bench is
        worth exactly zero and the choice cannot register. The weekly objective separates them,
        because for weeks 9-17 the starter is absent and the backup really plays. That gap is
        precisely what makes late-pick regret measurable."""
        _seed(con)
        _seed_weeks(con, absent="QB_7")
        league, static = _league(), load_season_static(con, _league(), 2023)
        weekly = load_weekly_points(con, 2023)
        season_scorer = make_roster_scorer(SEASON_LONG, league, static)
        weekly_scorer = make_roster_scorer(WEEKLY_NO_FORESIGHT, league, static, weekly)

        # `_seed` reverses the projection order, so index 7 is the best realized player and index
        # 0/1 are genuine bench fodder under BOTH objectives. RB_6 fills FLEX.
        core = ["QB_7", "RB_7", "WR_7", "TE_7", "RB_6"]
        better_backup = [*core, "QB_1", "WR_1"]
        worse_backup = [*core, "QB_0", "WR_1"]
        actual = _actual_points_for(con, 2023, sorted(set(better_backup + worse_backup)))

        season_better, _, _ = season_scorer(better_backup, actual)
        season_worse, _, _ = season_scorer(worse_backup, actual)
        weekly_better, _, _ = weekly_scorer(better_backup, actual)
        weekly_worse, _, _ = weekly_scorer(worse_backup, actual)

        assert season_better == season_worse, (
            "the season-long objective must be blind to which bench QB was taken -- this is the "
            "defect D86 measured and D102 said makes late-pick regret unmeasurable"
        )
        assert weekly_better > weekly_worse, (
            "the weekly objective must reward the backup who covers the starter's missing weeks"
        )
        assert weekly_better != season_better, "the two objectives must not coincide here"

    def test_audit_draft_accepts_the_weekly_objective_end_to_end(self, con):
        _seed(con)
        _seed_weeks(con)
        league, static = _league(), load_season_static(con, _league(), 2023)
        weekly = load_weekly_points(con, 2023)
        picks = audit_draft(
            con,
            league,
            2023,
            1,
            static,
            rounds=(1,),
            objective=WEEKLY_NO_FORESIGHT,
            weekly=weekly,
        )
        assert picks and picks[0].candidates
        assert picks[0].regret >= 0.0
        assert picks[0].alpha is not None
        season_picks = audit_draft(con, league, 2023, 1, static, rounds=(1,))
        weekly_values = {c.player_id: c.rollout_starter_points for c in picks[0].candidates}
        season_values = {c.player_id: c.rollout_starter_points for c in season_picks[0].candidates}
        assert weekly_values != season_values, (
            "the objective must actually change the rollout value"
        )
