"""In-memory Wiki store — suitable for unit tests and prototyping."""

from __future__ import annotations

from typing import Optional

from xagent.core.wiki.models import (
    CompileLog,
    PageLevel,
    WikiPage,
)


class InMemoryWikiStore:
    """Dict-backed Wiki store for tests.  Satisfies the WikiStore protocol."""

    def __init__(self) -> None:
        self._pages: dict[str, WikiPage] = {}          # key = "{namespace}:{page_id}"
        self._logs: list[CompileLog] = []

    @staticmethod
    def _key(page_id: str, namespace: str) -> str:
        return f"{namespace}:{page_id}"

    async def save_page(self, page: WikiPage) -> None:
        self._pages[self._key(page.page_id, page.namespace)] = page

    async def get_page(
        self, page_id: str, namespace: str = "default"
    ) -> Optional[WikiPage]:
        return self._pages.get(self._key(page_id, namespace))

    async def list_pages(
        self,
        *,
        namespace: str = "default",
        level: Optional[PageLevel] = None,
    ) -> list[WikiPage]:
        results = []
        for page in self._pages.values():
            if page.namespace != namespace:
                continue
            if level is not None and page.level != level:
                continue
            results.append(page)
        return results

    async def find_pages_by_entity(
        self, entity: str, namespace: str = "default"
    ) -> list[WikiPage]:
        entity_lower = entity.lower()
        results = []
        for page in self._pages.values():
            if page.namespace != namespace:
                continue
            if any(e.lower() == entity_lower for e in page.entities):
                results.append(page)
        return results

    async def search_text(
        self, query: str, namespace: str = "default", k: int = 5
    ) -> list[WikiPage]:
        """Simple term-level text search for testing."""
        query_lower = query.lower()
        terms = query_lower.split()
        results = []
        for page in self._pages.values():
            if page.namespace != namespace:
                continue
            content_lower = page.content.lower()
            title_lower = page.title.lower()
            # Match if any query term is found in title or content
            if any(t in content_lower or t in title_lower for t in terms):
                results.append(page)
        return results[:k]

    async def save_compile_log(self, log: CompileLog) -> None:
        self._logs.append(log)

    @property
    def compile_logs(self) -> list[CompileLog]:
        return list(self._logs)

    @property
    def page_count(self) -> int:
        return len(self._pages)
