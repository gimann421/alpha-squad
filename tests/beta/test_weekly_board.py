"""W16 beta board rules, on synthetic inputs (no database, no model)."""

from __future__ import annotations

import datetime as dt
import json

import pytest

from alpha_squad.beta import weekly_board as wb

pytestmark = pytest.mark.unit

GEN = dt.datetime(2026, 10, 11, 12, 0, tzinfo=dt.UTC)  # Sunday 08:00 ET

SCHEDULE = [
    # Thursday game: already started at GEN.
    {
        "season": 2026,
        "game_type": "REG",
        "week": 5,
        "gameday": "2026-10-08",
        "gametime": "20:15",
        "home_team": "KC",
        "away_team": "BUF",
        "game_id": "g1",
    },
    # Sunday game: not started.
    {
        "season": 2026,
        "game_type": "REG",
        "week": 5,
        "gameday": "2026-10-11",
        "gametime": "13:00",
        "home_team": "DAL",
        "away_team": "PHI",
        "game_id": "g2",
    },
    # Another week and a non-REG row must be ignored.
    {
        "season": 2026,
        "game_type": "REG",
        "week": 6,
        "gameday": "2026-10-18",
        "gametime": "13:00",
        "home_team": "NYJ",
        "away_team": "MIA",
        "game_id": "g3",
    },
    {
        "season": 2026,
        "game_type": "PRE",
        "week": 5,
        "gameday": "2026-10-11",
        "gametime": "13:00",
        "home_team": "NYJ",
        "away_team": "MIA",
        "game_id": "g4",
    },
]


def _r(gsis, team, pos, status="ACT", week=5, name=None):
    return {
        "gsis_id": gsis,
        "team": team,
        "position": pos,
        "status": status,
        "week": week,
        "full_name": name or gsis,
    }


ROSTER = [
    _r("g-rookie", "DAL", "WR"),  # has never played: no stats anywhere
    _r("g-vet", "PHI", "RB"),
    _r("g-te", "KC", "TE"),
    _r("g-qb", "BUF", "QB"),
    _r("g-k", "DAL", "K"),
    _r("g-ir", "DAL", "WR", status="RES"),
    _r("g-ps", "PHI", "RB", status="DEV"),
    _r("g-ina", "KC", "WR", status="INA"),
    _r("g-bye", "NYJ", "WR"),  # NYJ has no week-5 game
    _r("g-unknown", "PHI", "WR"),  # no canonical id
    _r("g-ol", "DAL", "OL"),  # not a fantasy position
]
IDS = {
    g: f"p_{g[2:]}"
    for g in ("g-rookie", "g-vet", "g-te", "g-qb", "g-k", "g-ir", "g-ps", "g-ina", "g-bye", "g-ol")
}


def _universe(**kw):
    games = wb.week_games(SCHEDULE, 2026, 5)
    return wb.build_universe(ROSTER, games, IDS, GEN, **kw)


def test_kickoff_is_eastern_time_and_requires_a_time():
    assert wb.kickoff_utc("2026-10-11", "13:00") == dt.datetime(2026, 10, 11, 17, 0, tzinfo=dt.UTC)
    assert wb.kickoff_utc("2026-12-06", "13:00").hour == 18  # EST after DST ends
    with pytest.raises(ValueError):
        wb.kickoff_utc("2026-10-11", None)


def test_week_games_only_reg_games_of_the_week_and_byes_absent():
    games = wb.week_games(SCHEDULE, 2026, 5)
    assert set(games) == {"KC", "BUF", "DAL", "PHI"}
    assert games["KC"].opponent == "BUF" and games["KC"].home
    assert not games["BUF"].home
    dup = SCHEDULE + [dict(SCHEDULE[1], game_id="dup")]
    with pytest.raises(ValueError):
        wb.week_games(dup, 2026, 5)


def test_roster_week_uses_latest_week_not_after_target():
    rows = [_r("a", "KC", "WR", week=3), _r("a", "KC", "WR", week=4), _r("b", "KC", "WR", week=6)]
    used, out = wb.roster_week_rows(rows, 5)
    assert used == 4 and [r["gsis_id"] for r in out] == ["a"]
    assert wb.roster_week_rows(rows, 2) == (None, [])


def test_player_without_any_stats_is_eligible():
    entries, _ = _universe()
    ids = {e.player_id for e in entries}
    assert "p_rookie" in ids  # eligibility comes from the roster, never a box score


def test_bye_week_players_are_excluded_and_counted():
    entries, ex = _universe()
    assert "p_bye" not in {e.player_id for e in entries}
    assert ex.bye_teams == ["NYJ"] and ex.bye_players == 1
    assert "asq_dst_NYJ" not in {e.player_id for e in entries}


