"""Runtime configuration. Values come from environment variables / .env; see .env.example
for the full list. Never hardcode secrets here."""

from __future__ import annotations

from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # populate_by_name=True is required alongside validation_alias: without it, pydantic
    # only accepts the alias (e.g. ALPHA_SQUAD_DATA_DIR) as a constructor kwarg and
    # `extra="ignore"` silently swallows `Settings(data_dir=...)` instead of raising —
    # which means tests/callers passing the Python field name would be silently ignored
    # and fall back to defaults. Verified this bug during M1; regression-tested in
    # tests/unit/test_settings.py.
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", populate_by_name=True)

    data_dir: Path = Field(default=Path("data"), validation_alias="ALPHA_SQUAD_DATA_DIR")
    db_path: Path = Field(
        default=Path("data/alpha_squad.duckdb"), validation_alias="ALPHA_SQUAD_DB_PATH"
    )
    models_dir: Path = Field(default=Path("models"), validation_alias="ALPHA_SQUAD_MODELS_DIR")

    sleeper_base_url: str = Field(
        default="https://api.sleeper.app/v1", validation_alias="SLEEPER_BASE_URL"
    )
    fantasypros_api_key: str | None = Field(default=None, validation_alias="FANTASYPROS_API_KEY")
    cfbd_api_key: str | None = Field(default=None, validation_alias="CFBD_API_KEY")

    # Claude strategic decision layer (Stage 1, docs/DECISIONS.md D74). Absent key means the
    # feature is simply unavailable -- strategy/provider.py degrades to a clear "unavailable"
    # status rather than erroring, the same discipline fantasypros/cfbd already follow above.
    # ALPHA_SQUAD_ANTHROPIC_API_KEY takes priority over ANTHROPIC_API_KEY (D77): Claude Code on
    # the Web reserves the ANTHROPIC_API_KEY/ANTHROPIC_AUTH_TOKEN names for its own subscription
    # auth and never exposes them to a cloud session's process environment, so a value set under
    # that name in a Claude Code cloud environment never reaches this app. ANTHROPIC_API_KEY is
    # kept as a fallback for local/non-Claude-Code deployments where the name isn't reserved.
    anthropic_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("ALPHA_SQUAD_ANTHROPIC_API_KEY", "ANTHROPIC_API_KEY"),
    )
    anthropic_model: str = Field(default="claude-opus-5", validation_alias="ANTHROPIC_MODEL")
    anthropic_timeout_seconds: float = Field(
        default=20.0, validation_alias="ANTHROPIC_TIMEOUT_SECONDS"
    )

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def features_dir(self) -> Path:
        return self.data_dir / "features"

    @property
    def processed_dir(self) -> Path:
        return self.data_dir / "processed"


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
