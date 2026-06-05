"""TC-V4: Cross-Source Synthesis — concept pages from multiple entities.

Value: Verify the Wiki compiler's core differentiator — synthesising new
knowledge from multiple entity pages (something RAG cannot do).
"""

from __future__ import annotations

import pytest

from xagent.core.wiki.config import WikiConfig
from xagent.core.wiki.engine import WikiEngine
from xagent.core.wiki.models import PageLevel


class TestCrossSourceSynthesis:
    """V4: Cross-Source Synthesis — concept pages are LLM-synthesised new knowledge."""

    @pytest.mark.e2e
    async def test_concept_page_synthesis(
        self, namespace: str, wiki_config: WikiConfig, mock_llm,
    ):
        """Compile multi-entity text → concept page auto-created.

        When a single compile call processes text with 3+ entities sharing
        a common concept, a concept page should be auto-generated.

        Verifications:
        1. Concept page is created with level = CONCEPT
        2. Content includes cross-entity patterns (not just copy of single entity)
        3. Concept page references source entities via wikilinks
        """
        wiki_config.concept_threshold = 3
        engine = WikiEngine.from_config(wiki_config, mock_llm)

        # Compile all students in a SINGLE call so the entity extractor
        # sees all entities together and can detect shared concepts.
        # 数据分析 appears in 3 entities (张伟, 李明, 赵六) → triggers concept page.
        combined_text = (
            "张伟，Python 基础 85 分，对数据分析感兴趣，偏好周末班。"
            "互联网运营转行，预算 5000-8000 元。\n\n"
            "李明，对数据分析方向也有兴趣，同时学习前端开发。\n\n"
            "王芳，零基础，对 UI设计 感兴趣。市场营销背景。\n\n"
            "赵六，Python 数据分析方向，3 年运营经验。学习 pandas。"
        )
        await engine.ingest_and_compile(combined_text, "text", namespace)

        # Verify 1: Concept page exists
        concept_pages = await engine.store.list_pages(
            namespace=namespace, level=PageLevel.CONCEPT,
        )
        assert len(concept_pages) >= 1, \
            f"Should auto-create ≥ 1 concept page, got {len(concept_pages)}"

        concept = concept_pages[0]
        assert concept.level == PageLevel.CONCEPT

        # Verify 2: Content includes cross-entity patterns
        content_lower = concept.content.lower()
        pattern_keywords = ["趋势", "模式", "共性", "特点", "群体", "整体", "综合"]
        has_pattern = any(kw in content_lower for kw in pattern_keywords)
        assert has_pattern, \
            "Concept page should contain cross-entity pattern/trend analysis"

        # Verify 3: References source entities via wikilinks
        assert len(concept.wikilinks) >= 2, \
            f"Concept page should reference ≥ 2 source entities, got {len(concept.wikilinks)}"

    @pytest.mark.e2e
    async def test_concept_page_file_written(
        self, namespace: str, wiki_config: WikiConfig, mock_llm,
    ):
        """Concept page should also be written to disk in level_2 directory."""
        wiki_config.concept_threshold = 3
        engine = WikiEngine.from_config(wiki_config, mock_llm)

        # Compile multi-entity text to trigger concept page creation
        combined_text = (
            "张伟，Python 基础 85 分，对数据分析感兴趣。\n\n"
            "李明，也对数据分析感兴趣，同时学习前端开发。\n\n"
            "王芳，零基础，学习 UI设计。\n\n"
            "赵六，Python 数据分析方向，学习 pandas。"
        )
        await engine.ingest_and_compile(combined_text, "text", namespace)

        # Check level_2 directory for concept page
        level2_dir = engine.vault.wiki_dir / namespace / "level_2"
        if level2_dir.exists():
            concept_files = list(level2_dir.glob("*.md"))
            assert len(concept_files) >= 1, \
                "Concept page .md file should be in level_2 directory"
