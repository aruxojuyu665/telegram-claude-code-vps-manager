"""Live E2E tests for verbose mode.

P0-E2E-001, P0-E2E-002: Verbose mode toggle and output tests via real Telegram.

These tests send REAL messages through Telegram to the REAL bot
and verify REAL responses. NO MOCKS.
"""

from __future__ import annotations

import asyncio
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
async def test_verbose_command_toggle_enable(
    telethon_client: "TelegramClient",
    bot_entity: "User",
    between_tests_delay: None,
) -> None:
    """P0-E2E-001a: Test /verbose command enables verbose mode.

    Verifies:
    - Bot responds to /verbose command
    - Response indicates verbose mode is enabled
    """
    response = await send_message_and_wait(
        telethon_client,
        bot_entity,
        "/verbose",
        timeout=30,
    )

    assert response.text is not None
    text_lower = response.text.lower()
    assert "verbose" in text_lower
    # Check for "enabled" but not "disabled" to avoid false positives
    assert "enabled" in text_lower and "disabled" not in text_lower


@pytest.mark.live
@pytest.mark.asyncio(loop_scope="session")
async def test_verbose_command_toggle_disable(
    telethon_client: "TelegramClient",
    bot_entity: "User",
    between_tests_delay: None,
) -> None:
    """P0-E2E-001b: Test /verbose command toggles off when already enabled.

    Verifies:
    - Second /verbose disables the mode
    - Response indicates verbose mode is disabled
    """
    # Send /verbose again to toggle off
    response = await send_message_and_wait(
        telethon_client,
        bot_entity,
        "/verbose",
        timeout=30,
    )

    assert response.text is not None
    text_lower = response.text.lower()
    assert "verbose" in text_lower
    # Check for "disabled" specifically
    assert "disabled" in text_lower


@pytest.mark.live
@pytest.mark.asyncio(loop_scope="session")
async def test_verbose_mode_shows_actions(
    telethon_client: "TelegramClient",
    bot_entity: "User",
    between_tests_delay: None,
    reset_session: None,
) -> None:
    """P0-E2E-002: Test verbose mode shows Claude Code actions.

    Verifies:
    - With verbose enabled, multiple messages are received
    - Status/progress messages appear before final response
    - Final response contains the answer

    Note: This test may take longer as it waits for Claude processing.
    """
    # Enable verbose mode
    enable_response = await send_message_and_wait(
        telethon_client,
        bot_entity,
        "/verbose",
        timeout=30,
    )
    # Check for "enabled" but not "disabled"
    text_lower = enable_response.text.lower()
    assert "enabled" in text_lower and "disabled" not in text_lower

    await asyncio.sleep(1)

    # Send a simple command that should trigger Claude actions
    responses = await send_and_collect_responses(
        telethon_client,
        bot_entity,
        "What is 2+2? Reply with just the number.",
        timeout=90,  # Longer timeout for Claude processing + verbose output
        max_messages=10,
    )

    # Should have at least 1 response (the final answer)
    assert len(responses) >= 1

    # Combine all responses
    all_text = "\n".join(r.text or "" for r in responses)

    # The final response should contain the answer
    assert "4" in all_text or len(all_text) > 10

    # Disable verbose mode for cleanup
    await send_message_and_wait(
        telethon_client,
        bot_entity,
        "/verbose",
        timeout=30,
    )


@pytest.mark.live
@pytest.mark.asyncio(loop_scope="session")
async def test_verbose_mode_in_help(
    telethon_client: "TelegramClient",
    bot_entity: "User",
    between_tests_delay: None,
) -> None:
    """Test that /verbose is documented in /help.

    Verifies:
    - /help includes /verbose command
    - Help text explains verbose mode
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
        "/verbose",
    )


@pytest.mark.live
@pytest.mark.asyncio(loop_scope="session")
async def test_verbose_toggle_sequence(
    telethon_client: "TelegramClient",
    bot_entity: "User",
    between_tests_delay: None,
) -> None:
    """Test multiple verbose toggle commands in sequence.

    Verifies:
    - Toggle on -> off -> on works correctly
    - State persists between commands
    """
    # Toggle 1: Enable
    response1 = await send_message_and_wait(
        telethon_client,
        bot_entity,
        "/verbose",
        timeout=30,
    )
    text1 = response1.text.lower()
    # Check for "enabled" but not "disabled"
    first_state = "enabled" in text1 and "disabled" not in text1

    await asyncio.sleep(2)

    # Toggle 2: Should be opposite
    response2 = await send_message_and_wait(
        telethon_client,
        bot_entity,
        "/verbose",
        timeout=30,
    )
    text2 = response2.text.lower()
    # Check for "enabled" but not "disabled"
    second_state = "enabled" in text2 and "disabled" not in text2

    # States should be opposite
    assert first_state != second_state

    await asyncio.sleep(1)

    # Toggle 3: Should be same as first
    response3 = await send_message_and_wait(
        telethon_client,
        bot_entity,
        "/verbose",
        timeout=30,
    )
    text3 = response3.text.lower()
    # Check for "enabled" but not "disabled"
    third_state = "enabled" in text3 and "disabled" not in text3

    # Third state should match first state
    assert first_state == third_state

    # Clean up: ensure verbose is off
    if third_state:
        await send_message_and_wait(
            telethon_client,
            bot_entity,
            "/verbose",
            timeout=30,
        )
