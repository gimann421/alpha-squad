"""CollegeFootballData (CFBD) adapter. Requires a free API key. Per
CLAUDE_CODE_LEAD_PROMPT.md §8, this adapter never attempts a network call without
CFBD_API_KEY already configured by the user. Direct egress to api.collegefootballdata.com is
additionally blocked by this environment's proxy policy regardless of key (confirmed
empirically). The operating substitute is cfbfastR-data's `player_stats` — see
docs/DECISIONS.md D3."""

from __future__ import annotations

from datetime import datetime

import httpx

from alpha_squad.config.settings import Settings, get_settings
from alpha_squad.sources.base import (
    RawSnapshot,
    SourceAdapter,
    SourceBlockedError,
    SourceCredentialsError,
    SourceError,
    sha256_file,
    utcnow,
    write_bytes_atomic,
)

_BASE = "https://api.collegefootballdata.com"
_DATASETS = {
    "teams": "/teams",
    "player_usage": "/player/usage",
    "recruiting_players": "/recruiting/players",
}


class CfbdSource(SourceAdapter):
    name = "cfbd"

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()

    def list_datasets(self) -> list[str]:
        return list(_DATASETS.keys())

    def default_health_params(self, dataset: str) -> dict:
        if dataset in ("player_usage", "recruiting_players"):
            return {"year": 2025}
        return {}

    def fetch(self, dataset: str, *, captured_at: datetime | None = None, **params) -> RawSnapshot:
        if dataset not in _DATASETS:
            raise SourceError(f"unknown cfbd dataset '{dataset}'")
        if not self.settings.cfbd_api_key:
            raise SourceCredentialsError(
                "CFBD_API_KEY is not configured. Get a free key at collegefootballdata.com and "
                "user authorization is required before use — see .env.example. Using "
                "cfbfastR-data as the operating substitute in the meantime."
            )

        url = f"{_BASE}{_DATASETS[dataset]}"
        captured_at = captured_at or utcnow()
        headers = {"Authorization": f"Bearer {self.settings.cfbd_api_key}"}

        try:
            resp = httpx.get(url, params=params, headers=headers, timeout=30, follow_redirects=True)
        except httpx.ProxyError as e:
            raise SourceBlockedError(f"egress policy blocked cfbd/{dataset}: {e}") from e
        except httpx.TransportError as e:
            raise SourceError(f"transport error fetching cfbd/{dataset}: {e}") from e

        if resp.status_code == 404:
            raise SourceError(f"cfbd/{dataset} not found (404): {url}")
        resp.raise_for_status()

        param_suffix = "_".join(f"{k}-{v}" for k, v in sorted(params.items())) or "default"
        dest = (
            self.settings.raw_dir
            / self.name
            / dataset
            / f"captured_at={captured_at.date().isoformat()}"
            / f"{param_suffix}_{dataset}.json"
        )
        dest.parent.mkdir(parents=True, exist_ok=True)
        write_bytes_atomic(dest, resp.content)

        body = resp.json()
        rows = len(body) if isinstance(body, list) else 1
        columns = tuple(sorted(body[0].keys())) if isinstance(body, list) and body else None

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
