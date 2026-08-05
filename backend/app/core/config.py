from pathlib import Path
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "Hedge Fund API"
    app_env: str = "development"
    debug: bool = True

    api_host: str = "0.0.0.0"
    api_port: int = 8000

    cors_origins: str = "http://localhost:3000"

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/hedge_fund"
    hf_supabase_database_url: str | None = None

    @field_validator("debug", mode="before")
    @classmethod
    def parse_debug(cls, value: object) -> object:
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"release", "production", "prod"}:
                return False
            if normalized in {"debug", "development", "dev"}:
                return True

        return value

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def sqlalchemy_database_url(self) -> str:
        database_url = self.hf_supabase_database_url or self.database_url
        database_url = self._encode_postgres_password(database_url)

        if database_url.startswith("postgresql+asyncpg://"):
            return self._with_pooler_options(database_url)

        if database_url.startswith("postgresql://"):
            return self._with_pooler_options(
                database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
            )

        if database_url.startswith("postgres://"):
            return self._with_pooler_options(
                database_url.replace("postgres://", "postgresql+asyncpg://", 1)
            )

        return database_url

    @staticmethod
    def _encode_postgres_password(database_url: str) -> str:
        if "://" not in database_url or "@" not in database_url:
            return database_url

        scheme, remainder = database_url.split("://", 1)
        credentials, host_and_path = remainder.rsplit("@", 1)

        if ":" not in credentials:
            return database_url

        username, password = credentials.split(":", 1)
        encoded_password = quote(password, safe="")
        return f"{scheme}://{username}:{encoded_password}@{host_and_path}"

    @staticmethod
    def _with_pooler_options(database_url: str) -> str:
        parsed = urlsplit(database_url)
        if not Settings._uses_pooler_host(parsed.hostname):
            return database_url

        query_params = dict(parse_qsl(parsed.query, keep_blank_values=True))
        query_params.setdefault("prepared_statement_cache_size", "0")

        return urlunsplit(
            (
                parsed.scheme,
                parsed.netloc,
                parsed.path,
                urlencode(query_params),
                parsed.fragment,
            )
        )

    @property
    def uses_database_pooler(self) -> bool:
        return self._uses_pooler_host(urlsplit(self.sqlalchemy_database_url).hostname)

    @staticmethod
    def _uses_pooler_host(hostname: str | None) -> bool:
        return hostname is not None and "pooler.supabase.com" in hostname


settings = Settings()
