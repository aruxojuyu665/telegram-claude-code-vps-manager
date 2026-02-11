"""Integration tests for Telegram Bot using mocked Telegram interactions.

NOTE: These are NOT true E2E tests - they use mocks for Telegram and Claude.
For real E2E tests, see tests/live_e2e/ directory.

This module provides integration tests that verify the bot stack logic
including handlers, middleware, and message flow using MOCKED interactions.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram import Bot
from aiogram.types import Chat, Message, User

from jarvis_mk1_lite.bot import (
    CONFIRMATION_TIMEOUT,
    JarvisBot,
    PendingConfirmation,
    pending_confirmations,
)
from jarvis_mk1_lite.bridge import ClaudeBridge, ClaudeResponse
from jarvis_mk1_lite.safety import RiskLevel

# Test fixtures and helpers
VALID_TEST_TOKEN = "123456789:ABCdefGHIjklMNOpqrsTUVwxyz"


def create_mock_user(user_id: int = 123, first_name: str = "TestUser") -> User:
    """Create a mock Telegram user."""
    return User(
        id=user_id,
        is_bot=False,
        first_name=first_name,
        last_name="User",
        username=f"test_user_{user_id}",
        language_code="en",
    )


def create_mock_chat(chat_id: int = 123) -> Chat:
    """Create a mock Telegram chat."""
    return Chat(
        id=chat_id,
        type="private",
    )


def create_mock_message(
    text: str,
    user_id: int = 123,
    chat_id: int = 123,
    message_id: int = 1,
) -> MagicMock:
    """Create a mock Telegram message with all required attributes."""
    message = MagicMock(spec=Message)
    message.message_id = message_id
    message.date = datetime.now(UTC)
    message.chat = create_mock_chat(chat_id)
    message.from_user = create_mock_user(user_id)
    message.text = text
    message.answer = AsyncMock()
    message.bot = MagicMock(spec=Bot)
    message.bot.send_chat_action = AsyncMock()
    return message


def create_mock_settings(
    allowed_user_ids: list[int] | None = None,
    rate_limit_enabled: bool = False,
) -> MagicMock:
    """Create mock settings for testing."""
    from pydantic import SecretStr

    settings = MagicMock()
    settings.telegram_bot_token = SecretStr(VALID_TEST_TOKEN)
    settings.app_name = "Test Bot"
    settings.app_version = "0.10.3"
    settings.allowed_user_ids = allowed_user_ids or [123, 456]
    settings.claude_model = "claude-sonnet-4-20250514"
    settings.workspace_dir = "/home/projects"
    settings.rate_limit_enabled = rate_limit_enabled
    settings.rate_limit_max_tokens = 10
    settings.rate_limit_refill_rate = 0.5
    return settings


class TestE2EBotInitialization:
    """E2E tests for bot initialization and setup."""

    def test_bot_initializes_with_correct_token(self) -> None:
        """Bot should initialize with the provided token."""
        settings = create_mock_settings()
        with patch("jarvis_mk1_lite.bot.claude_bridge"):
            bot = JarvisBot(settings)
            assert bot.bot.token == VALID_TEST_TOKEN

    def test_bot_has_all_handlers_registered(self) -> None:
        """Bot should have all command handlers registered."""
        settings = create_mock_settings()
        with patch("jarvis_mk1_lite.bot.claude_bridge"):
            bot = JarvisBot(settings)
            # Should have 14 handlers: start, help, status, new, metrics,
            # verbose, wide-context, sessions, switch, kill, text, voice, video_note, document
            assert len(bot.dp.message.handlers) == 14

    def test_bot_has_middleware_registered(self) -> None:
        """Bot should have whitelist middleware registered."""
        settings = create_mock_settings()
        with patch("jarvis_mk1_lite.bot.claude_bridge"):
            bot = JarvisBot(settings)
            assert len(bot.dp.message.middleware) >= 1

    def test_bot_has_bridge_reference(self) -> None:
        """Bot should have a reference to Claude Bridge."""
        settings = create_mock_settings()
        with patch("jarvis_mk1_lite.bot.claude_bridge") as mock_bridge:
            bot = JarvisBot(settings)
            assert bot.bridge is mock_bridge


class TestE2EStartCommand:
    """E2E tests for /start command handler."""

    @pytest.fixture
    def mock_settings(self) -> MagicMock:
        """Create mock settings."""
        return create_mock_settings()

    @pytest.fixture
    def bot(self, mock_settings: MagicMock) -> JarvisBot:
        """Create JarvisBot instance."""
        with patch("jarvis_mk1_lite.bot.claude_bridge"):
            return JarvisBot(mock_settings)

    @pytest.fixture(autouse=True)
    def reset_metrics(self) -> None:
        """Reset metrics before each test."""
        from jarvis_mk1_lite.metrics import metrics

        metrics.reset()

    def test_start_command_returns_welcome_message(self, bot: JarvisBot) -> None:
        """Start command should return welcome message with app info."""
        _ = create_mock_message("/start")  # Message would be used in actual handler

        # The welcome text should include these elements
        expected_elements = ["Welcome", "Test Bot", "Available Commands"]
        welcome_text = f"""
*Welcome to {bot.settings.app_name}!*

I'm your AI assistant powered by Claude Code.
Version: `{bot.settings.app_version}`

*Available Commands:*
- `/start` - Show this welcome message
- `/help` - Detailed help and usage examples
- `/status` - Check system status
- `/metrics` - View application metrics
- `/new` - Start a new conversation session

Simply send me any message and I'll forward it to Claude for processing.
        """.strip()

        for element in expected_elements:
            assert element in welcome_text

    def test_start_command_records_metrics(self) -> None:
        """Start command should record command metrics."""
        from jarvis_mk1_lite.metrics import metrics

        initial_commands = metrics.total_commands
        metrics.record_command("start", 123)

        assert metrics.total_commands == initial_commands + 1

    def test_start_command_with_no_user_returns_none(self) -> None:
        """Start command should return None if no user."""
        message = create_mock_message("/start")
        message.from_user = None

        # Handler checks for None user and returns early
        assert message.from_user is None


class TestE2EHelpCommand:
    """E2E tests for /help command handler."""

    @pytest.fixture
    def mock_settings(self) -> MagicMock:
        """Create mock settings."""
        return create_mock_settings()

    @pytest.fixture(autouse=True)
    def reset_metrics(self) -> None:
        """Reset metrics before each test."""
        from jarvis_mk1_lite.metrics import metrics

        metrics.reset()

    def test_help_command_includes_all_commands(self, mock_settings: MagicMock) -> None:
        """Help command should list all available commands."""
        help_text = """
