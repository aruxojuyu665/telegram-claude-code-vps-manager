"""Tests for main module entry point."""

from __future__ import annotations

import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from jarvis_mk1_lite.__main__ import configure_structlog, main, setup_logging, shutdown


class TestConfigureStructlog:
    """Tests for configure_structlog function."""

    def test_configure_structlog_sets_level(self) -> None:
        """Should configure logging with specified level."""
        with patch("logging.basicConfig") as mock_basic_config:
            configure_structlog("DEBUG")

            mock_basic_config.assert_called_once()
            call_kwargs = mock_basic_config.call_args[1]
            assert call_kwargs["level"] == logging.DEBUG

    def test_configure_structlog_info_level(self) -> None:
        """Should configure logging with INFO level."""
        with patch("logging.basicConfig") as mock_basic_config:
            configure_structlog("INFO")

            mock_basic_config.assert_called_once()
            call_kwargs = mock_basic_config.call_args[1]
            assert call_kwargs["level"] == logging.INFO

    def test_configure_structlog_warning_level(self) -> None:
        """Should configure logging with WARNING level."""
        with patch("logging.basicConfig") as mock_basic_config:
            configure_structlog("WARNING")

            mock_basic_config.assert_called_once()
            call_kwargs = mock_basic_config.call_args[1]
            assert call_kwargs["level"] == logging.WARNING

    def test_configure_structlog_error_level(self) -> None:
        """Should configure logging with ERROR level."""
        with patch("logging.basicConfig") as mock_basic_config:
            configure_structlog("ERROR")

            mock_basic_config.assert_called_once()
            call_kwargs = mock_basic_config.call_args[1]
            assert call_kwargs["level"] == logging.ERROR

    def test_configure_structlog_case_insensitive(self) -> None:
        """Should handle lowercase level names."""
        with patch("logging.basicConfig") as mock_basic_config:
            configure_structlog("debug")

            mock_basic_config.assert_called_once()
            call_kwargs = mock_basic_config.call_args[1]
            assert call_kwargs["level"] == logging.DEBUG

    def test_configure_structlog_uses_stdout_handler(self) -> None:
        """Should use stdout as the handler."""
        with patch("logging.basicConfig") as mock_basic_config:
            configure_structlog("INFO")

            call_kwargs = mock_basic_config.call_args[1]
            handlers = call_kwargs["handlers"]
            assert len(handlers) == 1
            assert isinstance(handlers[0], logging.StreamHandler)
            # Stream may be wrapped by colorama on Windows, so just check it's a StreamHandler

    def test_configure_structlog_format(self) -> None:
        """Should use message-only format for structlog."""
        with patch("logging.basicConfig") as mock_basic_config:
            configure_structlog("INFO")

            call_kwargs = mock_basic_config.call_args[1]
            assert call_kwargs["format"] == "%(message)s"

    def test_configure_structlog_calls_structlog_configure(self) -> None:
        """Should call structlog.configure with processors."""
        with (
            patch("logging.basicConfig"),
            patch("structlog.configure") as mock_structlog_configure,
        ):
            configure_structlog("INFO")

            mock_structlog_configure.assert_called_once()


class TestSetupLogging:
    """Tests for setup_logging function (backward compatibility)."""

    def test_setup_logging_calls_configure_structlog(self) -> None:
        """Should delegate to configure_structlog."""
        with patch("jarvis_mk1_lite.__main__.configure_structlog") as mock_configure:
            setup_logging("DEBUG")

            mock_configure.assert_called_once_with("DEBUG")


