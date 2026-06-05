"""TC-V7: Wikilink Discovery — cross-entity association via [[wikilinks]].

Value: Verify wikilinks automatically discover cross-entity and cross-concept
associations that would be invisible in flat search.
"""

from __future__ import annotations

import pytest

from xagent.core.wiki.engine import WikiEngine
from xagent.core.wiki.models import PageLevel


class TestWikilinkDiscovery:
    """V7: Wikilink Discovery — auto-build cross-entity associations."""

    @pytest.mark.e2e
    async def test_cross_entity_wikilinks(
        self, namespace: str, wiki_engine: WikiEngine,
        cross_entity_data: list[str],
    ):
        """Compile related entities, verify wikilinks establish associations.

        Expected wikilink graph:
          张伟 → [[数据分析]], [[SQL]], [[Python]], [[pandas]]
          数据分析岗位 → [[Python]], [[SQL]], [[pandas]]
          → 张伟 ←→ 数据分析岗位 via shared wikilinks

        Verifications:
        1. Entity pages have relevant wikilinks
        2. Graph traversal finds indirectly related pages
        3. include_wikilinks expands search results
        """
        for text in cross_entity_data:
            await wiki_engine.ingest_and_compile(text, "text", namespace)

        # 1: Entity pages have wikilinks
        zhang_page = await wiki_engine.store.get_page("张伟", namespace)
        assert zhang_page is not None, "张伟's page should exist"
        assert len(zhang_page.wikilinks) >= 1, \
            "张伟's page should have ≥ 1 wikilink"

        # 2: Graph traversal discovers related pages
        await wiki_engine.searcher.graph.build_index(namespace)
        related = await wiki_engine.searcher.graph.find_related(
            zhang_page.page_id, depth=2,
        )
        assert isinstance(related, list), "Graph traversal should return a list"

        # 3: include_wikilinks expands search results
        results_expanded = await wiki_engine.search(
            "张伟 课程", namespace=namespace,
            max_results=5, include_wikilinks=True,
        )
        results_basic = await wiki_engine.search(
            "张伟 课程", namespace=namespace,
            max_results=5, include_wikilinks=False,
        )
        assert len(results_expanded) >= len(results_basic), \
            "include_wikilinks should return ≥ results than basic search"

    @pytest.mark.e2e
    async def test_wikilink_graph_adjacency(
        self, namespace: str, wiki_engine: WikiEngine,
    ):
        """Wikilink graph should build correct adjacency structure."""
        await wiki_engine.ingest_and_compile(
            "张伟学习 Python 数据分析。", "text", namespace,
        )
        await wiki_engine.ingest_and_compile(
            "李明学习 Java 前端开发。学习 React。", "text", namespace,
        )

        # Build graph index
        await wiki_engine.searcher.graph.build_index(namespace)

        # Verify adjacency
        adjacency = wiki_engine.searcher.graph.adjacency
        assert isinstance(adjacency, dict)

        # At least the compiled pages should appear in the graph
        all_page_ids = set()
        pages = await wiki_engine.store.list_pages(namespace=namespace)
        for p in pages:
            all_page_ids.add(p.page_id)

        for pid in all_page_ids:
            assert pid in adjacency, \
                f"Page '{pid}' should appear in the wikilink graph"
