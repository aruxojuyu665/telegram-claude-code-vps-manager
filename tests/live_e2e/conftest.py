"""Pytest fixtures for Live E2E tests.

P0-LIVE-001, P0-LIVE-004: Telethon client fixture and session management.

Uses pytest-asyncio 0.21+ loop_scope for proper event loop handling with Telethon.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, AsyncGenerator

import pytest
import pytest_asyncio

from .config import LiveE2EConfig, get_config, is_live_e2e_configured

if TYPE_CHECKING:
    from telethon import TelegramClient
    from telethon.tl.types import User


def pytest_configure(config: pytest.Config) -> None:
    """Register custom markers."""
    config.addinivalue_line(
        "markers",
        "live: mark test as Live E2E test (requires real Telegram)",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip live tests if environment is not configured.

    Also adds loop_scope="session" to all asyncio tests in this directory.
    """
    if not is_live_e2e_configured():
        skip_live = pytest.mark.skip(
            reason="Live E2E not configured. Set LIVE_E2E_* environment variables."
        )
        for item in items:
            if "live" in item.keywords:
                item.add_marker(skip_live)


@pytest.fixture(scope="session")
def live_config() -> LiveE2EConfig:
    """Get Live E2E configuration.

    Returns:
        LiveE2EConfig instance.

    Raises:
        pytest.skip: If configuration is not available.
    """
    if not is_live_e2e_configured():
        pytest.skip("Live E2E not configured")
    return get_config()


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def telethon_client(
    live_config: LiveE2EConfig,
) -> AsyncGenerator["TelegramClient", None]:
    """Create and manage Telethon client for Live E2E tests.

    This fixture creates a real Telegram client using Telethon.
    The session is persisted between test runs to avoid re-authentication.

    P0-LIVE-001: Telethon Client Fixture

    Args:
        live_config: Live E2E configuration.

    Yields:
        Connected TelegramClient instance.
    """
    try:
        from telethon import TelegramClient
    except ImportError:
        pytest.skip("Telethon not installed. Run: pip install telethon")

    client = TelegramClient(
        str(live_config.session_path),
        live_config.api_id,
        live_config.api_hash,
    )

    await client.start(phone=live_config.phone)

    if not await client.is_user_authorized():
        pytest.fail(
            "Telethon client not authorized. "
            "Run the session interactively first to complete auth."
        )

    yield client

    await client.disconnect()


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def bot_entity(
    telethon_client: "TelegramClient",
    live_config: LiveE2EConfig,
) -> "User":
    """Get bot entity for sending messages.

    P0-LIVE-002: Bot Target Config

    Args:
        telethon_client: Connected Telethon client.
        live_config: Live E2E configuration.

    Returns:
        Bot entity (User object).
    """
    bot = await telethon_client.get_entity(live_config.bot_username)
    return bot


@pytest_asyncio.fixture(loop_scope="session")
async def between_tests_delay(live_config: LiveE2EConfig) -> None:
    """Add delay between tests to avoid Telegram rate limiting.

    Args:
        live_config: Live E2E configuration.
    """
    await asyncio.sleep(live_config.between_tests_delay)


@pytest_asyncio.fixture(loop_scope="session")
async def reset_session(
    telethon_client: "TelegramClient",
    bot_entity: "User",
    live_config: LiveE2EConfig,
) -> None:
    """Reset bot session before test to ensure clean state.

    This fixture sends /new to reset wide_context mode and clear session.
    Use this for tests that need Claude response (not just bot commands).

    Args:
        telethon_client: Connected Telethon client.
        bot_entity: Bot entity.
        live_config: Live E2E configuration.
    """
    # Send /new command
    sent_message = await telethon_client.send_message(bot_entity, "/new")
    sent_id = sent_message.id

    # Wait for the bot to respond to /new (confirm session reset)
    deadline = asyncio.get_running_loop().time() + 30
    while asyncio.get_running_loop().time() < deadline:
        messages = await telethon_client.get_messages(bot_entity, limit=5)
        for msg in messages:
            if msg.id > sent_id and msg.sender_id == bot_entity.id:
                # Got response, session is reset
                await asyncio.sleep(1)  # Small delay before test continues
                return
        await asyncio.sleep(0.5)

    # If no response within 30 seconds, continue anyway (but log warning)
    await asyncio.sleep(2)
