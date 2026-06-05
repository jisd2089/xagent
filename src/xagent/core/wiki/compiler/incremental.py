"""Incremental compiler — Karpathy rule #7.

New data triggers:
  1. Entity extraction
  2. Per-entity page update or creation
  3. Concept-page trigger when same-concept entity pages ≥ threshold
  4. Compile-log update
"""

from __future__ import annotations

import time
from collections import Counter
from typing import Optional

from xagent.core.wiki.compiler.entity_extractor import LLMEntityExtractor
from xagent.core.wiki.compiler.page_compiler import (
    ConceptPageCompiler,
    EntityPageCompiler,
)
from xagent.core.wiki.models import (
    Chunk,
    CompileLog,
    CompileResult,
    ExtractedEntity,
    PageLevel,
    WikiPage,
)
from xagent.core.wiki.protocols import WikiStore


class IncrementalCompiler:
    """Orchestrate incremental compilation over a WikiStore."""

    def __init__(
        self,
        entity_extractor: LLMEntityExtractor,
        entity_compiler: EntityPageCompiler,
        concept_compiler: ConceptPageCompiler,
        store: WikiStore,
        concept_threshold: int = 3,
    ):
        self.entity_extractor = entity_extractor
        self.entity_compiler = entity_compiler
        self.concept_compiler = concept_compiler
        self.store = store
        self.concept_threshold = concept_threshold

    async def compile(self, chunks: list[Chunk], namespace: str) -> CompileResult:
        start = time.monotonic()

        # Step 1: Extract entities
        entities, _relations = await self.entity_extractor.extract(chunks)

        pages_created: list[WikiPage] = []
        pages_updated: list[WikiPage] = []
        wikilinks_added: list[tuple[str, str]] = []

        # Step 2: Compile / update entity pages
        for entity in entities:
            existing_pages = await self.store.find_pages_by_entity(
                entity.name, namespace
            )
            existing_page = existing_pages[0] if existing_pages else None

            page = await self.entity_compiler.compile(
                entity.name, chunks, existing_page, namespace=namespace
            )
            await self.store.save_page(page)

            if existing_page:
                pages_updated.append(page)
            else:
                pages_created.append(page)

            wikilinks_added.extend(
                (page.page_id, link) for link in page.wikilinks
            )

        # Step 3: Check concept-page triggers
        concept_groups = self._group_entities_by_concept(entities)
        for concept in concept_groups:
            # Find entity pages that reference this concept via wikilinks
            all_entity_pages = await self.store.list_pages(
                namespace=namespace, level=PageLevel.ENTITY,
            )
            concept_pages = [
                p for p in all_entity_pages
                if concept in p.wikilinks or concept in p.content
            ]
            if len(concept_pages) >= self.concept_threshold:
                # Check if concept page already exists
                existing_concept = await self.store.get_page(
                    f"concept_{concept.replace(' ', '_').lower()}", namespace
                )
                if existing_concept is None:
                    concept_page = await self.concept_compiler.compile(
                        concept, concept_pages, namespace=namespace
                    )
                    await self.store.save_page(concept_page)
                    pages_created.append(concept_page)

        duration_ms = int((time.monotonic() - start) * 1000)

        # Step 4: Write compile log
        log = CompileLog(
            operation="COMPILE" if pages_created else "INCREMENTAL",
            namespace=namespace,
            pages_affected=len(pages_created) + len(pages_updated),
            entities_discovered=len(entities),
            duration_ms=duration_ms,
        )
        await self.store.save_compile_log(log)

        return CompileResult(
            pages_created=pages_created,
            pages_updated=pages_updated,
            entities_discovered=entities,
            wikilinks_added=wikilinks_added,
            compile_duration_ms=duration_ms,
        )

    def _group_entities_by_concept(self, entities: list[ExtractedEntity]) -> list[str]:
        """Find shared concept names across entity contexts.

        Scans each entity's context text for other entity names that co-occur.
        Returns concept names that appear in ≥ threshold entity contexts.
        """
        entity_names = {e.name for e in entities}
        concept_counts: Counter[str] = Counter()
        for entity in entities:
            text = entity.context
            for name in entity_names:
                if name != entity.name and name in text:
                    concept_counts[name] += 1
        return [name for name, count in concept_counts.items()
                if count >= self.concept_threshold]
