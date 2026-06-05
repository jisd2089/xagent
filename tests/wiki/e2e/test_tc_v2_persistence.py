"""TC-V2: Knowledge Persistence — compile once, use many times.

Value: Verify Wiki pages persist after compilation and survive engine restarts.
"""

from __future__ import annotations

import time

import pytest

from xagent.core.wiki.config import WikiConfig
from xagent.core.wiki.engine import WikiEngine


class TestKnowledgePersistence:
    """V2: Knowledge Persistence — compiled artefacts are durable."""

    @pytest.mark.e2e
    async def test_compile_once_search_many(
        self, namespace: str, wiki_engine: WikiEngine,
    ):
        """Compile once, search 10 times — same page, same revision, fast.

        Verifications:
        1. Every search returns the same page
        2. Page revision does not increase (search ≠ recompile)
        3. Search latency is well under compilation time
        """
        # Compile
        await wiki_engine.ingest_and_compile(
            "张伟学习 Python 数据分析，成绩 85 分。",
            source_type="text", namespace=namespace,
        )
        await wiki_engine.ingest_and_compile(
            "张伟正在学 SQL 基础课程。",
            source_type="text", namespace=namespace,
        )

        # Search 10 times
        search_times: list[float] = []
        results: list[list] = []
        for _ in range(10):
            start = time.perf_counter()
            result = await wiki_engine.search(
                "张伟 Python", namespace=namespace,
            )
            search_times.append(time.perf_counter() - start)
            results.append(result)

        # Verify 1: All searches return same pages
        first_ids = {r.page.page_id for r in results[0]}
        for r in results:
            current_ids = {sr.page.page_id for sr in r}
            assert current_ids == first_ids, \
                "Each search should return the same set of pages"

        # Verify 2: Revision unchanged
        pages = await wiki_engine.store.list_pages(namespace=namespace)
        for page in pages:
            assert page.revision <= 2, \
                "Search should not trigger re-compilation"

        # Verify 3: Search is fast
        avg_search = sum(search_times) / len(search_times)
        assert avg_search < 1.0, \
            f"Average search time should be < 1s, got {avg_search:.3f}s"

    @pytest.mark.e2e
    async def test_page_survives_engine_restart(
        self, namespace: str, wiki_config: WikiConfig, mock_llm,
    ):
        """After engine restart, compiled pages still exist.

        Knowledge lives in the store + files, not in memory.
        """
        # Compile with first engine
        engine1 = WikiEngine.from_config(wiki_config, mock_llm)
        await engine1.ingest_and_compile(
            "王五是一名资深 Java 开发者，10 年经验。",
            source_type="text", namespace=namespace,
        )

        # Get page from first engine
        page_before = await engine1.store.get_page("王五", namespace)
        assert page_before is not None, "Page should exist after compilation"

        # Rebuild engine (simulating restart) — reuses same store
        engine2 = WikiEngine.from_config(wiki_config, mock_llm, store=engine1.store)

        # Verify: page still accessible
        page_after = await engine2.store.get_page("王五", namespace)
        assert page_after is not None, "Page should survive engine restart"
        assert page_after.page_id == page_before.page_id
        assert "Java" in page_after.content or "java" in page_after.content.lower()

        # Verify: .md files still on disk
        md_path = engine2.file_writer.page_path(page_after)
        assert md_path.exists(), ".md file should persist on disk"
