"""L1 Ingestion layer — normalise inputs and chunk documents."""

from xagent.core.wiki.ingestion.chunker import WikiChunker
from xagent.core.wiki.ingestion.text_extractor import TextExtractor
from xagent.core.wiki.ingestion.registry import ExtractorRegistry

__all__ = ["ExtractorRegistry", "TextExtractor", "WikiChunker"]
