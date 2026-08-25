"""FantasyPros API adapter. Requires a paid API key. Per CLAUDE_CODE_LEAD_PROMPT.md §8
(item 4), paid/licensed access requires explicit user authorization — this adapter never
attempts a network call without FANTASYPROS_API_KEY already configured by the user, and never
invents or guesses a key. Live and AVAILABLE as of 2026-08-23 (D37) with a real key — see
docs/DECISIONS.md D3/D4/D31/D36/D37. The operating substitute, used when no key is configured,
is DynastyProcess's `db_fpecr` (historical ECR) and `values-players` (current ECR, including
2QB format)."""

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

_BASE = "https://api.fantasypros.com/public/v2/json/nfl"
_DATASETS = {
    "consensus_rankings": "/{season}/consensus-rankings",
    "projections": "/{season}/projections",
}


class FantasyProsSource(SourceAdapter):
    name = "fantasypros"

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()

    def list_datasets(self) -> list[str]:
        return list(_DATASETS.keys())

    def default_health_params(self, dataset: str) -> dict:
        # type must be uppercase per FantasyPros's real enum (ROS/DRAFT/DYNASTY/...,
        # confirmed against api.fantasypros.com/public/v2/docs/fantasypros_v2_public.yml) --
        # a lowercase value is silently ignored by the API rather than rejected.
        return {"season": 2026, "position": "WR", "type": "ROS"}

    def fetch(self, dataset: str, *, captured_at: datetime | None = None, **params) -> RawSnapshot:
        if dataset not in _DATASETS:
            raise SourceError(f"unknown fantasypros dataset '{dataset}'")
        if not self.settings.fantasypros_api_key:
            raise SourceCredentialsError(
                "FANTASYPROS_API_KEY is not configured. FantasyPros requires a paid API key "
                "and explicit user authorization before use — see .env.example. Using "
                "DynastyProcess ECR/values mirrors as the operating substitute in the meantime."
            )

        path = _DATASETS[dataset].format(season=params.get("season", 2026))
        query = {k: v for k, v in params.items() if k != "season"}
        url = f"{_BASE}{path}"
        captured_at = captured_at or utcnow()
        headers = {"x-api-key": self.settings.fantasypros_api_key}

        try:
            resp = httpx.get(url, params=query, headers=headers, timeout=30, follow_redirects=True)
        except httpx.ProxyError as e:
            raise SourceBlockedError(f"egress policy blocked fantasypros/{dataset}: {e}") from e
        except httpx.TransportError as e:
            raise SourceError(f"transport error fetching fantasypros/{dataset}: {e}") from e

        if resp.status_code == 404:
            raise SourceError(f"fantasypros/{dataset} not found (404): {url}")
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
        players = body.get("players", body) if isinstance(body, dict) else body
        rows = len(players) if isinstance(players, list) else 1
        columns = (
            tuple(sorted(players[0].keys())) if isinstance(players, list) and players else None
        )

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
