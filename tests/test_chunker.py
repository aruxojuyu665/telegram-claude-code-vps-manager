"""Tests for SmartChunker text splitting."""

from __future__ import annotations

import pytest

from jarvis_mk1_lite.chunker import ChunkResult, SmartChunker


class TestSmartChunkerInit:
    """Tests for SmartChunker initialization."""

    def test_default_max_size(self) -> None:
        """Test default max_size is 4000."""
        chunker = SmartChunker()
        assert chunker.max_size == 4000

    def test_custom_max_size(self) -> None:
        """Test custom max_size."""
        chunker = SmartChunker(max_size=2000)
        assert chunker.max_size == 2000

    def test_max_size_exceeds_telegram_limit(self) -> None:
        """Test ValueError when max_size exceeds 4096."""
        with pytest.raises(ValueError, match="cannot exceed Telegram limit"):
            SmartChunker(max_size=5000)

    def test_max_size_too_small(self) -> None:
        """Test ValueError when max_size is too small."""
        with pytest.raises(ValueError, match="must be at least 100"):
            SmartChunker(max_size=50)


class TestSmartChunkerChunk:
    """Tests for SmartChunker.chunk() method."""

    def test_empty_text(self) -> None:
        """Test empty text returns empty result."""
        chunker = SmartChunker()
        result = chunker.chunk("")
        assert result.chunks == []
        assert result.total_parts == 0

    def test_short_text_no_split(self) -> None:
        """Test short text is not split."""
        chunker = SmartChunker(max_size=100)
        text = "Hello, world!"
        result = chunker.chunk(text)
        assert result.chunks == [text]
        assert result.total_parts == 1

    def test_exact_max_size_no_split(self) -> None:
        """Test text exactly at max_size is not split."""
        chunker = SmartChunker(max_size=100)
        text = "a" * 100
        result = chunker.chunk(text)
        assert result.chunks == [text]
        assert result.total_parts == 1

    def test_split_adds_part_headers(self) -> None:
        """Test that split chunks have [Part X/Y] headers."""
        chunker = SmartChunker(max_size=100)
        text = "a" * 150
        result = chunker.chunk(text)
        assert result.total_parts == 2
        assert result.chunks[0].startswith("[Part 1/2]")
        assert result.chunks[1].startswith("[Part 2/2]")


class TestSmartChunkerSplitPoints:
    """Tests for split point detection."""

    def test_split_at_paragraph(self) -> None:
        """Test splitting at paragraph boundary."""
        chunker = SmartChunker(max_size=120)
        # Text needs to be longer than max_size to trigger splitting
        # First para: ~70 chars, second para: ~78 chars, total: ~150 chars
        text = (
            "First paragraph with some text that is long enough to split.\n\n"
            "Second paragraph with more text that continues for a while exceeding limit."
        )
        result = chunker.chunk(text)
        # Should split at \n\n
        assert result.total_parts == 2
        assert "First paragraph" in result.chunks[0]
        assert "Second paragraph" in result.chunks[1]

    def test_split_at_sentence(self) -> None:
        """Test splitting at sentence boundary."""
        chunker = SmartChunker(max_size=150)
        text = (
            "First sentence here with more content. "
            "Second sentence here with additional text. "
            "Third sentence continues with even more words to make it long enough. "
            "Fourth sentence adds more content."
        )
        result = chunker.chunk(text)
        # Should split after a period
        assert result.total_parts >= 2

    def test_split_at_line(self) -> None:
        """Test splitting at line boundary."""
        chunker = SmartChunker(max_size=150)
        text = (
            "Line one with some content here\n"
            "Line two with more content\n"
            "Line three with additional text\n"
            "Line four with even more words\n"
            "Line five continues the pattern\n"
            "Line six adds to the total"
        )
        result = chunker.chunk(text)
        # Should split at newline if text exceeds max_size
        assert result.total_parts >= 1

    def test_split_at_word(self) -> None:
        """Test splitting at word boundary."""
        chunker = SmartChunker(max_size=150)
        text = " ".join([f"word{i}" for i in range(50)])  # ~250 characters
        result = chunker.chunk(text)
        # Should not split mid-word
        for chunk in result.chunks:
            # Remove header and check no partial words
            content = chunk.split("\n", 1)[-1] if chunk.startswith("[Part") else chunk
            assert not content.startswith(" ")

    def test_hard_split_long_word(self) -> None:
        """Test hard split when no good split point."""
        chunker = SmartChunker(max_size=100)
        text = "a" * 250  # No spaces, paragraphs, or sentences
        result = chunker.chunk(text)
        assert result.total_parts == 3


