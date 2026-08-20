"""Base adapter for sources that publish whole immutable files (parquet/CSV) at a
predictable URL — nflverse, DynastyProcess, cfbfastR, ffopportunity all fit this shape."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import httpx
import pyarrow.parquet as pq

from alpha_squad.config.settings import Settings, get_settings
from alpha_squad.sources.base import (
    RawSnapshot,
    SourceAdapter,
    SourceBlockedError,
    SourceError,
    sha256_file,
    utcnow,
)
from alpha_squad.sources.http import http_get_to_file


@dataclass(frozen=True)
class DatasetSpec:
    key: str
    url_template: str  # may reference e.g. {season}
    file_format: str  # "parquet" | "csv"
    requires_season: bool = False
    default_health_season: int | None = None


class FileReleaseSourceAdapter(SourceAdapter):
    datasets: dict[str, DatasetSpec] = {}

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()

    def list_datasets(self) -> list[str]:
        return list(self.datasets.keys())

    def default_health_params(self, dataset: str) -> dict:
        spec = self.datasets[dataset]
        if spec.requires_season and spec.default_health_season is not None:
            return {"season": spec.default_health_season}
        return {}

    def fetch(self, dataset: str, *, captured_at: datetime | None = None, **params) -> RawSnapshot:
        if dataset not in self.datasets:
            raise SourceError(f"unknown dataset '{dataset}' for source '{self.name}'")
        spec = self.datasets[dataset]
        if spec.requires_season and "season" not in params:
            raise SourceError(f"dataset '{dataset}' requires a 'season' parameter")

        url = spec.url_template.format(**params)
        captured_at = captured_at or utcnow()
        param_suffix = "_".join(f"{k}-{v}" for k, v in sorted(params.items())) or "default"
        filename = url.rsplit("/", 1)[-1]
        dest = (
            self.settings.raw_dir
            / self.name
            / dataset
            / f"captured_at={captured_at.date().isoformat()}"
            / f"{param_suffix}_{filename}"
        )

        try:
            http_get_to_file(url, dest)
        except httpx.ProxyError as e:
            raise SourceBlockedError(f"egress policy blocked {self.name}/{dataset}: {e}") from e

        rows, columns = _inspect_file(dest, spec.file_format)
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


def _inspect_file(path: Path, file_format: str) -> tuple[int | None, tuple[str, ...] | None]:
    if file_format == "parquet":
        pf = pq.ParquetFile(path)
        return pf.metadata.num_rows, tuple(pf.schema_arrow.names)
    if file_format == "csv":
        with path.open(newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            header = next(reader, [])
            row_count = sum(1 for _ in reader)
        return row_count, tuple(header)
    raise SourceError(f"unsupported file_format '{file_format}'")
