from functools import lru_cache

from cryptography.fernet import Fernet
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "postgresql+asyncpg://webhooks:webhooks@localhost:5432/webhooks"
    jwt_secret: str = Field(min_length=32)
    encryption_key: str
    public_base_url: str = "http://localhost:8080"
    admin_username: str = "admin"
    admin_password: str = "Admin#123."
    token_expire_minutes: int = Field(default=120, ge=5, le=1440)
    llm_allowed_hosts: str = "api.openai.com"
    allow_http_llm: bool = False
    max_payload_bytes: int = Field(default=1048576, ge=1024)
    worker_poll_seconds: float = Field(default=2.0, gt=0)
    worker_lease_seconds: int = Field(default=300, ge=180)
    outbound_timeout_seconds: float = Field(default=45.0, gt=0, le=60)
    login_max_attempts: int = Field(default=10, ge=1)

    @field_validator("encryption_key")
    @classmethod
    def valid_key(cls, value: str) -> str:
        Fernet(value.encode())
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
