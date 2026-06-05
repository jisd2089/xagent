"""Wiki Engine configuration."""

from __future__ import annotations

from pathlib import Path
from dataclasses import dataclass, field


@dataclass
class WikiConfig:
    """Wiki Engine configuration — all tunables in one place."""

    # Storage
    wiki_dir: Path = field(default_factory=lambda: Path("workspace/wiki"))
    lancedb_dir: Path = field(default_factory=lambda: Path("workspace/lancedb"))

    # LLM
    wiki_llm_model: str = "claude-sonnet-4-20250514"
    embedding_model: str = "text-embedding-3-small"

    # Compilation parameters
    chunk_max_tokens: int = 3000
    chunk_overlap_tokens: int = 200
    concept_threshold: int = 3
    max_compile_concurrency: int = 5

    # Tenant
    namespace: str = "default"

    # Obsidian
    obsidian_defaults: bool = True

    def ensure_dirs(self) -> None:
        """Create output directories if they don't exist."""
        self.wiki_dir.mkdir(parents=True, exist_ok=True)
        self.lancedb_dir.mkdir(parents=True, exist_ok=True)
