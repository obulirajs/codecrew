"""
Config/secrets loading.

Uses pydantic-settings so the app fails fast at startup - with a clear,
specific error naming the missing field - if any required env var isn't
set. This satisfies story 0.4's acceptance criteria: no silent defaults
for secrets, no hardcoding.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    anthropic_api_key: str
    teams_app_id: str
    teams_app_password: str
    teams_tenant_id: str

    jira_base_url: str
    jira_email: str
    jira_api_token: str
    jira_project_key: str

    llm_provider: str = "ollama"
    cheap_model_anthropic: str = "claude-haiku-4-5-20251001"
    strong_model_anthropic: str = "claude-sonnet-5"
    cheap_model_ollama: str = "gemma3:4b"
    strong_model_ollama: str = "qwen2.5-coder:7b"
    ollama_base_url: str = "http://localhost:11434"

    port: int = 8000
    log_level: str = "INFO"
    log_file_path: str = "logs/codecrew.log"
    log_file_max_bytes: int = 5_000_000
    log_file_backup_count: int = 3

    @property
    def cheap_model(self) -> str:
        return self.cheap_model_ollama if self.llm_provider == "ollama" else self.cheap_model_anthropic

    @property
    def strong_model(self) -> str:
        return self.strong_model_ollama if self.llm_provider == "ollama" else self.strong_model_anthropic


@lru_cache
def get_settings() -> Settings:
    # Raises pydantic.ValidationError with the exact missing field name(s)
    # if required settings are absent - this IS the fail-fast behavior.
    return Settings()