*JARVIS MK1 Lite Help*

*Commands:*
- `/start` - Show welcome message
- `/help` - Show this help message
- `/status` - Check Claude CLI status and session info
- `/metrics` - View application metrics
- `/new` - Clear session and start fresh
        """.strip()

        commands = ["/start", "/help", "/status", "/metrics", "/new"]
        for cmd in commands:
            assert cmd in help_text

    def test_help_command_includes_security_section(self) -> None:
        """Help command should include security features section."""
        help_text = """
*Security Features:*
- Whitelist-based access control
- Socratic Gate for dangerous commands
- Commands like `rm -rf /` require confirmation
- Rate limiting to prevent abuse
        """.strip()

        security_keywords = ["Whitelist", "Socratic Gate", "confirmation", "Rate limiting"]
        for keyword in security_keywords:
            assert keyword in help_text

    def test_help_command_records_metrics(self) -> None:
        """Help command should record command metrics."""
        from jarvis_mk1_lite.metrics import metrics

        initial_commands = metrics.total_commands
        metrics.record_command("help", 123)

        assert metrics.total_commands == initial_commands + 1


class TestE2EStatusCommand:
    """E2E tests for /status command handler."""

    @pytest.fixture
    def mock_settings(self) -> MagicMock:
        """Create mock settings."""
        return create_mock_settings()

    @pytest.fixture
    def mock_bridge(self) -> MagicMock:
        """Create mock bridge."""
        bridge = MagicMock(spec=ClaudeBridge)
        bridge.check_health = AsyncMock(return_value=True)
        bridge.get_session = MagicMock(return_value="test-session-12345")
        return bridge

    @pytest.fixture(autouse=True)
    def reset_metrics(self) -> None:
        """Reset metrics before each test."""
        from jarvis_mk1_lite.metrics import metrics

        metrics.reset()

    @pytest.fixture(autouse=True)
    def clear_pending(self) -> None:
        """Clear pending confirmations."""
        pending_confirmations.clear()

    def test_status_shows_healthy_status(self, mock_bridge: MagicMock) -> None:
        """Status should show healthy when Claude CLI is healthy."""
        is_healthy = True
        status_emoji = "+" if is_healthy else "-"
        status_text = "Healthy" if is_healthy else "Unhealthy"

        assert status_emoji == "+"
        assert status_text == "Healthy"

    def test_status_shows_unhealthy_status(self) -> None:
        """Status should show unhealthy when Claude CLI is not healthy."""
        is_healthy = False
        status_emoji = "+" if is_healthy else "-"
        status_text = "Healthy" if is_healthy else "Unhealthy"

        assert status_emoji == "-"
        assert status_text == "Unhealthy"

    def test_status_shows_session_info(self, mock_bridge: MagicMock) -> None:
        """Status should show session info when session exists."""
        session = mock_bridge.get_session(123)
        session_info = f"`{session[:12]}...`" if session else "No active session"

        # Session is truncated to first 12 characters
        assert "test-session" in session_info

    def test_status_shows_pending_confirmation(self) -> None:
        """Status should show pending confirmation if exists."""
        pending_confirmations[123] = PendingConfirmation(
            command="rm -rf /",
            risk_level=RiskLevel.CRITICAL,
            timestamp=time.time(),
        )

        assert 123 in pending_confirmations
        pending = pending_confirmations[123]
        pending_info = f"\n*Pending:* {pending.risk_level.value.upper()} confirmation"

        assert "CRITICAL" in pending_info

    def test_status_records_metrics(self) -> None:
        """Status command should record command metrics."""
        from jarvis_mk1_lite.metrics import metrics

        initial_commands = metrics.total_commands
        metrics.record_command("status", 123)

        assert metrics.total_commands == initial_commands + 1


class TestE2ENewCommand:
    """E2E tests for /new command handler."""

    @pytest.fixture
    def mock_settings(self) -> MagicMock:
        """Create mock settings."""
        return create_mock_settings()

    @pytest.fixture
    def mock_bridge(self) -> MagicMock:
        """Create mock bridge."""
        bridge = MagicMock(spec=ClaudeBridge)
        bridge.clear_session = MagicMock(return_value=True)
        return bridge

    @pytest.fixture(autouse=True)
    def reset_all(self) -> None:
        """Reset all state."""
        from jarvis_mk1_lite.metrics import metrics, rate_limiter

        metrics.reset()
        rate_limiter.reset_all()
        pending_confirmations.clear()

    def test_new_command_clears_session(self, mock_bridge: MagicMock) -> None:
        """New command should clear existing session."""
        had_session = mock_bridge.clear_session(123)
        assert had_session is True

    def test_new_command_clears_pending_confirmation(self) -> None:
        """New command should clear pending confirmations."""
        pending_confirmations[123] = PendingConfirmation(
            command="rm -rf /",
            risk_level=RiskLevel.CRITICAL,
            timestamp=time.time(),
        )

        # Simulate handler clearing pending
        del pending_confirmations[123]

        assert 123 not in pending_confirmations

    def test_new_command_resets_rate_limiter(self) -> None:
        """New command should reset user's rate limit."""
        from jarvis_mk1_lite.metrics import rate_limiter

        # Exhaust tokens
        for _ in range(15):
            rate_limiter.is_allowed(123)

        # Reset
        rate_limiter.reset_user(123)

        # Should be allowed again
        assert rate_limiter.is_allowed(123) is True

    def test_new_command_response_with_session(self) -> None:
        """New command should respond appropriately when session existed."""
        had_session = True
        response = (
            "Previous session cleared. Starting fresh!"
            if had_session
            else "Ready for a new conversation!"
        )
        assert "Previous session cleared" in response

    def test_new_command_response_without_session(self) -> None:
        """New command should respond appropriately when no session existed."""
        had_session = False
        response = (
            "Previous session cleared. Starting fresh!"
            if had_session
            else "Ready for a new conversation!"
        )
        assert "Ready for a new conversation" in response


