"""Monte Carlo trade engine: determinism, common random numbers, replacement, classification."""

from __future__ import annotations

import numpy as np
import pytest

from alpha_squad.league.context import LeagueContext
from alpha_squad.ros import trade as T
from alpha_squad.ros.lineup import UNAVAILABLE, slot_plan

pytestmark = pytest.mark.unit

NOISE = {
    "weekly_sd": {p: {"a": 3.0, "b": 0.25} for p in ("QB", "RB", "WR", "TE")},
    "team_corr": {"WR": {"rho": 0.2}, "TE": {"rho": 0.15}, "RB": {"rho": 0.0}},
    "missed_fraction_sample": [0.2, 0.4, 0.6, 1.0],
}
WEEKS = tuple(range(9, 18))


def league(lineup=None) -> LeagueContext:
    return LeagueContext(
        league_id="t",
        format="redraft",
        teams=10,
        scoring={"ppr": True},
        lineup=lineup or {"QB": 1, "RB": 2, "WR": 2, "TE": 1, "FLEX": 2},
        roster={"bench": 6, "roster_size": 16},
    )


def asset(pid, pos, mu, team=None, avail=1.0, sd=1.0, weeks=WEEKS):
    return T.Asset(pid, pid, pos, team or pid, mu, sd, avail, tuple(weeks))


def fill_roster(qb_mu=15.0):
    return [
        asset("qb", "QB", qb_mu),
        asset("rb1", "RB", 14),
        asset("rb2", "RB", 12),
        asset("wr1", "WR", 13),
        asset("wr2", "WR", 11),
        asset("te", "TE", 8),
        asset("rb3", "RB", 7),
        asset("wr3", "WR", 7),
    ]


def waiver():
    return T.waiver_assets(
        league(),
        {
            "QB": (10.0, 1.0, 0.9),
            "RB": (6.0, 1.0, 0.9),
            "WR": (6.0, 1.0, 0.9),
            "TE": (5.0, 1.0, 0.9),
        },
        WEEKS,
    )


def test_simulation_is_deterministic_for_a_seed_and_differs_across_seeds():
    a = [asset("x", "QB", 18, avail=0.9)]
    s1 = T.simulate_assets(a, list(WEEKS), NOISE, 500, seed=3)["x"]
    s2 = T.simulate_assets(a, list(WEEKS), NOISE, 500, seed=3)["x"]
    s3 = T.simulate_assets(a, list(WEEKS), NOISE, 500, seed=4)["x"]
    assert np.array_equal(s1, s2) and not np.array_equal(s1, s3)


def test_an_assets_draws_do_not_depend_on_which_other_assets_are_simulated():
    a, b = asset("a", "QB", 18), asset("b", "RB", 12)
    solo = T.simulate_assets([a], list(WEEKS), NOISE, 300, seed=9)["a"]
    both = T.simulate_assets([b, a], list(WEEKS), NOISE, 300, seed=9)["a"]
    assert np.array_equal(solo, both)  # common random numbers across candidate rosters


def test_byes_are_exact_and_full_availability_means_no_missed_games():
    a = asset("a", "QB", 18, weeks=(9, 10, 12, 13), avail=1.0)
    sim = T.simulate_assets([a], list(WEEKS), NOISE, 200, seed=1)["a"]
    widx = {w: i for i, w in enumerate(WEEKS)}
    assert (sim[widx[11]] == UNAVAILABLE).all() and (sim[widx[9]] > UNAVAILABLE / 2).all()


def test_expected_availability_is_respected_on_average():
    a = asset("a", "QB", 18, avail=0.8)
    sim = T.simulate_assets([a], list(WEEKS), NOISE, 6000, seed=2)["a"]
    played = (sim > UNAVAILABLE / 2).mean()
    assert played == pytest.approx(0.8, abs=0.03)


def test_simulated_mean_matches_mu_and_teammates_are_positively_correlated():
    qb, wr = asset("q", "QB", 20, team="T1", sd=0.01), asset("w", "WR", 12, team="T1", sd=0.01)
    sim = T.simulate_assets([qb, wr], list(WEEKS), NOISE, 4000, seed=5)
    assert sim["q"].mean() == pytest.approx(20, abs=0.5)
    c = np.corrcoef(sim["q"].reshape(-1), sim["w"].reshape(-1))[0, 1]
    assert c == pytest.approx(0.2, abs=0.05)  # sqrt(.2)*sqrt(.2) from the loadings
    other = asset("o", "WR", 12, team="T2", sd=0.01)
    s2 = T.simulate_assets([qb, other], list(WEEKS), NOISE, 4000, seed=5)
    assert abs(np.corrcoef(s2["q"].reshape(-1), s2["o"].reshape(-1))[0, 1]) < 0.05


def test_trading_for_a_clearly_better_qb_at_no_cost_helps_nearly_always():
    sim = T.evaluate_trade(
        league(),
        fill_roster(12.0),
        [],
        [asset("star", "QB", 24, sd=1.0)],
        waiver(),
        NOISE,
        n_sims=800,
        seed=1,
    )
    s = sim.summary()
    assert s["mean"] > 40 and s["prob_improves"] > 0.97


def test_giving_a_bench_player_costs_nothing_but_giving_a_starter_does():
    roster = fill_roster()
    get = [asset("star", "QB", 22, sd=1.0)]
    bench = T.evaluate_trade(
        league(), roster, ["wr3"], get, waiver(), NOISE, n_sims=600, seed=1
    ).summary()["mean"]
    starter = T.evaluate_trade(
        league(), roster, ["rb1"], get, waiver(), NOISE, n_sims=600, seed=1
    ).summary()["mean"]
    assert bench > starter


