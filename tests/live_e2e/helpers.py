"""Helper functions for Live E2E tests.

Utilities for sending messages, waiting for responses, and cleanup.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from telethon import TelegramClient
    from telethon.tl.types import Message, User


class LiveE2EError(Exception):
    """Base exception for Live E2E tests."""


class ResponseTimeoutError(LiveE2EError):
    """Raised when bot doesn't respond within timeout."""


class UnexpectedResponseError(LiveE2EError):
    """Raised when bot response doesn't match expectations."""


async def send_message_and_wait(
    client: "TelegramClient",
    bot: "User",
    text: str,
    timeout: int = 30,
) -> "Message":
    """Send message to bot and wait for response.

    Args:
        client: Connected Telethon client.
        bot: Bot entity to send message to.
        text: Message text to send.
        timeout: Maximum seconds to wait for response.

    Returns:
        Bot's response message.

    Raises:
        ResponseTimeoutError: If bot doesn't respond within timeout.
    """
    # Send the message
    sent_message = await client.send_message(bot, text)
    sent_id = sent_message.id

    # Wait for response (message with id > sent_id from bot)
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout

    while loop.time() < deadline:
        # Get recent messages from chat with bot
        messages = await client.get_messages(bot, limit=10)

        for msg in messages:
            # Find bot's response (message after our sent message)
            if msg.id > sent_id and msg.sender_id == bot.id:
                return msg

        # Wait before checking again
        await asyncio.sleep(0.5)

    raise ResponseTimeoutError(f"Bot didn't respond within {timeout} seconds to: {text[:50]}...")


async def send_and_collect_responses(
    client: "TelegramClient",
    bot: "User",
    text: str,
    timeout: int = 30,
    max_messages: int = 10,
) -> list["Message"]:
    """Send message and collect all response messages (for chunked responses).

    Args:
        client: Connected Telethon client.
        bot: Bot entity to send message to.
        text: Message text to send.
        timeout: Maximum seconds to wait for all responses.
        max_messages: Maximum number of response messages to collect.

    Returns:
        List of bot's response messages.

    Raises:
        ResponseTimeoutError: If no response received within timeout.
    """
    sent_message = await client.send_message(bot, text)
    sent_id = sent_message.id

    responses: list["Message"] = []
    response_ids: set[int] = set()
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    last_response_time = loop.time()

    while loop.time() < deadline:
        messages = await client.get_messages(bot, limit=20)

        for msg in messages:
            if msg.id > sent_id and msg.sender_id == bot.id and msg.id not in response_ids:
                responses.append(msg)
                response_ids.add(msg.id)
                last_response_time = loop.time()

        # If we have responses and no new ones for 3 seconds, assume done
        if responses and (loop.time() - last_response_time) > 3:
            break

        if len(responses) >= max_messages:
            break

        await asyncio.sleep(0.5)

    if not responses:
        raise ResponseTimeoutError(
            f"Bot didn't respond within {timeout} seconds to: {text[:50]}..."
        )

    # Sort by message id to get correct order
    responses.sort(key=lambda m: m.id)
    return responses


async def wait_for_callback_response(
    client: "TelegramClient",
    bot: "User",
    callback_data: str,
    message_with_buttons: "Message",
    timeout: int = 30,
) -> "Message":
    """Click inline button and wait for response.

    Args:
        client: Connected Telethon client.
        bot: Bot entity.
        callback_data: Callback data to send.
        message_with_buttons: Message containing inline buttons.
        timeout: Maximum seconds to wait for response.

    Returns:
        Bot's response after callback.

    Raises:
        ResponseTimeoutError: If no response received.
    """
    # Find the button with matching callback data
    if not message_with_buttons.buttons:
        raise LiveE2EError("Message has no inline buttons")

    button_found = False
    for row in message_with_buttons.buttons:
        for button in row:
            if hasattr(button, "data") and button.data:
                if button.data.decode() == callback_data:
                    await button.click()
                    button_found = True
                    break
        if button_found:
            break

    if not button_found:
        raise LiveE2EError(f"Button with callback_data={callback_data} not found")

    # Wait for response
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    original_id = message_with_buttons.id

    while loop.time() < deadline:
        messages = await client.get_messages(bot, limit=10)

        for msg in messages:
            # Look for edited original or new message
            if msg.id == original_id and msg.edit_date:
                return msg
            if msg.id > original_id and msg.sender_id == bot.id:
                return msg

        await asyncio.sleep(0.5)

    raise ResponseTimeoutError(f"No response to callback {callback_data}")


async def cleanup_messages(
    client: "TelegramClient",
    bot: "User",
    message_ids: list[int],
) -> None:
    """Delete test messages from chat.

    Args:
        client: Connected Telethon client.
        bot: Bot entity (chat to delete from).
        message_ids: List of message IDs to delete.
    """
    if message_ids:
        await client.delete_messages(bot, message_ids)


def assert_contains(text: str, *substrings: str) -> None:
    """Assert that text contains all given substrings.

    Args:
        text: Text to check.
        *substrings: Substrings that must be present.

    Raises:
        AssertionError: If any substring is missing.
    """
    for substring in substrings:
        assert substring in text, f"Expected '{substring}' in response:\n{text}"


def assert_not_contains(text: str, *substrings: str) -> None:
    """Assert that text does NOT contain any of given substrings.

    Args:
        text: Text to check.
        *substrings: Substrings that must NOT be present.

    Raises:
        AssertionError: If any substring is found.
    """
    for substring in substrings:
        assert substring not in text, f"Unexpected '{substring}' in response:\n{text}"
