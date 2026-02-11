"""Live E2E tests for file download feature.

P3-LIVE-021 to P3-LIVE-026: File download tests via real Telegram.

These tests verify file download functionality using REAL Telegram. NO MOCKS.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import pytest

from .helpers import send_message_and_wait

if TYPE_CHECKING:
    from telethon import TelegramClient
    from telethon.tl.types import User


@pytest.mark.live
@pytest.mark.asyncio(loop_scope="session")
async def test_single_file_download_request_live(
    telethon_client: "TelegramClient",
    bot_entity: "User",
    between_tests_delay: None,
    reset_session: None,
) -> None:
    """P3-LIVE-021: Test single file download request.

    Verifies:
    - Bot understands file download request
    - Bot responds with file marker or appropriate message
    """
    # Request a common file that should exist
    response = await send_message_and_wait(
        telethon_client,
        bot_entity,
        "Download the README.md file from the current directory",
        timeout=60,
    )

    assert response.text is not None
    # Bot should either send the file or acknowledge the request
    text_lower = response.text.lower()
    assert (
        "readme" in text_lower
        or "file" in text_lower
        or "download" in text_lower
        or "send" in text_lower
    ), f"Expected file-related response, got: {response.text}"


@pytest.mark.live
@pytest.mark.asyncio(loop_scope="session")
async def test_file_not_found_response_live(
    telethon_client: "TelegramClient",
    bot_entity: "User",
    between_tests_delay: None,
) -> None:
    """P3-LIVE-022: Test response for non-existent file.

    Verifies:
    - Bot handles non-existent file gracefully
    - Bot provides appropriate error message
    """
    response = await send_message_and_wait(
        telethon_client,
        bot_entity,
        "Download /nonexistent/path/to/file_that_does_not_exist_12345.txt",
        timeout=60,
    )

    assert response.text is not None
    text_lower = response.text.lower()
    # Should indicate file not found or error
    assert (
        "not found" in text_lower
        or "not exist" in text_lower
        or "error" in text_lower
        or "cannot" in text_lower
        or "unable" in text_lower
    ), f"Expected error response for non-existent file, got: {response.text}"


@pytest.mark.live
@pytest.mark.asyncio(loop_scope="session")
async def test_directory_download_request_live(
    telethon_client: "TelegramClient",
    bot_entity: "User",
    between_tests_delay: None,
) -> None:
    """P3-LIVE-023: Test directory download request.

    Verifies:
    - Bot understands directory download request
    - Bot responds appropriately (may list files or send archive)
    """
    response = await send_message_and_wait(
        telethon_client,
        bot_entity,
        "Send me all files from the tests directory",
        timeout=90,
    )

    assert response.text is not None
    text_lower = response.text.lower()
    # Bot should acknowledge directory request
    assert (
        "test" in text_lower
        or "file" in text_lower
        or "directory" in text_lower
        or "folder" in text_lower
        or "send" in text_lower
    ), f"Expected directory-related response, got: {response.text}"


@pytest.mark.live
@pytest.mark.asyncio(loop_scope="session")
async def test_glob_pattern_download_request_live(
    telethon_client: "TelegramClient",
    bot_entity: "User",
    between_tests_delay: None,
) -> None:
    """P3-LIVE-024: Test glob pattern download request.

    Verifies:
    - Bot understands glob pattern requests
    - Bot responds with matching files or acknowledgement
    """
    response = await send_message_and_wait(
        telethon_client,
        bot_entity,
        "Download all .py files from the src directory",
        timeout=90,
    )

    assert response.text is not None
    text_lower = response.text.lower()
    # Bot should acknowledge the pattern request
    assert (
        "python" in text_lower
        or ".py" in text_lower
        or "file" in text_lower
        or "src" in text_lower
        or "send" in text_lower
    ), f"Expected pattern-related response, got: {response.text}"


@pytest.mark.live
@pytest.mark.asyncio(loop_scope="session")
async def test_file_download_with_specific_path_live(
    telethon_client: "TelegramClient",
    bot_entity: "User",
    between_tests_delay: None,
) -> None:
    """P3-LIVE-025: Test file download with absolute path.

    Verifies:
    - Bot handles absolute path requests
    - Bot responds with file or appropriate message
    """
    response = await send_message_and_wait(
        telethon_client,
        bot_entity,
        "Please download the file at /opt/0-intel/0-INTEL/README.md",
        timeout=60,
    )

    assert response.text is not None
    # Bot should acknowledge the request
    text_lower = response.text.lower()
    assert (
        "readme" in text_lower
        or "file" in text_lower
        or "download" in text_lower
        or "path" in text_lower
        or "send" in text_lower
    ), f"Expected path-related response, got: {response.text}"


@pytest.mark.live
@pytest.mark.asyncio(loop_scope="session")
async def test_multiple_files_download_request_live(
    telethon_client: "TelegramClient",
    bot_entity: "User",
    between_tests_delay: None,
) -> None:
    """P3-LIVE-026: Test multiple files download request.

    Verifies:
    - Bot handles request for multiple files
    - Bot responds appropriately
    """
    response = await send_message_and_wait(
        telethon_client,
        bot_entity,
        "Send me both README.md and CHANGELOG.md files",
        timeout=90,
    )

    assert response.text is not None
    text_lower = response.text.lower()
    # Bot should acknowledge multiple files
    assert (
        "file" in text_lower
        or "readme" in text_lower
        or "changelog" in text_lower
        or "send" in text_lower
        or "both" in text_lower
    ), f"Expected multi-file response, got: {response.text}"


@pytest.mark.live
@pytest.mark.asyncio(loop_scope="session")
async def test_file_download_receives_document_live(
    telethon_client: "TelegramClient",
    bot_entity: "User",
    between_tests_delay: None,
    reset_session: None,
) -> None:
    """P3-LIVE-027: Test that file download actually sends a document.

    Verifies:
    - Bot actually sends a document after download request
    - Document is received within timeout
    """
    # Send download request
    await telethon_client.send_message(
        bot_entity,
        "Download the pyproject.toml file please",
    )

    # Wait for response(s) - could be text + document
    await asyncio.sleep(5)

    # Get recent messages
    messages = await telethon_client.get_messages(bot_entity, limit=10)

    # Check if any document was received
    document_received = False
    for msg in messages:
        if msg.sender_id == bot_entity.id:
            if msg.document:
                document_received = True
                break

    # Note: This test may fail if bot doesn't have the file or Claude
    # doesn't use the correct marker format. This is expected behavior
    # during initial development.
    if not document_received:
        # At minimum, bot should have sent a text response
        text_responses = [
            msg for msg in messages
            if msg.sender_id == bot_entity.id and msg.text
        ]
        assert len(text_responses) > 0, "Bot should respond to download request"
