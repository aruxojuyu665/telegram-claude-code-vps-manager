"""Tests for voice transcription module."""

import builtins
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from jarvis_mk1_lite.transcription import (
    TRANSCRIPTION_ERROR_PATTERNS,
    PremiumRequiredError,
    TranscriptionError,
    TranscriptionPendingError,
    TranscriptionResult,
    VoiceTranscriber,
    _is_error_text,
    get_transcriber,
)


class TestIsErrorText:
    """Tests for _is_error_text helper function."""

    def test_empty_text_is_error(self) -> None:
        """Test that empty string is considered an error."""
        assert _is_error_text("") is True
        assert _is_error_text("   ") is False  # whitespace only, not empty after strip

    def test_valid_transcription_not_error(self) -> None:
        """Test that normal transcription text is not an error."""
        assert _is_error_text("Hello, how are you?") is False
        assert _is_error_text("This is a valid transcription.") is False
        assert _is_error_text("Hello, how are you?") is False

    def test_error_patterns_detected(self) -> None:
        """Test that known error patterns are detected."""
        # Test all patterns from TRANSCRIPTION_ERROR_PATTERNS
        for pattern in TRANSCRIPTION_ERROR_PATTERNS:
            assert _is_error_text(pattern) is True, f"Pattern '{pattern}' not detected"

    def test_error_patterns_case_insensitive(self) -> None:
        """Test that error detection is case-insensitive."""
        assert _is_error_text("ERROR DURING TRANSCRIPTION") is True
        assert _is_error_text("Error During Transcription") is True
        assert _is_error_text("error during transcription") is True

    def test_error_patterns_with_prefix_suffix(self) -> None:
        """Test error detection when pattern is part of larger text."""
        assert _is_error_text("Sorry, error during transcription occurred.") is True
        assert _is_error_text("The transcription failed due to server error.") is True

    def test_partial_matches_not_false_positive(self) -> None:
        """Test that partial matches don't cause false positives."""
        # "error" alone should not match - must be in context
        assert _is_error_text("There was an error in my reasoning.") is False
        assert _is_error_text("I failed to mention something.") is False


class TestTranscriptionResult:
    """Tests for TranscriptionResult dataclass."""

    def test_transcription_result_basic(self) -> None:
        """Test basic TranscriptionResult creation."""
        result = TranscriptionResult(
            text="Hello world",
            transcription_id=12345,
        )
        assert result.text == "Hello world"
        assert result.transcription_id == 12345
        assert result.pending is False
        assert result.trial_remains is None

    def test_transcription_result_with_all_fields(self) -> None:
        """Test TranscriptionResult with all fields."""
        result = TranscriptionResult(
            text="Test text",
            transcription_id=99999,
            pending=True,
            trial_remains=5,
        )
        assert result.text == "Test text"
        assert result.transcription_id == 99999
        assert result.pending is True
        assert result.trial_remains == 5


class TestTranscriptionExceptions:
    """Tests for transcription exception classes."""

    def test_transcription_error(self) -> None:
        """Test TranscriptionError base exception."""
        error = TranscriptionError("Test error")
        assert str(error) == "Test error"
        assert isinstance(error, Exception)

    def test_premium_required_error(self) -> None:
        """Test PremiumRequiredError exception."""
        error = PremiumRequiredError("Premium required")
        assert str(error) == "Premium required"
        assert isinstance(error, TranscriptionError)

    def test_transcription_pending_error(self) -> None:
        """Test TranscriptionPendingError exception."""
        error = TranscriptionPendingError("Still pending")
        assert str(error) == "Still pending"
        assert isinstance(error, TranscriptionError)


class TestVoiceTranscriberInit:
    """Tests for VoiceTranscriber initialization."""

    def test_init_with_defaults(self) -> None:
        """Test VoiceTranscriber initialization with default session name."""
        transcriber = VoiceTranscriber(
            api_id=12345,
            api_hash="test_hash",
            phone="+79001234567",
        )
        assert transcriber.api_id == 12345
        assert transcriber.api_hash == "test_hash"
        assert transcriber.phone == "+79001234567"
        assert transcriber.session_name == "jarvis_premium"
        assert transcriber._client is None
        assert transcriber._started is False

    def test_init_with_custom_session(self) -> None:
        """Test VoiceTranscriber initialization with custom session name."""
        transcriber = VoiceTranscriber(
            api_id=12345,
            api_hash="test_hash",
            phone="+79001234567",
            session_name="custom_session",
        )
        assert transcriber.session_name == "custom_session"

    def test_is_started_property_false(self) -> None:
        """Test is_started property when not started."""
        transcriber = VoiceTranscriber(
            api_id=12345,
            api_hash="test_hash",
            phone="+79001234567",
        )
        assert transcriber.is_started is False

    def test_is_started_property_true(self) -> None:
        """Test is_started property when started."""
        transcriber = VoiceTranscriber(
            api_id=12345,
            api_hash="test_hash",
            phone="+79001234567",
        )
        transcriber._started = True
        transcriber._client = MagicMock()
        assert transcriber.is_started is True


class TestVoiceTranscriberStart:
    """Tests for VoiceTranscriber.start() method."""

    @pytest.mark.asyncio
    async def test_start_already_started_does_nothing(self) -> None:
        """Test start logs warning when already started."""
        transcriber = VoiceTranscriber(
            api_id=12345,
            api_hash="test_hash",
            phone="+79001234567",
        )
        transcriber._started = True
        transcriber._client = MagicMock()

        # Should not raise, just return
        await transcriber.start()

        # Should still be started with same client
        assert transcriber._started is True

    @pytest.mark.asyncio
    async def test_start_success_with_mock(self) -> None:
        """Test successful start with mocked TelegramClient."""
        transcriber = VoiceTranscriber(
            api_id=12345,
            api_hash="test_hash",
            phone="+79001234567",
        )

        mock_client_class = MagicMock()
        mock_client_instance = MagicMock()
        mock_client_instance.start = AsyncMock()
        mock_client_class.return_value = mock_client_instance

        # Mock the import and class
        mock_telethon = MagicMock()
        mock_telethon.TelegramClient = mock_client_class

        with patch.dict(sys.modules, {"telethon": mock_telethon}):
            await transcriber.start()

        assert transcriber._started is True
        mock_client_instance.start.assert_called_once_with(phone="+79001234567")


class TestVoiceTranscriberStop:
    """Tests for VoiceTranscriber.stop() method."""

    @pytest.mark.asyncio
    async def test_stop_when_not_started(self) -> None:
        """Test stop when not started."""
        transcriber = VoiceTranscriber(
            api_id=12345,
            api_hash="test_hash",
            phone="+79001234567",
        )
        await transcriber.stop()
        assert transcriber._client is None
        assert transcriber._started is False

    @pytest.mark.asyncio
    async def test_stop_success(self) -> None:
        """Test successful stop."""
        transcriber = VoiceTranscriber(
            api_id=12345,
            api_hash="test_hash",
            phone="+79001234567",
        )

        mock_client = MagicMock()
        mock_client.disconnect = AsyncMock()
        transcriber._client = mock_client
        transcriber._started = True

        await transcriber.stop()

        mock_client.disconnect.assert_called_once()
        assert transcriber._client is None
        assert transcriber._started is False


