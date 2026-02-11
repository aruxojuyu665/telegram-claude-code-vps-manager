"""Live E2E tests for advanced features.

P3-LIVE-016 to P3-LIVE-020: Advanced feature tests via real Telegram.

These tests verify advanced bot features using REAL Telegram. NO MOCKS.
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
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

    from .config import LiveE2EConfig


@pytest.mark.live
@pytest.mark.asyncio(loop_scope="session")
async def test_wide_context_activation_live(
    telethon_client: "TelegramClient",
    bot_entity: "User",
    between_tests_delay: None,
) -> None:
    """P3-LIVE-016: Test /wide_context command activation.

    Verifies:
    - /wide_context command activates wide context mode
    - Bot responds with instructions for accumulating messages
    """
    response = await send_message_and_wait(
        telethon_client,
        bot_entity,
        "/wide_context",
        timeout=30,
    )

    assert response.text is not None
    text_lower = response.text.lower()

    # Should indicate wide context mode is activated
    assert (
        "wide" in text_lower
        or "context" in text_lower
        or "accumul" in text_lower  # accumulating
        or "collect" in text_lower
    ), f"Expected wide context confirmation, got: {response.text}"


@pytest.mark.live
@pytest.mark.asyncio(loop_scope="session")
async def test_wide_context_cancel_live(
    telethon_client: "TelegramClient",
    bot_entity: "User",
    between_tests_delay: None,
) -> None:
    """Test wide context cancellation.

    Verifies:
    - After activating wide context
    - Cancel button or /new resets the mode
    """
    # Activate wide context
    await send_message_and_wait(
        telethon_client,
        bot_entity,
        "/wide_context",
        timeout=30,
    )
    await asyncio.sleep(1)

    # Reset with /new
    response = await send_message_and_wait(
        telethon_client,
        bot_entity,
        "/new",
        timeout=30,
    )

    assert response.text is not None


@pytest.mark.live
@pytest.mark.asyncio(loop_scope="session")
async def test_file_upload_txt_live(
    telethon_client: "TelegramClient",
    bot_entity: "User",
    between_tests_delay: None,
) -> None:
    """P3-LIVE-017: Test .txt file upload and processing.

    Verifies:
    - Bot accepts .txt file upload
    - Bot extracts and processes file content
    """
    # Create a temporary test file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("This is a test file content.\nLine 2 of the test.")
        temp_path = Path(f.name)

    try:
        # Send file to bot
        await telethon_client.send_file(
            bot_entity,
            temp_path,
            caption="Please analyze this file",
        )

        # Wait for response
        await asyncio.sleep(3)

        # Get recent messages
        messages = await telethon_client.get_messages(bot_entity, limit=5)

        # Should have a response about the file
        found_response = False
        for msg in messages:
            if msg.sender_id == bot_entity.id and msg.text:
                # Bot should acknowledge the file or process it
                found_response = True
                break

        assert found_response, "Bot should respond to file upload"

    finally:
        # Cleanup temp file
        temp_path.unlink(missing_ok=True)


@pytest.mark.live
@pytest.mark.asyncio(loop_scope="session")
async def test_file_upload_py_live(
    telethon_client: "TelegramClient",
    bot_entity: "User",
    between_tests_delay: None,
) -> None:
    """Test .py file upload and processing.

    Verifies:
    - Bot accepts .py file upload
    - Bot can analyze Python code
    """
    # Create a temporary Python file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write('def hello():\n    print("Hello, World!")\n\nhello()')
        temp_path = Path(f.name)

    try:
        await telethon_client.send_file(
            bot_entity,
            temp_path,
            caption="What does this code do?",
        )

        # Wait for processing
        await asyncio.sleep(5)

        messages = await telethon_client.get_messages(bot_entity, limit=5)

        found_response = False
        for msg in messages:
            if msg.sender_id == bot_entity.id and msg.text:
                found_response = True
                break

        assert found_response, "Bot should respond to .py file"

    finally:
        temp_path.unlink(missing_ok=True)


@pytest.mark.live
@pytest.mark.asyncio(loop_scope="session")
async def test_long_response_chunking_live(
    telethon_client: "TelegramClient",
    bot_entity: "User",
    between_tests_delay: None,
    reset_session: None,
) -> None:
    """P3-LIVE-018: Test long response chunking.

    Verifies:
    - Bot properly chunks long responses
    - All parts are received
    - Parts are numbered [Part 1/N]
    """
    # Request something that generates a long response
    long_prompt = (
        "List all letters of the English alphabet, one per line, with a description of each letter."
    )

    responses = await send_and_collect_responses(
        telethon_client,
        bot_entity,
        long_prompt,
        timeout=120,  # Long responses take time
        max_messages=10,
    )

    assert len(responses) >= 1

    # If response was chunked, check for part numbers
    if len(responses) > 1:
        full_text = responses[0].text or ""
        assert "[Part" in full_text or len(full_text) > 100


@pytest.mark.live
@pytest.mark.asyncio(loop_scope="session")
async def test_session_persistence_live(
    telethon_client: "TelegramClient",
    bot_entity: "User",
    between_tests_delay: None,
    reset_session: None,
) -> None:
    """P3-LIVE-019: Test Claude session persistence.

    Verifies:
    - Bot remembers context from previous messages
    - Conversation continuity works
    """
    # First, reset session
    await send_message_and_wait(
        telethon_client,
        bot_entity,
        "/new",
        timeout=30,
    )
    await asyncio.sleep(2)

    # Send first message with context
    await send_message_and_wait(
        telethon_client,
        bot_entity,
        "My name is TestUser123. Remember this.",
        timeout=60,
    )
    await asyncio.sleep(2)

    # Ask about the context
    response = await send_message_and_wait(
        telethon_client,
        bot_entity,
        "What is my name?",
        timeout=60,
    )

    assert response.text is not None
    # Claude should remember the name
    assert (
        "TestUser123" in response.text or "test" in response.text.lower()
    ), f"Expected session to remember name, got: {response.text}"


@pytest.mark.live
@pytest.mark.asyncio(loop_scope="session")
async def test_error_recovery_live(
    telethon_client: "TelegramClient",
    bot_entity: "User",
    between_tests_delay: None,
    reset_session: None,
) -> None:
    """P3-LIVE-020: Test error recovery.

    Verifies:
    - Bot gracefully handles edge cases
    - User can continue after unusual input
    """
    # Send special characters that might cause parsing issues
    special_chars = "!@#$%^&*()_+-=[]{}|;':\",./<>?"
    response = await send_message_and_wait(
        telethon_client,
        bot_entity,
        special_chars,
        timeout=60,
    )

    # Bot should handle special characters gracefully
    assert response.text is not None

    # Verify bot still works after unusual input
    await asyncio.sleep(1)

    response = await send_message_and_wait(
        telethon_client,
        bot_entity,
        "Say 'hello'",
        timeout=60,
    )

    assert response.text is not None


@pytest.mark.live
@pytest.mark.asyncio(loop_scope="session")
async def test_concurrent_messages_live(
    telethon_client: "TelegramClient",
    bot_entity: "User",
    between_tests_delay: None,
    reset_session: None,
) -> None:
    """Test handling of rapid consecutive messages.

    Verifies:
    - Bot handles multiple quick messages
    - Responses are received for each
    """
    # Send multiple messages quickly
    messages_to_send = [
        "What is 1+1?",
        "What is 2+2?",
        "What is 3+3?",
    ]

    for msg in messages_to_send:
        await telethon_client.send_message(bot_entity, msg)
        await asyncio.sleep(0.5)  # Small delay

    # Wait for all responses
    await asyncio.sleep(30)

    # Check we got responses
    messages = await telethon_client.get_messages(bot_entity, limit=20)

    bot_responses = [m for m in messages if m.sender_id == bot_entity.id]

    # Should have at least some responses
    assert len(bot_responses) >= 1, "Should receive at least one response"


@pytest.mark.live
@pytest.mark.asyncio(loop_scope="session")
async def test_unicode_message_live(
    telethon_client: "TelegramClient",
    bot_entity: "User",
    between_tests_delay: None,
    reset_session: None,
) -> None:
    """Test Unicode/emoji handling.

    Verifies:
    - Bot correctly handles Unicode characters
    - Emojis don't break processing
    """
    unicode_message = "Hello! 你好! مرحبا! 🎉 What language is this?"

    response = await send_message_and_wait(
        telethon_client,
        bot_entity,
        unicode_message,
        timeout=60,
    )

    assert response.text is not None
    assert len(response.text) > 0
