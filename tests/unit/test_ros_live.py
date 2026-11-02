"""Live-module helpers that do not need network access."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from alpha_squad.ros import live

pytestmark = pytest.mark.unit


def test_attach_fp_sums_only_when_every_remaining_week_is_covered():
    board = pd.DataFrame({"fp_id": ["1", "2"], "team": ["AAA", "BBB"]})
    fp = {"available": True, "weekly": {9: {1: 20.0, 2: 18.0}, 10: {1: 21.0}}}
    out = live.attach_fp(board, fp, {"AAA": [9, 10], "BBB": [9, 10]})
    assert out.loc[0, "fp_ros_proj"] == 41.0 and np.isnan(out.loc[1, "fp_ros_proj"])
    assert "unavailable" in out.loc[1, "fp_ros_note"]


def test_attach_fp_reports_unavailability_instead_of_inventing_numbers():
    out = live.attach_fp(
        pd.DataFrame({"fp_id": ["1"], "team": ["A"]}), {"available": False, "reason": "no key"}, {}
    )
    assert np.isnan(out.loc[0, "fp_ros_proj"]) and out.loc[0, "fp_ros_note"] == "no key"


def test_fp_live_projections_without_a_key_is_unavailable_not_fabricated(monkeypatch):
    from alpha_squad.config.settings import Settings

    monkeypatch.delenv("FANTASYPROS_API_KEY", raising=False)
    out = live.fp_live_projections([9], settings=Settings(fantasypros_api_key=None))
    assert out["available"] is False and "FANTASYPROS_API_KEY" in out["reason"]


def test_trade_yaml_roundtrip(tmp_path):
    p = tmp_path / "t.yaml"
    p.write_text(
        "roster: [a, b, c]\ntargets: [x]\ngive: [[a], [b, c]]\nwaiver_qbs: [w]\n"
        "standings: {my_wins: 4, other_wins: [3,3,4,5,5,5,6,6,2]}\nplayoffs: {playoff_teams: 6}\n"
    )
    lg, ti = live.load_trade_yaml(p)
    assert (
        lg.league_id == "target_league"
        and ti.roster == ["a", "b", "c"]
        and ti.give_packages == [["a"], ["b", "c"]]
    )
    assert (
        ti.scenario.my_wins == 4 and ti.scenario.assumption_based
    )  # opp mean not supplied -> still scenario