class TestVoiceTranscriberTranscribe:
    """Tests for VoiceTranscriber.transcribe_voice() method."""

    @pytest.mark.asyncio
    async def test_transcribe_not_started(self) -> None:
        """Test transcribe raises error when not started."""
        transcriber = VoiceTranscriber(
            api_id=12345,
            api_hash="test_hash",
            phone="+79001234567",
        )

        with pytest.raises(TranscriptionError, match="not started"):
            await transcriber.transcribe_voice(peer=123, msg_id=456)

    @pytest.mark.asyncio
    async def test_transcribe_success_direct(self) -> None:
        """Test successful transcription with direct mock."""
        transcriber = VoiceTranscriber(
            api_id=12345,
            api_hash="test_hash",
            phone="+79001234567",
        )
        transcriber._started = True

        # Create mock result
        mock_result = MagicMock()
        mock_result.text = "Transcribed text"
        mock_result.transcription_id = 99999
        mock_result.pending = False

        # Create mock client that returns result when called
        mock_client = AsyncMock(return_value=mock_result)
        transcriber._client = mock_client

        # Mock the telethon modules in sys.modules
        mock_functions = MagicMock()
        mock_functions.messages.TranscribeAudioRequest = MagicMock()

        mock_errors = MagicMock()
        mock_errors.PremiumAccountRequiredError = Exception
        mock_errors.FloodWaitError = Exception
        mock_errors.MessageIdInvalidError = Exception

        mock_tl = MagicMock()
        mock_tl.functions = mock_functions

        mock_telethon = MagicMock()
        mock_telethon.tl = mock_tl
        mock_telethon.errors = mock_errors

        with patch.dict(
            sys.modules,
            {
                "telethon": mock_telethon,
                "telethon.tl": mock_tl,
                "telethon.tl.functions": mock_functions,
                "telethon.errors": mock_errors,
            },
        ):
            result = await transcriber.transcribe_voice(peer=123, msg_id=456)

        assert result.text == "Transcribed text"
        assert result.transcription_id == 99999
        assert result.pending is False


class TestGetTranscriber:
    """Tests for get_transcriber() function."""

    def test_get_transcriber_no_credentials(self) -> None:
        """Test get_transcriber returns None without credentials."""
        # Reset global instance
        import jarvis_mk1_lite.transcription as transcription_module

        transcription_module._transcriber = None

        result = get_transcriber()
        assert result is None

    def test_get_transcriber_partial_credentials(self) -> None:
        """Test get_transcriber returns None with partial credentials."""
        import jarvis_mk1_lite.transcription as transcription_module

        transcription_module._transcriber = None

        result = get_transcriber(api_id=12345)
        assert result is None

        result = get_transcriber(api_id=12345, api_hash="test")
        assert result is None

    def test_get_transcriber_with_credentials(self) -> None:
        """Test get_transcriber creates instance with full credentials."""
        import jarvis_mk1_lite.transcription as transcription_module

        transcription_module._transcriber = None

        result = get_transcriber(
            api_id=12345,
            api_hash="test_hash",
            phone="+79001234567",
        )
        assert result is not None
        assert isinstance(result, VoiceTranscriber)
        assert result.api_id == 12345

        # Cleanup
        transcription_module._transcriber = None

    def test_get_transcriber_returns_existing(self) -> None:
        """Test get_transcriber returns existing instance."""
        import jarvis_mk1_lite.transcription as transcription_module

        existing = VoiceTranscriber(
            api_id=99999,
            api_hash="existing_hash",
            phone="+79999999999",
        )
        transcription_module._transcriber = existing

        result = get_transcriber()
        assert result is existing

        # Cleanup
        transcription_module._transcriber = None


class TestTranscriptionResultEquality:
    """Tests for TranscriptionResult equality and representation."""

    def test_transcription_result_equality(self) -> None:
        """Test TranscriptionResult equality comparison."""
        result1 = TranscriptionResult(text="test", transcription_id=123)
        result2 = TranscriptionResult(text="test", transcription_id=123)
        result3 = TranscriptionResult(text="different", transcription_id=123)

        assert result1 == result2
        assert result1 != result3


class TestVoiceTranscriberProperties:
    """Tests for VoiceTranscriber properties (P2-TRANS-002)."""

    def test_session_file_path(self) -> None:
        """Test session_file_path property returns correct path."""
        transcriber = VoiceTranscriber(
            api_id=12345,
            api_hash="test_hash",
            phone="+79001234567",
            session_name="my_session",
        )
        path = transcriber.session_file_path
        assert path.name == "my_session.session"
        assert str(path) == "my_session.session"

    def test_session_file_path_default(self) -> None:
        """Test session_file_path with default session name."""
        transcriber = VoiceTranscriber(
            api_id=12345,
            api_hash="test_hash",
            phone="+79001234567",
        )
        path = transcriber.session_file_path
        assert path.name == "jarvis_premium.session"

    def test_session_exists_false(self) -> None:
        """Test session_exists returns False when file doesn't exist."""
        transcriber = VoiceTranscriber(
            api_id=12345,
            api_hash="test_hash",
            phone="+79001234567",
            session_name="nonexistent_session_12345",
        )
        assert transcriber.session_exists() is False

    def test_session_exists_true(self, tmp_path: "Path") -> None:
        """Test session_exists returns True when file exists."""
        from pathlib import Path

        # Create a temporary session file
        session_file = tmp_path / "temp_session.session"
        session_file.touch()

        transcriber = VoiceTranscriber(
            api_id=12345,
            api_hash="test_hash",
            phone="+79001234567",
            session_name=str(tmp_path / "temp_session"),
        )
        assert transcriber.session_exists() is True


class TestVoiceTranscriberIsAuthorized:
    """Tests for VoiceTranscriber.is_authorized() method (P2-TRANS-003)."""

    @pytest.mark.asyncio
    async def test_is_authorized_no_session(self) -> None:
        """Test is_authorized returns False when no session file."""
        transcriber = VoiceTranscriber(
            api_id=12345,
            api_hash="test_hash",
            phone="+79001234567",
            session_name="nonexistent_session_99999",
        )

        # Mock the import so it doesn't fail
        mock_telethon = MagicMock()
        with patch.dict(sys.modules, {"telethon": mock_telethon}):
            result = await transcriber.is_authorized()
        assert result is False

    @pytest.mark.asyncio
    async def test_is_authorized_import_error(self) -> None:
        """Test is_authorized raises ImportError when telethon not installed.

        Note: This test uses builtins.__import__ patching instead of sys.modules
        patching because sys.modules patching doesn't work reliably when
        telethon is already imported elsewhere in the test session.
        """
        transcriber = VoiceTranscriber(
            api_id=12345,
            api_hash="test_hash",
            phone="+79001234567",
        )

        # Use builtins patching to simulate import error
        original_import = builtins.__import__

        def mock_import(name: str, *args: object, **kwargs: object) -> object:
            if name == "telethon" or name.startswith("telethon."):
                raise ImportError("telethon is required for voice transcription")
            return original_import(name, *args, **kwargs)

        with patch.object(builtins, "__import__", side_effect=mock_import):
            with pytest.raises(ImportError, match="telethon is required"):
                await transcriber.is_authorized()


class TestVoiceTranscriberStartErrors:
    """Tests for VoiceTranscriber.start() error cases (P2-TRANS-004)."""

    @pytest.mark.asyncio
    async def test_start_import_error(self) -> None:
        """Test start raises ImportError when telethon not installed.

        Note: This test uses builtins.__import__ patching instead of sys.modules
        patching because sys.modules patching doesn't work reliably when
        telethon is already imported elsewhere in the test session.
        """
        transcriber = VoiceTranscriber(
            api_id=12345,
            api_hash="test_hash",
            phone="+79001234567",
        )

        # Use builtins patching to simulate import error
        original_import = builtins.__import__

        def mock_import(name: str, *args: object, **kwargs: object) -> object:
            if name == "telethon" or name.startswith("telethon."):
                raise ImportError("telethon is required for voice transcription")
            return original_import(name, *args, **kwargs)

        with patch.object(builtins, "__import__", side_effect=mock_import):
            with pytest.raises(ImportError, match="telethon is required"):
                await transcriber.start()


