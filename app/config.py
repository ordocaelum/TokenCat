from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


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


settings = Settings()
