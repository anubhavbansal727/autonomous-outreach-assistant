"""config.py — all settings/secrets for the app, in one place.

In plain English:
- ``Settings`` reads configuration from environment variables (or a local
  ``.env`` file) ONCE at startup: API keys, the database URL, the Redis URL,
  JWT secret, CORS origins, etc.
- Every other file imports the single shared ``settings`` object at the bottom
  instead of reading os.environ directly. Change a value in one place.
- The two ``@field_validator`` / ``@property`` helpers just clean up messy
  input (e.g. fix the database URL scheme, split CORS origins on commas).
"""

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # LLM
    OPENAI_API_KEY: str = ""

    # Search
    SERPER_API_KEY: str = ""

    # Email
    RESEND_API_KEY: str = ""

    # Database
    # Railway's Postgres plugin provides postgresql:// or postgres:// — both are
    # normalised to postgresql+asyncpg:// so every consumer gets the async driver.
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost/crm"

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def normalise_db_url(cls, v: str) -> str:
        """Ensure the asyncpg driver is always used regardless of how the URL arrives."""
        if v.startswith("postgres://"):
            return v.replace("postgres://", "postgresql+asyncpg://", 1)
        if v.startswith("postgresql://"):
            return v.replace("postgresql://", "postgresql+asyncpg://", 1)
        return v

    # Redis / ARQ
    REDIS_URL: str = "redis://localhost:6379"

    # JWT
    JWT_SECRET_KEY: str = ""
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # LangSmith / observability
    LANGCHAIN_API_KEY: str = ""
    LANGCHAIN_TRACING_V2: bool = False
    LANGCHAIN_PROJECT: str = "mini-crm-ai-crew"

    # Dev / demo
    MOCK_MODE: bool = False

    # CORS — comma-separated list of allowed origins
    # Local dev default; override in production with your Vercel URL.
    # Example: CORS_ORIGINS=https://mini-crm.vercel.app,https://www.yourdomain.com
    # Stored as a plain str so pydantic-settings doesn't attempt JSON-decoding.
    CORS_ORIGINS: str = "http://localhost:5173"

    @property
    def cors_origins_list(self) -> list[str]:
        """Return the comma-separated CORS_ORIGINS string as a list."""
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


settings = Settings()