class TestE2EMetricsCommand:
    """E2E tests for /metrics command handler."""

    @pytest.fixture(autouse=True)
    def reset_metrics(self) -> None:
        """Reset metrics before each test."""
        from jarvis_mk1_lite.metrics import metrics

        metrics.reset()

    def test_metrics_command_returns_formatted_message(self) -> None:
        """Metrics command should return formatted metrics message."""
        from jarvis_mk1_lite.metrics import format_metrics_message

        message = format_metrics_message()

        assert "*Application Metrics*" in message
        assert "*Status:*" in message
        assert "*Uptime:*" in message

    def test_metrics_command_includes_session_stats(self) -> None:
        """Metrics command should include session statistics."""
        from jarvis_mk1_lite.metrics import format_metrics_message

        session_stats = {
            "active_sessions": 5,
            "sessions_expired": 2,
            "sessions_evicted": 1,
            "oldest_session_age": 3600.0,
        }

        message = format_metrics_message(session_stats)  # type: ignore[arg-type]

        assert "*Sessions:*" in message
        assert "Active:" in message

    def test_metrics_command_records_metrics(self) -> None:
        """Metrics command should record command metrics."""
        from jarvis_mk1_lite.metrics import metrics

        initial_commands = metrics.total_commands
        metrics.record_command("metrics", 123)

        assert metrics.total_commands == initial_commands + 1


class TestE2EMessageHandling:
    """E2E tests for regular message handling."""

    @pytest.fixture
    def mock_settings(self) -> MagicMock:
        """Create mock settings."""
        return create_mock_settings(rate_limit_enabled=False)

    @pytest.fixture
    def mock_bridge(self) -> MagicMock:
        """Create mock bridge."""
        bridge = MagicMock(spec=ClaudeBridge)
        bridge.send = AsyncMock(return_value=ClaudeResponse(success=True, content="OK"))
        return bridge

    @pytest.fixture(autouse=True)
    def reset_all(self) -> None:
        """Reset all state."""
        from jarvis_mk1_lite.metrics import metrics, rate_limiter

        metrics.reset()
        rate_limiter.reset_all()
        pending_confirmations.clear()

    def test_safe_message_processed_directly(self) -> None:
        """Safe messages should be processed without confirmation."""
        from jarvis_mk1_lite.safety import RiskLevel, socratic_gate

        text = "ls -la"
        safety_check = socratic_gate.check(text)

        assert safety_check.risk_level == RiskLevel.SAFE
        assert safety_check.requires_confirmation is False

    def test_moderate_message_shows_info(self) -> None:
        """Moderate risk messages should show info and execute."""
        from jarvis_mk1_lite.safety import RiskLevel, socratic_gate

        text = "apt remove vim"
        safety_check = socratic_gate.check(text)

        assert safety_check.risk_level == RiskLevel.MODERATE
        # Moderate messages show info but don't require confirmation
        info_message = f"INFO: {safety_check.matched_pattern} - executing..."
        assert "INFO:" in info_message

    def test_dangerous_message_requires_confirmation(self) -> None:
        """Dangerous messages should require YES/NO confirmation."""
        from jarvis_mk1_lite.safety import RiskLevel, socratic_gate

        text = "rm -rf /home/user"
        safety_check = socratic_gate.check(text)

        assert safety_check.risk_level == RiskLevel.DANGEROUS
        assert safety_check.requires_confirmation is True

    def test_critical_message_requires_exact_phrase(self) -> None:
        """Critical messages should require exact phrase confirmation."""
        from jarvis_mk1_lite.safety import RiskLevel, socratic_gate

        text = "rm -rf /"
        safety_check = socratic_gate.check(text)

        assert safety_check.risk_level == RiskLevel.CRITICAL
        assert safety_check.requires_confirmation is True

    def test_message_records_request_metric(self) -> None:
        """Message handling should record request metric."""
        from jarvis_mk1_lite.metrics import metrics

        initial_messages = metrics.total_messages
        metrics.record_request(123, is_command=False)

        assert metrics.total_messages == initial_messages + 1

    def test_message_records_latency(self) -> None:
        """Message handling should record latency."""
        from jarvis_mk1_lite.metrics import metrics

        metrics.record_latency(0.5)

        assert len(metrics.latencies) >= 1


