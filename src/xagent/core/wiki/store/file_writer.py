"""Atomic .md file writer with YAML front-matter."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Optional

from xagent.core.wiki.models import WikiPage

_WIKI_TEMPLATE = """\
---
title: {title}
entities: {entities}
sources: {sources}
compiled_at: {compiled_at}
level: {level}
revision: {revision}
namespace: {namespace}
---

{content}

## Related
{wikilinks_section}
"""


class FileWriter:
    """Atomic .md file writer — temp file + rename guarantees no half-written state."""

    def __init__(self, wiki_dir: Path):
        self.wiki_dir = wiki_dir

    def page_path(self, page: WikiPage) -> Path:
        """Return the target file path for a page."""
        page_dir = self.wiki_dir / page.namespace / f"level_{page.level}"
        return page_dir / f"{page.slug}.md"

    def write_page(self, page: WikiPage) -> Path:
        """Write a Wiki page to disk atomically.  Returns the file path."""
        page_dir = self.wiki_dir / page.namespace / f"level_{page.level}"
        page_dir.mkdir(parents=True, exist_ok=True)
        target = page_dir / f"{page.slug}.md"

        wikilinks_section = "\n".join(f"- [[{link}]]" for link in page.wikilinks)
        content = _WIKI_TEMPLATE.format(
            title=page.title,
            entities=str(page.entities),
            sources=str(page.sources),
            compiled_at=page.compiled_at.isoformat(),
            level=page.level,
            revision=page.revision,
            namespace=page.namespace,
            content=page.content,
            wikilinks_section=wikilinks_section or "- (none)",
        )

        # Atomic write: write to temp file, then rename
        fd: Optional[int] = None
        tmp_path: Optional[str] = None
        try:
            fd, tmp_path = tempfile.mkstemp(dir=str(page_dir), suffix=".md.tmp")
            os.write(fd, content.encode("utf-8"))
            os.close(fd)
            fd = None
            os.replace(tmp_path, str(target))  # atomic on POSIX and Windows
        except Exception:
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise

        return target
