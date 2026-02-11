"""Configuration for Live E2E tests.

P0-LIVE-002, P0-LIVE-003: Bot target and environment configuration.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

__all__ = ["LiveE2EConfig", "get_config", "is_live_e2e_configured"]


@dataclass
class LiveE2EConfig:
    """Configuration for Live E2E tests using Telethon."""

    # Telethon credentials (from my.telegram.org)
    api_id: int
    api_hash: str
    phone: str

    # Session management
    session_path: Path

    # Target bot
    bot_username: str

    # Timeouts
    response_timeout: int = 30  # Seconds to wait for bot response
    between_tests_delay: float = 2.0  # Delay between tests to avoid rate limiting

    # Test behavior
    cleanup_after_test: bool = True  # Delete test messages after test

    @classmethod
    def from_env(cls) -> "LiveE2EConfig":
        """Load configuration from environment variables.

        Required environment variables:
        - LIVE_E2E_API_ID: Telegram API ID (int)
        - LIVE_E2E_API_HASH: Telegram API Hash (str)
        - LIVE_E2E_PHONE: Phone number (+7XXXXXXXXXX)

        Optional:
        - LIVE_E2E_SESSION: Session file name (default: live_e2e_session)
        - LIVE_E2E_BOT: Bot username (default: @jarvis_mk1_bot)
        - LIVE_E2E_TIMEOUT: Response timeout in seconds (default: 30)
        - LIVE_E2E_DELAY: Delay between tests in seconds (default: 2.0)

        Raises:
            ValueError: If required environment variables are missing.
        """
        api_id_str = os.getenv("LIVE_E2E_API_ID")
        api_hash = os.getenv("LIVE_E2E_API_HASH")
        phone = os.getenv("LIVE_E2E_PHONE")

        if not api_id_str:
            raise ValueError("LIVE_E2E_API_ID environment variable is required")
        if not api_hash:
            raise ValueError("LIVE_E2E_API_HASH environment variable is required")
        if not phone:
            raise ValueError("LIVE_E2E_PHONE environment variable is required")

        try:
            api_id = int(api_id_str)
        except ValueError as e:
            raise ValueError(f"LIVE_E2E_API_ID must be an integer: {e}") from e

        session_name = os.getenv("LIVE_E2E_SESSION", "live_e2e_session")
        session_path = Path(__file__).parent / session_name

        bot_username = os.getenv("LIVE_E2E_BOT", "@jarvis_mk1_bot")
        if not bot_username.startswith("@"):
            bot_username = f"@{bot_username}"

        timeout_str = os.getenv("LIVE_E2E_TIMEOUT", "30")
        delay_str = os.getenv("LIVE_E2E_DELAY", "2.0")

        return cls(
            api_id=api_id,
            api_hash=api_hash,
            phone=phone,
            session_path=session_path,
            bot_username=bot_username,
            response_timeout=int(timeout_str),
            between_tests_delay=float(delay_str),
        )

    def validate(self) -> None:
        """Validate configuration.

        Raises:
            ValueError: If configuration is invalid.
        """
        if self.api_id <= 0:
            raise ValueError("api_id must be positive")
        if len(self.api_hash) < 10:
            raise ValueError("api_hash seems too short")
        if not self.phone.startswith("+"):
            raise ValueError("phone must start with +")
        if not self.bot_username.startswith("@"):
            raise ValueError("bot_username must start with @")


def is_live_e2e_configured() -> bool:
    """Check if Live E2E environment is configured.

    Returns:
        True if all required environment variables are set.
    """
    required = ["LIVE_E2E_API_ID", "LIVE_E2E_API_HASH", "LIVE_E2E_PHONE"]
    return all(os.getenv(var) for var in required)


def get_config() -> LiveE2EConfig:
    """Get Live E2E configuration.

    Returns:
        LiveE2EConfig instance.

    Raises:
        ValueError: If configuration is missing or invalid.
    """
    config = LiveE2EConfig.from_env()
    config.validate()
    return config
