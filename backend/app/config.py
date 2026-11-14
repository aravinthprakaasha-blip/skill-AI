"""Central configuration. Every secret and integration endpoint comes from the environment."""
from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(BACKEND_DIR / ".env", ".env"), env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    # PostgreSQL 16 + pgvector in production; SQLite is the zero-dependency dev fallback.
    database_url: str = f"sqlite:///{(BACKEND_DIR / 'skillforge.db').as_posix()}"
    cors_origins: str = "http://localhost:3000"
    # Optional regex for extra allowed origins, e.g. your own Vercel preview URLs:
    #   ^https://skillai(-[a-z0-9-]+)?-yourteam-projects\.vercel\.app$
    cors_origin_regex: str = ""

    # Auth. If SUPABASE_JWT_SECRET is set, Supabase-issued tokens are accepted as well.
    jwt_secret: str = "dev-only-change-me"
    jwt_expire_minutes: int = 60 * 24
    supabase_jwt_secret: str = ""
    supabase_url: str = ""  # e.g. https://abcd.supabase.co - enables the new asymmetric JWT keys (JWKS)

    # Gemini (optional). Without a key every AI step uses a labelled deterministic fallback.
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    gemini_embedding_model: str = "gemini-embedding-001"
    embedding_dim: int = 768

    # Code execution. Judge0 is the isolated sandbox; the local runner is a dev-only fallback.
    judge0_url: str = ""
    judge0_api_key: str = ""
    # The local subprocess runner is NOT a security sandbox. Defaults to on in development only.
    allow_local_runner: bool | None = None
    exec_time_limit_s: float = 5.0
    exec_memory_limit_kb: int = 256_000

    # Background jobs. With REDIS_URL set, workflows run on an RQ worker.
    redis_url: str = ""

    github_enrichment: bool = False
    seed_demo_data: bool = True

    @field_validator("*", mode="before")
    @classmethod
    def _strip_whitespace(cls, v):
        # Values pasted into hosting dashboards often carry a trailing space or newline, which
        # makes HTTP headers (API keys) and URLs invalid. Strip them everywhere.
        return v.strip() if isinstance(v, str) else v

    @property
    def is_postgres(self) -> bool:
        return self.database_url.startswith(("postgresql", "postgres://"))

    @property
    def cors_list(self) -> list[str]:
        # Browsers send origins without a trailing slash, so tolerate "https://site.app/" in config.
        return [o.strip().rstrip("/") for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    if s.allow_local_runner is None:
        s.allow_local_runner = s.app_env != "production"
    return s
