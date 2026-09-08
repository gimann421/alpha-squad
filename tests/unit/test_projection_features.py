"""Regression tests for the D82 feature-addition pre-registration.

These lock the PROTOCOL, not any result: the arms, the blocks, the tiers, the gate thresholds,
the leakage assertion, and the property that the estimator is identical across arms. If a later
session quietly relaxes a gate or adds an arm after seeing results, these fail.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from alpha_squad.evaluation.projection_features import (
    AGE_BLOCK,
    F_ARM_BLOCKS,
    F_ARMS,
    MAX_ECR_SPEARMAN_GAIN,
    MAX_SPEARMAN_DROP,
    MIN_POOLED_GAIN,
    PREREGISTERED_ALPHA,
    PREREGISTERED_CONTROL,
    PREREGISTERED_MIN_BETTER_SEASONS,
    PREREGISTERED_OVERALL_TIERS,
    PREREGISTERED_TARGET_SEASONS,
    PREREGISTERED_TIERS,
    SHIPPED_ROW_SPECIFICATION,
    TOLERANCE,
    USAGE_BLOCK,
    VOLUME_BLOCK,
    TierRow,
    _assert_feature_leakage_free,
    _new_model,
    evaluate_gates,
    features_for,
    load_extended_features,
)
from alpha_squad.models.established.season_level import FEATURES

# ---------------------------------------------------------------------------------------------
# The pre-registration itself
# ---------------------------------------------------------------------------------------------


def test_arms_are_exactly_the_preregistered_five() -> None:
    assert F_ARMS == ("F0", "F1", "F2", "F3", "F4")
    assert PREREGISTERED_CONTROL == "F0"
    assert set(F_ARM_BLOCKS) == set(F_ARMS)


def test_control_arm_is_the_shipped_feature_set() -> None:
    """F0 must be Y1 exactly -- if the control drifts, every delta is meaningless."""
    assert F_ARM_BLOCKS["F0"] == ()
    assert features_for("F0") == list(FEATURES)


def test_every_arm_is_a_superset_of_the_shipped_features() -> None:
    """No arm may REMOVE a feature: this phase tests added information only."""
    for arm in F_ARMS:
        assert features_for(arm)[: len(FEATURES)] == list(FEATURES)


def test_f4_is_the_union_of_the_three_blocks_with_no_duplicates() -> None:
    assert F_ARM_BLOCKS["F4"] == AGE_BLOCK + VOLUME_BLOCK + USAGE_BLOCK
    assert len(set(features_for("F4"))) == len(features_for("F4"))


def test_blocks_are_disjoint() -> None:
    """F1-F3 exist to attribute a gain to one block; overlapping blocks would break that."""
    assert not (set(AGE_BLOCK) & set(VOLUME_BLOCK))
    assert not (set(AGE_BLOCK) & set(USAGE_BLOCK))
    assert not (set(VOLUME_BLOCK) & set(USAGE_BLOCK))
    assert not (set(FEATURES) & set(AGE_BLOCK + VOLUME_BLOCK + USAGE_BLOCK))


def test_unknown_arm_raises() -> None:
    with pytest.raises(ValueError):
        features_for("F9")


def test_row_specification_is_the_shipped_one() -> None:
    """Row selection must not vary with the feature set, or the arms differ in two ways."""
    assert SHIPPED_ROW_SPECIFICATION == "Y1"


def test_evaluation_window_matches_the_earlier_phases() -> None:
    assert PREREGISTERED_TARGET_SEASONS == (2022, 2023, 2024, 2025)


def test_gate_thresholds_are_pinned() -> None:
    assert TOLERANCE == 1.0
    assert MIN_POOLED_GAIN == 0.5
    assert MAX_SPEARMAN_DROP == 0.01
    assert MAX_ECR_SPEARMAN_GAIN == 0.05
    assert PREREGISTERED_ALPHA == 0.05
    assert PREREGISTERED_MIN_BETTER_SEASONS == 3


def test_tiers_cover_the_elite_head_and_the_body_for_every_position() -> None:
    """The whole point of tier preservation: a head tier AND a body tier, per position."""
    for position, tiers in PREREGISTERED_TIERS.items():
        labels = {label for label, _, _ in tiers}
        assert {"top5", "top10", "11_24", "all"} <= labels, position
    assert "61_100" in {label for label, _, _ in PREREGISTERED_TIERS["RB"]}
    assert "all" in {label for label, _, _ in PREREGISTERED_OVERALL_TIERS}


def test_tier_bounds_are_half_open_and_ordered() -> None:
    for position, tiers in PREREGISTERED_TIERS.items():
        for label, lo, hi in tiers:
            assert 1 <= lo < hi, (position, label)


def test_estimator_is_byte_identical_to_production() -> None:
    """The only thing that varies between arms is the columns. Pin the hyperparameters so a
    later edit cannot turn this into an estimator experiment by accident."""
    params = _new_model().get_params()
    assert params["iterations"] == 150
    assert params["depth"] == 3
    assert params["learning_rate"] == 0.08
    assert params["loss_function"] == "MAE"
    assert params["random_seed"] == 42
    assert "monotone_constraints" not in params


# ---------------------------------------------------------------------------------------------
# Leakage
# ---------------------------------------------------------------------------------------------


def _leak_con(rows: list[tuple[str, int, float]]):
    import duckdb

    con = duckdb.connect(":memory:")
    con.execute(
        "CREATE TABLE player_season_stats (player_id VARCHAR, season INTEGER, total_carries DOUBLE)"
    )
    if rows:
        con.executemany("INSERT INTO player_season_stats VALUES (?, ?, ?)", rows)
    return con


def test_leakage_assertion_raises_when_a_feature_comes_from_the_target_season() -> None:
    """The failure this guards against: joining S instead of S-1. It must RAISE, not warn."""
    con = _leak_con([("p1", 2021, 100.0), ("p1", 2022, 250.0)])
    leaked = pd.DataFrame([{"player_id": "p1", "target_season": 2022, "prior_carries": 250.0}])
    with pytest.raises(ValueError, match="leakage or misjoin"):
        _assert_feature_leakage_free(con, leaked, "RB")


def test_leakage_assertion_accepts_a_correct_prior_season_join() -> None:
    con = _leak_con([("p1", 2021, 100.0), ("p1", 2022, 250.0)])
    ok = pd.DataFrame([{"player_id": "p1", "target_season": 2022, "prior_carries": 100.0}])
    _assert_feature_leakage_free(con, ok, "RB")


def test_leakage_assertion_is_a_noop_on_an_empty_frame() -> None:
    _assert_feature_leakage_free(_leak_con([]), pd.DataFrame(), "RB")


def test_load_extended_features_returns_empty_when_the_base_is_empty(monkeypatch) -> None:
    """An empty base frame must short-circuit before the join, not raise on missing tables."""
    import duckdb

    import alpha_squad.evaluation.projection_features as mod

    monkeypatch.setattr(mod, "load_season_level_data", lambda *a, **k: pd.DataFrame())
    assert load_extended_features(duckdb.connect(":memory:"), "RB", 2015, 2025).empty


# ---------------------------------------------------------------------------------------------
# Gate arithmetic -- synthetic, so each gate is exercised in isolation
# ---------------------------------------------------------------------------------------------

_POSITIONS = ("QB", "RB", "WR", "TE")


def _tiers(control_mae: float, arm_mae: dict[tuple[str, str], float]) -> pd.DataFrame:
    rows: list[TierRow] = []
    for season in PREREGISTERED_TARGET_SEASONS:
        for position in _POSITIONS:
            for label, _, _ in PREREGISTERED_TIERS[position]:
                rows.append(TierRow("F0", season, position, label, 10, control_mae, 0.0, 0.0))
                rows.append(
                    TierRow(
                        "F1",
                        season,
                        position,
                        label,
                        10,
                        arm_mae.get((position, label), control_mae - 2.0),
                        0.0,
                        0.0,
                    )
                )
    return pd.DataFrame([r.__dict__ for r in rows])


def _extras(
    arm_pool: dict[str, float] | None = None,
    control_pool: float = 50.0,
    arm_spearman: float = 0.80,
    control_spearman: float = 0.80,
    arm_ecr: float = 0.70,
    control_ecr: float = 0.70,
) -> pd.DataFrame:
    arm_pool = arm_pool or {p: control_pool - 2.0 for p in _POSITIONS}
    rows = []
    for season in PREREGISTERED_TARGET_SEASONS:
        for arm, pool, sp, ecr in (
            ("F0", {p: control_pool for p in _POSITIONS}, control_spearman, control_ecr),
            ("F1", arm_pool, arm_spearman, arm_ecr),
        ):
            row = {
                "arm": arm,
                "season": season,
                "pool_mae_ALL": float(np.mean(list(pool.values()))),
            }
            for position in _POSITIONS:
                row[f"pool_mae_{position}"] = pool[position]
                row[f"spearman_{position}"] = sp
                row[f"ecr_spearman_{position}"] = ecr
            rows.append(row)
    return pd.DataFrame(rows)


def _gate(verdict, name: str):
    return next(g for g in verdict.gates if g.name.startswith(name))


def test_control_arm_has_no_gates_and_is_not_selectable() -> None:
    v = evaluate_gates(_tiers(50.0, {}), _extras(), "F0")
    assert v.gates == []
    assert v.passed is False


def test_a_uniformly_better_arm_passes_every_gate() -> None:
    v = evaluate_gates(_tiers(50.0, {}), _extras(), "F1")
    assert v.passed, [(g.name, g.detail) for g in v.gates if not g.passed]


def test_p2_rejects_buying_the_rb_head_with_the_rb_body() -> None:
    """The gate that matters most: an arm that trades one tier for another must fail even
    though its pooled mean improves."""
    v = evaluate_gates(
        _tiers(50.0, {("RB", "top10"): 30.0, ("RB", "25_60"): 60.0}), _extras(), "F1"
    )
    assert not _gate(v, "P2").passed
    assert "RB/25_60" in _gate(v, "P2").detail


def test_p2_tolerates_a_change_inside_tolerance() -> None:
    v = evaluate_gates(_tiers(50.0, {("RB", "25_60"): 50.0 + TOLERANCE - 0.01}), _extras(), "F1")
    assert _gate(v, "P2").passed


def test_p3_rejects_a_damaged_position() -> None:
    pool = {p: 48.0 for p in _POSITIONS}
    pool["WR"] = 55.0
    v = evaluate_gates(_tiers(50.0, {}), _extras(arm_pool=pool), "F1")
    assert not _gate(v, "P3").passed


def test_p4_rejects_making_the_known_rb_defect_worse() -> None:
    v = evaluate_gates(_tiers(50.0, {("RB", "top10"): 60.0}), _extras(), "F1")
    assert not _gate(v, "P4").passed


def test_p5_rejects_damaging_te_the_control_position() -> None:
    pool = {p: 48.0 for p in _POSITIONS}
    pool["TE"] = 52.0
    v = evaluate_gates(_tiers(50.0, {}), _extras(arm_pool=pool), "F1")
    assert not _gate(v, "P5").passed


def test_p6_rejects_an_improvement_carried_by_one_season() -> None:
    extras = _extras()
    for season in PREREGISTERED_TARGET_SEASONS[1:]:
        mask = (extras.arm == "F1") & (extras.season == season)
        extras.loc[mask, "pool_mae_ALL"] = 51.0
    mask = (extras.arm == "F1") & (extras.season == PREREGISTERED_TARGET_SEASONS[0])
    extras.loc[mask, "pool_mae_ALL"] = 10.0
    v = evaluate_gates(_tiers(50.0, {}), extras, "F1")
    assert not _gate(v, "P6").passed
    assert not _gate(v, "P7").passed


def test_p8_rejects_a_damaged_ordering() -> None:
    v = evaluate_gates(_tiers(50.0, {}), _extras(arm_spearman=0.50), "F1")
    assert not _gate(v, "P8").passed


def test_p9_rejects_an_arm_that_wins_by_copying_the_consensus() -> None:
    v = evaluate_gates(_tiers(50.0, {}), _extras(arm_ecr=0.70 + MAX_ECR_SPEARMAN_GAIN + 0.01), "F1")
    assert not _gate(v, "P9").passed


def test_p1_rejects_a_trivial_improvement_even_when_perfectly_significant() -> None:
    """The effect-size floor. These synthetic deltas have zero variance, so the paired t-test
    reports p=0 -- and P1 must STILL reject, because a reliably-detected 0.001-point gain is not
    a reason to change the production model."""
    tiers = _tiers(50.0, {(p, "all"): 49.999 for p in _POSITIONS})
    v = evaluate_gates(tiers, _extras(), "F1")
    assert not _gate(v, "P1").passed


def test_p1_accepts_a_gain_at_the_registered_floor() -> None:
    tiers = _tiers(50.0, {(p, "all"): 50.0 - MIN_POOLED_GAIN for p in _POSITIONS})
    assert _gate(evaluate_gates(tiers, _extras(), "F1"), "P1").passed


def test_p1_rejects_a_worse_arm_even_when_significant() -> None:
    tiers = _tiers(50.0, {(p, "all"): 60.0 for p in _POSITIONS})
    v = evaluate_gates(tiers, _extras(), "F1")
    assert not _gate(v, "P1").passed
