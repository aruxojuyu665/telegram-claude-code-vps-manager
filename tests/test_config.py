"""Tests for configuration module."""

import os
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from jarvis_mk1_lite.config import Settings, get_settings


class TestSettings:
    """Tests for Settings class."""

    def test_settings_from_env(self) -> None:
        """Should load settings from environment."""
        env_vars = {
            "TELEGRAM_BOT_TOKEN": "test-token",
            "ANTHROPIC_API_KEY": "test-api-key",
            "ALLOWED_USER_IDS": "[123, 456, 789]",
            "LOG_LEVEL": "DEBUG",
        }
        with patch.dict(os.environ, env_vars, clear=True):
            settings = Settings()  # type: ignore[call-arg]
            # SecretStr requires .get_secret_value() to access the actual value
            assert settings.telegram_bot_token.get_secret_value() == "test-token"
            assert settings.anthropic_api_key.get_secret_value() == "test-api-key"
            assert settings.log_level == "DEBUG"
            assert settings.allowed_user_ids == [123, 456, 789]

    def test_settings_required_fields(self) -> None:
        """Should fail without required fields when no .env file."""
        # Patch both environment AND _env_file to prevent loading .env
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(Settings, "model_config", {"env_file": None}),
            pytest.raises(ValidationError),
        ):
            Settings(_env_file=None)  # type: ignore[call-arg]

    def test_settings_defaults(self) -> None:
        """Should use default values."""
        env_vars = {
            "TELEGRAM_BOT_TOKEN": "test-token",
            "ANTHROPIC_API_KEY": "test-api-key",
        }
        with patch.dict(os.environ, env_vars, clear=True):
            # Use _env_file=None to prevent loading .env and test true defaults
            settings = Settings(_env_file=None)  # type: ignore[call-arg]
            assert settings.log_level == "INFO"
            assert settings.app_name == "JARVIS MK1 Lite"
            # Version should be a valid semver string (not checking exact value)
            assert settings.app_version is not None
            assert len(settings.app_version.split(".")) >= 2
            assert settings.allowed_user_ids == []

    def test_settings_allowed_user_ids_parsing(self) -> None:
        """Should parse allowed_user_ids from JSON array string."""
        env_vars = {
            "TELEGRAM_BOT_TOKEN": "test-token",
            "ANTHROPIC_API_KEY": "test-api-key",
            "ALLOWED_USER_IDS": "[123, 456, 789]",
        }
        with patch.dict(os.environ, env_vars, clear=True):
            settings = Settings()  # type: ignore[call-arg]
            assert settings.allowed_user_ids == [123, 456, 789]

    def test_settings_claude_defaults(self) -> None:
        """Should have correct Claude-related defaults."""
        env_vars = {
            "TELEGRAM_BOT_TOKEN": "test-token",
            "ANTHROPIC_API_KEY": "test-api-key",
        }
        with patch.dict(os.environ, env_vars, clear=True):
            # Use _env_file=None to test true defaults
            settings = Settings(_env_file=None)  # type: ignore[call-arg]
            assert settings.claude_model == "claude-sonnet-4-5-20250929"
            assert settings.claude_max_tokens == 64000
            assert settings.claude_timeout == 300

    def test_settings_claude_custom_values(self) -> None:
        """Should accept custom Claude settings."""
        env_vars = {
            "TELEGRAM_BOT_TOKEN": "test-token",
            "ANTHROPIC_API_KEY": "test-api-key",
            "CLAUDE_MODEL": "claude-opus-4-20250514",
            "CLAUDE_MAX_TOKENS": "8192",
            "CLAUDE_TIMEOUT": "600",
        }
        with patch.dict(os.environ, env_vars, clear=True):
            settings = Settings()  # type: ignore[call-arg]
            assert settings.claude_model == "claude-opus-4-20250514"
            assert settings.claude_max_tokens == 8192
            assert settings.claude_timeout == 600

    def test_settings_path_defaults(self) -> None:
        """Should have correct path defaults."""
        env_vars = {
            "TELEGRAM_BOT_TOKEN": "test-token",
            "ANTHROPIC_API_KEY": "test-api-key",
        }
        with patch.dict(os.environ, env_vars, clear=True):
            # Use _env_file=None to test true defaults without .env interference
            settings = Settings(_env_file=None)  # type: ignore[call-arg]
            assert settings.workspace_dir == "/home/projects"
            assert settings.system_prompt_path == "prompts/system.md"

    def test_settings_path_custom_values(self) -> None:
        """Should accept custom path settings."""
        env_vars = {
            "TELEGRAM_BOT_TOKEN": "test-token",
            "ANTHROPIC_API_KEY": "test-api-key",
            "WORKSPACE_DIR": "/custom/workspace",
            "SYSTEM_PROMPT_PATH": "custom/prompt.md",
        }
        with patch.dict(os.environ, env_vars, clear=True):
            settings = Settings()  # type: ignore[call-arg]
            assert settings.workspace_dir == "/custom/workspace"
            assert settings.system_prompt_path == "custom/prompt.md"

    def test_settings_dangerous_patterns_default(self) -> None:
        """Should have default dangerous patterns."""
        env_vars = {
            "TELEGRAM_BOT_TOKEN": "test-token",
            "ANTHROPIC_API_KEY": "test-api-key",
        }
        with patch.dict(os.environ, env_vars, clear=True):
            settings = Settings()  # type: ignore[call-arg]
            assert isinstance(settings.dangerous_patterns, list)
            assert len(settings.dangerous_patterns) > 0
            assert "rm -rf /" in settings.dangerous_patterns
            assert ":(){:|:&};:" in settings.dangerous_patterns

    def test_get_settings_returns_settings_instance(self) -> None:
        """get_settings should return a Settings instance."""
        env_vars = {
            "TELEGRAM_BOT_TOKEN": "test-token",
            "ANTHROPIC_API_KEY": "test-api-key",
        }
        with patch.dict(os.environ, env_vars, clear=True):
            settings = get_settings()
            assert isinstance(settings, Settings)
            # SecretStr requires .get_secret_value() to access the actual value
            assert settings.telegram_bot_token.get_secret_value() == "test-token"

    def test_settings_rate_limit_defaults(self) -> None:
        """Should have correct rate limit defaults."""
        env_vars = {
            "TELEGRAM_BOT_TOKEN": "test-token",
            "ANTHROPIC_API_KEY": "test-api-key",
        }
        with patch.dict(os.environ, env_vars, clear=True):
            settings = Settings()  # type: ignore[call-arg]
            assert settings.rate_limit_max_tokens == 10
            assert settings.rate_limit_refill_rate == 0.5
            assert settings.rate_limit_enabled is True

    def test_settings_rate_limit_custom_values(self) -> None:
        """Should accept custom rate limit settings."""
        env_vars = {
            "TELEGRAM_BOT_TOKEN": "test-token",
            "ANTHROPIC_API_KEY": "test-api-key",
            "RATE_LIMIT_MAX_TOKENS": "20",
            "RATE_LIMIT_REFILL_RATE": "1.0",
            "RATE_LIMIT_ENABLED": "false",
        }
        with patch.dict(os.environ, env_vars, clear=True):
            settings = Settings()  # type: ignore[call-arg]
            assert settings.rate_limit_max_tokens == 20
            assert settings.rate_limit_refill_rate == 1.0
            assert settings.rate_limit_enabled is False

    def test_settings_session_management_defaults(self) -> None:
        """Should have correct session management defaults."""
        env_vars = {
            "TELEGRAM_BOT_TOKEN": "test-token",
            "ANTHROPIC_API_KEY": "test-api-key",
        }
        with patch.dict(os.environ, env_vars, clear=True):
            settings = Settings()  # type: ignore[call-arg]
            assert settings.session_expiry_seconds == 3600  # 1 hour
            assert settings.max_sessions == 1000

    def test_settings_session_management_custom_values(self) -> None:
        """Should accept custom session management settings."""
        env_vars = {
            "TELEGRAM_BOT_TOKEN": "test-token",
            "ANTHROPIC_API_KEY": "test-api-key",
            "SESSION_EXPIRY_SECONDS": "7200",
            "MAX_SESSIONS": "500",
        }
        with patch.dict(os.environ, env_vars, clear=True):
            settings = Settings()  # type: ignore[call-arg]
            assert settings.session_expiry_seconds == 7200  # 2 hours
            assert settings.max_sessions == 500

    def test_settings_telethon_defaults(self) -> None:
        """Should have correct Telethon defaults (all optional)."""
        env_vars = {
            "TELEGRAM_BOT_TOKEN": "test-token",
            "ANTHROPIC_API_KEY": "test-api-key",
        }
        with patch.dict(os.environ, env_vars, clear=True):
            # Use _env_file=None to test true defaults
            settings = Settings(_env_file=None)  # type: ignore[call-arg]
            assert settings.telethon_api_id is None
            assert settings.telethon_api_hash is None
            assert settings.telethon_phone is None
            assert settings.telethon_session_name == "jarvis_premium"
            assert settings.voice_transcription_enabled is False

    def test_settings_telethon_custom_values(self) -> None:
        """Should accept custom Telethon settings."""
        env_vars = {
            "TELEGRAM_BOT_TOKEN": "test-token",
            "ANTHROPIC_API_KEY": "test-api-key",
            "TELETHON_API_ID": "12345",
            "TELETHON_API_HASH": "abc123xyz",
            "TELETHON_PHONE": "+79001234567",
            "TELETHON_SESSION_NAME": "custom_session",
            "VOICE_TRANSCRIPTION_ENABLED": "true",
        }
        with patch.dict(os.environ, env_vars, clear=True):
            settings = Settings(_env_file=None)  # type: ignore[call-arg]
            assert settings.telethon_api_id == 12345
            assert settings.telethon_api_hash == "abc123xyz"
            assert settings.telethon_phone == "+79001234567"
            assert settings.telethon_session_name == "custom_session"
            assert settings.voice_transcription_enabled is True
