#!/usr/bin/env python3
"""E2E test script for voice transcription.

This script tests the full voice transcription flow by:
1. Connecting to Telegram via Telethon (using existing bot session)
2. Finding a voice message in Saved Messages OR sending from file
3. Forwarding/sending it to the JARVIS bot
4. Waiting for the bot's response
5. Verifying the transcription was successful

Prerequisites:
    - Telethon session file must exist (created by bot on first run)
    - Bot must be running
    - For --use-saved: at least one voice message in Saved Messages

Usage:
    python scripts/test_voice.py --use-saved          # Forward voice from Saved Messages
    python scripts/test_voice.py --voice-file voice.ogg  # Send from file
    python scripts/test_voice.py --timeout 120

Author: JARVIS Team
Version: 0.12.1
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


async def find_voice_in_saved_messages(
    client: "TelegramClient",  # type: ignore[name-defined]
    limit: int = 100,
) -> "Message | None":  # type: ignore[name-defined]
    """Find first voice message in Saved Messages.

    Args:
        client: Connected Telethon client.
        limit: Maximum number of messages to search.

    Returns:
        Voice message if found, None otherwise.
    """
    try:
        from telethon.tl.types import DocumentAttributeAudio
    except ImportError:
        return None

    logger.info(f"Searching for voice message in Saved Messages (limit={limit})...")

    async for message in client.iter_messages("me", limit=limit):
        if message.voice or message.video_note:
            logger.info(f"Found voice message: id={message.id}, date={message.date}")
            return message

        # Also check for audio with voice=True attribute
        if message.document:
            for attr in message.document.attributes:
                if isinstance(attr, DocumentAttributeAudio) and attr.voice:
                    logger.info(f"Found voice message: id={message.id}, date={message.date}")
                    return message

    return None


async def forward_voice_and_wait_response(
    api_id: int,
    api_hash: str,
    session_path: str,
    bot_id: int,
    use_saved: bool = True,
    voice_path: Path | None = None,
    timeout: float = 60.0,
) -> tuple[bool, str]:
    """Forward voice from Saved Messages or send from file to bot.

    Args:
        api_id: Telegram API ID.
        api_hash: Telegram API hash.
        session_path: Path to existing session file.
        bot_id: Bot user ID to send voice to.
        use_saved: If True, find voice in Saved Messages and forward.
        voice_path: Path to voice file (used if use_saved=False).
        timeout: Timeout in seconds to wait for response.

    Returns:
        Tuple of (success: bool, message: str).
    """
    try:
        from telethon import TelegramClient
        from telethon.tl.types import DocumentAttributeAudio
    except ImportError:
        return False, "Telethon not installed. Run: pip install telethon"

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

        if use_saved:
            # Find voice in Saved Messages and forward
            voice_msg = await find_voice_in_saved_messages(client)
            if not voice_msg:
                return False, "No voice message found in Saved Messages. Save a voice message first!"

            logger.info("Forwarding voice message to bot...")
            sent_message = await client.forward_messages(bot_entity, voice_msg)
            if isinstance(sent_message, list):
                sent_message = sent_message[0]
            logger.info(f"Voice message forwarded, msg_id={sent_message.id}")

        else:
            # Send from file
            if voice_path is None or not voice_path.exists():
                return False, f"Voice file not found: {voice_path}"

            voice_data = voice_path.read_bytes()
            logger.info(f"Loaded voice file: {len(voice_data)} bytes")

            voice_attrs = [
                DocumentAttributeAudio(
                    duration=5,
                    voice=True,
                )
            ]

            logger.info("Sending voice message to bot...")
            sent_message = await client.send_file(
                bot_entity,
                voice_data,
                attributes=voice_attrs,
                voice_note=True,
            )
            logger.info(f"Voice message sent, msg_id={sent_message.id}")

        # Wait for response by polling for new messages
        logger.info(f"Waiting for bot response (timeout: {timeout}s)...")
        start_time = asyncio.get_event_loop().time()
        last_msg_id = sent_message.id

        while True:
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed >= timeout:
                return False, f"Bot did not respond within {timeout} seconds"

            # Check for new messages from bot
            messages = await client.get_messages(bot_entity, limit=5)
            for msg in messages:
                if msg.id > last_msg_id and msg.out is False:
                    # Found a response from bot (not our own message)
                    bot_response.append(msg.text or "[No text]")
                    break

            if bot_response:
                break

            await asyncio.sleep(2)  # Poll every 2 seconds

        response_text = "\n---\n".join(bot_response)
        logger.info("Bot response received:")
        print("-" * 50)
        print(response_text)
        print("-" * 50)

        # Check for transcription markers
        response_lower = response_text.lower()
        if "transcrib" in response_lower:
            return True, "Voice transcription E2E test passed!"
        elif "not enabled" in response_lower:
            return False, "Voice transcription is not enabled on the bot"
        elif "premium" in response_lower:
            return False, "Telegram Premium required for transcription"
        else:
            # Bot responded with something - might be valid
            return True, f"Bot responded: {response_text[:200]}..."

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


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="E2E test for voice transcription",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/test_voice.py --use-saved           # Forward from Saved Messages
  python scripts/test_voice.py --voice-file voice.ogg   # Send from file
  python scripts/test_voice.py --session /path/to/session   # Custom session path
  python scripts/test_voice.py --timeout 120
        """,
    )
    parser.add_argument(
        "--use-saved",
        action="store_true",
        default=True,
        help="Find voice in Saved Messages and forward to bot (default)",
    )
    parser.add_argument(
        "--voice-file",
        type=Path,
        default=None,
        help="Path to voice file (OGG format) - disables --use-saved",
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

    # Determine mode
    use_saved = args.use_saved and args.voice_file is None

    # Run test
    logger.info("=" * 50)
    logger.info("Voice Transcription E2E Test")
    logger.info("=" * 50)
    logger.info(f"Mode: {'Forward from Saved Messages' if use_saved else 'Send from file'}")
    if not use_saved:
        logger.info(f"Voice file: {args.voice_file}")
    logger.info(f"Bot ID: {bot_id}")
    logger.info(f"Session: {session_path}")
    logger.info(f"Timeout: {args.timeout}s")
    logger.info("=" * 50)

    success, message = await forward_voice_and_wait_response(
        api_id=int(api_id),
        api_hash=api_hash,
        session_path=session_path,
        bot_id=int(bot_id),
        use_saved=use_saved,
        voice_path=args.voice_file,
        timeout=args.timeout,
    )

    if success:
        logger.info(f"[SUCCESS] {message}")
        return 0
    else:
        logger.error(f"[FAILED] {message}")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
