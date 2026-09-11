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

#: D90 additionally varies `formats` -- that IS its experiment (cross-format generalisation).
#: It is listed separately rather than folded into SAMPLE_SIZE_FIELDS so the power lineage keeps
#: its strict guarantee and D90's one extra degree of freedom stays visible.
D90_EXTRA_FIELD = "formats"

#: The POWER lineage. These three must differ only in sample size.
DESIGNS = (rd.D87_SHORTLIST, rd.D88_TEN_SLOTS, rd.D89_SIX_SEASONS)

#: Every design, including the cross-format phase.
ALL_DESIGNS = (*DESIGNS, rd.D90_THIRD_FORMAT)


class TestOnlySampleSizeVaries:
    def test_every_non_sample_field_is_identical_across_the_lineage(self) -> None:
        for f in dataclasses.fields(rd.ReplicationDesign):
            if f.name in SAMPLE_SIZE_FIELDS:
                continue
            values = {getattr(d, f.name) for d in DESIGNS}
            assert len(values) == 1, f"{f.name} differs across replications: {values}"

    def test_d90_varies_the_format_and_nothing_else_beyond_sample_size(self) -> None:
        """The whole claim of D90 is that only the league changed. Pin it."""
        for f in dataclasses.fields(rd.ReplicationDesign):
            if f.name in SAMPLE_SIZE_FIELDS or f.name == D90_EXTRA_FIELD:
                continue
            values = {getattr(d, f.name) for d in ALL_DESIGNS}
            assert len(values) == 1, f"{f.name} differs once D90 is included: {values}"

    def test_d90_differs_from_d89_in_exactly_phase_and_formats(self) -> None:
        a, b = rd.D89_SIX_SEASONS, rd.D90_THIRD_FORMAT
        differing = {
            f.name
            for f in dataclasses.fields(rd.ReplicationDesign)
            if getattr(a, f.name) != getattr(b, f.name)
        }
        assert differing == {"phase", "formats"}

    def test_d90_reuses_d89s_seasons_and_slots_unchanged(self) -> None:
        assert rd.D90_THIRD_FORMAT.seasons == rd.D89_SIX_SEASONS.seasons
        assert rd.D90_THIRD_FORMAT.slots == rd.D89_SIX_SEASONS.slots
        assert rd.D90_THIRD_FORMAT.shortlist_k is None

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

    def test_the_active_design_is_d90_and_is_full_board(self) -> None:
        assert rd.ACTIVE_DESIGN is rd.D90_THIRD_FORMAT
        assert rd.ACTIVE_DESIGN.shortlist_k is None

    def test_no_design_in_the_lineage_ever_carries_a_shortlist_except_d87(self) -> None:
        shortlisted = [d.phase for d in ALL_DESIGNS if d.shortlist_k is not None]
        assert shortlisted == ["D87"]


class TestGatesAreImportedNotRestated:
    def test_module_does_not_define_its_own_thresholds(self) -> None:
        # re-exported, not redefined: identity with objective_candidates' values
        assert rd.MIN_STARTER_POINT_GAIN is MIN_STARTER_POINT_GAIN
        assert rd.MAX_WORSE_SEASONS is MAX_WORSE_SEASONS
        assert rd.MAX_SEASON_LONG_REGRESSION is MAX_SEASON_LONG_REGRESSION

    def test_control_treatment_and_metrics_are_d86s_in_every_design(self) -> None:
        for d in ALL_DESIGNS:
            assert d.control == PREREGISTERED_CONTROL == "O0"
            assert d.treatment == "O1"
            assert d.primary_metric == PRIMARY_METRIC == "weekly_no_foresight"
            assert d.metrics == METRICS

    def test_the_power_lineage_keeps_d86s_formats_and_only_d90_departs(self) -> None:
        for d in DESIGNS:
            assert d.formats == PREREGISTERED_FORMATS
        assert rd.D90_THIRD_FORMAT.formats == ("dynasty_1qb",)

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
    def test_2019_is_excluded_in_every_known_format_with_a_measured_reason(self) -> None:
        for fmt in rd.KNOWN_FORMATS:
            assert (fmt, 2019) in rd.EXCLUDED_SEASONS, f"{fmt} 2019 has no recorded reason"
        assert "0% market-rank coverage" in rd.EXCLUDED_SEASONS[(TARGET, 2019)]
        assert 2019 not in rd.D89_SIX_SEASONS.seasons
        assert 2019 not in rd.D90_THIRD_FORMAT.seasons

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
            assert fmt in rd.KNOWN_FORMATS

    def test_dynasty_1qb_keeps_2020_because_its_board_exists(self) -> None:
        """The mirror of the legacy 2020 exclusion: same page_type relabelling, opposite outcome.
        `do` DOES publish a 2020 preseason board (under `dynasty-offense`), so the cell stays."""
        assert ("dynasty_1qb", 2020) not in rd.EXCLUDED_SEASONS
        assert 2020 in rd.D90_THIRD_FORMAT.seasons_for("dynasty_1qb")
        assert "dynasty-offense" in rd.EXCLUDED_SEASONS[("dynasty_1qb", 2019)]

    def test_predictions_are_recorded_and_include_both_directions(self) -> None:
        assert set(rd.PREDICTIONS) == {"R1", "R2", "R3", "R4", "R5", "R6"}
        # R2 must register the failure mode as well as the success mode
        assert "does NOT fall" in rd.PREDICTIONS["R2"]
        assert "outlier" in rd.PREDICTIONS["R2"]

    def test_the_frozen_design_cannot_be_edited_after_the_fact(self) -> None:
        with pytest.raises(dataclasses.FrozenInstanceError):
            rd.D89_SIX_SEASONS.seasons = (2020,)  # type: ignore[misc]


