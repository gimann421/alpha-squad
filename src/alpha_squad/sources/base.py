"""Shared interface every data-source adapter implements.

Design rule (CLAUDE.md / ARCHITECTURE.md §12): a fetch either returns a RawSnapshot backed by
an immutable file actually written to disk, or raises a SourceError subclass. Nothing in this
module is allowed to return empty-but-successful data to paper over a failure, and nothing may
report AVAILABLE without a real snapshot on disk to point to.
"""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from uuid import uuid4


class SourceStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    BLOCKED_BY_POLICY = "BLOCKED_BY_POLICY"
    NO_CREDENTIALS = "NO_CREDENTIALS"
    NOT_FOUND = "NOT_FOUND"
    ERROR = "ERROR"


class SourceError(RuntimeError):
    """Base class for source adapter failures. Carries a SourceStatus so callers can
    distinguish 'this dataset does not exist' from 'we are not allowed to reach this host'
    from 'something actually broke'."""

    status: SourceStatus = SourceStatus.ERROR


class SourceBlockedError(SourceError):
    """The environment's egress policy denied the connection (proxy-level 403 on CONNECT,
    or an HTTP 403 from the origin). Not a credentials problem — retrying with a key will
    not help. See docs/DATA_SOURCES.md."""

    status = SourceStatus.BLOCKED_BY_POLICY


class SourceCredentialsError(SourceError):
    """A paid/licensed source has no configured credentials. Per lead-prompt §8, obtaining
    such credentials requires explicit user authorization — this adapter must never invent
    or guess a key."""

    status = SourceStatus.NO_CREDENTIALS


class SourceNotFoundError(SourceError):
    """The requested dataset/season genuinely does not exist upstream (e.g. a season that
    hasn't been published yet). Distinct from a policy block or transient error."""

    status = SourceStatus.NOT_FOUND


def utcnow() -> datetime:
    return datetime.now(UTC)


def write_bytes_atomic(dest: Path, content: bytes) -> None:
    """Write `content` to `dest` via a same-directory temp file + `Path.replace()` (atomic
    rename on the same filesystem), instead of `dest.write_bytes()`. `write_bytes()` opens
    in truncate mode: two concurrent fetches for the *same* (dataset, params) snapshot key
    -- a real case here, since two league_ids can point at the same underlying real Sleeper
    league -- can interleave a truncate from one write with a read from the other, producing
    a torn (partial/empty) file. Found live via Playwright as a `JSONDecodeError` reading a
    snapshot mid-write under real concurrent app traffic; `sources/http.py`'s
    `http_get_to_file` already used this pattern, this closes the same gap in the three
    adapters (sleeper/cfbd/fantasypros) that instead wrote in place."""
    tmp_dest = dest.with_name(f"{dest.name}.{uuid4().hex}.part")
    tmp_dest.write_bytes(content)
    tmp_dest.replace(dest)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass(frozen=True)
class SourceHealth:
    source: str
    dataset: str
    status: SourceStatus
    checked_at: datetime
    detail: str = ""


@dataclass(frozen=True)
class RawSnapshot:
    """An immutable, on-disk capture of one dataset fetch. `local_path` must exist and its
    content must hash to `sha256` — this is what identity/feature code reads, never a live
    re-fetch, so historical runs stay reproducible."""

    source: str
    dataset: str
    captured_at: datetime
    url: str
    local_path: Path
    sha256: str
    rows: int | None
    columns: tuple[str, ...] | None
    params: tuple[tuple[str, str], ...] = ()

    @property
    def snapshot_id(self) -> str:
        param_str = "&".join(f"{k}={v}" for k, v in self.params)
        return (
            f"{self.source}/{self.dataset}/{param_str or 'default'}@{self.captured_at.isoformat()}"
        )


class SourceAdapter(ABC):
    """One adapter per external data provider. `name` must be stable — it's used as a
    partition key in the snapshot registry and on-disk layout."""

    name: str

    @abstractmethod
    def list_datasets(self) -> list[str]:
        """Dataset keys this adapter knows how to fetch, independent of whether they are
        currently reachable."""

    @abstractmethod
    def fetch(self, dataset: str, *, captured_at: datetime | None = None, **params) -> RawSnapshot:
        """Fetch one dataset and persist it as an immutable snapshot. Raises a SourceError
        subclass on any failure; never returns a snapshot for data that wasn't actually
        written to disk."""

    def default_health_params(self, dataset: str) -> dict:
        """Cheapest params that produce a valid fetch for a health check (e.g. the most
        recent season). Override when a dataset requires one."""
        return {}

    def health(self, dataset: str | None = None) -> list[SourceHealth]:
        datasets = [dataset] if dataset else self.list_datasets()
        results: list[SourceHealth] = []
        for ds in datasets:
            try:
                snap = self.fetch(ds, **self.default_health_params(ds))
                detail = f"{snap.rows} rows, {len(snap.columns or ())} columns"
                results.append(
                    SourceHealth(self.name, ds, SourceStatus.AVAILABLE, utcnow(), detail)
                )
            except SourceError as e:
                results.append(SourceHealth(self.name, ds, e.status, utcnow(), str(e)))
            except Exception as e:  # noqa: BLE001 - health checks must never raise
                results.append(SourceHealth(self.name, ds, SourceStatus.ERROR, utcnow(), repr(e)))
        return results
