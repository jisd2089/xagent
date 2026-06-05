"""Tests for FileWriter — atomic writes, YAML front-matter, directory structure."""

from pathlib import Path

from xagent.core.wiki.models import PageLevel, PageStatus, WikiPage
from xagent.core.wiki.store.file_writer import FileWriter


class TestWritePage:
    async def test_creates_md_file(self, tmp_wiki_dir, sample_page):
        writer = FileWriter(tmp_wiki_dir)
        path = writer.write_page(sample_page)
        assert path.exists()
        assert path.suffix == ".md"

    async def test_correct_directory_structure(self, tmp_wiki_dir, sample_page):
        writer = FileWriter(tmp_wiki_dir)
        path = writer.write_page(sample_page)
        # Should be: wiki_dir / namespace / level_N / slug.md
        expected_dir = tmp_wiki_dir / sample_page.namespace / f"level_{sample_page.level}"
        assert path.parent == expected_dir

    async def test_file_contains_front_matter(self, tmp_wiki_dir, sample_page):
        writer = FileWriter(tmp_wiki_dir)
        path = writer.write_page(sample_page)
        content = path.read_text(encoding="utf-8")
        assert content.startswith("---")
        assert "title:" in content
        assert "compiled_at:" in content
        assert "level:" in content
        assert "revision:" in content

    async def test_file_contains_body(self, tmp_wiki_dir, sample_page):
        writer = FileWriter(tmp_wiki_dir)
        path = writer.write_page(sample_page)
        content = path.read_text(encoding="utf-8")
        assert "张伟是一名 Python 学习者" in content

    async def test_file_contains_wikilinks(self, tmp_wiki_dir, sample_page):
        writer = FileWriter(tmp_wiki_dir)
        path = writer.write_page(sample_page)
        content = path.read_text(encoding="utf-8")
        assert "[[SQL基础]]" in content
        assert "[[Python进阶]]" in content

    async def test_no_tmp_file_left(self, tmp_wiki_dir, sample_page):
        writer = FileWriter(tmp_wiki_dir)
        writer.write_page(sample_page)
        tmp_files = list(tmp_wiki_dir.rglob("*.tmp"))
        assert tmp_files == []

    async def test_overwrite_existing(self, tmp_wiki_dir, sample_page):
        writer = FileWriter(tmp_wiki_dir)
        writer.write_page(sample_page)
        sample_page.revision = 2
        sample_page.content = "Updated content"
        path = writer.write_page(sample_page)
        content = path.read_text(encoding="utf-8")
        assert "Updated content" in content
        assert "revision: 2" in content

    async def test_empty_wikilinks_section(self, tmp_wiki_dir):
        page = WikiPage(
            page_id="no_links", title="No Links",
            level=PageLevel.ENTITY, status=PageStatus.PUBLISHED,
            content="Some content", wikilinks=[], namespace="ns",
        )
        writer = FileWriter(tmp_wiki_dir)
        path = writer.write_page(page)
        content = path.read_text(encoding="utf-8")
        assert "## Related" in content
        assert "(none)" in content