class TestVoiceTranscriberTranscribeVoiceFile:
    """Tests for VoiceTranscriber.transcribe_voice_file() method (P2-TRANS-006)."""

    @pytest.mark.asyncio
    async def test_transcribe_voice_file_not_started(self) -> None:
        """Test transcribe_voice_file raises error when not started."""
        transcriber = VoiceTranscriber(
            api_id=12345,
            api_hash="test_hash",
            phone="+79001234567",
        )

        with pytest.raises(TranscriptionError, match="not started"):
            await transcriber.transcribe_voice_file(voice_data=b"test", duration=5)

    @pytest.mark.asyncio
    async def test_transcribe_voice_file_success(self) -> None:
        """Test successful transcribe_voice_file with mocked client."""
        transcriber = VoiceTranscriber(
            api_id=12345,
            api_hash="test_hash",
            phone="+79001234567",
        )
        transcriber._started = True

        # Create mock result
        mock_result = MagicMock()
        mock_result.text = "Transcribed from file"
        mock_result.transcription_id = 11111
        mock_result.pending = False

        # Create mock sent message
        mock_sent_message = MagicMock()
        mock_sent_message.id = 999

        # Create mock client
        mock_client = AsyncMock()
        mock_client.return_value = mock_result
        mock_client.send_file = AsyncMock(return_value=mock_sent_message)
        mock_client.delete_messages = AsyncMock()
        transcriber._client = mock_client

        # Mock telethon modules
        mock_functions = MagicMock()
        mock_functions.messages.TranscribeAudioRequest = MagicMock()

        mock_types = MagicMock()
        mock_types.DocumentAttributeAudio = MagicMock()

        mock_errors = MagicMock()
        mock_errors.PremiumAccountRequiredError = Exception
        mock_errors.FloodWaitError = Exception

        mock_tl = MagicMock()
        mock_tl.functions = mock_functions
        mock_tl.types = mock_types

        mock_telethon = MagicMock()
        mock_telethon.tl = mock_tl
        mock_telethon.errors = mock_errors

        with patch.dict(
            sys.modules,
            {
                "telethon": mock_telethon,
                "telethon.tl": mock_tl,
                "telethon.tl.functions": mock_functions,
                "telethon.tl.types": mock_types,
                "telethon.errors": mock_errors,
            },
        ):
            result = await transcriber.transcribe_voice_file(
                voice_data=b"test voice data",
                duration=5,
            )

        assert result.text == "Transcribed from file"
        assert result.transcription_id == 11111
        mock_client.send_file.assert_called_once()
        mock_client.delete_messages.assert_called_once()


# ==============================================================================
# P2-TRANS-005: Poll Transcription Tests (v1.0.8)
# ==============================================================================


class TestPollTranscriptionAdvanced:
    """Advanced tests for _poll_transcription method (P2-TRANS-005)."""

    @pytest.mark.asyncio
    async def test_poll_transcription_success(self) -> None:
        """Test successful poll transcription (P2-TRANS-005a)."""
        transcriber = VoiceTranscriber(
            api_id=12345,
            api_hash="test_hash",
            phone="+79001234567",
        )
        transcriber._started = True

        # Create mock results - first pending, then complete
        mock_result_complete = MagicMock()
        mock_result_complete.text = "Completed transcription"
        mock_result_complete.transcription_id = 55555
        mock_result_complete.pending = False

        mock_client = AsyncMock(return_value=mock_result_complete)
        transcriber._client = mock_client

        mock_functions = MagicMock()
        mock_functions.messages.TranscribeAudioRequest = MagicMock()

        mock_tl = MagicMock()
        mock_tl.functions = mock_functions

        with patch.dict(
            sys.modules,
            {
                "telethon.tl": mock_tl,
                "telethon.tl.functions": mock_functions,
            },
        ):
            result = await transcriber._poll_transcription(
                peer="me",
                msg_id=123,
                transcription_id=456,
                timeout=5.0,
                poll_interval=0.1,
            )

        assert result.text == "Completed transcription"
        assert result.pending is False
        mock_client.assert_called_once()

    @pytest.mark.asyncio
    async def test_poll_transcription_multiple_polls(self) -> None:
        """Test poll transcription with multiple poll attempts (P2-TRANS-005b)."""
        transcriber = VoiceTranscriber(
            api_id=12345,
            api_hash="test_hash",
            phone="+79001234567",
        )
        transcriber._started = True

        # Create mock results - pending twice, then complete
        mock_result_pending = MagicMock()
        mock_result_pending.pending = True

        mock_result_complete = MagicMock()
        mock_result_complete.text = "Finally completed"
        mock_result_complete.transcription_id = 77777
        mock_result_complete.pending = False

        # Return pending twice, then complete
        mock_client = AsyncMock(
            side_effect=[mock_result_pending, mock_result_pending, mock_result_complete]
        )
        transcriber._client = mock_client

        mock_functions = MagicMock()
        mock_functions.messages.TranscribeAudioRequest = MagicMock()

        mock_tl = MagicMock()
        mock_tl.functions = mock_functions

        with patch.dict(
            sys.modules,
            {
                "telethon.tl": mock_tl,
                "telethon.tl.functions": mock_functions,
            },
        ):
            result = await transcriber._poll_transcription(
                peer="me",
                msg_id=123,
                transcription_id=456,
                timeout=5.0,
                poll_interval=0.1,
            )

        assert result.text == "Finally completed"
        assert result.pending is False
        assert mock_client.call_count == 3


class TestPollTranscription:
    """Tests for VoiceTranscriber._poll_transcription() method (P2-TRANS-007)."""

    @pytest.mark.asyncio
    async def test_poll_transcription_client_not_initialized(self) -> None:
        """Test _poll_transcription raises error when client is None."""
        transcriber = VoiceTranscriber(
            api_id=12345,
            api_hash="test_hash",
            phone="+79001234567",
        )
        transcriber._started = True
        transcriber._client = None

        # Mock telethon.tl.functions
        mock_functions = MagicMock()
        mock_tl = MagicMock()
        mock_tl.functions = mock_functions

        with patch.dict(
            sys.modules, {"telethon.tl": mock_tl, "telethon.tl.functions": mock_functions}
        ):
            with pytest.raises(TranscriptionError, match="Client not initialized"):
                await transcriber._poll_transcription(
                    peer="me", msg_id=123, transcription_id=456, timeout=5.0, poll_interval=0.1
                )


# Import Path for type hint
from pathlib import Path


