from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    log_level: str = "INFO"

    azure_ai_inference_endpoint: str = ""
    azure_ai_inference_api_key: str = ""
    azure_ai_inference_model: str = "Kimi-K2.6"

    chroma_url: str = "http://chromadb:8000"
    chroma_collection: str = "articles"
    embedding_model: str = "intfloat/multilingual-e5-small"

    news_api_key: str = ""
    news_api_base_url: str = "https://newsapi.org/v2"

    backend_port: int = 8000
    frontend_port: int = 3000


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