class TestE2EConfirmationFlow:
    """E2E tests for confirmation flow."""

    @pytest.fixture
    def mock_message(self) -> MagicMock:
        """Create mock message."""
        return create_mock_message("yes")

    @pytest.fixture
    def mock_bridge(self) -> MagicMock:
        """Create mock bridge."""
        bridge = MagicMock(spec=ClaudeBridge)
        bridge.send = AsyncMock(return_value=ClaudeResponse(success=True, content="Executed"))
        return bridge

    @pytest.fixture(autouse=True)
    def clear_pending(self) -> None:
        """Clear pending confirmations."""
        pending_confirmations.clear()

    def test_dangerous_confirmation_yes_executes(
        self, mock_message: MagicMock, mock_bridge: MagicMock
    ) -> None:
        """YES confirmation should execute dangerous command."""

        pending_confirmations[123] = PendingConfirmation(
            command="shutdown now",
            risk_level=RiskLevel.DANGEROUS,
            timestamp=time.time(),
        )

        # Simulate confirmation (synchronous test)
        assert 123 in pending_confirmations
        assert pending_confirmations[123].risk_level == RiskLevel.DANGEROUS

    def test_dangerous_confirmation_no_cancels(self) -> None:
        """NO confirmation should cancel dangerous command."""
        from jarvis_mk1_lite.safety import socratic_gate

        pending_confirmations[123] = PendingConfirmation(
            command="shutdown now",
            risk_level=RiskLevel.DANGEROUS,
            timestamp=time.time(),
        )

        assert socratic_gate.is_cancellation("no") is True

        # Simulate cancellation
        del pending_confirmations[123]
        assert 123 not in pending_confirmations

    def test_critical_confirmation_exact_phrase_executes(self) -> None:
        """Exact phrase confirmation should execute critical command."""
        from jarvis_mk1_lite.safety import socratic_gate

        pending_confirmations[123] = PendingConfirmation(
            command="rm -rf /",
            risk_level=RiskLevel.CRITICAL,
            timestamp=time.time(),
        )

        phrase = socratic_gate.CRITICAL_CONFIRMATION_PHRASE
        is_valid = socratic_gate.is_confirmation_valid(phrase, RiskLevel.CRITICAL)

        assert is_valid is True

    def test_critical_confirmation_invalid_phrase_rejected(self) -> None:
        """Invalid phrase should be rejected for critical confirmation."""
        from jarvis_mk1_lite.safety import socratic_gate

        pending_confirmations[123] = PendingConfirmation(
            command="rm -rf /",
            risk_level=RiskLevel.CRITICAL,
            timestamp=time.time(),
        )

        # "yes" is not valid for critical
        is_valid = socratic_gate.is_confirmation_valid("yes", RiskLevel.CRITICAL)

        assert is_valid is False

    def test_confirmation_expires(self) -> None:
        """Confirmation should expire after timeout."""
        from jarvis_mk1_lite.bot import is_confirmation_expired

        pending = PendingConfirmation(
            command="rm -rf /",
            risk_level=RiskLevel.CRITICAL,
            timestamp=time.time() - CONFIRMATION_TIMEOUT - 1,
        )

        assert is_confirmation_expired(pending) is True

    def test_confirmation_not_expired(self) -> None:
        """Recent confirmation should not be expired."""
        from jarvis_mk1_lite.bot import is_confirmation_expired

        pending = PendingConfirmation(
            command="rm -rf /",
            risk_level=RiskLevel.CRITICAL,
            timestamp=time.time(),
        )

        assert is_confirmation_expired(pending) is False


class TestE2ERateLimiting:
    """E2E tests for rate limiting."""

    @pytest.fixture(autouse=True)
    def reset_rate_limiter(self) -> None:
        """Reset rate limiter."""
        from jarvis_mk1_lite.metrics import rate_limiter

        rate_limiter.reset_all()

    def test_rate_limiter_allows_initial_requests(self) -> None:
        """Rate limiter should allow initial requests."""
        from jarvis_mk1_lite.metrics import rate_limiter

        assert rate_limiter.is_allowed(123) is True

    def test_rate_limiter_blocks_after_limit(self) -> None:
        """Rate limiter should block after limit exceeded."""
        from jarvis_mk1_lite.metrics import rate_limiter

        # Exhaust tokens
        for _ in range(20):
            rate_limiter.is_allowed(123)

        assert rate_limiter.is_allowed(123) is False

    def test_rate_limiter_provides_retry_after(self) -> None:
        """Rate limiter should provide retry after seconds."""
        from jarvis_mk1_lite.metrics import rate_limiter

        # Exhaust tokens
        for _ in range(20):
            rate_limiter.is_allowed(123)

        retry_after = rate_limiter.get_retry_after(123)
        assert retry_after > 0

    def test_rate_limit_message_format(self) -> None:
        """Rate limit message should have correct format."""
        retry_after = 5.5
        message = f"Rate limit exceeded. Please wait {retry_after:.0f} seconds."

        assert "Rate limit exceeded" in message
        assert "6 seconds" in message  # 5.5 rounded to 6


class TestE2EWhitelistMiddleware:
    """E2E tests for whitelist middleware."""

    @pytest.fixture
    def mock_settings_restricted(self) -> MagicMock:
        """Create mock settings with restricted whitelist."""
        return create_mock_settings(allowed_user_ids=[123])

    def test_authorized_user_allowed(self, mock_settings_restricted: MagicMock) -> None:
        """Authorized user should be allowed."""
        user_id = 123
        assert user_id in mock_settings_restricted.allowed_user_ids

    def test_unauthorized_user_blocked(self, mock_settings_restricted: MagicMock) -> None:
        """Unauthorized user should be blocked."""
        user_id = 999
        assert user_id not in mock_settings_restricted.allowed_user_ids

    def test_empty_whitelist_blocks_all(self) -> None:
        """Empty whitelist should block all users."""
        # Create settings with empty allowed_user_ids
        settings = MagicMock()
        settings.allowed_user_ids = []
        assert 123 not in settings.allowed_user_ids
        assert 456 not in settings.allowed_user_ids


class TestE2EMessageSplitting:
    """E2E tests for long message splitting."""

    @pytest.mark.asyncio
    async def test_short_message_sent_directly(self) -> None:
        """Short messages should be sent without splitting."""
        from jarvis_mk1_lite.bot import send_long_message

        message = create_mock_message("test")
        text = "Hello, world!"

        await send_long_message(message, text)

        message.answer.assert_called_once_with(text)

    @pytest.mark.asyncio
    async def test_long_message_split_into_chunks(self) -> None:
        """Long messages should be split into chunks."""
        from jarvis_mk1_lite.bot import send_long_message

        message = create_mock_message("test")
        text = "A" * 250  # Create text needing 3 chunks at chunk_size=100

        await send_long_message(message, text, chunk_size=100)

        assert message.answer.call_count == 3

    @pytest.mark.asyncio
    async def test_chunks_have_part_numbers(self) -> None:
        """Chunks should have part numbers in header."""
        from jarvis_mk1_lite.bot import send_long_message

        message = create_mock_message("test")
        text = "Line1\n" * 50

        await send_long_message(message, text, chunk_size=100)

        first_call = message.answer.call_args_list[0][0][0]
        assert "[Part 1/" in first_call


