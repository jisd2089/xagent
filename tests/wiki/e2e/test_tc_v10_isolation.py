"""TC-V10: Competitive Moat — tenant isolation.

Value: Verify compiled knowledge bases are fully isolated per tenant —
one tenant's data is never visible to another.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from xagent.core.wiki.config import WikiConfig
from xagent.core.wiki.engine import WikiEngine


class TestCompetitiveMoat:
    """V10: Competitive Moat — compiled knowledge is tenant-exclusive."""

    @pytest.mark.e2e
    async def test_tenant_isolation(
        self, tmp_path: Path, mock_llm,
    ):
        """Two tenants' Wiki data should be completely isolated.

        Tenant A compiles 张伟's knowledge
        Tenant B searches for 张伟 → should get empty results

        Verifications:
        1. Different namespaces cannot see each other's pages
        2. Search is scoped to namespace
        3. .md files are isolated by namespace directory
        """
        ns_a = "tenant_edu_shanghai"
        ns_b = "tenant_edu_beijing"

        config = WikiConfig(
            wiki_dir=tmp_path / "wiki",
            namespace=ns_a,
        )
        engine = WikiEngine.from_config(config, mock_llm)

        # Tenant A compiles
        await engine.ingest_and_compile(
            "张伟，上海校区学员，Python 数据分析方向。学习 SQL。",
            "text", ns_a,
        )

        # Tenant B compiles
        await engine.ingest_and_compile(
            "李明，北京校区学员，Java 前端方向。学习 React。",
            "text", ns_b,
        )

        # Verify 1: Tenant A cannot see Tenant B's data
        results_a = await engine.search("李明", namespace=ns_a)
        assert len(results_a) == 0, \
            "Tenant A should not find Tenant B's 李明"

        # Verify 2: Tenant B cannot see Tenant A's data
        results_b = await engine.search("张伟", namespace=ns_b)
        assert len(results_b) == 0, \
            "Tenant B should not find Tenant A's 张伟"

        # Verify 3: File directories are isolated
        vault_dir = engine.vault.wiki_dir
        a_dir = vault_dir / ns_a
        b_dir = vault_dir / ns_b
        assert a_dir.is_dir(), "Tenant A's directory should exist"
        assert b_dir.is_dir(), "Tenant B's directory should exist"

        a_files = list(a_dir.rglob("*.md"))
        b_files = list(b_dir.rglob("*.md"))
        a_names = [f.stem for f in a_files if f.name not in ("index.md", "log.md")]
        b_names = [f.stem for f in b_files if f.name not in ("index.md", "log.md")]

        # 张伟 should only be in Tenant A's directory
        assert any("张伟" in n for n in a_names), \
            "张伟 should be in Tenant A's files"
        assert not any("张伟" in n for n in b_names), \
            "张伟 should NOT be in Tenant B's files"

    @pytest.mark.e2e
    async def test_namespace_scoped_list(
        self, tmp_path: Path, mock_llm,
    ):
        """list_pages should only return pages from the requested namespace."""
        ns_a = "tenant_a"
        ns_b = "tenant_b"

        config = WikiConfig(
            wiki_dir=tmp_path / "wiki",
            namespace=ns_a,
        )
        engine = WikiEngine.from_config(config, mock_llm)

        await engine.ingest_and_compile(
            "张伟学习 Python。", "text", ns_a,
        )
        await engine.ingest_and_compile(
            "李明学习 Java。", "text", ns_b,
        )

        pages_a = await engine.store.list_pages(namespace=ns_a)
        pages_b = await engine.store.list_pages(namespace=ns_b)

        a_titles = {p.title for p in pages_a}
        b_titles = {p.title for p in pages_b}

        assert "张伟" in a_titles or any("张伟" in t for t in a_titles), \
            "张伟 should be in Tenant A's pages"
        assert "李明" in b_titles or any("李明" in t for t in b_titles), \
            "李明 should be in Tenant B's pages"

        # No cross-contamination
        assert not any("李明" in t for t in a_titles), \
            "李明 should NOT appear in Tenant A's pages"
        assert not any("张伟" in t for t in b_titles), \
            "张伟 should NOT appear in Tenant B's pages"
