"""
Configuration module for the Logistics Control Tower (12-factor).
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal, Optional

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEFAULT_APP_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "logistics-agent-tower"
    env: str = "development"
    log_level: str = "INFO"

    # Paths
    project_root: Path = Field(default=_DEFAULT_APP_ROOT)

    # LLM Providers (ollama | gemini | openai)
    llm_provider: Literal["ollama", "gemini", "openai"] = "ollama"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:7b"

    google_api_key: Optional[SecretStr] = None
    gcp_project_id: str = "my-logistics-gcp-project"
    gcp_region: str = "southamerica-east1"
    gemini_model: str = "gemini-2.0-flash"

    openai_api_key: Optional[SecretStr] = None
    openai_model: str = "gpt-4o-mini"

    # Logistics & Distribution Center Operations (CD Itajaí - SC)
    default_cd_id: str = "CD-ITAJAI-SC01"
    cd_name: str = "Centro de Distribuição Itajaí - SC"
    cd_address: str = "Rod. Antônio Heil, 1001 - KM 1 - Itaipava, Itajaí - SC, 88316-001"
    cd_lat: float = -26.9315
    cd_lng: float = -48.7010

    max_weight_threshold_percent: float = 90.0
    max_volume_threshold_percent: float = 90.0

    # Human-in-the-Loop Gate
    hitl_auto_approve: bool = False

    # Serving & API
    api_port: int = 8000
    api_host: str = "0.0.0.0"

    @property
    def orders_path(self) -> Path:
        return self.project_root / "data" / "samples" / "orders.json"

    @property
    def fleet_path(self) -> Path:
        return self.project_root / "data" / "samples" / "fleet.json"

    @property
    def customer_rules_path(self) -> Path:
        return self.project_root / "data" / "samples" / "customer_rules.json"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
