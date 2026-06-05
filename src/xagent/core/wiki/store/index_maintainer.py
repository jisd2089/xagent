"""Maintain index.md and log.md in the wiki directory."""

from __future__ import annotations

from pathlib import Path

from xagent.core.wiki.models import CompileLog, WikiPage


class IndexMaintainer:
    """Keep ``index.md`` and ``log.md`` up to date."""

    def __init__(self, wiki_dir: Path):
        self.wiki_dir = wiki_dir

    async def update(self, page: WikiPage) -> None:
        """Update index.md and log.md after a page is saved."""
        self._update_index(page)
        self._append_log(page)

    async def update_from_log(self, log: CompileLog) -> None:
        """Append a structured compile-log line to log.md."""
        log_path = self.wiki_dir / log.namespace / "log.md"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        line = (
            f"- [{log.timestamp.isoformat()}] {log.operation} "
            f"pages={log.pages_affected} entities={log.entities_discovered} "
            f"duration={log.duration_ms}ms\n"
        )
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(line)

    # ---- internal ----

    def _update_index(self, page: WikiPage) -> None:
        index_path = self.wiki_dir / page.namespace / "index.md"
        index_path.parent.mkdir(parents=True, exist_ok=True)

        # Read existing entries to deduplicate
        existing_lines: list[str] = []
        if index_path.exists():
            existing_lines = index_path.read_text(encoding="utf-8").splitlines()

        entry = f"- [[{page.title}]] (Level {page.level}, rev {page.revision})"
        # Remove old entry for same page_id
        marker = f"[[{page.title}]]"
        filtered = [ln for ln in existing_lines if marker not in ln]
        filtered.append(entry)

        header = f"# Wiki Index — {page.namespace}\n\n"
        body = "\n".join(filtered) + "\n"
        index_path.write_text(header + body, encoding="utf-8")

    def _append_log(self, page: WikiPage) -> None:
        log_path = self.wiki_dir / page.namespace / "log.md"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        line = (
            f"- [{page.compiled_at.isoformat()}] COMPILE "
            f"page={page.page_id} level={page.level} rev={page.revision}\n"
        )
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(line)
