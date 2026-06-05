"""Core data models for the Wiki Engine."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import IntEnum
from typing import Optional


class PageLevel(IntEnum):
    """Wiki page hierarchy level."""

    ENTITY = 1      # Single-entity synthesis
    CONCEPT = 2     # Cross-entity synthesis
    SUMMARY = 3     # Global / domain-level summary


class PageStatus(str):
    DRAFT = "draft"
    PUBLISHED = "published"
    STALE = "stale"
    ARCHIVED = "archived"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def content_hash(text: str) -> str:
    """Deterministic content-hash: SHA-256 first 16 hex chars."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


@dataclass
class CanonicalDoc:
    """L1 output: normalised raw document."""

    doc_id: str
    content: str
    source_type: str            # "text" | "pdf" | "url" | "memory"
    source_ref: str
    metadata: dict = field(default_factory=dict)
    ingested_at: datetime = field(default_factory=_utcnow)

    @classmethod
    def from_text(cls, text: str, *, source_type: str = "text",
                  source_ref: str = "", metadata: Optional[dict] = None) -> CanonicalDoc:
        return cls(
            doc_id=content_hash(text),
            content=text,
            source_type=source_type,
            source_ref=source_ref,
            metadata=metadata or {},
        )


@dataclass
class Chunk:
    """L1 output: text segment with deterministic ID."""

    chunk_id: str
    doc_id: str
    content: str
    token_count: int
    position: int


@dataclass
class ExtractedEntity:
    """L2 intermediate: entity extracted by LLM."""

    name: str
    entity_type: str            # "person" | "concept" | "organization" | ...
    context: str = ""
    confidence: float = 0.8


@dataclass
class ExtractedRelation:
    """L2 intermediate: relation between entities."""

    source: str
    target: str
    relation_type: str = "related_to"
    context: str = ""


@dataclass
class WikiPage:
    """L2 output / L3 input: compiled Wiki page."""

    page_id: str
    title: str
    level: PageLevel
    status: str                 # PageStatus value
    content: str
    entities: list[str] = field(default_factory=list)
    wikilinks: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    compiled_at: datetime = field(default_factory=_utcnow)
    compiled_by: str = "llm"
    revision: int = 1
    token_count: int = 0
    namespace: str = "default"
    metadata: dict = field(default_factory=dict)

    @property
    def slug(self) -> str:
        return self.page_id


@dataclass
class SearchResult:
    """L4 output: search hit."""

    page: WikiPage
    score: float
    excerpt: str = ""
    rank_factors: dict = field(default_factory=dict)


@dataclass
class CompileResult:
    """Outcome of a compile operation."""

    pages_created: list[WikiPage] = field(default_factory=list)
    pages_updated: list[WikiPage] = field(default_factory=list)
    entities_discovered: list[ExtractedEntity] = field(default_factory=list)
    wikilinks_added: list[tuple[str, str]] = field(default_factory=list)
    compile_duration_ms: int = 0


@dataclass
class CompileLog:
    """Structured compile log entry."""

    timestamp: datetime = field(default_factory=_utcnow)
    operation: str = "COMPILE"      # COMPILE | INCREMENTAL | UPDATE
    namespace: str = "default"
    pages_affected: int = 0
    entities_discovered: int = 0
    duration_ms: int = 0
    details: dict = field(default_factory=dict)
