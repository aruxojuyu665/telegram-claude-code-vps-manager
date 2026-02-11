"""Tests for main module - v1.0.20 additions.

P2-MAIN-001: Main Entry Point Tests
"""

from __future__ import annotations

import asyncio
import importlib.util
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from jarvis_mk1_lite.__main__ import configure_structlog, main, setup_logging, shutdown


# =============================================================================
# P2-MAIN-001: Main Entry Point Tests (v1.0.20)
# =============================================================================


class TestMainEntryPointAdvanced:
    """Advanced tests for main entry point (P2-MAIN-001).

    Covers: configuration edge cases, logging scenarios,
    error handling paths, and graceful shutdown.
    """

    VALID_TEST_TOKEN = "123456789:ABCdefGHIjklMNOpqrsTUVwxyz"

    @pytest.fixture
    def mock_settings(self) -> MagicMock:
        """Create mock settings."""
        settings = MagicMock()
        mock_token = MagicMock()
        mock_token.get_secret_value.return_value = self.VALID_TEST_TOKEN
        settings.telegram_bot_token = mock_token
        settings.app_name = "Test Bot"
        settings.app_version = "1.0.20"
        settings.allowed_user_ids = [123]
        settings.claude_model = "claude-sonnet-4-20250514"
        settings.workspace_dir = "/home/projects"
        settings.log_level = "DEBUG"
        settings.shutdown_timeout = 10
        return settings

    def test_configure_structlog_with_critical_level(self) -> None:
        """Test structlog configuration with CRITICAL level."""
        with patch("logging.basicConfig") as mock_basic_config:
            configure_structlog("CRITICAL")
            mock_basic_config.assert_called_once()

    def test_setup_logging_is_alias(self) -> None:
        """Verify setup_logging is an alias for configure_structlog."""
        with patch("jarvis_mk1_lite.__main__.configure_structlog") as mock_configure:
            setup_logging("WARNING")
            mock_configure.assert_called_once_with("WARNING")

    @pytest.mark.asyncio
    async def test_shutdown_default_timeout(self) -> None:
        """Test shutdown with default timeout value."""
        mock_bot = MagicMock()
        mock_bot.stop = AsyncMock()

        with patch("structlog.get_logger") as mock_get_logger:
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger

            await shutdown(mock_bot)  # Default timeout

            mock_bot.stop.assert_called_once()
            # Check default timeout was used
            mock_logger.info.assert_any_call("Initiating graceful shutdown...", timeout=30)

    @pytest.mark.asyncio
    async def test_shutdown_logs_success_message(self) -> None:
        """Test that successful shutdown logs appropriate message."""
        mock_bot = MagicMock()
        mock_bot.stop = AsyncMock()

        with patch("structlog.get_logger") as mock_get_logger:
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger

            await shutdown(mock_bot, timeout=5)

            mock_logger.info.assert_any_call("Bot stopped successfully")

    @pytest.mark.asyncio
    async def test_main_logs_startup_info(self, mock_settings: MagicMock) -> None:
        """Main should log startup information with key parameters."""
        with (
            patch("jarvis_mk1_lite.__main__.get_settings") as mock_get_settings,
            patch("jarvis_mk1_lite.__main__.JarvisBot") as mock_jarvis_bot,
            patch("jarvis_mk1_lite.__main__.configure_structlog"),
            patch("structlog.get_logger") as mock_get_logger,
            patch("jarvis_mk1_lite.__main__.shutdown", new_callable=AsyncMock),
        ):
            mock_get_settings.return_value = mock_settings
            mock_bot_instance = MagicMock()
            mock_bot_instance.start = AsyncMock()
            mock_bot_instance.stop = AsyncMock()
            mock_jarvis_bot.return_value = mock_bot_instance
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger

            await main()

            # Verify startup info logged
            mock_logger.info.assert_any_call(
                "Starting JARVIS MK1 Lite",
                app_name=mock_settings.app_name,
                version=mock_settings.app_version,
                model=mock_settings.claude_model,
                workspace=mock_settings.workspace_dir,
                allowed_users=1,
            )

    @pytest.mark.asyncio
    async def test_main_logs_shutdown_complete(self, mock_settings: MagicMock) -> None:
        """Main should log 'Shutdown complete' message."""
        with (
            patch("jarvis_mk1_lite.__main__.get_settings") as mock_get_settings,
            patch("jarvis_mk1_lite.__main__.JarvisBot") as mock_jarvis_bot,
            patch("jarvis_mk1_lite.__main__.configure_structlog"),
            patch("structlog.get_logger") as mock_get_logger,
            patch("jarvis_mk1_lite.__main__.shutdown", new_callable=AsyncMock),
        ):
            mock_get_settings.return_value = mock_settings
            mock_bot_instance = MagicMock()
            mock_bot_instance.start = AsyncMock()
            mock_bot_instance.stop = AsyncMock()
            mock_jarvis_bot.return_value = mock_bot_instance
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger

            await main()

            mock_logger.info.assert_any_call("Shutdown complete")

    def test_main_module_entry_point(self) -> None:
        """Verify __main__.py can be run as module."""
        spec = importlib.util.find_spec("jarvis_mk1_lite.__main__")
        assert spec is not None
        assert spec.origin is not None
        assert "__main__.py" in spec.origin

    @pytest.mark.asyncio
    async def test_settings_error_message_content(self) -> None:
        """Verify error message content when settings fail."""
        with (
            patch("jarvis_mk1_lite.__main__.get_settings") as mock_get_settings,
            patch("builtins.print") as mock_print,
            pytest.raises(SystemExit) as exc_info,
        ):
            mock_get_settings.side_effect = ValueError("Invalid API key format")

            await main()

            assert exc_info.value.code == 1
            # Verify helpful message was printed
            calls = [str(call) for call in mock_print.call_args_list]
            assert any("Invalid API key" in str(c) for c in calls) or any(
                "Failed to load" in str(c) for c in calls
            )

    @pytest.mark.asyncio
    async def test_shutdown_timeout_logs_warning(self) -> None:
        """Test that timeout during shutdown logs a warning."""
        mock_bot = MagicMock()

        async def very_slow_stop() -> None:
            await asyncio.sleep(100)  # Will timeout

        mock_bot.stop = very_slow_stop

        with patch("structlog.get_logger") as mock_get_logger:
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger

            # Very short timeout to trigger
            await shutdown(mock_bot, timeout=0)

            # Should log warning about timeout
            mock_logger.warning.assert_called()

    def test_configure_structlog_configures_processors(self) -> None:
        """Verify structlog is configured with expected processors."""
        with (
            patch("logging.basicConfig"),
            patch("structlog.configure") as mock_structlog_configure,
        ):
            configure_structlog("INFO")

            mock_structlog_configure.assert_called_once()
            call_kwargs = mock_structlog_configure.call_args[1]
            assert "processors" in call_kwargs
            assert len(call_kwargs["processors"]) > 0
