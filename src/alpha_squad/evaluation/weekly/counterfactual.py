"""Oracle and counterfactual FLEX boards that isolate the combination step (W4).

Every board here is a **diagnostic**. Each one uses realized outcomes by design and **none is a
production candidate** — they exist to bound what fixing one half of the problem could possibly
buy, before any causal method is judged against that bound.

The two that matter
-------------------
A FLEX board is a pooled sort of three positional prediction vectors, so its quality has
exactly two inputs: the **order inside each position**, and the **scale that interleaves them**.
The oracles fix one and hold the other at Alpha's:

* ``ORACLE_XPOS`` — Alpha's within-position ordering, **perfect** cross-position scale.
  Ceiling on fixing the combination step alone.
* ``ORACLE_WITHIN`` — **perfect** within-position ordering, Alpha's cross-position scale.
  Ceiling on fixing the positional models alone.

Both are built by *permuting the same week's realized values*, never by inventing numbers. For
position *P*, let ``V_P`` be that week's realized values sorted descending and ``S_P`` Alpha's
predicted values sorted descending. Then

    ORACLE_XPOS  : the player at Alpha-rank i within P gets score V_P[i]
    ORACLE_WITHIN: the player at realized-rank i within P gets score S_P[i]

``ORACLE_XPOS`` therefore keeps Alpha's ordering intact inside each position — a player Alpha
ranked 4th among RBs still sits 4th among RBs — while giving the position the true value curve
it should be interleaved on. ``ORACLE_WITHIN`` does the mirror image.

The decomposition they produce is **not additive** and is labelled as such wherever it is
reported. The additive decomposition is the pairwise one in ``crosspos.py``.
"""

from __future__ import annotations

from alpha_squad.evaluation.weekly.benchmark import Board, BoardRow

#: Every counterfactual this module can build. Fixed in the pre-registration.
COUNTERFACTUALS: tuple[str, ...] = (
    "ORACLE_BOTH",
    "ORACLE_XPOS",
    "ORACLE_WITHIN",
    "CF_SWAP_RB",
    "CF_SWAP_WR",
    "CF_SWAP_TE",
)


def _by_position(board: Board) -> dict[str, list[BoardRow]]:
    out: dict[str, list[BoardRow]] = {}
    for row in board.rows:
        out.setdefault(row.position, []).append(row)
    return out


def _scored_board(
    board: Board, scores: dict[str, float], tiebreak: dict[str, float] | None = None
) -> Board:
    """Re-rank `board`'s players by `scores`, densely.

    `tiebreak` is load-bearing, not cosmetic. **42.5% of realized player-week values tie inside
    a position-week** over the evaluated universe (8,657 of 20,364 across 2021-2025 RB/WR/TE;
    3,393 of them exactly 0.0 -- counted by `scripts/research/w4_validity_gates.py`, which
    prints the figure on every run), so an oracle that
    assigns realized values to players will hand equal scores to players the source ordering
    had strictly separated. Falling back to `player_id` there would silently destroy the very
    ordering the oracle is supposed to preserve, and `ORACLE_XPOS` would no longer be "Alpha's
    within-position order with a perfect scale" -- it would be a partially scrambled version of
    it, understating the oracle and therefore the ceiling being measured.

    The caller passes the ordering whose ties should be resolved in its favour; `player_id`
    remains the final, deterministic backstop."""
    tb = tiebreak or {}
    ordered = sorted(
        board.rows,
        key=lambda r: (-scores[r.player_id], tb.get(r.player_id, 0.0), r.player_id),
    )
    return Board(
        board.season,
        board.week,
        board.label,
        [
            BoardRow(r.player_id, r.position, float(i), r.realized)
            for i, r in enumerate(ordered, start=1)
        ],
    )


def _rank_map(board: Board, key: dict[str, float]) -> dict[str, float]:
    """Global 1..N rank of each player under `key` (descending), for use as a tiebreak."""
    ordered = sorted(board.rows, key=lambda r: (-key[r.player_id], r.player_id))
    return {r.player_id: float(i) for i, r in enumerate(ordered, start=1)}


