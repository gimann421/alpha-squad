"""Pre-registered walk-forward projection calibration (docs/DECISIONS.md D68).

These tests pin the things that make the experiment trustworthy rather than merely runnable:
the leakage guard is structural, the evidence prior really does refuse to emit an adjustment on
thin evidence, the rank bands come from the league config rather than a constant, and the
control arm is the identity. Written alongside the pre-registration, before any arm was fitted
against real data.
"""

from __future__ import annotations

import pytest

from alpha_squad.evaluation.projection_calibration import (
    CALIBRATED_POSITIONS,
    FIRST_RESIDUAL_SEASON,
    MIN_TRAINING_ROWS,
    MIN_TRAINING_SEASONS,
    PREREGISTERED_TREATED_SEASONS,
    PREREGISTERED_X_CONTROL,
    X_ARMS,
    ResidualRow,
    apply_calibration,
    band_edges,
    band_of,
    draftable_depth,
    fit_arm,
)
from alpha_squad.league.context import LeagueContext, load_league_context

TARGET = "src/alpha_squad/config/league_configs/target_league.yaml"
LEGACY = "src/alpha_squad/config/league_configs/legacy_2qb_dynasty.yaml"

#: Roughly the shape `market_draft_demand` measures on the target format (D67), used so the
#: band edges under test are the ones the real experiment uses.
DEMAND = {"QB": 2.04, "RB": 4.64, "WR": 5.64, "TE": 1.68, "K": 1.0, "DST": 1.0}


def _target() -> LeagueContext:
    return load_league_context(TARGET)


def _rows(
    seasons: list[int],
    position: str = "RB",
    per_season: int = 40,
    residual: float = 20.0,
    band: int = 1,
) -> list[ResidualRow]:
    """A synthetic residual history with a known constant bias, so an estimator's output is
    checkable by hand rather than only against itself."""
    rows: list[ResidualRow] = []
    for season in seasons:
        for i in range(per_season):
            projected = 300.0 - i
            rows.append(
                ResidualRow(
                    season=season,
                    player_id=f"{position}_{season}_{i:03d}",
                    position=position,
                    projected=projected,
                    realized=projected + residual,
                    pos_rank=i + 1,
                    band=band,
                )
            )
    return rows


class TestLeakageGuard:
    """The single most important property of the whole module."""

    @pytest.mark.parametrize("arm", X_ARMS)
    def test_fitting_on_the_target_season_raises(self, arm):
        rows = _rows([2021, 2022, 2023])
        with pytest.raises(ValueError, match="leakage"):
            fit_arm(arm, rows, target_season=2023)

    @pytest.mark.parametrize("arm", X_ARMS)
    def test_fitting_on_a_later_season_raises(self, arm):
        rows = _rows([2021, 2024])
        with pytest.raises(ValueError, match="leakage"):
            fit_arm(arm, rows, target_season=2022)

    def test_strictly_earlier_seasons_are_accepted(self):
        params = fit_arm("X1", _rows([2021, 2022]), target_season=2023)
        assert params.training_seasons == (2021, 2022)

    def test_the_error_names_the_offending_seasons(self):
        with pytest.raises(ValueError, match=r"\[2023, 2024\]"):
            fit_arm("X1", _rows([2021, 2023, 2024]), target_season=2023)


