"""Smart text chunking for Telegram message limits.

This module provides intelligent text splitting that preserves
structure like code blocks, paragraphs, and sentences.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class ChunkResult:
    """Result of chunking operation.

    Attributes:
        chunks: List of text chunks.
        total_parts: Total number of parts.
    """

    chunks: list[str]
    total_parts: int


class SmartChunker:
    """Splits long text into Telegram-compatible chunks preserving structure.

    Priority of split points (highest to lowest):
    1. Paragraph boundary (\\n\\n)
    2. Code block boundary (```)
    3. Sentence boundary (. ! ?)
    4. Line boundary (\\n)
    5. Word boundary (space)
    6. Hard split at max_size

    Example:
        >>> chunker = SmartChunker(max_size=4000)
        >>> result = chunker.chunk(long_text)
        >>> for chunk in result.chunks:
        ...     await message.answer(chunk)
    """

    DEFAULT_MAX_SIZE = 4000  # Safety margin from Telegram's 4096
    TELEGRAM_LIMIT = 4096

    def __init__(self, max_size: int = DEFAULT_MAX_SIZE) -> None:
        """Initialize chunker.

        Args:
            max_size: Maximum chunk size. Default 4000 (margin from 4096).

        Raises:
            ValueError: If max_size exceeds Telegram limit.
        """
        if max_size > self.TELEGRAM_LIMIT:
            raise ValueError(f"max_size cannot exceed Telegram limit of {self.TELEGRAM_LIMIT}")
        if max_size < 100:
            raise ValueError("max_size must be at least 100")
        self._max_size = max_size

    @property
    def max_size(self) -> int:
        """Get the maximum chunk size."""
        return self._max_size

    def chunk(self, text: str) -> ChunkResult:
        """Split text into chunks.

        Args:
            text: Text to split.

        Returns:
            ChunkResult with list of chunks and total count.
        """
        if not text:
            return ChunkResult(chunks=[], total_parts=0)

        if len(text) <= self._max_size:
            return ChunkResult(chunks=[text], total_parts=1)

        chunks: list[str] = []
        remaining = text

        while remaining:
            if len(remaining) <= self._max_size:
                chunks.append(remaining)
                break

            split_pos = self._find_split_point(remaining)
            chunk = remaining[:split_pos].rstrip()
            if chunk:  # Only add non-empty chunks
                chunks.append(chunk)
            remaining = remaining[split_pos:].lstrip()

        # Add part headers if multiple chunks
        total = len(chunks)
        if total > 1:
            chunks = [f"[Part {i}/{total}]\n{chunk}" for i, chunk in enumerate(chunks, 1)]

        return ChunkResult(chunks=chunks, total_parts=total)

    def _find_split_point(self, text: str) -> int:
        """Find best split point within max_size.

        Args:
            text: Text to find split point in.

        Returns:
            Position to split at.
        """
        max_pos = self._max_size

        # 1. Try paragraph boundary (highest priority)
        para_match = text.rfind("\n\n", 0, max_pos)
        if para_match > max_pos // 2:  # At least halfway through
            return para_match + 2

        # 2. Try code block boundary
        code_end = self._find_code_block_boundary(text, max_pos)
        if code_end > 0:
            return code_end

        # 3. Try sentence boundary
        best_sentence = self._find_sentence_boundary(text, max_pos)
        if best_sentence > max_pos // 2:
            return best_sentence

        # 4. Try line boundary
        line_break = text.rfind("\n", 0, max_pos)
        if line_break > max_pos // 3:
            return line_break + 1

        # 5. Try word boundary
        word_break = text.rfind(" ", 0, max_pos)
        if word_break > max_pos // 4:
            return word_break + 1

        # 6. Hard split (last resort)
        return max_pos

    def _find_sentence_boundary(self, text: str, max_pos: int) -> int:
        """Find best sentence boundary within max_pos.

        Args:
            text: Text to search.
            max_pos: Maximum position to search.

        Returns:
            Position after sentence end, or -1 if not found.
        """
        sentence_patterns = [". ", "! ", "? ", ".\n", "!\n", "?\n"]
        best_pos = -1

        for pattern in sentence_patterns:
            pos = text.rfind(pattern, 0, max_pos)
            if pos > best_pos:
                best_pos = pos

        if best_pos > 0:
            return best_pos + 2  # Include the punctuation and space/newline

        return -1

    def _find_code_block_boundary(self, text: str, max_pos: int) -> int:
        """Find code block end within max_pos.

        Ensures we don't split in the middle of a code block.

        Args:
            text: Text to search.
            max_pos: Maximum position to search.

        Returns:
            Position after closing ```, or 0 if not found.
        """
        # Find all ``` positions in the text up to max_pos
        pattern = re.compile(r"```")
        matches = list(pattern.finditer(text[:max_pos]))

        if len(matches) < 2:
            return 0

        # We need an even number of ``` for complete blocks
        # Find the last complete code block (pairs of ```)
        for i in range(len(matches) - 1, 0, -2):
            close_pos = matches[i].end()
            if close_pos <= max_pos:
                # Look for newline after closing ```
                newline_pos = text.find("\n", close_pos)
                if 0 < newline_pos <= max_pos:
                    return newline_pos + 1
                # If no newline but still within limit
                if close_pos <= max_pos:
                    return close_pos

        return 0

    def chunk_with_prefix(self, text: str, prefix: str = "", suffix: str = "") -> ChunkResult:
        """Split text with optional prefix/suffix for each chunk.

        Args:
            text: Text to split.
            prefix: Prefix to add to each chunk.
            suffix: Suffix to add to each chunk.

        Returns:
            ChunkResult with prefixed/suffixed chunks.
        """
        # Account for prefix/suffix in max_size
        effective_max = self._max_size - len(prefix) - len(suffix)
        if effective_max < 100:
            raise ValueError("Prefix and suffix too long for meaningful chunking")

        # Temporarily adjust max_size
        original_max = self._max_size
        self._max_size = effective_max

        try:
            result = self.chunk(text)
            # Add prefix/suffix to each chunk
            result.chunks = [f"{prefix}{chunk}{suffix}" for chunk in result.chunks]
            return result
        finally:
            self._max_size = original_max