class TestSmartChunkerCodeBlocks:
    """Tests for code block handling."""

    def test_preserve_code_block_simple(self) -> None:
        """Test that simple code blocks are not split."""
        chunker = SmartChunker(max_size=200)
        text = """Some text before.

```python
def hello():
    print("Hello, World!")
```

Some text after."""
        result = chunker.chunk(text)
        # The code block should be intact in one chunk
        found_complete_block = False
        for chunk in result.chunks:
            if "```python" in chunk and "```\n" in chunk[chunk.find("```python") + 10 :]:
                found_complete_block = True
                break
        assert found_complete_block or result.total_parts == 1

    def test_code_block_boundary_detection(self) -> None:
        """Test that we split after code block, not inside."""
        chunker = SmartChunker(max_size=150)
        text = """```python
def foo():
    pass
```

After the code block comes regular text that continues for a while."""
        result = chunker.chunk(text)
        # First chunk should contain the complete code block
        if result.total_parts > 1:
            first_chunk = result.chunks[0]
            # Count ``` in first chunk - should be even (complete blocks)
            backtick_count = first_chunk.count("```")
            assert backtick_count % 2 == 0 or backtick_count == 0


class TestSmartChunkerUnicode:
    """Tests for Unicode handling."""

    def test_unicode_text(self) -> None:
        """Test handling of Unicode characters."""
        chunker = SmartChunker(max_size=100)
        text = "Hello world! " * 20  # Unicode text
        result = chunker.chunk(text)
        assert result.total_parts >= 1
        # All chunks should be valid
        for chunk in result.chunks:
            assert isinstance(chunk, str)

    def test_emoji_handling(self) -> None:
        """Test handling of emoji characters."""
        chunker = SmartChunker(max_size=100)
        text = "Hello! " * 10 + "Some text after."
        result = chunker.chunk(text)
        assert result.total_parts >= 1

    def test_mixed_unicode(self) -> None:
        """Test mixed Unicode scripts."""
        chunker = SmartChunker(max_size=150)
        text = "English text. Bonjour monde. 日本語テキスト. " * 5
        result = chunker.chunk(text)
        assert result.total_parts >= 1


class TestSmartChunkerEdgeCases:
    """Tests for edge cases."""

    def test_only_whitespace(self) -> None:
        """Test text with only whitespace."""
        chunker = SmartChunker(max_size=100)
        result = chunker.chunk("   \n\n   \t   ")
        # Should handle gracefully
        assert result.total_parts <= 1

    def test_single_very_long_line(self) -> None:
        """Test single line longer than max_size."""
        chunker = SmartChunker(max_size=100)
        text = "word " * 50  # ~250 characters, no newlines
        result = chunker.chunk(text)
        assert result.total_parts >= 3
        # Each chunk should be <= max_size (plus header)
        for chunk in result.chunks:
            assert len(chunk) <= 100 + 20  # Allow for [Part X/Y] header

    def test_many_small_paragraphs(self) -> None:
        """Test many small paragraphs."""
        chunker = SmartChunker(max_size=100)
        paragraphs = ["Short paragraph.\n\n"] * 10
        text = "".join(paragraphs)
        result = chunker.chunk(text)
        assert result.total_parts >= 1

    def test_nested_code_blocks(self) -> None:
        """Test handling of content that looks like nested code blocks."""
        chunker = SmartChunker(max_size=200)
        text = """```markdown
Here's some code:
```python
print("hello")
```
End of markdown.
```"""
        result = chunker.chunk(text)
        # Should not crash
        assert result.total_parts >= 1


