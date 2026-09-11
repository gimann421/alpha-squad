"""The replication designs are only replications if nothing but sample size differs (D87-D89)."""

from __future__ import annotations

import dataclasses

import pytest

from alpha_squad.evaluation import replication_design as rd
from alpha_squad.evaluation.objective_candidates import (
    MAX_SEASON_LONG_REGRESSION,
    MAX_WORSE_SEASONS,
    METRICS,
    MIN_STARTER_POINT_GAIN,
    PREREGISTERED_CONTROL,
    PREREGISTERED_FORMATS,
    PRIMARY_METRIC,
)

#: The fields a replication is allowed to change. Everything else must be constant across the
#: lineage, which is what makes D88 -> D89 a power experiment rather than a new experiment.
SAMPLE_SIZE_FIELDS = frozenset({"phase", "seasons", "slots", "shortlist_k"})

DESIGNS = (rd.D87_SHORTLIST, rd.D88_TEN_SLOTS, rd.D89_SIX_SEASONS)


class TestOnlySampleSizeVaries:
    def test_every_non_sample_field_is_identical_across_the_lineage(self) -> None:
        for f in dataclasses.fields(rd.ReplicationDesign):
            if f.name in SAMPLE_SIZE_FIELDS:
                continue
            values = {getattr(d, f.name) for d in DESIGNS}
            assert len(values) == 1, f"{f.name} differs across replications: {values}"

    def test_d89_differs_from_d88_in_the_seasons_and_nothing_else(self) -> None:
        a, b = rd.D88_TEN_SLOTS, rd.D89_SIX_SEASONS
        differing = {
            f.name
            for f in dataclasses.fields(rd.ReplicationDesign)
            if getattr(a, f.name) != getattr(b, f.name)
        }
        assert differing == {"phase", "seasons"}

    def test_d89_seasons_are_d88s_plus_2020_only(self) -> None:
        assert set(rd.D89_SIX_SEASONS.seasons) - set(rd.D88_TEN_SLOTS.seasons) == {2020}
        assert set(rd.D88_TEN_SLOTS.seasons) - set(rd.D89_SIX_SEASONS.seasons) == set()
        assert rd.D89_SIX_SEASONS.seasons == tuple(sorted(rd.D89_SIX_SEASONS.seasons))

    def test_d89_slots_are_d88s_exactly(self) -> None:
        assert rd.D89_SIX_SEASONS.slots == rd.D88_TEN_SLOTS.slots


class TestNoShortlistInAPowerPhase:
    def test_d88_and_d89_score_the_full_board(self) -> None:
        assert rd.D88_TEN_SLOTS.shortlist_k is None
        assert rd.D89_SIX_SEASONS.shortlist_k is None

    def test_d87_is_recorded_as_the_one_approximation(self) -> None:
        assert rd.D87_SHORTLIST.shortlist_k == 10

    def test_the_active_design_is_d89_and_is_full_board(self) -> None:
        assert rd.ACTIVE_DESIGN is rd.D89_SIX_SEASONS
        assert rd.ACTIVE_DESIGN.shortlist_k is None


class TestGatesAreImportedNotRestated:
    def test_module_does_not_define_its_own_thresholds(self) -> None:
        # re-exported, not redefined: identity with objective_candidates' values
        assert rd.MIN_STARTER_POINT_GAIN is MIN_STARTER_POINT_GAIN
        assert rd.MAX_WORSE_SEASONS is MAX_WORSE_SEASONS
        assert rd.MAX_SEASON_LONG_REGRESSION is MAX_SEASON_LONG_REGRESSION

    def test_control_treatment_metrics_and_formats_are_d86s(self) -> None:
        d = rd.ACTIVE_DESIGN
        assert d.control == PREREGISTERED_CONTROL == "O0"
        assert d.treatment == "O1"
        assert d.primary_metric == PRIMARY_METRIC == "weekly_no_foresight"
        assert d.metrics == METRICS
        assert d.formats == PREREGISTERED_FORMATS

    def test_no_new_gate_constants_leak_in(self) -> None:
        numeric = {
            k
            for k, v in vars(rd).items()
            if isinstance(v, (int, float)) and not isinstance(v, bool) and not k.startswith("_")
        }
        assert numeric <= {
            "MIN_STARTER_POINT_GAIN",
            "MAX_WORSE_SEASONS",
            "MAX_SEASON_LONG_REGRESSION",
        }, f"unexpected numeric constant(s) in a replication design: {numeric}"


class TestSampleSizeArithmetic:
    @pytest.mark.parametrize(
        ("design", "obs", "clusters", "drafts"),
        [
            (rd.D87_SHORTLIST, 20, 5, 80),
            (rd.D88_TEN_SLOTS, 50, 5, 200),
            (rd.D89_SIX_SEASONS, 60, 6, 240),
        ],
    )
    def test_counts(
        self, design: rd.ReplicationDesign, obs: int, clusters: int, drafts: int
    ) -> None:
        assert design.paired_observations == obs
        assert design.clusters == clusters
        assert design.drafts == drafts

    def test_d89_adds_exactly_one_cluster_and_20_percent_more_observations(self) -> None:
        assert rd.D89_SIX_SEASONS.clusters == rd.D88_TEN_SLOTS.clusters + 1
        assert rd.D89_SIX_SEASONS.paired_observations == rd.D88_TEN_SLOTS.paired_observations + 10


class TestExclusionsAndPredictions:
    def test_2019_is_excluded_with_a_measured_reason(self) -> None:
        assert 2019 in rd.EXCLUDED_SEASONS
        assert "0% market-rank coverage" in rd.EXCLUDED_SEASONS[2019]
        assert 2019 not in rd.D89_SIX_SEASONS.seasons

    def test_no_excluded_season_is_also_in_the_active_design(self) -> None:
        assert not set(rd.EXCLUDED_SEASONS) & set(rd.ACTIVE_DESIGN.seasons)

    def test_predictions_are_recorded_and_include_both_directions(self) -> None:
        assert set(rd.PREDICTIONS) == {"R1", "R2", "R3", "R4", "R5", "R6"}
        # R2 must register the failure mode as well as the success mode
        assert "does NOT fall" in rd.PREDICTIONS["R2"]
        assert "outlier" in rd.PREDICTIONS["R2"]

    def test_the_frozen_design_cannot_be_edited_after_the_fact(self) -> None:
        with pytest.raises(dataclasses.FrozenInstanceError):
            rd.D89_SIX_SEASONS.seasons = (2020,)  # type: ignore[misc]
