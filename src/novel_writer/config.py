"""Configuration and settings."""

import os
from pathlib import Path
from typing import Literal
from pydantic import Field
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

load_dotenv()


class Settings(BaseSettings):
    """Application settings."""
    
    # LLM Provider
    llm_provider: Literal["openai", "deepseek"] = Field(
        default="deepseek", 
        alias="LLM_PROVIDER"
    )
    
    # OpenAI
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4o", alias="OPENAI_MODEL")
    
    # DeepSeek
    deepseek_api_key: str = Field(default="", alias="DEEPSEEK_API_KEY")
    deepseek_model: str = Field(default="deepseek-chat", alias="DEEPSEEK_MODEL")
    deepseek_base_url: str = Field(
        default="https://api.deepseek.com/v1", 
        alias="DEEPSEEK_BASE_URL"
    )
    
    # Novel Writer Settings
    max_retry_count: int = Field(default=3, alias="MAX_RETRY_COUNT")
    default_chapter_length: int = Field(default=3000, alias="DEFAULT_CHAPTER_LENGTH")
    
    # Paths
    data_dir: Path = Field(default=Path("data"))
    novels_dir: Path = Field(default=Path("data/novels"))
    chroma_dir: Path = Field(default=Path("data/chroma_db"))
    
    class Config:
        env_file = ".env"
        extra = "ignore"
    
    def get_api_key(self) -> str:
        """Get the API key for the current provider."""
        if self.llm_provider == "openai":
            return self.openai_api_key
        return self.deepseek_api_key
    
    def get_model(self) -> str:
        """Get the model name for the current provider."""
        if self.llm_provider == "openai":
            return self.openai_model
        return self.deepseek_model
    
    def get_base_url(self) -> str | None:
        """Get the base URL for the current provider."""
        if self.llm_provider == "deepseek":
            return self.deepseek_base_url
        return None


settings = Settings()
