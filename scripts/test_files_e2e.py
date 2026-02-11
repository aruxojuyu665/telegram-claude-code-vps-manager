#!/usr/bin/env python3
"""E2E test script for file handling with internet sources.

This script tests file handling by:
1. Downloading test files from the internet
2. Sending them to the bot via Telethon
3. Verifying the bot correctly extracts and processes content

Usage:
    python scripts/test_files_e2e.py --format txt
    python scripts/test_files_e2e.py --format json
    python scripts/test_files_e2e.py --format md
    python scripts/test_files_e2e.py --format py
    python scripts/test_files_e2e.py --all
    python scripts/test_files_e2e.py --timeout 120

Author: JARVIS Team
Version: 0.14.0
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import tempfile
from pathlib import Path
from urllib.request import urlopen
from urllib.error import URLError

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

# Test file URLs and expected content
TEST_FILES: dict[str, dict[str, str]] = {
    "txt": {
        "url": "https://httpbin.org/robots.txt",
        "expected": "user-agent",
        "description": "Simple robots.txt file",
    },
    "json": {
        "url": "https://api.github.com/repos/aiogram/aiogram",
        "expected": "aiogram",
        "description": "GitHub API JSON response",
    },
    "md": {
        "url": "https://raw.githubusercontent.com/aiogram/aiogram/dev-3.x/README.md",
        "expected": "aiogram",
        "description": "aiogram README.md",
    },
    "py": {
        "url": "https://raw.githubusercontent.com/python/cpython/main/Lib/json/__init__.py",
        "expected": "json",
        "description": "Python stdlib json module",
    },
}


async def download_test_file(url: str, ext: str) -> Path | None:
    """Download file from URL to temp location.

    Args:
        url: URL to download from.
        ext: File extension.

    Returns:
        Path to downloaded file or None if failed.
    """
    try:
        logger.info(f"Downloading: {url}")
        with tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False) as f:
            with urlopen(url, timeout=30) as response:
                content = response.read()
                f.write(content)
                logger.info(f"Downloaded {len(content)} bytes to {f.name}")
            return Path(f.name)
    except URLError as e:
        logger.error(f"Failed to download {url}: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error downloading {url}: {e}")
        return None


async def test_file_format(
    client: "TelegramClient",  # type: ignore[name-defined]
    bot_id: int,
    format_key: str,
    timeout: float = 60.0,
) -> tuple[bool, str]:
    """Test file handling for a specific format.

    Args:
        client: Connected Telethon client.
        bot_id: Bot user ID.
        format_key: Key from TEST_FILES dict.
        timeout: Timeout in seconds.

    Returns:
        Tuple of (success: bool, message: str).
    """
    if format_key not in TEST_FILES:
        return False, f"Unknown format: {format_key}"

    file_info = TEST_FILES[format_key]
    logger.info(f"Testing {format_key} format: {file_info['description']}")

    # Download test file
    file_path = await download_test_file(file_info["url"], format_key)
    if file_path is None:
        return False, f"Failed to download test file from {file_info['url']}"

    try:
        # Send file to bot
        logger.info(f"Sending {format_key} file to bot...")
        sent_msg = await client.send_file(
            bot_id,
            file_path,
            caption=f"Analyze this {format_key} file and describe its contents briefly.",
        )

        # Wait for response
        logger.info(f"Waiting for response (timeout: {timeout}s)...")
        start_time = asyncio.get_event_loop().time()

        while True:
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed >= timeout:
                return False, f"Bot did not respond within {timeout} seconds"

            messages = await client.get_messages(bot_id, limit=5)
            for msg in messages:
                # Look for response after our message
                if msg.id > sent_msg.id and msg.out is False and msg.text:
                    # Check if it's a processing confirmation or actual response
                    if "Processing file" in msg.text or "Extracted:" in msg.text:
                        logger.info("Bot acknowledged file, waiting for Claude response...")
                        continue

                    # Check for expected content in response
                    expected = file_info["expected"].lower()
                    if expected in msg.text.lower():
                        return True, f"Bot correctly analyzed {format_key} file"
                    else:
                        return True, f"Bot responded: {msg.text[:150]}..."

            await asyncio.sleep(2)

    finally:
        # Cleanup temp file
        try:
            file_path.unlink()
        except Exception:
            pass


async def run_tests(
    api_id: int,
    api_hash: str,
    session_path: str,
    bot_id: int,
    formats: list[str],
    timeout: float,
) -> int:
    """Run file tests for specified formats.

    Args:
        api_id: Telegram API ID.
        api_hash: Telegram API hash.
        session_path: Path to session file.
        bot_id: Bot user ID.
        formats: List of formats to test.
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

        for fmt in formats:
            logger.info("-" * 40)
            success, message = await test_file_format(client, bot_id, fmt, timeout)
            results.append((f"{fmt.upper()} Format Test", success, message))

            # Pause between tests
            if fmt != formats[-1]:
                logger.info("Pausing before next test...")
                await asyncio.sleep(5)

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
        description="E2E test for file handling with internet sources",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/test_files_e2e.py --format txt
  python scripts/test_files_e2e.py --format json
  python scripts/test_files_e2e.py --all
  python scripts/test_files_e2e.py --timeout 120

Available formats:
  txt  - robots.txt from httpbin.org
  json - GitHub API response
  md   - aiogram README.md
  py   - Python stdlib json module
        """,
    )
    parser.add_argument(
        "--format",
        choices=list(TEST_FILES.keys()),
        default=None,
        help="File format to test",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Test all file formats",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=60.0,
        help="Timeout in seconds for each test",
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

    # Determine which formats to test
    if args.all:
        formats = list(TEST_FILES.keys())
    elif args.format:
        formats = [args.format]
    else:
        logger.error("Please specify --format or --all")
        return 1

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
    logger.info("File Handling E2E Test")
    logger.info("=" * 50)
    logger.info(f"Formats: {', '.join(formats)}")
    logger.info(f"Bot ID: {bot_id}")
    logger.info(f"Session: {session_path}")
    logger.info(f"Timeout: {args.timeout}s")
    logger.info("=" * 50)

    return await run_tests(
        api_id=int(api_id),
        api_hash=api_hash,
        session_path=session_path,
        bot_id=int(bot_id),
        formats=formats,
        timeout=args.timeout,
    )


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
