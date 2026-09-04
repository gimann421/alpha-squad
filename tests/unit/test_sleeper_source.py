"""Failure-mode coverage for `sources/sleeper.py::SleeperSource.fetch` (2026-09-04 hardening
pass, Phase 6). A live draft polls this every 8s -- every real Sleeper failure mode must
surface as a `SourceError` (which the API layer already translates into a graceful 503), not
propagate as a raw, uncaught httpx/json exception that the router's `except SourceError` /
`except RuntimeError` handlers cannot catch and that FastAPI would turn into an unhandled 500."""

from __future__ import annotations

import httpx
import pytest

from alpha_squad.config.settings import Settings
from alpha_squad.sources.base import SourceBlockedError, SourceError
from alpha_squad.sources.sleeper import SleeperSource


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(data_dir=tmp_path / "data", db_path=tmp_path / "data" / "x.duckdb")


class _FakeResponse:
    def __init__(self, status_code: int, content: bytes):
        self.status_code = status_code
        self.content = content

    def json(self):
        import json

        return json.loads(self.content)

    def raise_for_status(self):
        if self.status_code >= 400:
            request = httpx.Request("GET", "https://api.sleeper.app/v1/state/nfl")
            response = httpx.Response(self.status_code, request=request, content=self.content)
            raise httpx.HTTPStatusError(
                f"HTTP {self.status_code}", request=request, response=response
            )


class TestFetchFailureModes:
    def test_a_transient_5xx_raises_source_error_not_a_raw_httpx_exception(
        self, settings, monkeypatch
    ):
        """REGRESSION: previously an uncaught httpx.HTTPStatusError, invisible to every
        `except SourceError`/`except RuntimeError` handler in api/routers/league.py."""
        monkeypatch.setattr(httpx, "get", lambda url, **kw: _FakeResponse(503, b"upstream down"))
        with pytest.raises(SourceError):
            SleeperSource(settings).fetch("state")

    def test_a_429_raises_source_error(self, settings, monkeypatch):
        monkeypatch.setattr(httpx, "get", lambda url, **kw: _FakeResponse(429, b"rate limited"))
        with pytest.raises(SourceError):
            SleeperSource(settings).fetch("state")

    def test_a_malformed_200_body_raises_source_error_not_a_raw_json_error(
        self, settings, monkeypatch
    ):
        """REGRESSION: previously an uncaught json.JSONDecodeError from `resp.json()`."""
        monkeypatch.setattr(
            httpx, "get", lambda url, **kw: _FakeResponse(200, b"<html>maintenance</html>")
        )
        with pytest.raises(SourceError):
            SleeperSource(settings).fetch("state")

    def test_a_connect_timeout_raises_source_error(self, settings, monkeypatch):
        def raise_timeout(url, **kw):
            raise httpx.ConnectTimeout("timed out")

        monkeypatch.setattr(httpx, "get", raise_timeout)
        with pytest.raises(SourceError):
            SleeperSource(settings).fetch("state")

    def test_a_policy_blocked_host_raises_source_blocked_error(self, settings, monkeypatch):
        def raise_blocked(url, **kw):
            raise httpx.ProxyError("blocked")

        monkeypatch.setattr(httpx, "get", raise_blocked)
        with pytest.raises(SourceBlockedError):
            SleeperSource(settings).fetch("state")

    def test_a_genuine_404_raises_source_error(self, settings, monkeypatch):
        monkeypatch.setattr(httpx, "get", lambda url, **kw: _FakeResponse(404, b"not found"))
        with pytest.raises(SourceError):
            SleeperSource(settings).fetch("state")

    def test_a_healthy_response_still_parses_normally(self, settings, monkeypatch):
        monkeypatch.setattr(
            httpx, "get", lambda url, **kw: _FakeResponse(200, b'{"season": "2025"}')
        )
        snap = SleeperSource(settings).fetch("state")
        assert snap.rows == 1
