"""Tests for Ranker and WikilinkGraph traversal."""

from xagent.core.wiki.models import PageLevel, PageStatus, SearchResult, WikiPage
from xagent.core.wiki.search.graph_traverse import WikilinkGraph
from xagent.core.wiki.search.ranker import Ranker
from xagent.core.wiki.store.memory_store import InMemoryWikiStore


class TestRanker:
    def test_rank_sorts_by_score(self):
        pages = [
            WikiPage(page_id="a", title="A", level=PageLevel.ENTITY,
                     status=PageStatus.PUBLISHED, content="low", namespace="ns"),
            WikiPage(page_id="b", title="B", level=PageLevel.ENTITY,
                     status=PageStatus.PUBLISHED, content="high", namespace="ns"),
        ]
        results = [
            SearchResult(page=pages[0], score=0.3),
            SearchResult(page=pages[1], score=0.9),
        ]
        ranked = Ranker.rank(results)
        assert ranked[0].page.page_id == "b"

    def test_concept_pages_get_boost(self):
        entity_page = WikiPage(
            page_id="e", title="Entity", level=PageLevel.ENTITY,
            status=PageStatus.PUBLISHED, content="x", namespace="ns",
        )
        concept_page = WikiPage(
            page_id="c", title="Concept", level=PageLevel.CONCEPT,
            status=PageStatus.PUBLISHED, content="x", namespace="ns",
        )
        results = [
            SearchResult(page=entity_page, score=0.5),
            SearchResult(page=concept_page, score=0.5),
        ]
        ranked = Ranker.rank(results)
        # Concept should rank higher due to boost
        assert ranked[0].page.page_id == "c"

    def test_compute_text_score_title_match(self):
        score = Ranker.compute_text_score("Python", "some content", "Python 入门")
        assert score > 0

    def test_compute_text_score_no_match(self):
        score = Ranker.compute_text_score("量子计算", "regular text", "Page Title")
        assert score == 0.0

    def test_compute_text_score_empty_query(self):
        score = Ranker.compute_text_score("", "content", "title")
        assert score == 0.0


class TestWikilinkGraph:
    async def test_build_index(self, memory_store):
        page1 = WikiPage(
            page_id="a", title="A", level=PageLevel.ENTITY,
            status=PageStatus.PUBLISHED, content="content A",
            wikilinks=["b", "c"], namespace="ns",
        )
        page2 = WikiPage(
            page_id="b", title="B", level=PageLevel.ENTITY,
            status=PageStatus.PUBLISHED, content="content B",
            wikilinks=["a"], namespace="ns",
        )
        await memory_store.save_page(page1)
        await memory_store.save_page(page2)

        graph = WikilinkGraph(memory_store)
        await graph.build_index("ns")

        assert "b" in graph.adjacency["a"]
        assert "c" in graph.adjacency["a"]
        assert "a" in graph.adjacency["b"]

    async def test_find_related_depth_1(self):
        graph = WikilinkGraph()
        graph._adjacency = {
            "a": {"b", "c"},
            "b": {"d"},
            "c": set(),
            "d": set(),
        }
        related = await graph.find_related("a", depth=1)
        assert set(related) == {"b", "c"}

    async def test_find_related_depth_2(self):
        graph = WikilinkGraph()
        graph._adjacency = {
            "a": {"b"},
            "b": {"c"},
            "c": {"d"},
            "d": set(),
        }
        related = await graph.find_related("a", depth=2)
        assert "b" in related
        assert "c" in related
        assert "d" not in related  # depth 3, not reached

    async def test_find_related_no_cycles(self):
        graph = WikilinkGraph()
        graph._adjacency = {
            "a": {"b"},
            "b": {"a"},  # cycle
        }
        related = await graph.find_related("a", depth=5)
        assert related == ["b"]

    async def test_find_related_isolated_node(self):
        graph = WikilinkGraph()
        graph._adjacency = {"a": set()}
        related = await graph.find_related("a", depth=1)
        assert related == []

    async def test_add_page_incremental(self):
        graph = WikilinkGraph()
        page = WikiPage(
            page_id="new", title="New", level=PageLevel.ENTITY,
            status=PageStatus.PUBLISHED, content="x",
            wikilinks=["x", "y"], namespace="ns",
        )
        graph.add_page(page)
        assert graph.adjacency["new"] == {"x", "y"}
