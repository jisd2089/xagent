"""Tests for the WikiChunker — deterministic IDs, token estimation, splitting."""

from xagent.core.wiki.ingestion.chunker import WikiChunker
from xagent.core.wiki.models import CanonicalDoc


class TestEstimateTokens:
    def test_pure_english(self):
        assert WikiChunker._estimate_tokens("hello world foo bar") == 3  # 4 * 0.75 = 3

    def test_pure_chinese(self):
        # 5 CJK chars × 1.5 = 7
        assert WikiChunker._estimate_tokens("你好世界啊") == 7

    def test_mixed(self):
        text = "Hello 你好 world"
        tokens = WikiChunker._estimate_tokens(text)
        # 2 CJK × 1.5 = 3,  1 English word × 0.75 → int = 0  →  3
        assert tokens == 3

    def test_empty_string_min_one(self):
        assert WikiChunker._estimate_tokens("") == 1


class TestContentHash:
    def test_deterministic(self):
        h1 = WikiChunker._content_hash("doc1", 0, "some text")
        h2 = WikiChunker._content_hash("doc1", 0, "some text")
        assert h1 == h2

    def test_different_content_different_hash(self):
        h1 = WikiChunker._content_hash("doc1", 0, "text A")
        h2 = WikiChunker._content_hash("doc1", 0, "text B")
        assert h1 != h2

    def test_different_position_different_hash(self):
        h1 = WikiChunker._content_hash("doc1", 0, "same text")
        h2 = WikiChunker._content_hash("doc1", 1, "same text")
        assert h1 != h2

    def test_hash_length(self):
        h = WikiChunker._content_hash("doc", 0, "text")
        assert len(h) == 16


class TestChunking:
    def test_short_doc_single_chunk(self):
        doc = CanonicalDoc.from_text("Short text here.")
        chunker = WikiChunker(max_tokens=100)
        chunks = chunker.chunk(doc)
        assert len(chunks) == 1
        assert chunks[0].content == "Short text here."
        assert chunks[0].doc_id == doc.doc_id
        assert chunks[0].position == 0

    def test_long_doc_splits_into_multiple_chunks(self):
        # Build a document that exceeds 20 tokens
        long_text = "\n\n".join(f"Paragraph {i} with some words." for i in range(10))
        doc = CanonicalDoc.from_text(long_text)
        chunker = WikiChunker(max_tokens=20)
        chunks = chunker.chunk(doc)
        assert len(chunks) > 1
        # All chunks reference the same doc
        for c in chunks:
            assert c.doc_id == doc.doc_id
        # Positions are sequential
        for i, c in enumerate(chunks):
            assert c.position == i

    def test_deterministic_ids(self):
        """Same document → same chunk IDs."""
        doc = CanonicalDoc.from_text("Some content here.\n\nMore content here.")
        chunker = WikiChunker(max_tokens=10)
        chunks_a = chunker.chunk(doc)
        chunks_b = chunker.chunk(doc)
        assert [c.chunk_id for c in chunks_a] == [c.chunk_id for c in chunks_b]

    def test_empty_paragraphs_skipped(self):
        doc = CanonicalDoc.from_text("First paragraph.\n\n\n\nSecond paragraph.")
        chunker = WikiChunker(max_tokens=100)
        chunks = chunker.chunk(doc)
        # Should not produce empty chunks
        for c in chunks:
            assert c.content.strip()

    def test_token_counts_positive(self):
        doc = CanonicalDoc.from_text("A simple test document with several words.")
        chunker = WikiChunker(max_tokens=5)
        chunks = chunker.chunk(doc)
        for c in chunks:
            assert c.token_count > 0
