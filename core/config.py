import json
from typing import List, Union
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Discord Config
    DISCORD_TOKEN: str = Field(default="test_mock_discord_token")
    DISCORD_CLIENT_ID: str = Field(default="123456789012345678")
    DISCORD_CLIENT_SECRET: str = Field(default="test_discord_client_secret")
    DISCORD_PUBLIC_KEY: str = Field(default="test_discord_public_key")

    # Owner persona config (checked by Discord ID, never solely by name)
    OWNER_DISCORD_ID: int = Field(default=123456789012345678)
    OWNER_HANDLE: str = Field(default="mayankbereal1")

    # Database
    DATABASE_URL: str = Field(default="sqlite+aiosqlite:///./ryujin.db")

    # JWT Authentication
    JWT_SECRET_KEY: str = Field(default="ryujin-super-secret-development-key-32-chars-min")
    JWT_ALGORITHM: str = Field(default="HS256")
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=1440)
    JWT_ISSUER: str = Field(default="ryujin-auth")

    # Groq AI
    GROQ_API_KEY: str = Field(default="mock_groq_api_key")
    GROQ_MODEL_CHAT: str = Field(default="llama-3.3-70b-versatile")
    GROQ_MODEL_FAST: str = Field(default="llama-3.1-8b-instant")
    AI_DAILY_TOKEN_LIMIT: int = Field(default=100000)
    AI_USER_RPM_LIMIT: int = Field(default=10)

    # General / Localization
    DEFAULT_TIMEZONE: str = Field(default="Asia/Kolkata")
    API_HOST: str = Field(default="0.0.0.0")
    API_PORT: int = Field(default=8000)
    CORS_ORIGINS: Union[List[str], str] = Field(default=["http://localhost:3000"])
    ENVIRONMENT: str = Field(default="development")
    LOG_LEVEL: str = Field(default="INFO")

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str):
            try:
                decoded = json.loads(v)
                if isinstance(decoded, list):
                    return decoded
            except json.JSONDecodeError:
                return [origin.strip() for origin in v.split(",") if origin.strip()]
        elif isinstance(v, list):
            return v
        return ["http://localhost:3000"]


settings = Settings()