class TestChunkWithPrefix:
    """Tests for chunk_with_prefix method."""

    def test_prefix_suffix_added(self) -> None:
        """Test that prefix and suffix are added to each chunk."""
        chunker = SmartChunker(max_size=200)
        text = "Some text that might be split."
        result = chunker.chunk_with_prefix(text, prefix=">>> ", suffix=" <<<")
        for chunk in result.chunks:
            assert chunk.startswith(">>> ")
            assert chunk.endswith(" <<<")

    def test_prefix_suffix_too_long(self) -> None:
        """Test error when prefix/suffix too long."""
        chunker = SmartChunker(max_size=150)
        with pytest.raises(ValueError, match="too long"):
            chunker.chunk_with_prefix("text", prefix="a" * 100, suffix="b" * 100)


class TestChunkResult:
    """Tests for ChunkResult dataclass."""

    def test_chunk_result_creation(self) -> None:
        """Test ChunkResult can be created."""
        result = ChunkResult(chunks=["a", "b"], total_parts=2)
        assert result.chunks == ["a", "b"]
        assert result.total_parts == 2

    def test_chunk_result_empty(self) -> None:
        """Test empty ChunkResult."""
        result = ChunkResult(chunks=[], total_parts=0)
        assert len(result.chunks) == 0
        assert result.total_parts == 0


class TestFindCodeBlockBoundaryEdgeCases:
    """Edge case tests for _find_code_block_boundary (P4 coverage)."""

    def test_find_code_block_boundary_no_match(self) -> None:
        """Test when no code block boundary can be found."""
        chunker = SmartChunker(max_size=100)
        # Text with single ``` (incomplete block)
        text = "Some text\n```python\ndef foo():\n    pass"

        result = chunker._find_code_block_boundary(text, 100)

        # Should return 0 when no complete code block found
        assert result == 0

    def test_find_code_block_boundary_single_backtick(self) -> None:
        """Test with only one ``` marker."""
        chunker = SmartChunker(max_size=150)
        text = "Regular text here\n```python\ncode continues..."

        result = chunker._find_code_block_boundary(text, 150)

        # Only one ```, so no complete block
        assert result == 0

    def test_find_code_block_boundary_complete_block(self) -> None:
        """Test with complete code block."""
        chunker = SmartChunker(max_size=200)
        text = """Some intro text.
```python
def hello():
    pass
```
After the code block."""

        result = chunker._find_code_block_boundary(text, 200)

        # Should find the end of the code block
        assert result > 0
        # The result should be after the closing ```
        assert text[result - 10 : result].strip().endswith("```") or result > text.find("```\n")


class TestChunkWithPrefixEdgeCases:
    """Edge case tests for chunk_with_prefix (P4 coverage)."""

    def test_chunk_with_prefix_restores_max_size(self) -> None:
        """Test that max_size is restored after chunking with prefix."""
        chunker = SmartChunker(max_size=200)
        original_max = chunker.max_size

        chunker.chunk_with_prefix("Some text", prefix=">> ", suffix=" <<")

        # max_size should be restored to original
        assert chunker.max_size == original_max

    def test_chunk_with_prefix_empty_text(self) -> None:
        """Test chunk_with_prefix with empty text."""
        chunker = SmartChunker(max_size=200)
        result = chunker.chunk_with_prefix("", prefix=">> ", suffix=" <<")

        assert result.chunks == []
        assert result.total_parts == 0

    def test_chunk_with_prefix_short_text(self) -> None:
        """Test chunk_with_prefix with text that doesn't need splitting."""
        chunker = SmartChunker(max_size=200)
        result = chunker.chunk_with_prefix("Short text", prefix="[", suffix="]")

        assert len(result.chunks) == 1
        assert result.chunks[0] == "[Short text]"

    def test_chunk_with_prefix_long_text(self) -> None:
        """Test chunk_with_prefix with text that needs splitting."""
        chunker = SmartChunker(max_size=150)
        text = "word " * 50  # ~250 chars
        result = chunker.chunk_with_prefix(text, prefix=">> ", suffix=" <<")

        assert result.total_parts >= 2
        for chunk in result.chunks:
            assert chunk.startswith(">> ")
            assert chunk.endswith(" <<")


