"""Socratic Gate - Safety layer for dangerous command detection.

This module implements a security layer that categorizes commands by risk level
and requires appropriate confirmation for dangerous operations.
"""

import re
from dataclasses import dataclass
from enum import Enum


class RiskLevel(Enum):
    """Risk level for commands (ordered by severity).

    Attributes:
        SAFE: No risk, execute directly.
        MODERATE: Warning only, but execute.
        DANGEROUS: Requires YES/NO confirmation.
        CRITICAL: Requires explicit confirmation phrase.
    """

    SAFE = "safe"
    MODERATE = "moderate"
    DANGEROUS = "dangerous"
    CRITICAL = "critical"


@dataclass
class SafetyCheck:
    """Result of safety check.

    Attributes:
        risk_level: The risk level of the command.
        requires_confirmation: Whether user confirmation is needed.
        message: Optional message to display to user.
        matched_pattern: The pattern that matched, if any.
    """

    risk_level: RiskLevel
    requires_confirmation: bool
    message: str | None = None
    matched_pattern: str | None = None


# Critical patterns - system destruction, requires exact phrase confirmation
CRITICAL_PATTERNS: list[tuple[str, str]] = [
    (r"rm\s+-rf\s+/\s*$", "Deleting root filesystem"),
    (r"rm\s+-rf\s+/\*", "Deleting all root contents"),
    (r"rm\s+-rf\s+~", "Deleting home directory"),
    (r"mkfs\.", "Formatting filesystem"),
    (r"dd\s+if=.+of=/dev/[a-z]+\s*$", "Writing to block device"),
    (r"dd\s+if=.+of=/dev/sd[a-z]", "Writing to disk device"),
    (r">\s*/dev/sd[a-z]", "Overwriting block device"),
    (r":\(\)\{\s*:\|:&\s*\};:", "Fork bomb"),
    (r"DROP\s+DATABASE", "Dropping database"),
]

# Dangerous patterns - requires YES/NO confirmation
DANGEROUS_PATTERNS: list[tuple[str, str]] = [
    (r"rm\s+-rf", "Recursive file deletion"),
    (r"chmod\s+-R\s+777", "Opening all permissions recursively"),
    (r"chmod\s+777\s+/", "Opening permissions on system directories"),
    (r"shutdown", "System shutdown"),
    (r"reboot", "System reboot"),
    (r"init\s+[06]", "Changing runlevel"),
    (r"systemctl\s+(stop|disable)\s+(ssh|sshd|network)", "Stopping critical services"),
    (r"iptables\s+-F", "Flushing firewall rules"),
    (r"passwd\s+root", "Changing root password"),
    (r"userdel", "Deleting user"),
    (r"DROP\s+TABLE", "Dropping table"),
    (r"TRUNCATE", "Truncating table"),
    (r"chown\s+-R\s+root", "Recursive ownership change to root"),
    (r"curl\s+.+\|\s*(ba)?sh", "Pipe from URL to shell"),
    (r"wget\s+.+\|\s*(ba)?sh", "Pipe from URL to shell"),
]

# Moderate patterns - warning only, but execute
MODERATE_PATTERNS: list[tuple[str, str]] = [
    (r"apt\s+(remove|purge)", "Removing packages"),
    (r"pip\s+uninstall", "Removing Python packages"),
    (r"npm\s+uninstall\s+-g", "Removing global npm packages"),
    (r"docker\s+(rm|rmi|system\s+prune)", "Removing Docker resources"),
    (r"git\s+push\s+.*--force", "Force push to git"),
    (r"git\s+reset\s+--hard", "Hard reset in git"),
]


