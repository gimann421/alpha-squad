"""Sleeper API adapter. Sleeper itself requires no API key, but direct egress to
api.sleeper.app is blocked by this environment's proxy policy — confirmed empirically as
`httpx.ProxyError('403 Forbidden')` raised at connect time, not an application-level auth
failure. Implemented to the real endpoint shapes so it activates unchanged if the policy
changes. League/roster/draft state is loaded from local YAML in the meantime (see
docs/DECISIONS.md D6); the `player_ids` crosswalk role Sleeper would otherwise fill is
covered by DynastyProcess's `sleeper_id` column."""

from __future__ import annotations

from datetime import datetime

import httpx

from alpha_squad.config.settings import Settings, get_settings
from alpha_squad.sources.base import (
    RawSnapshot,
    SourceAdapter,
    SourceBlockedError,
    SourceError,
    sha256_file,
    utcnow,
)

_ENDPOINTS = {
    "state": "/state/nfl",
    "players": "/players/nfl",
    "trending_adds": "/players/nfl/trending/add?limit=25",
    "trending_drops": "/players/nfl/trending/drop?limit=25",
    "league": "/league/{league_id}",
    "league_rosters": "/league/{league_id}/rosters",
    "league_drafts": "/league/{league_id}/drafts",
    "league_users": "/league/{league_id}/users",
}


class SleeperSource(SourceAdapter):
    name = "sleeper"

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()

    def list_datasets(self) -> list[str]:
        return list(_ENDPOINTS.keys())

    def default_health_params(self, dataset: str) -> dict:
        if "{league_id}" in _ENDPOINTS[dataset]:
            return {"league_id": "0"}
        return {}

    def fetch(self, dataset: str, *, captured_at: datetime | None = None, **params) -> RawSnapshot:
        if dataset not in _ENDPOINTS:
            raise SourceError(f"unknown sleeper dataset '{dataset}'")
        path = _ENDPOINTS[dataset].format(**params)
        url = f"{self.settings.sleeper_base_url}{path}"
        captured_at = captured_at or utcnow()

        try:
            resp = httpx.get(url, timeout=30, follow_redirects=True)
        except httpx.ProxyError as e:
            raise SourceBlockedError(f"egress policy blocked sleeper/{dataset}: {e}") from e
        except httpx.TransportError as e:
            raise SourceError(f"transport error fetching sleeper/{dataset}: {e}") from e

        if resp.status_code == 404:
            raise SourceError(f"sleeper/{dataset} not found (404): {url}")
        resp.raise_for_status()

        dest = (
            self.settings.raw_dir
            / self.name
            / dataset
            / f"captured_at={captured_at.date().isoformat()}"
            / f"{dataset}.json"
        )
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(resp.content)

        body = resp.json()
        if isinstance(body, list):
            rows = len(body)
            columns = tuple(sorted(body[0].keys())) if body and isinstance(body[0], dict) else None
        elif isinstance(body, dict):
            rows = 1
            columns = tuple(sorted(body.keys()))
        else:
            rows, columns = None, None

        return RawSnapshot(
            source=self.name,
            dataset=dataset,
            captured_at=captured_at,
            url=url,
            local_path=dest,
            sha256=sha256_file(dest),
            rows=rows,
            columns=columns,
            params=tuple(sorted((k, str(v)) for k, v in params.items())),
        )
