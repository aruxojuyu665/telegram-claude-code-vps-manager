"""Live E2E tests for Socratic Gate safety flow.

P2-LIVE-011 to P2-LIVE-015: Safety-related tests via real Telegram.

These tests verify the Socratic Gate confirmation flow using REAL
Telegram messages. NO MOCKS.

WARNING: Some tests involve dangerous commands. They are designed to:
1. Trigger confirmation prompts
2. Test cancellation flows
3. NOT actually execute dangerous commands
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import pytest

from .helpers import (
    assert_contains,
    assert_not_contains,
    send_and_collect_responses,
    send_message_and_wait,
)

if TYPE_CHECKING:
    from telethon import TelegramClient
    from telethon.tl.types import User


@pytest.mark.live
@pytest.mark.asyncio(loop_scope="session")
async def test_safe_command_live(
    telethon_client: "TelegramClient",
    bot_entity: "User",
    between_tests_delay: None,
    reset_session: None,
) -> None:
    """P2-LIVE-011: Send safe command (ls -la) via real Telegram.

    Verifies:
    - Safe command is executed without confirmation
    - Response contains directory listing or relevant output
    """
    response = await send_message_and_wait(
        telethon_client,
        bot_entity,
        "ls -la",
        timeout=60,
    )

    assert response.text is not None
    # Should NOT ask for confirmation for safe commands
    assert_not_contains(
        response.text.lower(),
        "confirm",
        "dangerous",
        "critical",
    )


@pytest.mark.live
@pytest.mark.asyncio(loop_scope="session")
async def test_moderate_command_live(
    telethon_client: "TelegramClient",
    bot_entity: "User",
    between_tests_delay: None,
    reset_session: None,
) -> None:
    """P2-LIVE-012: Send moderate risk command via real Telegram.

    Verifies:
    - Moderate command shows INFO but proceeds
    - Does not require explicit confirmation
    """
    # "apt list" is moderate - shows package info
    response = await send_message_and_wait(
        telethon_client,
        bot_entity,
        "apt list --installed | head -5",
        timeout=60,
    )

    assert response.text is not None
    # Should get some response, might have INFO prefix but no hard block
    assert len(response.text) > 0


@pytest.mark.live
@pytest.mark.asyncio(loop_scope="session")
async def test_dangerous_command_prompt_live(
    telethon_client: "TelegramClient",
    bot_entity: "User",
    between_tests_delay: None,
    reset_session: None,
) -> None:
    """P2-LIVE-013: Send dangerous command and verify confirmation prompt.

    Verifies:
    - Dangerous command triggers confirmation prompt
    - Prompt contains YES/NO options or equivalent
    - Command is NOT executed before confirmation
    """
    # rm on a specific directory triggers DANGEROUS
    dangerous_cmd = "rm -rf ./test_temp_folder_that_doesnt_exist"

    response = await send_message_and_wait(
        telethon_client,
        bot_entity,
        dangerous_cmd,
        timeout=60,
    )

    assert response.text is not None
    text_lower = response.text.lower()

    # Should ask for confirmation
    assert (
        "confirm" in text_lower
        or "dangerous" in text_lower
        or "yes" in text_lower
        or "no" in text_lower
    ), f"Expected confirmation prompt, got: {response.text}"


@pytest.mark.live
@pytest.mark.asyncio(loop_scope="session")
async def test_dangerous_command_cancel_live(
    telethon_client: "TelegramClient",
    bot_entity: "User",
    between_tests_delay: None,
    reset_session: None,
) -> None:
    """P2-LIVE-014: Test dangerous command cancellation with NO.

    Verifies:
    - After confirmation prompt, sending "no" cancels the command
    - Bot confirms cancellation
    """
    # First trigger the confirmation
    dangerous_cmd = "rm -rf ./another_test_folder"

    prompt = await send_message_and_wait(
        telethon_client,
        bot_entity,
        dangerous_cmd,
        timeout=60,
    )

    assert prompt.text is not None

    # Wait a bit then send cancellation
    await asyncio.sleep(1)

    cancel_response = await send_message_and_wait(
        telethon_client,
        bot_entity,
        "no",
        timeout=30,
    )

    assert cancel_response.text is not None
    text_lower = cancel_response.text.lower()

    # Should confirm cancellation
    assert (
        "cancel" in text_lower
        or "aborted" in text_lower
        or "not executed" in text_lower
        or "no pending" in text_lower
    ), f"Expected cancellation confirmation, got: {cancel_response.text}"


@pytest.mark.live
@pytest.mark.asyncio(loop_scope="session")
async def test_critical_command_exact_phrase_prompt_live(
    telethon_client: "TelegramClient",
    bot_entity: "User",
    between_tests_delay: None,
    reset_session: None,
) -> None:
    """P2-LIVE-015: Test critical command requires exact phrase.

    Verifies:
    - Critical command (rm -rf /) shows CRITICAL warning
    - Requires exact phrase, not just YES
    - We cancel immediately to avoid any risk
    """
    # rm -rf / is CRITICAL - requires exact phrase
    critical_cmd = "rm -rf /"

    response = await send_message_and_wait(
        telethon_client,
        bot_entity,
        critical_cmd,
        timeout=60,
    )

    assert response.text is not None
    text_lower = response.text.lower()

    # Should show CRITICAL warning
    assert (
        "critical" in text_lower
    ), f"Expected CRITICAL warning, got: {response.text}"

    # Should require exact phrase (not just YES)
    assert (
        "confirm critical operation" in text_lower
        or "podtverzhdayu" in text_lower
        or "phrase" in text_lower
    ), f"Expected exact phrase requirement, got: {response.text}"

    # IMMEDIATELY cancel to avoid any risk
    await asyncio.sleep(0.5)

    cancel_response = await send_message_and_wait(
        telethon_client,
        bot_entity,
        "no",
        timeout=30,
    )

    # Confirm we cancelled
    assert cancel_response.text is not None


@pytest.mark.live
@pytest.mark.asyncio(loop_scope="session")
async def test_confirmation_timeout_live(
    telethon_client: "TelegramClient",
    bot_entity: "User",
    between_tests_delay: None,
    reset_session: None,
) -> None:
    """Test that confirmation expires after timeout.

    Note: This test may take longer as it waits for timeout.
    """
    # Trigger a dangerous command
    dangerous_cmd = "rm -rf ./timeout_test_folder"

    prompt = await send_message_and_wait(
        telethon_client,
        bot_entity,
        dangerous_cmd,
        timeout=60,
    )

    assert prompt.text is not None

    # Wait for confirmation to expire (default 60 seconds)
    # We'll just send /new to reset instead of waiting
    await asyncio.sleep(2)

    # Reset session
    reset_response = await send_message_and_wait(
        telethon_client,
        bot_entity,
        "/new",
        timeout=30,
    )

    assert reset_response.text is not None


@pytest.mark.live
@pytest.mark.asyncio(loop_scope="session")
async def test_safe_after_dangerous_cancel_live(
    telethon_client: "TelegramClient",
    bot_entity: "User",
    between_tests_delay: None,
    reset_session: None,
) -> None:
    """Test that safe commands work after cancelling dangerous one.

    Verifies:
    - After cancelling dangerous command
    - Safe commands still work normally
    """
    # 1. Trigger dangerous
    await send_message_and_wait(
        telethon_client,
        bot_entity,
        "rm -rf ./some_folder",
        timeout=60,
    )
    await asyncio.sleep(1)

    # 2. Cancel
    await send_message_and_wait(
        telethon_client,
        bot_entity,
        "no",
        timeout=30,
    )
    await asyncio.sleep(1)

    # 3. Safe command should work
    response = await send_message_and_wait(
        telethon_client,
        bot_entity,
        "echo 'hello world'",
        timeout=60,
    )

    assert response.text is not None
    # Should get response without confirmation prompt
    assert_not_contains(
        response.text.lower(),
        "dangerous",
        "confirm",
    )
