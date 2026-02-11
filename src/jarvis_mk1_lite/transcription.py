"""Voice transcription module using Telethon and Telegram Premium.

This module provides voice message transcription via Telegram's built-in
TranscribeAudio API, which requires a Telegram Premium account.

Architecture:
    User Voice -> Aiogram Bot -> Telethon (Premium) -> TranscribeAudio API -> Text

Note:
    Bot API (aiogram) does not support messages.transcribeAudio.
    Only MTProto API (Telethon) with Premium account has access.
"""

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from telethon import TelegramClient  # type: ignore[import-untyped]

logger = logging.getLogger(__name__)

# Error patterns that Telegram may return in transcription text instead of raising exception
TRANSCRIPTION_ERROR_PATTERNS = [
    "error during transcription",
    "transcription failed",
    "audio is too",
    "could not transcribe",
    "unable to transcribe",
    "transcription error",
    "failed to transcribe",
]


def _is_error_text(text: str) -> bool:
    """Check if transcription result text is actually an error message.

    Telegram sometimes returns error messages in the text field instead of
    raising a proper exception. This function detects such cases.

    Args:
        text: The transcription result text to check.

    Returns:
        True if the text appears to be an error message.
    """
    if not text:
        return True  # Empty text is an error

    text_lower = text.lower().strip()
    return any(pattern in text_lower for pattern in TRANSCRIPTION_ERROR_PATTERNS)


class TranscriptionError(Exception):
    """Base exception for transcription errors."""

    pass


class PremiumRequiredError(TranscriptionError):
    """Raised when Telegram Premium is required but not available."""

    pass


class TranscriptionPendingError(TranscriptionError):
    """Raised when transcription is still pending after timeout."""

    pass


@dataclass
class TranscriptionResult:
    """Result of voice transcription.

    Attributes:
        text: Transcribed text from voice message.
        transcription_id: Unique ID assigned by Telegram.
        pending: Whether transcription is still processing.
        trial_remains: Number of trial transcriptions remaining (for non-Premium).
    """

    text: str
    transcription_id: int
    pending: bool = False
    trial_remains: int | None = None