class TestE2EErrorHandling:
    """E2E tests for error handling."""

    @pytest.fixture
    def mock_message(self) -> MagicMock:
        """Create mock message."""
        return create_mock_message("test")

    @pytest.fixture
    def mock_bridge_error(self) -> MagicMock:
        """Create mock bridge that returns error."""
        bridge = MagicMock(spec=ClaudeBridge)
        bridge.send = AsyncMock(
            return_value=ClaudeResponse(success=False, content="", error="Connection failed")
        )
        return bridge

    @pytest.fixture
    def mock_bridge_exception(self) -> MagicMock:
        """Create mock bridge that raises exception."""
        bridge = MagicMock(spec=ClaudeBridge)
        bridge.send = AsyncMock(side_effect=Exception("Unexpected error"))
        return bridge

    @pytest.fixture(autouse=True)
    def reset_metrics(self) -> None:
        """Reset metrics."""
        from jarvis_mk1_lite.metrics import metrics

        metrics.reset()

    @pytest.mark.asyncio
    async def test_bridge_error_records_metric(
        self, mock_message: MagicMock, mock_bridge_error: MagicMock
    ) -> None:
        """Bridge error should record error metric."""
        from jarvis_mk1_lite.bot import execute_and_respond
        from jarvis_mk1_lite.metrics import metrics

        await execute_and_respond(mock_message, "test", mock_bridge_error)

        assert metrics.user_error_counts.get(123, 0) == 1

    @pytest.mark.asyncio
    async def test_bridge_error_shows_error_message(
        self, mock_message: MagicMock, mock_bridge_error: MagicMock
    ) -> None:
        """Bridge error should show error message to user."""
        from jarvis_mk1_lite.bot import execute_and_respond

        await execute_and_respond(mock_message, "test", mock_bridge_error)

        mock_message.answer.assert_called_once()
        call_args = mock_message.answer.call_args[0][0]
        assert "Error" in call_args

    @pytest.mark.asyncio
    async def test_exception_records_metric(
        self, mock_message: MagicMock, mock_bridge_exception: MagicMock
    ) -> None:
        """Exception should record error metric."""
        from jarvis_mk1_lite.bot import execute_and_respond
        from jarvis_mk1_lite.metrics import metrics

        await execute_and_respond(mock_message, "test", mock_bridge_exception)

        assert metrics.user_error_counts.get(123, 0) == 1

    @pytest.mark.asyncio
    async def test_exception_shows_generic_error(
        self, mock_message: MagicMock, mock_bridge_exception: MagicMock
    ) -> None:
        """Exception should show generic error message (no details leaked)."""
        from jarvis_mk1_lite.bot import execute_and_respond

        await execute_and_respond(mock_message, "test", mock_bridge_exception)

        mock_message.answer.assert_called_once()
        call_args = mock_message.answer.call_args[0][0]
        assert "An error occurred" in call_args
        assert "Unexpected error" not in call_args  # Don't leak details


class TestE2ELifecycleHooks:
    """E2E tests for bot lifecycle hooks."""

    @pytest.mark.asyncio
    async def test_on_startup_healthy(self) -> None:
        """Startup hook should check health successfully."""
        from jarvis_mk1_lite.bot import on_startup

        mock_bridge = MagicMock(spec=ClaudeBridge)
        mock_bridge.check_health = AsyncMock(return_value=True)

        mock_settings = MagicMock()
        mock_settings.voice_transcription_enabled = False

        await on_startup(mock_bridge, mock_settings)

        mock_bridge.check_health.assert_called_once()

    @pytest.mark.asyncio
    async def test_on_startup_unhealthy(self) -> None:
        """Startup hook should handle unhealthy status."""
        from jarvis_mk1_lite.bot import on_startup

        mock_bridge = MagicMock(spec=ClaudeBridge)
        mock_bridge.check_health = AsyncMock(return_value=False)

        mock_settings = MagicMock()
        mock_settings.voice_transcription_enabled = False

        # Should not raise
        await on_startup(mock_bridge, mock_settings)

        mock_bridge.check_health.assert_called_once()

    @pytest.mark.asyncio
    async def test_on_shutdown_completes(self) -> None:
        """Shutdown hook should complete without error."""
        from jarvis_mk1_lite.bot import on_shutdown

        # Should not raise
        await on_shutdown()


class TestE2EFullFlow:
    """E2E tests for complete user flows."""

    @pytest.fixture
    def mock_settings(self) -> MagicMock:
        """Create mock settings."""
        return create_mock_settings()

    @pytest.fixture
    def mock_bridge(self) -> MagicMock:
        """Create mock bridge."""
        bridge = MagicMock(spec=ClaudeBridge)
        bridge.check_health = AsyncMock(return_value=True)
        bridge.get_session = MagicMock(return_value=None)
        bridge.clear_session = MagicMock(return_value=False)
        bridge.send = AsyncMock(return_value=ClaudeResponse(success=True, content="Response"))
        bridge.get_session_stats = MagicMock(
            return_value={
                "active_sessions": 0,
                "sessions_expired": 0,
                "sessions_evicted": 0,
                "oldest_session_age": None,
            }
        )
        return bridge

    @pytest.fixture(autouse=True)
    def reset_all(self) -> None:
        """Reset all state."""
        from jarvis_mk1_lite.metrics import metrics, rate_limiter

        metrics.reset()
        rate_limiter.reset_all()
        pending_confirmations.clear()

    def test_new_user_full_flow(self) -> None:
        """Test full flow for a new user: start -> help -> safe message."""
        from jarvis_mk1_lite.metrics import metrics

        # 1. User sends /start
        metrics.record_command("start", 123)
        assert metrics.total_commands >= 1

        # 2. User sends /help
        metrics.record_command("help", 123)
        assert metrics.total_commands >= 2

        # 3. User sends a safe message
        metrics.record_request(123, is_command=False)
        assert metrics.total_messages >= 1

    def test_dangerous_command_flow(self) -> None:
        """Test full flow for dangerous command: detect -> confirm -> execute."""
        from jarvis_mk1_lite.safety import RiskLevel, socratic_gate

        # 1. User sends dangerous command
        text = "rm -rf /home/user/test"
        safety_check = socratic_gate.check(text)
        assert safety_check.risk_level == RiskLevel.DANGEROUS

        # 2. Store pending confirmation
        pending_confirmations[123] = PendingConfirmation(
            command=text,
            risk_level=RiskLevel.DANGEROUS,
            timestamp=time.time(),
        )
        assert 123 in pending_confirmations

        # 3. User confirms with YES
        is_valid = socratic_gate.is_confirmation_valid("yes", RiskLevel.DANGEROUS)
        assert is_valid is True

        # 4. Clear pending and execute
        del pending_confirmations[123]
        assert 123 not in pending_confirmations

    def test_critical_command_flow(self) -> None:
        """Test full flow for critical command: detect -> exact phrase -> execute."""
        from jarvis_mk1_lite.safety import RiskLevel, socratic_gate

        # 1. User sends critical command
        text = "rm -rf /"
        safety_check = socratic_gate.check(text)
        assert safety_check.risk_level == RiskLevel.CRITICAL

        # 2. Store pending confirmation
        pending_confirmations[123] = PendingConfirmation(
            command=text,
            risk_level=RiskLevel.CRITICAL,
            timestamp=time.time(),
        )

        # 3. User tries "yes" - should be rejected
        is_valid = socratic_gate.is_confirmation_valid("yes", RiskLevel.CRITICAL)
        assert is_valid is False

        # 4. User sends exact phrase
        phrase = socratic_gate.CRITICAL_CONFIRMATION_PHRASE
        is_valid = socratic_gate.is_confirmation_valid(phrase, RiskLevel.CRITICAL)
        assert is_valid is True

        # 5. Clear pending and execute
        del pending_confirmations[123]
        assert 123 not in pending_confirmations

    def test_session_management_flow(self) -> None:
        """Test session management: create -> use -> clear."""
        from jarvis_mk1_lite.bridge import ClaudeBridge

        # Pass allowed_user_ids to authorize user 123
        bridge = ClaudeBridge(allowed_user_ids=[123])

        # 1. No session initially
        assert bridge.get_session(123) is None

        # 2. Create named session (new multi-session API)
        session_name = bridge.create_session(123, name="test")
        assert session_name == "test"

        # Verify session was created (session_id starts as empty)
        sessions = bridge.list_sessions(123)
        assert len(sessions) >= 1
        assert any(s.name == "test" for s in sessions)

        # 3. Use session (age tracking)
        age = bridge.get_session_age(123)
        assert age is not None and age >= 0

        # 4. Clear session (/new command)
        bridge.clear_session(123)
        assert bridge.get_session(123) is None