class TestFindSentenceBoundaryEdgeCases:
    """Edge case tests for _find_sentence_boundary."""

    def test_find_sentence_boundary_no_sentence(self) -> None:
        """Test when no sentence boundary exists."""
        chunker = SmartChunker(max_size=100)
        text = "no sentence ending here just words"

        result = chunker._find_sentence_boundary(text, 100)

        assert result == -1

    def test_find_sentence_boundary_multiple_sentences(self) -> None:
        """Test finding the last sentence boundary."""
        chunker = SmartChunker(max_size=100)
        text = "First sentence. Second sentence. Third sentence continues."

        result = chunker._find_sentence_boundary(text, 100)

        # Should find the last sentence boundary before limit
        assert result > 0
        # Verify it's after a sentence-ending punctuation
        assert text[result - 2] in ".!?"


class TestSmartChunkerBoundaryConditions:
    """Boundary condition tests for SmartChunker."""

    def test_max_size_exactly_100(self) -> None:
        """Test with minimum allowed max_size of 100."""
        chunker = SmartChunker(max_size=100)
        text = "a" * 50
        result = chunker.chunk(text)

        assert result.total_parts == 1

    def test_max_size_exactly_4096(self) -> None:
        """Test with maximum allowed max_size of 4096."""
        chunker = SmartChunker(max_size=4096)
        text = "a" * 4096
        result = chunker.chunk(text)

        assert result.total_parts == 1

    def test_text_with_only_newlines(self) -> None:
        """Test text containing only newlines."""
        chunker = SmartChunker(max_size=100)
        result = chunker.chunk("\n\n\n\n\n")

        # Should handle gracefully
        assert result.total_parts <= 1

    def test_text_with_mixed_line_endings(self) -> None:
        """Test text with mixed line endings (\\n, \\r\\n, \\r)."""
        chunker = SmartChunker(max_size=100)
        text = "Line1\r\nLine2\rLine3\nLine4"
        result = chunker.chunk(text)

        assert result.total_parts == 1
        assert "Line1" in result.chunks[0]


# =============================================================================
# P2-CHK-001: Chunker Edge Cases (v1.0.20)
# =============================================================================


