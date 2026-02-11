"""Custom exceptions for JARVIS MK1 Lite.

This module defines a hierarchy of exceptions for proper error handling
across the application. All exceptions inherit from JarvisError.
"""

from __future__ import annotations


class JarvisError(Exception):
    """Base exception for all JARVIS MK1 Lite errors.

    All custom exceptions in this application should inherit from this class.
    This allows for catch-all exception handling when needed.
    """

    def __init__(self, message: str = "An error occurred") -> None:
        """Initialize the exception.

        Args:
            message: Human-readable error message.
        """
        self.message = message
        super().__init__(self.message)


# =============================================================================
# Session Errors
# =============================================================================


class SessionError(JarvisError):
    """Base exception for session-related errors."""

    pass


class SessionNotFoundError(SessionError):
    """Raised when a requested session does not exist.

    Attributes:
        session_name: The name of the session that was not found.
        user_id: The user ID that owns (or should own) the session.
    """

    def __init__(
        self,
        session_name: str,
        user_id: int | None = None,
        message: str | None = None,
    ) -> None:
        """Initialize the exception.

        Args:
            session_name: Name of the session that was not found.
            user_id: Optional user ID for context.
            message: Optional custom message.
        """
        self.session_name = session_name
        self.user_id = user_id
        msg = message or f"Session '{session_name}' not found"
        if user_id is not None:
            msg += f" for user {user_id}"
        super().__init__(msg)


class SessionLimitExceededError(SessionError):
    """Raised when user exceeds maximum allowed sessions.

    Attributes:
        user_id: The user ID that exceeded the limit.
        current_count: Current number of sessions.
        max_sessions: Maximum allowed sessions.
    """

    def __init__(
        self,
        user_id: int,
        current_count: int,
        max_sessions: int,
        message: str | None = None,
    ) -> None:
        """Initialize the exception.

        Args:
            user_id: User ID that exceeded the limit.
            current_count: Current number of sessions.
            max_sessions: Maximum allowed sessions.
            message: Optional custom message.
        """
        self.user_id = user_id
        self.current_count = current_count
        self.max_sessions = max_sessions
        msg = message or (
            f"Session limit exceeded for user {user_id}: "
            f"{current_count}/{max_sessions} sessions"
        )
        super().__init__(msg)


class InvalidSessionNameError(SessionError):
    """Raised when session name is invalid.

    Attributes:
        session_name: The invalid session name.
        reason: Reason why the name is invalid.
    """

    def __init__(
        self,
        session_name: str,
        reason: str = "invalid characters",
        message: str | None = None,
    ) -> None:
        """Initialize the exception.

        Args:
            session_name: The invalid session name.
            reason: Reason why the name is invalid.
            message: Optional custom message.
        """
        self.session_name = session_name
        self.reason = reason
        msg = message or f"Invalid session name '{session_name}': {reason}"
        super().__init__(msg)


class SessionAlreadyExistsError(SessionError):
    """Raised when trying to create a session that already exists.

    Attributes:
        session_name: The name of the existing session.
        user_id: The user ID that owns the session.
    """

    def __init__(
        self,
        session_name: str,
        user_id: int | None = None,
        message: str | None = None,
    ) -> None:
        """Initialize the exception.

        Args:
            session_name: Name of the existing session.
            user_id: Optional user ID for context.
            message: Optional custom message.
        """
        self.session_name = session_name
        self.user_id = user_id
        msg = message or f"Session '{session_name}' already exists"
        if user_id is not None:
            msg += f" for user {user_id}"
        super().__init__(msg)


# =============================================================================
# Telegram Errors
# =============================================================================


class TelegramError(JarvisError):
    """Base exception for Telegram API errors."""

    pass


class TelegramRateLimitError(TelegramError):
    """Raised when Telegram rate limit is hit.

    Attributes:
        retry_after: Seconds to wait before retrying.
    """

    def __init__(
        self,
        retry_after: float,
        message: str | None = None,
    ) -> None:
        """Initialize the exception.

        Args:
            retry_after: Seconds to wait before retrying.
            message: Optional custom message.
        """
        self.retry_after = retry_after
        msg = message or f"Rate limited by Telegram, retry after {retry_after}s"
        super().__init__(msg)


class TelegramConnectionError(TelegramError):
    """Raised when connection to Telegram API fails.

    Attributes:
        original_error: The original exception that caused this error.
    """

    def __init__(
        self,
        original_error: Exception | None = None,
        message: str | None = None,
    ) -> None:
        """Initialize the exception.

        Args:
            original_error: The original exception that caused this error.
            message: Optional custom message.
        """
        self.original_error = original_error
        msg = message or "Failed to connect to Telegram API"
        if original_error:
            msg += f": {original_error}"
        super().__init__(msg)


class TelegramMessageError(TelegramError):
    """Raised when a message operation fails.

    Attributes:
        operation: The operation that failed (send, edit, delete).
        chat_id: The chat ID where the operation failed.
    """

    def __init__(
        self,
        operation: str = "send",
        chat_id: int | str | None = None,
        message: str | None = None,
    ) -> None:
        """Initialize the exception.

        Args:
            operation: The operation that failed.
            chat_id: The chat ID where the operation failed.
            message: Optional custom message.
        """
        self.operation = operation
        self.chat_id = chat_id
        msg = message or f"Failed to {operation} message"
        if chat_id:
            msg += f" in chat {chat_id}"
        super().__init__(msg)


# =============================================================================
# Bridge Errors
# =============================================================================


class BridgeError(JarvisError):
    """Base exception for Claude Bridge errors."""

    pass