class TestD90ThirdFormat:
    """D90's format selection must be forced by data, not by preference."""

    def test_the_selected_format_is_the_dynasty_1qb_league(self) -> None:
        assert rd.D90_THIRD_FORMAT.formats == ("dynasty_1qb",)
        assert rd.ACTIVE_DESIGN is rd.D90_THIRD_FORMAT

    def test_the_selected_format_has_both_a_kicker_and_a_defense_slot(self) -> None:
        """Criterion 2. Note `DEF` normalises to `DST` via SLOT_POSITION_ALIASES -- checking for
        the literal key 'DEF' in dedicated_slots() is the trap CLAUDE.md warns about."""
        from alpha_squad.league.context import _LEAGUE_CONFIGS_DIR, load_league_context

        league = load_league_context(_LEAGUE_CONFIGS_DIR / "dynasty_1qb.yaml")
        dedicated = league.dedicated_slots()
        assert dedicated.get("K") == 1
        assert dedicated.get("DST") == 1, f"DEF must normalise to DST; got {dedicated}"

    def test_it_resolves_to_the_one_unused_series_that_carries_k_and_dst(self) -> None:
        from alpha_squad.league.context import _LEAGUE_CONFIGS_DIR, load_league_context
        from alpha_squad.market.series import DYNASTY_1QB, resolve_market_series

        league = load_league_context(_LEAGUE_CONFIGS_DIR / "dynasty_1qb.yaml")
        assert resolve_market_series(league) == DYNASTY_1QB

    def test_it_is_distinct_from_both_existing_formats_on_the_board(self) -> None:
        from alpha_squad.league.context import _LEAGUE_CONFIGS_DIR, load_league_context
        from alpha_squad.market.series import resolve_market_series

        series = {
            name: resolve_market_series(load_league_context(_LEAGUE_CONFIGS_DIR / f"{name}.yaml"))
            for name in ("target_league", "legacy_2qb_dynasty", "dynasty_1qb")
        }
        assert len(set(series.values())) == 3, f"boards must all differ: {series}"

    def test_its_lineup_is_identical_to_the_target_formats(self) -> None:
        """Criterion 3, and the reason D90 has almost no design discretion: exactly one field
        differs from target_league. This also bounds the conclusion -- see prediction T6."""
        from alpha_squad.league.context import _LEAGUE_CONFIGS_DIR, load_league_context

        target = load_league_context(_LEAGUE_CONFIGS_DIR / "target_league.yaml")
        third = load_league_context(_LEAGUE_CONFIGS_DIR / "dynasty_1qb.yaml")
        assert third.lineup == target.lineup
        assert third.teams == target.teams
        assert third.roster == target.roster
        assert third.scoring == target.scoring
        assert third.format != target.format

    def test_roster_arithmetic_holds(self) -> None:
        from alpha_squad.league.context import _LEAGUE_CONFIGS_DIR, load_league_context

        league = load_league_context(_LEAGUE_CONFIGS_DIR / "dynasty_1qb.yaml")
        starters = sum(league.lineup.values())
        assert starters + int(league.roster["bench"]) == int(league.roster["roster_size"]) == 16

    def test_it_runs_six_clusters_like_the_target_format(self) -> None:
        assert rd.D90_THIRD_FORMAT.clusters("dynasty_1qb") == 6
        assert rd.D90_THIRD_FORMAT.paired_observations("dynasty_1qb") == 60
        assert rd.D90_THIRD_FORMAT.drafts() == 120

    def test_predictions_record_the_mechanism_test_and_its_failure_mode(self) -> None:
        assert set(rd.D90_PREDICTIONS) == {"T1", "T2", "T3", "T4", "T5", "T6"}
        # T2 must state what a NEGATIVE result would mean, not only a positive one
        assert "genuine cross-format weakness" in rd.D90_PREDICTIONS["T2"]
        # T3 must refuse to pre-commit to a magnitude
        assert "no specific magnitude is predicted" in rd.D90_PREDICTIONS["T3"]
        # T5 must forbid redefining G7 by arithmetic
        assert "NOT REDEFINED" in rd.D90_PREDICTIONS["T5"]
        # T6 must record the board-vs-lineup scope limit
        assert "does NOT vary the" in rd.D90_PREDICTIONS["T6"]
