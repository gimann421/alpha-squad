"""W12 timestamped-information instrument: cutoff, injury-report features, pre-registered verdict."""

from __future__ import annotations

import datetime as dt

import pytest

from alpha_squad.evaluation.weekly import timestamped as ts

FRI = dt.date(2023, 10, 6)
K = ts.cutoff_instant(FRI)
SEC = dt.timedelta(seconds=1)


def _row(pid, status=None, practice=None, modified=K - dt.timedelta(hours=4), position="RB"):
    return {
        "player_id": pid,
        "position": position,
        "status": status,
        "practice": practice,
        "modified": modified,
    }


def test_cutoff_rule():
    assert ts.friday_before(dt.date(2023, 10, 8)) == FRI
    assert ts.friday_before(dt.date(2023, 10, 6)) == dt.date(2023, 9, 29)
    assert ts.cutoff_instant(FRI) == dt.datetime(2023, 10, 6, 23, 59, 59, tzinfo=ts.ET)
    assert ts.cutoff_instant(FRI, strict=True) == dt.datetime(2023, 10, 6, tzinfo=ts.ET)
    # Friday 23:30 ET is Saturday in UTC and is still before the cutoff
    late = dt.datetime(2023, 10, 7, 3, 30, tzinfo=dt.UTC)
    assert late <= K and not late <= ts.cutoff_instant(FRI, strict=True)


def test_team_alias():
    assert ts.team_code("OAK") == "LV" and ts.team_code("SD") == "LAC"
    assert ts.team_code("STL") == "LA" and ts.team_code("KC") == "KC"


def test_touches_per_game_window():
    games = [(1, 30.0), (2, 10.0), (3, 12.0), (4, 14.0), (6, 99.0)]
    assert ts.touches_per_game(games, 5) == pytest.approx(12.0)
    assert ts.touches_per_game(games, 1) == 0.0


def test_teammate_out_is_counted_by_workload():
    rows = [
        _row("me"),
        _row("star", "Out"),
        _row("backup", "Doubtful"),
        _row("wr", "Out", position="WR"),
    ]
    f = ts.features("me", "RB", rows, K, {"star": 18.0, "backup": 3.0, "wr": 9.0}, set())
    assert f["tm_out_opp"] == pytest.approx(21.0)  # other positions never count
    assert ts.vacancy(f) is True
    assert f["own_status"] == 0.0 and f["own_practice"] == 0.0


def test_one_second_after_the_cutoff_is_invisible():
    late = [_row("me"), _row("star", "Out", modified=K + SEC)]
    on_time = [_row("me"), _row("star", "Out", modified=K - SEC)]
    tpg = {"star": 20.0}
    assert ts.features("me", "RB", late, K, tpg, set())["tm_out_opp"] == 0.0
    assert ts.features("me", "RB", on_time, K, tpg, set())["tm_out_opp"] == 20.0


def test_unobservable_report_is_missing_not_healthy():
    rows = [_row("star", "Out", modified=K + SEC)]
    f = ts.features("me", "RB", rows, K, {"star": 20.0}, set())
    assert all(v is None for v in f.values()) and ts.vacancy(f) is None
    assert all(v is None for v in ts.features("me", "RB", [], K, {}, set()).values())


def test_own_row_edited_after_the_cutoff_is_invisible():
    # Regression (W12 A1): calling it "unknown" revealed that a post-cutoff edit existed.
    rows = [_row("other"), _row("me", "Questionable", modified=K + SEC)]
    f = ts.features("me", "RB", rows, K, {}, set())
    assert f["own_status"] == 0.0 and f["own_practice"] == 0.0
    rows = [_row("other"), _row("me", "Questionable", "Limited Participation in Practice")]
    f = ts.features("me", "RB", rows, K, {}, set())
    assert f["own_status"] == 1.0 and f["own_practice"] == 1.0


def test_deleting_post_cutoff_rows_never_changes_a_feature():
    rows = [
        _row("me", "Out", modified=K + SEC),
        _row("star", "Out"),
        _row("late", "Out", modified=K + SEC),
        _row("q", "Questionable", modified=K + 3600 * SEC),
    ]
    tpg = {"star": 12.0, "late": 9.0, "q": 4.0}
    pruned = [r for r in rows if r["modified"] <= K]
    for pid in ("me", "star", "late", "q", "nobody"):
        assert ts.features(pid, "RB", rows, K, tpg, {"q"}) == ts.features(
            pid, "RB", pruned, K, tpg, {"q"}
        )


