"""
Application configuration (12-factor).

Every setting can be overridden by an environment variable with the same name in upper case,
or by a `.env` file in the working directory. See `.env.example` for the full reference.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEFAULT_APP_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- Application ---------------------------------------------------------
    app_name: str = "logistics-agent-tower"
    env: Literal["development", "staging", "production", "test"] = "development"
    log_level: str = "INFO"
    project_root: Path = Field(default=_DEFAULT_APP_ROOT)

    # --- Database ------------------------------------------------------------
    # Empty -> SQLite file under <project_root>/data. Any SQLAlchemy URL is accepted
    # (e.g. postgresql+psycopg://user:pass@host:5432/db).
    database_url: str | None = None

    # --- LLM providers (reserved for LLM-backed agent nodes) -----------------
    llm_provider: Literal["ollama", "gemini", "openai"] = "ollama"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:7b"
    google_api_key: SecretStr | None = None
    gemini_model: str = "gemini-2.0-flash"
    openai_api_key: SecretStr | None = None
    openai_model: str = "gpt-4o-mini"

    # --- Google Cloud / Maps -------------------------------------------------
    gcp_project_id: str = "my-logistics-gcp-project"
    gcp_region: str = "southamerica-east1"
    google_maps_api_key: SecretStr | None = None
    google_maps_cache_ttl_seconds: int = 300

    # --- Distribution center (CD Itajaí - SC) --------------------------------
    default_cd_id: str = "CD-ITAJAI-SC01"
    cd_name: str = "Centro de Distribuição Itajaí - SC"
    cd_address: str = (
        "Rod. Antônio Heil (ao lado da Rua Anair de Souza) - Rio do Meio / Itaipava, Itajaí - SC, 88316-060"
    )
    cd_lat: float = -26.9418
    cd_lng: float = -48.7094

    # --- Capacity thresholds audited by the Risk Agent -----------------------
    max_weight_threshold_percent: float = 100.0
    max_volume_threshold_percent: float = 100.0

    # --- Operational constraints (one multi-stop route per vehicle per day) --
    max_stops_per_vehicle: int = 12  # deliveries per route
    loading_time_minutes: int = 60  # dock loading at the CD before departure
    unloading_time_minutes: int = 20  # service time at each customer
    dock_start_time: str = "05:00"  # loading starts at 05:00, departure at 06:00
    lunch_break_minutes: int = 60  # mandatory intra-shift break (Lei 13.103/2015)
    lunch_earliest_time: str = "11:30"  # break is taken at the first stop completed after this time
    max_shift_hours: float = 11.0  # legal daily driving shift
    urban_speed_kmh: float = 32.0  # fallback average speed when Google Maps is not configured
    road_circuity_factor: float = 1.35  # haversine -> road distance multiplier

    # --- Human-in-the-Loop gate ----------------------------------------------
    hitl_auto_approve: bool = False

    # --- API server ----------------------------------------------------------
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # --- Derived paths -------------------------------------------------------
    @property
    def data_dir(self) -> Path:
        return self.project_root / "data"

    @property
    def sqlite_path(self) -> Path:
        return self.data_dir / "logistics.db"

    @property
    def resolved_database_url(self) -> str:
        """SQLAlchemy URL actually used by the engine (explicit URL or local SQLite)."""
        if self.database_url:
            return self.database_url
        return f"sqlite:///{self.sqlite_path.as_posix()}"

    @property
    def orders_path(self) -> Path:
        return self.data_dir / "samples" / "orders.json"

    @property
    def fleet_path(self) -> Path:
        return self.data_dir / "samples" / "fleet.json"

    @property
    def customer_rules_path(self) -> Path:
        return self.data_dir / "samples" / "customer_rules.json"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
