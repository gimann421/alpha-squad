"""nflverse/nfldata adapter (full NFL schedule incl. future games). No auth required.

The repo's other nflverse access is via release assets, which publish no schedule tag
(``features/games.py`` derives the played-games calendar from play-by-play). A ROS model also
needs the *unplayed* remainder of the schedule -- remaining games per team, bye weeks, and the
kickoff date of every game -- and pbp cannot supply that. ``nflverse/nfldata``'s ``games.csv``
carries every game of every season (including the not-yet-played rest of the current season)
with ``gameday``/``gametime``. Verified reachable via raw.githubusercontent.com (D116).

Deliberately NOT registered in ``sources/registry.py::all_adapters``: that would change what
``alpha-squad sources status``/``ingest`` do for every existing workflow. The ROS pipeline
(``ros/ingest.py``) instantiates it directly.

Note: games.csv also carries pregame betting lines and (for played games) results. The ROS panel
reads only ``game_id/season/game_type/week/gameday/gametime/away_team/home_team``; lines for
future weeks would be a leakage hazard at a historical snapshot and are never used."""

from __future__ import annotations

from alpha_squad.sources.file_release import DatasetSpec, FileReleaseSourceAdapter

_BASE = "https://raw.githubusercontent.com/nflverse/nfldata/master/data"


class NfldataSource(FileReleaseSourceAdapter):
    name = "nfldata"
    datasets = {"games": DatasetSpec("games", f"{_BASE}/games.csv", "csv")}