def test_vacated_slot_is_refilled_at_waiver_level_not_zero():
    roster = [asset("qb", "QB", 15), asset("rb1", "RB", 14)]
    plan = slot_plan(league({"QB": 1, "RB": 1}))
    sim = T.evaluate_trade(
        league({"QB": 1, "RB": 1}),
        roster,
        ["rb1"],
        [],
        waiver(),
        NOISE,
        n_sims=500,
        seed=1,
        plan=plan,
    )
    # after giving the only RB the lineup falls back to a ~6 point waiver RB, not to 0
    loss = -sim.summary()["mean"]
    # lineups are chosen by forecast, so a swarm of identical ~6-pt waiver bodies cannot be
    # "best of five with hindsight" every week: expected loss ~ (14 - 6*0.9) * 9 games
    assert loss == pytest.approx((14 - 6 * 0.9) * len(WEEKS), rel=0.2)


def test_hindsight_lineups_overstate_depth_value():
    roster = [asset("qb", "QB", 15), asset("rb1", "RB", 14)]
    lg = league({"QB": 1, "RB": 1})
    plan = slot_plan(lg)
    fc = T.evaluate_trade(lg, roster, ["rb1"], [], waiver(), NOISE, n_sims=500, seed=1, plan=plan)
    hs = T.evaluate_trade(
        lg,
        roster,
        ["rb1"],
        [],
        waiver(),
        NOISE,
        n_sims=500,
        seed=1,
        plan=plan,
        hindsight_lineups=True,
    )
    assert (
        -hs.summary()["mean"] < -fc.summary()["mean"]
    )  # hindsight makes giving a starter look cheaper


def test_cannot_give_a_player_not_on_the_roster():
    with pytest.raises(ValueError):
        T.evaluate_trade(league(), fill_roster(), ["ghost"], [], waiver(), NOISE, n_sims=10)


def test_swapping_a_player_for_himself_is_neutral():
    roster = fill_roster()
    s = T.evaluate_trade(
        league(), roster, ["qb"], [roster[0]], waiver(), NOISE, n_sims=400, seed=1
    ).summary()
    assert s["mean"] == pytest.approx(0.0, abs=1e-9) and s["prob_improves"] == 0.0


def test_classification_requires_agreement_with_sensitivities_and_evidence():
    strong = {"mean": 30.0, "prob_improves": 0.9}
    assert T.classify(strong, {"a": {"mean": 12.0}})[0] == "Strongly favorable"
    lab, notes = T.classify(strong, {"a": {"mean": -3.0}})
    assert lab == "Favorable" and notes
    assert T.classify({"mean": 9.0, "prob_improves": 0.7}, {"a": {"mean": 1.0}})[0] == "Favorable"
    assert (
        T.classify({"mean": 9.0, "prob_improves": 0.7}, {"a": {"mean": -1.0}})[0]
        == "Approximately neutral"
    )
    assert T.classify({"mean": 2.0, "prob_improves": 0.55}, {})[0] == "Approximately neutral"
    assert (
        T.classify({"mean": -25.0, "prob_improves": 0.05}, {"a": {"mean": -9.0}})[0]
        == "Strongly unfavorable"
    )
    assert T.classify(strong, {}, evidence_ok=False)[0] == "Insufficient evidence"


def test_playoff_probability_is_monotone_in_team_strength_and_flags_assumptions():
    scen = T.LeagueScenario()
    assert scen.assumption_based
    weeks = list(range(9, 18))
    rng = np.random.default_rng(0)
    base = rng.normal(100, 15, (len(weeks), 3000))
    lo = T.simulate_outcomes(base, weeks, scen, opp_mean=100.0)
    hi = T.simulate_outcomes(base + 25, weeks, scen, opp_mean=100.0)
    assert hi["made_playoffs"].mean() > lo["made_playoffs"].mean() + 0.1
    assert hi["champion"].mean() > lo["champion"].mean()
    # identical rivals for before/after: a zero-change roster has exactly zero delta
    sim = T.TradeSim(base, base, weeks)
    d = T.playoff_deltas(sim, scen, 100.0)
    assert d["d_playoffs_pp"] == 0.0 and d["d_champion_pp"] == 0.0


def test_noise_model_counts_receivers_as_playing_and_fits_every_position():
    import pandas as pd

    from alpha_squad.ros import noise as NZ

    rng = np.random.default_rng(0)
    rows = []
    for pos, att, car, tgt in (
        ("QB", 30, 3, 0),
        ("RB", 0, 15, 3),
        ("WR", 0, 0, 8),
        ("TE", 0, 0, 5),
    ):
        for pid in range(30):
            mu = 8 + pid * 0.3
            for wk in range(1, 13):
                rows.append(
                    dict(
                        player_id=f"{pos}{pid}",
                        season=2023,
                        week=wk,
                        team=f"T{pid}",
                        position=pos,
                        attempts=att,
                        carries=car,
                        targets=tgt,
                        appeared=int(att + car > 0),
                        pts=float(max(rng.normal(mu, 2 + 0.2 * mu), 0)),
                    )
                )
    model = NZ.fit_weekly_sd(pd.DataFrame(rows))
    assert set(model) == {"QB", "RB", "WR", "TE"}  # WR/TE have `appeared` == 0 but DID play
    assert all(v["b"] > 0 for v in model.values())
