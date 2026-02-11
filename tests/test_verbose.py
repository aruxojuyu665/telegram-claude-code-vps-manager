"""Unit tests for verbose mode functionality.

P1-UNIT-001: Tests for VerboseContext, toggle, formatting, and batching.
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from jarvis_mk1_lite.bot import (
    MAX_VERBOSE_USERS,
    VerboseContext,
    _format_verbose_line,
    _verbose_contexts,
    _verbose_users,
    add_verbose_line,
    finalize_verbose_context,
    flush_verbose_context,
    is_verbose_enabled,
    toggle_verbose,
)


@pytest.fixture(autouse=True)
def cleanup_verbose_state():
    """Clean up verbose state before and after each test."""
    _verbose_users.clear()
    _verbose_contexts.clear()
    yield
    _verbose_users.clear()
    _verbose_contexts.clear()


class TestToggleVerbose:
    """Tests for toggle_verbose function."""

    def test_toggle_enables_verbose(self):
        """Test that toggle enables verbose for new user."""
        user_id = 12345

        result = toggle_verbose(user_id)

        assert result is True
        assert is_verbose_enabled(user_id)
        assert user_id in _verbose_users

    def test_toggle_disables_verbose(self):
        """Test that toggle disables verbose when already enabled."""
        user_id = 12345
        _verbose_users[user_id] = time.time()

        result = toggle_verbose(user_id)

        assert result is False
        assert not is_verbose_enabled(user_id)
        assert user_id not in _verbose_users

    def test_toggle_cleans_up_context(self):
        """Test that disabling verbose cleans up context."""
        user_id = 12345
        _verbose_users[user_id] = time.time()
        _verbose_contexts[user_id] = VerboseContext(lines=["test"])

        toggle_verbose(user_id)

        assert user_id not in _verbose_contexts

    def test_toggle_enforces_max_users_limit(self):
        """Test that max users limit is enforced with LRU eviction."""
        # Fill up to max with staggered timestamps
        for i in range(MAX_VERBOSE_USERS):
            _verbose_users[i] = time.time() + i * 0.001

        # Add one more
        new_user_id = 99999
        result = toggle_verbose(new_user_id)

        assert result is True
        assert is_verbose_enabled(new_user_id)
        # Should have evicted one user
        assert len(_verbose_users) == MAX_VERBOSE_USERS


class TestIsVerboseEnabled:
    """Tests for is_verbose_enabled function."""

    def test_returns_false_for_disabled_user(self):
        """Test returns False when user not in verbose mode."""
        assert is_verbose_enabled(12345) is False

    def test_returns_true_for_enabled_user(self):
        """Test returns True when user is in verbose mode."""
        _verbose_users[12345] = time.time()
        assert is_verbose_enabled(12345) is True


class TestFormatVerboseLine:
    """Tests for _format_verbose_line function."""

    def test_formats_regular_line(self):
        """Test formatting a regular line."""
        result = _format_verbose_line("Hello world")
        assert result == "`Hello world`"

    def test_skips_empty_line(self):
        """Test that empty lines return None."""
        assert _format_verbose_line("") is None
        assert _format_verbose_line("   ") is None

    def test_skips_json_lines(self):
        """Test that JSON lines are skipped."""
        assert _format_verbose_line('{"type": "test"}') is None
        assert _format_verbose_line('[{"item": 1}]') is None

    def test_truncates_long_lines(self):
        """Test that long lines are truncated."""
        long_line = "x" * 150
        result = _format_verbose_line(long_line, max_length=100)

        assert result is not None
        assert len(result) <= 102  # 100 chars + backticks
        assert result.endswith("...`")

    def test_respects_custom_max_length(self):
        """Test custom max_length parameter."""
        line = "x" * 50
        result = _format_verbose_line(line, max_length=20)

        assert result is not None
        assert "..." in result


class TestVerboseContext:
    """Tests for VerboseContext dataclass."""

    def test_default_values(self):
        """Test default values are set correctly."""
        ctx = VerboseContext()

        assert ctx.lines == []
        assert ctx.status_message is None
        assert ctx.total_actions == 0
        assert ctx.last_flush_time > 0

    def test_can_set_values(self):
        """Test values can be set."""
        msg = MagicMock()
        ctx = VerboseContext(
            lines=["line1", "line2"],
            status_message=msg,
            total_actions=5,
        )

        assert ctx.lines == ["line1", "line2"]
        assert ctx.status_message is msg
        assert ctx.total_actions == 5


class TestFlushVerboseContext:
    """Tests for flush_verbose_context function."""

    @pytest.mark.asyncio
    async def test_flush_does_nothing_for_nonexistent_user(self):
        """Test flush does nothing if user has no context."""
        message = MagicMock()
        await flush_verbose_context(99999, message)
        # Should not raise

    @pytest.mark.asyncio
    async def test_flush_does_nothing_for_empty_lines(self):
        """Test flush does nothing if lines are empty."""
        user_id = 12345
        _verbose_contexts[user_id] = VerboseContext(lines=[])
        message = MagicMock()

        await flush_verbose_context(user_id, message)
        # Should not send any message

    @pytest.mark.asyncio
    async def test_flush_sends_message_when_force(self):
        """Test flush sends message when force=True."""
        user_id = 12345
        message = MagicMock()
        message.answer = AsyncMock(return_value=MagicMock())

        _verbose_contexts[user_id] = VerboseContext(lines=["`test line`"])

        with patch("jarvis_mk1_lite.bot.send_with_retry") as mock_retry:
            mock_retry.return_value = message

            await flush_verbose_context(user_id, message, force=True)

            mock_retry.assert_called_once()


class TestAddVerboseLine:
    """Tests for add_verbose_line function."""

    @pytest.mark.asyncio
    async def test_does_nothing_if_not_enabled(self):
        """Test that nothing happens if verbose is not enabled."""
        message = MagicMock()

        await add_verbose_line(12345, "test line", message)

        assert 12345 not in _verbose_contexts

    @pytest.mark.asyncio
    async def test_creates_context_if_needed(self):
        """Test that context is created if it doesn't exist."""
        user_id = 12345
        _verbose_users[user_id] = time.time()
        message = MagicMock()
        message.answer = AsyncMock()

        await add_verbose_line(user_id, "test line", message)

        assert user_id in _verbose_contexts

    @pytest.mark.asyncio
    async def test_increments_action_counter(self):
        """Test that total_actions is incremented."""
        user_id = 12345
        _verbose_users[user_id] = time.time()
        message = MagicMock()
        message.answer = AsyncMock()

        await add_verbose_line(user_id, "line 1", message)
        await add_verbose_line(user_id, "line 2", message)

        ctx = _verbose_contexts[user_id]
        assert ctx.total_actions == 2


class TestFinalizeVerboseContext:
    """Tests for finalize_verbose_context function."""

    @pytest.mark.asyncio
    async def test_does_nothing_if_no_context(self):
        """Test finalize does nothing if no context exists."""
        message = MagicMock()

        await finalize_verbose_context(99999, message)
        # Should not raise

    @pytest.mark.asyncio
    async def test_cleans_up_context(self):
        """Test that context is cleaned up after finalize."""
        user_id = 12345
        _verbose_contexts[user_id] = VerboseContext()
        message = MagicMock()

        await finalize_verbose_context(user_id, message)

        assert user_id not in _verbose_contexts
