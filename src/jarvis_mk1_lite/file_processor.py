"""File processor for extracting text content from various file formats.

This module provides a unified interface for extracting text content from
files sent to the Telegram bot. It supports:
- Text-based files (.txt, .md, .py, .js, .json, etc.) - direct UTF-8 decode
- PDF files - extraction via PyMuPDF (optional dependency)

The extracted text is passed to Claude Code as part of the message context.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class FileProcessingError(Exception):
    """Raised when file processing fails."""

    pass


class UnsupportedFileTypeError(FileProcessingError):
    """Raised when file type is not supported."""

    pass


class FileProcessor:
    """Extracts text content from various file formats.

    Attributes:
        TEXT_EXTENSIONS: Set of extensions that can be read as plain text.
        BINARY_EXTENSIONS: Dict mapping extensions to their handler names.
    """

    # Text-based extensions (direct read with encoding detection)
    TEXT_EXTENSIONS: frozenset[str] = frozenset(
        {
            ".txt",
            ".md",
            ".py",
            ".js",
            ".ts",
            ".jsx",
            ".tsx",
            ".json",
            ".yaml",
            ".yml",
            ".xml",
            ".html",
            ".css",
            ".sql",
            ".sh",
            ".bash",
            ".toml",
            ".env",
            ".log",
            ".csv",
            ".ini",
            ".cfg",
            ".conf",
            ".rst",
            ".go",
            ".rs",
            ".java",
            ".kt",
            ".swift",
            ".c",
            ".cpp",
            ".h",
            ".hpp",
            ".cs",
            ".php",
            ".rb",
            ".pl",
            ".r",
            ".scala",
            ".vue",
            ".svelte",
            ".astro",
            ".prisma",
            ".graphql",
            ".proto",
            ".dockerfile",
            ".makefile",
            ".cmake",
            ".gradle",
            ".properties",
        }
    )

    # Binary formats requiring special handling
    BINARY_EXTENSIONS: dict[str, str] = {
        ".pdf": "pdf",
    }

    def __init__(self, max_chars: int = 100000) -> None:
        """Initialize the file processor.

        Args:
            max_chars: Maximum characters to extract from a file.
                       Content exceeding this limit will be truncated.
        """
        self._max_chars = max_chars

    def is_supported(self, filename: str) -> bool:
        """Check if the file type is supported.

        Args:
            filename: Name of the file (with extension).

        Returns:
            True if the file type can be processed.
        """
        ext = Path(filename).suffix.lower()
        return ext in self.TEXT_EXTENSIONS or ext in self.BINARY_EXTENSIONS

    def get_supported_extensions(self) -> list[str]:
        """Get list of all supported file extensions.

        Returns:
            Sorted list of supported extensions.
        """
        all_extensions = set(self.TEXT_EXTENSIONS) | set(self.BINARY_EXTENSIONS.keys())
        return sorted(all_extensions)

    def extract_text(self, data: bytes, filename: str) -> str:
        """Extract text content from file data.

        Args:
            data: Raw file bytes.
            filename: Name of the file (used for extension detection).

        Returns:
            Extracted text content.

        Raises:
            UnsupportedFileTypeError: If the file type is not supported.
            FileProcessingError: If extraction fails.
        """
        ext = Path(filename).suffix.lower()

        logger.debug(
            "Extracting text from file",
            extra={"file_name": filename, "extension": ext, "size_bytes": len(data)},
        )

        if ext in self.TEXT_EXTENSIONS:
            return self._extract_text_file(data)
        elif ext in self.BINARY_EXTENSIONS:
            handler = self.BINARY_EXTENSIONS[ext]
            if handler == "pdf":
                return self._extract_pdf(data)

        raise UnsupportedFileTypeError(f"Unsupported file type: {ext}")

    def _extract_text_file(self, data: bytes) -> str:
        """Extract text from a text-based file.

        Tries multiple encodings to handle various file sources.

        Args:
            data: Raw file bytes.

        Returns:
            Decoded text content.

        Raises:
            FileProcessingError: If decoding fails with all encodings.
        """
        # Try common encodings in order of likelihood
        encodings = ("utf-8", "utf-8-sig", "utf-16", "latin-1", "cp1251", "cp1252")

        for encoding in encodings:
            try:
                text = data.decode(encoding)
                logger.debug(f"Successfully decoded file with {encoding}")
                return self._truncate(text)
            except UnicodeDecodeError:
                continue

        raise FileProcessingError(
            "Could not decode file with any known encoding. " f"Tried: {', '.join(encodings)}"
        )

    def _extract_pdf(self, data: bytes) -> str:
        """Extract text from a PDF file.

        Args:
            data: Raw PDF bytes.

        Returns:
            Extracted text with page markers.

        Raises:
            FileProcessingError: If PyMuPDF is not installed or extraction fails.
        """
        try:
            import fitz  # type: ignore[import-not-found]  # PyMuPDF
        except ImportError as err:
            raise FileProcessingError("PyMuPDF not installed. Run: pip install pymupdf") from err

        try:
            doc = fitz.open(stream=data, filetype="pdf")
            text_parts: list[str] = []

            for page_num, page in enumerate(doc, 1):
                page_text = page.get_text()
                if page_text.strip():
                    text_parts.append(f"--- Page {page_num} ---\n{page_text}")

            doc.close()

            if not text_parts:
                return "[PDF contains no extractable text]"

            result = "\n\n".join(text_parts)
            logger.debug(
                "Extracted PDF text",
                extra={"pages": len(text_parts), "chars": len(result)},
            )
            return self._truncate(result)

        except Exception as e:
            raise FileProcessingError(f"Failed to extract PDF text: {e}") from e

    def _truncate(self, text: str) -> str:
        """Truncate text if it exceeds the maximum character limit.

        Args:
            text: Text to potentially truncate.

        Returns:
            Original text or truncated version with notice.
        """
        if len(text) > self._max_chars:
            truncated = text[: self._max_chars]
            notice = f"\n\n[Truncated: showing {self._max_chars:,} of {len(text):,} chars]"
            return truncated + notice
        return text


# Module-level convenience instance
_default_processor: FileProcessor | None = None


def get_file_processor(max_chars: int = 100000) -> FileProcessor:
    """Get or create the default file processor instance.

    Args:
        max_chars: Maximum characters to extract.

    Returns:
        FileProcessor instance.
    """
    global _default_processor
    if _default_processor is None:
        _default_processor = FileProcessor(max_chars=max_chars)
    return _default_processor
