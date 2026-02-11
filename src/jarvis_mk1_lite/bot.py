"""Telegram Bot handlers using aiogram 3.x.

This module implements the Telegram bot with:
- Whitelist middleware for security
- Command handlers (/start, /new, /status, /help, /metrics)
- Message handling with Claude Bridge integration
- Long message splitting for Telegram's character limit
- Socratic Gate integration for dangerous command confirmation
- Metrics tracking and rate limiting
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from aiogram import Bot, Dispatcher, F, types
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramNetworkError,
    TelegramRetryAfter,
)
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    BotCommand,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    TelegramObject,
)

from jarvis_mk1_lite.bridge import ClaudeBridge, SessionInfo, claude_bridge
from jarvis_mk1_lite.exceptions import (
    InvalidSessionNameError,
    SessionAlreadyExistsError,
    SessionLimitExceededError,
    SessionNotFoundError,
)
from jarvis_mk1_lite.chunker import SmartChunker
from jarvis_mk1_lite.config import Settings, get_settings
from jarvis_mk1_lite.file_processor import (
    FileProcessingError,
    FileProcessor,
    UnsupportedFileTypeError,
)
from jarvis_mk1_lite.file_sender import FileRequest, FileSender
from jarvis_mk1_lite.metrics import format_metrics_message, metrics, rate_limiter
from jarvis_mk1_lite.safety import RiskLevel, socratic_gate
from jarvis_mk1_lite.transcription import (
    PremiumRequiredError,
    TranscriptionError,
    TranscriptionPendingError,
    VoiceTranscriber,
    get_transcriber,
)

if TYPE_CHECKING:
    pass

# Global transcriber instance (initialized on first use)
_voice_transcriber: VoiceTranscriber | None = None

# Global file sender instance
_file_sender: FileSender | None = None

logger = logging.getLogger(__name__)

# Regex patterns for file markers in Claude responses
FILE_MARKER_PATTERN = re.compile(r"\[FILE:([^\]]+)\]")
DIR_MARKER_PATTERN = re.compile(r"\[DIR:([^\]]+)\]")
GLOB_MARKER_PATTERN = re.compile(r"\[GLOB:([^\]]+)\]")


def get_file_sender() -> FileSender:
    """Get or create the global FileSender instance.

    Uses settings from config for initialization.

    Returns:
        The FileSender instance.
    """
    global _file_sender
    if _file_sender is None:
        settings = get_settings()
        _file_sender = FileSender(
            max_file_size_mb=settings.file_send_max_size_mb,
            compress_large_files=settings.file_send_compress_large,
            temp_dir=settings.file_send_temp_dir,
        )
    return _file_sender


def parse_file_markers(text: str) -> list[FileRequest]:
    """Parse file markers from Claude response text.

    Extracts [FILE:path], [DIR:path], and [GLOB:pattern] markers
    from the response and returns corresponding FileRequest objects.

    Args:
        text: The response text from Claude.

    Returns:
        List of FileRequest objects extracted from the text.
    """
    requests: list[FileRequest] = []

    # Find all FILE markers
    for match in FILE_MARKER_PATTERN.finditer(text):
        path = match.group(1).strip()
        if path:
            requests.append(FileRequest(path=path, request_type="file"))

    # Find all DIR markers
    for match in DIR_MARKER_PATTERN.finditer(text):
        path = match.group(1).strip()
        if path:
            requests.append(FileRequest(path=path, request_type="dir"))

    # Find all GLOB markers
    for match in GLOB_MARKER_PATTERN.finditer(text):
        pattern = match.group(1).strip()
        if pattern:
            requests.append(FileRequest(path=pattern, request_type="glob"))

    return requests


def strip_file_markers(text: str) -> str:
    """Remove file markers from text for display.

    Args:
        text: Text potentially containing file markers.

    Returns:
        Text with file markers removed.
    """
    text = FILE_MARKER_PATTERN.sub("", text)
    text = DIR_MARKER_PATTERN.sub("", text)
    text = GLOB_MARKER_PATTERN.sub("", text)
    # Clean up extra whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


@dataclass
class PendingConfirmation:
    """Stores a pending dangerous command awaiting confirmation.

    Attributes:
        command: The original command text.
        risk_level: The risk level of the command.
        timestamp: Unix timestamp when confirmation was requested.
    """

    command: str
    risk_level: RiskLevel
    timestamp: float


# Confirmation timeout in seconds (5 minutes)
CONFIRMATION_TIMEOUT = 300

# Maximum number of pending confirmations (prevent memory exhaustion)
MAX_PENDING_CONFIRMATIONS = 100

# Maximum items in wide context mode (prevent memory exhaustion)
MAX_WIDE_CONTEXT_MESSAGES = 50
MAX_WIDE_CONTEXT_FILES = 20

# Maximum verbose users (prevent memory exhaustion)
MAX_VERBOSE_USERS = 100


@dataclass
class PendingContext:
    """Accumulated context for message batching.

    Attributes:
        messages: List of accumulated text messages.
        files: List of (filename, content) tuples for accumulated files.
        timer: Asyncio task for delayed send (None if wide mode).
        wide_mode: True if in /wide_context mode (manual Accept required).
        created_at: Unix timestamp when context was created.
        status_message: The message with Accept/Cancel buttons (for editing).
    """

    messages: list[str] = field(default_factory=list)
    files: list[tuple[str, str]] = field(default_factory=list)
    timer: asyncio.Task[None] | None = None
    wide_mode: bool = False
    created_at: float = field(default_factory=time.time)
    status_message: types.Message | None = None


# Global storage for pending contexts (per user)
_pending_contexts: dict[int, PendingContext] = {}

# Global storage for verbose mode users (OrderedDict for LRU eviction)
_verbose_users: dict[int, float] = {}  # user_id -> timestamp


@dataclass
class VerboseContext:
    """Context for verbose mode output batching.

    Attributes:
        lines: Accumulated log lines to send.
        last_flush_time: Unix timestamp of last flush.
        status_message: The message to edit with updates.
        total_actions: Counter of total actions performed.
    """

    lines: list[str] = field(default_factory=list)
    last_flush_time: float = field(default_factory=time.time)
    status_message: types.Message | None = None
    total_actions: int = 0


# Global storage for active verbose contexts
_verbose_contexts: dict[int, VerboseContext] = {}

# Global SmartChunker instance
_chunker: SmartChunker | None = None


def get_chunker(max_size: int = 4000) -> SmartChunker:
    """Get or create the global SmartChunker instance."""
    global _chunker
    if _chunker is None or _chunker.max_size != max_size:
        _chunker = SmartChunker(max_size=max_size)
    return _chunker


def _format_session_age(timestamp: float) -> str:
    """Format session age as human-readable string.

    Args:
        timestamp: Unix timestamp of last activity.

    Returns:
        Formatted age string like "5m ago", "2h ago", "1d ago".
    """
    if timestamp == 0:
        return "new"

    age_seconds = time.time() - timestamp

    if age_seconds < 60:
        return "just now"
    elif age_seconds < 3600:
        minutes = int(age_seconds / 60)
        return f"{minutes}m ago"
    elif age_seconds < 86400:
        hours = int(age_seconds / 3600)
        return f"{hours}h ago"
    else:
        days = int(age_seconds / 86400)
        return f"{days}d ago"


class PendingConfirmationManager:
    """Manages pending confirmations with automatic cleanup.

    Provides thread-safe access to pending confirmations storage
    and automatic cleanup of expired entries.
    """

    def __init__(
        self,
        timeout: int = CONFIRMATION_TIMEOUT,
        max_pending: int = MAX_PENDING_CONFIRMATIONS,
    ) -> None:
        """Initialize the manager.

        Args:
            timeout: Timeout in seconds for confirmations.
            max_pending: Maximum number of pending confirmations.
        """
        self._storage: dict[int, PendingConfirmation] = {}
        self._timeout = timeout
        self._max_pending = max_pending

    def add(self, user_id: int, confirmation: PendingConfirmation) -> None:
        """Add a pending confirmation.

        Args:
            user_id: Telegram user ID.
            confirmation: The pending confirmation to store.
        """
        # Cleanup expired before adding
        self.cleanup_expired()

        # Enforce limit - remove oldest if at max
        if len(self._storage) >= self._max_pending:
            oldest_user_id = min(
                self._storage.keys(),
                key=lambda uid: self._storage[uid].timestamp,
            )
            del self._storage[oldest_user_id]
            logger.warning(
                "Evicted oldest pending confirmation due to limit",
                extra={"evicted_user_id": oldest_user_id, "max_pending": self._max_pending},
            )

        self._storage[user_id] = confirmation

    def get(self, user_id: int) -> PendingConfirmation | None:
        """Get a pending confirmation for a user.

        Args:
            user_id: Telegram user ID.

        Returns:
            The pending confirmation if exists and not expired, None otherwise.
        """
        confirmation = self._storage.get(user_id)
        if confirmation and self._is_expired(confirmation):
            del self._storage[user_id]
            return None
        return confirmation

    def remove(self, user_id: int) -> bool:
        """Remove a pending confirmation.

        Args:
            user_id: Telegram user ID.

        Returns:
            True if removed, False if not found.
        """
        if user_id in self._storage:
            del self._storage[user_id]
            return True
        return False

    def contains(self, user_id: int) -> bool:
        """Check if user has a pending confirmation.

        Args:
            user_id: Telegram user ID.

        Returns:
            True if exists and not expired.
        """
        return self.get(user_id) is not None

    def _is_expired(self, confirmation: PendingConfirmation) -> bool:
        """Check if a confirmation is expired.

        Args:
            confirmation: The confirmation to check.

        Returns:
            True if expired.
        """
        return time.time() - confirmation.timestamp > self._timeout

    def cleanup_expired(self) -> int:
        """Remove all expired confirmations.

        Returns:
            Number of removed confirmations.
        """
        now = time.time()
        expired_users = [
            user_id
            for user_id, conf in self._storage.items()
            if now - conf.timestamp > self._timeout
        ]

        for user_id in expired_users:
            del self._storage[user_id]
            logger.debug("Cleaned up expired confirmation", extra={"user_id": user_id})

        return len(expired_users)

    def count(self) -> int:
        """Get the number of pending confirmations.

        Returns:
            Number of pending confirmations.
        """
        return len(self._storage)


# Global instance for pending confirmations
pending_confirmations_manager = PendingConfirmationManager()

# Legacy dict for backward compatibility (used in existing code)
# TODO: Migrate all usages to pending_confirmations_manager in future versions
pending_confirmations: dict[int, PendingConfirmation] = pending_confirmations_manager._storage


async def send_with_retry(
    send_func: Callable[[], Awaitable[types.Message | bool | None]],
    max_retries: int = 3,
    base_delay: float = 1.0,
) -> types.Message | bool | None:
    """Execute a send function with retry logic for Telegram API errors.

    Handles:
    - TelegramRetryAfter: Wait specified time and retry
    - TelegramNetworkError: Exponential backoff retry
    - TelegramBadRequest: Log and return None (don't retry)

    Args:
        send_func: Async function that sends message/edits.
        max_retries: Maximum number of retry attempts.
        base_delay: Base delay for exponential backoff.

    Returns:
        Result of send_func or None if all retries failed.
    """
    last_error: Exception | None = None

    for attempt in range(max_retries + 1):
        try:
            return await send_func()
        except TelegramRetryAfter as e:
            # Telegram asks us to wait
            wait_time = e.retry_after
            logger.warning(
                "Rate limited by Telegram, waiting",
                extra={"retry_after": wait_time, "attempt": attempt},
            )
            await asyncio.sleep(wait_time)
            last_error = e
        except TelegramNetworkError as e:
            # Network error, use exponential backoff
            if attempt < max_retries:
                delay = base_delay * (2**attempt)
                logger.warning(
                    "Network error, retrying",
                    extra={"error": str(e), "delay": delay, "attempt": attempt},
                )
                await asyncio.sleep(delay)
            last_error = e
        except TelegramBadRequest as e:
            error_str = str(e).lower()
            # Handle specific recoverable errors
            if "message is not modified" in error_str:
                # Message content didn't change, ignore
                logger.debug("Message not modified, ignoring")
                return None
            if "message to edit not found" in error_str:
                # Message was deleted, can't edit
                logger.warning("Message to edit not found")
                return None
            if "can't parse entities" in error_str:
                # Markdown error - don't retry, caller should handle
                raise
            # Other bad requests - log and don't retry
            logger.error("Telegram bad request", extra={"error": str(e)})
            return None

    if last_error:
        logger.error(
            "All retries failed",
            extra={"max_retries": max_retries, "error": str(last_error)},
        )
    return None


async def send_long_message(
    message: types.Message,
    text: str,
    chunk_size: int = 4000,
) -> None:
    """Send a long message by splitting it into chunks using SmartChunker.

    Includes fallback to plain text if Markdown parsing fails.
    Uses retry logic for Telegram API errors.

    Args:
        message: The original message to reply to.
        text: The text to send.
        chunk_size: Maximum size of each chunk (default 4000 for Telegram's limit).
    """
    chunker = get_chunker(max_size=chunk_size)
    result = chunker.chunk(text)

    for i, chunk in enumerate(result.chunks):
        try:
            await send_with_retry(lambda c=chunk: message.answer(c))
        except TelegramBadRequest as e:
            if "can't parse entities" in str(e).lower():
                # Markdown parsing failed, retry as plain text
                logger.warning(
                    "Markdown parse error, sending as plain text",
                    extra={"error": str(e), "chunk_index": i, "chunk_length": len(chunk)},
                )
                await send_with_retry(lambda c=chunk: message.answer(c, parse_mode=None))
            else:
                raise

        if i < result.total_parts - 1:
            await asyncio.sleep(0.5)  # Delay between chunks


def is_verbose_enabled(user_id: int) -> bool:
    """Check if verbose mode is enabled for a user.

    Args:
        user_id: Telegram user ID.

    Returns:
        True if verbose mode is enabled.
    """
    return user_id in _verbose_users


def toggle_verbose(user_id: int) -> bool:
    """Toggle verbose mode for a user.

    Uses LRU eviction when max users limit is reached.

    Args:
        user_id: Telegram user ID.

    Returns:
        True if verbose is now enabled, False if disabled.
    """
    if user_id in _verbose_users:
        del _verbose_users[user_id]
        # Clean up any active verbose context
        _verbose_contexts.pop(user_id, None)
        return False

    # Enforce limit with LRU eviction
    if len(_verbose_users) >= MAX_VERBOSE_USERS:
        # Find and remove oldest user (earliest timestamp)
        oldest_user = min(_verbose_users, key=lambda uid: _verbose_users[uid])
        del _verbose_users[oldest_user]
        _verbose_contexts.pop(oldest_user, None)
        logger.warning(
            "Verbose users limit reached, evicted oldest user",
            extra={"evicted_user_id": oldest_user},
        )

    _verbose_users[user_id] = time.time()
    return True


def _format_verbose_line(line: str, max_length: int = 100) -> str | None:
    """Format a line for verbose output.

    Args:
        line: Raw line from Claude CLI output.
        max_length: Maximum line length.

    Returns:
        Formatted line or None if should be skipped.
    """
    line = line.strip()
    if not line:
        return None

    # Skip JSON-only lines (they're not human-readable)
    if line.startswith("{") or line.startswith("["):
        return None

    # Truncate long lines
    if len(line) > max_length:
        line = line[: max_length - 3] + "..."

    return f"`{line}`"


async def flush_verbose_context(
    user_id: int,
    message: types.Message,
    force: bool = False,
) -> None:
    """Flush accumulated verbose lines to user.

    Args:
        user_id: Telegram user ID.
        message: Message to reply to or edit.
        force: Force flush even if batch not full.
    """
    ctx = _verbose_contexts.get(user_id)
    if ctx is None or not ctx.lines:
        return

    settings = get_settings()
    now = time.time()

    # Check if should flush
    should_flush = (
        force
        or len(ctx.lines) >= settings.verbose_batch_size
        or (now - ctx.last_flush_time) >= settings.verbose_flush_interval
    )

    if not should_flush:
        return

    # Build message content
    lines_text = "\n".join(ctx.lines)
    status_text = f"*Processing...* ({ctx.total_actions} actions)\n\n{lines_text}"

    # Truncate if too long
    if len(status_text) > 4000:
        status_text = status_text[:3900] + "\n\n_...truncated_"

    # Capture status_message reference to avoid race condition
    status_msg = ctx.status_message

    # Try to edit existing message, or send new one
    try:
        if status_msg:
            await send_with_retry(lambda: status_msg.edit_text(status_text))
        else:
            result = await send_with_retry(lambda: message.answer(status_text))
            if isinstance(result, types.Message):
                ctx.status_message = result
    except Exception as e:
        # On any error, try sending new message
        logger.warning("Failed to update verbose message", extra={"error": str(e)})
        with contextlib.suppress(Exception):
            result = await message.answer(status_text)
            ctx.status_message = result

    # Clear lines and update timestamp
    ctx.lines = []
    ctx.last_flush_time = now


async def add_verbose_line(
    user_id: int,
    line: str,
    message: types.Message,
) -> None:
    """Add a line to verbose output buffer.

    Args:
        user_id: Telegram user ID.
        line: Line to add.
        message: Message for replying.
    """
    if not is_verbose_enabled(user_id):
        return

    settings = get_settings()
    formatted = _format_verbose_line(line, settings.verbose_max_line_length)
    if formatted is None:
        return

    # Get or create context
    if user_id not in _verbose_contexts:
        _verbose_contexts[user_id] = VerboseContext()

    ctx = _verbose_contexts[user_id]
    ctx.lines.append(formatted)
    ctx.total_actions += 1

    # Try to flush
    await flush_verbose_context(user_id, message)


async def finalize_verbose_context(user_id: int, message: types.Message) -> None:
    """Finalize verbose context after command completes.

    Args:
        user_id: Telegram user ID.
        message: Message for replying.
    """
    if user_id not in _verbose_contexts:
        return

    ctx = _verbose_contexts[user_id]

    # Final flush
    if ctx.lines:
        await flush_verbose_context(user_id, message, force=True)

    # Capture references to avoid race conditions
    status_msg = ctx.status_message
    total_actions = ctx.total_actions

    # Update status message to show completion
    if status_msg and total_actions > 0:
        try:
            await send_with_retry(
                lambda: status_msg.edit_text(f"Completed ({total_actions} actions)")
            )
        except Exception as e:
            logger.warning("Failed to finalize verbose message", extra={"error": str(e)})

    # Clean up context
    _verbose_contexts.pop(user_id, None)


def _combine_context(ctx: PendingContext) -> str:
    """Combine accumulated messages and files into single prompt.

    Args:
        ctx: The pending context to combine.

    Returns:
        Combined text from all messages and files.
    """
    parts: list[str] = []

    # Add messages
    for msg in ctx.messages:
        parts.append(msg)

    # Add files
    for filename, content in ctx.files:
        parts.append(f"\n=== File: {filename} ===\n{content}\n=== End of file ===")

    return "\n\n".join(parts)


async def _delayed_send(
    user_id: int,
    delay: float,
    message: types.Message,
    bridge: ClaudeBridge,
) -> None:
    """Wait for delay, then send accumulated context to Claude.

    Args:
        user_id: The user ID.
        delay: Delay in seconds before sending.
        message: The message to reply to.
        bridge: The Claude bridge instance.
    """
    await asyncio.sleep(delay)

    ctx = _pending_contexts.pop(user_id, None)
    if ctx is None:
        return

    # Combine all messages and files
    combined = _combine_context(ctx)

    if combined.strip():
        # Send to Claude
        await execute_and_respond(message, combined, bridge)


async def cleanup_stale_contexts(timeout: int = 300) -> int:
    """Remove contexts older than timeout.

    Args:
        timeout: Maximum age in seconds for a context.

    Returns:
        Number of cleaned up contexts.
    """
    now = time.time()
    stale_users = [
        user_id for user_id, ctx in _pending_contexts.items() if now - ctx.created_at > timeout
    ]

    for user_id in stale_users:
        ctx = _pending_contexts.pop(user_id)
        if ctx.timer:
            ctx.timer.cancel()
        logger.info(f"Cleaned up stale context for user {user_id}")

    return len(stale_users)


async def _keep_alive_loop(message: types.Message) -> None:
    """Send typing action every 5 seconds to keep connection alive.

    This prevents Telegram from showing timeout during long operations.

    Args:
        message: The message to keep alive for.
    """
    try:
        while True:
            await asyncio.sleep(5)
            await message.bot.send_chat_action(
                chat_id=message.chat.id,
                action="typing"  # type: ignore[union-attr]
            )
    except asyncio.CancelledError:
        # Task was cancelled, normal exit
        pass
    except Exception as e:
        # Log but don't raise - keep-alive is best-effort
        logger.warning(f"Keep-alive error: {e}")


async def execute_and_respond(
    message: types.Message,
    text: str,
    bridge: ClaudeBridge,
) -> None:
    """Execute a command via Claude Bridge and respond.

    Supports verbose mode for real-time action streaming.

    Args:
        message: The Telegram message to respond to.
        text: The text/command to send to Claude.
        bridge: The Claude Bridge instance.
    """
    if message.from_user is None:
        return

    user_id = message.from_user.id

    # Send typing action
    await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")  # type: ignore[union-attr]

    # Start keep-alive task to show activity during long operations
    keep_alive_task = asyncio.create_task(_keep_alive_loop(message))

    try:
        # Create verbose callback if verbose mode is enabled
        verbose_callback = None
        if is_verbose_enabled(user_id):

            async def verbose_callback(line: str) -> None:
                await add_verbose_line(user_id, line, message)

        # Call Claude Bridge with optional verbose callback
        response = await bridge.send(user_id, text, verbose_callback=verbose_callback)

        # Stop keep-alive task
        keep_alive_task.cancel()
        try:
            await keep_alive_task
        except asyncio.CancelledError:
            pass

        # Finalize verbose context if enabled
        if is_verbose_enabled(user_id):
            await finalize_verbose_context(user_id, message)

        if response.success:
            logger.info(
                "Message processed successfully",
                extra={"user_id": user_id, "response_length": len(response.content)},
            )

            # Parse file markers from response
            file_requests = parse_file_markers(response.content)

            # Send text response (with markers stripped if files present)
            if file_requests:
                display_text = strip_file_markers(response.content)
                if display_text:
                    await send_long_message(message, display_text)
            else:
                await send_long_message(message, response.content)

            # Process file requests if any (with DoS protection limit)
            if file_requests:
                # Limit number of file requests to prevent abuse
                from jarvis_mk1_lite.file_sender import MAX_FILE_REQUESTS_PER_RESPONSE
                if len(file_requests) > MAX_FILE_REQUESTS_PER_RESPONSE:
                    logger.warning(
                        "Too many file requests (%d), limiting to %d",
                        len(file_requests),
                        MAX_FILE_REQUESTS_PER_RESPONSE,
                        extra={"user_id": user_id},
                    )
                    file_requests = file_requests[:MAX_FILE_REQUESTS_PER_RESPONSE]

                logger.info(
                    "Processing %d file requests",
                    len(file_requests),
                    extra={"user_id": user_id},
                )
                file_sender = get_file_sender()
                try:
                    results = await file_sender.process_file_requests(message, file_requests)
                    # Log results
                    success_count = sum(1 for r in results if r.success)
                    fail_count = len(results) - success_count
                    if fail_count > 0:
                        logger.warning(
                            "File send results: %d success, %d failed",
                            success_count,
                            fail_count,
                            extra={"user_id": user_id},
                        )
                except Exception as e:
                    logger.exception("Error processing file requests", extra={"user_id": user_id})
                    await message.answer(f"Error sending files: {e}")
        else:
            error_msg = response.error or "Unknown error occurred"

            # Check if we have partial results on timeout
            if "timed out" in error_msg.lower() and response.content.strip():
                logger.warning(
                    "Timeout with partial results",
                    extra={"user_id": user_id, "partial_length": len(response.content)},
                )
                # Send partial content with warning
                await send_long_message(
                    message,
                    f"{response.content}\n\n⚠️ **Operation timed out.** Showing partial results above."
                )
                metrics.record_error(user_id)
            else:
                logger.error(
                    "Claude Bridge error",
                    extra={"user_id": user_id, "error": error_msg},
                )
                metrics.record_error(user_id)
                await message.answer(f"Error: {error_msg}")
    except Exception:
        logger.exception("Unexpected error processing message", extra={"user_id": user_id})
        metrics.record_error(user_id)
        await message.answer("An error occurred while processing your request. Please try again.")
        # Clean up verbose context on error
        if is_verbose_enabled(user_id):
            _verbose_contexts.pop(user_id, None)
    finally:
        # Always cancel keep-alive task
        keep_alive_task.cancel()
        try:
            await keep_alive_task
        except asyncio.CancelledError:
            pass


def is_confirmation_expired(pending: PendingConfirmation) -> bool:
    """Check if a pending confirmation has expired.

    Args:
        pending: The pending confirmation to check.

    Returns:
        True if expired, False otherwise.
    """
    return time.time() - pending.timestamp > CONFIRMATION_TIMEOUT


async def handle_confirmation(
    message: types.Message,
    text: str,
    bridge: ClaudeBridge,
) -> bool:
    """Handle a potential confirmation response.

    Args:
        message: The Telegram message.
        text: The message text.
        bridge: The Claude Bridge instance.

    Returns:
        True if this was a confirmation response (handled), False otherwise.
    """
    if message.from_user is None:
        return False

    user_id = message.from_user.id

    # Check if user has pending confirmation
    if user_id not in pending_confirmations:
        return False

    pending = pending_confirmations[user_id]

    # Check for expiration
    if is_confirmation_expired(pending):
        del pending_confirmations[user_id]
        await message.answer("Confirmation expired. Please send the command again.")
        return True

    # Check for cancellation
    if socratic_gate.is_cancellation(text):
        del pending_confirmations[user_id]
        logger.info(
            "User cancelled dangerous command",
            extra={"user_id": user_id, "risk_level": pending.risk_level.value},
        )
        await message.answer("Operation cancelled.")
        return True

    # Check for valid confirmation
    if socratic_gate.is_confirmation_valid(text, pending.risk_level):
        original_command = pending.command
        del pending_confirmations[user_id]
        logger.info(
            "User confirmed dangerous command",
            extra={
                "user_id": user_id,
                "risk_level": pending.risk_level.value,
                "command_length": len(original_command),
            },
        )
        await message.answer("Confirmed. Executing command...")
        await execute_and_respond(message, original_command, bridge)
        return True

    # Invalid response - remind user
    if pending.risk_level == RiskLevel.CRITICAL:
        await message.answer(
            f"Invalid confirmation. Please send exactly:\n"
            f"`{socratic_gate.CRITICAL_CONFIRMATION_PHRASE}`\n\n"
            f"Or `NO` to cancel."
        )
    else:
        await message.answer("Invalid response. Send `YES` to confirm or `NO` to cancel.")

    return True


class JarvisBot:
    """JARVIS MK1 Lite Telegram Bot.

    This class encapsulates the bot setup and handlers,
    providing a clean interface for starting and stopping the bot.
    """

    def __init__(self, settings: Settings) -> None:
        """Initialize the bot.

        Args:
            settings: Application settings.
        """
        self.settings = settings
        self.bot = Bot(
            token=settings.telegram_bot_token.get_secret_value(),
            default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN),
        )
        self.dp = Dispatcher()
        self.bridge: ClaudeBridge = claude_bridge

        # Register middleware
        self._setup_middleware()

        # Register handlers
        self._setup_handlers()

        # Register lifecycle hooks
        async def startup_hook() -> None:
            # Set bot commands for dropdown menu
            commands = [
                # Main commands
                BotCommand(command="start", description="Show welcome message"),
                BotCommand(command="help", description="Detailed help and examples"),
                BotCommand(command="status", description="System and session status"),
                # Session management
                BotCommand(command="sessions", description="List and manage sessions"),
                BotCommand(command="new", description="Create new session"),
                BotCommand(command="switch", description="Switch active session"),
                BotCommand(command="kill", description="Delete a session"),
                # Model selection
                BotCommand(command="model", description="Change Claude model (opus/sonnet/haiku)"),
                # Advanced features
                BotCommand(command="wide_context", description="Batch multiple messages"),
                BotCommand(command="verbose", description="Toggle real-time action logs"),
                BotCommand(command="metrics", description="View usage statistics"),
            ]
            await self.bot.set_my_commands(commands)
            logger.info("Bot commands registered")

            await on_startup(self.bridge, self.settings)

        self.dp.startup.register(startup_hook)
        self.dp.shutdown.register(on_shutdown)

    def _setup_middleware(self) -> None:
        """Set up message middleware for whitelist filtering."""
        settings = self.settings

        @self.dp.message.middleware()  # type: ignore[misc,call-arg,arg-type]
        async def whitelist_middleware(
            handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
            event: TelegramObject,
            data: dict[str, Any],
        ) -> Any:
            """Middleware to filter unauthorized users."""
            # Type narrowing for Message type
            if not isinstance(event, types.Message):
                return await handler(event, data)

            if event.from_user is None:
                logger.warning("Message without user info")
                return None

            if event.from_user.id not in settings.allowed_user_ids:
                logger.warning(
                    "Unauthorized access attempt",
                    extra={"user_id": event.from_user.id},
                )
                return None  # Silently ignore unauthorized users

            return await handler(event, data)

    def _setup_handlers(self) -> None:
        """Set up command and message handlers."""

        @self.dp.message(CommandStart())
        async def cmd_start(message: types.Message) -> Any:
            """Handle /start command.

            Sends a welcome message with bot description and available commands.
            """
            if message.from_user is None:
                return None

            user_id = message.from_user.id
            logger.info("Start command received", extra={"user_id": user_id})
            metrics.record_command("start", user_id)

            welcome_text = f"""
*Welcome to {self.settings.app_name}!*

I'm your AI assistant powered by Claude Code.
Version: `{self.settings.app_version}`

*Available Commands:*
/start - Show this welcome message
/help - Detailed help and usage examples
/status - Check system status
/sessions - Manage multiple sessions
/new - Create a new session
/switch - Switch between sessions
/metrics - View application metrics

Simply send me any message and I'll forward it to Claude for processing.
            """.strip()

            return await message.answer(welcome_text)

        @self.dp.message(Command("help"))
        async def cmd_help(message: types.Message) -> Any:
            """Handle /help command.

            Shows detailed help with examples and security notice.
            """
            if message.from_user is None:
                return None

            user_id = message.from_user.id
            logger.info("Help command received", extra={"user_id": user_id})
            metrics.record_command("help", user_id)

            help_text = f"""
*JARVIS MK1 Lite Help*

*Commands:*
- `/start` - Show welcome message
- `/help` - Show this help message
- `/status` - Check Claude CLI status and session info
- `/metrics` - View application metrics

*Session Management:*
- `/sessions` - List all sessions with inline buttons
- `/new [name]` - Create new session (default: auto-named)
- `/switch <name>` - Switch to existing session
- `/kill <name>` - Delete a session

*Advanced:*
- `/wide_context` - Batch messages/files before sending
- `/verbose` - Toggle real-time action logging

*Multi-Session Examples:*
- `/new api` - Create session named "api"
- `/switch api` - Switch to "api" session
- `/kill api` - Delete "api" session

*Usage Examples:*
- `List files in current directory`
- `Create a Python script`
- `Explain this code`
- `Fix the bug in main.py`

*File Download:*
- `Download config.py` - Get a single file
- `Send me all .py files from src` - Files by pattern
- `Export the logs folder` - Get all files from directory

*Security Features:*
- Whitelist-based access control
- Socratic Gate for dangerous commands
- Rate limiting to prevent abuse

*Limits:*
- Max {self.settings.max_sessions_per_user} sessions per user
- Session expires after {self.settings.session_expiry_seconds // 60} min inactivity
- Workspace: `{self.settings.workspace_dir}`
            """.strip()

            return await message.answer(help_text)

        @self.dp.message(Command("status"))
        async def cmd_status(message: types.Message) -> Any:
            """Handle /status command.

            Shows Claude CLI health, current model, and workspace info.
            """
            if message.from_user is None:
                return None

            user_id = message.from_user.id
            logger.info("Status command received", extra={"user_id": user_id})
            metrics.record_command("status", user_id)

            # Check Claude health
            is_healthy = await self.bridge.check_health()
            status_emoji = "+" if is_healthy else "-"
            status_text = "Healthy" if is_healthy else "Unhealthy"

            # Get session info (multi-session)
            active_name = self.bridge.get_active_session_name(user_id)
            sessions = self.bridge.list_sessions(user_id)
            session_count = len(sessions)

            if session_count > 0:
                session_info = f"`{active_name}` ({session_count} total)"
            else:
                session_info = "No active session"

            # Get current model for active session
            current_model = self.bridge.get_session_model(user_id)
            model_display = {
                "opus": "Opus 4.5",
                "sonnet": "Sonnet 4.5",
                "haiku": "Haiku 4.5",
            }
            model_name = model_display.get(current_model, current_model)

            # Check for pending confirmation
            pending_info = ""
            if user_id in pending_confirmations:
                pending = pending_confirmations[user_id]
                if not is_confirmation_expired(pending):
                    pending_info = f"\n*Pending:* {pending.risk_level.value.upper()} confirmation"

            # Metrics summary
            metrics_summary = f"""
*Uptime:* `{metrics.format_uptime()}`
*Requests:* `{metrics.total_requests}` (Errors: `{metrics.total_errors}`)"""

            status_msg = f"""
*System Status*

*Claude CLI:* {status_emoji} {status_text}
*Model:* `{model_name}`
*Workspace:* `{self.settings.workspace_dir}`
*Session:* {session_info}{pending_info}
{metrics_summary}

Use `/sessions` to manage sessions, `/model` to change model, `/metrics` for detailed metrics.
            """.strip()

            return await message.answer(status_msg)

        @self.dp.message(Command("new"))
        async def cmd_new(message: types.Message) -> Any:
            """Handle /new command.

            Creates a new named session or clears current one.
            Usage: /new [session_name]
            """
            if message.from_user is None:
                return None

            user_id = message.from_user.id
            logger.info("New session command received", extra={"user_id": user_id})
            metrics.record_command("new", user_id)

            # Parse session name from command arguments
            args = message.text.split(maxsplit=1) if message.text else []
            session_name = args[1].strip() if len(args) > 1 else None

            # Clear any pending confirmations
            if user_id in pending_confirmations:
                del pending_confirmations[user_id]

            # Clear wide context mode
            if user_id in _pending_contexts:
                ctx = _pending_contexts.pop(user_id)
                if ctx.timer:
                    ctx.timer.cancel()

            # Reset user's rate limit bucket
            rate_limiter.reset_user(user_id)

            try:
                created_name = self.bridge.create_session(user_id, session_name, set_active=True)
                return await message.answer(
                    f"*New session created:* `{created_name}`\n\n"
                    f"This is now your active session. Start chatting!"
                )
            except InvalidSessionNameError as e:
                return await message.answer(
                    f"Invalid session name: {e.reason}\n"
                    f"Use only letters, numbers, underscore and hyphen."
                )
            except SessionAlreadyExistsError:
                # Session exists, switch to it and clear
                self.bridge.switch_session(user_id, session_name)  # type: ignore
                self.bridge.clear_session(user_id)
                return await message.answer(
                    f"*Session `{session_name}` already exists.*\n"
                    f"Switched to it and cleared context. Ready for new conversation!"
                )
            except SessionLimitExceededError as e:
                return await message.answer(
                    f"Session limit reached ({e.max_sessions} max).\n"
                    f"Use `/kill <name>` to delete old sessions first."
                )

        @self.dp.message(Command("sessions"))
        async def cmd_sessions(message: types.Message) -> Any:
            """Handle /sessions command.

            Shows list of all sessions with inline keyboard for management.
            """
            if message.from_user is None:
                return None

            user_id = message.from_user.id
            logger.info("Sessions command received", extra={"user_id": user_id})
            metrics.record_command("sessions", user_id)

            sessions = self.bridge.list_sessions(user_id)

            if not sessions:
                return await message.answer(
                    "*No active sessions*\n\n"
                    "Send a message to start your first session,\n"
                    "or use `/new [name]` to create a named session."
                )

            # Build session list text
            active_name = self.bridge.get_active_session_name(user_id)
            session_lines = []
            for s in sessions:
                marker = " ✓" if s.is_active else ""
                age = _format_session_age(s.last_used)
                session_lines.append(f"- `{s.name}`{marker} ({age})")

            session_text = "\n".join(session_lines)

            # Build inline keyboard
            buttons: list[list[InlineKeyboardButton]] = []
            row: list[InlineKeyboardButton] = []

            for s in sessions[:6]:  # Max 6 sessions in buttons
                indicator = " ✓" if s.is_active else ""
                row.append(
                    InlineKeyboardButton(
                        text=f"{s.name}{indicator}",
                        callback_data=f"session_switch:{user_id}:{s.name}",
                    )
                )
                if len(row) == 3:
                    buttons.append(row)
                    row = []

            if row:
                buttons.append(row)

            # Add action buttons
            buttons.append(
                [
                    InlineKeyboardButton(
                        text="+ New",
                        callback_data=f"session_new:{user_id}",
                    ),
                    InlineKeyboardButton(
                        text="🗑️ Kill current",
                        callback_data=f"session_kill:{user_id}:{active_name}",
                    ),
                ]
            )

            keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

            return await message.answer(
                f"*Your Sessions* ({len(sessions)}/{self.settings.max_sessions_per_user})\n\n"
                f"{session_text}\n\n"
                f"*Active:* `{active_name}`\n"
                f"Click to switch or manage:",
                reply_markup=keyboard,
            )

        @self.dp.message(Command("switch"))
        async def cmd_switch(message: types.Message) -> Any:
            """Handle /switch command.

            Switches to an existing session.
            Usage: /switch <session_name>
            """
            if message.from_user is None:
                return None

            user_id = message.from_user.id
            logger.info("Switch session command received", extra={"user_id": user_id})
            metrics.record_command("switch", user_id)

            # Parse session name from command arguments
            args = message.text.split(maxsplit=1) if message.text else []

            if len(args) < 2:
                sessions = self.bridge.list_sessions(user_id)
                if not sessions:
                    return await message.answer(
                        "No sessions available. Use `/new [name]` to create one."
                    )
                session_names = ", ".join(f"`{s.name}`" for s in sessions[:5])
                return await message.answer(
                    f"*Usage:* `/switch <session_name>`\n\n"
                    f"Available sessions: {session_names}\n\n"
                    f"Or use `/sessions` for interactive selection."
                )

            session_name = args[1].strip()

            try:
                self.bridge.switch_session(user_id, session_name)
                return await message.answer(f"*Switched to session:* `{session_name}`")
            except SessionNotFoundError:
                sessions = self.bridge.list_sessions(user_id)
                session_names = ", ".join(f"`{s.name}`" for s in sessions[:5])
                hint = f"\n\nAvailable: {session_names}" if sessions else ""
                return await message.answer(
                    f"Session `{session_name}` not found.{hint}\n\n"
                    f"Use `/new {session_name}` to create it."
                )

        @self.dp.message(Command("kill"))
        async def cmd_kill(message: types.Message) -> Any:
            """Handle /kill command.

            Deletes a session.
            Usage: /kill <session_name>
            """
            if message.from_user is None:
                return None

            user_id = message.from_user.id
            logger.info("Kill session command received", extra={"user_id": user_id})
            metrics.record_command("kill", user_id)

            # Parse session name from command arguments
            args = message.text.split(maxsplit=1) if message.text else []

            if len(args) < 2:
                sessions = self.bridge.list_sessions(user_id)
                if not sessions:
                    return await message.answer("No sessions to delete.")
                session_names = ", ".join(f"`{s.name}`" for s in sessions[:5])
                return await message.answer(
                    f"*Usage:* `/kill <session_name>`\n\n" f"Available sessions: {session_names}"
                )

            session_name = args[1].strip()

            try:
                self.bridge.delete_session(user_id, session_name)
                new_active = self.bridge.get_active_session_name(user_id)
                return await message.answer(
                    f"*Session deleted:* `{session_name}`\n\n"
                    f"Active session is now: `{new_active}`"
                )
            except SessionNotFoundError:
                return await message.answer(f"Session `{session_name}` not found.")

        # Session management callback handlers
        @self.dp.callback_query(F.data.startswith("session_switch:"))
        async def handle_session_switch(callback: CallbackQuery) -> Any:
            """Handle session switch from inline keyboard."""
            if callback.from_user is None or callback.message is None:
                return None

            if not hasattr(callback.message, "edit_text"):
                return None

            try:
                parts = callback.data.split(":")  # type: ignore
                callback_user_id = int(parts[1])
                session_name = parts[2]
            except (ValueError, IndexError):
                await callback.answer("Invalid callback data", show_alert=True)
                return None

            if callback.from_user.id != callback_user_id:
                await callback.answer("This is not your session list!", show_alert=True)
                return None

            try:
                self.bridge.switch_session(callback_user_id, session_name)
                await callback.answer(f"Switched to {session_name}")

                # Refresh the session list
                await cmd_sessions(callback.message)  # type: ignore
            except SessionNotFoundError:
                await callback.answer(f"Session {session_name} not found", show_alert=True)

            return None

        @self.dp.callback_query(F.data.startswith("session_new:"))
        async def handle_session_new(callback: CallbackQuery) -> Any:
            """Handle new session creation from inline keyboard."""
            if callback.from_user is None or callback.message is None:
                return None

            if not hasattr(callback.message, "edit_text"):
                return None

            try:
                parts = callback.data.split(":")  # type: ignore
                callback_user_id = int(parts[1])
            except (ValueError, IndexError):
                await callback.answer("Invalid callback data", show_alert=True)
                return None

            if callback.from_user.id != callback_user_id:
                await callback.answer("This is not your session list!", show_alert=True)
                return None

            try:
                new_name = self.bridge.create_session(callback_user_id, None, set_active=True)
                await callback.answer(f"Created session: {new_name}")

                # Update the message
                await callback.message.edit_text(  # type: ignore
                    f"*New session created:* `{new_name}`\n\n"
                    f"Use `/sessions` to view all sessions."
                )
            except SessionLimitExceededError:
                await callback.answer("Session limit reached. Delete some first.", show_alert=True)

            return None

        @self.dp.callback_query(F.data.startswith("session_kill:"))
        async def handle_session_kill(callback: CallbackQuery) -> Any:
            """Handle session deletion from inline keyboard."""
            if callback.from_user is None or callback.message is None:
                return None

            if not hasattr(callback.message, "edit_text"):
                return None

            try:
                parts = callback.data.split(":")  # type: ignore
                callback_user_id = int(parts[1])
                session_name = parts[2]
            except (ValueError, IndexError):
                await callback.answer("Invalid callback data", show_alert=True)
                return None

            if callback.from_user.id != callback_user_id:
                await callback.answer("This is not your session list!", show_alert=True)
                return None

            try:
                self.bridge.delete_session(callback_user_id, session_name)
                new_active = self.bridge.get_active_session_name(callback_user_id)
                await callback.answer(f"Deleted {session_name}")

                # Update the message
                await callback.message.edit_text(  # type: ignore
                    f"*Session deleted:* `{session_name}`\n\n"
                    f"Active session: `{new_active}`\n"
                    f"Use `/sessions` to view remaining sessions."
                )
            except SessionNotFoundError:
                await callback.answer(f"Session {session_name} not found", show_alert=True)

            return None

        @self.dp.message(Command("metrics"))
        async def cmd_metrics(message: types.Message) -> Any:
            """Handle /metrics command.

            Shows detailed application metrics including session statistics.
            """
            if message.from_user is None:
                return None

            user_id = message.from_user.id
            logger.info("Metrics command received", extra={"user_id": user_id})
            metrics.record_command("metrics", user_id)

            # Get session statistics from bridge
            session_stats = self.bridge.get_session_stats()

            return await message.answer(format_metrics_message(session_stats))

        @self.dp.message(Command("verbose"))
        async def cmd_verbose(message: types.Message) -> Any:
            """Handle /verbose command.

            Toggles verbose mode for real-time Claude Code action logging.
            """
            if message.from_user is None:
                return None

            user_id = message.from_user.id
            logger.info("Verbose command received", extra={"user_id": user_id})
            metrics.record_command("verbose", user_id)

            # Toggle verbose mode
            is_enabled = toggle_verbose(user_id)

            if is_enabled:
                return await message.answer(
                    "*Verbose mode enabled*\n\n"
                    "You will now see Claude Code actions in real-time.\n"
                    "Send `/verbose` again to disable."
                )
            return await message.answer(
                "*Verbose mode disabled*\n\n" "You will only see final responses."
            )

        @self.dp.message(Command("model"))
        async def cmd_model(message: types.Message) -> Any:
            """Handle /model command.

            Switches Claude model for the active session.
            Usage: /model [opus|sonnet|haiku]
            """
            if message.from_user is None:
                return None

            user_id = message.from_user.id
            logger.info("Model command received", extra={"user_id": user_id})
            metrics.record_command("model", user_id)

            # Parse model argument
            args = message.text.split(maxsplit=1) if message.text else []

            # Model mappings - use aliases that Claude CLI accepts
            model_map = {
                "opus": "opus",      # Claude CLI alias
                "sonnet": "sonnet",  # Claude CLI alias
                "haiku": "haiku",    # Claude CLI alias
            }

            # Short names for display
            model_display = {
                "opus": "Opus 4.5",
                "sonnet": "Sonnet 4.5",
                "haiku": "Haiku 4.5",
            }

            if len(args) < 2:
                # Show current model and available options
                try:
                    # Ensure user has a session
                    active_session = self.bridge.get_active_session_name(user_id)
                    if not self.bridge.has_session(user_id, active_session):
                        self.bridge.create_session(user_id, active_session, set_active=True)

                    current_model = self.bridge.get_session_model(user_id)
                    current_display = model_display.get(current_model, current_model)

                    return await message.answer(
                        f"*Current model:* `{current_display}`\n\n"
                        "*Available models:*\n"
                        "• `/model opus` - Claude Opus 4.5 (most capable)\n"
                        "• `/model sonnet` - Claude Sonnet 4.5 (default, balanced)\n"
                        "• `/model haiku` - Claude Haiku 4.5 (fastest)\n\n"
                        "Model applies to the active session only."
                    )
                except Exception as e:
                    logger.error(f"Failed to get model: {e}", extra={"user_id": user_id})
                    return await message.answer(f"Failed to get current model: {e}")

            model_arg = args[1].strip().lower()

            if model_arg not in model_map:
                return await message.answer(
                    f"Unknown model: `{model_arg}`\n\n"
                    "Available: `opus`, `sonnet`, `haiku`"
                )

            # Set model for active session
            new_model = model_map[model_arg]
            try:
                # Ensure user has a session (create default if needed)
                active_session = self.bridge.get_active_session_name(user_id)
                if not self.bridge.has_session(user_id, active_session):
                    # Create default session
                    self.bridge.create_session(user_id, active_session, set_active=True)
                    logger.info(
                        "Auto-created default session for model change",
                        extra={"user_id": user_id, "session": active_session},
                    )

                self.bridge.set_session_model(user_id, new_model)
                display_name = model_display[new_model]

                return await message.answer(
                    f"*Model changed to:* `{display_name}`\n\n"
                    f"Session: `{active_session}`\n\n"
                    "Next message will use the new model."
                )
            except Exception as e:
                logger.error(f"Failed to set model: {e}", extra={"user_id": user_id})
                return await message.answer(f"Failed to set model: {e}")

        @self.dp.message(Command("wide_context"))
        async def cmd_wide_context(message: types.Message) -> Any:
            """Handle /wide_context command.

            Starts wide context mode for accumulating multiple messages and files.
            User must click Accept button to send accumulated context to Claude.
            """
            if message.from_user is None:
                return None

            user_id = message.from_user.id
            logger.info("Wide context command received", extra={"user_id": user_id})
            metrics.record_command("wide_context", user_id)

            # Cancel any existing timer
            if user_id in _pending_contexts:
                ctx = _pending_contexts[user_id]
                if ctx.timer:
                    ctx.timer.cancel()

            # Create new wide context
            _pending_contexts[user_id] = PendingContext(
                messages=[],
                files=[],
                timer=None,
                wide_mode=True,
                created_at=time.time(),
            )

            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="Accept & Send",
                            callback_data=f"wide_accept:{user_id}",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="Cancel",
                            callback_data=f"wide_cancel:{user_id}",
                        )
                    ],
                ]
            )

            status_msg = await message.answer(
                "*Wide Context Mode Active*\n\n"
                "Send multiple messages and files.\n"
                "I will accumulate them and send to Claude when you click Accept.\n\n"
                "Messages: 0\n"
                "Files: 0\n\n"
                "Click Accept when ready, or Cancel to abort.",
                reply_markup=keyboard,
            )

            # Store the status message for later editing
            _pending_contexts[user_id].status_message = status_msg
            return None

        @self.dp.callback_query(F.data.startswith("wide_accept:"))
        async def handle_wide_accept(callback: CallbackQuery) -> Any:
            """Handle Accept button click for wide context."""
            if callback.from_user is None or callback.message is None:
                return None

            # Check if message is accessible (has edit_text)
            if not hasattr(callback.message, "edit_text"):
                return None

            message = callback.message
            user_id = callback.from_user.id
            try:
                callback_user_id = int(callback.data.split(":")[1])  # type: ignore[union-attr]
            except (ValueError, IndexError, AttributeError):
                await callback.answer("Invalid callback data", show_alert=True)
                return None

            # Security check - only the user who started can accept
            if user_id != callback_user_id:
                await callback.answer("This is not your context!", show_alert=True)
                return None

            ctx = _pending_contexts.pop(user_id, None)
            if ctx is None or not ctx.wide_mode:
                await callback.answer("No active wide context found.", show_alert=True)
                return None

            if not ctx.messages and not ctx.files:
                await callback.answer(
                    "Context is empty. Send some messages first.", show_alert=True
                )
                # Put the context back
                _pending_contexts[user_id] = ctx
                return None

            await callback.answer("Processing...")

            # Combine and send to Claude
            combined = _combine_context(ctx)

            # Show what we're sending
            preview = combined[:200] + "..." if len(combined) > 200 else combined
            await message.edit_text(  # type: ignore[union-attr]
                f"*Sending to Claude*\n\n"
                f"Messages: {len(ctx.messages)}\n"
                f"Files: {len(ctx.files)}\n\n"
                f"Preview:\n```\n{preview}\n```"
            )

            # Send to Claude - message is guaranteed to be Message due to hasattr check
            await execute_and_respond(message, combined, self.bridge)  # type: ignore[arg-type]
            return None

        @self.dp.callback_query(F.data.startswith("wide_cancel:"))
        async def handle_wide_cancel(callback: CallbackQuery) -> Any:
            """Handle Cancel button click for wide context."""
            if callback.from_user is None or callback.message is None:
                return None

            # Check if message is accessible (has edit_text)
            if not hasattr(callback.message, "edit_text"):
                return None

            message = callback.message
            user_id = callback.from_user.id
            try:
                callback_user_id = int(callback.data.split(":")[1])  # type: ignore[union-attr]
            except (ValueError, IndexError, AttributeError):
                await callback.answer("Invalid callback data", show_alert=True)
                return None

            if user_id != callback_user_id:
                await callback.answer("This is not your context!", show_alert=True)
                return None

            ctx = _pending_contexts.pop(user_id, None)
            if ctx and ctx.timer:
                ctx.timer.cancel()

            await callback.answer("Cancelled")
            await message.edit_text("Wide context mode cancelled.")  # type: ignore[union-attr]
            return None

        @self.dp.message(F.text)
        async def handle_message(message: types.Message) -> Any:
            """Handle regular text messages.

            Processes user messages through the Socratic Gate safety check
            and forwards them to Claude Bridge. Includes rate limiting and metrics.
            """
            if message.from_user is None or message.text is None:
                return None

            user_id = message.from_user.id
            text = message.text.strip()
            start_time = time.time()

            logger.info(
                "Message received",
                extra={"user_id": user_id, "message_length": len(text)},
            )

            # Track request metrics
            metrics.record_request(user_id, is_command=False)

            # Check rate limit (if enabled)
            if self.settings.rate_limit_enabled and not rate_limiter.is_allowed(user_id):
                retry_after = rate_limiter.get_retry_after(user_id)
                logger.warning(
                    "Rate limit exceeded",
                    extra={"user_id": user_id, "retry_after": retry_after},
                )
                await message.answer(f"Rate limit exceeded. Please wait {retry_after:.0f} seconds.")
                return None

            # Check for confirmation response first
            was_confirmation = await handle_confirmation(message, text, self.bridge)
            if was_confirmation:
                latency = time.time() - start_time
                metrics.record_latency(latency)
                return None

            # Check if user is in wide context mode
            if user_id in _pending_contexts:
                ctx = _pending_contexts[user_id]
                if ctx.wide_mode:
                    # Check limits before accumulating
                    if len(ctx.messages) >= MAX_WIDE_CONTEXT_MESSAGES:
                        await message.reply(
                            f"Wide context limit reached ({MAX_WIDE_CONTEXT_MESSAGES} messages). "
                            "Click 'Accept & Send' or 'Cancel'."
                        )
                        return None

                    # Accumulate message in wide context mode
                    ctx.messages.append(text)
                    logger.info(
                        "Message accumulated in wide context",
                        extra={
                            "user_id": user_id,
                            "messages": len(ctx.messages),
                            "files": len(ctx.files),
                        },
                    )
                    # Update status message
                    if ctx.status_message:
                        keyboard = InlineKeyboardMarkup(
                            inline_keyboard=[
                                [
                                    InlineKeyboardButton(
                                        text="Accept & Send",
                                        callback_data=f"wide_accept:{user_id}",
                                    )
                                ],
                                [
                                    InlineKeyboardButton(
                                        text="Cancel",
                                        callback_data=f"wide_cancel:{user_id}",
                                    )
                                ],
                            ]
                        )
                        with contextlib.suppress(Exception):
                            await ctx.status_message.edit_text(
                                "*Wide Context Mode Active*\n\n"
                                "Send multiple messages and files.\n"
                                "Will send to Claude when you click Accept.\n\n"
                                f"Messages: {len(ctx.messages)}\n"
                                f"Files: {len(ctx.files)}\n\n"
                                "Click Accept when ready, or Cancel to abort.",
                                reply_markup=keyboard,
                            )
                    latency = time.time() - start_time
                    metrics.record_latency(latency)
                    return None
                else:
                    # Non-wide mode: accumulate and reset timer
                    ctx.messages.append(text)
                    if ctx.timer:
                        ctx.timer.cancel()
                    # Start new timer
                    ctx.timer = asyncio.create_task(
                        _delayed_send(
                            user_id,
                            self.settings.message_accumulation_delay,
                            message,
                            self.bridge,
                        )
                    )
                    logger.debug(
                        "Message accumulated, timer reset",
                        extra={"user_id": user_id, "messages": len(ctx.messages)},
                    )
                    latency = time.time() - start_time
                    metrics.record_latency(latency)
                    return None

            # Check for dangerous patterns (Socratic Gate)
            safety_check = socratic_gate.check(text)
            metrics.record_safety_check(
                is_dangerous=safety_check.risk_level == RiskLevel.DANGEROUS,
                is_critical=safety_check.risk_level == RiskLevel.CRITICAL,
            )

            if safety_check.risk_level == RiskLevel.CRITICAL:
                # Critical - requires exact phrase confirmation
                logger.warning(
                    "Critical command detected",
                    extra={
                        "user_id": user_id,
                        "pattern": safety_check.matched_pattern,
                    },
                )

                # Store pending confirmation
                pending_confirmations[user_id] = PendingConfirmation(
                    command=text,
                    risk_level=RiskLevel.CRITICAL,
                    timestamp=time.time(),
                )

                warning_msg = f"""
*CRITICAL OPERATION*

Detected: {safety_check.matched_pattern}

This operation may lead to *irreversible data loss* or *system failure*.

To confirm, send exactly:
`{socratic_gate.CRITICAL_CONFIRMATION_PHRASE}`

Or send `NO` to cancel.
                """.strip()

                latency = time.time() - start_time
                metrics.record_latency(latency)
                return await message.answer(warning_msg)

            if safety_check.risk_level == RiskLevel.DANGEROUS:
                # Dangerous - requires YES/NO confirmation
                logger.warning(
                    "Dangerous command detected",
                    extra={
                        "user_id": user_id,
                        "pattern": safety_check.matched_pattern,
                    },
                )

                # Store pending confirmation
                pending_confirmations[user_id] = PendingConfirmation(
                    command=text,
                    risk_level=RiskLevel.DANGEROUS,
                    timestamp=time.time(),
                )

                warning_msg = f"""
*DANGEROUS OPERATION*

Detected: {safety_check.matched_pattern}

Are you sure you want to continue?

Send `YES` to confirm or `NO` to cancel.
                """.strip()

                latency = time.time() - start_time
                metrics.record_latency(latency)
                return await message.answer(warning_msg)

            if safety_check.risk_level == RiskLevel.MODERATE:
                # Moderate - show info and execute
                logger.info(
                    "Moderate risk command detected",
                    extra={
                        "user_id": user_id,
                        "pattern": safety_check.matched_pattern,
                    },
                )

                await message.answer(f"INFO: {safety_check.matched_pattern} - executing...")

            # Forward to Claude Bridge
            await execute_and_respond(message, text, self.bridge)

            latency = time.time() - start_time
            metrics.record_latency(latency)
            return None

        @self.dp.message(F.voice)
        async def handle_voice(message: types.Message) -> Any:
            """Handle voice messages.

            Transcribes voice messages using Telegram Premium API via Telethon
            and forwards the transcribed text to Claude Bridge.
            """
            if message.from_user is None or message.voice is None:
                return None

            user_id = message.from_user.id
            start_time = time.time()

            logger.info(
                "Voice message received",
                extra={
                    "user_id": user_id,
                    "duration": message.voice.duration,
                    "file_size": message.voice.file_size,
                },
            )

            # Track request metrics
            metrics.record_request(user_id, is_command=False)

            # Check rate limit (if enabled)
            if self.settings.rate_limit_enabled and not rate_limiter.is_allowed(user_id):
                retry_after = rate_limiter.get_retry_after(user_id)
                logger.warning(
                    "Rate limit exceeded",
                    extra={"user_id": user_id, "retry_after": retry_after},
                )
                await message.answer(f"Rate limit exceeded. Please wait {retry_after:.0f} seconds.")
                return None

            # Check if voice transcription is enabled
            if not self.settings.voice_transcription_enabled:
                await message.answer(
                    "Voice transcription is not enabled.\n"
                    "Please send text messages or ask the administrator to enable voice support."
                )
                latency = time.time() - start_time
                metrics.record_latency(latency)
                return None

            # Send typing action
            await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")  # type: ignore[union-attr]

            # Transcribe voice message
            transcribed_text = await self._transcribe_voice_message(message)

            if transcribed_text is None:
                latency = time.time() - start_time
                metrics.record_latency(latency)
                return None

            # Show transcribed text to user
            await message.answer(f"🎤 Transcribed: _{transcribed_text}_")

            # Forward transcribed text to Claude Bridge
            await execute_and_respond(message, transcribed_text, self.bridge)

            latency = time.time() - start_time
            metrics.record_latency(latency)
            return None

        @self.dp.message(F.video_note)
        async def handle_video_note(message: types.Message) -> Any:
            """Handle video note messages (circles).

            Transcribes audio from video notes using Telegram Premium API
            and forwards the transcribed text to Claude Bridge.
            """
            if message.from_user is None or message.video_note is None:
                return None

            user_id = message.from_user.id
            start_time = time.time()

            logger.info(
                "Video note received",
                extra={
                    "user_id": user_id,
                    "duration": message.video_note.duration,
                    "file_size": message.video_note.file_size,
                },
            )

            # Track request metrics
            metrics.record_request(user_id, is_command=False)

            # Check rate limit (if enabled)
            if self.settings.rate_limit_enabled and not rate_limiter.is_allowed(user_id):
                retry_after = rate_limiter.get_retry_after(user_id)
                logger.warning(
                    "Rate limit exceeded",
                    extra={"user_id": user_id, "retry_after": retry_after},
                )
                await message.answer(f"Rate limit exceeded. Please wait {retry_after:.0f} seconds.")
                return None

            # Check if voice transcription is enabled
            if not self.settings.voice_transcription_enabled:
                await message.answer(
                    "Voice transcription is not enabled.\n"
                    "Please send text messages or ask the administrator to enable voice support."
                )
                latency = time.time() - start_time
                metrics.record_latency(latency)
                return None

            # Send typing action
            await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")  # type: ignore[union-attr]

            # Transcribe video note
            transcribed_text = await self._transcribe_voice_message(message)

            if transcribed_text is None:
                latency = time.time() - start_time
                metrics.record_latency(latency)
                return None

            # Show transcribed text to user
            await message.answer(f"🎥 Transcribed: _{transcribed_text}_")

            # Forward transcribed text to Claude Bridge
            await execute_and_respond(message, transcribed_text, self.bridge)

            latency = time.time() - start_time
            metrics.record_latency(latency)
            return None

        @self.dp.message(F.document)
        async def handle_document(message: types.Message) -> Any:
            """Handle document messages.

            Extracts text content from supported file formats and forwards
            to Claude Bridge for processing.

            Supported formats:
            - Text files: .txt, .md, .py, .js, .json, .yaml, .xml, .html, etc.
            - PDF files: .pdf (requires PyMuPDF)
            """
            if message.from_user is None or message.document is None:
                return None

            user_id = message.from_user.id
            start_time = time.time()

            filename = message.document.file_name or "unknown"

            logger.info(
                "Document received",
                extra={
                    "user_id": user_id,
                    "doc_filename": filename,
                    "file_size": message.document.file_size,
                    "mime_type": message.document.mime_type,
                },
            )

            # Track request metrics
            metrics.record_request(user_id, is_command=False)

            # Check rate limit (if enabled)
            if self.settings.rate_limit_enabled and not rate_limiter.is_allowed(user_id):
                retry_after = rate_limiter.get_retry_after(user_id)
                logger.warning(
                    "Rate limit exceeded",
                    extra={"user_id": user_id, "retry_after": retry_after},
                )
                await message.answer(f"Rate limit exceeded. Please wait {retry_after:.0f} seconds.")
                return None

            # Check if file handling is enabled
            if not self.settings.file_handling_enabled:
                await message.answer(
                    "File handling is not enabled.\n" "Please send text messages instead."
                )
                latency = time.time() - start_time
                metrics.record_latency(latency)
                return None

            # Check file size
            file_size_bytes = message.document.file_size or 0
            file_size_mb = file_size_bytes / (1024 * 1024)
            if file_size_mb > self.settings.max_file_size_mb:
                await message.answer(
                    f"File too large ({file_size_mb:.1f}MB).\n"
                    f"Maximum size: {self.settings.max_file_size_mb}MB"
                )
                latency = time.time() - start_time
                metrics.record_latency(latency)
                return None

            # Create file processor
            processor = FileProcessor(max_chars=self.settings.max_extracted_text_chars)

            # Check if format is supported
            if not processor.is_supported(filename):
                from pathlib import Path

                ext = Path(filename).suffix.lower()
                await message.answer(
                    f"Unsupported file format: {ext}\n"
                    "Supported formats: .txt, .md, .py, .js, .json, .pdf, etc."
                )
                latency = time.time() - start_time
                metrics.record_latency(latency)
                return None

            # Send typing action
            await message.bot.send_chat_action(  # type: ignore[union-attr]
                chat_id=message.chat.id, action="typing"
            )

            # Download file
            try:
                file = await message.bot.get_file(  # type: ignore[union-attr]
                    message.document.file_id
                )

                from io import BytesIO

                buffer = BytesIO()
                if file.file_path is None:
                    raise ValueError("File path not available")
                await message.bot.download_file(file.file_path, buffer)  # type: ignore[union-attr]
                file_data = buffer.getvalue()

                logger.debug(
                    f"Downloaded file: {len(file_data)} bytes",
                    extra={"doc_filename": filename},
                )

            except Exception as e:
                logger.error(f"Failed to download file: {e}", extra={"user_id": user_id})
                metrics.record_error(user_id)
                await message.answer("Failed to download file. Please try again.")
                latency = time.time() - start_time
                metrics.record_latency(latency)
                return None

            # Extract text content
            try:
                extracted_text = processor.extract_text(file_data, filename)
                logger.info(
                    "Text extracted from file",
                    extra={
                        "user_id": user_id,
                        "doc_filename": filename,
                        "extracted_chars": len(extracted_text),
                    },
                )

            except UnsupportedFileTypeError:
                await message.answer(f"Unsupported file format: {filename}")
                latency = time.time() - start_time
                metrics.record_latency(latency)
                return None

            except FileProcessingError as e:
                logger.error(f"File processing error: {e}", extra={"user_id": user_id})
                metrics.record_error(user_id)
                await message.answer(f"Failed to process file: {e}")
                latency = time.time() - start_time
                metrics.record_latency(latency)
                return None

            # Format message for Claude
            caption = message.caption or "Analyze this file"
            claude_message = (
                f"{caption}\n\n"
                f"=== File: {filename} ===\n"
                f"{extracted_text}\n"
                f"=== End of file ==="
            )

            # Check if user is in wide context mode
            if user_id in _pending_contexts:
                ctx = _pending_contexts[user_id]
                if ctx.wide_mode:
                    # Check limits before accumulating
                    if len(ctx.files) >= MAX_WIDE_CONTEXT_FILES:
                        await message.reply(
                            f"Wide context limit reached ({MAX_WIDE_CONTEXT_FILES} files). "
                            "Click 'Accept & Send' or 'Cancel'."
                        )
                        return None

                    # Accumulate file in wide context mode
                    ctx.files.append((filename, extracted_text))
                    logger.info(
                        "File accumulated in wide context",
                        extra={
                            "user_id": user_id,
                            "doc_filename": filename,
                            "messages": len(ctx.messages),
                            "files": len(ctx.files),
                        },
                    )
                    await message.answer(f"File `{filename}` added to context.")
                    # Update status message
                    if ctx.status_message:
                        keyboard = InlineKeyboardMarkup(
                            inline_keyboard=[
                                [
                                    InlineKeyboardButton(
                                        text="Accept & Send",
                                        callback_data=f"wide_accept:{user_id}",
                                    )
                                ],
                                [
                                    InlineKeyboardButton(
                                        text="Cancel",
                                        callback_data=f"wide_cancel:{user_id}",
                                    )
                                ],
                            ]
                        )
                        with contextlib.suppress(Exception):
                            await ctx.status_message.edit_text(
                                "*Wide Context Mode Active*\n\n"
                                "Send multiple messages and files.\n"
                                "Will send to Claude when you click Accept.\n\n"
                                f"Messages: {len(ctx.messages)}\n"
                                f"Files: {len(ctx.files)}\n\n"
                                "Click Accept when ready, or Cancel to abort.",
                                reply_markup=keyboard,
                            )
                    latency = time.time() - start_time
                    metrics.record_latency(latency)
                    return None

            # Show confirmation to user
            preview_length = min(100, len(extracted_text))
            preview = extracted_text[:preview_length]
            if len(extracted_text) > preview_length:
                preview += "..."

            await message.answer(
                f"Processing file: `{filename}`\n" f"Extracted: {len(extracted_text):,} chars"
            )

            # Forward to Claude Bridge (same flow as text messages)
            await execute_and_respond(message, claude_message, self.bridge)

            latency = time.time() - start_time
            metrics.record_latency(latency)
            return None

    async def _transcribe_voice_message(self, message: types.Message) -> str | None:
        """Transcribe a voice or video note message.

        Downloads the voice file via Bot API, uploads to Telethon's Saved Messages,
        transcribes using Premium API, and cleans up.

        Args:
            message: The Telegram message containing voice or video note.

        Returns:
            Transcribed text or None if transcription failed.
        """
        global _voice_transcriber

        user_id = message.from_user.id if message.from_user else 0

        # Check if transcriber is initialized (should be done at startup)
        if _voice_transcriber is None or not _voice_transcriber.is_started:
            logger.error("Voice transcriber not initialized. Check startup logs.")
            await message.answer(
                "Voice transcription is not ready.\n"
                "Please contact the administrator to check Telethon authorization."
            )
            return None

        try:
            # Download voice file via Bot API
            if message.voice:
                file = await message.bot.get_file(message.voice.file_id)  # type: ignore[union-attr]
            elif message.video_note:
                file = await message.bot.get_file(message.video_note.file_id)  # type: ignore[union-attr]
            else:
                logger.error("No voice or video_note in message")
                return None

            # Download file content
            from io import BytesIO

            buffer = BytesIO()
            await message.bot.download_file(file.file_path, buffer)  # type: ignore[union-attr, arg-type]
            voice_data = buffer.getvalue()
            logger.info(f"Downloaded voice file: {len(voice_data)} bytes")

            # Get duration from the original message
            duration = 0
            if message.voice:
                duration = message.voice.duration
            elif message.video_note:
                duration = message.video_note.duration

            # Transcribe using Telethon via Saved Messages
            result = await _voice_transcriber.transcribe_voice_file(
                voice_data=voice_data,
                duration=duration,
                timeout=30.0,
            )

            # Log detailed transcription result for debugging
            logger.info(
                "Voice transcription successful",
                extra={
                    "user_id": user_id,
                    "transcription_id": result.transcription_id,
                    "text_length": len(result.text),
                    "text_preview": result.text[:100] if result.text else "",
                    "pending": result.pending,
                    "trial_remains": result.trial_remains,
                    "voice_duration": duration,
                    "voice_bytes": len(voice_data),
                },
            )

            return result.text

        except PremiumRequiredError:
            logger.error("Telegram Premium required for transcription")
            metrics.record_error(user_id)
            await message.answer(
                "⚠️ Telegram Premium subscription required for voice transcription.\n"
                "Please contact the administrator."
            )
            return None

        except TranscriptionPendingError:
            logger.warning("Transcription timed out", extra={"user_id": user_id})
            metrics.record_error(user_id)
            await message.answer(
                "⏳ Voice transcription is taking too long.\n"
                "Please try again with a shorter message."
            )
            return None

        except TranscriptionError as e:
            logger.error(f"Transcription error: {e}", extra={"user_id": user_id})
            metrics.record_error(user_id)
            await message.answer(
                "❌ Failed to transcribe voice message.\n"  # noqa: E501
                "Please try again or send a text message."
            )
            return None

    async def start(self) -> None:
        """Start the bot polling."""
        logger.info(
            "Starting bot",
            extra={
                "app_name": self.settings.app_name,
                "app_version": self.settings.app_version,
            },
        )
        await self.dp.start_polling(self.bot)

    async def stop(self) -> None:
        """Stop the bot gracefully."""
        logger.info("Stopping bot")
        await self.bot.session.close()


async def on_startup(bridge: ClaudeBridge, settings: Settings) -> None:
    """Startup hook to verify system health and initialize Telethon.

    Args:
        bridge: The Claude Bridge instance to check.
        settings: Application settings.
    """
    global _voice_transcriber
    import os
    from pathlib import Path

    logger.info("Running startup checks...")

    # Check workspace directory permissions
    workspace = Path(settings.workspace_dir)
    if workspace.exists():
        is_readable = os.access(workspace, os.R_OK)
        is_writable = os.access(workspace, os.W_OK)
        is_executable = os.access(workspace, os.X_OK)

        if not is_writable:
            logger.error(
                "CRITICAL: Workspace directory is not writable! "
                "Claude Code will not be able to modify files.",
                extra={
                    "workspace": str(workspace),
                    "readable": is_readable,
                    "writable": is_writable,
                    "executable": is_executable,
                },
            )
            logger.error(
                f"Fix with: sudo chown -R $USER:$USER {workspace} "
                f"or add current user to the appropriate group"
            )
        elif not is_readable or not is_executable:
            logger.warning(
                "Workspace directory has limited permissions",
                extra={
                    "workspace": str(workspace),
                    "readable": is_readable,
                    "writable": is_writable,
                    "executable": is_executable,
                },
            )
        else:
            logger.info(
                "Workspace directory permissions OK",
                extra={"workspace": str(workspace)},
            )
    else:
        logger.warning(
            "Workspace directory does not exist",
            extra={"workspace": str(workspace)},
        )

    # Check Claude CLI health
    is_healthy = await bridge.check_health()
    if is_healthy:
        logger.info("Claude CLI is healthy and ready")
    else:
        logger.warning("Claude CLI health check failed - some features may not work")

    # Initialize Telethon if voice transcription is enabled
    if settings.voice_transcription_enabled:
        logger.info("Voice transcription enabled, initializing Telethon...")

        _voice_transcriber = get_transcriber(
            api_id=settings.telethon_api_id,
            api_hash=settings.telethon_api_hash,
            phone=settings.telethon_phone,
            session_name=settings.telethon_session_name,
        )

        if _voice_transcriber is None:
            logger.error(
                "Voice transcription enabled but Telethon credentials not configured. "
                "Set TELETHON_API_ID, TELETHON_API_HASH, and TELETHON_PHONE in .env"
            )
            return

        # Check if session exists and is authorized
        if not _voice_transcriber.session_exists():
            logger.warning(
                f"Telethon session file not found: {_voice_transcriber.session_file_path}. "
                "First-time authorization required. Run bot manually to enter code."
            )

        # Try to start the transcriber (will prompt for code if not authorized)
        try:
            await _voice_transcriber.start()
            logger.info("Telethon client started and authorized successfully")
        except ImportError:
            logger.error("Telethon not installed. Install with: pip install telethon")
        except TranscriptionError as e:
            logger.error(f"Failed to start Telethon: {e}")
    else:
        logger.info("Voice transcription disabled")


async def on_shutdown() -> None:
    """Shutdown hook for cleanup."""
    global _voice_transcriber

    # Stop Telethon client if running
    if _voice_transcriber is not None and _voice_transcriber.is_started:
        await _voice_transcriber.stop()
        logger.info("Telethon client stopped")

    logger.info("Bot shutdown complete")


def setup_bot(settings: Settings | None = None) -> tuple[Dispatcher, Bot]:
    """Set up the bot with handlers and middleware.

    Args:
        settings: Optional settings instance. If not provided, loads from environment.

    Returns:
        Tuple of (Dispatcher, Bot) instances ready for polling.
    """
    if settings is None:
        settings = get_settings()

    # Create bot instance
    bot = Bot(
        token=settings.telegram_bot_token.get_secret_value(),
        default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN),
    )
    dp = Dispatcher()

    # Create JarvisBot instance for handlers
    jarvis_bot = JarvisBot(settings)

    # Use the dispatcher from JarvisBot (hooks already registered in __init__)
    dp = jarvis_bot.dp

    logger.info("Bot setup complete")

    return dp, bot