class TestTranscribeVoiceErrors:
    """Tests for transcribe_voice error handling (P2-TRANS-005)."""

    def test_transcription_exceptions_hierarchy(self) -> None:
        """Test that exception classes are properly defined."""
        assert issubclass(PremiumRequiredError, TranscriptionError)
        assert issubclass(TranscriptionPendingError, TranscriptionError)
        assert issubclass(TranscriptionError, Exception)

    def test_exception_messages(self) -> None:
        """Test exception messages are properly set."""
        error = TranscriptionError("Test error")
        assert str(error) == "Test error"

        error = PremiumRequiredError("Premium required")
        assert "Premium required" in str(error)

        error = TranscriptionPendingError("Still pending after 30s")
        assert "pending" in str(error)

    @pytest.mark.asyncio
    async def test_transcribe_voice_not_started_error(self) -> None:
        """Test transcribe_voice raises error when not started."""
        transcriber = VoiceTranscriber(
            api_id=12345,
            api_hash="test_hash",
            phone="+79001234567",
        )
        # Don't set _started = True

        with pytest.raises(TranscriptionError, match="not started"):
            await transcriber.transcribe_voice(peer=123, msg_id=456)

    @pytest.mark.asyncio
    async def test_transcribe_voice_premium_required_error(self) -> None:
        """Test transcribe_voice raises PremiumRequiredError when Premium not available."""
        transcriber = VoiceTranscriber(
            api_id=12345,
            api_hash="test_hash",
            phone="+79001234567",
        )
        transcriber._started = True

        # Create a PremiumAccountRequiredError exception class
        class MockPremiumAccountRequiredError(Exception):
            pass

        # Create mock client that raises PremiumAccountRequiredError
        mock_client = AsyncMock(side_effect=MockPremiumAccountRequiredError("Premium required"))
        transcriber._client = mock_client

        # Mock telethon modules
        mock_functions = MagicMock()
        mock_functions.messages.TranscribeAudioRequest = MagicMock()

        mock_errors = MagicMock()
        mock_errors.PremiumAccountRequiredError = MockPremiumAccountRequiredError
        mock_errors.FloodWaitError = Exception
        mock_errors.MessageIdInvalidError = Exception

        mock_tl = MagicMock()
        mock_tl.functions = mock_functions

        with patch.dict(
            sys.modules,
            {
                "telethon": MagicMock(tl=mock_tl, errors=mock_errors),
                "telethon.tl": mock_tl,
                "telethon.tl.functions": mock_functions,
                "telethon.errors": mock_errors,
            },
        ):
            with pytest.raises(PremiumRequiredError, match="Premium"):
                await transcriber.transcribe_voice(peer=123, msg_id=456)


class TestTranscribeVoicePending:
    """Tests for transcribe_voice pending handling (P2-TRANS-005)."""

    @pytest.mark.asyncio
    async def test_transcribe_voice_with_pending_result(self) -> None:
        """Test transcribe_voice handles pending result and polls."""
        transcriber = VoiceTranscriber(
            api_id=12345,
            api_hash="test_hash",
            phone="+79001234567",
        )
        transcriber._started = True

        # Create mock results - first pending, then complete
        mock_result_pending = MagicMock()
        mock_result_pending.text = ""
        mock_result_pending.transcription_id = 99999
        mock_result_pending.pending = True

        mock_result_complete = MagicMock()
        mock_result_complete.text = "Transcribed text"
        mock_result_complete.transcription_id = 99999
        mock_result_complete.pending = False

        mock_client = AsyncMock(side_effect=[mock_result_pending, mock_result_complete])
        transcriber._client = mock_client

        mock_functions = MagicMock()
        mock_functions.messages.TranscribeAudioRequest = MagicMock()

        mock_errors = MagicMock()
        mock_errors.PremiumAccountRequiredError = Exception
        mock_errors.FloodWaitError = Exception
        mock_errors.MessageIdInvalidError = Exception

        mock_tl = MagicMock()
        mock_tl.functions = mock_functions

        with patch.dict(
            sys.modules,
            {
                "telethon": MagicMock(tl=mock_tl, errors=mock_errors),
                "telethon.tl": mock_tl,
                "telethon.tl.functions": mock_functions,
                "telethon.errors": mock_errors,
            },
        ):
            result = await transcriber.transcribe_voice(
                peer=123, msg_id=456, timeout=5.0, poll_interval=0.1
            )

        assert result.text == "Transcribed text"
        assert result.transcription_id == 99999
        assert mock_client.call_count == 2

    @pytest.mark.asyncio
    async def test_poll_transcription_timeout(self) -> None:
        """Test _poll_transcription raises TranscriptionPendingError on timeout."""
        transcriber = VoiceTranscriber(
            api_id=12345,
            api_hash="test_hash",
            phone="+79001234567",
        )
        transcriber._started = True

        # Always return pending result
        mock_result = MagicMock()
        mock_result.pending = True

        mock_client = AsyncMock(return_value=mock_result)
        transcriber._client = mock_client

        mock_functions = MagicMock()
        mock_functions.messages.TranscribeAudioRequest = MagicMock()

        mock_tl = MagicMock()
        mock_tl.functions = mock_functions

        with patch.dict(
            sys.modules,
            {
                "telethon.tl": mock_tl,
                "telethon.tl.functions": mock_functions,
            },
        ):
            with pytest.raises(TranscriptionPendingError, match="still pending"):
                await transcriber._poll_transcription(
                    peer="me",
                    msg_id=123,
                    transcription_id=456,
                    timeout=0.3,  # Very short timeout
                    poll_interval=0.1,
                )


# ==============================================================================
# P2-TRANS-004: File Transcription Tests (v1.0.8)
# ==============================================================================


class TestTranscribeVoiceFileAdvanced:
    """Advanced tests for transcribe_voice_file method (P2-TRANS-004)."""

    @pytest.mark.asyncio
    async def test_transcribe_voice_file_upload_error(self) -> None:
        """Test transcribe_voice_file handles upload error (P2-TRANS-004b)."""
        transcriber = VoiceTranscriber(
            api_id=12345,
            api_hash="test_hash",
            phone="+79001234567",
        )
        transcriber._started = True

        # Create unique exception classes to avoid isinstance matching issues
        class MockPremiumAccountRequiredError(Exception):
            pass

        class MockFloodWaitError(Exception):
            def __init__(self) -> None:
                self.seconds = 60
                super().__init__("Flood wait")

        # Mock client that fails on send_file with RuntimeError (not matching mock errors)
        mock_client = AsyncMock()
        mock_client.send_file = AsyncMock(side_effect=RuntimeError("Upload failed: network error"))
        mock_client.delete_messages = AsyncMock()
        transcriber._client = mock_client

        mock_functions = MagicMock()
        mock_types = MagicMock()
        mock_types.DocumentAttributeAudio = MagicMock()

        mock_errors = MagicMock()
        mock_errors.PremiumAccountRequiredError = MockPremiumAccountRequiredError
        mock_errors.FloodWaitError = MockFloodWaitError

        mock_tl = MagicMock()
        mock_tl.functions = mock_functions
        mock_tl.types = mock_types

        with patch.dict(
            sys.modules,
            {
                "telethon": MagicMock(tl=mock_tl, errors=mock_errors),
                "telethon.tl": mock_tl,
                "telethon.tl.functions": mock_functions,
                "telethon.tl.types": mock_types,
                "telethon.errors": mock_errors,
            },
        ):
            with pytest.raises(TranscriptionError, match="Transcription failed"):
                await transcriber.transcribe_voice_file(
                    voice_data=b"test voice data",
                    duration=5,
                )

        # Verify delete_messages was NOT called (no message was sent)
        mock_client.delete_messages.assert_not_called()

    @pytest.mark.asyncio
    async def test_transcribe_voice_file_with_pending_result(self) -> None:
        """Test transcribe_voice_file handles pending transcription (P2-TRANS-004c)."""
        transcriber = VoiceTranscriber(
            api_id=12345,
            api_hash="test_hash",
            phone="+79001234567",
        )
        transcriber._started = True

        # Create unique exception classes
        class MockPremiumAccountRequiredError(Exception):
            pass

        class MockFloodWaitError(Exception):
            def __init__(self) -> None:
                self.seconds = 60
                super().__init__("Flood wait")

        # Mock sent message
        mock_sent_message = MagicMock()
        mock_sent_message.id = 999

        # Create mock results - pending first, then complete
        mock_result_pending = MagicMock()
        mock_result_pending.text = ""
        mock_result_pending.transcription_id = 88888
        mock_result_pending.pending = True

        mock_result_complete = MagicMock()
        mock_result_complete.text = "Completed voice transcription"
        mock_result_complete.transcription_id = 88888
        mock_result_complete.pending = False

        mock_client = AsyncMock(side_effect=[mock_result_pending, mock_result_complete])
        mock_client.send_file = AsyncMock(return_value=mock_sent_message)
        mock_client.delete_messages = AsyncMock()
        transcriber._client = mock_client

        mock_functions = MagicMock()
        mock_functions.messages.TranscribeAudioRequest = MagicMock()

        mock_types = MagicMock()
        mock_types.DocumentAttributeAudio = MagicMock()

        mock_errors = MagicMock()
        mock_errors.PremiumAccountRequiredError = MockPremiumAccountRequiredError
        mock_errors.FloodWaitError = MockFloodWaitError

        mock_tl = MagicMock()
        mock_tl.functions = mock_functions
        mock_tl.types = mock_types

        with patch.dict(
            sys.modules,
            {
                "telethon": MagicMock(tl=mock_tl, errors=mock_errors),
                "telethon.tl": mock_tl,
                "telethon.tl.functions": mock_functions,
                "telethon.tl.types": mock_types,
                "telethon.errors": mock_errors,
            },
        ):
            result = await transcriber.transcribe_voice_file(
                voice_data=b"test voice data",
                duration=5,
                timeout=5.0,
                poll_interval=0.1,
            )

        assert result.text == "Completed voice transcription"
        assert result.transcription_id == 88888
        # Verify cleanup was called
        mock_client.delete_messages.assert_called_once_with("me", [999])


