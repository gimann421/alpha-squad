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


TARGET = "target_league"
LEGACY = "legacy_2qb_dynasty"


class TestSampleSizeArithmetic:
    @pytest.mark.parametrize(
        ("design", "fmt", "obs", "clusters"),
        [
            (rd.D87_SHORTLIST, TARGET, 20, 5),
            (rd.D87_SHORTLIST, LEGACY, 20, 5),
            (rd.D88_TEN_SLOTS, TARGET, 50, 5),
            (rd.D88_TEN_SLOTS, LEGACY, 50, 5),
            (rd.D89_SIX_SEASONS, TARGET, 60, 6),
            # legacy has no 2020 preseason board, so it stays at five clusters
            (rd.D89_SIX_SEASONS, LEGACY, 50, 5),
        ],
    )
    def test_counts(self, design: rd.ReplicationDesign, fmt: str, obs: int, clusters: int) -> None:
        assert design.paired_observations(fmt) == obs
        assert design.clusters(fmt) == clusters

    @pytest.mark.parametrize(
        ("design", "drafts"),
        [(rd.D87_SHORTLIST, 80), (rd.D88_TEN_SLOTS, 200), (rd.D89_SIX_SEASONS, 220)],
    )
    def test_total_drafts(self, design: rd.ReplicationDesign, drafts: int) -> None:
        assert design.drafts() == drafts

    def test_d89_adds_a_cluster_in_the_target_format_only(self) -> None:
        assert rd.D89_SIX_SEASONS.clusters(TARGET) == rd.D88_TEN_SLOTS.clusters(TARGET) + 1
        assert rd.D89_SIX_SEASONS.clusters(LEGACY) == rd.D88_TEN_SLOTS.clusters(LEGACY)

    def test_earlier_designs_are_unaffected_by_the_2020_exclusion(self) -> None:
        # D87/D88 never ran 2020, so a per-format exclusion of it must change nothing for them
        for design in (rd.D87_SHORTLIST, rd.D88_TEN_SLOTS):
            for fmt in design.formats:
                assert design.seasons_for(fmt) == design.seasons


class TestExclusionsAndPredictions:
    def test_2019_is_excluded_in_both_formats_with_a_measured_reason(self) -> None:
        for fmt in rd.ACTIVE_DESIGN.formats:
            assert (fmt, 2019) in rd.EXCLUDED_SEASONS
        assert "0% market-rank coverage" in rd.EXCLUDED_SEASONS[(TARGET, 2019)]
        assert 2019 not in rd.D89_SIX_SEASONS.seasons

    def test_legacy_2020_is_excluded_because_no_preseason_board_exists(self) -> None:
        reason = rd.EXCLUDED_SEASONS[(LEGACY, 2020)]
        assert "NO PRESEASON BOARD EXISTS" in reason
        assert "2020-10-16" in reason
        assert 2020 not in rd.D89_SIX_SEASONS.seasons_for(LEGACY)

    def test_target_2020_is_NOT_excluded(self) -> None:
        assert (TARGET, 2020) not in rd.EXCLUDED_SEASONS
        assert 2020 in rd.D89_SIX_SEASONS.seasons_for(TARGET)

    def test_exclusion_is_per_format_not_global(self) -> None:
        # the whole point: the same season is usable in one format and not the other
        assert 2020 in rd.D89_SIX_SEASONS.seasons_for(TARGET)
        assert 2020 not in rd.D89_SIX_SEASONS.seasons_for(LEGACY)

    def test_no_excluded_cell_survives_into_the_active_design(self) -> None:
        for fmt in rd.ACTIVE_DESIGN.formats:
            for season in rd.ACTIVE_DESIGN.seasons_for(fmt):
                assert (fmt, season) not in rd.EXCLUDED_SEASONS

    def test_every_exclusion_names_a_real_format(self) -> None:
        for fmt, _season in rd.EXCLUDED_SEASONS:
            assert fmt in rd.ACTIVE_DESIGN.formats

    def test_predictions_are_recorded_and_include_both_directions(self) -> None:
        assert set(rd.PREDICTIONS) == {"R1", "R2", "R3", "R4", "R5", "R6"}
        # R2 must register the failure mode as well as the success mode
        assert "does NOT fall" in rd.PREDICTIONS["R2"]
        assert "outlier" in rd.PREDICTIONS["R2"]

    def test_the_frozen_design_cannot_be_edited_after_the_fact(self) -> None:
        with pytest.raises(dataclasses.FrozenInstanceError):
            rd.D89_SIX_SEASONS.seasons = (2020,)  # type: ignore[misc]
