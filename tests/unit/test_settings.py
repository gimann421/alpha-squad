"""Regression coverage for a real M1 bug: Settings fields use `validation_alias` (so env
vars can use the ALPHA_SQUAD_/SLEEPER_/etc. names in .env.example) but without
`populate_by_name=True`, pydantic silently ignored Python-name kwargs like
`Settings(data_dir=...)` and fell back to defaults — with `extra="ignore"` swallowing what
would otherwise be a loud ValidationError. Test fixtures across the suite construct Settings
with explicit kwargs to isolate I/O to tmp_path; this bug meant those fixtures were silently
writing into the real repo data/ directory instead."""

from pathlib import Path

from alpha_squad.config.settings import Settings


def test_settings_accepts_python_field_name_kwargs(tmp_path):
    s = Settings(data_dir=tmp_path / "data", db_path=tmp_path / "data" / "x.duckdb")
    assert s.data_dir == tmp_path / "data"
    assert s.db_path == tmp_path / "data" / "x.duckdb"


def test_settings_still_accepts_env_alias_kwargs(tmp_path):
    s = Settings(ALPHA_SQUAD_DATA_DIR=tmp_path / "data")
    assert s.data_dir == tmp_path / "data"


def test_settings_defaults_are_relative_paths_under_data():
    s = Settings(_env_file=None)
    assert s.data_dir == Path("data")
    assert s.raw_dir == Path("data") / "raw"
