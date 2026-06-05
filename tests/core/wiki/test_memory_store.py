"""Tests for InMemoryWikiStore — CRUD, entity search, text search."""

from xagent.core.wiki.models import (
    CompileLog,
    PageLevel,
    PageStatus,
    WikiPage,
)
from xagent.core.wiki.store.memory_store import InMemoryWikiStore


class TestSaveAndGet:
    async def test_save_and_retrieve(self, memory_store, sample_page):
        await memory_store.save_page(sample_page)
        page = await memory_store.get_page("zhang_wei", "test_ns")
        assert page is not None
        assert page.title == "张伟"

    async def test_get_nonexistent_returns_none(self, memory_store):
        page = await memory_store.get_page("nonexistent", "test_ns")
        assert page is None

    async def test_save_overwrites(self, memory_store, sample_page):
        await memory_store.save_page(sample_page)
        sample_page.revision = 2
        sample_page.content = "Updated content"
        await memory_store.save_page(sample_page)
        page = await memory_store.get_page("zhang_wei", "test_ns")
        assert page.revision == 2
        assert page.content == "Updated content"


class TestListPages:
    async def test_list_all_in_namespace(self, memory_store):
        for i in range(3):
            page = WikiPage(
                page_id=f"page_{i}", title=f"Page {i}",
                level=PageLevel.ENTITY, status=PageStatus.PUBLISHED,
                content=f"Content {i}", namespace="ns_a",
            )
            await memory_store.save_page(page)
        # Add one in different namespace
        other = WikiPage(
            page_id="other", title="Other",
            level=PageLevel.ENTITY, status=PageStatus.PUBLISHED,
            content="Other content", namespace="ns_b",
        )
        await memory_store.save_page(other)

        pages = await memory_store.list_pages(namespace="ns_a")
        assert len(pages) == 3

    async def test_list_filter_by_level(self, memory_store):
        entity = WikiPage(
            page_id="e1", title="Entity",
            level=PageLevel.ENTITY, status=PageStatus.PUBLISHED,
            content="Entity content", namespace="ns",
        )
        concept = WikiPage(
            page_id="c1", title="Concept",
            level=PageLevel.CONCEPT, status=PageStatus.PUBLISHED,
            content="Concept content", namespace="ns",
        )
        await memory_store.save_page(entity)
        await memory_store.save_page(concept)

        entities = await memory_store.list_pages(namespace="ns", level=PageLevel.ENTITY)
        assert len(entities) == 1
        assert entities[0].title == "Entity"


class TestFindByEntity:
    async def test_find_by_entity_name(self, memory_store, sample_page):
        await memory_store.save_page(sample_page)
        results = await memory_store.find_pages_by_entity("Python", "test_ns")
        assert len(results) == 1
        assert results[0].page_id == "zhang_wei"

    async def test_find_by_entity_case_insensitive(self, memory_store, sample_page):
        await memory_store.save_page(sample_page)
        results = await memory_store.find_pages_by_entity("python", "test_ns")
        assert len(results) == 1

    async def test_find_nonexistent_entity(self, memory_store, sample_page):
        await memory_store.save_page(sample_page)
        results = await memory_store.find_pages_by_entity("Java", "test_ns")
        assert results == []


class TestSearchText:
    async def test_search_by_title(self, memory_store, sample_page):
        await memory_store.save_page(sample_page)
        results = await memory_store.search_text("张伟", "test_ns")
        assert len(results) >= 1

    async def test_search_by_content(self, memory_store, sample_page):
        await memory_store.save_page(sample_page)
        results = await memory_store.search_text("数据分析", "test_ns")
        assert len(results) >= 1

    async def test_search_no_match(self, memory_store, sample_page):
        await memory_store.save_page(sample_page)
        results = await memory_store.search_text("量子计算", "test_ns")
        assert results == []

    async def test_search_respects_k_limit(self, memory_store):
        for i in range(10):
            page = WikiPage(
                page_id=f"p{i}", title="Test",
                level=PageLevel.ENTITY, status=PageStatus.PUBLISHED,
                content="test content", namespace="ns",
            )
            await memory_store.save_page(page)
        results = await memory_store.search_text("test", "ns", k=3)
        assert len(results) == 3


class TestCompileLog:
    async def test_save_compile_log(self, memory_store):
        log = CompileLog(operation="COMPILE", namespace="ns", pages_affected=2)
        await memory_store.save_compile_log(log)
        assert len(memory_store.compile_logs) == 1
        assert memory_store.compile_logs[0].pages_affected == 2

    async def test_page_count(self, memory_store, sample_page):
        assert memory_store.page_count == 0
        await memory_store.save_page(sample_page)
        assert memory_store.page_count == 1
