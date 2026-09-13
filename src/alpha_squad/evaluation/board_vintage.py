"""Board-vintage identity for reproducible draft-layer experiments (D92).

Why this exists
---------------
D91 concluded that the historical ECR board is mutable and that board vintage explained why
D89's published +49.0 came back as +28.0 on a rebuild. **D92 showed that was wrong**, and the
error was a measurement mistake rather than a data problem: D89 counted market-ranked players
*inside the projected board*, D91 counted every `market_rank` entry. Measured consistently, every
published board figure reproduces exactly, and the upstream file's sha256 is provably the same
blob D89 read.

What D92 *did* find is worse for reproducibility and has nothing to do with the board: **D88, D89
and D90's runner was never committed.** Every documented input to those phases reproduces
byte-for-byte in a fresh container, the simulation is deterministic, and model training is
bit-reproducible -- yet their published control-arm behaviour does not come back. Inputs that
match plus outputs that do not means the *transformation* differed, and the transformation was
uncommitted code.

So this module exists to make the *inputs* of a draft-layer experiment stateable and checkable in
one line, and `scripts/d92_paired_grid.py` exists so the transformation is never uncommitted
again. Neither is imported by any production path.

What a vintage is
-----------------
Three hashes, because no one of them is sufficient:

* **upstream board blob** -- `sha256(db_fpecr.parquet)`. DynastyProcess commits this file weekly
  to a public repo, so a vintage is addressable by commit forever. The `snapshot_registry.url`
  points at `master`, which moves; the sha256 does not.
* **upstream identity map** -- `sha256(db_playerids.csv)`. The same file decides which canonical
  `asq_` id each FantasyPros row lands on, so the board's *player set* depends on it as much as on
  the ranks.
* **assembled board** -- a per-season hash of `load_season_projections`, which is what the draft
  engine actually reads. It spans three tables (`uncertainty_predictions`, `rookie_predictions`
  and `projection_snapshot` for K/DST), so neither upstream hash implies it.

A database timestamp deliberately does **not** appear. `market/consensus.py` deletes and re-inserts
rather than appending, and the raw landing path is partitioned only by day
(`captured_at=YYYY-MM-DD`), so a timestamp does not determine the content: two captures on the same
day overwrite each other and leave one row in `snapshot_registry`.

A measured property worth stating, because it is what makes historical backtests safe
------------------------------------------------------------------------------------
D92 materialised four real vintages from upstream git (2026-07-03, 08-28, 09-04, 09-11) and hashed
the exact `(player, position, rank)` map the draft consumes. **All 17 historical board-seasons --
six for `ro`, six for `do`, five for `dsf` -- are identical across all four**, while the same hash
over the *live* season (2026) does change. The file grows only by appending new scrapes; rows
describing a past preseason never move. So board vintage cannot shift a 2020-2025 backtest, and
`HISTORICAL_BOARD_IS_APPEND_ONLY` records that as a checkable claim rather than folklore.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

import duckdb

from alpha_squad.league.replacement import load_season_projections

#: The two upstream datasets a board vintage depends on, as `snapshot_registry.dataset` values.
BOARD_DATASET = "fp_ecr_history"
IDMAP_DATASET = "player_ids"
BOARD_SOURCE = "dynastyprocess"

#: Projection values are hashed at this precision. Float text repr is not stable enough to hash
#: raw, and six decimals is far finer than any difference that could change a pick.
PROJECTION_DECIMALS = 6

#: Seasons every draft-layer phase since D89 measures over.
BACKTEST_SEASONS: tuple[int, ...] = (2020, 2021, 2022, 2023, 2024, 2025)

#: The vintage D88, D89, D90, D91 and D92 all ran against, verified three ways in D92: the blob at
#: dynastyprocess/data commit 9338630 (2026-09-11T04:31:15Z), the `snapshot_registry` row, and the
#: file on disk all carry the board sha256 below. Recorded so a later phase can assert it rather
#: than re-derive it, and so a *change* is loud instead of silent.
D89_BOARD_SHA256 = "a966176d2966591c4986833aefafb4c74e86f848ca1ba708f43e6a9e79e29525"
D89_IDMAP_SHA256 = "0174ea890e71d33fa0afc1b846ce1c92273542278a287b6bd52c3a4aa5edce73"
D89_BOARD_COMMIT = "9338630"

#: D92 measured this over four vintages spanning ten weeks; see the module docstring.
HISTORICAL_BOARD_IS_APPEND_ONLY = True


class VintageMismatchError(RuntimeError):
    """Raised when a run's board vintage is not the one it claims to be.

    Loud rather than tolerated: a draft-layer number is only comparable to another phase's number
    if both were measured against the same board, and D92 exists because that was never checkable.
    """


@dataclass(frozen=True)
class BoardVintage:
    """A reproducible identifier for the board an experiment ran against."""

    board_sha256: str | None
    idmap_sha256: str | None
    season_hashes: dict[int, str] = field(default_factory=dict)

    @property
    def combined_hash(self) -> str:
        """One hash over every season, so a report can quote a single value."""
        payload = json.dumps({str(s): h for s, h in sorted(self.season_hashes.items())})
        return hashlib.sha256(payload.encode()).hexdigest()

    def as_dict(self) -> dict:
        return {
            "board_sha256": self.board_sha256,
            "idmap_sha256": self.idmap_sha256,
            "season_hashes": {str(s): h for s, h in sorted(self.season_hashes.items())},
            "combined_hash": self.combined_hash,
        }

    def matches_d89(self) -> bool:
        """Is this the board every phase from D88 onward measured against?"""
        return self.board_sha256 == D89_BOARD_SHA256 and self.idmap_sha256 == D89_IDMAP_SHA256


def board_hash(con: duckdb.DuckDBPyConnection, season: int) -> str:
    """Hash of the assembled board for `season`, exactly as the draft engine reads it.

    Sorted by player id so row order cannot change the hash, and values rounded so that a
    difference has to be real rather than a float-formatting artifact."""
    projections, positions = load_season_projections(con, season)
    items = sorted(
        (pid, round(value, PROJECTION_DECIMALS), positions[pid])
        for pid, value in projections.items()
    )
    return hashlib.sha256(json.dumps(items).encode()).hexdigest()


def registry_source_hash(
    con: duckdb.DuckDBPyConnection, dataset: str, source: str = BOARD_SOURCE
) -> str | None:
    """The sha256 of the most recently captured snapshot of one upstream dataset.

    Returns `None` rather than raising when the dataset was never ingested, so a caller working
    against a fixture database gets a vintage with nulls instead of an exception."""
    row = con.execute(
        "SELECT sha256 FROM snapshot_registry WHERE source = ? AND dataset = ? "
        "ORDER BY captured_at DESC LIMIT 1",
        [source, dataset],
    ).fetchone()
    return row[0] if row else None


def compute_board_vintage(
    con: duckdb.DuckDBPyConnection, seasons: tuple[int, ...] = BACKTEST_SEASONS
) -> BoardVintage:
    """The full vintage triple for `seasons`."""
    return BoardVintage(
        board_sha256=registry_source_hash(con, BOARD_DATASET),
        idmap_sha256=registry_source_hash(con, IDMAP_DATASET),
        season_hashes={s: board_hash(con, s) for s in seasons},
    )


def assert_vintage(
    con: duckdb.DuckDBPyConnection,
    expected_combined_hash: str,
    seasons: tuple[int, ...] = BACKTEST_SEASONS,
) -> BoardVintage:
    """Verify the live board matches `expected_combined_hash`, or raise.

    Call this as a precondition of any experiment whose result will be compared against an earlier
    phase's. It is the check whose absence made D88-D90 unreproducible.

    `seasons` defaults to the whole `BACKTEST_SEASONS` window **on purpose, and a caller running a
    subset should leave it alone**. A vintage identifies the *board*, not the slice of it an
    experiment happened to touch: if the identifier changed with the season list, then a one-season
    diagnostic and a six-season replication could never quote the same vintage even when they read
    byte-identical data. Narrow it only to check a board that genuinely does not have the other
    seasons (a fixture, or a format whose series starts later)."""
    actual = compute_board_vintage(con, seasons)
    if actual.combined_hash != expected_combined_hash:
        raise VintageMismatchError(
            f"board vintage mismatch: expected combined_hash={expected_combined_hash}, "
            f"got {actual.combined_hash}. Per-season hashes: {actual.season_hashes}. "
            "A draft-layer result measured against a different board is not comparable to one "
            "measured against this board."
        )
    return actual


__all__ = [
    "BACKTEST_SEASONS",
    "BOARD_DATASET",
    "BOARD_SOURCE",
    "D89_BOARD_COMMIT",
    "D89_BOARD_SHA256",
    "D89_IDMAP_SHA256",
    "HISTORICAL_BOARD_IS_APPEND_ONLY",
    "IDMAP_DATASET",
    "PROJECTION_DECIMALS",
    "BoardVintage",
    "VintageMismatchError",
    "assert_vintage",
    "board_hash",
    "compute_board_vintage",
    "registry_source_hash",
]
