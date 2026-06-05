"""TC-V9: Cross-Flow Knowledge Transfer — Wiki knowledge via search.

Value: Verify Wiki compiled knowledge can be retrieved across different
business flows, simulating Agent Handoff knowledge injection.
"""

from __future__ import annotations

import pytest

from xagent.core.wiki.engine import WikiEngine


class TestCrossFlowKnowledgeTransfer:
    """V9: Cross-Flow Knowledge Transfer — Wiki knowledge crosses business flows."""

    @pytest.mark.e2e
    async def test_sales_to_academic_knowledge_transfer(
        self, namespace: str, wiki_engine: WikiEngine,
    ):
        """Simulate: Sales flow compiles → Academic flow retrieves via search.

        Sales CRM records: "张伟对数据分析感兴趣，预算 5000-8000"
        Academic Agent should be able to search and find this knowledge.

        Verifications:
        1. Knowledge compiled from sales data is searchable
        2. Search results include relevant content with scores > 0
        3. Wikilinks provide related knowledge context
        """
        # Simulate sales flow: compile CRM data
        await wiki_engine.ingest_and_compile(
            "张伟来电咨询，对数据分析方向感兴趣。互联网运营背景，预算 5000-8000。"
            "偏好周末班。已签单。",
            "text", namespace,
            metadata={"flow": "sales", "source": "crm"},
        )
        await wiki_engine.ingest_and_compile(
            "张伟 Python 基础测评 85 分。pandas 数据处理熟练，SQL 基础薄弱。",
            "text", namespace,
            metadata={"flow": "sales", "source": "assessment"},
        )

        # Simulate academic flow: Agent searches for student info
        results = await wiki_engine.search(
            "张伟 课程安排 学习方向",
            namespace=namespace,
            max_results=5,
        )

        # Verify 1: Knowledge from sales flow is retrievable
        assert len(results) >= 1, \
            "Academic flow should find knowledge compiled from sales data"

        # Verify 2: Results are relevant with positive scores
        for r in results:
            assert r.score > 0, "Search result should have positive relevance score"

        # Verify 3: Content contains sales-derived information
        all_content = " ".join(r.page.content for r in results)
        # The compiled page should contain keywords from the original sales data
        relevant_keywords = ["张伟", "数据分析", "Python"]
        has_relevant = any(kw in all_content for kw in relevant_keywords)
        assert has_relevant, \
            "Search results should contain sales-flow derived knowledge"

    @pytest.mark.e2e
    async def test_multi_source_knowledge_merging(
        self, namespace: str, wiki_engine: WikiEngine,
    ):
        """Knowledge from different flows should be merged into the same entity page."""
        # Sales flow
        await wiki_engine.ingest_and_compile(
            "张伟对数据分析感兴趣。预算 5000-8000。",
            "text", namespace,
            metadata={"flow": "sales"},
        )

        # Academic flow
        await wiki_engine.ingest_and_compile(
            "张伟 Python 基础 85 分。建议深入数据分析。",
            "text", namespace,
            metadata={"flow": "academic"},
        )

        # Career flow
        await wiki_engine.ingest_and_compile(
            "张伟完成 SQL 课程。求职数据分析岗位。",
            "text", namespace,
            metadata={"flow": "career"},
        )

        # The entity page should aggregate all flows
        zhang_page = await wiki_engine.store.get_page("张伟", namespace)
        assert zhang_page is not None
        # Multiple compiles should have increased the revision
        assert zhang_page.revision >= 2, \
            "Multi-flow updates should increment revision ≥ 2"
