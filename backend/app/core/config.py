from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"), env_file_encoding="utf-8", extra="ignore"
    )

    # Application
    APP_NAME: str = "JalRakshak AI Backend"
    APP_ENV: str = "local"  # local, test, staging, production
    APP_SECRET: str = "dev-secret-change-in-production"
    LOG_LEVEL: str = "INFO"
    DEBUG: bool = True

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://jalrakshak:jalrakshak@localhost:5432/jalrakshak"
    DATABASE_SYNC_URL: str | None = "postgresql://jalrakshak:jalrakshak@localhost:5432/jalrakshak"
    POSTGRES_DB: str = "jalrakshak"
    POSTGRES_USER: str = "jalrakshak"
    POSTGRES_PASSWORD: str = "jalrakshak"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # Object Storage (MinIO / S3)
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_BUCKET: str = "jalrakshak"
    MINIO_SECURE: bool = False

    # Supabase Auth / OIDC
    SUPABASE_URL: str = "https://placeholder-project.supabase.co"
    SUPABASE_PUBLISHABLE_KEY: str = "placeholder-anon-key"
    SUPABASE_SECRET_KEY: str = "placeholder-service-key"
    SUPABASE_JWT_SECRET: str = "placeholder-jwt-secret"
    AUTH_MODE: str = "mock"  # "mock" for local dev/testing, "supabase" for JWT validation

    # Internal ML Service
    ML_SERVICE_URL: str = "http://localhost:8001"
    ML_SERVICE_TOKEN: str = "dev-ml-token"
    ML_PROVIDER: str = "stub"  # "stub" or "service"

    # Notifications & Routing
    NOTIFICATION_PROVIDER: str = "console"  # "console" or "expo"
    ROUTING_PROVIDER: str = "stub"  # "stub" or "service"

    # Observability & Tracing
    SENTRY_DSN: str | None = None
    PROMETHEUS_ENABLED: bool = True
    OTEL_SERVICE_NAME: str = "jalrakshak-backend"
    OTEL_EXPORTER_OTLP_ENDPOINT: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