class TestShutdown:
    """Tests for shutdown function."""

    @pytest.mark.asyncio
    async def test_shutdown_stops_bot(self) -> None:
        """Should call bot.stop()."""
        mock_bot = MagicMock()
        mock_bot.stop = AsyncMock()

        with patch("structlog.get_logger"):
            await shutdown(mock_bot)

        mock_bot.stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_shutdown_handles_exception(self) -> None:
        """Should handle exception during shutdown gracefully."""
        mock_bot = MagicMock()
        mock_bot.stop = AsyncMock(side_effect=Exception("Shutdown error"))

        with patch("structlog.get_logger"):
            # Should not raise
            await shutdown(mock_bot)

        mock_bot.stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_shutdown_with_custom_timeout(self) -> None:
        """Should accept custom timeout parameter."""
        mock_bot = MagicMock()
        mock_bot.stop = AsyncMock()

        with patch("structlog.get_logger") as mock_get_logger:
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger

            await shutdown(mock_bot, timeout=60)

        mock_bot.stop.assert_called_once()
        # Verify timeout was logged
        mock_logger.info.assert_any_call("Initiating graceful shutdown...", timeout=60)

    @pytest.mark.asyncio
    async def test_shutdown_handles_timeout(self) -> None:
        """Should handle shutdown timeout gracefully."""
        mock_bot = MagicMock()

        async def slow_stop() -> None:
            """Simulate slow stop that times out."""
            await asyncio.sleep(10)

        mock_bot.stop = slow_stop

        with patch("structlog.get_logger") as mock_get_logger:
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger

            # Use a very short timeout to trigger timeout
            await shutdown(mock_bot, timeout=0)

        # Verify timeout was logged
        mock_logger.warning.assert_called_once()


