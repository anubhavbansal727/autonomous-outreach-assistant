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
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost/crm"

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
