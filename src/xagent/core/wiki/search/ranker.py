"""Search result ranker — combines multiple scoring factors."""

from __future__ import annotations

from xagent.core.wiki.models import SearchResult, PageLevel


class Ranker:
    """Score and rank search results by multiple factors."""

    # Level boost weights: higher-level pages get a small boost
    LEVEL_BOOST = {
        PageLevel.ENTITY: 1.0,
        PageLevel.CONCEPT: 1.1,
        PageLevel.SUMMARY: 1.2,
    }

    @classmethod
    def rank(cls, results: list[SearchResult]) -> list[SearchResult]:
        """Sort results by score descending, applying level boost."""
        for r in results:
            boost = cls.LEVEL_BOOST.get(r.page.level, 1.0)
            r.score *= boost
            r.rank_factors["level_boost"] = boost
        results.sort(key=lambda r: r.score, reverse=True)
        return results

    @classmethod
    def compute_text_score(cls, query: str, page_content: str, page_title: str) -> float:
        """Simple text-match score based on query term frequency."""
        query_lower = query.lower()
        content_lower = page_content.lower()
        title_lower = page_title.lower()

        terms = query_lower.split()
        if not terms:
            return 0.0

        content_hits = sum(1 for t in terms if t in content_lower)
        title_hits = sum(1 for t in terms if t in title_lower)

        # Title matches are worth 2× content matches
        raw = (content_hits + title_hits * 2) / (len(terms) * 3)
        return min(1.0, raw)
