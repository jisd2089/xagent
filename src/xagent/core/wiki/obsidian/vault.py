"""Obsidian vault initialisation — .obsidian/ defaults."""

from __future__ import annotations

import json
from pathlib import Path

_OBSIDIAN_GRAPH = {
    "colorGroups": [
        {"query": "path:level_1", "color": {"a": 1, "rgb": 5395106}},
        {"query": "path:level_2", "color": {"a": 1, "rgb": 16744448}},
        {"query": "path:level_3", "color": {"a": 1, "rgb": 16711680}},
    ],
    "search": "",
    "tags": [],
    "attachments": True,
    "backlinks": True,
    "showGraph": True,
    "showBacklinks": True,
}

_OBSIDIAN_TYPES = {
    "types": {
        "compiled_at": "datetime",
        "entities": "tags",
        "level": "number",
        "revision": "number",
    },
    "typesAliases": {},
}


class ObsidianVault:
    """Ensure .obsidian/ default config files exist in the wiki directory."""

    def __init__(self, wiki_dir: Path):
        self.wiki_dir = wiki_dir

    def ensure_defaults(self, namespace: str = "default") -> None:
        """Write .obsidian/ config if missing (idempotent)."""
        obs_dir = self.wiki_dir / namespace / ".obsidian"
        obs_dir.mkdir(parents=True, exist_ok=True)

        self._write_if_missing(obs_dir / "graph.json", _OBSIDIAN_GRAPH)
        self._write_if_missing(obs_dir / "types.json", _OBSIDIAN_TYPES)

    @staticmethod
    def _write_if_missing(path: Path, data: dict) -> None:
        if not path.exists():
            path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
