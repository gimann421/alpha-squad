"""Alpha's weekly board, built from the existing model's stored predictions (W3).

**This module builds no model and fits nothing.** It reads `weekly_projection_snapshot` —
written by the unmodified `alpha-squad train established` path — and turns it into a board
shaped exactly like the ECR and baseline boards in `benchmark.py`, so all three are scored by
the same code over the same players.

Two properties of the existing implementation that this module must respect rather than paper
over, both established in the W3 audit (`docs/weekly/W3_PREREGISTRATION.md` §2.1):

* **Alpha can only predict a player who played.** `player_week_features` is built from
  `player_week_stats`, which has a row only when the player appeared. So Alpha's coverage of a
  week is bounded by who played, and the model cannot produce a real Friday board at all. W3
  measures its ranking quality on the evaluable set, which is what every system is scored on —
  but `coverage_report` exists so that limitation is counted, not assumed away.
* **No K, no DST, no FLEX.** `POSITIONS` is QB/RB/WR/TE. FLEX is *constructed here* by pooling
  the RB/WR/TE predictions and ranking by predicted points, with no separate model, no manual
  cross-position adjustment and no normalisation — exactly the architecture the product intends
  and the W3 brief specifies.
"""

from __future__ import annotations

from dataclasses import dataclass

import duckdb

from alpha_squad.evaluation.weekly.benchmark import Board, BoardRow
from alpha_squad.evaluation.weekly.scoring import FLEX_POSITIONS

#: The only model whose weekly predictions are persisted, and therefore the only one the
#: product could serve. Imported by name rather than hardcoded so a rename cannot silently
#: point W3 at a different model than the one the API reads.
from alpha_squad.models.established.train import (  # noqa: E402
    WEEKLY_PROJECTION_BASE_MODEL,
)

#: Positions the existing weekly model covers. K and DST are absent by design (D57 made them
#: baselines, not models) and are NOT retrofitted in W3.
ALPHA_POSITIONS: tuple[str, ...] = ("QB", "RB", "WR", "TE")


@dataclass
class CoverageReport:
    """How much of the shared universe each system could actually rank."""

    universe: int
    alpha_ranked: int
    missing_player_ids: tuple[str, ...]

    @property
    def coverage(self) -> float:
        return self.alpha_ranked / self.universe if self.universe else 0.0


def load_alpha_predictions(
    con: duckdb.DuckDBPyConnection,
    season: int,
    week: int,
    *,
    positions: tuple[str, ...] = ALPHA_POSITIONS,
    model_name: str = WEEKLY_PROJECTION_BASE_MODEL,
) -> dict[str, float]:
    """`{player_id: predicted_points}` for one week, straight from the stored snapshot.

    Nothing is recomputed, rescaled or imputed here: a player Alpha did not predict is simply
    absent, and the caller decides what that means."""
    rows = con.execute(
        """
        SELECT player_id, predicted_points
        FROM weekly_projection_snapshot
        WHERE season = ? AND week = ? AND model_name = ? AND position = ANY(?)
        """,
        [season, week, model_name, list(positions)],
    ).fetchall()
    return {r[0]: float(r[1]) for r in rows}


def alpha_board(
    reference: Board,
    predictions: dict[str, float],
    tiebreak: dict[str, float] | None = None,
) -> tuple[Board, CoverageReport]:
    """Alpha's ranking of **exactly the players on `reference`**, ordered by predicted points.

    Taking the universe from the reference board (ECR's, per the pre-registration) is what
    makes the three-way comparison paired: every system ranks the same players, so a
    difference between them is a difference in *ordering*, never in who was on the list.

    A reference player Alpha did not predict is **dropped and counted**, never imputed —
    inventing a prediction would be fabricating the very quantity under test. The caller
    applies the same drop to the other systems so the universes stay identical.

    `tiebreak` (default `None`, which reproduces W3 exactly) resolves equal predicted values in
    favour of a caller-supplied ordering before falling back to `player_id`. It exists for W4's
    calibration boards: `CAL_QUANTILE` and `CAL_RANKPCT` are step functions on an empirical
    distribution, so they map distinct predictions onto **equal** calibrated values -- 362 and
    355 manufactured same-position ties per week respectively over the 79 evaluated weeks, while
    the strictly-increasing `CAL_MEANVAR` and `CAL_AFFINE` manufacture exactly 0
    (`scripts/research/w4_validity_gates.py` prints these counts on every run). Without a
    tiebreak the sort would reorder those players by `player_id`, a within-position change --
    and W4's whole claim is that these transforms are monotone within a position and therefore
    purely cross-position. Passing Alpha's own order here keeps that true."""
    ranked = [r for r in reference.rows if r.player_id in predictions]
    missing = tuple(r.player_id for r in reference.rows if r.player_id not in predictions)
    tb = tiebreak or {}
    ordered = sorted(
        ranked,
        key=lambda r: (-predictions[r.player_id], tb.get(r.player_id, 0.0), r.player_id),
    )
    board = Board(
        reference.season,
        reference.week,
        reference.label,
        [
            BoardRow(r.player_id, r.position, float(i), r.realized)
            for i, r in enumerate(ordered, start=1)
        ],
    )
    return board, CoverageReport(len(reference.rows), len(ranked), missing)


def restrict_board(reference: Board, keep: set[str]) -> Board:
    """Re-rank `reference` over only `keep`, preserving its own ordering.

    Used to shrink ECR and the baseline to Alpha's coverage so all three systems are scored on
    an identical player set. The surviving rows keep their relative order and are renumbered
    1..N, which is the same dense-rank convention every other board uses."""
    rows = [r for r in reference.rows if r.player_id in keep]
    rows.sort(key=lambda r: (r.ecr, r.player_id))
    return Board(
        reference.season,
        reference.week,
        reference.label,
        [BoardRow(r.player_id, r.position, float(i), r.realized) for i, r in enumerate(rows, 1)],
    )


def flex_reference_from_positions(
    con: duckdb.DuckDBPyConnection,
    flex_board_: Board,
    season: int,
    week: int,
) -> dict[str, float]:
    """Alpha's pooled FLEX signal: RB + WR + TE predicted points in one pool, unadjusted.

    This is the whole cross-position calibration question made concrete — three separately
    trained models' absolute outputs are compared directly against each other, with no
    normalisation. W3 measures whether that ordering is coherent and does not correct it."""
    preds = load_alpha_predictions(con, season, week, positions=FLEX_POSITIONS)
    on_board = {r.player_id for r in flex_board_.rows}
    return {pid: v for pid, v in preds.items() if pid in on_board}
