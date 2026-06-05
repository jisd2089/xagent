"""TC-V5: Human Reviewability — Obsidian compatibility.

Value: Verify Wiki output is human-readable, browsable in Obsidian, and
editable without being overwritten by subsequent compilations.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from xagent.core.wiki.engine import WikiEngine


class TestHumanReviewability:
    """V5: Human Reviewability — Markdown in Obsidian is browsable/editable."""

    @pytest.mark.e2e
    async def test_obsidian_vault_structure(
        self, namespace: str, wiki_engine: WikiEngine,
        student_zhang_wei_records: list[dict],
    ):
        """Compile data, then verify Obsidian vault structure is complete.

        Verifications:
        1. .obsidian/ directory exists with graph.json and types.json
        2. graph.json defines colour groups by level
        3. All .md files have valid YAML front-matter
        4. [[wikilinks]] follow Obsidian standard format
        5. index.md exists and references compiled pages
        """
        for record in student_zhang_wei_records[:5]:
            await wiki_engine.ingest_and_compile(
                record["content"], "text", namespace,
                metadata={"source": record["source"]},
            )

        vault_dir = wiki_engine.vault.wiki_dir / namespace

        # 1: .obsidian/ exists
        assert (vault_dir / ".obsidian").is_dir(), ".obsidian/ directory should exist"
        assert (vault_dir / ".obsidian" / "graph.json").exists()
        assert (vault_dir / ".obsidian" / "types.json").exists()

        # 2: graph.json colour groups
        graph = json.loads(
            (vault_dir / ".obsidian" / "graph.json").read_text(encoding="utf-8")
        )
        assert "colorGroups" in graph
        assert len(graph["colorGroups"]) >= 2, \
            "graph.json should define ≥ 2 colour groups"

        # 3: All .md files have valid YAML front-matter
        md_files = list(vault_dir.rglob("*.md"))
        assert len(md_files) >= 3, f"Should have ≥ 3 .md files, got {len(md_files)}"
        for md_file in md_files:
            content = md_file.read_text(encoding="utf-8")
            if md_file.name not in ("index.md", "log.md"):
                assert content.startswith("---"), \
                    f"{md_file.name} should start with YAML front-matter"
                # Find closing ---
                second_delim = content.find("---", 3)
                assert second_delim > 3, \
                    f"{md_file.name} should have closing YAML delimiter"

        # 4: [[wikilinks]] format
        all_content = "\n".join(f.read_text(encoding="utf-8") for f in md_files)
        wikilinks = re.findall(r"\[\[(.+?)\]\]", all_content)
        assert len(wikilinks) >= 1, "Should have ≥ 1 [[wikilink]]"
        for wl in wikilinks:
            assert "|" not in wl or len(wl.split("|")) == 2, \
                "Wikilink should be [[page]] or [[page|alias]] format"

        # 5: index.md references compiled pages
        index_content = (vault_dir / "index.md").read_text(encoding="utf-8")
        pages = await wiki_engine.store.list_pages(namespace=namespace)
        for page in pages:
            assert page.title in index_content or page.page_id in index_content, \
                f"index.md should reference page '{page.title}'"

    @pytest.mark.e2e
    async def test_types_json_structure(
        self, namespace: str, wiki_engine: WikiEngine,
    ):
        """types.json should define property types for Obsidian."""
        await wiki_engine.ingest_and_compile(
            "张伟学习 Python。", "text", namespace,
        )

        types_path = wiki_engine.vault.wiki_dir / namespace / ".obsidian" / "types.json"
        assert types_path.exists()
        types_data = json.loads(types_path.read_text(encoding="utf-8"))
        assert "types" in types_data
        obsidian_types = types_data["types"]
        assert "compiled_at" in obsidian_types
        assert obsidian_types["compiled_at"] == "datetime"
