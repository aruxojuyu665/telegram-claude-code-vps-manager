"""Configuration management using Pydantic Settings."""

import tempfile

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables.

    Security: API keys are stored as SecretStr to prevent accidental logging.
    Use .get_secret_value() to access the actual key value when needed.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",  # Ignore extra environment variables
    )

    # Telegram
    telegram_bot_token: SecretStr = Field(
        ...,
        description="Telegram Bot API token from @BotFather",
    )

    # Anthropic (optional - Claude CLI can use OAuth login instead)
    anthropic_api_key: SecretStr | None = Field(
        default=None,
        description="Anthropic API key for Claude (optional if using Claude CLI OAuth)",
    )

    def __repr__(self) -> str:
        """Safe representation that hides secrets."""
        return (
            f"Settings(telegram_bot_token=SecretStr('***'), "
            f"anthropic_api_key=SecretStr('***'), "
            f"allowed_user_ids={self.allowed_user_ids}, "
            f"app_version='{self.app_version}')"
        )

    # Security
    allowed_user_ids: list[int] = Field(
        default_factory=list,
        description="List of allowed Telegram user IDs (whitelist)",
    )

    # Claude Code Settings
    claude_model: str = Field(
        default="claude-sonnet-4-5-20250929",
        description="Claude model to use",
    )
    claude_max_tokens: int = Field(
        default=64000,
        description="Maximum tokens for Claude responses",
    )
    claude_timeout: int = Field(
        default=300,
        description="Timeout in seconds for Claude requests",
    )

    # Paths
    workspace_dir: str = Field(
        default="/home/projects",
        description="Directory for workspace operations",
    )
    system_prompt_path: str = Field(
        default="prompts/system.md",
        description="Path to system prompt file",
    )

    # Safety
    dangerous_patterns: list[str] = Field(
        default_factory=lambda: [
            "rm -rf /",
            "rm -rf /*",
            ":(){:|:&};:",
            "mkfs.",
            "dd if=",
            "> /dev/sda",
            "chmod -R 777 /",
            "wget | sh",
            "curl | sh",
        ],
        description="List of dangerous command patterns to block",
    )

    # Logging
    log_level: str = Field(
        default="INFO",
        description="Logging level (DEBUG, INFO, WARNING, ERROR)",
    )

    # Shutdown
    shutdown_timeout: int = Field(
        default=30,
        description="Timeout in seconds for graceful shutdown",
    )

    # Rate Limiting
    rate_limit_max_tokens: int = Field(
        default=10,
        description="Maximum tokens per user for rate limiting",
    )
    rate_limit_refill_rate: float = Field(
        default=0.5,
        description="Token refill rate per second",
    )
    rate_limit_enabled: bool = Field(
        default=True,
        description="Enable rate limiting",
    )

    # Session Management
    session_expiry_seconds: int = Field(
        default=3600,
        description="Time in seconds before a session expires due to inactivity",
    )
    max_sessions: int = Field(
        default=1000,
        description="Maximum number of sessions to keep (LRU eviction when exceeded)",
    )
    max_sessions_per_user: int = Field(
        default=10,
        description="Maximum number of sessions per user (LRU eviction when exceeded)",
    )
    default_session_name: str = Field(
        default="main",
        description="Default session name for new users",
    )
    session_name_max_length: int = Field(
        default=32,
        description="Maximum length for session names",
    )
    show_session_indicator: bool = Field(
        default=True,
        description="Show session name indicator in responses",
    )

    # Telethon (optional - for voice transcription via Telegram Premium)
    telethon_api_id: int | None = Field(
        default=None,
        description="Telegram API ID from my.telegram.org (for voice transcription)",
    )
    telethon_api_hash: str | None = Field(
        default=None,
        description="Telegram API hash from my.telegram.org",
    )
    telethon_phone: str | None = Field(
        default=None,
        description="Phone number for Telethon authentication",
    )
    telethon_session_name: str = Field(
        default="jarvis_premium",
        description="Name for Telethon session file",
    )
    voice_transcription_enabled: bool = Field(
        default=False,
        description="Enable voice transcription via Telegram Premium",
    )

    # File Handling (Upload - receiving files from user)
    file_handling_enabled: bool = Field(
        default=True,
        description="Enable file handling for documents sent to the bot",
    )
    max_file_size_mb: int = Field(
        default=20,
        description="Maximum file size in MB (Telegram Bot API limit is 20MB)",
    )
    max_extracted_text_chars: int = Field(
        default=100000,
        description="Maximum characters to extract from a file before truncation",
    )

    # File Sending (Download - sending files to user)
    file_send_enabled: bool = Field(
        default=True,
        description="Enable file download/send feature",
    )
    file_send_max_size_mb: int = Field(
        default=50,
        description="Maximum file size for sending in MB (Telegram limit: 50MB)",
    )
    file_send_compress_large: bool = Field(
        default=True,
        description="Compress files larger than max size to ZIP",
    )
    file_send_temp_dir: str = Field(
        default_factory=lambda: f"{tempfile.gettempdir()}/jarvis_files",
        description="Temporary directory for file compression",
    )
    file_send_archive_threshold: int = Field(
        default=5,
        description="Number of files before auto-archiving into ZIP",
    )

    # Wide Context Settings
    message_accumulation_delay: float = Field(
        default=2.0,
        description="Delay in seconds before sending accumulated messages",
    )
    wide_context_timeout: int = Field(
        default=300,
        description="Maximum time in seconds to wait for wide context completion (5 minutes)",
    )
    max_chunk_size: int = Field(
        default=4000,
        description="Maximum chunk size for message splitting (Telegram limit: 4096)",
    )

    # Verbose Mode Settings
    verbose_batch_size: int = Field(
        default=10,
        description="Number of log lines to batch before sending",
    )
    verbose_flush_interval: float = Field(
        default=3.0,
        description="Maximum seconds between verbose message flushes",
    )
    verbose_max_line_length: int = Field(
        default=100,
        description="Maximum length of a single verbose log line",
    )

    # Telegram Retry Settings
    telegram_max_retries: int = Field(
        default=3,
        description="Maximum retry attempts for Telegram API calls",
    )
    telegram_retry_base_delay: float = Field(
        default=1.0,
        description="Base delay in seconds for exponential backoff",
    )

    # Application
    app_name: str = Field(
        default="JARVIS MK1 Lite",
        description="Application name",
    )
    app_version: str = Field(
        default="1.3.1",
        description="Application version",
    )


def get_settings() -> Settings:
    """Get cached settings instance.

    Settings are loaded from environment variables and .env file.
    """
    return Settings()  # type: ignore[call-arg]
