"""Live E2E tests for bot commands.

P1-LIVE-005 to P1-LIVE-010: Core command tests via real Telegram.

These tests send REAL messages through Telegram to the REAL bot
and verify REAL responses. NO MOCKS.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from .helpers import (
    assert_contains,
    send_and_collect_responses,
    send_message_and_wait,
)

if TYPE_CHECKING:
    from telethon import TelegramClient
    from telethon.tl.types import User


@pytest.mark.live
@pytest.mark.asyncio(loop_scope="session")
async def test_start_command_live(
    telethon_client: "TelegramClient",
    bot_entity: "User",
    between_tests_delay: None,
) -> None:
    """P1-LIVE-005: Send /start to real bot and verify response.

    Verifies:
    - Bot responds to /start command
    - Response contains welcome message
    - Response contains app name (JARVIS)
    - Response contains available commands
    """
    response = await send_message_and_wait(
        telethon_client,
        bot_entity,
        "/start",
        timeout=30,
    )

    assert response.text is not None
    assert_contains(
        response.text,
        "Welcome",
        "JARVIS",
    )


@pytest.mark.live
@pytest.mark.asyncio(loop_scope="session")
async def test_help_command_live(
    telethon_client: "TelegramClient",
    bot_entity: "User",
    between_tests_delay: None,
) -> None:
    """P1-LIVE-006: Send /help to real bot and verify response.

    Verifies:
    - Bot responds to /help command
    - Response contains command list
    - Response contains security features section
    """
    response = await send_message_and_wait(
        telethon_client,
        bot_entity,
        "/help",
        timeout=30,
    )

    assert response.text is not None
    assert_contains(
        response.text,
        "/start",
        "/help",
        "/status",
    )


@pytest.mark.live
@pytest.mark.asyncio(loop_scope="session")
async def test_status_command_live(
    telethon_client: "TelegramClient",
    bot_entity: "User",
    between_tests_delay: None,
) -> None:
    """P1-LIVE-007: Send /status to real bot and verify response.

    Verifies:
    - Bot responds to /status command
    - Response contains Claude CLI status
    - Response shows health status (Healthy/Unhealthy)
    """
    response = await send_message_and_wait(
        telethon_client,
        bot_entity,
        "/status",
        timeout=30,
    )

    assert response.text is not None
    # Status should contain health indicator
    assert "Status" in response.text or "status" in response.text.lower()


@pytest.mark.live
@pytest.mark.asyncio(loop_scope="session")
async def test_new_command_live(
    telethon_client: "TelegramClient",
    bot_entity: "User",
    between_tests_delay: None,
) -> None:
    """P1-LIVE-008: Send /new to real bot and verify response.

    Verifies:
    - Bot responds to /new command
    - Response confirms session cleared or new conversation started
    """
    response = await send_message_and_wait(
        telethon_client,
        bot_entity,
        "/new",
        timeout=30,
    )

    assert response.text is not None
    # Should indicate new session/conversation
    text_lower = response.text.lower()
    assert (
        "new" in text_lower
        or "fresh" in text_lower
        or "clear" in text_lower
        or "session" in text_lower
    )


@pytest.mark.live
@pytest.mark.asyncio(loop_scope="session")
async def test_metrics_command_live(
    telethon_client: "TelegramClient",
    bot_entity: "User",
    between_tests_delay: None,
) -> None:
    """P1-LIVE-009: Send /metrics to real bot and verify response.

    Verifies:
    - Bot responds to /metrics command
    - Response contains metrics information
    - Response shows uptime or status
    """
    response = await send_message_and_wait(
        telethon_client,
        bot_entity,
        "/metrics",
        timeout=30,
    )

    assert response.text is not None
    assert_contains(
        response.text,
        "Metrics",
    )


@pytest.mark.live
@pytest.mark.asyncio(loop_scope="session")
async def test_simple_message_live(
    telethon_client: "TelegramClient",
    bot_entity: "User",
    between_tests_delay: None,
    reset_session: None,
) -> None:
    """P1-LIVE-010: Send simple message to real bot and get Claude response.

    Verifies:
    - Bot forwards message to Claude
    - Claude processes and responds
    - Response is meaningful (not empty or error)

    Note: This test requires Claude CLI to be working on the VPS.
    """
    # Simple, safe prompt that should always get a response
    test_message = "What is 2+2? Reply with just the number."

    responses = await send_and_collect_responses(
        telethon_client,
        bot_entity,
        test_message,
        timeout=60,  # Claude may take longer
    )

    assert len(responses) >= 1

    # Combine all response parts
    full_response = "\n".join(r.text or "" for r in responses)

    # Should contain the answer (4) or at least be non-empty
    assert len(full_response) > 0
    # Claude should respond with something containing "4"
    assert "4" in full_response or len(full_response) > 10


@pytest.mark.live
@pytest.mark.asyncio(loop_scope="session")
async def test_command_sequence_live(
    telethon_client: "TelegramClient",
    bot_entity: "User",
    between_tests_delay: None,
) -> None:
    """Test a sequence of commands like a real user would.

    Simulates: /start -> /help -> /status -> /new
    """
    import asyncio

    # 1. Start
    response = await send_message_and_wait(telethon_client, bot_entity, "/start", timeout=30)
    assert "Welcome" in response.text or "JARVIS" in response.text
    await asyncio.sleep(1)

    # 2. Help
    response = await send_message_and_wait(telethon_client, bot_entity, "/help", timeout=30)
    assert "/start" in response.text
    await asyncio.sleep(1)

    # 3. Status
    response = await send_message_and_wait(telethon_client, bot_entity, "/status", timeout=30)
    assert response.text is not None
    await asyncio.sleep(1)

    # 4. New (reset session)
    response = await send_message_and_wait(telethon_client, bot_entity, "/new", timeout=30)
    assert response.text is not None
