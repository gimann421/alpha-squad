"""Fetch (or locate) the raw files the ROS pipeline reads, and record their provenance.

Reuses the repository's source adapters (``sources/nflverse.py``, ``sources/dynastyprocess.py``,
plus the new ``sources/nfldata.py``) so downloads land in the same immutable, timestamped
``data/raw/<source>/<dataset>/captured_at=<date>/`` layout with a sha256, exactly like
``alpha-squad sources ingest``. Nothing is downloaded when a local copy already exists unless
``refresh=True``; the newest ``captured_at`` directory wins.

The DynastyProcess ECR archive is one cumulative file, so a stale copy silently lacks the most
recent weekly scrapes. ``ensure_inputs`` therefore reports each input's ``captured_at`` and the
latest ECR ``scrape_date`` it actually contains (see ``snapshots.describe_ecr_archive``) so a
caller can see how fresh the live recommendation's market data is.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from alpha_squad.config.settings import Settings, get_settings
from alpha_squad.sources.dynastyprocess import DynastyProcessSource
from alpha_squad.sources.nfldata import NfldataSource
from alpha_squad.sources.nflverse import NflverseSource

_CAPTURED = re.compile(r"captured_at=(\d{4}-\d{2}-\d{2})")


@dataclass(frozen=True)
class InputFile:
    source: str
    dataset: str
    season: int | None
    path: str
    captured_at: str
    sha256: str
    bytes: int


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def latest_local(
    settings: Settings, source: str, dataset: str, season: int | None = None
) -> Path | None:
    """Newest local raw file for (source, dataset[, season]), or None."""
    base = settings.raw_dir / source / dataset
    if not base.exists():
        return None
    pattern = f"season-{season}_*" if season is not None else "*"
    candidates = [p for p in base.glob(f"captured_at=*/{pattern}") if p.is_file()]
    if not candidates:
        return None

    def key(p: Path) -> str:
        m = _CAPTURED.search(str(p))
        return m.group(1) if m else ""

    return max(candidates, key=key)


def _describe(source: str, dataset: str, season: int | None, path: Path) -> InputFile:
    m = _CAPTURED.search(str(path))
    return InputFile(
        source=source,
        dataset=dataset,
        season=season,
        path=str(path),
        captured_at=m.group(1) if m else "unknown",
        sha256=_sha256(path),
        bytes=path.stat().st_size,
    )


def ensure_inputs(
    seasons: list[int],
    settings: Settings | None = None,
    *,
    refresh: bool = False,
    refresh_season: int | None = None,
) -> dict[str, InputFile | dict[int, InputFile]]:
    """Make sure every raw input exists locally; return their provenance records.

    ``refresh=True`` re-downloads everything. ``refresh_season=S`` re-downloads only the inputs
    that change as a season is played -- the cumulative ECR archive, the ID map, the schedule and
    season ``S``'s weekly files -- unless today's copy is already local; completed seasons are
    reused. Raises (via the adapters) rather than substituting anything if a download fails."""
    settings = settings or get_settings()
    today = datetime.now(UTC).date().isoformat()
    nfl, dp, nfld = (
        NflverseSource(settings),
        DynastyProcessSource(settings),
        NfldataSource(settings),
    )

    def get(adapter, dataset: str, season: int | None = None) -> InputFile:
        path = None if refresh else latest_local(settings, adapter.name, dataset, season)
        moving = refresh_season is not None and (season is None or season == refresh_season)
        if path is not None and moving and f"captured_at={today}" not in str(path):
            path = None
        if path is None:
            params = {"season": season} if season is not None else {}
            path = Path(adapter.fetch(dataset, **params).local_path)
        return _describe(adapter.name, dataset, season, path)

    out: dict[str, InputFile | dict[int, InputFile]] = {
        "ecr": get(dp, "fp_ecr_history"),
        "player_ids": get(dp, "player_ids"),
        "schedule": get(nfld, "games"),
    }
    for ds in ("stats_player_week", "pbp", "injuries"):
        out[ds] = {s: get(nfl, ds, s) for s in seasons}
    return out


def write_manifest(inputs: dict, path: Path) -> None:
    def conv(v):
        if isinstance(v, dict):
            return {str(k): conv(x) for k, x in v.items()}
        return asdict(v)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({k: conv(v) for k, v in inputs.items()}, indent=2, sort_keys=True))