class VoiceTranscriber:
    """Voice message transcriber using Telegram Premium API.

    This class handles voice transcription via Telethon's MTProto API.
    Requires a Telegram Premium account for unlimited transcriptions.

    Example:
        transcriber = VoiceTranscriber(api_id, api_hash, phone, "session")
        await transcriber.start()
        result = await transcriber.transcribe_voice(peer_id, msg_id)
        print(result.text)
    """

    def __init__(
        self,
        api_id: int,
        api_hash: str,
        phone: str,
        session_name: str = "jarvis_premium",
    ) -> None:
        """Initialize VoiceTranscriber.

        Args:
            api_id: Telegram API ID from my.telegram.org.
            api_hash: Telegram API hash from my.telegram.org.
            phone: Phone number with country code (e.g., +79001234567).
            session_name: Name for the session file.
        """
        self.api_id = api_id
        self.api_hash = api_hash
        self.phone = phone
        self.session_name = session_name
        self._client: TelegramClient | None = None
        self._started = False

    @property
    def is_started(self) -> bool:
        """Check if transcriber is started and connected."""
        return self._started and self._client is not None

    @property
    def session_file_path(self) -> Path:
        """Get the path to the session file."""
        return Path(f"{self.session_name}.session")

    def session_exists(self) -> bool:
        """Check if the session file exists.

        Returns:
            True if session file exists, False otherwise.
        """
        return self.session_file_path.exists()

    async def is_authorized(self) -> bool:
        """Check if the Telethon client is authorized.

        This connects to Telegram and checks if the session is valid.

        Returns:
            True if authorized, False otherwise.

        Raises:
            ImportError: If telethon is not installed.
        """
        try:
            from telethon import TelegramClient
        except ImportError as e:
            raise ImportError(
                "telethon is required for voice transcription. "
                "Install it with: pip install telethon"
            ) from e

        if not self.session_exists():
            return False

        client = TelegramClient(self.session_name, self.api_id, self.api_hash)
        try:
            await client.connect()
            authorized = await client.is_user_authorized()
            await client.disconnect()
            return bool(authorized)
        except Exception as e:
            logger.warning(f"Failed to check authorization: {e}")
            return False

    async def start(self) -> None:
        """Start the Telethon client and authenticate.

        First-time authentication requires interactive code input.
        Subsequent starts use the saved session file.

        Raises:
            ImportError: If telethon is not installed.
            TranscriptionError: If authentication fails.
        """
        if self._started:
            logger.warning("Transcriber already started")
            return

        try:
            from telethon import TelegramClient
        except ImportError as e:
            raise ImportError(
                "telethon is required for voice transcription. "
                "Install it with: pip install telethon"
            ) from e

        self._client = TelegramClient(self.session_name, self.api_id, self.api_hash)

        try:
            await self._client.start(phone=self.phone)
            self._started = True
            logger.info("VoiceTranscriber started successfully")
        except Exception as e:
            logger.error(f"Failed to start VoiceTranscriber: {e}")
            raise TranscriptionError(f"Failed to start: {e}") from e

    async def stop(self) -> None:
        """Stop the Telethon client and disconnect.

        Handles disconnect errors gracefully to ensure cleanup.
        """
        if self._client:
            try:
                await self._client.disconnect()
            except Exception as e:
                logger.warning(f"Error during disconnect: {e}")
            finally:
                self._client = None
                self._started = False
                logger.info("VoiceTranscriber stopped")

    async def transcribe_voice(
        self,
        peer: int | str,
        msg_id: int,
        timeout: float = 30.0,
        poll_interval: float = 1.0,
    ) -> TranscriptionResult:
        """Transcribe a voice message using Telegram Premium API.

        Args:
            peer: Chat/user ID or username where the voice message is.
            msg_id: Message ID of the voice message.
            timeout: Maximum time to wait for transcription (seconds).
            poll_interval: Interval between polling for pending results.

        Returns:
            TranscriptionResult with transcribed text.

        Raises:
            TranscriptionError: If transcriber is not started.
            PremiumRequiredError: If Premium subscription is required.
            TranscriptionPendingError: If transcription times out.
        """
        if not self._client or not self._started:
            raise TranscriptionError("Transcriber not started. Call start() first.")

        try:
            from telethon.errors import (  # type: ignore[import-untyped]
                FloodWaitError,
                MessageIdInvalidError,
                PremiumAccountRequiredError,
            )
            from telethon.tl import functions  # type: ignore[import-untyped]
        except ImportError as e:
            raise ImportError("telethon is required for voice transcription.") from e

        try:
            result = await self._client(
                functions.messages.TranscribeAudioRequest(peer=peer, msg_id=msg_id)
            )

            # Handle pending transcription with polling
            if result.pending:
                logger.info(f"Transcription pending for msg_id={msg_id}, polling...")
                result = await self._poll_transcription(
                    peer, msg_id, result.transcription_id, timeout, poll_interval
                )

            # Validate transcription result - Telegram sometimes returns error in text field
            if _is_error_text(result.text):
                logger.warning(
                    f"Transcription returned error text: {result.text}",
                    extra={"msg_id": msg_id, "transcription_id": result.transcription_id},
                )
                raise TranscriptionError(f"Telegram transcription error: {result.text}")

            return TranscriptionResult(
                text=result.text,
                transcription_id=result.transcription_id,
                pending=result.pending,
                trial_remains=getattr(result, "trial_remains_num", None),
            )

        except PremiumAccountRequiredError as e:
            logger.error("Telegram Premium required for transcription")
            raise PremiumRequiredError(
                "Telegram Premium subscription required for voice transcription"
            ) from e
        except FloodWaitError as e:
            logger.warning(f"FloodWait: need to wait {e.seconds} seconds")
            raise TranscriptionError(f"Rate limited. Please wait {e.seconds} seconds.") from e
        except MessageIdInvalidError as e:
            logger.error(f"Invalid message ID: {msg_id}")
            raise TranscriptionError(f"Invalid message ID: {msg_id}") from e
        except Exception as e:
            logger.error(f"Transcription failed: {e}")
            raise TranscriptionError(f"Transcription failed: {e}") from e

    async def transcribe_voice_file(
        self,
        voice_data: bytes,
        duration: int = 0,
        timeout: float = 30.0,
        poll_interval: float = 1.0,
    ) -> TranscriptionResult:
        """Transcribe a voice file by uploading to Saved Messages.

        This method uploads the voice file to the Telethon user's Saved Messages,
        transcribes it, and then deletes the message.

        Args:
            voice_data: Raw voice file bytes (OGG format).
            duration: Duration of the voice message in seconds.
            timeout: Maximum time to wait for transcription (seconds).
            poll_interval: Interval between polling for pending results.

        Returns:
            TranscriptionResult with transcribed text.

        Raises:
            TranscriptionError: If transcriber is not started or upload fails.
            PremiumRequiredError: If Premium subscription is required.
            TranscriptionPendingError: If transcription times out.
        """
        if not self._client or not self._started:
            raise TranscriptionError("Transcriber not started. Call start() first.")

        try:
            from telethon.errors import (
                FloodWaitError,
                PremiumAccountRequiredError,
            )
            from telethon.tl import functions, types
        except ImportError as e:
            raise ImportError("telethon is required for voice transcription.") from e

        sent_message = None
        try:
            # Create proper voice attributes for Telegram to recognize it as voice
            voice_attrs = [
                types.DocumentAttributeAudio(
                    duration=duration,
                    voice=True,  # Critical: marks as voice message
                )
            ]

            # Upload voice file to Saved Messages ("me")
            logger.info(
                f"Uploading voice file ({len(voice_data)} bytes, {duration}s) to Saved Messages..."
            )
            sent_message = await self._client.send_file(
                "me",  # Saved Messages
                voice_data,
                attributes=voice_attrs,
                voice_note=True,  # Additional flag for voice note
                mime_type="audio/ogg",  # Required for Telegram to recognize as voice
            )
            logger.info(f"Voice file uploaded, msg_id={sent_message.id}")

            # Transcribe from Saved Messages
            result = await self._client(
                functions.messages.TranscribeAudioRequest(
                    peer="me",
                    msg_id=sent_message.id,
                )
            )

            # Handle pending transcription with polling
            if result.pending:
                logger.info("Transcription pending, polling...")
                result = await self._poll_transcription(
                    "me", sent_message.id, result.transcription_id, timeout, poll_interval
                )

            # Validate transcription result - Telegram sometimes returns error in text field
            if _is_error_text(result.text):
                logger.warning(
                    f"Transcription returned error text: {result.text}",
                    extra={"transcription_id": result.transcription_id},
                )
                raise TranscriptionError(f"Telegram transcription error: {result.text}")

            return TranscriptionResult(
                text=result.text,
                transcription_id=result.transcription_id,
                pending=result.pending,
                trial_remains=getattr(result, "trial_remains_num", None),
            )

        except PremiumAccountRequiredError as e:
            logger.error("Telegram Premium required for transcription")
            raise PremiumRequiredError(
                "Telegram Premium subscription required for voice transcription"
            ) from e
        except FloodWaitError as e:
            logger.warning(f"FloodWait: need to wait {e.seconds} seconds")
            raise TranscriptionError(f"Rate limited. Please wait {e.seconds} seconds.") from e
        except Exception as e:
            logger.error(f"Transcription failed: {e}")
            raise TranscriptionError(f"Transcription failed: {e}") from e
        finally:
            # Clean up: delete the uploaded message from Saved Messages
            if sent_message is not None:
                try:
                    await self._client.delete_messages("me", [sent_message.id])
                    logger.debug(f"Deleted temp voice message {sent_message.id}")
                except Exception as e:
                    logger.warning(f"Failed to delete temp message: {e}")

    async def _poll_transcription(
        self,
        peer: int | str,
        msg_id: int,
        transcription_id: int,
        timeout: float,
        poll_interval: float,
    ) -> Any:
        """Poll for pending transcription result.

        Args:
            peer: Chat/user ID where the voice message is.
            msg_id: Message ID of the voice message.
            transcription_id: Transcription ID from initial request.
            timeout: Maximum polling time.
            poll_interval: Time between polls.

        Returns:
            Raw Telethon TranscribedAudio result.

        Raises:
            TranscriptionPendingError: If transcription doesn't complete in time.
            TranscriptionError: If client is not initialized.
        """
        from telethon.tl import functions

        if self._client is None:
            raise TranscriptionError("Client not initialized")

        start_time = asyncio.get_running_loop().time()

        while True:
            elapsed = asyncio.get_running_loop().time() - start_time
            if elapsed >= timeout:
                raise TranscriptionPendingError(
                    f"Transcription still pending after {timeout}s timeout"
                )

            await asyncio.sleep(poll_interval)

            result = await self._client(
                functions.messages.TranscribeAudioRequest(peer=peer, msg_id=msg_id)
            )

            if not result.pending:
                return result

            logger.debug(
                f"Still pending... elapsed={elapsed:.1f}s, " f"transcription_id={transcription_id}"
            )


# Global transcriber instance (lazy loaded)
_transcriber: VoiceTranscriber | None = None


def get_transcriber(
    api_id: int | None = None,
    api_hash: str | None = None,
    phone: str | None = None,
    session_name: str = "jarvis_premium",
) -> VoiceTranscriber | None:
    """Get or create the global VoiceTranscriber instance.

    Args:
        api_id: Telegram API ID (required for first call).
        api_hash: Telegram API hash (required for first call).
        phone: Phone number (required for first call).
        session_name: Session file name.

    Returns:
        VoiceTranscriber instance or None if credentials not provided.
    """
    global _transcriber

    if _transcriber is not None:
        return _transcriber

    if api_id is None or api_hash is None or phone is None:
        return None

    _transcriber = VoiceTranscriber(api_id, api_hash, phone, session_name)
    return _transcriber
