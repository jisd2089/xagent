"""Hybrid Wiki searcher — text match + optional wikilink expansion."""

from __future__ import annotations

from xagent.core.wiki.models import SearchResult, WikiPage
from xagent.core.wiki.protocols import WikiStore
from xagent.core.wiki.search.graph_traverse import WikilinkGraph
from xagent.core.wiki.search.ranker import Ranker


class WikiSearcher:
    """Search compiled Wiki pages.

    Uses text matching via the store's ``search_text`` and optional
    wikilink-graph expansion.
    """

    def __init__(self, store: WikiStore, graph: WikilinkGraph | None = None):
        self.store = store
        self.graph = graph

    async def search(
        self,
        query: str,
        *,
        namespace: str = "default",
        max_results: int = 5,
        include_wikilinks: bool = False,
    ) -> list[SearchResult]:
        """Execute a hybrid search."""
        # 1. Text search via store
        pages = await self.store.search_text(query, namespace, k=max_results * 3)

        # 2. Score each page
        results: list[SearchResult] = []
        for page in pages:
            text_score = Ranker.compute_text_score(query, page.content, page.title)
            results.append(SearchResult(
                page=page,
                score=text_score,
                excerpt=page.content[:200],
                rank_factors={"text_match": text_score},
            ))

        # 3. Rank
        ranked = Ranker.rank(results)

        # 4. Wikilink expansion (optional)
        if include_wikilinks and self.graph is not None:
            ranked = await self._expand_wikilinks(ranked, namespace, max_results)

        return ranked[:max_results]

    async def _expand_wikilinks(
        self,
        results: list[SearchResult],
        namespace: str,
        max_results: int,
    ) -> list[SearchResult]:
        """Add wikilinked pages to results."""
        if self.graph is None:
            return results

        seen_ids = {r.page.page_id for r in results}
        expanded = list(results)

        for r in results:
            related = await self.graph.find_related(r.page.page_id, depth=1)
            for rel_id in related:
                if rel_id in seen_ids:
                    continue
                page = await self.store.get_page(rel_id, namespace)
                if page is not None:
                    expanded.append(SearchResult(
                        page=page,
                        score=r.score * 0.8,  # decay for related pages
                        excerpt=page.content[:200],
                        rank_factors={"wikilink_expansion": True, "source": r.page.page_id},
                    ))
                    seen_ids.add(rel_id)

        expanded.sort(key=lambda r: r.score, reverse=True)
        return expanded[:max_results]