class TestTranscribeVoiceFileErrors:
    """Tests for transcribe_voice_file error handling (P2-TRANS-006)."""

    @pytest.mark.asyncio
    async def test_transcribe_voice_file_premium_error(self) -> None:
        """Test transcribe_voice_file handles PremiumAccountRequiredError."""
        transcriber = VoiceTranscriber(
            api_id=12345,
            api_hash="test_hash",
            phone="+79001234567",
        )
        transcriber._started = True

        class MockPremiumAccountRequiredError(Exception):
            pass

        # Mock sent message
        mock_sent_message = MagicMock()
        mock_sent_message.id = 999

        mock_client = AsyncMock()
        mock_client.send_file = AsyncMock(return_value=mock_sent_message)
        mock_client.delete_messages = AsyncMock()
        # Raise premium error on transcription call
        mock_client.side_effect = MockPremiumAccountRequiredError("Premium required")
        transcriber._client = mock_client

        mock_functions = MagicMock()
        mock_types = MagicMock()
        mock_types.DocumentAttributeAudio = MagicMock()

        mock_errors = MagicMock()
        mock_errors.PremiumAccountRequiredError = MockPremiumAccountRequiredError
        mock_errors.FloodWaitError = Exception

        mock_tl = MagicMock()
        mock_tl.functions = mock_functions
        mock_tl.types = mock_types

        with patch.dict(
            sys.modules,
            {
                "telethon": MagicMock(tl=mock_tl, errors=mock_errors),
                "telethon.tl": mock_tl,
                "telethon.tl.functions": mock_functions,
                "telethon.tl.types": mock_types,
                "telethon.errors": mock_errors,
            },
        ):
            with pytest.raises(PremiumRequiredError, match="Premium"):
                await transcriber.transcribe_voice_file(voice_data=b"test", duration=5)

    @pytest.mark.asyncio
    async def test_transcribe_voice_file_cleanup_on_error(self) -> None:
        """Test that message is deleted even on error."""
        transcriber = VoiceTranscriber(
            api_id=12345,
            api_hash="test_hash",
            phone="+79001234567",
        )
        transcriber._started = True

        # Mock sent message
        mock_sent_message = MagicMock()
        mock_sent_message.id = 999

        # Create mock client that succeeds on send_file but fails on transcription
        mock_client = AsyncMock()
        mock_client.send_file = AsyncMock(return_value=mock_sent_message)
        mock_client.delete_messages = AsyncMock()

        # Return error result
        mock_result = MagicMock()
        mock_result.text = "error during transcription"
        mock_result.transcription_id = 111
        mock_result.pending = False
        mock_client.return_value = mock_result

        transcriber._client = mock_client

        mock_functions = MagicMock()
        mock_types = MagicMock()
        mock_types.DocumentAttributeAudio = MagicMock()

        mock_errors = MagicMock()
        mock_errors.PremiumAccountRequiredError = Exception
        mock_errors.FloodWaitError = Exception

        mock_tl = MagicMock()
        mock_tl.functions = mock_functions
        mock_tl.types = mock_types

        with patch.dict(
            sys.modules,
            {
                "telethon": MagicMock(tl=mock_tl, errors=mock_errors),
                "telethon.tl": mock_tl,
                "telethon.tl.functions": mock_functions,
                "telethon.tl.types": mock_types,
                "telethon.errors": mock_errors,
            },
        ):
            with pytest.raises(TranscriptionError):
                await transcriber.transcribe_voice_file(voice_data=b"test", duration=5)

            # Verify cleanup was called
            mock_client.delete_messages.assert_called_once_with("me", [999])


class TestTranscriptionErrorPatterns:
    """Additional tests for error pattern detection (P2-TRANS-005)."""

    def test_all_error_patterns_in_list(self) -> None:
        """Test that all expected error patterns are in the list."""
        expected_patterns = [
            "error during transcription",
            "transcription failed",
            "audio is too",
            "could not transcribe",
            "unable to transcribe",
            "transcription error",
            "failed to transcribe",
        ]

        for pattern in expected_patterns:
            assert pattern in TRANSCRIPTION_ERROR_PATTERNS

    def test_error_pattern_detection_edge_cases(self) -> None:
        """Test error pattern detection edge cases."""
        # Empty string
        assert _is_error_text("") is True

        # Whitespace only
        assert _is_error_text("   ") is False

        # Very long valid text
        long_text = "This is a very long transcription that should be valid. " * 100
        assert _is_error_text(long_text) is False

        # Unicode text
        assert _is_error_text("Hello, world!") is False
        assert _is_error_text("こんにちは") is False

        # Mixed case error
        assert _is_error_text("ERROR DURING TRANSCRIPTION detected") is True


# ==============================================================================
# P2-TRANS-002: VoiceTranscriber Advanced Tests (v1.0.7)
# ==============================================================================


class TestVoiceTranscriberIsAuthorizedAdvanced:
    """Advanced tests for VoiceTranscriber.is_authorized() (P2-TRANS-002a/b)."""

    @pytest.mark.asyncio
    async def test_is_authorized_with_session_success(self, tmp_path: "Path") -> None:
        """Test is_authorized returns True when session exists and is valid."""
        # Create a temporary session file
        session_file = tmp_path / "valid_session.session"
        session_file.touch()

        transcriber = VoiceTranscriber(
            api_id=12345,
            api_hash="test_hash",
            phone="+79001234567",
            session_name=str(tmp_path / "valid_session"),
        )

        # Mock TelegramClient to return authorized
        mock_client_instance = MagicMock()
        mock_client_instance.connect = AsyncMock()
        mock_client_instance.disconnect = AsyncMock()
        mock_client_instance.is_user_authorized = AsyncMock(return_value=True)

        mock_client_class = MagicMock(return_value=mock_client_instance)

        mock_telethon = MagicMock()
        mock_telethon.TelegramClient = mock_client_class

        with patch.dict(sys.modules, {"telethon": mock_telethon}):
            result = await transcriber.is_authorized()

        assert result is True
        mock_client_instance.connect.assert_called_once()
        mock_client_instance.is_user_authorized.assert_called_once()
        mock_client_instance.disconnect.assert_called_once()

    @pytest.mark.asyncio
    async def test_is_authorized_exception_handling(self, tmp_path: "Path") -> None:
        """Test is_authorized returns False on exception (P2-TRANS-002b)."""
        # Create a temporary session file
        session_file = tmp_path / "exception_session.session"
        session_file.touch()

        transcriber = VoiceTranscriber(
            api_id=12345,
            api_hash="test_hash",
            phone="+79001234567",
            session_name=str(tmp_path / "exception_session"),
        )

        # Mock TelegramClient to raise exception
        mock_client_instance = MagicMock()
        mock_client_instance.connect = AsyncMock(side_effect=Exception("Connection failed"))

        mock_client_class = MagicMock(return_value=mock_client_instance)

        mock_telethon = MagicMock()
        mock_telethon.TelegramClient = mock_client_class

        with patch.dict(sys.modules, {"telethon": mock_telethon}):
            result = await transcriber.is_authorized()

        assert result is False

    @pytest.mark.asyncio
    async def test_is_authorized_not_authorized(self, tmp_path: "Path") -> None:
        """Test is_authorized returns False when user not authorized."""
        # Create a temporary session file
        session_file = tmp_path / "unauth_session.session"
        session_file.touch()

        transcriber = VoiceTranscriber(
            api_id=12345,
            api_hash="test_hash",
            phone="+79001234567",
            session_name=str(tmp_path / "unauth_session"),
        )

        # Mock TelegramClient to return not authorized
        mock_client_instance = MagicMock()
        mock_client_instance.connect = AsyncMock()
        mock_client_instance.disconnect = AsyncMock()
        mock_client_instance.is_user_authorized = AsyncMock(return_value=False)

        mock_client_class = MagicMock(return_value=mock_client_instance)

        mock_telethon = MagicMock()
        mock_telethon.TelegramClient = mock_client_class

        with patch.dict(sys.modules, {"telethon": mock_telethon}):
            result = await transcriber.is_authorized()

        assert result is False


