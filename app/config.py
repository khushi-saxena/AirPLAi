from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    # Defaults to a zero-setup SQLite file so the project runs out of the box.
    # In production this is set to a Postgres URL (docker-compose / Render).
    database_url: str = "sqlite:///./gameday.db"


def _normalize(url: str) -> str:
    # Managed Postgres providers (Render, Heroku) hand out 'postgres://' or
    # 'postgresql://' URLs. SQLAlchemy needs an explicit driver; we use
    # psycopg v3, so normalize the scheme to 'postgresql+psycopg://'.
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


settings = Settings()
DATABASE_URL = _normalize(settings.database_url)


def is_postgres() -> bool:
    return DATABASE_URL.startswith("postgresql")
