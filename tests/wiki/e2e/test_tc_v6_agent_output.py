"""TC-V6: Agent Output Improvement — Wiki search enriches Agent responses.

Value: Verify Wiki compiled knowledge significantly improves Agent output
quality (L1 framework-level → L2/L3 actionable/closed-loop).
"""

from __future__ import annotations

import time

import pytest

from xagent.core.wiki.engine import WikiEngine


class TestAgentOutputImprovement:
    """V6: Agent Output Improvement — Wiki knowledge elevates Agent quality."""

    @pytest.mark.e2e
    async def test_wiki_enhanced_course_recommendation(
        self, namespace: str, wiki_engine: WikiEngine,
    ):
        """Simulate Agent calling wiki_search for course recommendation.

        Scenario: "帮我推荐适合学员张伟的编程课程"

        Without Wiki (L1): generic advice
        With Wiki (L2-L3): specific data (scores, cohort cases, market data)

        Verifications:
        1. Search results contain specific data points
        2. Results include wikilinks for related knowledge
        3. Search latency < 1s (does not slow Agent response)
        """
        # Prepare: compile Zhang Wei's knowledge
        zhang_data = [
            "张伟，Python 基础测评 85 分，对数据分析感兴趣。互联网运营转行。",
            "张伟正在学习 SQL 基础，进度 60%。教师建议往数据分析方向深入。",
            "同背景学员（运营转数据分析）3 人: 2 人选进阶数据分析课成功，1 人选机器学习退课。",
            "2026 Q1 数据分析师薪资 15-25K，要求 Python+SQL+pandas。",
        ]
        for text in zhang_data:
            await wiki_engine.ingest_and_compile(text, "text", namespace)

        # Execute: simulate Agent calling wiki_search
        results = await wiki_engine.search(
            "张伟 编程课程推荐 学习路径",
            namespace=namespace,
            max_results=5,
        )

        # Verify 1: Search results contain specific data
        assert len(results) >= 1, "Should return search results"
        all_content = " ".join(r.page.content for r in results)

        specific_keywords = ["Python", "数据分析", "SQL", "张伟"]
        has_specific = any(kw in all_content for kw in specific_keywords)
        assert has_specific, "Search results should contain specific student data"

        # Verify 2: Wikilinks provide related knowledge
        all_wikilinks: list[str] = []
        for r in results:
            all_wikilinks.extend(r.page.wikilinks)
        assert len(all_wikilinks) >= 1, \
            "Results should have wikilinks for related knowledge"

        # Verify 3: Latency acceptable
        start = time.perf_counter()
        await wiki_engine.search("张伟 课程", namespace=namespace)
        latency = time.perf_counter() - start
        assert latency < 1.0, f"Search latency should be < 1s, got {latency:.3f}s"

    @pytest.mark.e2e
    async def test_search_result_quality(
        self, namespace: str, wiki_engine: WikiEngine,
    ):
        """Search results should have scores and excerpts."""
        await wiki_engine.ingest_and_compile(
            "张伟学习 Python 数据分析。", "text", namespace,
        )

        results = await wiki_engine.search("张伟", namespace=namespace)
        assert len(results) >= 1

        for r in results:
            assert r.score > 0, "Each result should have a positive score"
            assert len(r.excerpt) > 0, "Each result should have an excerpt"
            assert r.page.page_id, "Each result should reference a page"