def test_questionable_and_returning_teammates():
    rows = [_row("me"), _row("q", "Questionable"), _row("back", None), _row("gone", "Out")]
    f = ts.features("me", "RB", rows, K, {"q": 6.0, "back": 15.0, "gone": 4.0}, {"back", "gone"})
    assert f["tm_q_opp"] == 6.0
    assert f["tm_ret_opp"] == 15.0  # an Out teammate who missed last game is not "returning"
    assert f["tm_out_opp"] == 4.0


def test_status_and_practice_codes():
    for status, code in (("Out", 3.0), ("Doubtful", 2.0), ("Questionable", 1.0), ("Probable", 0.0)):
        f = ts.features("me", "RB", [_row("me", status)], K, {}, set())
        assert f["own_status"] == code
    f = ts.features("me", "RB", [_row("me", "Out", "Out (Definitely Will Not Play)")], K, {}, set())
    assert f["own_practice"] == 2.0
    assert set(ts.FEATURES) == {c for v in ts.CATEGORIES.values() for c in v}


def _r(m, lo, hi):
    return {"mean_diff": m, "ci_low": lo, "ci_high": hi}


COV = {"risers": 666, "vacancy": 39, "breakouts": 120, "vacancy_weeks": 30}
GOOD = {
    "coverage": COV,
    "qa1": {"diff": 0.2, "ci_low": 0.05, "ci_high": 0.35},
    "rb": _r(0.025, 0.008, 0.04),
    "rb_null": _r(0.02, 0.004, 0.036),
    "rb_seasons": [0.03, 0.02, 0.01, -0.01],
    "rb_loso": [_r(0.02, 0.001, 0.04)] * 3 + [_r(0.02, -0.001, 0.04)],
    "guard": {"TE|capture@10": _r(0.0, -0.01, 0.01)},
    "wr": _r(-0.002, -0.01, 0.006),
    "wr_vs_a": _r(0.02, 0.005, 0.035),
}


def test_coverage_gate_comes_first():
    for key in COV:
        v = ts.verdict(GOOD | {"coverage": COV | {key: 0}})
        assert v["verdict"] == "DATA INSUFFICIENT"


def test_actionable_needs_every_condition():
    assert ts.verdict(GOOD)["verdict"] == "INFORMATION EXISTS + ACTIONABLE"
    for bad in (
        {"rb": _r(0.015, 0.001, 0.03)},
        {"rb_null": _r(0.01, -0.005, 0.03)},
        {"rb_seasons": [0.03, -0.02, -0.01, 0.04]},
        {"wr_vs_a": _r(0.01, -0.005, 0.02)},
    ):
        assert ts.verdict(GOOD | bad)["verdict"] == "INFORMATION EXISTS + NOT ACTIONABLE"


def test_tradeoff_harm_and_no_signal():
    assert ts.verdict(GOOD | {"wr": _r(-0.02, -0.03, -0.01)})["verdict"] == "TRADEOFF"
    harm = GOOD | {"rb": _r(0.0, -0.01, 0.01), "guard": {"WR|spearman": _r(-0.01, -0.02, -0.006)}}
    assert ts.verdict(harm)["verdict"] == "HARM"
    none = GOOD | {
        "rb": _r(0.003, -0.006, 0.012),
        "qa1": {"diff": 0.1, "ci_low": -0.02, "ci_high": 0.2},
    }
    assert ts.verdict(none)["verdict"] == "NO INCREMENTAL SIGNAL"
    exists = none | {"qa1": {"diff": 0.1, "ci_low": 0.01, "ci_high": 0.2}}
    assert ts.verdict(exists)["verdict"] == "INFORMATION EXISTS + NOT ACTIONABLE"


def test_small_significant_loss_is_not_a_breach():
    assert not ts.is_breach(_r(-0.003, -0.005, -0.001)) and ts.is_breach(_r(-0.006, -0.01, -0.001))


def test_features_do_not_depend_on_row_order():
    rows = [_row("me")] + [_row(f"t{i}", "Out") for i in range(6)]
    tpg = {f"t{i}": v for i, v in enumerate((0.1, 0.2, 0.3, 1e16, -1e16, 0.7))}
    a = ts.features("me", "RB", rows, K, tpg, set())
    b = ts.features("me", "RB", list(reversed(rows)), K, tpg, set())
    assert a == b and a["tm_out_opp"] == pytest.approx(1.3)
