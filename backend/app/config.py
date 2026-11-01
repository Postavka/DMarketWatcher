from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    dmarket_public_key: str
    dmarket_secret_key: SecretStr
    dmarket_base_url: str = "https://api.dmarket.com"
    dmarket_max_rps: float = 10.0

    anthropic_api_key: SecretStr | None = None  # only the AI modes need it
    ai_model: str = "claude-opus-5-5"
    ai_effort: str = "medium"
