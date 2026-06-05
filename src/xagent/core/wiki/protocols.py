"""Protocol / ABC interfaces for the Wiki Engine.

All inter-layer contracts live here so that implementations depend on
abstractions, not concrete classes.
"""

from __future__ import annotations

from typing import Optional, Protocol, runtime_checkable

from xagent.core.wiki.models import (
    CanonicalDoc,
    Chunk,
    CompileLog,
    CompileResult,
    PageLevel,
    WikiPage,
)


# ---------------------------------------------------------------------------
# L1: Extractor
# ---------------------------------------------------------------------------


@runtime_checkable
class Extractor(Protocol):
    """Data-source extractor — normalise arbitrary input to CanonicalDoc."""

    @property
    def source_type(self) -> str: ...

    def can_handle(self, source: str | bytes, metadata: dict) -> bool: ...

    async def extract(self, source: str | bytes, metadata: dict) -> CanonicalDoc: ...


# ---------------------------------------------------------------------------
# L2: LLM function
# ---------------------------------------------------------------------------


@runtime_checkable
class LLMFunc(Protocol):
    """LLM call protocol — decouple compiler from model implementation."""

    async def __call__(
        self,
        prompt: str,
        *,
        system: str = "",
        temperature: float = 0.3,
    ) -> str: ...


# ---------------------------------------------------------------------------
# L2: Page compiler
# ---------------------------------------------------------------------------


@runtime_checkable
class PageCompiler(Protocol):
    """Page compiler strategy — different strategies per level."""

    @property
    def level(self) -> PageLevel: ...


# ---------------------------------------------------------------------------
# L3: Wiki store
# ---------------------------------------------------------------------------


@runtime_checkable
class WikiStore(Protocol):
    """Storage protocol — decouple compiler from storage backend."""

    async def save_page(self, page: WikiPage) -> None: ...

    async def get_page(self, page_id: str, namespace: str = "default") -> Optional[WikiPage]: ...

    async def list_pages(
        self,
        *,
        namespace: str = "default",
        level: Optional[PageLevel] = None,
    ) -> list[WikiPage]: ...

    async def find_pages_by_entity(
        self, entity: str, namespace: str = "default"
    ) -> list[WikiPage]: ...

    async def search_text(
        self, query: str, namespace: str = "default", k: int = 5
    ) -> list[WikiPage]: ...

    async def save_compile_log(self, log: CompileLog) -> None: ...
