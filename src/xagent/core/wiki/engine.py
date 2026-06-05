"""WikiEngine — the single entry-point that orchestrates all six layers."""

from __future__ import annotations

from pathlib import Path

from xagent.core.wiki.compiler.entity_extractor import LLMEntityExtractor
from xagent.core.wiki.compiler.incremental import IncrementalCompiler
from xagent.core.wiki.compiler.page_compiler import (
    ConceptPageCompiler,
    EntityPageCompiler,
)
from xagent.core.wiki.config import WikiConfig
from xagent.core.wiki.ingestion.chunker import WikiChunker
from xagent.core.wiki.ingestion.registry import ExtractorRegistry
from xagent.core.wiki.models import (
    CanonicalDoc,
    CompileResult,
    SearchResult,
)
from xagent.core.wiki.obsidian.vault import ObsidianVault
from xagent.core.wiki.protocols import LLMFunc, WikiStore
from xagent.core.wiki.search.graph_traverse import WikilinkGraph
from xagent.core.wiki.search.searcher import WikiSearcher
from xagent.core.wiki.store.file_writer import FileWriter
from xagent.core.wiki.store.index_maintainer import IndexMaintainer
from xagent.core.wiki.store.memory_store import InMemoryWikiStore


class WikiEngine:
    """Facade that wires together all six layers.

    Usage::

        engine = WikiEngine.from_config(config, llm_func)
        result = await engine.ingest_and_compile("some text", "text", "default")
        hits   = await engine.search("query", namespace="default")
    """

    def __init__(
        self,
        registry: ExtractorRegistry,
        chunker: WikiChunker,
        compiler: IncrementalCompiler,
        store: WikiStore,
        searcher: WikiSearcher,
        vault: ObsidianVault,
        file_writer: FileWriter | None = None,
        index_maintainer: IndexMaintainer | None = None,
    ):
        self.registry = registry
        self.chunker = chunker
        self.compiler = compiler
        self.store = store
        self.searcher = searcher
        self.vault = vault
        self.file_writer = file_writer
        self.index_maintainer = index_maintainer

    @classmethod
    def from_config(
        cls,
        config: WikiConfig,
        llm: LLMFunc,
        *,
        store: WikiStore | None = None,
    ) -> WikiEngine:
        """Build a fully-wired engine from configuration.

        If *store* is not provided, an ``InMemoryWikiStore`` is used
        (suitable for testing; swap for PostgresStore in production).
        """
        registry = ExtractorRegistry.create_default()
        chunker = WikiChunker(
            max_tokens=config.chunk_max_tokens,
            overlap_tokens=config.chunk_overlap_tokens,
        )

        # Compilers
        entity_extractor = LLMEntityExtractor(llm)
        entity_compiler = EntityPageCompiler(
            llm, namespace=config.namespace, model_name=config.wiki_llm_model
        )
        concept_compiler = ConceptPageCompiler(
            llm, namespace=config.namespace, model_name=config.wiki_llm_model
        )

        # Store
        wiki_store = store or InMemoryWikiStore()

        compiler = IncrementalCompiler(
            entity_extractor,
            entity_compiler,
            concept_compiler,
            wiki_store,
            concept_threshold=config.concept_threshold,
        )

        # Search
        graph = WikilinkGraph(wiki_store)
        searcher = WikiSearcher(wiki_store, graph)

        # Obsidian + files
        vault = ObsidianVault(config.wiki_dir)
        file_writer = FileWriter(config.wiki_dir)
        index_maintainer = IndexMaintainer(config.wiki_dir)

        return cls(
            registry=registry,
            chunker=chunker,
            compiler=compiler,
            store=wiki_store,
            searcher=searcher,
            vault=vault,
            file_writer=file_writer,
            index_maintainer=index_maintainer,
        )

    async def ingest_and_compile(
        self,
        source: str | bytes,
        source_type: str,
        namespace: str,
        metadata: dict | None = None,
    ) -> CompileResult:
        """End-to-end: input → canonicalize → chunk → compile → persist."""
        meta = dict(metadata or {})
        meta.setdefault("source_type", source_type)

        # 1. Extract
        doc: CanonicalDoc = await self.registry.extract(source, meta)

        # 2. Chunk
        chunks = self.chunker.chunk(doc)

        # 3. Compile
        result = await self.compiler.compile(chunks, namespace)

        # 4. Write files + update index (best-effort)
        if self.file_writer:
            for page in result.pages_created + result.pages_updated:
                self.file_writer.write_page(page)
        if self.index_maintainer:
            for page in result.pages_created + result.pages_updated:
                await self.index_maintainer.update(page)

        # 5. Obsidian defaults
        self.vault.ensure_defaults(namespace)

        # 6. Rebuild wikilink graph
        if self.searcher.graph:
            await self.searcher.graph.build_index(namespace)

        return result

    async def search(
        self,
        query: str,
        *,
        namespace: str = "default",
        max_results: int = 5,
        include_wikilinks: bool = False,
    ) -> list[SearchResult]:
        """Search compiled Wiki pages."""
        return await self.searcher.search(
            query,
            namespace=namespace,
            max_results=max_results,
            include_wikilinks=include_wikilinks,
        )
