"""Tests for IndexMaintainer — index.md and log.md maintenance."""

from pathlib import Path

from xagent.core.wiki.models import PageLevel, PageStatus, WikiPage
from xagent.core.wiki.store.index_maintainer import IndexMaintainer


class TestIndexMaintainer:
    async def test_creates_index_md(self, tmp_path):
        wiki_dir = tmp_path / "wiki"
        wiki_dir.mkdir()
        maintainer = IndexMaintainer(wiki_dir)

        page = WikiPage(
            page_id="test", title="Test Page",
            level=PageLevel.ENTITY, status=PageStatus.PUBLISHED,
            content="content", namespace="ns", revision=1,
        )
        await maintainer.update(page)

        index_path = wiki_dir / "ns" / "index.md"
        assert index_path.exists()
        content = index_path.read_text(encoding="utf-8")
        assert "Test Page" in content
        assert "[[Test Page]]" in content

    async def test_creates_log_md(self, tmp_path):
        wiki_dir = tmp_path / "wiki"
        wiki_dir.mkdir()
        maintainer = IndexMaintainer(wiki_dir)

        page = WikiPage(
            page_id="test", title="Test",
            level=PageLevel.ENTITY, status=PageStatus.PUBLISHED,
            content="content", namespace="ns",
        )
        await maintainer.update(page)

        log_path = wiki_dir / "ns" / "log.md"
        assert log_path.exists()
        content = log_path.read_text(encoding="utf-8")
        assert "COMPILE" in content

    async def test_log_is_append_only(self, tmp_path):
        wiki_dir = tmp_path / "wiki"
        wiki_dir.mkdir()
        maintainer = IndexMaintainer(wiki_dir)

        page1 = WikiPage(
            page_id="a", title="A", level=PageLevel.ENTITY,
            status=PageStatus.PUBLISHED, content="c1", namespace="ns",
        )
        await maintainer.update(page1)

        log_path = wiki_dir / "ns" / "log.md"
        lines_v1 = log_path.read_text(encoding="utf-8").strip().split("\n")

        page2 = WikiPage(
            page_id="b", title="B", level=PageLevel.ENTITY,
            status=PageStatus.PUBLISHED, content="c2", namespace="ns",
        )
        await maintainer.update(page2)

        lines_v2 = log_path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines_v2) > len(lines_v1)
        # Original lines preserved
        for i, line in enumerate(lines_v1):
            assert lines_v2[i] == line

    async def test_index_deduplicates(self, tmp_path):
        wiki_dir = tmp_path / "wiki"
        wiki_dir.mkdir()
        maintainer = IndexMaintainer(wiki_dir)

        page = WikiPage(
            page_id="test", title="Test", level=PageLevel.ENTITY,
            status=PageStatus.PUBLISHED, content="c", namespace="ns",
            revision=1,
        )
        await maintainer.update(page)

        page.revision = 2
        await maintainer.update(page)

        index_path = wiki_dir / "ns" / "index.md"
        content = index_path.read_text(encoding="utf-8")
        # Should appear only once
        assert content.count("[[Test]]") == 1
        assert "rev 2" in content
