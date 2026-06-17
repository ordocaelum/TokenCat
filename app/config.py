from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    UPSTREAM_BASE: str = Field(default="https://api.openai.com", alias="LLM_UPSTREAM")
    TARGET_RATIO: float = Field(default=0.7, alias="LLMLINGUA_RATE")
    RATE_PER_1K: float = Field(default=0.005, alias="LLM_PRICE_PER_1K")


settings = Settings()