def test_bye_teams_come_from_the_schedule_when_the_roster_omits_them():
    """Regression (W16, real 2026 week 5): nflverse's weekly roster leaves bye teams out, so a
    bye list built from roster teams was empty while CAR and KC were on bye."""
    games = wb.week_games(SCHEDULE, 2026, 5)
    roster = [r for r in ROSTER if r["team"] != "NYJ"]
    _, ex = wb.build_universe(roster, games, IDS, GEN)
    assert ex.bye_teams == []  # the old behaviour: invisible
    _, ex = wb.build_universe(
        roster, games, IDS, GEN, season_teams={"KC", "BUF", "DAL", "PHI", "NYJ", "MIA"}
    )
    assert ex.bye_teams == ["MIA", "NYJ"]


def test_roster_status_rules_are_explicit():
    entries, ex = _universe()
    ids = {e.player_id for e in entries}
    assert "p_ir" not in ids and "p_ps" not in ids
    assert ex.roster_status == {"RES": 1, "DEV": 1}
    ina = next(e for e in entries if e.player_id == "p_ina")
    assert ina.roster_status == "INA"  # shown as availability, not removed


def test_unresolved_identity_is_reported_not_dropped_silently():
    entries, ex = _universe()
    assert [u["gsis_id"] for u in ex.unresolved_identity] == ["g-unknown"]
    assert "g-unknown" not in {e.player_id for e in entries}


def test_identity_keys_are_canonical_ids_and_dst_from_team_code():
    entries, _ = _universe()
    by = {e.player_id: e for e in entries}
    assert by["p_vet"].gsis_id == "g-vet" and by["p_vet"].team == "PHI"
    dst = [e for e in entries if e.position == "DST"]
    assert sorted(e.player_id for e in dst) == [
        "asq_dst_BUF",
        "asq_dst_DAL",
        "asq_dst_KC",
        "asq_dst_PHI",
    ]
    assert "p_ol" not in by


def test_started_games_are_flagged_by_kickoff_vs_cutoff():
    entries, _ = _universe()
    by = {e.player_id: e for e in entries}
    assert by["p_te"].game_started and by["p_qb"].game_started  # Thursday KC-BUF
    assert not by["p_rookie"].game_started and not by["p_vet"].game_started


def test_injury_status_is_attached_not_used_to_remove():
    entries, _ = _universe(injuries={"g-vet": "Questionable", "g-rookie": "Out"})
    by = {e.player_id: e for e in entries}
    assert by["p_vet"].injury_status == "Questionable"
    assert by["p_rookie"].injury_status == "Out"  # still on the board


def test_duplicate_player_on_roster_raises():
    games = wb.week_games(SCHEDULE, 2026, 5)
    with pytest.raises(ValueError):
        wb.build_universe([_r("g-vet", "PHI", "RB"), _r("g-vet", "DAL", "RB")], games, IDS, GEN)


def test_half_ppr_is_full_minus_half_recent_receptions():
    assert wb.half_ppr(15.0, 6.0) == 12.0
    assert wb.half_ppr(15.0, None) == 15.0
    assert wb.half_ppr(15.0, float("nan")) == 15.0
    assert wb.scored(None, 3.0) is None
    assert wb.scored(10.0, 4.0) == {"full_ppr": 10.0, "half_ppr": 8.0}


def _players():
    def p(pid, pos, a, b, rec=0.0):
        return {
            "player_id": pid,
            "position": pos,
            "projections": {wb.CONTROL: wb.scored(a, rec), wb.W10: wb.scored(b, rec)},
        }

    return [
        p("qb1", "QB", 20.0, 20.0),
        p("rb1", "RB", 14.0, 13.0, rec=1.0),
        p("wr1", "WR", 15.0, 18.0, rec=8.0),
        p("wr2", "WR", 15.0, 9.0, rec=2.0),  # ties wr1 under control, Full PPR
        p("te1", "TE", 9.0, 11.0, rec=5.0),
        p("k1", "K", 8.0, 8.0),
        p("dst1", "DST", 7.0, 7.0),
        {"player_id": "nop", "position": "WR", "projections": {wb.CONTROL: None, wb.W10: None}},
    ]


def test_flex_contains_only_rb_wr_te():
    ps = _players()
    by = {p["player_id"]: p["position"] for p in ps}
    for m in wb.MODELS:
        for s in wb.SCORINGS:
            flex = wb.rank_view(ps, m, s, "FLEX")
            assert {by[i] for i in flex} <= {"RB", "WR", "TE"}
            assert set(flex) == {"rb1", "wr1", "wr2", "te1"}


def test_position_filters_and_overall():
    ps = _players()
    assert wb.rank_view(ps, wb.CONTROL, wb.FULL_PPR, "QB") == ["qb1"]
    assert wb.rank_view(ps, wb.CONTROL, wb.FULL_PPR, "K") == ["k1"]
    assert wb.rank_view(ps, wb.CONTROL, wb.FULL_PPR, "DST") == ["dst1"]
    overall = wb.rank_view(ps, wb.CONTROL, wb.FULL_PPR, "OVERALL")
    assert overall[0] == "qb1" and "nop" not in overall and len(overall) == 7


