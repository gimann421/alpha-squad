"""Configurable fantasy scoring computed from raw stat lines.

The repository has no scoring engine of its own: it trusts nflverse's precomputed
``fantasy_points`` / ``fantasy_points_ppr`` columns (``features/player.py``), which hard-code one
scoring system. A ROS trade model has to answer "what is this QB worth in *my* league", so the
scoring rules must be an input. ``ScoringRules.nflverse_standard()`` reproduces nflverse's columns
exactly (asserted by ``tests/unit/test_ros_scoring.py`` and, against real data when present, by
``tests/integration/test_ros_panel.py``), so the default path is numerically identical to what the
rest of the repo already uses.

League-config keys understood by ``ScoringRules.from_league`` (all optional; absent keys fall back
to the nflverse defaults rather than to a guess):

``ppr`` / ``ppr_value``, ``half_ppr``, ``pass_td``, ``pass_yd``, ``pass_int``, ``pass_300_bonus``,
``pass_400_bonus``, ``pass_cmp``, ``pass_inc``, ``pass_att``, ``rush_yd``, ``rush_td``,
``rush_300_bonus`` (unused), ``rec_yd``, ``rec_td``, ``fumble_lost``, ``two_pt``, ``sack_taken``,
``te_premium``.
"""

from __future__ import annotations

from dataclasses import dataclass, fields

import pandas as pd

# nflverse stat columns each rule reads; missing columns are treated as 0 (documented, tested).
_FUMBLE_LOST_COLS = ("sack_fumbles_lost", "rushing_fumbles_lost", "receiving_fumbles_lost")
_TWO_PT_COLS = ("passing_2pt_conversions", "rushing_2pt_conversions", "receiving_2pt_conversions")


@dataclass(frozen=True)
class ScoringRules:
    pass_yd: float = 0.04
    pass_td: float = 4.0
    pass_int: float = -2.0
    pass_cmp: float = 0.0
    pass_inc: float = 0.0  # applied to (attempts - completions)
    pass_att: float = 0.0
    pass_300_bonus: float = 0.0  # awarded once for a >=300 yard passing game
    pass_400_bonus: float = 0.0
    sack_taken: float = 0.0
    rush_yd: float = 0.1
    rush_td: float = 6.0
    rec: float = 0.0  # points per reception: 0 standard, 0.5 half, 1.0 PPR
    rec_yd: float = 0.1
    rec_td: float = 6.0
    fumble_lost: float = -2.0
    two_pt: float = 2.0
    special_teams_td: float = 6.0
    te_premium: float = 0.0  # extra points per reception for TEs

    @classmethod
    def nflverse_standard(cls) -> ScoringRules:
        """Reproduces nflverse ``fantasy_points`` (no PPR)."""
        return cls()

    @classmethod
    def nflverse_ppr(cls) -> ScoringRules:
        """Reproduces nflverse ``fantasy_points_ppr``."""
        return cls(rec=1.0)

    @classmethod
    def from_league(cls, league) -> ScoringRules:
        """Scoring implied by a ``LeagueContext.scoring`` dict. Unknown keys are ignored; absent
        keys keep the nflverse defaults. ``ppr_value`` wins over the boolean ``ppr``."""
        if isinstance(league, dict):  # a bare scoring dict, or a league-shaped dict
            s = dict(league.get("scoring", league))
        else:
            s = dict(getattr(league, "scoring", None) or {})
        rec = s.get("ppr_value")
        if rec is None:
            rec = 0.5 if s.get("half_ppr") else (1.0 if s.get("ppr") else 0.0)
        kwargs = {"rec": float(rec)}
        for f in fields(cls):
            if f.name != "rec" and f.name in s:
                kwargs[f.name] = float(s[f.name])
        return cls(**kwargs)

    def describe(self) -> dict[str, float]:
        return {f.name: getattr(self, f.name) for f in fields(self)}


def _col(df: pd.DataFrame, name: str) -> pd.Series:
    if name in df.columns:
        return pd.to_numeric(df[name], errors="coerce").fillna(0.0)
    return pd.Series(0.0, index=df.index)


def score_stat_lines(df: pd.DataFrame, rules: ScoringRules) -> pd.Series:
    """Fantasy points for each row of an nflverse ``stats_player_week``-shaped frame."""
    pass_yds = _col(df, "passing_yards")
    attempts = _col(df, "attempts")
    comps = _col(df, "completions")
    rec = rules.rec + (rules.te_premium * (df["position"] == "TE") if "position" in df else 0.0)
    pts = (
        pass_yds * rules.pass_yd
        + _col(df, "passing_tds") * rules.pass_td
        + _col(df, "passing_interceptions") * rules.pass_int
        + comps * rules.pass_cmp
        + (attempts - comps).clip(lower=0) * rules.pass_inc
        + attempts * rules.pass_att
        + (pass_yds >= 300) * rules.pass_300_bonus
        + (pass_yds >= 400) * rules.pass_400_bonus
        + _col(df, "sacks_suffered") * rules.sack_taken
        + _col(df, "rushing_yards") * rules.rush_yd
        + _col(df, "rushing_tds") * rules.rush_td
        + _col(df, "receptions") * rec
        + _col(df, "receiving_yards") * rules.rec_yd
        + _col(df, "receiving_tds") * rules.rec_td
        + sum(_col(df, c) for c in _FUMBLE_LOST_COLS) * rules.fumble_lost
        + sum(_col(df, c) for c in _TWO_PT_COLS) * rules.two_pt
        + _col(df, "special_teams_tds") * rules.special_teams_td
    )
    return pts.astype(float)
