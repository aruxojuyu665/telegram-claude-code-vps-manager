"""File Sender - Send files to Telegram users.

This module provides functionality to send files from the VPS to Telegram users.
Supports single files, directories, and glob patterns.
"""

from __future__ import annotations

import asyncio
import glob
import logging
import os
import tempfile
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from aiogram.types import FSInputFile, Message

from jarvis_mk1_lite.exceptions import (
    FileAccessDeniedError,
    FileNotFoundSendError,
    FileSendError,
    FileTooLargeError,
    TelegramFileSendError,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

logger = logging.getLogger(__name__)

# Constants
MAX_FILE_SIZE_MB = 50  # Telegram limit
# More specific patterns to avoid false positives (e.g., "keyboard.py")
SENSITIVE_PATTERNS = [".env", "credentials.", "secret.", ".pem", "_key.", "key_", "password."]
MAX_FILE_REQUESTS_PER_RESPONSE = 20  # Limit to prevent DoS


@dataclass
class FileRequest:
    """Represents a file download request.

    Attributes:
        path: The file path or pattern.
        request_type: Type of request - "file", "dir", or "glob".
    """

    path: str
    request_type: str  # "file", "dir", "glob"


@dataclass
class SendResult:
    """Result of sending a file.

    Attributes:
        success: Whether the file was sent successfully.
        file_path: The path of the file.
        error: Error message if sending failed.
        was_compressed: Whether the file was compressed before sending.
    """

    success: bool
    file_path: str
    error: str | None = None
    was_compressed: bool = False


class FileSender:
    """Handles sending files to Telegram users.

    This class provides methods to send files, directories, and glob patterns
    to Telegram users. It handles validation, compression, and error handling.

    Example:
        >>> sender = FileSender()
        >>> result = await sender.send_file(message, "/path/to/file.txt")
        >>> print(result.success)
    """

    def __init__(
        self,
        max_file_size_mb: float = MAX_FILE_SIZE_MB,
        compress_large_files: bool = True,
        temp_dir: str | None = None,
    ) -> None:
        """Initialize the FileSender.

        Args:
            max_file_size_mb: Maximum file size in MB before compression.
            compress_large_files: Whether to compress files exceeding the limit.
            temp_dir: Directory for temporary files (compression).
        """
        self.max_file_size_mb = max_file_size_mb
        self.max_file_size_bytes = int(max_file_size_mb * 1024 * 1024)
        self.compress_large_files = compress_large_files
        self.temp_dir = temp_dir or tempfile.gettempdir()

    def _normalize_path(self, path: str) -> Path:
        """Normalize and resolve the file path.

        Args:
            path: The raw file path.

        Returns:
            Normalized Path object.
        """
        # Expand user home directory
        expanded = os.path.expanduser(path)
        # Resolve to absolute path
        resolved = Path(expanded).resolve()
        return resolved

    def _check_sensitive_file(self, path: Path) -> bool:
        """Check if the file matches sensitive patterns.

        Args:
            path: The file path to check.

        Returns:
            True if the file is sensitive, False otherwise.
        """
        path_str = str(path).lower()
        name = path.name.lower()

        for pattern in SENSITIVE_PATTERNS:
            if pattern in name or pattern in path_str:
                return True
        return False

    def _validate_file(self, path: Path) -> None:
        """Validate that the file exists and is accessible.

        Args:
            path: The file path to validate.

        Raises:
            FileNotFoundSendError: If the file does not exist.
            FileAccessDeniedError: If the file is not accessible.
        """
        if not path.exists():
            raise FileNotFoundSendError(str(path))

        if not path.is_file():
            raise FileNotFoundSendError(str(path), f"Not a file: {path}")

        # Check read access
        try:
            with open(path, "rb") as f:
                f.read(1)
        except PermissionError as e:
            raise FileAccessDeniedError(str(path), "permission denied") from e
        except OSError as e:
            raise FileAccessDeniedError(str(path), str(e)) from e

    def _get_file_size_mb(self, path: Path) -> float:
        """Get file size in megabytes.

        Args:
            path: The file path.

        Returns:
            File size in MB.
        """
        return path.stat().st_size / (1024 * 1024)

    def _compress_file(self, path: Path) -> tuple[Path, str]:
        """Compress a file to ZIP format.

        Args:
            path: The file path to compress.

        Returns:
            Tuple of (path to the compressed ZIP file, original filename).
        """
        original_name = path.name
        # Use UUID to prevent race conditions between concurrent requests
        unique_id = uuid.uuid4().hex[:8]
        zip_path = Path(self.temp_dir) / f"{path.stem}_{unique_id}.zip"

        # Ensure temp directory exists
        Path(self.temp_dir).mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(path, original_name)

        logger.info(
            "Compressed file %s to %s (%.1fMB -> %.1fMB)",
            path,
            zip_path,
            self._get_file_size_mb(path),
            self._get_file_size_mb(zip_path),
        )

        return zip_path, original_name

    def _compress_files(self, paths: Sequence[Path], archive_name: str) -> Path:
        """Compress multiple files to a single ZIP archive.

        Args:
            paths: List of file paths to compress.
            archive_name: Name for the archive (without extension).

        Returns:
            Path to the compressed ZIP file.
        """
        if not paths:
            raise ValueError("No files to compress")

        # Use UUID to prevent race conditions between concurrent requests
        unique_id = uuid.uuid4().hex[:8]
        zip_path = Path(self.temp_dir) / f"{archive_name}_{unique_id}.zip"

        # Ensure temp directory exists
        Path(self.temp_dir).mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for path in paths:
                if path.is_file():
                    zf.write(path, path.name)

        logger.info(
            "Compressed %d files to %s (%.1fMB)",
            len(paths),
            zip_path,
            self._get_file_size_mb(zip_path),
        )

        return zip_path

    async def send_file(
        self,
        message: Message,
        file_path: str,
        caption: str | None = None,
    ) -> SendResult:
        """Send a single file to the user.

        Args:
            message: The Telegram message to reply to.
            file_path: Path to the file to send.
            caption: Optional caption for the file.

        Returns:
            SendResult with success status and details.
        """
        path = self._normalize_path(file_path)
        original_path = str(path)
        original_name = path.name
        was_compressed = False
        temp_file: Path | None = None

        try:
            # Validate file
            self._validate_file(path)

            # Check for sensitive files
            if self._check_sensitive_file(path):
                logger.warning("Sending sensitive file: %s", path)

            # Get file size
            size_mb = self._get_file_size_mb(path)

            # Compress if needed
            if size_mb > self.max_file_size_mb:
                if self.compress_large_files:
                    temp_file, original_name = self._compress_file(path)
                    path = temp_file
                    was_compressed = True
                    size_mb = self._get_file_size_mb(path)

                    # Check if still too large after compression
                    if size_mb > self.max_file_size_mb:
                        raise FileTooLargeError(
                            original_path,
                            size_mb,
                            self.max_file_size_mb,
                            "File still too large after compression",
                        )
                else:
                    raise FileTooLargeError(original_path, size_mb, self.max_file_size_mb)

            # Create InputFile and send
            input_file = FSInputFile(path)
            # Use original filename in caption even if compressed
            if was_compressed:
                file_caption = caption or f"📦 `{original_name}` (compressed)"
            else:
                file_caption = caption or f"📄 `{original_name}`"

            await message.answer_document(
                document=input_file,
                caption=file_caption,
            )

            logger.info("Sent file %s to user %s", original_path, message.from_user.id if message.from_user else "unknown")

            return SendResult(
                success=True,
                file_path=original_path,
                was_compressed=was_compressed,
            )

        except (FileNotFoundSendError, FileTooLargeError, FileAccessDeniedError):
            raise
        except Exception as e:
            logger.exception("Failed to send file %s", file_path)
            raise TelegramFileSendError(str(path), e) from e
        finally:
            # Cleanup temp file
            if temp_file and temp_file.exists():
                try:
                    temp_file.unlink()
                except OSError:
                    pass

    async def send_files(
        self,
        message: Message,
        file_paths: Sequence[str],
        archive_if_many: bool = True,
        archive_threshold: int = 5,
    ) -> list[SendResult]:
        """Send multiple files to the user.

        Args:
            message: The Telegram message to reply to.
            file_paths: List of file paths to send.
            archive_if_many: Whether to archive if more than threshold files.
            archive_threshold: Number of files before archiving.

        Returns:
            List of SendResult for each file.
        """
        results: list[SendResult] = []
        paths = [self._normalize_path(p) for p in file_paths]

        # Filter valid files
        valid_paths: list[Path] = []
        for path in paths:
            try:
                self._validate_file(path)
                valid_paths.append(path)
            except FileSendError as e:
                results.append(SendResult(success=False, file_path=str(path), error=str(e)))

        if not valid_paths:
            return results

        # Archive if many files
        if archive_if_many and len(valid_paths) > archive_threshold:
            try:
                archive_path = self._compress_files(valid_paths, "files_archive")

                # Check archive size
                size_mb = self._get_file_size_mb(archive_path)
                if size_mb > self.max_file_size_mb:
                    raise FileTooLargeError(
                        str(archive_path),
                        size_mb,
                        self.max_file_size_mb,
                        f"Archive of {len(valid_paths)} files too large",
                    )

                input_file = FSInputFile(archive_path)
                await message.answer_document(
                    document=input_file,
                    caption=f"📦 Archive of {len(valid_paths)} files",
                )

                # Cleanup
                archive_path.unlink(missing_ok=True)

                for path in valid_paths:
                    results.append(SendResult(success=True, file_path=str(path), was_compressed=True))

                return results

            except Exception as e:
                logger.warning("Failed to create archive, sending individually: %s", e)

        # Send files individually
        for path in valid_paths:
            try:
                result = await self.send_file(message, str(path))
                results.append(result)
                # Small delay to avoid rate limiting
                await asyncio.sleep(0.5)
            except FileSendError as e:
                results.append(SendResult(success=False, file_path=str(path), error=str(e)))

        return results

    async def send_directory(
        self,
        message: Message,
        dir_path: str,
        pattern: str = "*",
    ) -> list[SendResult]:
        """Send all files from a directory.

        Args:
            message: The Telegram message to reply to.
            dir_path: Path to the directory.
            pattern: Glob pattern for filtering files (default: all files).

        Returns:
            List of SendResult for each file.
        """
        path = self._normalize_path(dir_path)

        if not path.exists():
            raise FileNotFoundSendError(str(path), "Directory not found")

        if not path.is_dir():
            raise FileNotFoundSendError(str(path), "Not a directory")

        # Get all matching files
        file_paths = list(path.glob(pattern))
        file_paths = [p for p in file_paths if p.is_file()]

        if not file_paths:
            await message.answer(f"No files found in directory: {path}")
            return []

        # Notify user about file count
        await message.answer(f"📁 Found {len(file_paths)} files in `{path.name}`")

        return await self.send_files(message, [str(p) for p in file_paths])

    async def send_glob(
        self,
        message: Message,
        pattern: str,
    ) -> list[SendResult]:
        """Send files matching a glob pattern.

        Args:
            message: The Telegram message to reply to.
            pattern: Glob pattern (e.g., "/path/*.py").

        Returns:
            List of SendResult for each file.
        """
        # Expand glob pattern
        file_paths = glob.glob(pattern, recursive=True)
        file_paths = [p for p in file_paths if os.path.isfile(p)]

        if not file_paths:
            await message.answer(f"No files found matching pattern: `{pattern}`")
            return []

        # Notify user about file count
        await message.answer(f"🔍 Found {len(file_paths)} files matching `{pattern}`")

        return await self.send_files(message, file_paths)

    async def process_file_requests(
        self,
        message: Message,
        requests: Sequence[FileRequest],
    ) -> list[SendResult]:
        """Process multiple file requests of different types.

        Args:
            message: The Telegram message to reply to.
            requests: List of FileRequest objects.

        Returns:
            List of SendResult for all files.
        """
        all_results: list[SendResult] = []

        for request in requests:
            try:
                if request.request_type == "file":
                    result = await self.send_file(message, request.path)
                    all_results.append(result)
                elif request.request_type == "dir":
                    results = await self.send_directory(message, request.path)
                    all_results.extend(results)
                elif request.request_type == "glob":
                    results = await self.send_glob(message, request.path)
                    all_results.extend(results)
                else:
                    logger.warning("Unknown request type: %s", request.request_type)

                # Small delay between requests
                await asyncio.sleep(0.3)

            except FileSendError as e:
                all_results.append(SendResult(success=False, file_path=request.path, error=str(e)))
                await message.answer(f"❌ Error: {e.message}")

        return all_results
