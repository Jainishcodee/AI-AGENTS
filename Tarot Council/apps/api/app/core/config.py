"""Runtime configuration.

Model routing is by *role*, never by name at the call site (ADR-005). Three roles
exist and each maps to one `provider:model` string, so the whole cost model of the
product is three environment variables.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Depth = Literal["quick", "standard", "deep"]
Role = Literal["intake", "reasoning", "synthesis"]

REPO_MARKERS = (".env", "docs")


def _find_env_file() -> Path | None:
    """Walk upward looking for the repo-root .env.

    The API lives at apps/api/, the .env at the repo root, and the process may be
    launched from either. Walking up is more robust than a relative path.
    """
    for parent in Path(__file__).resolve().parents:
        candidate = parent / ".env"
        if candidate.is_file():
            return candidate
    return None


class ModelRoute(BaseModel):
    """A parsed `provider:model` pair."""

    model_config = ConfigDict(frozen=True)

    provider: str
    name: str

    @classmethod
    def parse(cls, raw: str) -> "ModelRoute":
        if ":" not in raw:
            raise ValueError(
                f"model route {raw!r} must be '<provider>:<model>' "
                "(e.g. gemini:gemini-2.5-flash)"
            )
        provider, _, name = raw.partition(":")
        provider, name = provider.strip().lower(), name.strip()
        if not provider or not name:
            raise ValueError(f"model route {raw!r} has an empty provider or model")
        return cls(provider=provider, name=name)

    def __str__(self) -> str:  # pragma: no cover - display only
        return f"{self.provider}:{self.name}"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_find_env_file(),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        protected_namespaces=(),
    )

    # ------------------------------------------------------------- providers --
    gemini_api_key: str | None = Field(default=None, validation_alias="GEMINI_API_KEY")
    openrouter_api_key: str | None = Field(
        default=None, validation_alias="OPENROUTER_API_KEY"
    )
    anthropic_api_key: str | None = Field(
        default=None, validation_alias="ANTHROPIC_API_KEY"
    )
    openai_api_key: str | None = Field(default=None, validation_alias="OPENAI_API_KEY")
    ollama_host: str = Field(
        default="http://127.0.0.1:11434", validation_alias="OLLAMA_HOST"
    )

    # --------------------------------------------------------------- routing --
    route_intake: str = Field(
        default="gemini:gemini-2.5-flash-lite", validation_alias="COUNCIL_MODEL_INTAKE"
    )
    route_reasoning: str = Field(
        default="gemini:gemini-2.5-flash", validation_alias="COUNCIL_MODEL_REASONING"
    )
    route_synthesis: str = Field(
        default="gemini:gemini-2.5-flash", validation_alias="COUNCIL_MODEL_SYNTHESIS"
    )
    route_fallback: str | None = Field(
        default=None, validation_alias="COUNCIL_MODEL_FALLBACK"
    )

    # ---------------------------------------------------------------- limits --
    max_concurrency: int = Field(default=3, ge=1, le=32, validation_alias="COUNCIL_MAX_CONCURRENCY")
    max_rpm: int = Field(
        default=8, ge=0, le=10_000, validation_alias="COUNCIL_MAX_RPM"
    )
    """Requests per minute, across all providers. 0 disables pacing.

    This, not concurrency, is what free tiers actually meter."""
    request_timeout_s: float = Field(
        default=120.0, gt=0, validation_alias="COUNCIL_REQUEST_TIMEOUT_S"
    )
    max_retries: int = Field(default=3, ge=0, le=8, validation_alias="COUNCIL_MAX_RETRIES")
    default_depth: Depth = Field(default="standard", validation_alias="COUNCIL_DEFAULT_DEPTH")
    default_preset: str = Field(default="full", validation_alias="COUNCIL_DEFAULT_PRESET")

    # ---------------------------------------------------------------- server --
    cors_origins_raw: str = Field(
        default="http://localhost:3000,http://127.0.0.1:3000",
        validation_alias="COUNCIL_CORS_ORIGINS",
    )
    log_level: str = Field(default="INFO", validation_alias="COUNCIL_LOG_LEVEL")
    store: Literal["memory", "file"] = Field(default="file", validation_alias="COUNCIL_STORE")
    store_dir: Path = Field(
        default=Path(__file__).resolve().parents[2] / "var",
        validation_alias="COUNCIL_STORE_DIR",
    )

    @field_validator("log_level")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.upper()

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.cors_origins_raw.split(",") if o.strip()]

    def route(self, role: Role) -> ModelRoute:
        raw = {
            "intake": self.route_intake,
            "reasoning": self.route_reasoning,
            "synthesis": self.route_synthesis,
        }[role]
        return ModelRoute.parse(raw)

    @property
    def fallback_route(self) -> ModelRoute | None:
        return ModelRoute.parse(self.route_fallback) if self.route_fallback else None

    def has_credentials_for(self, provider: str) -> bool:
        return {
            "gemini": bool(self.gemini_api_key),
            "openrouter": bool(self.openrouter_api_key),
            "anthropic": bool(self.anthropic_api_key),
            "openai": bool(self.openai_api_key),
            "ollama": True,
            "mock": True,
        }.get(provider, False)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