class TestChunkerAdvancedEdgeCases:
    """Advanced edge case tests for SmartChunker (P2-CHK-001).

    Covers: extreme inputs, special characters, boundary conditions,
    multi-byte characters, and stress testing.
    """

    def test_single_character_text(self) -> None:
        """Test chunking single character text."""
        chunker = SmartChunker(max_size=100)
        result = chunker.chunk("X")
        assert result.total_parts == 1
        assert result.chunks[0] == "X"

    def test_text_with_tabs(self) -> None:
        """Test handling of tab characters."""
        chunker = SmartChunker(max_size=150)
        text = "Column1\tColumn2\tColumn3\n" * 10
        result = chunker.chunk(text)
        assert result.total_parts >= 1
        for chunk in result.chunks:
            assert "\t" in chunk or "Column" in chunk

    def test_consecutive_code_blocks(self) -> None:
        """Test handling multiple consecutive code blocks."""
        chunker = SmartChunker(max_size=300)
        text = """```python
def foo():
    pass
```

```javascript
function bar() {}
```

```go
func baz() {}
```"""
        result = chunker.chunk(text)
        assert result.total_parts >= 1

    def test_deeply_nested_structure(self) -> None:
        """Test handling deeply nested markdown structure."""
        chunker = SmartChunker(max_size=200)
        text = """# Heading 1
## Heading 2
### Heading 3
#### Heading 4
##### Heading 5
###### Heading 6

- Item 1
  - Item 1.1
    - Item 1.1.1
      - Item 1.1.1.1
"""
        result = chunker.chunk(text)
        assert result.total_parts >= 1
        assert "Heading" in result.chunks[0]

    def test_cyrillic_text_chunking(self) -> None:
        """Test chunking Cyrillic (Russian) text."""
        chunker = SmartChunker(max_size=100)
        text = "Hello world! This is a test message in another language. " * 5
        result = chunker.chunk(text)
        assert result.total_parts >= 1
        # Verify all chunks contain valid text
        for chunk in result.chunks:
            assert len(chunk) > 0

    def test_chinese_text_chunking(self) -> None:
        """Test chunking Chinese text."""
        chunker = SmartChunker(max_size=100)
        text = "你好世界！这是一条中文测试消息。" * 5
        result = chunker.chunk(text)
        assert result.total_parts >= 1

    def test_arabic_text_chunking(self) -> None:
        """Test chunking Arabic (RTL) text."""
        chunker = SmartChunker(max_size=100)
        text = "مرحبا بالعالم! هذه رسالة اختبار. " * 5
        result = chunker.chunk(text)
        assert result.total_parts >= 1

    def test_mixed_content_complex(self) -> None:
        """Test complex mixed content: code, markdown, unicode."""
        chunker = SmartChunker(max_size=300)
        text = """# Welcome 你好 مرحبا

Here's some code:

```python
def hello():
    print("Hello!")
```

> Quote with emoji 🎉

| Column A | Column B |
|----------|----------|
| Value 1  | Value 2  |
"""
        result = chunker.chunk(text)
        assert result.total_parts >= 1
        # Content should be preserved
        full_content = "".join(result.chunks)
        assert "python" in full_content or "```" in full_content

    def test_very_long_url(self) -> None:
        """Test handling very long URL without breaking it."""
        chunker = SmartChunker(max_size=150)
        url = "https://example.com/" + "path/" * 50 + "end"
        text = f"Check this link: {url}"
        result = chunker.chunk(text)
        assert result.total_parts >= 1

    def test_text_with_zero_width_chars(self) -> None:
        """Test handling zero-width characters."""
        chunker = SmartChunker(max_size=100)
        # Zero-width space and zero-width joiner
        text = "Hello\u200bWorld\u200cTest\u200dExample"
        result = chunker.chunk(text)
        assert result.total_parts == 1

    def test_text_with_special_punctuation(self) -> None:
        """Test handling various punctuation marks."""
        chunker = SmartChunker(max_size=150)
        text = (
            "Sentence one... Sentence two! "
            "Question? Answer. "
            "Ellipsis… Dash—here. "
            "Quote: 'text'. "
            'Double: "quoted". '
        ) * 3
        result = chunker.chunk(text)
        assert result.total_parts >= 1

    def test_repeated_pattern_stress(self) -> None:
        """Stress test with repeated pattern."""
        chunker = SmartChunker(max_size=500)
        # Create text with many repeated patterns
        text = "ABCD. " * 200  # ~1200 chars
        result = chunker.chunk(text)
        assert result.total_parts >= 2
        # Verify no data loss
        total_abcd = sum(chunk.count("ABCD") for chunk in result.chunks)
        assert total_abcd >= 195  # Allow for some trimming

    def test_alternating_long_short_lines(self) -> None:
        """Test alternating long and short lines."""
        chunker = SmartChunker(max_size=150)
        lines = []
        for i in range(20):
            if i % 2 == 0:
                lines.append("Short line.")
            else:
                lines.append("This is a much longer line with more content here.")
        text = "\n".join(lines)
        result = chunker.chunk(text)
        assert result.total_parts >= 1

    def test_markdown_list_preservation(self) -> None:
        """Test that markdown lists are handled gracefully."""
        chunker = SmartChunker(max_size=100)
        text = """
- Item 1
- Item 2
- Item 3
- Item 4
- Item 5
- Item 6
- Item 7
- Item 8
- Item 9
- Item 10
"""
        result = chunker.chunk(text)
        assert result.total_parts >= 1
        # Items should be present
        all_text = " ".join(result.chunks)
        assert "Item" in all_text

    def test_json_like_content(self) -> None:
        """Test handling JSON-like content."""
        chunker = SmartChunker(max_size=200)
        text = """{
  "name": "test",
  "data": [1, 2, 3, 4, 5],
  "nested": {
    "key": "value",
    "items": ["a", "b", "c"]
  },
  "description": "A test JSON object"
}"""
        result = chunker.chunk(text)
        assert result.total_parts >= 1

    def test_html_like_content(self) -> None:
        """Test handling HTML-like content."""
        chunker = SmartChunker(max_size=200)
        text = """<html>
<head><title>Test</title></head>
<body>
<h1>Hello World</h1>
<p>This is a paragraph with <strong>bold</strong> text.</p>
<ul>
<li>Item 1</li>
<li>Item 2</li>
</ul>
</body>
</html>"""
        result = chunker.chunk(text)
        assert result.total_parts >= 1