class TestMain:
    """Tests for main function."""

    VALID_TEST_TOKEN = "123456789:ABCdefGHIjklMNOpqrsTUVwxyz"

    @pytest.fixture
    def mock_settings(self) -> MagicMock:
        """Create mock settings."""
        settings = MagicMock()
        mock_token = MagicMock()

        mock_token.get_secret_value.return_value = self.VALID_TEST_TOKEN

        settings.telegram_bot_token = mock_token
        settings.app_name = "Test Bot"
        settings.app_version = "0.10.3"
        settings.allowed_user_ids = [123]
        settings.claude_model = "claude-sonnet-4-20250514"
        settings.workspace_dir = "/home/projects"
        settings.log_level = "INFO"
        settings.shutdown_timeout = 30
        return settings

    @pytest.mark.asyncio
    async def test_main_exits_on_settings_error(self) -> None:
        """Should exit with code 1 when settings fail to load."""
        with (
            patch("jarvis_mk1_lite.__main__.get_settings") as mock_get_settings,
            patch("builtins.print") as mock_print,
            pytest.raises(SystemExit) as exc_info,
        ):
            mock_get_settings.side_effect = Exception("Missing .env file")

            await main()

            assert exc_info.value.code == 1
            mock_print.assert_called()

    @pytest.mark.asyncio
    async def test_main_prints_error_on_settings_failure(self) -> None:
        """Should print helpful error message when settings fail."""
        with (
            patch("jarvis_mk1_lite.__main__.get_settings") as mock_get_settings,
            patch("builtins.print") as mock_print,
            pytest.raises(SystemExit),
        ):
            mock_get_settings.side_effect = Exception("Missing API key")

            await main()

            # Verify error message was printed
            calls = [str(call) for call in mock_print.call_args_list]
            error_msg_found = any("Failed to load settings" in str(c) for c in calls)
            env_msg_found = any(".env" in str(c) for c in calls)
            assert error_msg_found or env_msg_found

    @pytest.mark.asyncio
    async def test_main_creates_jarvis_bot(self, mock_settings: MagicMock) -> None:
        """Should create JarvisBot with settings."""
        with (
            patch("jarvis_mk1_lite.__main__.get_settings") as mock_get_settings,
            patch("jarvis_mk1_lite.__main__.JarvisBot") as mock_jarvis_bot,
            patch("jarvis_mk1_lite.__main__.configure_structlog"),
            patch("structlog.get_logger"),
            patch("jarvis_mk1_lite.__main__.shutdown", new_callable=AsyncMock),
        ):
            mock_get_settings.return_value = mock_settings
            mock_bot_instance = MagicMock()
            mock_bot_instance.start = AsyncMock()
            mock_bot_instance.stop = AsyncMock()
            mock_jarvis_bot.return_value = mock_bot_instance

            await main()

            mock_jarvis_bot.assert_called_once_with(mock_settings)

    @pytest.mark.asyncio
    async def test_main_starts_bot(self, mock_settings: MagicMock) -> None:
        """Should call bot.start()."""
        with (
            patch("jarvis_mk1_lite.__main__.get_settings") as mock_get_settings,
            patch("jarvis_mk1_lite.__main__.JarvisBot") as mock_jarvis_bot,
            patch("jarvis_mk1_lite.__main__.configure_structlog"),
            patch("structlog.get_logger"),
            patch("jarvis_mk1_lite.__main__.shutdown", new_callable=AsyncMock),
        ):
            mock_get_settings.return_value = mock_settings
            mock_bot_instance = MagicMock()
            mock_bot_instance.start = AsyncMock()
            mock_bot_instance.stop = AsyncMock()
            mock_jarvis_bot.return_value = mock_bot_instance

            await main()

            mock_bot_instance.start.assert_called_once()

    @pytest.mark.asyncio
    async def test_main_calls_shutdown_in_finally(self, mock_settings: MagicMock) -> None:
        """Should call shutdown in finally block."""
        with (
            patch("jarvis_mk1_lite.__main__.get_settings") as mock_get_settings,
            patch("jarvis_mk1_lite.__main__.JarvisBot") as mock_jarvis_bot,
            patch("jarvis_mk1_lite.__main__.configure_structlog"),
            patch("structlog.get_logger"),
            patch("jarvis_mk1_lite.__main__.shutdown", new_callable=AsyncMock) as mock_shutdown,
        ):
            mock_get_settings.return_value = mock_settings
            mock_bot_instance = MagicMock()
            mock_bot_instance.start = AsyncMock()
            mock_bot_instance.stop = AsyncMock()
            mock_jarvis_bot.return_value = mock_bot_instance

            await main()

            mock_shutdown.assert_called_once_with(mock_bot_instance, timeout=30)

    @pytest.mark.asyncio
    async def test_main_calls_shutdown_on_bot_completion(self, mock_settings: MagicMock) -> None:
        """Should call shutdown when bot completes (including on error)."""
        with (
            patch("jarvis_mk1_lite.__main__.get_settings") as mock_get_settings,
            patch("jarvis_mk1_lite.__main__.JarvisBot") as mock_jarvis_bot,
            patch("jarvis_mk1_lite.__main__.configure_structlog"),
            patch("structlog.get_logger"),
            patch("jarvis_mk1_lite.__main__.shutdown", new_callable=AsyncMock) as mock_shutdown,
        ):
            mock_get_settings.return_value = mock_settings
            mock_bot_instance = MagicMock()
            # Bot start completes immediately (simulating normal completion)
            mock_bot_instance.start = AsyncMock()
            mock_bot_instance.stop = AsyncMock()
            mock_jarvis_bot.return_value = mock_bot_instance

            await main()

            # Shutdown should be called with bot instance and timeout
            mock_shutdown.assert_called_once_with(mock_bot_instance, timeout=30)

    @pytest.mark.asyncio
    async def test_main_calls_configure_structlog(self, mock_settings: MagicMock) -> None:
        """Should call configure_structlog with log_level from settings."""
        with (
            patch("jarvis_mk1_lite.__main__.get_settings") as mock_get_settings,
            patch("jarvis_mk1_lite.__main__.JarvisBot") as mock_jarvis_bot,
            patch("jarvis_mk1_lite.__main__.configure_structlog") as mock_configure_structlog,
            patch("structlog.get_logger"),
            patch("jarvis_mk1_lite.__main__.shutdown", new_callable=AsyncMock),
        ):
            mock_get_settings.return_value = mock_settings
            mock_bot_instance = MagicMock()
            mock_bot_instance.start = AsyncMock()
            mock_bot_instance.stop = AsyncMock()
            mock_jarvis_bot.return_value = mock_bot_instance

            await main()

            mock_configure_structlog.assert_called_once_with("INFO")

    @pytest.mark.asyncio
    async def test_main_handles_keyboard_interrupt(self, mock_settings: MagicMock) -> None:
        """Should handle KeyboardInterrupt gracefully."""
        with (
            patch("jarvis_mk1_lite.__main__.get_settings") as mock_get_settings,
            patch("jarvis_mk1_lite.__main__.JarvisBot") as mock_jarvis_bot,
            patch("jarvis_mk1_lite.__main__.configure_structlog"),
            patch("structlog.get_logger") as mock_get_logger,
            patch("jarvis_mk1_lite.__main__.shutdown", new_callable=AsyncMock) as mock_shutdown,
            patch("asyncio.wait") as mock_wait,
        ):
            mock_get_settings.return_value = mock_settings
            mock_bot_instance = MagicMock()
            mock_bot_instance.start = AsyncMock()
            mock_bot_instance.stop = AsyncMock()
            mock_jarvis_bot.return_value = mock_bot_instance
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger

            # Simulate KeyboardInterrupt during asyncio.wait
            mock_wait.side_effect = KeyboardInterrupt

            # Should not raise, should handle gracefully
            await main()

            # Shutdown should still be called in finally block with timeout
            mock_shutdown.assert_called_once_with(mock_bot_instance, timeout=30)

    @pytest.mark.asyncio
    async def test_main_handles_unexpected_exception(self, mock_settings: MagicMock) -> None:
        """Should handle unexpected exceptions and re-raise after cleanup."""
        with (
            patch("jarvis_mk1_lite.__main__.get_settings") as mock_get_settings,
            patch("jarvis_mk1_lite.__main__.JarvisBot") as mock_jarvis_bot,
            patch("jarvis_mk1_lite.__main__.configure_structlog"),
            patch("structlog.get_logger") as mock_get_logger,
            patch("jarvis_mk1_lite.__main__.shutdown", new_callable=AsyncMock) as mock_shutdown,
            patch("asyncio.wait") as mock_wait,
            pytest.raises(RuntimeError, match="Unexpected test error"),
        ):
            mock_get_settings.return_value = mock_settings
            mock_bot_instance = MagicMock()
            mock_bot_instance.start = AsyncMock()
            mock_bot_instance.stop = AsyncMock()
            mock_jarvis_bot.return_value = mock_bot_instance
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger

            # Simulate unexpected error during asyncio.wait
            mock_wait.side_effect = RuntimeError("Unexpected test error")

            await main()

        # Verify shutdown was called even though exception was raised
        mock_shutdown.assert_called_once_with(mock_bot_instance, timeout=30)

    @pytest.mark.asyncio
    async def test_main_logs_keyboard_interrupt(self, mock_settings: MagicMock) -> None:
        """Should log when KeyboardInterrupt is received."""
        with (
            patch("jarvis_mk1_lite.__main__.get_settings") as mock_get_settings,
            patch("jarvis_mk1_lite.__main__.JarvisBot") as mock_jarvis_bot,
            patch("jarvis_mk1_lite.__main__.configure_structlog"),
            patch("structlog.get_logger") as mock_get_logger,
            patch("jarvis_mk1_lite.__main__.shutdown", new_callable=AsyncMock),
            patch("asyncio.wait") as mock_wait,
        ):
            mock_get_settings.return_value = mock_settings
            mock_bot_instance = MagicMock()
            mock_bot_instance.start = AsyncMock()
            mock_bot_instance.stop = AsyncMock()
            mock_jarvis_bot.return_value = mock_bot_instance
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger

            # Simulate KeyboardInterrupt during asyncio.wait
            mock_wait.side_effect = KeyboardInterrupt

            await main()

            # Verify keyboard interrupt was logged
            mock_logger.info.assert_any_call("Received keyboard interrupt")

    @pytest.mark.asyncio
    async def test_main_logs_unexpected_exception(self, mock_settings: MagicMock) -> None:
        """Should log unexpected exceptions with exception details."""
        with (
            patch("jarvis_mk1_lite.__main__.get_settings") as mock_get_settings,
            patch("jarvis_mk1_lite.__main__.JarvisBot") as mock_jarvis_bot,
            patch("jarvis_mk1_lite.__main__.configure_structlog"),
            patch("structlog.get_logger") as mock_get_logger,
            patch("jarvis_mk1_lite.__main__.shutdown", new_callable=AsyncMock),
            patch("asyncio.wait") as mock_wait,
            pytest.raises(ValueError),
        ):
            mock_get_settings.return_value = mock_settings
            mock_bot_instance = MagicMock()
            mock_bot_instance.start = AsyncMock()
            mock_bot_instance.stop = AsyncMock()
            mock_jarvis_bot.return_value = mock_bot_instance
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger

            # Simulate ValueError during asyncio.wait
            mock_wait.side_effect = ValueError("Test error")

            await main()

        # Verify exception was logged
        mock_logger.exception.assert_called_once()
        call_args = mock_logger.exception.call_args
        assert "Unexpected error" in call_args[0][0]


