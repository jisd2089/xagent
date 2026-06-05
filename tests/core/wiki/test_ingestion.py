"""Tests for ExtractorRegistry and TextExtractor."""

from xagent.core.wiki.ingestion.registry import ExtractorRegistry
from xagent.core.wiki.ingestion.text_extractor import TextExtractor


class TestTextExtractor:
    def test_source_type(self):
        ext = TextExtractor()
        assert ext.source_type == "text"

    def test_can_handle_string(self):
        ext = TextExtractor()
        assert ext.can_handle("some text", {"source_type": "text"})

    def test_can_handle_bytes(self):
        ext = TextExtractor()
        assert ext.can_handle(b"some bytes", {})

    def test_cannot_handle_binary(self):
        ext = TextExtractor()
        assert not ext.can_handle(b"\xff\xfe", {})

    def test_cannot_handle_unknown_type(self):
        ext = TextExtractor()
        assert not ext.can_handle("text", {"source_type": "pdf"})

    async def test_extract_string(self):
        ext = TextExtractor()
        doc = await ext.extract("Hello world", {})
        assert doc.content == "Hello world"
        assert doc.source_type == "text"

    async def test_extract_bytes(self):
        ext = TextExtractor()
        doc = await ext.extract(b"byte content", {})
        assert doc.content == "byte content"


class TestExtractorRegistry:
    def test_create_default_has_text_extractor(self):
        reg = ExtractorRegistry.create_default()
        ext = reg.find("some text", {"source_type": "text"})
        assert ext is not None

    def test_find_returns_none_for_unknown(self):
        reg = ExtractorRegistry()  # empty
        assert reg.find("text", {"source_type": "pdf"}) is None

    async def test_extract_raises_for_unknown(self):
        reg = ExtractorRegistry()
        try:
            await reg.extract("text", {"source_type": "pdf"})
            assert False, "Should have raised ValueError"
        except ValueError:
            pass

    async def test_extract_with_registered_extractor(self):
        reg = ExtractorRegistry()
        reg.register(TextExtractor())
        doc = await reg.extract("test content", {"source_type": "text"})
        assert doc.content == "test content"