class TestEvidencePrior:
    """An arm with thin evidence must emit zero, not a confident-looking small number."""

    @pytest.mark.parametrize("arm", ("X1", "X2", "X3", "X4"))
    def test_one_training_season_is_identity(self, arm):
        params = fit_arm(arm, _rows([2021]), target_season=2022)
        assert params.is_identity
        assert "training season" in params.fits["RB"].reason

    @pytest.mark.parametrize("arm", ("X1", "X2", "X3", "X4"))
    def test_too_few_rows_is_identity(self, arm):
        rows = _rows([2021, 2022], per_season=MIN_TRAINING_ROWS // 2 - 1)
        params = fit_arm(arm, rows, target_season=2023)
        assert params.is_identity
        assert "training rows" in params.fits["RB"].reason

    def test_the_prior_matches_the_uncertainty_model(self):
        """M6 declines to fit a thin position rather than fitting noise; so does this."""
        from alpha_squad.models.uncertainty.run import MIN_TRAIN_ROWS

        assert MIN_TRAINING_ROWS == MIN_TRAIN_ROWS

    def test_treated_seasons_follow_from_the_prior(self):
        """2021 and 2022 cannot be treated: with M6 predictions starting in 2021 they have 0
        and 1 training seasons against a minimum of 2. If this ever changes silently, the
        pre-registered 'treated subset is primary' rule would quietly mean something else."""
        treatable = [
            season
            for season in range(FIRST_RESIDUAL_SEASON, 2026)
            if season - FIRST_RESIDUAL_SEASON >= MIN_TRAINING_SEASONS
        ]
        assert tuple(treatable) == PREREGISTERED_TREATED_SEASONS


class TestControlArm:
    def test_x0_is_the_identity_on_any_evidence(self):
        params = fit_arm("X0", _rows([2021, 2022, 2023]), target_season=2024)
        assert params.is_identity
        assert PREREGISTERED_X_CONTROL == "X0"

    def test_x0_leaves_projections_untouched(self):
        params = fit_arm("X0", _rows([2021, 2022]), target_season=2023)
        projections = {"RB_1": 250.0, "WR_1": 200.0, "K_1": 130.0}
        positions = {"RB_1": "RB", "WR_1": "WR", "K_1": "K"}
        out = apply_calibration(params, projections, positions, band_edges(_target(), DEMAND))
        assert out == projections
        assert out is not projections


class TestExcludedPositions:
    @pytest.mark.parametrize("arm", X_ARMS)
    def test_k_and_dst_are_never_adjusted(self, arm):
        """D57 ships baselines for K/DST because their year-over-year signal is weak (K r=0.41,
        DST r=0.29). A bias correction on top of that fits noise."""
        assert "K" not in CALIBRATED_POSITIONS
        assert "DST" not in CALIBRATED_POSITIONS
        rows = _rows([2021, 2022], position="RB", residual=50.0)
        params = fit_arm(arm, rows, target_season=2023)
        projections = {"K_1": 130.0, "DST_1": 98.0}
        positions = {"K_1": "K", "DST_1": "DST"}
        out = apply_calibration(params, projections, positions, band_edges(_target(), DEMAND))
        assert out == projections


class TestAdditiveArm:
    def test_recovers_a_known_constant_bias(self):
        params = fit_arm("X1", _rows([2021, 2022], residual=20.0), target_season=2023)
        assert params.fits["RB"].offsets[1] == pytest.approx(20.0)

    def test_seasons_are_weighted_equally(self):
        """The variation being corrected is BETWEEN seasons, so the estimate belongs at that
        level -- a season with more qualifying players must not outweigh one with fewer."""
        rows = _rows([2021], per_season=200, residual=0.0) + _rows(
            [2022], per_season=40, residual=100.0
        )
        params = fit_arm("X1", rows, target_season=2023)
        assert params.fits["RB"].offsets[1] == pytest.approx(50.0)

    def test_positions_with_no_evidence_stay_identity(self):
        params = fit_arm("X1", _rows([2021, 2022], position="RB"), target_season=2023)
        assert not params.fits["RB"].is_identity
        assert params.fits["WR"].is_identity


class TestAffineArm:
    def test_recovers_a_known_slope(self):
        rows = []
        for season in (2021, 2022):
            for i in range(40):
                projected = 300.0 - 5 * i
                rows.append(
                    ResidualRow(
                        season=season,
                        player_id=f"QB_{season}_{i}",
                        position="QB",
                        projected=projected,
                        realized=50.0 + 0.5 * projected,
                        pos_rank=i + 1,
                        band=1,
                    )
                )
        fit = fit_arm("X2", rows, target_season=2023).fits["QB"]
        assert fit.slope == pytest.approx(0.5, abs=1e-6)
        assert fit.intercept == pytest.approx(50.0, abs=1e-6)

    def test_a_non_positive_slope_is_refused(self):
        """A negative slope would invert the position's board -- pathological, not calibrated."""
        rows = []
        for season in (2021, 2022):
            for i in range(40):
                projected = 300.0 - 5 * i
                rows.append(
                    ResidualRow(
                        season=season,
                        player_id=f"QB_{season}_{i}",
                        position="QB",
                        projected=projected,
                        realized=400.0 - projected,
                        pos_rank=i + 1,
                        band=1,
                    )
                )
        fit = fit_arm("X2", rows, target_season=2023).fits["QB"]
        assert fit.is_identity
        assert "degenerate slope" in fit.reason


class TestShrinkageArm:
    def test_no_between_season_variation_keeps_the_estimate(self):
        """Identical per-season means: nothing to shrink against, so lambda is 1."""
        rows = _rows([2021, 2022, 2023], residual=20.0)
        fit = fit_arm("X4", rows, target_season=2024).fits["RB"]
        assert fit.lam == pytest.approx(1.0)
        assert fit.offsets[1] == pytest.approx(20.0)

    def test_sign_flipping_evidence_is_shrunk_toward_zero(self):
        """The measured RB case: per-season means that swing hard have a between-season variance
        large enough that the mean's standard error swamps the signal, and the arm declines."""
        rows = (
            _rows([2021], residual=-40.0)
            + _rows([2022], residual=+60.0)
            + _rows([2023], residual=+20.0)
        )
        fit = fit_arm("X4", rows, target_season=2024).fits["RB"]
        assert abs(fit.offsets[1]) < abs(
            fit_arm("X1", rows, target_season=2024).fits["RB"].offsets[1]
        )

    def test_shrinkage_never_amplifies(self):
        rows = _rows([2021], residual=10.0) + _rows([2022], residual=30.0)
        unshrunk = fit_arm("X1", rows, target_season=2023).fits["RB"].offsets[1]
        shrunk = fit_arm("X4", rows, target_season=2023).fits["RB"].offsets[1]
        assert 0.0 <= shrunk <= unshrunk


class TestRankBands:
    def test_edges_come_from_the_league_not_a_constant(self):
        """A hardcoded edge would reintroduce exactly the format-bound constant D58 removed and
        the tuned constant D66/D67 removed."""
        target_edges = band_edges(_target(), DEMAND)
        legacy_edges = band_edges(load_league_context(LEGACY), DEMAND)
        assert target_edges != legacy_edges

    def test_band_one_is_the_leagues_dedicated_starters(self):
        league = _target()
        edges = band_edges(league, DEMAND)
        assert edges["RB"][0] == league.teams * league.dedicated_slots()["RB"]
        assert edges["QB"][0] == league.teams * league.dedicated_slots()["QB"]

    def test_band_two_ends_at_full_draft_consumption(self):
        league = _target()
        edges = band_edges(league, DEMAND)
        assert edges["RB"][1] == draftable_depth(league, DEMAND, "RB")
        assert edges["RB"][1] == round(league.teams * DEMAND["RB"])

    def test_band_membership(self):
        assert band_of(1, (20, 46)) == 1
        assert band_of(20, (20, 46)) == 1
        assert band_of(21, (20, 46)) == 2
        assert band_of(46, (20, 46)) == 2
        assert band_of(47, (20, 46)) == 3

    def test_band_three_is_never_adjusted(self):
        """Nobody drafts past the demand boundary, so adjusting there cannot change a draft and
        would only add noise to the comparison."""
        rows = _rows([2021, 2022], residual=30.0, band=1)
        params = fit_arm("X3", rows, target_season=2023)
        assert params.fits["RB"].offsets.get(3, 0.0) == 0.0

    def test_a_band_with_thin_evidence_gets_zero_independently(self):
        rows = _rows([2021, 2022], residual=30.0, band=1) + _rows(
            [2021, 2022], per_season=2, residual=99.0, band=2
        )
        fit = fit_arm("X3", rows, target_season=2023).fits["RB"]
        assert fit.offsets[1] == pytest.approx(30.0)
        assert fit.offsets[2] == 0.0


class TestApplication:
    def test_within_position_order_is_preserved_by_the_monotone_arms(self):
        """X1/X2/X4 are monotone per position, so gate G2 is satisfied by construction for them
        and only X3 can actually fail it."""
        params = fit_arm("X1", _rows([2021, 2022], residual=25.0), target_season=2023)
        projections = {f"RB_{i}": 300.0 - i for i in range(60)}
        positions = {f"RB_{i}": "RB" for i in range(60)}
        out = apply_calibration(params, projections, positions, band_edges(_target(), DEMAND))
        before = sorted(projections, key=lambda p: -projections[p])
        after = sorted(out, key=lambda p: -out[p])
        assert before == after

    def test_does_not_mutate_its_input(self):
        params = fit_arm("X1", _rows([2021, 2022], residual=25.0), target_season=2023)
        projections = {"RB_1": 250.0}
        positions = {"RB_1": "RB"}
        apply_calibration(params, projections, positions, band_edges(_target(), DEMAND))
        assert projections == {"RB_1": 250.0}

    def test_unknown_positions_pass_through(self):
        params = fit_arm("X1", _rows([2021, 2022], residual=25.0), target_season=2023)
        projections = {"P_1": 10.0}
        out = apply_calibration(params, projections, {}, band_edges(_target(), DEMAND))
        assert out == projections


class TestDeterminism:
    @pytest.mark.parametrize("arm", X_ARMS)
    def test_identical_inputs_give_identical_parameters(self, arm):
        rows = _rows([2021, 2022, 2023], residual=13.5)
        a = fit_arm(arm, rows, target_season=2024)
        b = fit_arm(arm, list(reversed(rows)), target_season=2024)
        assert {p: f.offsets for p, f in a.fits.items()} == {
            p: f.offsets for p, f in b.fits.items()
        }
        assert {p: (f.slope, f.intercept) for p, f in a.fits.items()} == {
            p: (f.slope, f.intercept) for p, f in b.fits.items()
        }


class TestPreRegistrationIsIntact:
    def test_there_are_exactly_five_arms(self):
        """Adding a sixth arm after seeing results is a protocol violation, not a fix."""
        assert X_ARMS == ("X0", "X1", "X2", "X3", "X4")

    def test_an_unknown_arm_is_refused(self):
        with pytest.raises(ValueError, match="unknown calibration arm"):
            fit_arm("X5", _rows([2021, 2022]), target_season=2023)


class TestHarnessIdentity:
    """X0 must be the shipped W1 engine, not a reconstruction of it."""

    def test_an_identity_arm_returns_the_control_object_itself(self):
        """`_calibrated_static` returns the control `SeasonStatic` unchanged when the arm is the
        identity, rather than rebuilding an equal one. That is what makes 'X0 scored the same as
        W1' mean byte-identical rather than equal-up-to-floating-point-reconstruction, so a zero
        in the results table says exactly what it looks like it says."""
        from alpha_squad.evaluation.draft_forensics import _calibrated_static

        sentinel = object()
        result = _calibrated_static(
            con=None,
            league=_target(),
            season=2023,
            arm="X0",
            residual_rows=_rows([2021, 2022]),
            control=sentinel,
        )
        assert result is sentinel

    def test_an_arm_zeroed_by_the_evidence_prior_also_returns_the_control(self):
        from alpha_squad.evaluation.draft_forensics import _calibrated_static

        sentinel = object()
        result = _calibrated_static(
            con=None,
            league=_target(),
            season=2022,
            arm="X1",
            residual_rows=_rows([2021]),
            control=sentinel,
        )
        assert result is sentinel
