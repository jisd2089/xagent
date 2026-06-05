"""Tests for core data models — content_hash, CanonicalDoc, WikiPage."""

from datetime import datetime, timezone

from xagent.core.wiki.models import (
    CanonicalDoc,
    Chunk,
    CompileResult,
    ExtractedEntity,
    PageLevel,
    PageStatus,
    SearchResult,
    WikiPage,
    content_hash,
)


class TestContentHash:
    def test_deterministic(self):
        assert content_hash("hello") == content_hash("hello")

    def test_different_inputs(self):
        assert content_hash("hello") != content_hash("world")

    def test_length_16(self):
        assert len(content_hash("test")) == 16


class TestCanonicalDoc:
    def test_from_text(self):
        doc = CanonicalDoc.from_text("Hello world")
        assert doc.doc_id == content_hash("Hello world")
        assert doc.content == "Hello world"
        assert doc.source_type == "text"

    def test_from_text_with_metadata(self):
        doc = CanonicalDoc.from_text(
            "data", source_type="crm", source_ref="ticket:42",
            metadata={"priority": "high"},
        )
        assert doc.source_type == "crm"
        assert doc.source_ref == "ticket:42"
        assert doc.metadata["priority"] == "high"


class TestPageLevel:
    def test_ordering(self):
        assert PageLevel.ENTITY < PageLevel.CONCEPT < PageLevel.SUMMARY

    def test_values(self):
        assert PageLevel.ENTITY == 1
        assert PageLevel.CONCEPT == 2
        assert PageLevel.SUMMARY == 3


class TestWikiPage:
    def test_slug_property(self):
        page = WikiPage(page_id="my_page", title="My Page",
                        level=PageLevel.ENTITY, status=PageStatus.PUBLISHED,
                        content="content")
        assert page.slug == "my_page"

    def test_defaults(self):
        page = WikiPage(page_id="x", title="X", level=PageLevel.ENTITY,
                        status=PageStatus.DRAFT, content="c")
        assert page.entities == []
        assert page.wikilinks == []
        assert page.sources == []
        assert page.revision == 1
        assert page.namespace == "default"


class TestCompileResult:
    def test_defaults(self):
        result = CompileResult()
        assert result.pages_created == []
        assert result.pages_updated == []
        assert result.compile_duration_ms == 0
