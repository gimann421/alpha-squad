"""W1.1 --- harvest FantasyPros weekly consensus boards from the official API.

Why this exists
---------------
W1 concluded "no 1-QB weekly overall/FLEX board exists". That conclusion was drawn from the
**DynastyProcess `db_fpecr` mirror**, which is the only weekly ECR source this repository had
ever read. It is correct about the mirror (verified exhaustively in W1.1: 54 distinct modern
`fp_page` values, none an RB/WR/TE weekly board) and **wrong as a statement about
FantasyPros**, which publishes a regular weekly FLEX board and serves it historically through
its official API -- a source this project already has a configured key for and had never
queried for weekly rankings.

This script harvests that API, caching every response to disk with its own hash so the boards
are an immutable, re-checkable vintage rather than a live re-fetch (the same discipline
`storage/snapshots.py` applies to every other source).

What the API gives, and what it does NOT
----------------------------------------
* `position=FLX` is the genuine RB/WR/TE board -- verified: zero QB rows.
* `position=OP` is the superflex board, a different product.
* `scoring` accepts `PPR`, `HALF` and `STD`, so Half-PPR weekly ECR exists historically.
* Every response carries `last_updated_ts`, and it is **Sunday ~16:54-17:00 UTC** -- i.e. the
  board frozen at the 1pm ET kickoff. That is a *different vintage* from the mirror's Friday
  board, and the two must never be pooled.
* **The configured key is a public tier: `public_api_limited=true`, `limit=10`.** `count`
  reports the true board size (e.g. 371 for 2023 wk8 FLX) but only the top 10 rows are
  returned. No parameter defeats it (`limit`, `offset`, `experts` all tested); the
  non-public `/v2/` and `/v1/` paths return 403. This is an access control and is not worked
  around -- it is reported as the acquisition limit it is.

**Per-player context fields are NOT historical and must not be used.** Verified on 2021 wk5:
`player_team_id` gives Davante Adams as LAR, Stefon Diggs as WAS, Cooper Kupp as SEA -- their
*current* teams, not their 2021 ones. `player_opponent` and `player_game_kickoff_ts` are the
historical week's schedule joined to that **current** team, so they are internally consistent
and externally wrong. Using them for the already-played exclusion would drop the wrong players
in nearly every week. Only the ranking columns and the player identity are taken from this
source; every schedule and roster fact comes from nflverse.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

import httpx

BASE = "https://api.fantasypros.com/public/v2/json/nfl"

#: The boards W1.1 harvests. FLX is the finding that reopened the question; the positional
#: boards are what let vintage drift be separated from reconstruction error (both products
#: exist in the mirror too, so the same board can be compared across the two sources).
POSITIONS = ("FLX", "OP", "QB", "RB", "WR", "TE", "K", "DST")
SCORINGS = ("PPR", "HALF")

#: Only the columns that are actually historical. See the module docstring: everything
#: schedule- or roster-derived in the payload is reconstructed against the CURRENT roster.
KEEP_PLAYER_FIELDS = (
    "player_id",
    "player_name",
    "player_position_id",
    "sportsdata_id",
    "rank_ecr",
    "rank_ave",
    "rank_min",
    "rank_max",
    "rank_std",
    "pos_rank",
)


def cache_path(root: Path, season: int, week: int, position: str, scoring: str) -> Path:
    return root / f"{season}" / f"wk{week:02d}" / f"{position}_{scoring}.json"


#: The API rate-limits with a bare 429 and no Retry-After header, so backoff is the only
#: signal available. Being a good citizen of someone else's API is not optional: a harvest
#: that hammers through 429s is abuse, not research.
MAX_RETRIES = 6
BACKOFF_BASE_SECONDS = 4.0


def fetch_board(
    client: httpx.Client, key: str, season: int, week: int, position: str, scoring: str
) -> dict:
    for attempt in range(MAX_RETRIES):
        resp = client.get(
            f"{BASE}/{season}/consensus-rankings",
            params={"position": position, "scoring": scoring, "week": week, "type": "WEEKLY"},
            headers={"x-api-key": key},
            timeout=60,
        )
        if resp.status_code != 429:
            break
        wait = BACKOFF_BASE_SECONDS * (2**attempt)
        print(f"    429 on {season} wk{week} {position}/{scoring}; backing off {wait:.0f}s")
        time.sleep(wait)
    resp.raise_for_status()
    body = resp.json()
    players = [{k: p.get(k) for k in KEEP_PLAYER_FIELDS} for p in (body.get("players") or [])]
    return {
        "season": season,
        "week": week,
        "position": position,
        "scoring": scoring,
        "count": body.get("count"),
        "returned": len(players),
        "limit": body.get("limit"),
        "public_api_limited": body.get("public_api_limited"),
        "total_experts": body.get("total_experts"),
        "last_updated": body.get("last_updated"),
        "last_updated_ts": body.get("last_updated_ts"),
        "expert_filters": body.get("filters"),
        "players": players,
        # Hash of exactly what we kept, so a later re-harvest can be diffed against this one.
        "content_sha256": hashlib.sha256(json.dumps(players, sort_keys=True).encode()).hexdigest(),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seasons", default="2021,2022,2023,2024,2025")
    ap.add_argument("--weeks", default="1-18")
    ap.add_argument("--positions", default=",".join(POSITIONS))
    ap.add_argument("--scorings", default=",".join(SCORINGS))
    ap.add_argument("--cache", default="reports/weekly/fp_api_cache")
    ap.add_argument("--sleep", type=float, default=0.25)
    ap.add_argument("--refresh", action="store_true", help="re-fetch even if cached")
    args = ap.parse_args()

    key = os.environ.get("FANTASYPROS_API_KEY")
    if not key:
        sys.exit(
            "FANTASYPROS_API_KEY is not configured. This adapter never guesses a key "
            "(CLAUDE_CODE_LEAD_PROMPT.md §8)."
        )

    seasons = [int(s) for s in args.seasons.split(",")]
    lo, hi = (args.weeks.split("-") + [args.weeks])[:2]
    weeks = list(range(int(lo), int(hi) + 1))
    positions = args.positions.split(",")
    scorings = args.scorings.split(",")
    root = Path(args.cache)

    fetched = cached = failed = 0
    with httpx.Client(follow_redirects=True) as client:
        for season in seasons:
            for week in weeks:
                for position in positions:
                    for scoring in scorings:
                        dest = cache_path(root, season, week, position, scoring)
                        if dest.exists() and not args.refresh:
                            cached += 1
                            continue
                        try:
                            board = fetch_board(client, key, season, week, position, scoring)
                        except Exception as exc:  # noqa: BLE001 - report, never fabricate
                            print(f"  FAIL {season} wk{week} {position}/{scoring}: {exc}")
                            failed += 1
                            continue
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        dest.write_text(json.dumps(board, indent=1))
                        fetched += 1
                        if fetched % 50 == 0:
                            print(f"  ... {fetched} fetched")
                        time.sleep(args.sleep)
            print(f"{season}: done (fetched={fetched} cached={cached} failed={failed})")
    print(f"\nfetched={fetched} cached={cached} failed={failed}  -> {root}")


if __name__ == "__main__":
    main()
