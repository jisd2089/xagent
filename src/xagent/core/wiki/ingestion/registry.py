"""Plugin-style extractor registry."""

from __future__ import annotations

from typing import Optional

from xagent.core.wiki.models import CanonicalDoc
from xagent.core.wiki.protocols import Extractor
from xagent.core.wiki.ingestion.text_extractor import TextExtractor


class ExtractorRegistry:
    """Registry of data-source extractors.

    New data sources are added by registering an Extractor implementation.
    """

    def __init__(self) -> None:
        self._extractors: list[Extractor] = []

    def register(self, extractor: Extractor) -> None:
        self._extractors.append(extractor)

    def find(self, source: str | bytes, metadata: dict) -> Optional[Extractor]:
        for ext in self._extractors:
            if ext.can_handle(source, metadata):
                return ext
        return None

    async def extract(self, source: str | bytes, metadata: dict) -> CanonicalDoc:
        """Find the right extractor and run it.  Raises ValueError if none matches."""
        ext = self.find(source, metadata)
        if ext is None:
            raise ValueError(
                f"No extractor found for source_type={metadata.get('source_type', '?')}"
            )
        return await ext.extract(source, metadata)

    @classmethod
    def create_default(cls) -> ExtractorRegistry:
        """Create a registry with all built-in extractors."""
        reg = cls()
        reg.register(TextExtractor())
        return reg
