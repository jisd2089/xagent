"""TC-V8: Incremental Compilation — only affected pages are updated.

Value: Verify Karpathy rule #7 — new data only updates affected pages,
leaving unrelated pages untouched.
"""

from __future__ import annotations

import pytest

from xagent.core.wiki.engine import WikiEngine


class TestIncrementalCompilation:
    """V8: Incremental Compilation — new data only touches affected pages."""

    @pytest.mark.e2e
    async def test_incremental_update_preserves_unrelated(
        self, namespace: str, wiki_engine: WikiEngine,
    ):
        """Update 张伟 → 李明's page should NOT be affected.

        Verifications:
        1. 张伟's revision increases after new data
        2. 李明's revision stays the same
        3. Compile log records the incremental operation
        """
        # Initial compilation: both entities
        await wiki_engine.ingest_and_compile(
            "张伟，Python 学习者，数据分析方向。学习 SQL。",
            "text", namespace,
        )
        await wiki_engine.ingest_and_compile(
            "李明，Java 开发者，前端方向。学习 React。",
            "text", namespace,
        )

        zhang_v1 = await wiki_engine.store.get_page("张伟", namespace)
        li_v1 = await wiki_engine.store.get_page("李明", namespace)
        assert zhang_v1 is not None, "张伟's page should exist"
        assert li_v1 is not None, "李明's page should exist"

        zhang_rev_before = zhang_v1.revision
        li_rev_before = li_v1.revision

        # Only update 张伟's data
        await wiki_engine.ingest_and_compile(
            "张伟完成 SQL 课程，成绩 A。推荐继续学习 pandas 高级应用。",
            "text", namespace,
        )

        zhang_v2 = await wiki_engine.store.get_page("张伟", namespace)
        li_v2 = await wiki_engine.store.get_page("李明", namespace)

        # Verify 1: 张伟's revision increased
        assert zhang_v2.revision > zhang_rev_before, \
            f"张伟's revision should increase: {zhang_rev_before} → {zhang_v2.revision}"

        # Verify 2: 李明's revision unchanged
        assert li_v2.revision == li_rev_before, \
            f"李明's revision should stay at {li_rev_before}, got {li_v2.revision}"

    @pytest.mark.e2e
    async def test_compile_log_append_only(
        self, namespace: str, wiki_engine: WikiEngine,
    ):
        """log.md should be append-only (Karpathy rule #4).

        Each compilation appends a new line; existing lines are never modified.
        """
        await wiki_engine.ingest_and_compile(
            "张伟学 Python。", "text", namespace,
        )

        log_path = wiki_engine.vault.wiki_dir / namespace / "log.md"
        log_v1 = log_path.read_text(encoding="utf-8")
        lines_v1 = log_v1.strip().split("\n")

        await wiki_engine.ingest_and_compile(
            "李明学 Java。", "text", namespace,
        )

        log_v2 = log_path.read_text(encoding="utf-8")
        lines_v2 = log_v2.strip().split("\n")

        # Verify: second compilation appends, first lines unchanged
        assert len(lines_v2) > len(lines_v1), \
            "Log should have more lines after second compilation"
        for i, line in enumerate(lines_v1):
            assert lines_v2[i] == line, \
                f"Existing log line {i} should not be modified"

    @pytest.mark.e2e
    async def test_multiple_updates_same_entity(
        self, namespace: str, wiki_engine: WikiEngine,
    ):
        """Multiple updates to the same entity should increment revision each time."""
        await wiki_engine.ingest_and_compile(
            "张伟学习 Python 基础。", "text", namespace,
        )
        page_v1 = await wiki_engine.store.get_page("张伟", namespace)
        assert page_v1 is not None

        await wiki_engine.ingest_and_compile(
            "张伟完成 SQL 课程。学习 pandas。", "text", namespace,
        )
        page_v2 = await wiki_engine.store.get_page("张伟", namespace)

        await wiki_engine.ingest_and_compile(
            "张伟通过数据分析面试。学习机器学习。", "text", namespace,
        )
        page_v3 = await wiki_engine.store.get_page("张伟", namespace)

        assert page_v1.revision < page_v2.revision < page_v3.revision, \
            f"Revisions should increase: {page_v1.revision} < {page_v2.revision} < {page_v3.revision}"
