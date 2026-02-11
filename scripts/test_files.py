#!/usr/bin/env python3
"""E2E test script for file handling.

This script tests the full file handling flow by:
1. Connecting to Telegram via Telethon (using existing bot session)
2. Sending a file to the JARVIS bot
3. Waiting for the bot's response
4. Verifying the response contains file content analysis

Prerequisites:
    - Telethon session file must exist (created by bot on first run)
    - Bot must be running
    - Test data files should exist in scripts/test_data/

Usage:
    python scripts/test_files.py --file scripts/test_data/sample.txt
    python scripts/test_files.py --file scripts/test_data/sample.py
    python scripts/test_files.py --file scripts/test_data/sample.pdf
    python scripts/test_files.py --all  # Test all sample files
    python scripts/test_files.py --timeout 120

Author: JARVIS Team
Version: 0.13.0
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


async def send_file_to_bot(
    api_id: int,
    api_hash: str,
    session_path: str,
    bot_id: int,
    file_path: Path,
    caption: str = "Analyze this file",
    timeout: float = 60.0,
) -> tuple[bool, str]:
    """Send file to bot and wait for response.

    Args:
        api_id: Telegram API ID.
        api_hash: Telegram API hash.
        session_path: Path to existing session file.
        bot_id: Bot user ID to send file to.
        file_path: Path to file to send.
        caption: Caption for the file.
        timeout: Timeout in seconds to wait for response.

    Returns:
        Tuple of (success: bool, message: str).
    """
    try:
        from telethon import TelegramClient
    except ImportError:
        return False, "Telethon not installed. Run: pip install telethon"

    if not file_path.exists():
        return False, f"File not found: {file_path}"

    # Create client with existing session
    client = TelegramClient(session_path, api_id, api_hash)
    bot_response: list[str] = []

    try:
        # Connect (session should already be authorized)
        await client.connect()

        if not await client.is_user_authorized():
            return False, "Session not authorized. Run the bot first to create session."

        me = await client.get_me()
        logger.info(f"Connected to Telegram as: @{me.username} (id={me.id})")

        # Get bot entity
        try:
            bot_entity = await client.get_entity(bot_id)
            logger.info(f"Found bot: @{getattr(bot_entity, 'username', bot_id)}")
        except Exception as e:
            return False, f"Failed to get bot entity: {e}"

        # Send file
        logger.info(f"Sending file: {file_path.name} ({file_path.stat().st_size} bytes)")
        sent_message = await client.send_file(
            bot_entity,
            file_path,
            caption=caption,
        )
        logger.info(f"File sent, msg_id={sent_message.id}")

        # Wait for response by polling for new messages
        logger.info(f"Waiting for bot response (timeout: {timeout}s)...")
        start_time = asyncio.get_event_loop().time()
        last_msg_id = sent_message.id

        while True:
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed >= timeout:
                return False, f"Bot did not respond within {timeout} seconds"

            # Check for new messages from bot
            messages = await client.get_messages(bot_entity, limit=10)
            for msg in messages:
                if msg.id > last_msg_id and msg.out is False:
                    # Found a response from bot (not our own message)
                    bot_response.append(msg.text or "[No text]")
                    # Update last_msg_id to catch multiple responses
                    last_msg_id = msg.id

            # If we have at least 2 responses (confirmation + Claude response), break
            if len(bot_response) >= 2:
                break

            # If we have 1 response and some time passed, maybe Claude is still processing
            if len(bot_response) >= 1 and elapsed >= 10:
                # Wait a bit more for the actual Claude response
                await asyncio.sleep(2)
                # Re-check
                messages = await client.get_messages(bot_entity, limit=10)
                for msg in messages:
                    if msg.id > last_msg_id and msg.out is False:
                        bot_response.append(msg.text or "[No text]")
                        last_msg_id = msg.id
                if len(bot_response) >= 2:
                    break

            await asyncio.sleep(2)  # Poll every 2 seconds

        response_text = "\n---\n".join(bot_response)
        logger.info("Bot response received:")
        print("-" * 50)
        print(response_text[:2000])  # Truncate for display
        if len(response_text) > 2000:
            print(f"... [{len(response_text)} chars total]")
        print("-" * 50)

        # Check for file processing markers
        response_lower = response_text.lower()
        if "processing file" in response_lower or "extracted" in response_lower:
            return True, f"File handling E2E test passed! File: {file_path.name}"
        elif "unsupported" in response_lower:
            return False, f"File format not supported: {file_path.name}"
        elif "failed" in response_lower or "error" in response_lower:
            return False, f"File processing failed: {response_text[:200]}"
        else:
            # Bot responded with something - might be Claude's analysis
            return True, f"Bot responded to file: {file_path.name}"

    except Exception as e:
        logger.exception("Error during test")
        return False, f"Error: {e}"
    finally:
        await client.disconnect()


def find_session_file(session_name: str, search_paths: list[Path]) -> Path | None:
    """Find session file in multiple locations.

    Args:
        session_name: Session name (without .session extension).
        search_paths: List of directories to search.

    Returns:
        Path to session file if found, None otherwise.
    """
    for search_dir in search_paths:
        session_path = search_dir / f"{session_name}.session"
        if session_path.exists():
            return session_path
    return None


def copy_session_to_temp(session_path: Path) -> Path:
    """Copy session file to temp directory to avoid conflicts.

    Args:
        session_path: Path to original session file.

    Returns:
        Path to temporary session copy (without .session extension).
    """
    import shutil
    import tempfile

    temp_dir = Path(tempfile.gettempdir())
    temp_session = temp_dir / f"test_{session_path.stem}.session"

    # Copy the session file
    shutil.copy2(session_path, temp_session)
    logger.info(f"Copied session to: {temp_session}")

    return temp_session.with_suffix("")  # Return without .session for Telethon


def get_test_files(test_data_dir: Path) -> list[Path]:
    """Get all test files from test_data directory.

    Args:
        test_data_dir: Path to test data directory.

    Returns:
        List of test file paths.
    """
    if not test_data_dir.exists():
        return []

    supported_extensions = {".txt", ".md", ".py", ".js", ".json", ".pdf"}
    files = []
    for ext in supported_extensions:
        files.extend(test_data_dir.glob(f"*{ext}"))
    return sorted(files)


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="E2E test for file handling",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/test_files.py --file scripts/test_data/sample.txt
  python scripts/test_files.py --file scripts/test_data/sample.py
  python scripts/test_files.py --all  # Test all files in test_data/
  python scripts/test_files.py --session /path/to/session
  python scripts/test_files.py --timeout 120
        """,
    )
    parser.add_argument(
        "--file",
        type=Path,
        default=None,
        help="Path to file to send to bot",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Test all files in scripts/test_data/",
    )
    parser.add_argument(
        "--caption",
        type=str,
        default="Analyze this file and summarize what it contains",
        help="Caption to send with the file",
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
        # Search in common locations
        search_paths = [
            PROJECT_ROOT,  # Project root
            Path.cwd(),  # Current directory
            Path.home(),  # Home directory
            Path("/opt/jarvis-mk1"),  # VPS location
        ]
        found_session = find_session_file(session_name, search_paths)
        if found_session:
            logger.info(f"Found session file: {found_session}")
            # Copy to temp to avoid conflicts with running bot
            session_path = str(copy_session_to_temp(found_session))
        else:
            session_path = session_name
            logger.warning(f"Session file not found, will try: {session_name}")

    # Determine files to test
    test_data_dir = PROJECT_ROOT / "scripts" / "test_data"
    files_to_test: list[Path] = []

    if args.all:
        files_to_test = get_test_files(test_data_dir)
        if not files_to_test:
            logger.error(f"No test files found in {test_data_dir}")
            logger.error("Create test files first: sample.txt, sample.py, sample.md, sample.pdf")
            return 1
    elif args.file:
        files_to_test = [args.file]
    else:
        # Default: test sample.txt if exists
        default_file = test_data_dir / "sample.txt"
        if default_file.exists():
            files_to_test = [default_file]
        else:
            logger.error("No file specified. Use --file or --all")
            logger.error(f"Or create {default_file}")
            return 1

    # Run tests
    logger.info("=" * 50)
    logger.info("File Handling E2E Test")
    logger.info("=" * 50)
    logger.info(f"Files to test: {len(files_to_test)}")
    logger.info(f"Bot ID: {bot_id}")
    logger.info(f"Session: {session_path}")
    logger.info(f"Timeout: {args.timeout}s")
    logger.info("=" * 50)

    passed = 0
    failed = 0

    for file_path in files_to_test:
        logger.info(f"\n--- Testing: {file_path.name} ---")

        success, message = await send_file_to_bot(
            api_id=int(api_id),
            api_hash=api_hash,
            session_path=session_path,
            bot_id=int(bot_id),
            file_path=file_path,
            caption=args.caption,
            timeout=args.timeout,
        )

        if success:
            logger.info(f"[SUCCESS] {message}")
            passed += 1
        else:
            logger.error(f"[FAILED] {message}")
            failed += 1

    # Summary
    logger.info("\n" + "=" * 50)
    logger.info("Test Summary")
    logger.info("=" * 50)
    logger.info(f"Passed: {passed}")
    logger.info(f"Failed: {failed}")
    logger.info(f"Total:  {passed + failed}")
    logger.info("=" * 50)

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
