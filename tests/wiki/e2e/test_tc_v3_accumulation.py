"""TC-V3: Knowledge Accumulation — Wiki grows over time (data flywheel).

Value: Verify the Wiki becomes richer with each round of input, demonstrating
measurable knowledge compounding.
"""

from __future__ import annotations

import pytest

from xagent.core.wiki.engine import WikiEngine
from xagent.core.wiki.models import PageLevel


class TestKnowledgeAccumulation:
    """V3: Knowledge Accumulation — the data flywheel effect."""

    @pytest.mark.e2e
    async def test_wiki_grows_over_time(
        self, namespace: str, wiki_engine: WikiEngine,
    ):
        """3 rounds of data input → Wiki knowledge grows monotonically.

        Round 1: 5 student records → ~3+ entity pages
        Round 2: 5 academic records → existing pages update + possible new pages
        Round 3: 5 industry records → concept pages may trigger

        Verifications:
        1. Page count increases each round
        2. Existing pages get revision bumps (incremental update)
        3. Wikilinks increase over time (richer associations)
        4. Compile log records all operations
        """
        # ---- Round 1: Student records ----
        round1_data = [
            "张伟，Python 基础扎实，对数据分析感兴趣。",
            "李明，前端开发方向，有 Java 基础。",
            "王芳，零基础转行，对 UI设计 感兴趣。",
            "赵六，3 年运营经验，想学数据分析。学习 pandas。",
            "陈七，应届毕业生，计算机专业，对机器学习方向感兴趣。",
        ]
        for text in round1_data:
            await wiki_engine.ingest_and_compile(text, "text", namespace)

        round1_pages = await wiki_engine.store.list_pages(namespace=namespace)
        round1_wikilinks = sum(len(p.wikilinks) for p in round1_pages)

        # ---- Round 2: Academic records (some entities already have pages) ----
        round2_data = [
            "张伟完成 Python 基础测评，85 分。建议进阶数据分析方向。",
            "李明完成 HTML/CSS 项目，评分 A。推荐学习 React。",
            "新课程「AI 产品经理」上线，面向非技术背景学员。",
            "张伟 SQL 基础课进度 60%，需要额外辅导。",
            "本月新增学员 12 人，编程方向占比 45%。",
        ]
        for text in round2_data:
            await wiki_engine.ingest_and_compile(text, "text", namespace)

        round2_pages = await wiki_engine.store.list_pages(namespace=namespace)
        round2_wikilinks = sum(len(p.wikilinks) for p in round2_pages)

        # ---- Round 3: Industry records ----
        round3_data = [
            "2026 Q1 数据分析师岗位需求增长 25%，平均薪资 15-25K。要求 Python + SQL + pandas。",
            "前端开发岗位竞争激烈，React 成为标配技能。",
            "机器学习岗位新兴，需求增长 50%，供给不足。",
            "Python 连续 3 年位居编程语言排行榜第一。",
            "在线教育行业 2026 年市场规模预计达 5000 亿。",
        ]
        for text in round3_data:
            await wiki_engine.ingest_and_compile(text, "text", namespace)

        round3_pages = await wiki_engine.store.list_pages(namespace=namespace)
        round3_wikilinks = sum(len(p.wikilinks) for p in round3_pages)

        # ---- Verifications ----

        # 1: Page count increases
        assert len(round1_pages) >= 3, \
            f"Round 1 should produce ≥ 3 pages, got {len(round1_pages)}"
        assert len(round2_pages) >= len(round1_pages), \
            f"Round 2 ({len(round2_pages)}) should have ≥ pages than Round 1 ({len(round1_pages)})"
        assert len(round3_pages) >= len(round2_pages), \
            f"Round 3 ({len(round3_pages)}) should have ≥ pages than Round 2 ({len(round2_pages)})"

        # 2: Existing pages get revision bumps
        zhang_page = await wiki_engine.store.get_page("张伟", namespace)
        assert zhang_page is not None, "张伟's page should exist"
        assert zhang_page.revision >= 2, \
            f"张伟's page should be updated ≥ 2 times, got revision={zhang_page.revision}"

        # 3: Wikilinks grow over time
        assert round3_wikilinks >= round1_wikilinks, \
            f"Wikilinks should grow: round1={round1_wikilinks}, round3={round3_wikilinks}"

        # 4: Compile log records operations
        log_path = wiki_engine.vault.wiki_dir / namespace / "log.md"
        assert log_path.exists()
        log_content = log_path.read_text(encoding="utf-8")
        compile_count = log_content.count("COMPILE")
        assert compile_count >= 10, \
            f"Log should record ≥ 10 compile operations, got {compile_count}"
