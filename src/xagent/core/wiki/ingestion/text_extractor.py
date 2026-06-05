"""Plain text / Markdown extractor."""

from __future__ import annotations

from xagent.core.wiki.models import CanonicalDoc, content_hash


class TextExtractor:
    """Extract CanonicalDoc from plain text or Markdown strings."""

    @property
    def source_type(self) -> str:
        return "text"

    def can_handle(self, source: str | bytes, metadata: dict) -> bool:
        if isinstance(source, bytes):
            try:
                source.decode("utf-8")
                return True
            except UnicodeDecodeError:
                return False
        src_type = metadata.get("source_type", "text")
        return src_type in ("text", "markdown", "md")

    async def extract(self, source: str | bytes, metadata: dict) -> CanonicalDoc:
        if isinstance(source, bytes):
            source = source.decode("utf-8")
        return CanonicalDoc(
            doc_id=content_hash(source),
            content=source,
            source_type=metadata.get("source_type", "text"),
            source_ref=metadata.get("source_ref", ""),
            metadata=metadata,
        )