class TestVoiceTranscriberStartAdvanced:
    """Advanced tests for VoiceTranscriber.start() (P2-TRANS-002c)."""

    @pytest.mark.asyncio
    async def test_start_authentication_error(self) -> None:
        """Test start raises TranscriptionError on authentication failure."""
        transcriber = VoiceTranscriber(
            api_id=12345,
            api_hash="test_hash",
            phone="+79001234567",
        )

        # Mock TelegramClient to raise on start
        mock_client_instance = MagicMock()
        mock_client_instance.start = AsyncMock(side_effect=Exception("Auth failed"))

        mock_client_class = MagicMock(return_value=mock_client_instance)

        mock_telethon = MagicMock()
        mock_telethon.TelegramClient = mock_client_class

        with patch.dict(sys.modules, {"telethon": mock_telethon}):
            with pytest.raises(TranscriptionError, match="Failed to start"):
                await transcriber.start()

        assert transcriber._started is False


class TestVoiceTranscriberStopAdvanced:
    """Advanced tests for VoiceTranscriber.stop() (P2-TRANS-002d)."""

    @pytest.mark.asyncio
    async def test_stop_disconnect_clears_state(self) -> None:
        """Test stop properly clears all state."""
        transcriber = VoiceTranscriber(
            api_id=12345,
            api_hash="test_hash",
            phone="+79001234567",
        )

        mock_client = MagicMock()
        mock_client.disconnect = AsyncMock()
        transcriber._client = mock_client
        transcriber._started = True

        await transcriber.stop()

        mock_client.disconnect.assert_called_once()
        assert transcriber._client is None
        assert transcriber._started is False
        assert transcriber.is_started is False


# ==============================================================================
# P2-TRANS-003: Transcription Methods Advanced Tests (v1.0.7)
# ==============================================================================


class TestTranscribeVoiceAdvanced:
    """Advanced tests for transcribe_voice method (P2-TRANS-003).

    Note: Due to how telethon.errors are imported inside transcribe_voice(),
    we test the generic Exception handling path instead of specific error types.
    The specific error handling is already covered by unit tests that verify
    the exception hierarchy and message formatting.
    """

    @pytest.mark.asyncio
    async def test_transcribe_voice_generic_exception_handling(self) -> None:
        """Test transcribe_voice handles generic exceptions (P2-TRANS-003b).

        This tests the fallback exception handler that catches any Exception.
        """
        transcriber = VoiceTranscriber(
            api_id=12345,
            api_hash="test_hash",
            phone="+79001234567",
        )
        transcriber._started = True

        # Create a generic exception that will be caught by the fallback handler
        mock_client = AsyncMock(side_effect=RuntimeError("Connection timeout"))
        transcriber._client = mock_client

        mock_functions = MagicMock()
        mock_functions.messages.TranscribeAudioRequest = MagicMock()

        mock_errors = MagicMock()
        mock_errors.PremiumAccountRequiredError = type(
            "PremiumAccountRequiredError", (Exception,), {}
        )
        mock_errors.FloodWaitError = type("FloodWaitError", (Exception,), {"seconds": 60})
        mock_errors.MessageIdInvalidError = type("MessageIdInvalidError", (Exception,), {})

        mock_tl = MagicMock()
        mock_tl.functions = mock_functions

        with patch.dict(
            sys.modules,
            {
                "telethon": MagicMock(tl=mock_tl, errors=mock_errors),
                "telethon.tl": mock_tl,
                "telethon.tl.functions": mock_functions,
                "telethon.errors": mock_errors,
            },
        ):
            with pytest.raises(TranscriptionError, match="Transcription failed"):
                await transcriber.transcribe_voice(peer=123, msg_id=456)

    @pytest.mark.asyncio
    async def test_transcribe_voice_exception_chaining(self) -> None:
        """Test that exceptions are properly chained (P2-TRANS-003c)."""
        transcriber = VoiceTranscriber(
            api_id=12345,
            api_hash="test_hash",
            phone="+79001234567",
        )
        transcriber._started = True

        original_error = ValueError("Original error message")
        mock_client = AsyncMock(side_effect=original_error)
        transcriber._client = mock_client

        mock_functions = MagicMock()
        mock_functions.messages.TranscribeAudioRequest = MagicMock()

        mock_errors = MagicMock()
        mock_errors.PremiumAccountRequiredError = type(
            "PremiumAccountRequiredError", (Exception,), {}
        )
        mock_errors.FloodWaitError = type("FloodWaitError", (Exception,), {"seconds": 60})
        mock_errors.MessageIdInvalidError = type("MessageIdInvalidError", (Exception,), {})

        mock_tl = MagicMock()
        mock_tl.functions = mock_functions

        with patch.dict(
            sys.modules,
            {
                "telethon": MagicMock(tl=mock_tl, errors=mock_errors),
                "telethon.tl": mock_tl,
                "telethon.tl.functions": mock_functions,
                "telethon.errors": mock_errors,
            },
        ):
            try:
                await transcriber.transcribe_voice(peer=123, msg_id=456)
            except TranscriptionError as e:
                # Verify exception chaining
                assert e.__cause__ is original_error
                assert "Original error message" in str(e)

    @pytest.mark.asyncio
    async def test_transcribe_voice_error_text_detection(self) -> None:
        """Test transcribe_voice detects error in text (P2-TRANS-003d)."""
        transcriber = VoiceTranscriber(
            api_id=12345,
            api_hash="test_hash",
            phone="+79001234567",
        )
        transcriber._started = True

        # Create mock result with error text
        mock_result = MagicMock()
        mock_result.text = "error during transcription"
        mock_result.transcription_id = 99999
        mock_result.pending = False

        mock_client = AsyncMock(return_value=mock_result)
        transcriber._client = mock_client

        mock_functions = MagicMock()
        mock_functions.messages.TranscribeAudioRequest = MagicMock()

        mock_errors = MagicMock()
        mock_errors.PremiumAccountRequiredError = type(
            "PremiumAccountRequiredError", (Exception,), {}
        )
        mock_errors.FloodWaitError = type("FloodWaitError", (Exception,), {"seconds": 60})
        mock_errors.MessageIdInvalidError = type("MessageIdInvalidError", (Exception,), {})

        mock_tl = MagicMock()
        mock_tl.functions = mock_functions

        with patch.dict(
            sys.modules,
            {
                "telethon": MagicMock(tl=mock_tl, errors=mock_errors),
                "telethon.tl": mock_tl,
                "telethon.tl.functions": mock_functions,
                "telethon.errors": mock_errors,
            },
        ):
            with pytest.raises(TranscriptionError, match="Telegram transcription error"):
                await transcriber.transcribe_voice(peer=123, msg_id=456)


