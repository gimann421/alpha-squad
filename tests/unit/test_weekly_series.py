"""Weekly market-series definitions (W1).

These pin the two facts about the weekly boards that a future change is most likely to erase,
both of which are D56's rule applied to the weekly program:

1. a series is `(ecr_type, page_type)`, never `ecr_type` alone; and
2. the only weekly cross-position board that exists is the **superflex** one, so a FLEX
   benchmark is a *reconstruction* from it and must never be named as though it were a
   published 1-QB board.

Offline; these are definitional, not data-dependent.
"""

from __future__ import annotations

import pytest

from alpha_squad.evaluation.weekly.scoring import FLEX_POSITIONS, RANKED_POSITIONS
from alpha_squad.evaluation.weekly.series import (
    ALL_WEEKLY_SERIES,
    WEEKLY_DST,
    WEEKLY_OVERALL_SUPERFLEX,
    flex_reference_series,
    positional_series,
)


def test_every_ranked_position_has_a_weekly_board():
    """All six product positions must resolve, or that position has no benchmark at all."""
    for position in RANKED_POSITIONS:
        assert positional_series(position).positions == (position,)


def test_series_are_uniquely_identified_by_the_ecr_type_page_type_pair():
    """D56: `ecr_type` alone is not a rank space. `wp` labels six independently-ranked pages,
    so keying on it would merge six different 1..N rankings into one colliding board."""
    pairs = [(s.ecr_type, s.page_type) for s in ALL_WEEKLY_SERIES]
    assert len(set(pairs)) == len(pairs)
    assert len({s.ecr_type for s in ALL_WEEKLY_SERIES}) < len(pairs)


def test_the_only_cross_position_weekly_board_is_the_superflex_one():
    """If a 1-QB weekly overall board is ever added, this test should fail and force the FLEX
    reconstruction to be revisited rather than silently kept."""
    cross = [s for s in ALL_WEEKLY_SERIES if len(s.positions) > 1]
    assert cross == [WEEKLY_OVERALL_SUPERFLEX]
    assert "SUPERFLEX" in WEEKLY_OVERALL_SUPERFLEX.label


def test_flex_reference_is_the_superflex_board_and_says_so():
    """The FLEX benchmark is built by dropping QBs from a superflex board. Naming that
    function `weekly_flex_series` is exactly how a superflex measurement gets restated as a
    1-QB one -- the mistake D56 found had already happened for every pre-D56 draft number."""
    assert flex_reference_series() is WEEKLY_OVERALL_SUPERFLEX
    assert "QB" in WEEKLY_OVERALL_SUPERFLEX.positions
    assert set(FLEX_POSITIONS) < set(WEEKLY_OVERALL_SUPERFLEX.positions)


def test_flex_positions_exclude_qb_k_and_dst():
    assert FLEX_POSITIONS == ("RB", "WR", "TE")
    assert "QB" not in FLEX_POSITIONS
    assert not {"K", "DST"} & set(FLEX_POSITIONS)


def test_the_superflex_board_carries_no_kicker_or_defense():
    """A cross-position ranking spanning all six positions does not exist in the mirror, so an
    'overall' ranking including K/DST has no ECR analogue. FLEX (RB/WR/TE) does."""
    assert not {"K", "DST"} & set(WEEKLY_OVERALL_SUPERFLEX.positions)


def test_dst_series_is_flagged_as_team_coded():
    """DST rows identify a team, not a player, so they join through the team-code alias path
    (`asq_dst_<team>`), never through `fantasypros_id`. A caller that treated them uniformly
    would silently drop all 32 defenses."""
    assert WEEKLY_DST.team_coded is True
    assert all(s.team_coded is False for s in ALL_WEEKLY_SERIES if s is not WEEKLY_DST)


def test_unknown_position_raises_rather_than_defaulting():
    with pytest.raises(ValueError, match="no weekly board for position"):
        positional_series("LB")


def test_rb_wr_te_boards_are_the_ppr_pages():
    """There is no half-PPR page in the mirror. Recording which page each series actually is
    keeps that limitation visible at the definition site."""
    for position in ("RB", "WR", "TE"):
        assert "ppr" in positional_series(position).fp_page
        assert "half" not in positional_series(position).fp_page