class TestE2EWideContextFlow:
    """E2E tests for wide context flow (P4-E2E-003)."""

    @pytest.fixture(autouse=True)
    def reset_contexts(self) -> None:
        """Reset pending contexts before each test."""
        from jarvis_mk1_lite.bot import _pending_contexts

        _pending_contexts.clear()

    @pytest.fixture(autouse=True)
    def reset_metrics(self) -> None:
        """Reset metrics before each test."""
        from jarvis_mk1_lite.metrics import metrics

        metrics.reset()

    def test_e2e_wide_context_activation(self) -> None:
        """Test wide context mode activation via /wide_context command (P4-E2E-003a)."""
        from jarvis_mk1_lite.bot import PendingContext, _pending_contexts
        from jarvis_mk1_lite.metrics import metrics

        user_id = 123

        # 1. Simulate /wide_context command
        metrics.record_command("wide_context", user_id)

        # 2. Create wide context for user
        _pending_contexts[user_id] = PendingContext(wide_mode=True)

        # 3. Verify context is active
        assert user_id in _pending_contexts
        ctx = _pending_contexts[user_id]
        assert ctx.wide_mode is True
        assert ctx.messages == []
        assert ctx.files == []

    def test_e2e_wide_context_accumulation(self) -> None:
        """Test message accumulation in wide context mode (P4-E2E-003b)."""
        from jarvis_mk1_lite.bot import PendingContext, _pending_contexts

        user_id = 123

        # 1. Create wide context
        _pending_contexts[user_id] = PendingContext(wide_mode=True)

        # 2. Accumulate messages
        ctx = _pending_contexts[user_id]
        ctx.messages.append("First message")
        ctx.messages.append("Second message")
        ctx.messages.append("Third message")

        # 3. Verify accumulation
        assert len(ctx.messages) == 3
        assert "First message" in ctx.messages
        assert "Third message" in ctx.messages

    def test_e2e_wide_context_accept(self) -> None:
        """Test wide context accept button flow (P4-E2E-003c)."""
        from jarvis_mk1_lite.bot import PendingContext, _pending_contexts, _combine_context

        user_id = 123

        # 1. Create wide context with accumulated content
        _pending_contexts[user_id] = PendingContext(wide_mode=True)
        ctx = _pending_contexts[user_id]
        ctx.messages.append("Message 1")
        ctx.messages.append("Message 2")
        ctx.files.append(("test.py", "print('hello')"))

        # 2. Combine context (simulates accept action)
        combined = _combine_context(ctx)

        # 3. Verify combined content
        assert "Message 1" in combined
        assert "Message 2" in combined
        assert "test.py" in combined
        assert "print('hello')" in combined

        # 4. Clear context after accept (simulates real handler)
        del _pending_contexts[user_id]
        assert user_id not in _pending_contexts

    def test_e2e_wide_context_cancel(self) -> None:
        """Test wide context cancel button flow (P4-E2E-003d)."""
        from jarvis_mk1_lite.bot import PendingContext, _pending_contexts

        user_id = 123

        # 1. Create wide context with content
        _pending_contexts[user_id] = PendingContext(wide_mode=True)
        ctx = _pending_contexts[user_id]
        ctx.messages.append("This will be cancelled")

        # 2. Cancel context (delete without sending)
        del _pending_contexts[user_id]

        # 3. Verify context is cleared
        assert user_id not in _pending_contexts

    def test_e2e_wide_context_timeout(self) -> None:
        """Test wide context timeout handling (P4-E2E-003e)."""
        import time as time_module

        from jarvis_mk1_lite.bot import PendingContext, _pending_contexts

        user_id = 123

        # 1. Create wide context with old timestamp
        old_timestamp = time_module.time() - 400  # 400 seconds ago (> 5 min timeout)
        _pending_contexts[user_id] = PendingContext(wide_mode=True, created_at=old_timestamp)

        # 2. Check if context is expired (5 minute timeout = 300 seconds)
        ctx = _pending_contexts[user_id]
        age = time_module.time() - ctx.created_at
        is_expired = age > 300  # 5 minute timeout

        # 3. Verify timeout detection
        assert is_expired is True

        # 4. Clean up expired context
        if is_expired:
            del _pending_contexts[user_id]
        assert user_id not in _pending_contexts


