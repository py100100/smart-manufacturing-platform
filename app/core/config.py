from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "智能制造服务平台"
    app_version: str = "0.1.0"
    app_env: str = "dev"
    debug: bool = True
    api_prefix: str = "/api/v1"
    cors_origins: list[str] = Field(default_factory=lambda: ["*"])

    deepseek_api_key: str = Field(default="", alias="DEEPSEEK_API_KEY")
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-v4-flash"

    mcp_enabled: bool = False
    mcp_server_url: str = ""
    mcp_tool_name: str = ""
    mcp_auth_token: str = Field(default="", alias="MCP_AUTH_TOKEN")
    mcp_timeout_seconds: int = 5

    mysql_host: str = "127.0.0.1"
    mysql_port: int = 3306
    mysql_user: str = "root"
    mysql_password: str = Field(default="", alias="MYSQL_PASSWORD")
    mysql_db: str = "smart_manufacturing"

    neo4j_enabled: bool = False
    neo4j_uri: str = "bolt://127.0.0.1:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = Field(default="", alias="NEO4J_PASSWORD")

    request_timeout_seconds: int = 30
    memory_file: Path = BASE_DIR / "MEMORY.md"
    claude_file: Path = BASE_DIR / "CLAUDE.md"

    @property
    def mysql_url(self) -> str:
        return (
            f"mysql+pymysql://{self.mysql_user}:{self.mysql_password}"
            f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_db}?charset=utf8mb4"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
