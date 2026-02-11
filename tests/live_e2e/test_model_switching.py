"""Live E2E tests for model switching feature.

P1-LIVE-MODEL-001 to P1-LIVE-MODEL-005: Model switching tests via real Telegram.

These tests send REAL messages through Telegram to the REAL bot
and verify REAL responses for model switching functionality. NO MOCKS.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from .helpers import (
    assert_contains,
    send_message_and_wait,
)

if TYPE_CHECKING:
    from telethon import TelegramClient
    from telethon.tl.types import User


@pytest.mark.live
@pytest.mark.asyncio(loop_scope="session")
async def test_model_command_show_current_live(
    telethon_client: "TelegramClient",
    bot_entity: "User",
    between_tests_delay: None,
) -> None:
    """P1-LIVE-MODEL-001: Send /model without args to show current model.

    Verifies:
    - Bot responds to /model command
    - Response shows current model
    - Response shows available models (opus, sonnet, haiku)
    """
    response = await send_message_and_wait(
        telethon_client,
        bot_entity,
        "/model",
        timeout=30,
    )

    assert response.text is not None
    assert_contains(
        response.text,
        "Current model",
        "opus",
        "sonnet",
        "haiku",
    )


@pytest.mark.live
@pytest.mark.asyncio(loop_scope="session")
async def test_model_switch_to_haiku_live(
    telethon_client: "TelegramClient",
    bot_entity: "User",
    between_tests_delay: None,
) -> None:
    """P1-LIVE-MODEL-002: Switch to Haiku model.

    Verifies:
    - Bot accepts /model haiku command
    - Response confirms model changed to Haiku
    """
    response = await send_message_and_wait(
        telethon_client,
        bot_entity,
        "/model haiku",
        timeout=30,
    )

    assert response.text is not None
    assert_contains(
        response.text,
        "Model changed",
        "Haiku",
    )


@pytest.mark.live
@pytest.mark.asyncio(loop_scope="session")
async def test_model_switch_to_opus_live(
    telethon_client: "TelegramClient",
    bot_entity: "User",
    between_tests_delay: None,
) -> None:
    """P1-LIVE-MODEL-003: Switch to Opus model.

    Verifies:
    - Bot accepts /model opus command
    - Response confirms model changed to Opus
    """
    response = await send_message_and_wait(
        telethon_client,
        bot_entity,
        "/model opus",
        timeout=30,
    )

    assert response.text is not None
    assert_contains(
        response.text,
        "Model changed",
        "Opus",
    )


@pytest.mark.live
@pytest.mark.asyncio(loop_scope="session")
async def test_model_switch_to_sonnet_live(
    telethon_client: "TelegramClient",
    bot_entity: "User",
    between_tests_delay: None,
) -> None:
    """P1-LIVE-MODEL-004: Switch to Sonnet model (default).

    Verifies:
    - Bot accepts /model sonnet command
    - Response confirms model changed to Sonnet
    """
    response = await send_message_and_wait(
        telethon_client,
        bot_entity,
        "/model sonnet",
        timeout=30,
    )

    assert response.text is not None
    assert_contains(
        response.text,
        "Model changed",
        "Sonnet",
    )


@pytest.mark.live
@pytest.mark.asyncio(loop_scope="session")
async def test_model_invalid_argument_live(
    telethon_client: "TelegramClient",
    bot_entity: "User",
    between_tests_delay: None,
) -> None:
    """P1-LIVE-MODEL-005: Try to set invalid model.

    Verifies:
    - Bot rejects invalid model name
    - Response shows error message
    - Response suggests available models
    """
    response = await send_message_and_wait(
        telethon_client,
        bot_entity,
        "/model invalid",
        timeout=30,
    )

    assert response.text is not None
    assert_contains(
        response.text,
        "Unknown model",
    )
    # Should suggest available models
    assert "opus" in response.text.lower() or "sonnet" in response.text.lower()


@pytest.mark.live
@pytest.mark.asyncio(loop_scope="session")
async def test_status_shows_current_model_live(
    telethon_client: "TelegramClient",
    bot_entity: "User",
    between_tests_delay: None,
) -> None:
    """P1-LIVE-MODEL-006: Check /status shows current model.

    Verifies:
    - /status command shows current model
    - Model name is displayed correctly
    """
    response = await send_message_and_wait(
        telethon_client,
        bot_entity,
        "/status",
        timeout=30,
    )

    assert response.text is not None
    assert_contains(
        response.text,
        "Model:",
    )
    # Should show one of the model names
    text_lower = response.text.lower()
    assert any(model in text_lower for model in ["opus", "sonnet", "haiku"])