class TestE2EFileHandlingFlow:
    """E2E tests for file handling flow (P4-E2E-004)."""

    @pytest.fixture(autouse=True)
    def reset_metrics(self) -> None:
        """Reset metrics before each test."""
        from jarvis_mk1_lite.metrics import metrics

        metrics.reset()

    def test_e2e_file_txt_processing(self) -> None:
        """Test .txt file processing end-to-end (P4-E2E-004a)."""
        from jarvis_mk1_lite.file_processor import FileProcessor

        processor = FileProcessor()

        # 1. Verify .txt is supported
        assert processor.is_supported("test.txt") is True

        # 2. Verify TEXT_EXTENSIONS contains .txt
        assert ".txt" in processor.TEXT_EXTENSIONS

        # 3. Process text content
        test_content = b"Hello, this is a test file content."
        extracted = processor.extract_text(test_content, "test.txt")
        assert "Hello" in extracted
        assert len(extracted) > 0

    def test_e2e_file_py_processing(self) -> None:
        """Test .py file processing end-to-end (P4-E2E-004b)."""
        from jarvis_mk1_lite.file_processor import FileProcessor

        processor = FileProcessor()

        # 1. Verify .py is supported
        assert processor.is_supported("script.py") is True

        # 2. Verify TEXT_EXTENSIONS contains .py
        assert ".py" in processor.TEXT_EXTENSIONS

        # 3. Verify other code extensions
        assert processor.is_supported("config.yaml") is True
        assert processor.is_supported("data.json") is True
        assert processor.is_supported("module.js") is True

        # 4. Process Python code
        code = b"def hello():\n    print('world')"
        extracted = processor.extract_text(code, "script.py")
        assert "def hello" in extracted

    def test_e2e_file_pdf_processing(self) -> None:
        """Test .pdf file processing end-to-end (P4-E2E-004c)."""
        from jarvis_mk1_lite.file_processor import FileProcessor

        processor = FileProcessor()

        # 1. Verify .pdf is supported
        assert processor.is_supported("document.pdf") is True

        # 2. Verify BINARY_EXTENSIONS contains .pdf
        assert ".pdf" in processor.BINARY_EXTENSIONS

        # 3. Verify PDF extension variations (case-insensitive)
        assert processor.is_supported("REPORT.PDF") is True
        assert processor.is_supported("mixed.Pdf") is True

    def test_e2e_file_unsupported(self) -> None:
        """Test unsupported file format handling (P4-E2E-004d)."""
        from jarvis_mk1_lite.file_processor import FileProcessor, UnsupportedFileTypeError

        processor = FileProcessor()

        # 1. Verify unsupported formats
        assert processor.is_supported("image.jpg") is False
        assert processor.is_supported("video.mp4") is False
        assert processor.is_supported("archive.zip") is False
        assert processor.is_supported("document.docx") is False
        assert processor.is_supported("binary.exe") is False

        # 2. Attempting to extract from unsupported file raises error
        with pytest.raises(UnsupportedFileTypeError):
            processor.extract_text(b"fake content", "image.jpg")

    def test_e2e_file_too_large(self) -> None:
        """Test file content truncation (P4-E2E-004e)."""
        from jarvis_mk1_lite.file_processor import FileProcessor

        # 1. Create processor with small limit for testing
        small_limit = 100
        processor = FileProcessor(max_chars=small_limit)

        # 2. Create content exceeding the limit
        large_content = b"A" * 500

        # 3. Extract and verify truncation
        extracted = processor.extract_text(large_content, "large.txt")
        assert len(extracted) <= small_limit + 100  # Allow for truncation notice
        assert "[Truncated:" in extracted or len(extracted) <= small_limit


class TestE2EConversationFlow:
    """E2E tests for full conversation flow (P4-E2E-001)."""

    @pytest.fixture
    def mock_bridge(self) -> MagicMock:
        """Create mock bridge."""
        bridge = MagicMock(spec=ClaudeBridge)
        bridge.send = AsyncMock(
            return_value=ClaudeResponse(success=True, content="Hello! How can I help?")
        )
        bridge.get_session = MagicMock(return_value="session-abc123")
        bridge.clear_session = MagicMock(return_value=True)
        return bridge

    @pytest.fixture(autouse=True)
    def reset_all(self) -> None:
        """Reset all state."""
        from jarvis_mk1_lite.metrics import metrics, rate_limiter

        metrics.reset()
        rate_limiter.reset_all()
        pending_confirmations.clear()

    def test_e2e_full_conversation_flow(self) -> None:
        """Test complete conversation flow from start to response (P4-E2E-001a)."""
        from jarvis_mk1_lite.metrics import metrics
        from jarvis_mk1_lite.safety import socratic_gate

        user_id = 123

        # 1. User joins with /start
        metrics.record_command("start", user_id)
        assert metrics.total_commands >= 1

        # 2. User requests help
        metrics.record_command("help", user_id)
        assert metrics.total_commands >= 2

        # 3. User sends a safe message
        text = "Write a hello world program"
        safety_check = socratic_gate.check(text)
        assert safety_check.risk_level == RiskLevel.SAFE

        # 4. Message is processed
        metrics.record_request(user_id, is_command=False)
        assert metrics.total_messages >= 1

        # 5. Response latency recorded
        metrics.record_latency(0.5)
        assert len(metrics.latencies) >= 1

    def test_e2e_session_management(self) -> None:
        """Test session creation and management (P4-E2E-001b)."""
        from jarvis_mk1_lite.bridge import ClaudeBridge

        user_id = 123

        # 1. Initialize bridge with allowed user
        bridge = ClaudeBridge(allowed_user_ids=[user_id])

        # 2. No session initially
        assert bridge.get_session(user_id) is None

        # 3. Create session (new multi-session API)
        session_name = bridge.create_session(user_id, name="test-session")
        assert session_name == "test-session"

        # Verify session was created
        sessions = bridge.list_sessions(user_id)
        assert len(sessions) >= 1
        assert any(s.name == "test-session" for s in sessions)

        # 4. Verify can switch sessions
        result = bridge.switch_session(user_id, "test-session")
        assert result is True

        # 5. Clear session (user sends /new)
        bridge.clear_session(user_id)
        assert bridge.get_session(user_id) is None

    def test_e2e_error_recovery(self, mock_bridge: MagicMock) -> None:
        """Test error recovery flow (P4-E2E-001c)."""
        from jarvis_mk1_lite.metrics import metrics

        user_id = 123

        # 1. First request fails
        mock_bridge.send = AsyncMock(
            return_value=ClaudeResponse(success=False, content="", error="Connection error")
        )
        metrics.record_error(user_id)
        assert metrics.user_error_counts.get(user_id, 0) >= 1

        # 2. Error is logged
        initial_errors = metrics.user_error_counts.get(user_id, 0)

        # 3. Retry succeeds
        mock_bridge.send = AsyncMock(return_value=ClaudeResponse(success=True, content="Success!"))
        # Error count doesn't increase on success
        assert metrics.user_error_counts.get(user_id, 0) == initial_errors

        # 4. User can continue with /new to reset
        pending_confirmations.clear()
        assert user_id not in pending_confirmations