class SocraticGate:
    """Security gate that checks commands for dangerous patterns.

    The Socratic Gate implements a tiered security approach:
    - SAFE: Execute without any warning
    - MODERATE: Show info message and execute
    - DANGEROUS: Require YES/NO confirmation
    - CRITICAL: Require exact phrase confirmation
    """

    # Confirmation constants
    CRITICAL_CONFIRMATION_PHRASE = "CONFIRM CRITICAL OPERATION"
    CRITICAL_CONFIRMATION_PHRASE_RU = "PODTVERZHDAYU KRITICHESKUYU OPERATSIYU"

    def check(self, message: str) -> SafetyCheck:
        """Check a message for dangerous patterns.

        Args:
            message: The message/command to check.

        Returns:
            SafetyCheck with risk level and confirmation requirements.
        """
        text = message.lower()

        # Check CRITICAL patterns first (highest priority)
        for pattern, description in CRITICAL_PATTERNS:
            if re.search(pattern, message, re.IGNORECASE):
                return SafetyCheck(
                    risk_level=RiskLevel.CRITICAL,
                    requires_confirmation=True,
                    message=self._critical_message(description),
                    matched_pattern=description,
                )

        # Check DANGEROUS patterns second
        for pattern, description in DANGEROUS_PATTERNS:
            if re.search(pattern, message, re.IGNORECASE):
                return SafetyCheck(
                    risk_level=RiskLevel.DANGEROUS,
                    requires_confirmation=True,
                    message=self._dangerous_message(description),
                    matched_pattern=description,
                )

        # Check MODERATE patterns third
        for pattern, description in MODERATE_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return SafetyCheck(
                    risk_level=RiskLevel.MODERATE,
                    requires_confirmation=False,
                    message=self._moderate_message(description),
                    matched_pattern=description,
                )

        # No dangerous patterns found
        return SafetyCheck(
            risk_level=RiskLevel.SAFE,
            requires_confirmation=False,
            message=None,
            matched_pattern=None,
        )

    def _critical_message(self, description: str) -> str:
        """Generate message for critical risk operations.

        Args:
            description: Description of the detected pattern.

        Returns:
            Formatted warning message in Russian.
        """
        return f"""CRITICAL OPERATION

Detected: {description}

This operation may lead to **irreversible data loss**
or **system failure**.

To confirm, send:
`{self.CRITICAL_CONFIRMATION_PHRASE}`

Or in Russian:
`{self.CRITICAL_CONFIRMATION_PHRASE_RU}`"""

    def _dangerous_message(self, description: str) -> str:
        """Generate message for dangerous operations.

        Args:
            description: Description of the detected pattern.

        Returns:
            Formatted warning message in Russian.
        """
        return f"""DANGEROUS OPERATION

Detected: {description}

Are you sure you want to continue?

Send `YES` to confirm or `NO` to cancel."""

    def _moderate_message(self, description: str) -> str:
        """Generate info message for moderate risk operations.

        Args:
            description: Description of the detected pattern.

        Returns:
            Info message.
        """
        return f"INFO: {description} - executing..."

    def is_confirmation_valid(
        self,
        response: str,
        risk_level: RiskLevel,
    ) -> bool:
        """Check if a confirmation response is valid for the given risk level.

        Args:
            response: The user's confirmation response.
            risk_level: The risk level requiring confirmation.

        Returns:
            True if confirmation is valid, False otherwise.
        """
        response_upper = response.strip().upper()
        response_lower = response.strip().lower()

        if risk_level == RiskLevel.CRITICAL:
            # Require exact phrase (case-insensitive)
            return response_upper in (
                self.CRITICAL_CONFIRMATION_PHRASE,
                self.CRITICAL_CONFIRMATION_PHRASE_RU,
            )

        if risk_level == RiskLevel.DANGEROUS:
            # Accept common confirmation words
            return response_lower in ("yes", "y", "da", "confirm", "ok")

        return False

    def is_cancellation(self, response: str) -> bool:
        """Check if a response indicates cancellation.

        Args:
            response: The user's response.

        Returns:
            True if user wants to cancel, False otherwise.
        """
        response_lower = response.strip().lower()
        return response_lower in ("no", "n", "net", "cancel", "otmena")


# Singleton instance
socratic_gate = SocraticGate()


def is_user_allowed(user_id: int, allowed_ids: list[int]) -> bool:
    """Check if user is in the whitelist.

    Args:
        user_id: Telegram user ID
        allowed_ids: List of allowed user IDs

    Returns:
        True if user is allowed, False otherwise
    """
    return user_id in allowed_ids
