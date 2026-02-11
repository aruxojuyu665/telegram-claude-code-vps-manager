#!/usr/bin/env python3
"""E2E test script for wide context feature.

This script tests:
1. 2-second delay message accumulation
2. /wide-context command with Accept button
3. Message and file accumulation in wide mode

Usage:
    python scripts/test_wide_context.py --mode delay     # Test 2s delay
    python scripts/test_wide_context.py --mode wide      # Test /wide-context
    python scripts/test_wide_context.py --all            # Run all tests
    python scripts/test_wide_context.py --timeout 60

Author: JARVIS Team
Version: 0.14.0
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from dotenv import load_dotenv  # noqa: E402

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


async def test_delay_accumulation(
    client: "TelegramClient",  # type: ignore[name-defined]
    bot_id: int,
    timeout: float = 30.0,
) -> tuple[bool, str]:
    """Test 2-second delay message accumulation.

    Sends 3 messages rapidly (faster than 2s delay) and expects
    a single combined response from Claude.

    Args:
        client: Connected Telethon client.
        bot_id: Bot user ID to send messages to.
        timeout: Timeout in seconds to wait for response.

    Returns:
        Tuple of (success: bool, message: str).
    """
    logger.info("Testing 2-second delay message accumulation...")

    # Send 3 messages rapidly
    messages = [
        "This is part 1 of my question.",
        "This is part 2 with more context.",
        "And part 3 asking: what is 2+2?",
    ]

    sent_msg = None
    for i, msg in enumerate(messages):
        sent_msg = await client.send_message(bot_id, msg)
        logger.info(f"Sent message {i + 1}/3")
        await asyncio.sleep(0.3)  # Send faster than 2s delay

    if sent_msg is None:
        return False, "Failed to send messages"

    # Wait for response (2s delay + Claude processing time)
    logger.info(f"Waiting for response (timeout: {timeout}s)...")
    start_time = asyncio.get_event_loop().time()

    while True:
        elapsed = asyncio.get_event_loop().time() - start_time
        if elapsed >= timeout:
            return False, f"Bot did not respond within {timeout} seconds"

        # Check for new messages from bot
        messages_received = await client.get_messages(bot_id, limit=5)
        for msg in messages_received:
            # Find response after our last sent message
            if msg.id > sent_msg.id and msg.out is False:
                logger.info("Received response from bot")
                return True, f"Got response: {msg.text[:100] if msg.text else '[No text]'}..."

        await asyncio.sleep(1)


async def test_wide_context_mode(
    client: "TelegramClient",  # type: ignore[name-defined]
    bot_id: int,
    timeout: float = 60.0,
) -> tuple[bool, str]:
    """Test /wide_context command with Accept button.

    Sends /wide_context, accumulates messages, then clicks Accept.

    Args:
        client: Connected Telethon client.
        bot_id: Bot user ID to send messages to.
        timeout: Timeout in seconds to wait for response.

    Returns:
        Tuple of (success: bool, message: str).
    """
    logger.info("Testing /wide_context command...")

    # Send /wide_context command
    await client.send_message(bot_id, "/wide_context")
    await asyncio.sleep(2)

    # Check for status message with buttons
    messages = await client.get_messages(bot_id, limit=3)
    status_msg = None
    for msg in messages:
        if msg.buttons and "Wide Context" in (msg.text or ""):
            status_msg = msg
            break

    if status_msg is None:
        return False, "/wide-context status message not found"

    logger.info("Found wide context status message")

    # Send multiple messages
    test_messages = [
        "First context message for wide mode.",
        "Second context message with more details.",
        "What should I do with all this context?",
    ]

    for i, msg in enumerate(test_messages):
        await client.send_message(bot_id, msg)
        logger.info(f"Sent context message {i + 1}/3")
        await asyncio.sleep(0.5)

    await asyncio.sleep(1)

    # Find and click Accept button
    messages = await client.get_messages(bot_id, limit=5)
    accept_clicked = False

    for msg in messages:
        if msg.buttons:
            for row in msg.buttons:
                for button in row:
                    if "Accept" in button.text:
                        logger.info("Clicking Accept button...")
                        await button.click()
                        accept_clicked = True
                        break
                if accept_clicked:
                    break
        if accept_clicked:
            break

    if not accept_clicked:
        return False, "Accept button not found"

    # Wait for Claude response
    logger.info(f"Waiting for Claude response (timeout: {timeout}s)...")
    await asyncio.sleep(5)  # Give Claude time to process

    start_time = asyncio.get_event_loop().time()
    while True:
        elapsed = asyncio.get_event_loop().time() - start_time
        if elapsed >= timeout:
            return False, f"Claude did not respond within {timeout} seconds"

        messages_received = await client.get_messages(bot_id, limit=5)
        for msg in messages_received:
            # Look for Claude's response (not our messages, not status updates)
            if msg.out is False and msg.text:
                if "Sending to Claude" not in msg.text and "Wide Context" not in msg.text:
                    logger.info("Received Claude response")
                    return True, f"Got response: {msg.text[:100]}..."

        await asyncio.sleep(1)


async def run_tests(
    api_id: int,
    api_hash: str,
    session_path: str,
    bot_id: int,
    mode: str,
    timeout: float,
) -> int:
    """Run the specified tests.

    Args:
        api_id: Telegram API ID.
        api_hash: Telegram API hash.
        session_path: Path to session file.
        bot_id: Bot user ID.
        mode: Test mode ('delay', 'wide', or 'all').
        timeout: Timeout in seconds.

    Returns:
        Exit code (0 for success, 1 for failure).
    """
    try:
        from telethon import TelegramClient
    except ImportError:
        logger.error("Telethon not installed. Run: pip install telethon")
        return 1

    client = TelegramClient(session_path, api_id, api_hash)

    try:
        await client.connect()

        if not await client.is_user_authorized():
            logger.error("Session not authorized. Run the bot first to create session.")
            return 1

        me = await client.get_me()
        logger.info(f"Connected as: @{me.username} (id={me.id})")

        results: list[tuple[str, bool, str]] = []

        if mode in ("delay", "all"):
            success, message = await test_delay_accumulation(client, bot_id, timeout)
            results.append(("2s Delay Test", success, message))
            await asyncio.sleep(3)  # Pause between tests

        if mode in ("wide", "all"):
            success, message = await test_wide_context_mode(client, bot_id, timeout)
            results.append(("Wide Context Test", success, message))

        # Print results
        logger.info("=" * 50)
        logger.info("TEST RESULTS")
        logger.info("=" * 50)

        all_passed = True
        for test_name, success, message in results:
            status = "[SUCCESS]" if success else "[FAILED]"
            logger.info(f"{status} {test_name}: {message}")
            if not success:
                all_passed = False

        return 0 if all_passed else 1

    except Exception as e:
        logger.exception(f"Test failed with error: {e}")
        return 1
    finally:
        await client.disconnect()


def find_session_file(session_name: str, search_paths: list[Path]) -> Path | None:
    """Find session file in multiple locations."""
    for search_dir in search_paths:
        session_path = search_dir / f"{session_name}.session"
        if session_path.exists():
            return session_path
    return None


def copy_session_to_temp(session_path: Path) -> Path:
    """Copy session file to temp directory to avoid conflicts."""
    import shutil
    import tempfile

    temp_dir = Path(tempfile.gettempdir())
    temp_session = temp_dir / f"test_{session_path.stem}.session"

    shutil.copy2(session_path, temp_session)
    logger.info(f"Copied session to: {temp_session}")

    return temp_session.with_suffix("")


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="E2E test for wide context feature",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/test_wide_context.py --mode delay    # Test 2s delay
  python scripts/test_wide_context.py --mode wide     # Test /wide-context
  python scripts/test_wide_context.py --all           # Run all tests
  python scripts/test_wide_context.py --timeout 120
        """,
    )
    parser.add_argument(
        "--mode",
        choices=["delay", "wide", "all"],
        default="all",
        help="Test mode: 'delay' for 2s accumulation, 'wide' for /wide-context, 'all' for both",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=60.0,
        help="Timeout in seconds to wait for bot response",
    )
    parser.add_argument(
        "--session",
        type=str,
        default=None,
        help="Path to Telethon session file (without .session extension)",
    )
    return parser.parse_args()