def test_board_sorted_by_selected_model_and_scoring_with_id_tiebreak():
    ps = _players()
    assert wb.rank_view(ps, wb.CONTROL, wb.FULL_PPR, "WR") == ["wr1", "wr2"]  # tie -> id
    assert wb.rank_view(ps, wb.W10, wb.FULL_PPR, "FLEX") == ["wr1", "rb1", "te1", "wr2"]
    # Half-PPR: wr1 15-4=11, wr2 15-1=14, rb1 13.5, te1 6.5
    assert wb.rank_view(ps, wb.CONTROL, wb.HALF_PPR, "FLEX") == ["wr2", "rb1", "wr1", "te1"]
    by = {p["player_id"]: p for p in ps}
    for m in wb.MODELS:
        for s in wb.SCORINGS:
            vals = [by[i]["projections"][m][s] for i in wb.rank_view(ps, m, s, "OVERALL")]
            assert vals == sorted(vals, reverse=True)


def test_unknown_board_rejected():
    with pytest.raises(ValueError):
        wb.rank_view(_players(), "w11", wb.FULL_PPR, "WR")
    with pytest.raises(ValueError):
        wb.rank_view(_players(), wb.CONTROL, "standard", "WR")
    with pytest.raises(ValueError):
        wb.rank_view(_players(), wb.CONTROL, wb.FULL_PPR, "SUPERFLEX")


def _snapshot(generated_at=GEN, control_bump=0.0):
    entries, ex = _universe()
    proj = {wb.CONTROL: {}, wb.W10: {}}
    src = {wb.CONTROL: {}, wb.W10: {}}
    inputs = {}
    for n, e in enumerate(sorted(entries, key=lambda e: e.player_id)):
        proj[wb.CONTROL][e.player_id] = 10.0 + n + control_bump
        proj[wb.W10][e.player_id] = 30.0 - n
        src[wb.CONTROL][e.player_id] = "control"
        src[wb.W10][e.player_id] = "w10"
        inputs[e.player_id] = {"receptions_avg_last3": float(n % 3)}
    return wb.assemble_snapshot(
        season=2026,
        week=5,
        generated_at=generated_at,
        entries=entries,
        exclusions=ex,
        projections=proj,
        sources=src,
        inputs=inputs,
        models={wb.CONTROL: {"model": "ml_catboost"}, wb.W10: {"model": "ALPHA_PLUS_HISTORICAL"}},
        data_sources=[{"source": "nflverse", "dataset": "weekly_rosters", "sha256": "x"}],
        roster_week_used=5,
        checks={"ok": True},
    )


def test_snapshot_is_deterministic_and_identified():
    a, b = _snapshot(), _snapshot()
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
    assert a["snapshot_id"] == b["snapshot_id"]
    assert _snapshot(generated_at=GEN + dt.timedelta(minutes=1))["snapshot_id"] != a["snapshot_id"]
    assert _snapshot(control_bump=0.5)["snapshot_id"] != a["snapshot_id"]


def test_snapshot_metadata_identifies_models_scoring_cutoff_and_is_experimental():
    s = _snapshot()
    assert s["experimental"] is True and "NOT validated" in s["disclaimer"]
    assert s["beta_version"] == wb.BETA_VERSION
    assert s["season"] == 2026 and s["week"] == 5
    assert s["cutoff"] == s["generated_at"] == GEN.isoformat()
    assert set(s["models"]) == set(wb.MODELS)
    assert set(s["scoring"]) == set(wb.SCORINGS) and "approximation" in s["scoring"]["half_ppr"]
    assert s["data_sources"] and s["roster_week_used"] == 5
    assert set(s["boards"]) == set(wb.MODELS)
    for m in wb.MODELS:
        assert set(s["boards"][m]) == set(wb.SCORINGS)
        assert set(s["boards"][m][wb.FULL_PPR]) == set(wb.VIEWS)


def test_snapshot_boards_match_the_selected_models_projections():
    s = _snapshot()
    by = {p["player_id"]: p for p in s["players"]}
    a = s["boards"][wb.CONTROL][wb.FULL_PPR]["OVERALL"]
    b = s["boards"][wb.W10][wb.FULL_PPR]["OVERALL"]
    assert a != b  # the selector changes the board
    for m, order in ((wb.CONTROL, a), (wb.W10, b)):
        vals = [by[i]["projections"][m][wb.FULL_PPR] for i in order]
        assert vals == sorted(vals, reverse=True)
        assert all(
            by[i]["projection_source"][m] == ("control" if m == wb.CONTROL else "w10")
            for i in order
        )
