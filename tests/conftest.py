"""Pytest configuration and shared fixtures.

This module provides mock infrastructure for testing, especially for telethon.
"""

import sys
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock

import pytest


# ==============================================================================
# P2-TRANS-001: Mock Telethon Infrastructure
# ==============================================================================


class MockFloodWaitError(Exception):
    """Mock FloodWaitError from telethon.errors."""

    def __init__(self, seconds: int = 60) -> None:
        self.seconds = seconds
        super().__init__(f"A wait of {seconds} seconds is required")


class MockPremiumAccountRequiredError(Exception):
    """Mock PremiumAccountRequiredError from telethon.errors."""

    pass


class MockMessageIdInvalidError(Exception):
    """Mock MessageIdInvalidError from telethon.errors."""

    pass


class MockTranscribeAudioRequest:
    """Mock TranscribeAudioRequest from telethon.tl.functions.messages."""

    def __init__(self, peer: Any, msg_id: int) -> None:
        self.peer = peer
        self.msg_id = msg_id


class MockDocumentAttributeAudio:
    """Mock DocumentAttributeAudio from telethon.tl.types."""

    def __init__(
        self,
        duration: int = 0,
        voice: bool = False,
        title: str | None = None,
        performer: str | None = None,
    ) -> None:
        self.duration = duration
        self.voice = voice
        self.title = title
        self.performer = performer


class MockTelegramClient:
    """Mock TelegramClient for testing."""

    def __init__(
        self,
        session: str,
        api_id: int,
        api_hash: str,
    ) -> None:
        self.session = session
        self.api_id = api_id
        self.api_hash = api_hash
        self._connected = False
        self._authorized = True

    async def connect(self) -> None:
        """Mock connect method."""
        self._connected = True

    async def disconnect(self) -> None:
        """Mock disconnect method."""
        self._connected = False

    async def is_user_authorized(self) -> bool:
        """Mock is_user_authorized method."""
        return self._authorized

    async def start(self, phone: str) -> None:
        """Mock start method."""
        self._connected = True

    async def send_file(
        self,
        entity: Any,
        file: Any,
        **kwargs: Any,
    ) -> MagicMock:
        """Mock send_file method."""
        mock_message = MagicMock()
        mock_message.id = 12345
        return mock_message

    async def delete_messages(
        self,
        entity: Any,
        message_ids: list[int],
    ) -> None:
        """Mock delete_messages method."""
        pass

    async def __call__(self, request: Any) -> MagicMock:
        """Mock call method for API requests."""
        result = MagicMock()
        result.text = "Mock transcription result"
        result.transcription_id = 99999
        result.pending = False
        result.trial_remains_num = None
        return result


def create_mock_telethon_modules() -> Dict[str, MagicMock]:
    """Create mock telethon module hierarchy.

    Returns:
        Dict with mock modules ready to be patched into sys.modules.
    """
    # Create mock modules
    mock_telethon = MagicMock()
    mock_tl = MagicMock()
    mock_functions = MagicMock()
    mock_messages = MagicMock()
    mock_types = MagicMock()
    mock_errors = MagicMock()

    # Set up TelegramClient
    mock_telethon.TelegramClient = MockTelegramClient

    # Set up functions.messages
    mock_messages.TranscribeAudioRequest = MockTranscribeAudioRequest
    mock_functions.messages = mock_messages

    # Set up types
    mock_types.DocumentAttributeAudio = MockDocumentAttributeAudio

    # Set up errors
    mock_errors.FloodWaitError = MockFloodWaitError
    mock_errors.PremiumAccountRequiredError = MockPremiumAccountRequiredError
    mock_errors.MessageIdInvalidError = MockMessageIdInvalidError

    # Connect hierarchy
    mock_tl.functions = mock_functions
    mock_tl.types = mock_types
    mock_telethon.tl = mock_tl
    mock_telethon.errors = mock_errors

    return {
        "telethon": mock_telethon,
        "telethon.tl": mock_tl,
        "telethon.tl.functions": mock_functions,
        "telethon.tl.functions.messages": mock_messages,
        "telethon.tl.types": mock_types,
        "telethon.errors": mock_errors,
    }


@pytest.fixture
def mock_telethon_modules() -> Dict[str, MagicMock]:
    """Fixture providing mock telethon modules.

    Returns:
        Dict with mock modules for use with patch.dict(sys.modules, ...).
    """
    return create_mock_telethon_modules()


@pytest.fixture
def mock_telegram_client() -> MockTelegramClient:
    """Fixture providing a mock TelegramClient instance.

    Returns:
        MockTelegramClient instance.
    """
    return MockTelegramClient(
        session="test_session",
        api_id=12345,
        api_hash="test_hash",
    )


@pytest.fixture
def mock_transcription_result() -> MagicMock:
    """Fixture providing a mock transcription result.

    Returns:
        MagicMock configured as transcription result.
    """
    result = MagicMock()
    result.text = "Mock transcribed text"
    result.transcription_id = 99999
    result.pending = False
    result.trial_remains_num = None
    return result


@pytest.fixture
def mock_pending_transcription_result() -> MagicMock:
    """Fixture providing a mock pending transcription result.

    Returns:
        MagicMock configured as pending transcription result.
    """
    result = MagicMock()
    result.text = ""
    result.transcription_id = 88888
    result.pending = True
    result.trial_remains_num = 5
    return result


# ==============================================================================
# Common Test Fixtures
# ==============================================================================


@pytest.fixture
def sample_voice_bytes() -> bytes:
    """Fixture providing sample voice message bytes.

    Returns:
        Sample bytes representing voice data.
    """
    return b"\x00\x01\x02\x03" * 100  # 400 bytes of sample data


@pytest.fixture
def sample_text_content() -> str:
    """Fixture providing sample text content.

    Returns:
        Sample text string.
    """
    return "This is sample text content for testing."


# ==============================================================================
# Async Test Helpers
# ==============================================================================


@pytest.fixture
def async_mock() -> AsyncMock:
    """Fixture providing a generic AsyncMock.

    Returns:
        AsyncMock instance.
    """
    return AsyncMock()