# =============================================================================
# P3-TRS-001: VoiceTranscriber Lifecycle Tests (v1.0.14)
# =============================================================================


class TestVoiceTranscriberLifecycle:
    """Tests for VoiceTranscriber lifecycle management (P3-TRS-001).

    Tests init, is_authorized, start, stop with mocked Telethon client.
    """

    def test_lifecycle_init_properties(self) -> None:
        """Test VoiceTranscriber initialization sets all properties."""
        transcriber = VoiceTranscriber(
            api_id=12345,
            api_hash="test_hash_123",
            phone="+79001234567",
            session_name="test_session",
        )

        assert transcriber.api_id == 12345
        assert transcriber.api_hash == "test_hash_123"
        assert transcriber.phone == "+79001234567"
        assert transcriber.session_name == "test_session"
        assert transcriber._client is None
        assert transcriber._started is False
        assert transcriber.is_started is False

    def test_lifecycle_session_file_path(self) -> None:
        """Test session_file_path property returns correct path."""
        from pathlib import Path

        transcriber = VoiceTranscriber(
            api_id=12345,
            api_hash="test_hash",
            phone="+79001234567",
            session_name="custom_session",
        )

        expected_path = Path("custom_session.session")
        assert transcriber.session_file_path == expected_path

    def test_lifecycle_session_exists_false(self) -> None:
        """Test session_exists returns False when no session file."""
        transcriber = VoiceTranscriber(
            api_id=12345,
            api_hash="test_hash",
            phone="+79001234567",
            session_name="nonexistent_session_12345",
        )

        # Session file should not exist
        assert transcriber.session_exists() is False

    @pytest.mark.asyncio
    async def test_lifecycle_is_authorized_no_session(self) -> None:
        """Test is_authorized returns False when no session exists."""
        transcriber = VoiceTranscriber(
            api_id=12345,
            api_hash="test_hash",
            phone="+79001234567",
            session_name="nonexistent_auth_session_12345",
        )

        mock_telethon = MagicMock()
        mock_telethon.TelegramClient = MagicMock()

        # Without session file, should return False without connecting
        with patch.dict(sys.modules, {"telethon": mock_telethon}):
            with patch.object(transcriber, "session_exists", return_value=False):
                result = await transcriber.is_authorized()
                assert result is False

    @pytest.mark.asyncio
    async def test_lifecycle_is_authorized_with_mock_client(self) -> None:
        """Test is_authorized with mocked client."""
        transcriber = VoiceTranscriber(
            api_id=12345,
            api_hash="test_hash",
            phone="+79001234567",
        )

        mock_client_class = MagicMock()
        mock_client_instance = MagicMock()
        mock_client_instance.connect = AsyncMock()
        mock_client_instance.is_user_authorized = AsyncMock(return_value=True)
        mock_client_instance.disconnect = AsyncMock()
        mock_client_class.return_value = mock_client_instance

        mock_telethon = MagicMock()
        mock_telethon.TelegramClient = mock_client_class

        with patch.object(transcriber, "session_exists", return_value=True):
            with patch.dict(sys.modules, {"telethon": mock_telethon}):
                result = await transcriber.is_authorized()
                assert result is True

        mock_client_instance.connect.assert_called_once()
        mock_client_instance.is_user_authorized.assert_called_once()
        mock_client_instance.disconnect.assert_called_once()

    @pytest.mark.asyncio
    async def test_lifecycle_is_authorized_connection_error(self) -> None:
        """Test is_authorized handles connection errors gracefully."""
        transcriber = VoiceTranscriber(
            api_id=12345,
            api_hash="test_hash",
            phone="+79001234567",
        )

        mock_client_class = MagicMock()
        mock_client_instance = MagicMock()
        mock_client_instance.connect = AsyncMock(side_effect=ConnectionError("Failed"))
        mock_client_class.return_value = mock_client_instance

        mock_telethon = MagicMock()
        mock_telethon.TelegramClient = mock_client_class

        with patch.object(transcriber, "session_exists", return_value=True):
            with patch.dict(sys.modules, {"telethon": mock_telethon}):
                result = await transcriber.is_authorized()
                assert result is False

    @pytest.mark.asyncio
    async def test_lifecycle_start_already_started(self) -> None:
        """Test start does nothing when already started."""
        transcriber = VoiceTranscriber(
            api_id=12345,
            api_hash="test_hash",
            phone="+79001234567",
        )
        transcriber._started = True
        transcriber._client = MagicMock()

        # Should return early without error
        await transcriber.start()

        assert transcriber._started is True

    @pytest.mark.asyncio
    async def test_lifecycle_start_creates_client(self) -> None:
        """Test start creates and connects client."""
        transcriber = VoiceTranscriber(
            api_id=12345,
            api_hash="test_hash",
            phone="+79001234567",
        )

        mock_client_class = MagicMock()
        mock_client_instance = MagicMock()
        mock_client_instance.start = AsyncMock()
        mock_client_class.return_value = mock_client_instance

        mock_telethon = MagicMock()
        mock_telethon.TelegramClient = mock_client_class

        with patch.dict(sys.modules, {"telethon": mock_telethon}):
            await transcriber.start()

        assert transcriber._started is True
        assert transcriber._client is not None
        mock_client_instance.start.assert_called_once_with(phone="+79001234567")

    @pytest.mark.asyncio
    async def test_lifecycle_start_handles_auth_error(self) -> None:
        """Test start handles authentication errors."""
        transcriber = VoiceTranscriber(
            api_id=12345,
            api_hash="test_hash",
            phone="+79001234567",
        )

        mock_client_class = MagicMock()
        mock_client_instance = MagicMock()
        mock_client_instance.start = AsyncMock(side_effect=Exception("Authentication failed"))
        mock_client_class.return_value = mock_client_instance

        mock_telethon = MagicMock()
        mock_telethon.TelegramClient = mock_client_class

        with patch.dict(sys.modules, {"telethon": mock_telethon}):
            with pytest.raises(TranscriptionError, match="Failed to start"):
                await transcriber.start()

        assert transcriber._started is False

    @pytest.mark.asyncio
    async def test_lifecycle_stop_when_started(self) -> None:
        """Test stop disconnects client when started."""
        transcriber = VoiceTranscriber(
            api_id=12345,
            api_hash="test_hash",
            phone="+79001234567",
        )

        mock_client = MagicMock()
        mock_client.disconnect = AsyncMock()

        transcriber._started = True
        transcriber._client = mock_client

        await transcriber.stop()

        assert transcriber._started is False
        assert transcriber._client is None
        mock_client.disconnect.assert_called_once()

    @pytest.mark.asyncio
    async def test_lifecycle_stop_when_not_started(self) -> None:
        """Test stop does nothing when not started."""
        transcriber = VoiceTranscriber(
            api_id=12345,
            api_hash="test_hash",
            phone="+79001234567",
        )

        # Should not raise
        await transcriber.stop()

        assert transcriber._started is False
        assert transcriber._client is None

    @pytest.mark.asyncio
    async def test_lifecycle_stop_handles_disconnect_error(self) -> None:
        """Test stop handles disconnect errors gracefully."""
        transcriber = VoiceTranscriber(
            api_id=12345,
            api_hash="test_hash",
            phone="+79001234567",
        )

        mock_client = MagicMock()
        mock_client.disconnect = AsyncMock(side_effect=Exception("Disconnect failed"))

        transcriber._started = True
        transcriber._client = mock_client

        # Should not raise, just log
        await transcriber.stop()

        # State should still be cleaned up
        assert transcriber._started is False
        assert transcriber._client is None

    def test_lifecycle_is_started_property_logic(self) -> None:
        """Test is_started property requires both flags."""
        transcriber = VoiceTranscriber(
            api_id=12345,
            api_hash="test_hash",
            phone="+79001234567",
        )

        # Default: not started
        assert transcriber.is_started is False

        # Only _started=True: not started (no client)
        transcriber._started = True
        assert transcriber.is_started is False

        # Both set: started
        transcriber._client = MagicMock()
        assert transcriber.is_started is True

        # Only client set: not started
        transcriber._started = False
        assert transcriber.is_started is False


