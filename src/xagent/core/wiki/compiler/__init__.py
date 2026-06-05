"""L2 Compiler layer — entity extraction, page compilation, wikilinking."""

from xagent.core.wiki.compiler.entity_extractor import LLMEntityExtractor
from xagent.core.wiki.compiler.page_compiler import (
    ConceptPageCompiler,
    EntityPageCompiler,
)
from xagent.core.wiki.compiler.wikilinker import Wikilinker
from xagent.core.wiki.compiler.incremental import IncrementalCompiler

__all__ = [
    "ConceptPageCompiler",
    "EntityPageCompiler",
    "IncrementalCompiler",
    "LLMEntityExtractor",
    "Wikilinker",
]
