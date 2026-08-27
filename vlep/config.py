"""
VLEP Pipeline — Application Configuration.

Uses pydantic-settings to load from environment variables / .env file.
All sensitive values must be provided via environment; defaults are
development-safe stubs only.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolve project root relative to this file
_PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Central configuration for every VLEP subsystem."""

    model_config = SettingsConfigDict(
        env_file=str(_PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Database ────────────────────────────────────────────────────────────
    database_url: str = (
        "postgresql+asyncpg://vlep:vlep_secure_dev@localhost:5432/vlep_db"
    )
    database_url_sync: str = (
        "postgresql+psycopg2://vlep:vlep_secure_dev@localhost:5432/vlep_db"
    )
    db_echo: bool = False
    db_pool_size: int = 10
    db_max_overflow: int = 20

    # ── Redis / Celery ──────────────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"

    # ── Neo4j (optional) ────────────────────────────────────────────────────
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "vlep_neo4j_dev"

    # ── API ──────────────────────────────────────────────────────────────────
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_debug: bool = True
    api_title: str = "VLEP Pipeline API"
    api_version: str = "0.1.0"

    # ── Security / OIDC ─────────────────────────────────────────────────────
    oidc_issuer_url: str = "https://accounts.example.com"
    oidc_client_id: str = "vlep-dev-client"
    oidc_audience: str = "vlep-api"

    # ── NLP ──────────────────────────────────────────────────────────────────
    nlp_model_name: str = "emilyalsentzer/Bio_ClinicalBERT"
    nlp_device: str = "cpu"
    nlp_batch_size: int = 32

    # ── Logging ─────────────────────────────────────────────────────────────
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_format: Literal["json", "console"] = "json"

    # ── Governance ──────────────────────────────────────────────────────────
    governance_strict_mode: bool = True
    audit_log_enabled: bool = True

    # ── Paths ───────────────────────────────────────────────────────────────
    @property
    def project_root(self) -> Path:
        return _PROJECT_ROOT

    @property
    def migrations_dir(self) -> Path:
        return _PROJECT_ROOT / "migrations" / "up"

    @property
    def data_dir(self) -> Path:
        return _PROJECT_ROOT / "data"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached singleton of the application settings."""
    return Settings()
