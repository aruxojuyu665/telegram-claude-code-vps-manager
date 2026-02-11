"""Unit tests for file_sender module.

Tests FileSender class for sending files to Telegram users.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from jarvis_mk1_lite.exceptions import (
    FileAccessDeniedError,
    FileNotFoundSendError,
    FileTooLargeError,
)
from jarvis_mk1_lite.file_sender import (
    FileRequest,
    FileSender,
    SendResult,
)


class TestFileSenderValidation:
    """Tests for file validation."""

    def test_normalize_path_absolute(self) -> None:
        """Test path normalization for absolute paths."""
        sender = FileSender()
        path = sender._normalize_path("/tmp/test.txt")
        assert path.is_absolute()

    def test_normalize_path_with_user_home(self) -> None:
        """Test path normalization expands user home."""
        sender = FileSender()
        path = sender._normalize_path("~/test.txt")
        assert path.is_absolute()
        assert "~" not in str(path)

    def test_validate_existing_file(self) -> None:
        """Test validation passes for existing file."""
        sender = FileSender()

        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"test content")
            temp_path = Path(f.name)

        try:
            # Should not raise
            sender._validate_file(temp_path)
        finally:
            temp_path.unlink()

    def test_validate_nonexistent_file_raises(self) -> None:
        """Test validation raises for non-existent file."""
        sender = FileSender()

        with pytest.raises(FileNotFoundSendError):
            sender._validate_file(Path("/nonexistent/path/file.txt"))

    def test_validate_directory_raises(self) -> None:
        """Test validation raises for directory instead of file."""
        sender = FileSender()

        with tempfile.TemporaryDirectory() as temp_dir:
            with pytest.raises(FileNotFoundSendError) as exc_info:
                sender._validate_file(Path(temp_dir))
            assert "Not a file" in str(exc_info.value)

    def test_check_sensitive_file_env(self) -> None:
        """Test sensitive file detection for .env."""
        sender = FileSender()
        assert sender._check_sensitive_file(Path("/app/.env"))
        assert sender._check_sensitive_file(Path("/app/.env.local"))

    def test_check_sensitive_file_credentials(self) -> None:
        """Test sensitive file detection for credentials."""
        sender = FileSender()
        assert sender._check_sensitive_file(Path("/app/credentials.json"))
        assert sender._check_sensitive_file(Path("/app/secret.txt"))

    def test_check_sensitive_file_key(self) -> None:
        """Test sensitive file detection for key files."""
        sender = FileSender()
        assert sender._check_sensitive_file(Path("/app/private_key.pem"))
        assert sender._check_sensitive_file(Path("/app/api_key.txt"))

    def test_check_non_sensitive_file(self) -> None:
        """Test non-sensitive file is not flagged."""
        sender = FileSender()
        assert not sender._check_sensitive_file(Path("/app/config.yaml"))
        assert not sender._check_sensitive_file(Path("/app/readme.md"))


class TestFileSenderSize:
    """Tests for file size handling."""

    def test_get_file_size_mb(self) -> None:
        """Test file size calculation."""
        sender = FileSender()

        with tempfile.NamedTemporaryFile(delete=False) as f:
            # Write 1MB of data
            f.write(b"x" * (1024 * 1024))
            temp_path = Path(f.name)

        try:
            size = sender._get_file_size_mb(temp_path)
            assert 0.99 < size < 1.01  # ~1 MB
        finally:
            temp_path.unlink()

    def test_compress_file(self) -> None:
        """Test file compression creates smaller file."""
        sender = FileSender()

        with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as f:
            # Write compressible content
            f.write(b"a" * (1024 * 100))  # 100KB of 'a's
            temp_path = Path(f.name)

        try:
            zip_path, original_name = sender._compress_file(temp_path)
            assert zip_path.exists()
            assert zip_path.suffix == ".zip"
            # ZIP should be smaller (or at least exist)
            assert zip_path.stat().st_size > 0
            # Original name should be preserved
            assert original_name == temp_path.name
            zip_path.unlink()
        finally:
            temp_path.unlink()


class TestFileSenderSend:
    """Tests for file sending."""

    @pytest.fixture
    def mock_message(self) -> MagicMock:
        """Create a mock Telegram message."""
        message = MagicMock()
        message.answer_document = AsyncMock()
        message.answer = AsyncMock()
        message.from_user = MagicMock()
        message.from_user.id = 123456
        return message

    @pytest.mark.asyncio
    async def test_send_file_success(self, mock_message: MagicMock) -> None:
        """Test successful file send."""
        sender = FileSender()

        with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as f:
            f.write(b"test content")
            temp_path = f.name

        try:
            result = await sender.send_file(mock_message, temp_path)

            assert result.success
            assert result.file_path == temp_path
            assert not result.was_compressed
            mock_message.answer_document.assert_called_once()
        finally:
            Path(temp_path).unlink()

    @pytest.mark.asyncio
    async def test_send_file_with_caption(self, mock_message: MagicMock) -> None:
        """Test file send with custom caption."""
        sender = FileSender()

        with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as f:
            f.write(b"test content")
            temp_path = f.name

        try:
            await sender.send_file(mock_message, temp_path, caption="Custom caption")

            call_kwargs = mock_message.answer_document.call_args[1]
            assert call_kwargs["caption"] == "Custom caption"
        finally:
            Path(temp_path).unlink()

    @pytest.mark.asyncio
    async def test_send_file_not_found(self, mock_message: MagicMock) -> None:
        """Test error handling for non-existent file."""
        sender = FileSender()

        with pytest.raises(FileNotFoundSendError):
            await sender.send_file(mock_message, "/nonexistent/file.txt")

    @pytest.mark.asyncio
    async def test_send_multiple_files(self, mock_message: MagicMock) -> None:
        """Test sending multiple files."""
        sender = FileSender()

        temp_files = []
        try:
            for i in range(3):
                with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as f:
                    f.write(f"content {i}".encode())
                    temp_files.append(f.name)

            results = await sender.send_files(
                mock_message,
                temp_files,
                archive_if_many=False,
            )

            assert len(results) == 3
            assert all(r.success for r in results)
            assert mock_message.answer_document.call_count == 3
        finally:
            for path in temp_files:
                Path(path).unlink()

    @pytest.mark.asyncio
    async def test_send_files_archive_many(self, mock_message: MagicMock) -> None:
        """Test that many files are archived."""
        sender = FileSender()

        temp_files = []
        try:
            for i in range(6):  # More than threshold of 5
                with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as f:
                    f.write(f"content {i}".encode())
                    temp_files.append(f.name)

            results = await sender.send_files(
                mock_message,
                temp_files,
                archive_if_many=True,
                archive_threshold=5,
            )

            assert len(results) == 6
            # All should be marked as compressed (archived)
            assert all(r.was_compressed for r in results)
            # Should have sent only 1 archive
            mock_message.answer_document.assert_called_once()
        finally:
            for path in temp_files:
                Path(path).unlink()


class TestFileSenderDirectory:
    """Tests for directory sending."""

    @pytest.fixture
    def mock_message(self) -> MagicMock:
        """Create a mock Telegram message."""
        message = MagicMock()
        message.answer_document = AsyncMock()
        message.answer = AsyncMock()
        message.from_user = MagicMock()
        message.from_user.id = 123456
        return message

    @pytest.mark.asyncio
    async def test_send_directory(self, mock_message: MagicMock) -> None:
        """Test sending files from directory."""
        sender = FileSender()

        with tempfile.TemporaryDirectory() as temp_dir:
            # Create test files
            for i in range(3):
                (Path(temp_dir) / f"file{i}.txt").write_text(f"content {i}")

            results = await sender.send_directory(
                mock_message,
                temp_dir,
            )

            assert len(results) == 3
            # Should have notified about file count
            mock_message.answer.assert_called()

    @pytest.mark.asyncio
    async def test_send_directory_with_pattern(self, mock_message: MagicMock) -> None:
        """Test sending files from directory with pattern."""
        sender = FileSender()

        with tempfile.TemporaryDirectory() as temp_dir:
            # Create mixed files
            (Path(temp_dir) / "file1.txt").write_text("txt content")
            (Path(temp_dir) / "file2.py").write_text("py content")
            (Path(temp_dir) / "file3.txt").write_text("txt content")

            results = await sender.send_directory(
                mock_message,
                temp_dir,
                pattern="*.txt",
            )

            assert len(results) == 2  # Only .txt files

    @pytest.mark.asyncio
    async def test_send_directory_not_found(self, mock_message: MagicMock) -> None:
        """Test error handling for non-existent directory."""
        sender = FileSender()

        with pytest.raises(FileNotFoundSendError):
            await sender.send_directory(mock_message, "/nonexistent/directory")


class TestFileSenderGlob:
    """Tests for glob pattern sending."""

    @pytest.fixture
    def mock_message(self) -> MagicMock:
        """Create a mock Telegram message."""
        message = MagicMock()
        message.answer_document = AsyncMock()
        message.answer = AsyncMock()
        message.from_user = MagicMock()
        message.from_user.id = 123456
        return message

    @pytest.mark.asyncio
    async def test_send_glob_pattern(self, mock_message: MagicMock) -> None:
        """Test sending files matching glob pattern."""
        sender = FileSender()

        with tempfile.TemporaryDirectory() as temp_dir:
            # Create test files
            for i in range(2):
                (Path(temp_dir) / f"file{i}.py").write_text(f"content {i}")
            (Path(temp_dir) / "readme.md").write_text("readme")

            pattern = str(Path(temp_dir) / "*.py")
            results = await sender.send_glob(mock_message, pattern)

            assert len(results) == 2  # Only .py files

    @pytest.mark.asyncio
    async def test_send_glob_no_matches(self, mock_message: MagicMock) -> None:
        """Test glob with no matches."""
        sender = FileSender()

        with tempfile.TemporaryDirectory() as temp_dir:
            pattern = str(Path(temp_dir) / "*.xyz")
            results = await sender.send_glob(mock_message, pattern)

            assert len(results) == 0
            # Should have notified about no files found
            mock_message.answer.assert_called()


class TestFileRequest:
    """Tests for FileRequest dataclass."""

    def test_file_request_creation(self) -> None:
        """Test FileRequest creation."""
        request = FileRequest(path="/path/to/file.txt", request_type="file")
        assert request.path == "/path/to/file.txt"
        assert request.request_type == "file"

    def test_file_request_directory(self) -> None:
        """Test FileRequest for directory."""
        request = FileRequest(path="/path/to/dir", request_type="dir")
        assert request.request_type == "dir"

    def test_file_request_glob(self) -> None:
        """Test FileRequest for glob pattern."""
        request = FileRequest(path="/path/*.py", request_type="glob")
        assert request.request_type == "glob"


class TestSendResult:
    """Tests for SendResult dataclass."""

    def test_send_result_success(self) -> None:
        """Test SendResult for successful send."""
        result = SendResult(success=True, file_path="/path/to/file.txt")
        assert result.success
        assert result.error is None
        assert not result.was_compressed

    def test_send_result_failure(self) -> None:
        """Test SendResult for failed send."""
        result = SendResult(
            success=False,
            file_path="/path/to/file.txt",
            error="File not found",
        )
        assert not result.success
        assert result.error == "File not found"

    def test_send_result_compressed(self) -> None:
        """Test SendResult with compression flag."""
        result = SendResult(
            success=True,
            file_path="/path/to/file.txt",
            was_compressed=True,
        )
        assert result.was_compressed


class TestProcessFileRequests:
    """Tests for processing multiple file requests."""

    @pytest.fixture
    def mock_message(self) -> MagicMock:
        """Create a mock Telegram message."""
        message = MagicMock()
        message.answer_document = AsyncMock()
        message.answer = AsyncMock()
        message.from_user = MagicMock()
        message.from_user.id = 123456
        return message

    @pytest.mark.asyncio
    async def test_process_mixed_requests(self, mock_message: MagicMock) -> None:
        """Test processing mixed file and directory requests."""
        sender = FileSender()

        with tempfile.TemporaryDirectory() as temp_dir:
            # Create a file
            file_path = Path(temp_dir) / "test.txt"
            file_path.write_text("content")

            # Create a subdirectory with files
            sub_dir = Path(temp_dir) / "subdir"
            sub_dir.mkdir()
            (sub_dir / "sub1.txt").write_text("sub content")

            requests = [
                FileRequest(path=str(file_path), request_type="file"),
                FileRequest(path=str(sub_dir), request_type="dir"),
            ]

            results = await sender.process_file_requests(mock_message, requests)

            # Should have results for file + directory files
            assert len(results) >= 2

    @pytest.mark.asyncio
    async def test_process_requests_with_errors(self, mock_message: MagicMock) -> None:
        """Test processing requests with some errors."""
        sender = FileSender()

        with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as f:
            f.write(b"content")
            valid_path = f.name

        try:
            requests = [
                FileRequest(path=valid_path, request_type="file"),
                FileRequest(path="/nonexistent/file.txt", request_type="file"),
            ]

            results = await sender.process_file_requests(mock_message, requests)

            assert len(results) == 2
            # First should succeed
            assert results[0].success
            # Second should fail
            assert not results[1].success
            assert results[1].error is not None
        finally:
            Path(valid_path).unlink()
