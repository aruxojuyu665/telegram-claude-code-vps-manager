"""Unit tests for retry logic.

P1-UNIT-002: Tests for send_with_retry function and error handling.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramNetworkError,
    TelegramRetryAfter,
)

from jarvis_mk1_lite.bot import send_with_retry


class TestSendWithRetry:
    """Tests for send_with_retry function."""

    @pytest.mark.asyncio
    async def test_success_on_first_attempt(self):
        """Test successful send on first attempt."""
        mock_result = MagicMock()
        send_func = AsyncMock(return_value=mock_result)

        result = await send_with_retry(send_func)

        assert result is mock_result
        send_func.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_retry_after_network_error(self):
        """Test retry after TelegramNetworkError."""
        mock_result = MagicMock()
        send_func = AsyncMock(
            side_effect=[
                TelegramNetworkError(method=MagicMock(), message="Network error"),
                mock_result,
            ]
        )

        result = await send_with_retry(send_func, max_retries=3, base_delay=0.01)

        assert result is mock_result
        assert send_func.await_count == 2

    @pytest.mark.asyncio
    async def test_retry_after_rate_limit(self):
        """Test retry after TelegramRetryAfter."""
        mock_result = MagicMock()

        # Create a proper TelegramRetryAfter exception
        retry_error = TelegramRetryAfter(
            method=MagicMock(),
            message="Flood control",
            retry_after=0.01,  # Very short for testing
        )

        send_func = AsyncMock(
            side_effect=[
                retry_error,
                mock_result,
            ]
        )

        result = await send_with_retry(send_func, max_retries=3)

        assert result is mock_result
        assert send_func.await_count == 2

    @pytest.mark.asyncio
    async def test_returns_none_on_message_not_modified(self):
        """Test returns None for 'message is not modified' error."""
        error = TelegramBadRequest(
            method=MagicMock(),
            message="message is not modified",
        )
        send_func = AsyncMock(side_effect=error)

        result = await send_with_retry(send_func)

        assert result is None
        send_func.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_none_on_message_not_found(self):
        """Test returns None for 'message to edit not found' error."""
        error = TelegramBadRequest(
            method=MagicMock(),
            message="message to edit not found",
        )
        send_func = AsyncMock(side_effect=error)

        result = await send_with_retry(send_func)

        assert result is None
        send_func.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_raises_on_markdown_error(self):
        """Test raises for 'can't parse entities' error."""
        error = TelegramBadRequest(
            method=MagicMock(),
            message="can't parse entities",
        )
        send_func = AsyncMock(side_effect=error)

        with pytest.raises(TelegramBadRequest):
            await send_with_retry(send_func)

    @pytest.mark.asyncio
    async def test_returns_none_on_other_bad_request(self):
        """Test returns None for other TelegramBadRequest errors."""
        error = TelegramBadRequest(
            method=MagicMock(),
            message="some other error",
        )
        send_func = AsyncMock(side_effect=error)

        result = await send_with_retry(send_func)

        assert result is None

    @pytest.mark.asyncio
    async def test_max_retries_exceeded(self):
        """Test that function gives up after max retries."""
        send_func = AsyncMock(
            side_effect=TelegramNetworkError(
                method=MagicMock(),
                message="Network error",
            )
        )

        result = await send_with_retry(send_func, max_retries=2, base_delay=0.01)

        assert result is None
        assert send_func.await_count == 3  # Initial + 2 retries

    @pytest.mark.asyncio
    async def test_exponential_backoff(self):
        """Test that delays increase exponentially."""
        import time

        call_times: list[float] = []

        async def tracking_func():
            call_times.append(time.time())
            raise TelegramNetworkError(
                method=MagicMock(),
                message="Network error",
            )

        await send_with_retry(tracking_func, max_retries=2, base_delay=0.05)

        # Check that delays approximately double
        if len(call_times) >= 3:
            delay1 = call_times[1] - call_times[0]
            delay2 = call_times[2] - call_times[1]
            # Second delay should be approximately 2x the first
            assert delay2 > delay1 * 1.5  # Allow some margin

    @pytest.mark.asyncio
    async def test_respects_custom_max_retries(self):
        """Test custom max_retries parameter."""
        send_func = AsyncMock(
            side_effect=TelegramNetworkError(
                method=MagicMock(),
                message="Network error",
            )
        )

        await send_with_retry(send_func, max_retries=5, base_delay=0.01)

        assert send_func.await_count == 6  # Initial + 5 retries

    @pytest.mark.asyncio
    async def test_respects_custom_base_delay(self):
        """Test custom base_delay parameter."""
        import time

        start = time.time()

        send_func = AsyncMock(
            side_effect=TelegramNetworkError(
                method=MagicMock(),
                message="Network error",
            )
        )

        await send_with_retry(send_func, max_retries=1, base_delay=0.1)

        elapsed = time.time() - start
        # Should have waited at least 0.1 seconds
        assert elapsed >= 0.1
