from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    UPSTREAM_BASE: str = Field(default="https://api.openai.com", alias="LLM_UPSTREAM")
    TARGET_RATIO: float = Field(default=0.7, alias="LLMLINGUA_RATE")
    RATE_PER_1K: float = Field(default=0.005, alias="LLM_PRICE_PER_1K")
    MODEL_PRICING: dict[str, float] = Field(
        default={
            "gpt-4o": 0.005,
            "gpt-4": 0.03,
            "claude-3-5": 0.003,
            "default": 0.005,
        }
    )
    GATEWAY_TOKEN: str = Field(alias="TOKENCAT_API_KEY")
    UPSTREAM_API_KEY: str = Field(alias="LLM_UPSTREAM_KEY")

    @field_validator("GATEWAY_TOKEN")
    @classmethod
    def _reject_weak_token(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("TOKENCAT_API_KEY must be set to a non-empty secret")
        if v == "tokencat_secret_fallback":
            raise ValueError("Refusing to start with the public fallback token")
        if len(v) < 32:
            raise ValueError("TOKENCAT_API_KEY must be at least 32 chars")
        return v


settings = Settings()
