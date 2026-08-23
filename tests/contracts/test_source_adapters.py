"""Contract tests for source adapters, against a mocked httpx transport rather than the
network. These prove the adapter *logic* is correct (URL building, error classification,
snapshot bookkeeping) independent of real reachability, which is covered separately by
network-marked tests in tests/integration/test_sources_live.py."""

from __future__ import annotations

import io

import httpx
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from alpha_squad.config.settings import Settings
from alpha_squad.sources.base import (
    SourceBlockedError,
    SourceCredentialsError,
    SourceError,
    SourceNotFoundError,
)
from alpha_squad.sources.cfbd import CfbdSource
from alpha_squad.sources.dynastyprocess import DynastyProcessSource
from alpha_squad.sources.fantasypros import FantasyProsSource
from alpha_squad.sources.nflverse import NflverseSource
from alpha_squad.sources.registry import all_adapters
from alpha_squad.sources.sleeper import SleeperSource
from tests.fixtures.httpx_fakes import make_fake_get, make_fake_stream


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(data_dir=tmp_path / "data", db_path=tmp_path / "data" / "x.duckdb")


def _synthetic_parquet_bytes() -> bytes:
    df = pd.DataFrame({"gsis_id": ["00-001", "00-002"], "display_name": ["Player A", "Player B"]})
    buf = io.BytesIO()
    pq.write_table(pa.Table.from_pandas(df), buf)
    return buf.getvalue()


class TestAdapterRegistry:
    def test_every_adapter_has_a_unique_name_and_nonempty_datasets(self, settings):
        adapters = all_adapters(settings)
        names = [a.name for a in adapters]
        assert len(names) == len(set(names)), "adapter names must be unique"
        for adapter in adapters:
            datasets = adapter.list_datasets()
            assert datasets, f"{adapter.name} declares no datasets"
            for ds in datasets:
                # must not raise for any declared dataset
                adapter.default_health_params(ds)


class TestFileReleaseAdapterSuccess:
    def test_nflverse_fetch_success_writes_snapshot_and_parses_schema(self, settings, monkeypatch):
        content = _synthetic_parquet_bytes()
        monkeypatch.setattr(httpx, "stream", make_fake_stream(status_code=200, content=content))

        adapter = NflverseSource(settings)
        snap = adapter.fetch("players")

        assert snap.local_path.exists()
        assert snap.rows == 2
        assert snap.columns == ("gsis_id", "display_name")
        assert len(snap.sha256) == 64

    def test_dynastyprocess_csv_fetch_parses_rows_and_header(self, settings, monkeypatch):
        csv_bytes = b"mfl_id,name,position\n1,Player A,WR\n2,Player B,RB\n"
        monkeypatch.setattr(httpx, "stream", make_fake_stream(status_code=200, content=csv_bytes))

        adapter = DynastyProcessSource(settings)
        snap = adapter.fetch("player_ids")

        assert snap.rows == 2
        assert snap.columns == ("mfl_id", "name", "position")


class TestFileReleaseAdapterFailures:
    def test_policy_block_raises_source_blocked_error(self, settings, monkeypatch):
        monkeypatch.setattr(
            httpx, "stream", make_fake_stream(raise_exc=httpx.ProxyError("403 Forbidden"))
        )
        adapter = NflverseSource(settings)
        with pytest.raises(SourceBlockedError):
            adapter.fetch("players")

    def test_policy_block_leaves_no_partial_file(self, settings, monkeypatch):
        """The parent directory may still be created (mkdir happens before the request),
        but no snapshot *file* — partial or otherwise — may exist where a real one is
        expected, since that could be mistaken for real data by anything that lists the
        directory instead of querying the registry."""
        monkeypatch.setattr(
            httpx, "stream", make_fake_stream(raise_exc=httpx.ProxyError("403 Forbidden"))
        )
        adapter = NflverseSource(settings)
        with pytest.raises(SourceBlockedError):
            adapter.fetch("players")
        dataset_dir = settings.raw_dir / "nflverse" / "players"
        leftover_files = (
            [p for p in dataset_dir.rglob("*") if p.is_file()] if dataset_dir.exists() else []
        )
        assert leftover_files == [], f"policy block left files behind: {leftover_files}"

    def test_missing_season_raises_before_any_network_call(self, settings, monkeypatch):
        def boom(*a, **kw):
            raise AssertionError("must not attempt network call without required season param")

        monkeypatch.setattr(httpx, "stream", boom)
        adapter = NflverseSource(settings)
        with pytest.raises(SourceError):
            adapter.fetch("stats_player_week")

    def test_unpublished_season_is_not_found_not_fabricated(self, settings, monkeypatch):
        monkeypatch.setattr(httpx, "stream", make_fake_stream(status_code=404))
        adapter = NflverseSource(settings)
        with pytest.raises(SourceNotFoundError):
            adapter.fetch("stats_player_week", season=2099)


class TestJsonApiAdapters:
    def test_sleeper_policy_block(self, settings, monkeypatch):
        monkeypatch.setattr(
            httpx, "get", make_fake_get(raise_exc=httpx.ProxyError("403 Forbidden"))
        )
        adapter = SleeperSource(settings)
        with pytest.raises(SourceBlockedError):
            adapter.fetch("state")

    def test_sleeper_success_writes_json_snapshot(self, settings, monkeypatch):
        monkeypatch.setattr(
            httpx, "get", make_fake_get(status_code=200, json_body={"season": "2026", "week": 1})
        )
        adapter = SleeperSource(settings)
        snap = adapter.fetch("state")
        assert snap.rows == 1
        assert snap.columns == ("season", "week")
        assert snap.local_path.exists()

    def test_fantasypros_without_key_never_makes_network_call(self, settings, monkeypatch):
        def boom(*a, **kw):
            raise AssertionError("must not call network without a configured API key")

        monkeypatch.setattr(httpx, "get", boom)
        assert settings.fantasypros_api_key is None
        adapter = FantasyProsSource(settings)
        with pytest.raises(SourceCredentialsError):
            adapter.fetch("consensus_rankings", season=2026)

    def test_cfbd_without_key_never_makes_network_call(self, settings, monkeypatch):
        def boom(*a, **kw):
            raise AssertionError("must not call network without a configured API key")

        monkeypatch.setattr(httpx, "get", boom)
        assert settings.cfbd_api_key is None
        adapter = CfbdSource(settings)
        with pytest.raises(SourceCredentialsError):
            adapter.fetch("teams")

    def test_fantasypros_with_key_attempts_call_and_reports_block(self, settings, monkeypatch):
        settings = settings.model_copy(update={"fantasypros_api_key": "fake-key-for-test"})
        monkeypatch.setattr(
            httpx, "get", make_fake_get(raise_exc=httpx.ProxyError("403 Forbidden"))
        )
        adapter = FantasyProsSource(settings)
        with pytest.raises(SourceBlockedError):
            adapter.fetch("consensus_rankings", season=2026)


class TestHealthCheckNeverRaises:
    def test_health_translates_every_error_kind_without_raising(self, settings, monkeypatch):
        monkeypatch.setattr(
            httpx, "stream", make_fake_stream(raise_exc=httpx.ProxyError("403 Forbidden"))
        )
        adapter = NflverseSource(settings)
        results = adapter.health()
        assert results, "health() should report on every dataset"
        assert all(r.status.value == "BLOCKED_BY_POLICY" for r in results)
