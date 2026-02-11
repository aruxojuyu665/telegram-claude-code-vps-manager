"""Claude Code Bridge - Integration with Claude CLI.

This module provides a bridge to communicate with Claude CLI for executing
agentic tasks through Telegram. Supports multiple named sessions per user.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from jarvis_mk1_lite.exceptions import (
    ClaudeCLIError,
    ClaudeCLINotFoundError,
    ClaudeTimeoutError,
    ConfigurationError,
    InvalidSessionNameError,
    SessionAlreadyExistsError,
    SessionLimitExceededError,
    SessionNotFoundError,
    UnauthorizedUserError,
)

# Constants for input validation
MAX_MESSAGE_LENGTH = 50000  # Maximum allowed message length
MAX_SESSION_ID_LENGTH = 256  # Maximum session ID length
SESSION_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")
SESSION_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")
DEFAULT_SESSION_NAME = "main"
MAX_SESSION_NAME_LENGTH = 32

# Default system prompt fallback when file is not available
DEFAULT_SYSTEM_PROMPT = """You are JARVIS, a helpful AI assistant.
Be concise, accurate, and helpful in your responses.
When asked to perform tasks, explain what you're doing step by step.

## File Download Feature
When the user asks to download, export, or send files to them, use special markers:
- For a single file: [FILE:/absolute/path/to/file.ext]
- For a directory (all files): [DIR:/absolute/path/to/directory]
- For a pattern (glob): [GLOB:/path/to/*.py]

Examples:
- User: "Download config.py" → "Here is the file [FILE:/opt/project/config.py]"
- User: "Send me all .py files from src" → "Sending files [GLOB:/opt/project/src/*.py]"
- User: "Export the logs folder" → "Exporting directory [DIR:/opt/project/logs]"

IMPORTANT:
- Always use absolute paths
- The bot will automatically send the files to the user
- You can include multiple markers in one response
- The markers will be stripped from the visible response"""


if TYPE_CHECKING:
    pass

# Use standard logging (structlog would be added as dependency if needed)
logger = logging.getLogger(__name__)


@dataclass
class SessionInfo:
    """Information about a session.

    Attributes:
        name: Session name (user-defined).
        session_id: Claude CLI session ID.
        created_at: Unix timestamp when session was created.
        last_used: Unix timestamp when session was last used.
        is_active: Whether this is the active session.
        model: Claude model to use for this session.
    """

    name: str
    session_id: str
    created_at: float
    last_used: float
    is_active: bool = False
    model: str = "sonnet"  # Default to sonnet 4.5


@dataclass
class ClaudeResponse:
    """Response from Claude CLI.

    Attributes:
        success: Whether the request was successful.
        content: The response content from Claude.
        error: Error message if the request failed.
        session_id: Session ID for conversation continuity.
        session_name: Name of the session used.
    """

    success: bool
    content: str
    error: str | None = None
    session_id: str | None = None
    session_name: str | None = None


@dataclass
class UserSessions:
    """Container for a user's sessions.

    Attributes:
        sessions: Mapping of session name to session ID.
        timestamps: Mapping of session name to last activity timestamp.
        active_session: Name of the currently active session.
        created_at: Mapping of session name to creation timestamp.
        models: Mapping of session name to Claude model.
    """

    sessions: dict[str, str] = field(default_factory=dict)
    timestamps: dict[str, float] = field(default_factory=dict)
    created_at: dict[str, float] = field(default_factory=dict)
    models: dict[str, str] = field(default_factory=dict)
    active_session: str = DEFAULT_SESSION_NAME


class ClaudeBridge:
    """Bridge to Claude CLI for executing agentic tasks.

    This class manages communication with the Claude CLI, including:
    - Multi-session management per user with LRU eviction and expiry
    - User authorization via allowed_user_ids whitelist
    - System prompt loading
    - Command building and execution
    - Error handling and timeouts

    Example:
        >>> bridge = ClaudeBridge()
        >>> response = await bridge.send(user_id=123, message="Hello")
        >>> print(response.content)
    """

    def __init__(self, allowed_user_ids: list[int] | None = None) -> None:
        """Initialize the Claude Bridge.

        Args:
            allowed_user_ids: Optional list of allowed user IDs. If None, loads from settings.

        Loads settings and system prompt on initialization.
        """
        # Multi-session storage: user_id -> UserSessions
        self._user_sessions: dict[int, UserSessions] = {}

        # Session metrics for observability
        self._sessions_expired: int = 0
        self._sessions_evicted: int = 0
        self._total_sessions_created: int = 0

        self._system_prompt: str | None = None
        self._settings: Any = None  # Settings instance, loaded lazily
        self._allowed_user_ids: set[int] = set(allowed_user_ids or [])
        self._load_settings()
        self._load_system_prompt()

        # Update allowed_user_ids from settings if not explicitly provided
        if not self._allowed_user_ids and self._settings:
            self._allowed_user_ids = set(self._settings.allowed_user_ids)

    def _load_settings(self) -> None:
        """Load settings from configuration.

        Imports settings lazily to avoid circular imports.
        """
        try:
            from jarvis_mk1_lite.config import get_settings

            self._settings = get_settings()
            logger.info("Settings loaded successfully")
        except Exception as e:
            logger.warning("Failed to load settings: %s", e)
            self._settings = None

    def _validate_user(self, user_id: int) -> bool:
        """Validate if user_id is authorized.

        Args:
            user_id: The Telegram user ID to validate.

        Returns:
            True if user is authorized, False otherwise.
        """
        # If no whitelist is configured, allow all users (development mode)
        if not self._allowed_user_ids:
            return True

        is_valid = user_id in self._allowed_user_ids
        if not is_valid:
            logger.warning(
                "Unauthorized user_id attempted session access",
                extra={"user_id": user_id},
            )
        return is_valid

    def _validate_session_name(self, name: str) -> bool:
        """Validate session name format.

        Args:
            name: The session name to validate.

        Returns:
            True if valid, False otherwise.
        """
        if not name:
            return False

        max_length = MAX_SESSION_NAME_LENGTH
        if self._settings:
            setting_value = getattr(self._settings, "session_name_max_length", None)
            if isinstance(setting_value, int):
                max_length = setting_value

        if len(name) > max_length:
            return False

        return bool(SESSION_NAME_PATTERN.match(name))

    def _sanitize_message(self, message: str) -> str:
        """Sanitize user message by removing dangerous characters.

        Args:
            message: The raw message to sanitize.

        Returns:
            Sanitized message safe for processing.
        """
        # Remove null bytes which could cause issues
        sanitized = message.replace("\x00", "")

        # Limit message length to prevent DoS
        if len(sanitized) > MAX_MESSAGE_LENGTH:
            logger.warning(
                "Message truncated due to length limit",
                extra={"original_length": len(message), "max_length": MAX_MESSAGE_LENGTH},
            )
            sanitized = sanitized[:MAX_MESSAGE_LENGTH]

        return sanitized

    def _validate_session_id(self, session_id: str) -> bool:
        """Validate session_id format and length.

        Args:
            session_id: The session ID to validate.

        Returns:
            True if valid, False otherwise.
        """
        if not session_id:
            return False

        if len(session_id) > MAX_SESSION_ID_LENGTH:
            logger.warning(
                "Invalid session_id: exceeds max length",
                extra={"length": len(session_id), "max_length": MAX_SESSION_ID_LENGTH},
            )
            return False

        if not SESSION_ID_PATTERN.match(session_id):
            logger.warning(
                "Invalid session_id: contains invalid characters",
                extra={"session_id_prefix": session_id[:20]},
            )
            return False

        return True

    def _load_system_prompt(self) -> None:
        """Load system prompt from file with fallback to default.

        Reads the system prompt from the path specified in settings.
        Falls back to DEFAULT_SYSTEM_PROMPT if file is not available.
        """
        if self._settings is None:
            logger.warning("Settings not available, using default system prompt")
            self._system_prompt = DEFAULT_SYSTEM_PROMPT
            return

        prompt_path = Path(self._settings.system_prompt_path)
        try:
            if prompt_path.exists():
                self._system_prompt = prompt_path.read_text(encoding="utf-8")
                logger.info(
                    "System prompt loaded",
                    extra={"path": str(prompt_path), "length": len(self._system_prompt)},
                )
            else:
                logger.warning(
                    "System prompt file not found, using default",
                    extra={"path": str(prompt_path)},
                )
                self._system_prompt = DEFAULT_SYSTEM_PROMPT
        except UnicodeDecodeError as e:
            logger.error(
                "Failed to decode system prompt (encoding error), using default",
                extra={"path": str(prompt_path), "error": str(e)},
            )
            self._system_prompt = DEFAULT_SYSTEM_PROMPT
        except OSError as e:
            logger.error(
                "Failed to load system prompt (IO error), using default",
                extra={"path": str(prompt_path), "error": str(e)},
            )
            self._system_prompt = DEFAULT_SYSTEM_PROMPT

    def _get_user_sessions(self, user_id: int) -> UserSessions:
        """Get or create UserSessions for a user.

        Args:
            user_id: The Telegram user ID.

        Returns:
            UserSessions instance for the user.
        """
        if user_id not in self._user_sessions:
            self._user_sessions[user_id] = UserSessions()
        return self._user_sessions[user_id]

    def _get_max_sessions_per_user(self) -> int:
        """Get maximum sessions per user from settings.

        Returns:
            Maximum sessions per user.
        """
        if self._settings:
            setting_value = getattr(self._settings, "max_sessions_per_user", None)
            if isinstance(setting_value, int):
                return setting_value
        return 10  # Default

    def _build_command(
        self, user_id: int, message: str, session_name: str | None = None
    ) -> list[str]:
        """Build the Claude CLI command.

        Args:
            user_id: The Telegram user ID for session tracking.
            message: The message to send to Claude.
            session_name: Optional session name to use. Uses active session if None.

        Returns:
            List of command arguments for subprocess execution.
        """
        cmd = [
            "claude",
            "--output-format",
            "json",
        ]

        # Get session info
        user_sessions = self._get_user_sessions(user_id)
        target_session = session_name or user_sessions.active_session

        # Get model from session or use default from settings
        session_model = user_sessions.models.get(target_session)
        if session_model:
            cmd.extend(["--model", session_model])
        elif self._settings:
            cmd.extend(["--model", self._settings.claude_model])

        if self._settings:
            # Add workspace directory access
            cmd.extend(["--add-dir", self._settings.workspace_dir])

        # Add system prompt if available
        if self._system_prompt:
            cmd.extend(["--system-prompt", self._system_prompt])

        # Only add --resume if session_id is non-empty
        session_id = user_sessions.sessions.get(target_session)
        if session_id:
            cmd.extend(["--resume", session_id])

        # Add --print flag with "-" to read from stdin (prevents CLI parsing issues)
        cmd.extend(["--print", "-"])

        return cmd

    async def _execute(
        self,
        cmd: list[str],
        stdin_input: str | None = None,
        verbose_callback: Callable[[str], Awaitable[None]] | None = None,
    ) -> ClaudeResponse:
        """Execute the Claude CLI command.

        Args:
            cmd: The command arguments to execute.
            stdin_input: Optional input to send to stdin (for --print -).
            verbose_callback: Optional async callback for streaming output lines.

        Returns:
            ClaudeResponse with the result or error.
        """
        timeout = self._settings.claude_timeout if self._settings else 300

        logger.debug(
            "Executing Claude CLI",
            extra={
                "command_length": len(cmd),
                "timeout": timeout,
                "verbose": verbose_callback is not None,
                "has_stdin": stdin_input is not None,
            },
        )

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE if stdin_input else None,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                # Write stdin if provided
                if stdin_input and process.stdin:
                    process.stdin.write(stdin_input.encode('utf-8'))
                    await process.stdin.drain()
                    process.stdin.close()

                if verbose_callback and process.stdout:
                    # Stream stdout line by line for verbose mode
                    stdout_lines: list[bytes] = []
                    stderr_data = b""
                    stderr_task: asyncio.Task[bytes] | None = None
                    start_time = asyncio.get_event_loop().time()

                    async def read_stderr() -> bytes:
                        """Read stderr in background."""
                        if process.stderr:
                            return await process.stderr.read()
                        return b""

                    try:
                        # Start stderr reader
                        stderr_task = asyncio.create_task(read_stderr())

                        # Read stdout line by line with total timeout check
                        while True:
                            # Check total operation timeout
                            elapsed = asyncio.get_event_loop().time() - start_time
                            remaining_timeout = max(1.0, timeout - elapsed)

                            if elapsed >= timeout:
                                raise TimeoutError("Total operation timeout")

                            try:
                                line = await asyncio.wait_for(
                                    process.stdout.readline(),
                                    timeout=remaining_timeout,
                                )
                                if not line:
                                    break

                                stdout_lines.append(line)
                                decoded_line = line.decode("utf-8", errors="replace").strip()

                                # Call verbose callback for non-empty lines
                                if decoded_line:
                                    try:
                                        await verbose_callback(decoded_line)
                                    except Exception as e:
                                        # Log callback errors at WARNING level for visibility
                                        logger.warning(
                                            "Verbose callback error",
                                            extra={"error": str(e)},
                                        )
                            except TimeoutError:
                                raise

                        # Wait for process to complete
                        await process.wait()
                        stderr_data = await stderr_task

                    except TimeoutError:
                        # Cancel stderr task if running
                        if stderr_task and not stderr_task.done():
                            stderr_task.cancel()
                            with contextlib.suppress(asyncio.CancelledError):
                                await stderr_task

                        # Kill process
                        process.kill()
                        await process.wait()

                        # Return partial output if available
                        partial_output = b"".join(stdout_lines).decode("utf-8", errors="replace")
                        if partial_output.strip():
                            logger.warning(
                                "Claude CLI timeout with partial output",
                                extra={"timeout": timeout, "partial_length": len(partial_output)},
                            )
                            return ClaudeResponse(
                                success=False,
                                content=partial_output,
                                error=f"Request timed out after {timeout} seconds (partial output available)",
                            )

                        logger.error(
                            "Claude CLI timeout during streaming", extra={"timeout": timeout}
                        )
                        return ClaudeResponse(
                            success=False,
                            content="",
                            error=f"Request timed out after {timeout} seconds",
                        )

                    stdout = b"".join(stdout_lines)
                    stderr = stderr_data
                else:
                    # Non-verbose mode: use communicate()
                    stdin_bytes = stdin_input.encode('utf-8') if stdin_input else None
                    stdout, stderr = await asyncio.wait_for(
                        process.communicate(input=stdin_bytes),
                        timeout=timeout,
                    )

            except TimeoutError:
                process.kill()
                await process.wait()
                logger.error("Claude CLI timeout", extra={"timeout": timeout})
                return ClaudeResponse(
                    success=False,
                    content="",
                    error=f"Request timed out after {timeout} seconds",
                )

            if process.returncode != 0:
                error_msg = stderr.decode("utf-8", errors="replace").strip()
                logger.error(
                    "Claude CLI error",
                    extra={"returncode": process.returncode, "stderr": error_msg},
                )
                return ClaudeResponse(
                    success=False,
                    content="",
                    error=f"CLI error (code {process.returncode}): {error_msg}",
                )

            # Parse JSON response
            output = stdout.decode("utf-8", errors="replace")
            return self._parse_response(output)

        except FileNotFoundError:
            logger.error("Claude CLI not found")
            return ClaudeResponse(
                success=False,
                content="",
                error="Claude CLI not found. Please ensure 'claude' is installed and in PATH.",
            )
        except OSError as e:
            logger.error("Subprocess error", extra={"error": str(e)})
            return ClaudeResponse(
                success=False,
                content="",
                error=f"Failed to execute Claude CLI: {e}",
            )

    def _parse_response(self, output: str) -> ClaudeResponse:
        """Parse the JSON response from Claude CLI.

        Claude CLI returns a JSON array with multiple objects:
        - type="system": initialization info
        - type="assistant": the response message
        - type="result": final result with session_id

        Args:
            output: Raw output from the CLI.

        Returns:
            ClaudeResponse with parsed content.
        """
        try:
            data = json.loads(output)

            # Handle JSON array format (Claude CLI 2.x)
            if isinstance(data, list):
                content = ""
                session_id = None
                is_error = False
                error_msg = None

                for item in data:
                    if not isinstance(item, dict):
                        continue

                    item_type = item.get("type")

                    # Extract result from "result" type object
                    if item_type == "result":
                        content = item.get("result", "")
                        session_id = item.get("session_id")
                        is_error = item.get("is_error", False)
                        if is_error:
                            error_msg = item.get("error", "Unknown error")

                    # Fallback: extract from "assistant" type if no result
                    elif item_type == "assistant" and not content:
                        message = item.get("message", {})
                        msg_content = message.get("content", [])
                        if isinstance(msg_content, list):
                            texts = []
                            for c in msg_content:
                                if isinstance(c, dict) and c.get("type") == "text":
                                    texts.append(c.get("text", ""))
                            content = "\n".join(texts)

                if is_error:
                    logger.error("Claude CLI returned error", extra={"error": error_msg})
                    return ClaudeResponse(
                        success=False,
                        content="",
                        error=error_msg,
                    )

                logger.debug(
                    "Response parsed (array format)",
                    extra={
                        "content_length": len(str(content)),
                        "has_session": session_id is not None,
                    },
                )

                return ClaudeResponse(
                    success=True,
                    content=str(content),
                    session_id=session_id,
                )

            # Handle single object format (legacy)
            if isinstance(data, dict):
                # Check for explicit error field
                if data.get("error"):
                    error_msg = str(data.get("error"))
                    logger.error("Claude CLI returned error in JSON", extra={"error": error_msg})
                    return ClaudeResponse(
                        success=False,
                        content="",
                        error=error_msg,
                    )

                # Try common response fields
                content: Any = data.get("result", data.get("content", data.get("text", "")))

                # If content is a list of messages, extract text
                if isinstance(content, list):
                    texts = []
                    for item in content:
                        if isinstance(item, dict):
                            texts.append(item.get("text", str(item)))
                        else:
                            texts.append(str(item))
                    content = "\n".join(texts)

                session_id = data.get("session_id")

                logger.debug(
                    "Response parsed (object format)",
                    extra={
                        "content_length": len(str(content)),
                        "has_session": session_id is not None,
                    },
                )

                return ClaudeResponse(
                    success=True,
                    content=str(content),
                    session_id=session_id,
                )

            # Unknown format
            logger.warning("Unknown JSON format", extra={"type": type(data).__name__})
            return ClaudeResponse(
                success=True,
                content=str(data),
            )

        except json.JSONDecodeError as e:
            logger.warning(
                "JSON parse error, using raw output",
                extra={"error": str(e)},
            )
            # If not JSON, return raw output (might be plain text mode)
            return ClaudeResponse(
                success=True,
                content=output.strip(),
            )
        except (TypeError, AttributeError, KeyError) as e:
            logger.error(
                "Unexpected error parsing response",
                extra={"error": str(e), "error_type": type(e).__name__},
            )
            return ClaudeResponse(
                success=False,
                content="",
                error=f"Failed to parse Claude response: {type(e).__name__}",
            )

    # =========================================================================
    # Model Management Methods
    # =========================================================================

    def set_session_model(self, user_id: int, model: str, session_name: str | None = None) -> bool:
        """Set Claude model for a session.

        Args:
            user_id: The Telegram user ID.
            model: Model identifier (e.g., "claude-opus-4-5-20250514").
            session_name: Session name. Uses active session if None.

        Returns:
            True if model was set successfully.

        Raises:
            UnauthorizedUserError: If user is not authorized.
            SessionNotFoundError: If session does not exist.
        """
        if not self._validate_user(user_id):
            raise UnauthorizedUserError(user_id)

        user_sessions = self._get_user_sessions(user_id)
        target_session = session_name or user_sessions.active_session

        if target_session not in user_sessions.sessions:
            raise SessionNotFoundError(target_session, user_id)

        user_sessions.models[target_session] = model

        logger.info(
            "Session model updated",
            extra={
                "user_id": user_id,
                "session_name": target_session,
                "model": model,
            },
        )

        return True

    def get_session_model(self, user_id: int, session_name: str | None = None) -> str:
        """Get Claude model for a session.

        Args:
            user_id: The Telegram user ID.
            session_name: Session name. Uses active session if None.

        Returns:
            Model identifier.
        """
        user_sessions = self._get_user_sessions(user_id)
        target_session = session_name or user_sessions.active_session

        # Return session model or default
        session_model = user_sessions.models.get(target_session)
        if session_model:
            return session_model

        # Fallback to settings default
        if self._settings:
            return self._settings.claude_model

        # Ultimate fallback
        return "sonnet"

    # =========================================================================
    # Session Management Methods
    # =========================================================================

    def create_session(
        self,
        user_id: int,
        name: str | None = None,
        set_active: bool = True,
    ) -> str:
        """Create a new named session for a user.

        Args:
            user_id: The Telegram user ID.
            name: Session name. Auto-generates if None.
            set_active: Whether to set this as the active session.

        Returns:
            The session name.

        Raises:
            UnauthorizedUserError: If user is not authorized.
            InvalidSessionNameError: If session name is invalid.
            SessionAlreadyExistsError: If session with this name already exists.
            SessionLimitExceededError: If user has too many sessions.
        """
        if not self._validate_user(user_id):
            raise UnauthorizedUserError(user_id)

        user_sessions = self._get_user_sessions(user_id)
        max_sessions = self._get_max_sessions_per_user()

        # Auto-generate name if not provided
        if name is None:
            name = self._generate_session_name(user_id)

        # Validate name
        if not self._validate_session_name(name):
            raise InvalidSessionNameError(
                name,
                reason=f"must match pattern [a-zA-Z0-9_-] and be <= {MAX_SESSION_NAME_LENGTH} chars",
            )

        # Check if session already exists
        if name in user_sessions.sessions:
            raise SessionAlreadyExistsError(name, user_id)

        # Check limit
        if len(user_sessions.sessions) >= max_sessions:
            # Try to evict oldest session
            evicted = self._evict_oldest_session(user_id)
            if not evicted:
                raise SessionLimitExceededError(
                    user_id,
                    len(user_sessions.sessions),
                    max_sessions,
                )

        # Create session (without session_id - will be set after first message)
        now = time.time()
        user_sessions.sessions[name] = ""  # Empty until first response
        user_sessions.timestamps[name] = now
        user_sessions.created_at[name] = now
        # Set default model from settings
        default_model = self._settings.claude_model if self._settings else "sonnet"
        user_sessions.models[name] = default_model
        self._total_sessions_created += 1

        if set_active:
            user_sessions.active_session = name

        logger.info(
            "Session created",
            extra={
                "user_id": user_id,
                "session_name": name,
                "model": default_model,
                "total_sessions": len(user_sessions.sessions),
            },
        )

        return name

    def _generate_session_name(self, user_id: int) -> str:
        """Generate an auto-incremented session name.

        Args:
            user_id: The Telegram user ID.

        Returns:
            A unique session name like "session-1", "session-2", etc.
        """
        user_sessions = self._get_user_sessions(user_id)
        counter = 1

        while f"session-{counter}" in user_sessions.sessions:
            counter += 1

        return f"session-{counter}"

    def _evict_oldest_session(self, user_id: int) -> bool:
        """Evict the oldest session for a user.

        Args:
            user_id: The Telegram user ID.

        Returns:
            True if a session was evicted, False if no sessions to evict.
        """
        user_sessions = self._get_user_sessions(user_id)

        if not user_sessions.sessions:
            return False

        # Don't evict the active session if it's the only one
        if len(user_sessions.sessions) == 1:
            return False

        # Find oldest non-active session
        oldest_name = None
        oldest_time = float("inf")

        for name, timestamp in user_sessions.timestamps.items():
            if name != user_sessions.active_session and timestamp < oldest_time:
                oldest_time = timestamp
                oldest_name = name

        if oldest_name is None:
            # All sessions are active, evict the oldest one
            oldest_name = min(user_sessions.timestamps, key=user_sessions.timestamps.get)  # type: ignore

        # Evict
        user_sessions.sessions.pop(oldest_name, None)
        user_sessions.timestamps.pop(oldest_name, None)
        user_sessions.created_at.pop(oldest_name, None)
        user_sessions.models.pop(oldest_name, None)
        self._sessions_evicted += 1

        logger.info(
            "Session evicted (LRU)",
            extra={
                "user_id": user_id,
                "session_name": oldest_name,
                "reason": "max_sessions_exceeded",
            },
        )

        return True

    def switch_session(self, user_id: int, name: str) -> bool:
        """Switch to a different session.

        Args:
            user_id: The Telegram user ID.
            name: Name of the session to switch to.

        Returns:
            True if switched successfully.

        Raises:
            UnauthorizedUserError: If user is not authorized.
            SessionNotFoundError: If session does not exist.
        """
        if not self._validate_user(user_id):
            raise UnauthorizedUserError(user_id)

        user_sessions = self._get_user_sessions(user_id)

        if name not in user_sessions.sessions:
            raise SessionNotFoundError(name, user_id)

        user_sessions.active_session = name
        user_sessions.timestamps[name] = time.time()

        logger.info(
            "Session switched",
            extra={"user_id": user_id, "session_name": name},
        )

        return True

    def delete_session(self, user_id: int, name: str) -> bool:
        """Delete a session.

        Args:
            user_id: The Telegram user ID.
            name: Name of the session to delete.

        Returns:
            True if deleted successfully.

        Raises:
            UnauthorizedUserError: If user is not authorized.
            SessionNotFoundError: If session does not exist.
        """
        if not self._validate_user(user_id):
            raise UnauthorizedUserError(user_id)

        user_sessions = self._get_user_sessions(user_id)

        if name not in user_sessions.sessions:
            raise SessionNotFoundError(name, user_id)

        # Delete session
        user_sessions.sessions.pop(name, None)
        user_sessions.timestamps.pop(name, None)
        user_sessions.created_at.pop(name, None)
        user_sessions.models.pop(name, None)

        # If deleted active session, switch to another or create default
        if user_sessions.active_session == name:
            if user_sessions.sessions:
                # Switch to most recently used session
                most_recent = max(user_sessions.timestamps, key=user_sessions.timestamps.get)  # type: ignore
                user_sessions.active_session = most_recent
            else:
                # No sessions left, reset to default
                user_sessions.active_session = DEFAULT_SESSION_NAME

        logger.info(
            "Session deleted",
            extra={
                "user_id": user_id,
                "session_name": name,
                "remaining_sessions": len(user_sessions.sessions),
            },
        )

        return True

    def list_sessions(self, user_id: int) -> list[SessionInfo]:
        """List all sessions for a user.

        Args:
            user_id: The Telegram user ID.

        Returns:
            List of SessionInfo objects.

        Raises:
            UnauthorizedUserError: If user is not authorized.
        """
        if not self._validate_user(user_id):
            raise UnauthorizedUserError(user_id)

        user_sessions = self._get_user_sessions(user_id)
        result: list[SessionInfo] = []

        for name, session_id in user_sessions.sessions.items():
            # Get model for this session
            session_model = user_sessions.models.get(name)
            if not session_model:
                session_model = self._settings.claude_model if self._settings else "sonnet"

            result.append(
                SessionInfo(
                    name=name,
                    session_id=session_id,
                    created_at=user_sessions.created_at.get(name, 0),
                    last_used=user_sessions.timestamps.get(name, 0),
                    is_active=(name == user_sessions.active_session),
                    model=session_model,
                )
            )

        # Sort by last_used descending
        result.sort(key=lambda s: s.last_used, reverse=True)

        return result

    def get_active_session_name(self, user_id: int) -> str:
        """Get the name of the active session.

        Args:
            user_id: The Telegram user ID.

        Returns:
            Name of the active session.
        """
        user_sessions = self._get_user_sessions(user_id)
        return user_sessions.active_session

    def has_session(self, user_id: int, name: str) -> bool:
        """Check if a session exists.

        Args:
            user_id: The Telegram user ID.
            name: Session name to check.

        Returns:
            True if session exists.
        """
        user_sessions = self._get_user_sessions(user_id)
        return name in user_sessions.sessions

    # =========================================================================
    # Main API Methods
    # =========================================================================

    async def send(
        self,
        user_id: int,
        message: str,
        new_session: bool = False,
        session_name: str | None = None,
        verbose_callback: Callable[[str], Awaitable[None]] | None = None,
    ) -> ClaudeResponse:
        """Send a message to Claude CLI.

        Args:
            user_id: The Telegram user ID for session tracking.
            message: The message to send to Claude.
            new_session: If True, start a new session (clear existing).
            session_name: Optional session name to use. Uses active session if None.
            verbose_callback: Optional async callback for streaming output lines.

        Returns:
            ClaudeResponse with the result.
        """
        # Validate user authorization
        if not self._validate_user(user_id):
            return ClaudeResponse(
                success=False,
                content="",
                error="Unauthorized user",
            )

        # Sanitize user input
        message = self._sanitize_message(message)
        if not message.strip():
            return ClaudeResponse(
                success=False,
                content="",
                error="Empty message after sanitization",
            )

        # Cleanup expired sessions before processing
        self._cleanup_expired_sessions()

        user_sessions = self._get_user_sessions(user_id)
        target_session = session_name or user_sessions.active_session

        # Handle new_session flag
        if new_session:
            # Clear the target session's session_id to start fresh
            if target_session in user_sessions.sessions:
                user_sessions.sessions[target_session] = ""
            else:
                # Create the session if it doesn't exist
                try:
                    self.create_session(user_id, target_session, set_active=True)
                except (SessionAlreadyExistsError, SessionLimitExceededError):
                    pass  # Ignore if already exists or limit exceeded

        # Ensure session exists (create default if needed)
        if target_session not in user_sessions.sessions:
            try:
                self.create_session(user_id, target_session, set_active=True)
            except SessionLimitExceededError:
                return ClaudeResponse(
                    success=False,
                    content="",
                    error=f"Session limit exceeded. Delete some sessions first.",
                )

        logger.info(
            "Sending message to Claude",
            extra={
                "user_id": user_id,
                "message_length": len(message),
                "session_name": target_session,
                "has_session_id": bool(user_sessions.sessions.get(target_session)),
                "new_session": new_session,
                "verbose": verbose_callback is not None,
            },
        )

        # Build and execute command
        cmd = self._build_command(user_id, message, target_session)
        response = await self._execute(cmd, stdin_input=message, verbose_callback=verbose_callback)

        # Update session if successful and session_id provided
        if response.success and response.session_id:
            self._update_session(user_id, target_session, response.session_id)

        # Add session name to response
        response.session_name = target_session

        return response

    def _update_session(self, user_id: int, session_name: str, session_id: str) -> bool:
        """Update session with new session_id.

        Args:
            user_id: The Telegram user ID.
            session_name: The session name to update.
            session_id: The Claude session ID.

        Returns:
            True if session was updated, False if session_id is invalid.
        """
        # Validate session_id format
        if not self._validate_session_id(session_id):
            logger.warning(
                "Rejected invalid session_id",
                extra={"user_id": user_id, "session_name": session_name},
            )
            return False

        user_sessions = self._get_user_sessions(user_id)

        if session_name not in user_sessions.sessions:
            # Session was deleted while processing, ignore
            return False

        user_sessions.sessions[session_name] = session_id
        user_sessions.timestamps[session_name] = time.time()

        logger.debug(
            "Session updated",
            extra={
                "user_id": user_id,
                "session_name": session_name,
                "session_id": session_id,
            },
        )
        return True

    def _cleanup_expired_sessions(self) -> int:
        """Remove expired sessions based on inactivity timeout.

        Returns:
            Number of sessions cleaned up.
        """
        if self._settings is None:
            return 0

        now = time.time()
        expiry_seconds = self._settings.session_expiry_seconds
        total_expired = 0

        for user_id, user_sessions in list(self._user_sessions.items()):
            expired_names: list[str] = []

            for name, timestamp in user_sessions.timestamps.items():
                if now - timestamp > expiry_seconds:
                    expired_names.append(name)

            for name in expired_names:
                user_sessions.sessions.pop(name, None)
                user_sessions.timestamps.pop(name, None)
                user_sessions.created_at.pop(name, None)
                user_sessions.models.pop(name, None)
                self._sessions_expired += 1
                total_expired += 1

                logger.info(
                    "Session expired",
                    extra={
                        "user_id": user_id,
                        "session_name": name,
                        "reason": "inactivity_timeout",
                    },
                )

            # If active session expired, switch to another
            if user_sessions.active_session in expired_names:
                if user_sessions.sessions:
                    most_recent = max(user_sessions.timestamps, key=user_sessions.timestamps.get)  # type: ignore
                    user_sessions.active_session = most_recent
                else:
                    user_sessions.active_session = DEFAULT_SESSION_NAME

        return total_expired

    async def check_health(self) -> bool:
        """Check if Claude CLI is available and working.

        Returns:
            True if Claude CLI is healthy, False otherwise.
        """
        logger.debug("Checking Claude CLI health")

        try:
            process = await asyncio.create_subprocess_exec(
                "claude",
                "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, _ = await asyncio.wait_for(
                process.communicate(),
                timeout=10,
            )

            is_healthy = process.returncode == 0
            version = stdout.decode("utf-8", errors="replace").strip() if is_healthy else "unknown"

            logger.info(
                "Health check completed",
                extra={"healthy": is_healthy, "version": version},
            )

            return is_healthy

        except (TimeoutError, FileNotFoundError, OSError) as e:
            logger.error("Health check failed", extra={"error": str(e)})
            return False

    # =========================================================================
    # Legacy API (Backward Compatibility)
    # =========================================================================

    def clear_session(self, user_id: int) -> bool:
        """Clear the active session for a user (legacy API).

        Args:
            user_id: The Telegram user ID.

        Returns:
            True if a session was cleared, False if no session existed or unauthorized.
        """
        if not self._validate_user(user_id):
            return False

        user_sessions = self._get_user_sessions(user_id)
        active = user_sessions.active_session

        if active in user_sessions.sessions:
            # Clear the session_id but keep the session entry
            user_sessions.sessions[active] = ""
            logger.info(
                "Session cleared (legacy)",
                extra={"user_id": user_id, "session_name": active},
            )
            return True

        return False

    def get_session(self, user_id: int) -> str | None:
        """Get the session ID for the active session (legacy API).

        Args:
            user_id: The Telegram user ID.

        Returns:
            The session ID if exists and authorized, None otherwise.
        """
        if not self._validate_user(user_id):
            return None

        user_sessions = self._get_user_sessions(user_id)
        active = user_sessions.active_session
        session_id = user_sessions.sessions.get(active, "")

        return session_id if session_id else None

    def get_session_count(self) -> int:
        """Get the total number of active sessions across all users.

        Returns:
            Number of active sessions.
        """
        total = 0
        for user_sessions in self._user_sessions.values():
            total += len(user_sessions.sessions)
        return total

    def get_session_age(self, user_id: int) -> float | None:
        """Get the age of the active session in seconds.

        Args:
            user_id: The Telegram user ID.

        Returns:
            Session age in seconds, or None if no session exists.
        """
        user_sessions = self._get_user_sessions(user_id)
        active = user_sessions.active_session
        timestamp = user_sessions.timestamps.get(active)

        if timestamp is None:
            return None
        return time.time() - timestamp

    def get_oldest_session_age(self) -> float | None:
        """Get the age of the oldest session in seconds.

        Returns:
            Oldest session age in seconds, or None if no sessions exist.
        """
        oldest_timestamp = None

        for user_sessions in self._user_sessions.values():
            for timestamp in user_sessions.timestamps.values():
                if oldest_timestamp is None or timestamp < oldest_timestamp:
                    oldest_timestamp = timestamp

        if oldest_timestamp is None:
            return None
        return time.time() - oldest_timestamp

    def get_session_stats(self) -> dict[str, int | float | None]:
        """Get session statistics for monitoring.

        Returns:
            Dictionary with session statistics.
        """
        total_sessions = 0
        total_users = len(self._user_sessions)

        for user_sessions in self._user_sessions.values():
            total_sessions += len(user_sessions.sessions)

        avg_sessions_per_user = total_sessions / total_users if total_users > 0 else 0

        return {
            "active_sessions": total_sessions,
            "total_users": total_users,
            "avg_sessions_per_user": round(avg_sessions_per_user, 2),
            "sessions_expired": self._sessions_expired,
            "sessions_evicted": self._sessions_evicted,
            "total_sessions_created": self._total_sessions_created,
            "oldest_session_age": self.get_oldest_session_age(),
        }


def _create_bridge() -> ClaudeBridge:
    """Create the ClaudeBridge singleton instance.

    This function exists to handle potential import errors gracefully
    during module initialization.

    Returns:
        ClaudeBridge instance.
    """
    return ClaudeBridge()


# Singleton instance
claude_bridge = _create_bridge()
