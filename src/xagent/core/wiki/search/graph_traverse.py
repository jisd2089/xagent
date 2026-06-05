"""Wikilink graph traversal — BFS over page relationships."""

from __future__ import annotations

from typing import Optional

from xagent.core.wiki.models import WikiPage
from xagent.core.wiki.protocols import WikiStore


class WikilinkGraph:
    """Adjacency-list graph built from wikilinks.

    Supports BFS traversal for related-page discovery.
    """

    def __init__(self, store: Optional[WikiStore] = None):
        self.store = store
        self._adjacency: dict[str, set[str]] = {}

    async def build_index(self, namespace: str = "default") -> None:
        """Build adjacency list from all pages in the namespace."""
        if self.store is None:
            return
        pages = await self.store.list_pages(namespace=namespace)
        self._adjacency.clear()
        for page in pages:
            self._adjacency[page.page_id] = set(page.wikilinks)

    def add_page(self, page: WikiPage) -> None:
        """Update adjacency for a single page (incremental)."""
        self._adjacency[page.page_id] = set(page.wikilinks)

    async def find_related(self, page_id: str, depth: int = 1) -> list[str]:
        """BFS from *page_id* up to *depth* hops. Returns related page IDs."""
        visited: set[str] = set()
        queue: list[tuple[str, int]] = [(page_id, 0)]
        related: list[str] = []

        while queue:
            current, d = queue.pop(0)
            if current in visited or d > depth:
                continue
            visited.add(current)
            if current != page_id:
                related.append(current)
            for neighbor in self._adjacency.get(current, set()):
                if neighbor not in visited:
                    queue.append((neighbor, d + 1))

        return related

    @property
    def adjacency(self) -> dict[str, set[str]]:
        return dict(self._adjacency)
