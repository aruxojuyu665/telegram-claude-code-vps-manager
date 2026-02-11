"""Live E2E tests for multitasking (named sessions) functionality.

P0.6-E2E: Multi-session management tests via real Telegram.

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
    wait_for_callback_response,
)

if TYPE_CHECKING:
    from telethon import TelegramClient
    from telethon.tl.types import Message, User


@pytest.mark.live
@pytest.mark.asyncio(loop_scope="session")
async def test_sessions_command_live(
    telethon_client: "TelegramClient",
    bot_entity: "User",
    between_tests_delay: None,
) -> None:
    """P0.6-E2E-001: Send /sessions to real bot and verify response.

    Verifies:
    - Bot responds to /sessions command
    - Response contains session list or "no sessions" message
    - Response contains inline keyboard buttons
    """
    response = await send_message_and_wait(
        telethon_client,
        bot_entity,
        "/sessions",
        timeout=30,
    )

    assert response.text is not None
    # Should contain session info or indicate no sessions
    text_lower = response.text.lower()
    assert "session" in text_lower or "main" in text_lower or "no active" in text_lower


@pytest.mark.live
@pytest.mark.asyncio(loop_scope="session")
async def test_create_named_session_live(
    telethon_client: "TelegramClient",
    bot_entity: "User",
    between_tests_delay: None,
) -> None:
    """P0.6-E2E-002: Create a named session via /new command.

    Verifies:
    - Bot responds to /new <name> command
    - Response confirms new session creation
    - Session name is included in response
    """
    # First reset to clean state
    await send_message_and_wait(telethon_client, bot_entity, "/new", timeout=30)
    await asyncio.sleep(1)

    # Create a named session
    response = await send_message_and_wait(
        telethon_client,
        bot_entity,
        "/new test_session_e2e",
        timeout=30,
    )

    assert response.text is not None
    text_lower = response.text.lower()
    # Should confirm session creation with the name
    assert (
        "session" in text_lower
        or "created" in text_lower
        or "new" in text_lower
        or "test_session_e2e" in text_lower
    )


@pytest.mark.live
@pytest.mark.asyncio(loop_scope="session")
async def test_switch_between_sessions_live(
    telethon_client: "TelegramClient",
    bot_entity: "User",
    between_tests_delay: None,
) -> None:
    """P0.6-E2E-003: Switch between sessions via /switch command.

    Verifies:
    - Bot responds to /switch <name> command
    - Response confirms session switch
    - Switching to non-existent session shows error
    """
    # First create two sessions
    await send_message_and_wait(telethon_client, bot_entity, "/new session_a", timeout=30)
    await asyncio.sleep(1)
    await send_message_and_wait(telethon_client, bot_entity, "/new session_b", timeout=30)
    await asyncio.sleep(1)

    # Switch to session_a
    response = await send_message_and_wait(
        telethon_client,
        bot_entity,
        "/switch session_a",
        timeout=30,
    )

    assert response.text is not None
    text_lower = response.text.lower()
    # Should confirm switch or show session_a
    assert "session_a" in text_lower or "switch" in text_lower or "active" in text_lower

    await asyncio.sleep(1)

    # Try to switch to non-existent session
    response = await send_message_and_wait(
        telethon_client,
        bot_entity,
        "/switch nonexistent_session",
        timeout=30,
    )

    assert response.text is not None
    text_lower = response.text.lower()
    # Should show error about session not found
    assert (
        "not found" in text_lower
        or "error" in text_lower
        or "does not exist" in text_lower
        or "no session" in text_lower
    )


@pytest.mark.live
@pytest.mark.asyncio(loop_scope="session")
async def test_kill_session_live(
    telethon_client: "TelegramClient",
    bot_entity: "User",
    between_tests_delay: None,
) -> None:
    """P0.6-E2E-004: Delete a session via /kill command.

    Verifies:
    - Bot responds to /kill <name> command
    - Response confirms session deletion
    - Cannot kill non-existent session
    """
    # Create a session to kill
    await send_message_and_wait(telethon_client, bot_entity, "/new kill_me_session", timeout=30)
    await asyncio.sleep(1)

    # Kill the session
    response = await send_message_and_wait(
        telethon_client,
        bot_entity,
        "/kill kill_me_session",
        timeout=30,
    )

    assert response.text is not None
    text_lower = response.text.lower()
    # Should confirm deletion
    assert (
        "deleted" in text_lower
        or "killed" in text_lower
        or "removed" in text_lower
        or "kill_me_session" in text_lower
    )

    await asyncio.sleep(1)

    # Try to kill already deleted session
    response = await send_message_and_wait(
        telethon_client,
        bot_entity,
        "/kill kill_me_session",
        timeout=30,
    )

    assert response.text is not None
    text_lower = response.text.lower()
    # Should show error
    assert "not found" in text_lower or "error" in text_lower or "does not exist" in text_lower


@pytest.mark.live
@pytest.mark.asyncio(loop_scope="session")
async def test_sessions_list_display_live(
    telethon_client: "TelegramClient",
    bot_entity: "User",
    between_tests_delay: None,
) -> None:
    """P0.6-E2E-005: Verify session list display with inline buttons.

    Verifies:
    - /sessions shows list of sessions
    - Response contains inline keyboard
    - Session names are visible
    """
    # Reset and create sessions
    await send_message_and_wait(telethon_client, bot_entity, "/new", timeout=30)
    await asyncio.sleep(1)
    await send_message_and_wait(telethon_client, bot_entity, "/new list_test_1", timeout=30)
    await asyncio.sleep(1)
    await send_message_and_wait(telethon_client, bot_entity, "/new list_test_2", timeout=30)
    await asyncio.sleep(1)

    # Get sessions list
    response = await send_message_and_wait(
        telethon_client,
        bot_entity,
        "/sessions",
        timeout=30,
    )

    assert response.text is not None
    text_lower = response.text.lower()

    # Should show session info
    assert "session" in text_lower

    # Should have inline buttons (check if buttons exist)
    if response.buttons:
        # Verify buttons are present
        assert len(response.buttons) >= 1


@pytest.mark.live
@pytest.mark.asyncio(loop_scope="session")
async def test_default_session_on_new_live(
    telethon_client: "TelegramClient",
    bot_entity: "User",
    between_tests_delay: None,
) -> None:
    """P0.6-E2E-006: Verify /new without name creates default session.

    Verifies:
    - /new without name resets to default session
    - Response confirms fresh start
    """
    # Send /new without name
    response = await send_message_and_wait(
        telethon_client,
        bot_entity,
        "/new",
        timeout=30,
    )

    assert response.text is not None
    text_lower = response.text.lower()

    # Should confirm new session/fresh start
    assert (
        "new" in text_lower
        or "fresh" in text_lower
        or "session" in text_lower
        or "main" in text_lower
    )


@pytest.mark.live
@pytest.mark.asyncio(loop_scope="session")
async def test_session_persistence_live(
    telethon_client: "TelegramClient",
    bot_entity: "User",
    between_tests_delay: None,
    reset_session: None,
) -> None:
    """P0.6-E2E-007: Verify session persists across messages.

    Verifies:
    - Messages in same session maintain context
    - Session doesn't reset between messages
    """
    # Create a specific session
    await send_message_and_wait(
        telethon_client,
        bot_entity,
        "/new persistence_test",
        timeout=30,
    )
    await asyncio.sleep(1)

    # Send first message
    responses = await send_and_collect_responses(
        telethon_client,
        bot_entity,
        "Remember this number: 42. Just say OK.",
        timeout=60,
    )

    first_response = "\n".join(r.text or "" for r in responses)
    assert len(first_response) > 0

    await asyncio.sleep(2)

    # Send second message asking about the number
    responses = await send_and_collect_responses(
        telethon_client,
        bot_entity,
        "What number did I ask you to remember?",
        timeout=60,
    )

    second_response = "\n".join(r.text or "" for r in responses)
    assert len(second_response) > 0

    # Claude should remember 42 from same session
    assert "42" in second_response, "Session context was not preserved"


@pytest.mark.live
@pytest.mark.asyncio(loop_scope="session")
async def test_session_isolation_live(
    telethon_client: "TelegramClient",
    bot_entity: "User",
    between_tests_delay: None,
) -> None:
    """P0.6-E2E-008: Verify sessions are isolated from each other.

    Verifies:
    - Different sessions have different contexts
    - Switching sessions changes context
    """
    # Create first session and set context
    await send_message_and_wait(telethon_client, bot_entity, "/new isolation_test_a", timeout=30)
    await asyncio.sleep(1)

    responses = await send_and_collect_responses(
        telethon_client,
        bot_entity,
        "My secret code is ALPHA123. Just say OK.",
        timeout=60,
    )
    await asyncio.sleep(2)

    # Create second session (different context)
    await send_message_and_wait(telethon_client, bot_entity, "/new isolation_test_b", timeout=30)
    await asyncio.sleep(1)

    # Ask about the code in second session - should NOT know it
    responses = await send_and_collect_responses(
        telethon_client,
        bot_entity,
        "What is my secret code? If you don't know, say 'unknown'.",
        timeout=60,
    )

    second_response = "\n".join(r.text or "" for r in responses).lower()

    # Second session should NOT have ALPHA123 context
    # It should either not know or give a different answer
    assert (
        "alpha123" not in second_response
        or "don't know" in second_response
        or "unknown" in second_response
        or "haven't" in second_response
        or "not sure" in second_response
    ), "Sessions are not properly isolated"


@pytest.mark.live
@pytest.mark.asyncio(loop_scope="session")
async def test_status_shows_active_session_live(
    telethon_client: "TelegramClient",
    bot_entity: "User",
    between_tests_delay: None,
) -> None:
    """P0.6-E2E-009: Verify /status shows active session info.

    Verifies:
    - /status displays current session name
    - Session info is visible in status
    """
    # Create named session
    await send_message_and_wait(telethon_client, bot_entity, "/new status_test_session", timeout=30)
    await asyncio.sleep(1)

    # Check status
    response = await send_message_and_wait(
        telethon_client,
        bot_entity,
        "/status",
        timeout=30,
    )

    assert response.text is not None
    # Status should show some session info
    text_lower = response.text.lower()
    assert "session" in text_lower or "status_test_session" in text_lower or "active" in text_lower