async def main() -> int:
    """Main entry point."""
    args = parse_args()

    # Load environment variables
    env_path = PROJECT_ROOT / ".env"
    if env_path.exists():
        load_dotenv(env_path)
        logger.info(f"Loaded configuration from {env_path}")
    else:
        logger.warning(f".env file not found at {env_path}")

    # Get configuration
    api_id = os.getenv("TELETHON_API_ID")
    api_hash = os.getenv("TELETHON_API_HASH")
    session_name = os.getenv("TELETHON_SESSION_NAME", "jarvis_premium")
    bot_id = os.getenv("BOT_ID")

    # Validate configuration
    missing = []
    if not api_id:
        missing.append("TELETHON_API_ID")
    if not api_hash:
        missing.append("TELETHON_API_HASH")
    if not bot_id:
        missing.append("BOT_ID")

    if missing:
        logger.error(f"Missing environment variables: {', '.join(missing)}")
        logger.error("Please configure these in your .env file")
        return 1

    # Find session file
    if args.session:
        session_path = args.session
    else:
        search_paths = [
            PROJECT_ROOT,
            Path.cwd(),
            Path.home(),
            Path("/opt/jarvis-mk1"),
        ]
        found_session = find_session_file(session_name, search_paths)
        if found_session:
            logger.info(f"Found session file: {found_session}")
            session_path = str(copy_session_to_temp(found_session))
        else:
            session_path = session_name
            logger.warning(f"Session file not found, will try: {session_name}")

    # Run tests
    logger.info("=" * 50)
    logger.info("Wide Context E2E Test")
    logger.info("=" * 50)
    logger.info(f"Mode: {args.mode}")
    logger.info(f"Bot ID: {bot_id}")
    logger.info(f"Session: {session_path}")
    logger.info(f"Timeout: {args.timeout}s")
    logger.info("=" * 50)

    return await run_tests(
        api_id=int(api_id),
        api_hash=api_hash,
        session_path=session_path,
        bot_id=int(bot_id),
        mode=args.mode,
        timeout=args.timeout,
    )


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
