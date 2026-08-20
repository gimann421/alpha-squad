"""Shared HTTP fetch-to-file helper used by every file-based adapter (nflverse,
DynastyProcess, cfbfastR, ffopportunity).

Error classification below is based on empirical testing against this environment's egress
proxy, not assumption:
- A policy-blocked host raises `httpx.ProxyError('403 Forbidden')` directly from
  `httpx.get`/`httpx.stream` (the proxy refuses the CONNECT tunnel before any request
  reaches the origin). We translate that into SourceBlockedError.
- A dataset that genuinely doesn't exist upstream (e.g. an unpublished season) returns a
  normal HTTP 404 response from the origin, not an exception. We translate that into
  SourceNotFoundError.
- Anything else transient (429/5xx, connect timeouts) is retried with backoff.
"""

from __future__ import annotations

import time
from pathlib import Path

import httpx

from alpha_squad.sources.base import SourceError, SourceNotFoundError

TRANSIENT_STATUS = {429, 500, 502, 503, 504}
DEFAULT_TIMEOUT = 120.0
DEFAULT_MAX_RETRIES = 3


def http_get_to_file(
    url: str,
    dest: Path,
    *,
    timeout: float = DEFAULT_TIMEOUT,
    max_retries: int = DEFAULT_MAX_RETRIES,
    headers: dict[str, str] | None = None,
) -> None:
    """Fetch `url` and stream it to `dest`, retrying transient failures only. Raises a
    SourceError subclass (never returns) on any non-retryable outcome. Writes to a temp
    path first and renames on success so a failed fetch never leaves a partial file where a
    snapshot is expected."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp_dest = dest.with_suffix(dest.suffix + ".part")
    last_error: str = ""

    for attempt in range(1, max_retries + 1):
        try:
            with httpx.stream(
                "GET", url, follow_redirects=True, timeout=timeout, headers=headers
            ) as resp:
                if resp.status_code == 404:
                    raise SourceNotFoundError(f"dataset not found (404): {url}")
                if resp.status_code in TRANSIENT_STATUS:
                    last_error = f"HTTP {resp.status_code} from {url}"
                    if attempt < max_retries:
                        time.sleep(2**attempt)
                        continue
                    raise SourceError(f"{last_error} after {max_retries} attempts")
                resp.raise_for_status()
                with tmp_dest.open("wb") as f:
                    for chunk in resp.iter_bytes():
                        f.write(chunk)
            tmp_dest.replace(dest)
            return
        except SourceError:
            tmp_dest.unlink(missing_ok=True)
            raise
        except httpx.ProxyError:
            # Confirmed empirically: egress-policy denial surfaces here, not as an HTTP
            # response. Left unwrapped so the caller (FileReleaseSourceAdapter.fetch) can
            # translate it into SourceBlockedError with dataset-specific context.
            tmp_dest.unlink(missing_ok=True)
            raise
        except httpx.HTTPStatusError as e:
            tmp_dest.unlink(missing_ok=True)
            raise SourceError(f"HTTP error fetching {url}: {e}") from e
        except httpx.TransportError as e:
            last_error = str(e)
            if attempt < max_retries:
                time.sleep(2**attempt)
                continue
            tmp_dest.unlink(missing_ok=True)
            raise SourceError(
                f"transport error fetching {url} after {max_retries} attempts: {e}"
            ) from e

    tmp_dest.unlink(missing_ok=True)
    raise SourceError(f"failed fetching {url} after {max_retries} attempts: {last_error}")
