"""TC-V1: Knowledge Compilation — raw data → structured Wiki pages.

Value: Verify the core compilation capability — LLM synthesises multi-source
raw data into structured, human-readable Wiki pages.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from xagent.core.wiki.config import WikiConfig
from xagent.core.wiki.engine import WikiEngine
from xagent.core.wiki.models import PageLevel, PageStatus


class TestKnowledgeCompilation:
    """V1: Knowledge Compilation — the core value of Karpathy Wiki."""

    @pytest.mark.e2e
    async def test_entity_page_compilation(
        self, student_zhang_wei_records: list[dict],
        namespace: str, wiki_engine: WikiEngine,
    ):
        """Compile 7 cross-source records into entity pages.

        Verifications:
        1. At least one entity page is created
        2. .md files exist with YAML front-matter
        3. Content is synthesised knowledge, not raw data concatenation
        4. Pages contain [[wikilinks]]
        5. index.md and log.md are updated
        """
        # Execute: ingest and compile each record
        all_results = []
        for record in student_zhang_wei_records:
            result = await wiki_engine.ingest_and_compile(
                source=record["content"],
                source_type="text",
                namespace=namespace,
                metadata={"source": record["source"], "type": record["type"]},
            )
            all_results.append(result)

        # Verify 1: Entity pages exist
        pages = await wiki_engine.store.list_pages(namespace=namespace)
        assert len(pages) >= 1, "Should create at least 1 entity page"

        # Check 张伟 page specifically
        zhang_page = await wiki_engine.store.get_page("张伟", namespace)
        assert zhang_page is not None, "张伟's entity page should be created"
        assert zhang_page.level == PageLevel.ENTITY
        assert zhang_page.status == PageStatus.PUBLISHED

        # Verify 2: .md files exist with correct format
        md_path = wiki_engine.file_writer.page_path(zhang_page)
        assert md_path.exists(), ".md file should be written to disk"
        md_content = md_path.read_text(encoding="utf-8")
        assert "---" in md_content, "Should contain YAML front-matter delimiter"
        assert "title:" in md_content, "Should contain title in front-matter"
        assert "compiled_at:" in md_content, "Should contain compiled_at"
        assert "level:" in md_content, "Should contain level"

        # Verify 3: Content is synthesised knowledge, not raw concatenation
        assert "Python" in zhang_page.content or "数据分析" in zhang_page.content, \
            "Content should contain key topics from the source data"
        assert zhang_page.content.startswith("#"), \
            "Content should be structured with Markdown headings"

        # Verify 4: Contains wikilinks
        assert len(zhang_page.wikilinks) > 0, \
            "Should generate at least one [[wikilink]]"

        # Verify 5: index.md + log.md updated
        wiki_dir: Path = wiki_engine.vault.wiki_dir
        index_path = wiki_dir / namespace / "index.md"
        assert index_path.exists(), "index.md should be created"
        index_content = index_path.read_text(encoding="utf-8")
        assert "张伟" in index_content, "index.md should reference 张伟"

        log_path = wiki_dir / namespace / "log.md"
        assert log_path.exists(), "log.md should be created"
        log_content = log_path.read_text(encoding="utf-8")
        assert "COMPILE" in log_content, "log.md should record compile operations"

    @pytest.mark.e2e
    async def test_compile_result_structure(self, namespace, wiki_engine):
        """CompileResult should contain proper statistics."""
        result = await wiki_engine.ingest_and_compile(
            "张伟学习 Python 数据分析。",
            source_type="text",
            namespace=namespace,
        )

        assert result.compile_duration_ms >= 0
        total_pages = len(result.pages_created) + len(result.pages_updated)
        assert total_pages >= 1
        assert len(result.entities_discovered) >= 1
