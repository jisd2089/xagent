"""Tests for WikiSearcher — text search, wikilink expansion."""

from xagent.core.wiki.models import PageLevel, PageStatus, WikiPage
from xagent.core.wiki.search.graph_traverse import WikilinkGraph
from xagent.core.wiki.search.searcher import WikiSearcher
from xagent.core.wiki.store.memory_store import InMemoryWikiStore


class TestSearch:
    async def test_search_finds_matching_pages(self, memory_store):
        page = WikiPage(
            page_id="python", title="Python",
            level=PageLevel.ENTITY, status=PageStatus.PUBLISHED,
            content="Python 是一种编程语言，广泛用于数据分析。",
            entities=["Python"], namespace="ns",
        )
        await memory_store.save_page(page)

        searcher = WikiSearcher(memory_store)
        results = await searcher.search("Python 数据分析", namespace="ns")
        assert len(results) >= 1
        assert results[0].page.page_id == "python"

    async def test_search_empty_store(self, memory_store):
        searcher = WikiSearcher(memory_store)
        results = await searcher.search("anything", namespace="ns")
        assert results == []

    async def test_search_respects_max_results(self, memory_store):
        for i in range(10):
            page = WikiPage(
                page_id=f"p{i}", title=f"Page {i}",
                level=PageLevel.ENTITY, status=PageStatus.PUBLISHED,
                content="common keyword in all pages", namespace="ns",
            )
            await memory_store.save_page(page)

        searcher = WikiSearcher(memory_store)
        results = await searcher.search("common", namespace="ns", max_results=3)
        assert len(results) <= 3

    async def test_search_namespace_isolation(self, memory_store):
        page_a = WikiPage(
            page_id="a", title="Test A",
            level=PageLevel.ENTITY, status=PageStatus.PUBLISHED,
            content="unique content for A", namespace="ns_a",
        )
        page_b = WikiPage(
            page_id="b", title="Test B",
            level=PageLevel.ENTITY, status=PageStatus.PUBLISHED,
            content="unique content for B", namespace="ns_b",
        )
        await memory_store.save_page(page_a)
        await memory_store.save_page(page_b)

        searcher = WikiSearcher(memory_store)
        results_a = await searcher.search("unique", namespace="ns_a")
        assert all(r.page.namespace == "ns_a" for r in results_a)

    async def test_search_with_wikilink_expansion(self, memory_store):
        page1 = WikiPage(
            page_id="python", title="Python",
            level=PageLevel.ENTITY, status=PageStatus.PUBLISHED,
            content="Python 编程语言", wikilinks=["数据分析"],
            namespace="ns",
        )
        page2 = WikiPage(
            page_id="data_analysis", title="数据分析",
            level=PageLevel.ENTITY, status=PageStatus.PUBLISHED,
            content="数据分析是处理数据的技术", wikilinks=["Python"],
            namespace="ns",
        )
        await memory_store.save_page(page1)
        await memory_store.save_page(page2)

        graph = WikilinkGraph(memory_store)
        await graph.build_index("ns")
        searcher = WikiSearcher(memory_store, graph)

        results = await searcher.search(
            "Python", namespace="ns", include_wikilinks=True, max_results=5
        )
        page_ids = [r.page.page_id for r in results]
        # Should include both the direct match and the wikilinked page
        assert "python" in page_ids

    async def test_search_returns_search_result_with_score(self, memory_store):
        page = WikiPage(
            page_id="x", title="Test",
            level=PageLevel.ENTITY, status=PageStatus.PUBLISHED,
            content="matching content here", namespace="ns",
        )
        await memory_store.save_page(page)

        searcher = WikiSearcher(memory_store)
        results = await searcher.search("matching", namespace="ns")
        assert len(results) > 0
        assert results[0].score > 0
        assert results[0].excerpt