class ClaudeTimeoutError(BridgeError):
    """Raised when Claude CLI request times out.

    Attributes:
        timeout: The timeout value in seconds.
        partial_output: Any partial output received before timeout.
    """

    def __init__(
        self,
        timeout: float,
        partial_output: str | None = None,
        message: str | None = None,
    ) -> None:
        """Initialize the exception.

        Args:
            timeout: The timeout value in seconds.
            partial_output: Any partial output received before timeout.
            message: Optional custom message.
        """
        self.timeout = timeout
        self.partial_output = partial_output
        msg = message or f"Claude CLI request timed out after {timeout}s"
        super().__init__(msg)


class ClaudeCLIError(BridgeError):
    """Raised when Claude CLI returns an error.

    Attributes:
        return_code: The CLI return code.
        stderr: The stderr output from CLI.
    """

    def __init__(
        self,
        return_code: int,
        stderr: str = "",
        message: str | None = None,
    ) -> None:
        """Initialize the exception.

        Args:
            return_code: The CLI return code.
            stderr: The stderr output from CLI.
            message: Optional custom message.
        """
        self.return_code = return_code
        self.stderr = stderr
        msg = message or f"Claude CLI error (code {return_code})"
        if stderr:
            msg += f": {stderr[:200]}"
        super().__init__(msg)


class ClaudeCLINotFoundError(BridgeError):
    """Raised when Claude CLI is not found in PATH."""

    def __init__(self, message: str | None = None) -> None:
        """Initialize the exception.

        Args:
            message: Optional custom message.
        """
        msg = message or "Claude CLI not found. Ensure 'claude' is installed and in PATH."
        super().__init__(msg)


class UnauthorizedUserError(BridgeError):
    """Raised when an unauthorized user attempts to use the bridge.

    Attributes:
        user_id: The unauthorized user ID.
    """

    def __init__(
        self,
        user_id: int,
        message: str | None = None,
    ) -> None:
        """Initialize the exception.

        Args:
            user_id: The unauthorized user ID.
            message: Optional custom message.
        """
        self.user_id = user_id
        msg = message or f"Unauthorized user: {user_id}"
        super().__init__(msg)


# =============================================================================
# Configuration Errors
# =============================================================================


class ConfigurationError(JarvisError):
    """Raised when configuration is invalid or missing.

    Attributes:
        config_key: The configuration key that is invalid.
    """

    def __init__(
        self,
        config_key: str | None = None,
        message: str | None = None,
    ) -> None:
        """Initialize the exception.

        Args:
            config_key: The configuration key that is invalid.
            message: Optional custom message.
        """
        self.config_key = config_key
        msg = message or "Configuration error"
        if config_key:
            msg = f"Invalid configuration for '{config_key}'"
        super().__init__(msg)


# =============================================================================
# File Send Errors
# =============================================================================


class FileSendError(JarvisError):
    """Base exception for file sending errors.

    Attributes:
        file_path: The path of the file that caused the error.
    """

    def __init__(
        self,
        file_path: str | None = None,
        message: str | None = None,
    ) -> None:
        """Initialize the exception.

        Args:
            file_path: The path of the file that caused the error.
            message: Optional custom message.
        """
        self.file_path = file_path
        msg = message or "File send error"
        if file_path:
            msg += f": {file_path}"
        super().__init__(msg)


class FileNotFoundSendError(FileSendError):
    """Raised when file to send is not found.

    Attributes:
        file_path: The path of the file that was not found.
    """

    def __init__(
        self,
        file_path: str,
        message: str | None = None,
    ) -> None:
        """Initialize the exception.

        Args:
            file_path: The path of the file that was not found.
            message: Optional custom message.
        """
        msg = message or f"File not found: {file_path}"
        super().__init__(file_path, msg)


class FileTooLargeError(FileSendError):
    """Raised when file exceeds Telegram size limit (50MB).

    Attributes:
        file_path: The path of the file.
        size_mb: The actual file size in MB.
        max_size_mb: The maximum allowed size in MB.
    """

    def __init__(
        self,
        file_path: str,
        size_mb: float,
        max_size_mb: float = 50.0,
        message: str | None = None,
    ) -> None:
        """Initialize the exception.

        Args:
            file_path: The path of the file.
            size_mb: The actual file size in MB.
            max_size_mb: The maximum allowed size in MB.
            message: Optional custom message.
        """
        self.size_mb = size_mb
        self.max_size_mb = max_size_mb
        msg = message or (
            f"File too large: {file_path} "
            f"({size_mb:.1f}MB > {max_size_mb:.1f}MB limit)"
        )
        super().__init__(file_path, msg)


class FileAccessDeniedError(FileSendError):
    """Raised when access to file is denied.

    Attributes:
        file_path: The path of the file.
        reason: The reason for access denial.
    """

    def __init__(
        self,
        file_path: str,
        reason: str = "permission denied",
        message: str | None = None,
    ) -> None:
        """Initialize the exception.

        Args:
            file_path: The path of the file.
            reason: The reason for access denial.
            message: Optional custom message.
        """
        self.reason = reason
        msg = message or f"Access denied to file {file_path}: {reason}"
        super().__init__(file_path, msg)


class TelegramFileSendError(FileSendError):
    """Raised when Telegram API fails to send file.

    Attributes:
        file_path: The path of the file.
        original_error: The original Telegram error.
    """

    def __init__(
        self,
        file_path: str,
        original_error: Exception | None = None,
        message: str | None = None,
    ) -> None:
        """Initialize the exception.

        Args:
            file_path: The path of the file.
            original_error: The original Telegram error.
            message: Optional custom message.
        """
        self.original_error = original_error
        msg = message or f"Failed to send file via Telegram: {file_path}"
        if original_error:
            msg += f" ({original_error})"
        super().__init__(file_path, msg)