def oracle_both(board: Board) -> Board:
    """Perfect board: pool realized points. A sanity check — must score ρ = 1."""
    return _scored_board(board, {r.player_id: float(r.realized) for r in board.rows})


def oracle_cross_position(
    board: Board, predictions: dict[str, float], *, use_tiebreak: bool = True
) -> Board:
    """``ORACLE_XPOS`` — Alpha's within-position order, the true cross-position scale.

    The player Alpha ranked *i*-th among RBs receives the *i*-th largest realized RB value of
    that week. Alpha's ordering inside every position is preserved exactly; only the values the
    positions are interleaved on change. Whatever this board gains over current Alpha is the
    **entire** ceiling of the combination step."""
    scores: dict[str, float] = {}
    for _position, rows in _by_position(board).items():
        values = sorted((float(r.realized) for r in rows), reverse=True)
        alpha_order = sorted(rows, key=lambda r: (-predictions[r.player_id], r.player_id))
        for i, row in enumerate(alpha_order):
            scores[row.player_id] = values[i]
    # Ties in the realized value curve must resolve in ALPHA's favour, or this stops being
    # "Alpha's within-position ordering with a perfect scale". `use_tiebreak=False` reproduces
    # the defective construction W4 caught and is for that diagnostic only (see the module
    # docstring of `scripts/research/w4_flex_forensics.py`); it is never the default.
    return _scored_board(board, scores, _rank_map(board, predictions) if use_tiebreak else None)


def oracle_within_position(
    board: Board, predictions: dict[str, float], *, use_tiebreak: bool = True
) -> Board:
    """``ORACLE_WITHIN`` — perfect within-position order, Alpha's cross-position scale.

    The genuinely best RB of the week receives Alpha's largest RB prediction, and so on. The
    positional rankings become perfect while the scale that interleaves them stays exactly as
    miscalibrated (or not) as Alpha's is."""
    scores: dict[str, float] = {}
    for _position, rows in _by_position(board).items():
        alpha_values = sorted((predictions[r.player_id] for r in rows), reverse=True)
        true_order = sorted(rows, key=lambda r: (-float(r.realized), r.player_id))
        for i, row in enumerate(true_order):
            scores[row.player_id] = alpha_values[i]
    # Mirror image: ties in Alpha's value curve resolve in the REALIZED ordering's favour.
    realized_key = {r.player_id: float(r.realized) for r in board.rows}
    return _scored_board(board, scores, _rank_map(board, realized_key) if use_tiebreak else None)


def swap_one_position_scale(
    board: Board, predictions: dict[str, float], position: str, *, use_tiebreak: bool = True
) -> Board:
    """``CF_SWAP_<P>`` — give **one** position the oracle scale, leave the others as Alpha.

    Answers "which position's scale is carrying the effect?" directly. Within-position ordering
    is Alpha's everywhere, including the swapped position, so this isolates scale alone."""
    scores = dict(predictions)
    for pos, rows in _by_position(board).items():
        if pos != position:
            continue
        values = sorted((float(r.realized) for r in rows), reverse=True)
        alpha_order = sorted(rows, key=lambda r: (-predictions[r.player_id], r.player_id))
        for i, row in enumerate(alpha_order):
            scores[row.player_id] = values[i]
    return _scored_board(board, scores, _rank_map(board, predictions) if use_tiebreak else None)


def build(
    name: str, board: Board, predictions: dict[str, float], *, use_tiebreak: bool = True
) -> Board:
    """Dispatch by counterfactual name, raising on an unknown one rather than defaulting."""
    if name == "ORACLE_BOTH":
        return oracle_both(board)
    if name == "ORACLE_XPOS":
        return oracle_cross_position(board, predictions, use_tiebreak=use_tiebreak)
    if name == "ORACLE_WITHIN":
        return oracle_within_position(board, predictions, use_tiebreak=use_tiebreak)
    if name.startswith("CF_SWAP_"):
        return swap_one_position_scale(
            board, predictions, name.removeprefix("CF_SWAP_"), use_tiebreak=use_tiebreak
        )
    known = ", ".join(COUNTERFACTUALS)
    raise ValueError(f"unknown counterfactual {name!r}; known: {known}")