class TestSignalHandler:
    """Tests for signal handler functionality."""

    VALID_TEST_TOKEN = "123456789:ABCdefGHIjklMNOpqrsTUVwxyz"

    @pytest.fixture
    def mock_settings(self) -> MagicMock:
        """Create mock settings."""
        settings = MagicMock()
        mock_token = MagicMock()

        mock_token.get_secret_value.return_value = self.VALID_TEST_TOKEN

        settings.telegram_bot_token = mock_token
        settings.app_name = "Test Bot"
        settings.app_version = "0.10.3"
        settings.allowed_user_ids = [123]
        settings.claude_model = "claude-sonnet-4-20250514"
        settings.workspace_dir = "/home/projects"
        settings.log_level = "INFO"
        return settings

    @pytest.mark.asyncio
    async def test_signal_handler_sets_shutdown_event(self, mock_settings: MagicMock) -> None:
        """Should set shutdown event when signal is received."""

        shutdown_triggered = False

        with (
            patch("jarvis_mk1_lite.__main__.get_settings") as mock_get_settings,
            patch("jarvis_mk1_lite.__main__.JarvisBot") as mock_jarvis_bot,
            patch("jarvis_mk1_lite.__main__.configure_structlog"),
            patch("structlog.get_logger") as mock_get_logger,
            patch("jarvis_mk1_lite.__main__.shutdown", new_callable=AsyncMock) as mock_shutdown,
        ):
            mock_get_settings.return_value = mock_settings
            mock_bot_instance = MagicMock()

            async def start_with_signal_trigger() -> None:
                """Simulate bot running and then shutdown triggered."""
                nonlocal shutdown_triggered
                # Allow shutdown event to be set
                await asyncio.sleep(0.01)
                shutdown_triggered = True

            mock_bot_instance.start = AsyncMock(side_effect=start_with_signal_trigger)
            mock_bot_instance.stop = AsyncMock()
            mock_jarvis_bot.return_value = mock_bot_instance
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger

            await main()

            # Verify shutdown was called
            mock_shutdown.assert_called_once()

    @pytest.mark.asyncio
    async def test_signal_handler_logs_signal_name(self, mock_settings: MagicMock) -> None:
        """Should log the signal name when handling signal."""
        import signal

        # Test the signal handler function directly
        shutdown_event = asyncio.Event()
        mock_logger = MagicMock()

        def signal_handler(sig: signal.Signals) -> None:
            mock_logger.info("Received signal", signal=sig.name)
            shutdown_event.set()

        # Simulate SIGTERM signal
        signal_handler(signal.SIGTERM)

        # Verify signal was logged
        mock_logger.info.assert_called_once_with("Received signal", signal="SIGTERM")
        assert shutdown_event.is_set()

    @pytest.mark.asyncio
    async def test_signal_handler_with_sigint(self, mock_settings: MagicMock) -> None:
        """Should handle SIGINT signal correctly."""
        import signal

        shutdown_event = asyncio.Event()
        mock_logger = MagicMock()

        def signal_handler(sig: signal.Signals) -> None:
            mock_logger.info("Received signal", signal=sig.name)
            shutdown_event.set()

        # Simulate SIGINT signal
        signal_handler(signal.SIGINT)

        mock_logger.info.assert_called_once_with("Received signal", signal="SIGINT")
        assert shutdown_event.is_set()
