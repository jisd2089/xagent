"""Wikilink extraction and generation utilities."""

from __future__ import annotations

import re
from typing import Optional

# Matches [[page]] or [[page|alias]]
_WIKILINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]")


class Wikilinker:
    """Extract and generate [[wikilinks]]."""

    @staticmethod
    def extract(text: str) -> list[str]:
        """Return all wikilink targets found in *text*, deduplicated, order-preserved."""
        seen: set[str] = set()
        result: list[str] = []
        for match in _WIKILINK_RE.finditer(text):
            target = match.group(1).strip()
            if target and target not in seen:
                seen.add(target)
                result.append(target)
        return result

    @staticmethod
    def generate(targets: list[str]) -> str:
        """Generate a Markdown list of wikilinks."""
        return "\n".join(f"- [[{t}]]" for t in targets)

    @staticmethod
    def make_link(target: str, alias: Optional[str] = None) -> str:
        """Build a single [[target]] or [[target|alias]]."""
        if alias:
            return f"[[{target}|{alias}]]"
        return f"[[{target}]]"