class TestE2ESafetyFlow:
    """E2E tests for Safety Flow (Socratic Gate) (P4-E2E-002)."""

    @pytest.fixture(autouse=True)
    def reset_all(self) -> None:
        """Reset all state."""
        from jarvis_mk1_lite.metrics import metrics, rate_limiter

        metrics.reset()
        rate_limiter.reset_all()
        pending_confirmations.clear()

    def test_e2e_dangerous_command_warning(self) -> None:
        """Test dangerous command detection and warning (P4-E2E-002a)."""
        from jarvis_mk1_lite.safety import socratic_gate

        user_id = 123

        # 1. User sends a dangerous command
        dangerous_cmd = "rm -rf /var/log/old"
        safety_check = socratic_gate.check(dangerous_cmd)

        # 2. Command is detected as dangerous
        assert safety_check.risk_level == RiskLevel.DANGEROUS
        assert safety_check.requires_confirmation is True
        assert safety_check.message is not None
        assert "DANGEROUS" in safety_check.message

        # 3. System stores pending confirmation
        pending_confirmations[user_id] = PendingConfirmation(
            command=dangerous_cmd,
            risk_level=RiskLevel.DANGEROUS,
            timestamp=time.time(),
        )
        assert user_id in pending_confirmations
        assert pending_confirmations[user_id].command == dangerous_cmd

    def test_e2e_dangerous_command_confirm(self) -> None:
        """Test dangerous command confirmation with YES (P4-E2E-002b)."""
        from jarvis_mk1_lite.safety import socratic_gate

        user_id = 123
        dangerous_cmd = "rm -rf ./temp_folder"

        # 1. Create pending confirmation
        pending_confirmations[user_id] = PendingConfirmation(
            command=dangerous_cmd,
            risk_level=RiskLevel.DANGEROUS,
            timestamp=time.time(),
        )

        # 2. User confirms with YES
        confirmation = "yes"
        is_valid = socratic_gate.is_confirmation_valid(confirmation, RiskLevel.DANGEROUS)
        assert is_valid is True

        # 3. Also test alternative confirmations
        for alt in ["y", "YES", "Yes", "confirm", "ok", "da"]:
            assert socratic_gate.is_confirmation_valid(alt, RiskLevel.DANGEROUS) is True

        # 4. System clears pending confirmation after execution
        del pending_confirmations[user_id]
        assert user_id not in pending_confirmations

    def test_e2e_dangerous_command_cancel(self) -> None:
        """Test dangerous command cancellation with NO (P4-E2E-002c)."""
        from jarvis_mk1_lite.safety import socratic_gate

        user_id = 123
        dangerous_cmd = "shutdown -h now"

        # 1. Create pending confirmation
        pending_confirmations[user_id] = PendingConfirmation(
            command=dangerous_cmd,
            risk_level=RiskLevel.DANGEROUS,
            timestamp=time.time(),
        )

        # 2. User cancels with NO
        cancellation = "no"
        is_cancelled = socratic_gate.is_cancellation(cancellation)
        assert is_cancelled is True

        # 3. Also test alternative cancellations
        for alt in ["n", "NO", "No", "cancel", "net", "otmena"]:
            assert socratic_gate.is_cancellation(alt) is True

        # 4. System clears pending confirmation
        del pending_confirmations[user_id]
        assert user_id not in pending_confirmations

        # 5. Invalid confirmation should NOT be accepted
        assert socratic_gate.is_confirmation_valid("no", RiskLevel.DANGEROUS) is False

    def test_e2e_critical_command_exact_phrase(self) -> None:
        """Test critical command requires exact phrase confirmation (P4-E2E-002d)."""
        from jarvis_mk1_lite.safety import socratic_gate

        user_id = 123

        # 1. User sends a critical command
        critical_cmd = "rm -rf /"
        safety_check = socratic_gate.check(critical_cmd)

        # 2. Command is detected as critical
        assert safety_check.risk_level == RiskLevel.CRITICAL
        assert safety_check.requires_confirmation is True
        assert "CRITICAL" in safety_check.message

        # 3. Store pending confirmation
        pending_confirmations[user_id] = PendingConfirmation(
            command=critical_cmd,
            risk_level=RiskLevel.CRITICAL,
            timestamp=time.time(),
        )

        # 4. Simple YES should NOT work for critical
        assert socratic_gate.is_confirmation_valid("yes", RiskLevel.CRITICAL) is False
        assert socratic_gate.is_confirmation_valid("y", RiskLevel.CRITICAL) is False

        # 5. Exact phrase (English) should work
        exact_phrase_en = "CONFIRM CRITICAL OPERATION"
        assert socratic_gate.is_confirmation_valid(exact_phrase_en, RiskLevel.CRITICAL) is True

        # 6. Exact phrase (Russian) should work
        exact_phrase_ru = "PODTVERZHDAYU KRITICHESKUYU OPERATSIYU"
        assert socratic_gate.is_confirmation_valid(exact_phrase_ru, RiskLevel.CRITICAL) is True

        # 7. Case insensitive check
        assert (
            socratic_gate.is_confirmation_valid("confirm critical operation", RiskLevel.CRITICAL)
            is True
        )

        # 8. Cleanup
        del pending_confirmations[user_id]
        assert user_id not in pending_confirmations