# =============================================================================
# P2-TRS-002: Transcription Error Handling Tests (v1.0.19)
# =============================================================================


class TestTranscriptionErrorHandling:
    """Tests for transcription error handling scenarios (P2-TRS-002).

    Covers: error text detection, exception handling, retry logic,
    timeout handling, API error responses.
    """

    def test_error_text_detection_empty(self) -> None:
        """Empty transcription should be detected as error."""
        assert _is_error_text("") is True

    def test_error_text_detection_whitespace(self) -> None:
        """Whitespace-only text should not be error (after strip check)."""
        # After strip, it's empty-ish but the function checks content
        assert _is_error_text("   ") is False  # Contains whitespace chars

    def test_error_text_detection_patterns(self) -> None:
        """Known error patterns should be detected."""
        error_texts = [
            "error during transcription",
            "transcription failed",
            "could not transcribe",
            "unable to transcribe",
            "transcription error occurred",
            "failed to transcribe audio",
        ]

        for text in error_texts:
            assert _is_error_text(text) is True, f"Should detect: {text}"

    def test_error_text_case_insensitive(self) -> None:
        """Error detection should be case-insensitive."""
        assert _is_error_text("ERROR DURING TRANSCRIPTION") is True
        assert _is_error_text("Error During Transcription") is True
        assert _is_error_text("error during transcription") is True

    def test_valid_transcription_not_error(self) -> None:
        """Valid transcription text should not be detected as error."""
        valid_texts = [
            "Hello, how are you today?",
            "This is a valid transcription of speech.",
            "Hello, how are you?",
            "Testing 123",
            "The quick brown fox jumps over the lazy dog.",
        ]

        for text in valid_texts:
            assert _is_error_text(text) is False, f"Should not detect: {text}"

    def test_transcription_error_exception(self) -> None:
        """TranscriptionError should be properly catchable."""
        with pytest.raises(TranscriptionError):
            raise TranscriptionError("Test transcription error")

    def test_premium_required_error_exception(self) -> None:
        """PremiumRequiredError should inherit from TranscriptionError."""
        with pytest.raises(TranscriptionError):
            raise PremiumRequiredError("Premium required")

        error = PremiumRequiredError("Premium required")
        assert isinstance(error, TranscriptionError)

    def test_transcription_pending_error_exception(self) -> None:
        """TranscriptionPendingError should inherit from TranscriptionError."""
        with pytest.raises(TranscriptionError):
            raise TranscriptionPendingError("Still pending")

        error = TranscriptionPendingError("Pending")
        assert isinstance(error, TranscriptionError)

    @pytest.mark.asyncio
    async def test_transcribe_raises_when_not_started(self) -> None:
        """Transcribe should raise error when transcriber not started."""
        transcriber = VoiceTranscriber(
            api_id=12345,
            api_hash="test_hash",
            phone="+79001234567",
        )

        with pytest.raises(TranscriptionError, match="not started"):
            await transcriber.transcribe_voice(peer=123, msg_id=456)

    def test_error_patterns_constant_exists(self) -> None:
        """TRANSCRIPTION_ERROR_PATTERNS should be defined."""
        assert isinstance(TRANSCRIPTION_ERROR_PATTERNS, list)
        assert len(TRANSCRIPTION_ERROR_PATTERNS) > 0

    def test_all_error_patterns_detected(self) -> None:
        """All patterns in TRANSCRIPTION_ERROR_PATTERNS should be detected."""
        for pattern in TRANSCRIPTION_ERROR_PATTERNS:
            assert _is_error_text(pattern) is True

    def test_transcription_result_with_error_text(self) -> None:
        """TranscriptionResult with error text should be identifiable."""
        result = TranscriptionResult(
            text="error during transcription",
            transcription_id=12345,
            pending=False,
        )

        assert _is_error_text(result.text) is True

    def test_transcription_result_pending_state(self) -> None:
        """Pending transcription should have pending=True."""
        result = TranscriptionResult(
            text="",
            transcription_id=12345,
            pending=True,
        )

        assert result.pending is True
        assert result.text == ""


class TestTranscriptionEdgeCases:
    """Edge case tests for transcription module (P2-TRS-002).

    Covers: session file handling, authorization checks, import errors.
    """

    def test_session_file_path_formatting(self) -> None:
        """Session file path should be properly formatted."""
        transcriber = VoiceTranscriber(
            api_id=12345,
            api_hash="test_hash",
            phone="+79001234567",
            session_name="test_session",
        )

        path = transcriber.session_file_path
        assert "test_session" in str(path)
        assert str(path).endswith(".session")

    def test_session_exists_false_default(self) -> None:
        """Session should not exist for nonexistent file."""
        transcriber = VoiceTranscriber(
            api_id=12345,
            api_hash="test_hash",
            phone="+79001234567",
            session_name="nonexistent_session_xyz123",
        )

        assert transcriber.session_exists() is False

    def test_is_started_requires_both_flags(self) -> None:
        """is_started should require both _started and _client."""
        transcriber = VoiceTranscriber(
            api_id=12345,
            api_hash="test_hash",
            phone="+79001234567",
        )

        # Default: not started
        assert transcriber.is_started is False

        # Only _started: not started
        transcriber._started = True
        assert transcriber.is_started is False

        # Both set: started
        transcriber._client = MagicMock()
        assert transcriber.is_started is True

        # Only client: not started
        transcriber._started = False
        assert transcriber.is_started is False

    @pytest.mark.asyncio
    async def test_stop_handles_disconnect_error(self) -> None:
        """Stop should handle disconnect errors gracefully."""
        transcriber = VoiceTranscriber(
            api_id=12345,
            api_hash="test_hash",
            phone="+79001234567",
        )

        mock_client = MagicMock()
        mock_client.disconnect = AsyncMock(side_effect=Exception("Disconnect failed"))

        transcriber._started = True
        transcriber._client = mock_client

        # Should not raise
        await transcriber.stop()

        # State should be cleaned up
        assert transcriber._started is False
        assert transcriber._client is None

    def test_get_transcriber_with_missing_params(self) -> None:
        """get_transcriber should return None with missing params."""
        import jarvis_mk1_lite.transcription as transcription_module

        transcription_module._transcriber = None

        # Missing all params
        result = get_transcriber()
        assert result is None

        # Missing phone
        result = get_transcriber(api_id=123, api_hash="hash")
        assert result is None

        # Missing api_hash
        result = get_transcriber(api_id=123, phone="+123")
        assert result is None

    def test_get_transcriber_returns_existing(self) -> None:
        """get_transcriber should return existing instance."""
        import jarvis_mk1_lite.transcription as transcription_module

        existing = VoiceTranscriber(
            api_id=99999,
            api_hash="existing",
            phone="+99999",
        )
        transcription_module._transcriber = existing

        result = get_transcriber()
        assert result is existing

        # Cleanup
        transcription_module._transcriber = None
