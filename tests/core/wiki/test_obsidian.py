"""Tests for ObsidianVault — .obsidian/ defaults."""

import json
from pathlib import Path

from xagent.core.wiki.obsidian.vault import ObsidianVault


class TestObsidianVault:
    def test_ensure_defaults_creates_obsidian_dir(self, tmp_path):
        wiki_dir = tmp_path / "wiki"
        wiki_dir.mkdir()
        vault = ObsidianVault(wiki_dir)
        vault.ensure_defaults("ns")

        obs_dir = wiki_dir / "ns" / ".obsidian"
        assert obs_dir.is_dir()
        assert (obs_dir / "graph.json").exists()
        assert (obs_dir / "types.json").exists()

    def test_graph_json_has_color_groups(self, tmp_path):
        wiki_dir = tmp_path / "wiki"
        wiki_dir.mkdir()
        vault = ObsidianVault(wiki_dir)
        vault.ensure_defaults("ns")

        graph = json.loads((wiki_dir / "ns" / ".obsidian" / "graph.json").read_text())
        assert "colorGroups" in graph
        assert len(graph["colorGroups"]) == 3

    def test_types_json_has_type_definitions(self, tmp_path):
        wiki_dir = tmp_path / "wiki"
        wiki_dir.mkdir()
        vault = ObsidianVault(wiki_dir)
        vault.ensure_defaults("ns")

        types = json.loads((wiki_dir / "ns" / ".obsidian" / "types.json").read_text())
        assert "types" in types
        assert "level" in types["types"]

    def test_idempotent(self, tmp_path):
        wiki_dir = tmp_path / "wiki"
        wiki_dir.mkdir()
        vault = ObsidianVault(wiki_dir)

        vault.ensure_defaults("ns")
        graph_path = wiki_dir / "ns" / ".obsidian" / "graph.json"
        first_content = graph_path.read_text()

        vault.ensure_defaults("ns")  # second call should not overwrite
        second_content = graph_path.read_text()
        assert first_content == second_content
