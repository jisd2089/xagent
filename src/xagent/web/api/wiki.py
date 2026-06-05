"""Wiki HTTP API — FastAPI router for Karpathy Obsidian-Wiki Engine.

Endpoints:
  POST /api/wiki/compile          — trigger incremental compilation
  POST /api/wiki/search           — search compiled Wiki pages
  GET  /api/wiki/page/{page_id}   — get a single Wiki page
  GET  /api/wiki/pages            — list all Wiki pages
  GET  /api/wiki/stats/{ns}       — Wiki statistics
  GET  /api/wiki/index/{ns}       — get index.md content
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from ..auth_dependencies import get_current_user
from ..models.user import User

logger = logging.getLogger(__name__)

wiki_router = APIRouter(prefix="/api/wiki", tags=["wiki"])


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class WikiCompileRequest(BaseModel):
    source: str = Field(..., description="Raw text / URL / file content to compile")
    source_type: str = Field("text", description="Source type: text | url | file")
    namespace: str = Field("default", description="Tenant namespace")
    metadata: dict = Field(default_factory=dict, description="Source-specific metadata")


class WikiCompileResponse(BaseModel):
    pages_created: int
    pages_updated: int
    entities_discovered: int
    wikilinks_added: int
    compile_duration_ms: int
    created_titles: list[str] = []
    updated_titles: list[str] = []


class WikiSearchRequest(BaseModel):
    query: str = Field(..., description="Search query")
    namespace: str = Field("default", description="Tenant namespace")
    max_results: int = Field(5, ge=1, le=50)
    include_wikilinks: bool = Field(False, description="Expand via wikilink graph")


class WikiSearchHit(BaseModel):
    page_id: str
    title: str
    level: int
    score: float
    excerpt: str
    entities: list[str]
    wikilinks: list[str]
    revision: int
    compiled_at: str


class WikiSearchResponse(BaseModel):
    hits: list[WikiSearchHit]
    total: int
    query_time_ms: float


class WikiPageResponse(BaseModel):
    page_id: str
    title: str
    level: int
    status: str
    content: str
    entities: list[str]
    wikilinks: list[str]
    sources: list[str]
    compiled_at: str
    compiled_by: str
    revision: int
    token_count: int
    namespace: str


class WikiPageListItem(BaseModel):
    page_id: str
    title: str
    level: int
    status: str
    revision: int
    entities: list[str]
    wikilinks_count: int
    compiled_at: str
    namespace: str


class WikiStatsResponse(BaseModel):
    namespace: str
    total_pages: int
    entity_pages: int
    concept_pages: int
    summary_pages: int
    total_entities: int
    total_wikilinks: int
    last_compiled_at: str | None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_wiki_engine(request: Request):
    """Get WikiEngine from app state."""
    engine = getattr(request.app.state, "wiki_engine", None)
    if engine is None:
        raise HTTPException(status_code=503, detail="Wiki Engine not initialized")
    return engine


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@wiki_router.post("/compile", response_model=WikiCompileResponse)
async def compile_wiki(
    req: WikiCompileRequest,
    request: Request,
    _user: User = Depends(get_current_user),
):
    """Trigger incremental compilation of raw data into Wiki pages."""
    engine = _get_wiki_engine(request)

    try:
        result = await engine.ingest_and_compile(
            source=req.source,
            source_type=req.source_type,
            namespace=req.namespace,
            metadata=req.metadata,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Wiki compile error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Compilation failed: {str(e)}")

    return WikiCompileResponse(
        pages_created=len(result.pages_created),
        pages_updated=len(result.pages_updated),
        entities_discovered=len(result.entities_discovered),
        wikilinks_added=len(result.wikilinks_added),
        compile_duration_ms=result.compile_duration_ms,
        created_titles=[p.title for p in result.pages_created],
        updated_titles=[p.title for p in result.pages_updated],
    )


@wiki_router.post("/search", response_model=WikiSearchResponse)
async def search_wiki(
    req: WikiSearchRequest,
    request: Request,
    _user: User = Depends(get_current_user),
):
    """Search compiled Wiki pages."""
    engine = _get_wiki_engine(request)

    import time
    start = time.perf_counter()

    results = await engine.search(
        req.query,
        namespace=req.namespace,
        max_results=req.max_results,
        include_wikilinks=req.include_wikilinks,
    )

    elapsed_ms = (time.perf_counter() - start) * 1000

    hits = [
        WikiSearchHit(
            page_id=r.page.page_id,
            title=r.page.title,
            level=r.page.level,
            score=round(r.score, 4),
            excerpt=r.excerpt[:300],
            entities=r.page.entities,
            wikilinks=r.page.wikilinks,
            revision=r.page.revision,
            compiled_at=r.page.compiled_at.isoformat(),
        )
        for r in results
    ]

    return WikiSearchResponse(
        hits=hits,
        total=len(hits),
        query_time_ms=round(elapsed_ms, 2),
    )


@wiki_router.get("/page/{page_id}", response_model=WikiPageResponse)
async def get_page(
    page_id: str,
    namespace: str = Query("default"),
    request: Request = None,
    _user: User = Depends(get_current_user),
):
    """Get a single Wiki page by ID."""
    engine = _get_wiki_engine(request)
    page = await engine.store.get_page(page_id, namespace)

    if page is None:
        raise HTTPException(status_code=404, detail=f"Page '{page_id}' not found")

    return WikiPageResponse(
        page_id=page.page_id,
        title=page.title,
        level=page.level,
        status=page.status,
        content=page.content,
        entities=page.entities,
        wikilinks=page.wikilinks,
        sources=page.sources,
        compiled_at=page.compiled_at.isoformat(),
        compiled_by=page.compiled_by,
        revision=page.revision,
        token_count=page.token_count,
        namespace=page.namespace,
    )


@wiki_router.get("/pages", response_model=list[WikiPageListItem])
async def list_pages(
    namespace: str = Query("default"),
    level: int | None = Query(None, description="1=entity, 2=concept, 3=summary"),
    request: Request = None,
    _user: User = Depends(get_current_user),
):
    """List Wiki pages with optional level filter."""
    engine = _get_wiki_engine(request)

    from xagent.core.wiki.models import PageLevel

    level_enum = PageLevel(level) if level is not None else None
    pages = await engine.store.list_pages(namespace=namespace, level=level_enum)

    return [
        WikiPageListItem(
            page_id=p.page_id,
            title=p.title,
            level=p.level,
            status=p.status,
            revision=p.revision,
            entities=p.entities,
            wikilinks_count=len(p.wikilinks),
            compiled_at=p.compiled_at.isoformat(),
            namespace=p.namespace,
        )
        for p in pages
    ]


@wiki_router.get("/stats/{namespace}", response_model=WikiStatsResponse)
async def get_stats(
    namespace: str,
    request: Request = None,
    _user: User = Depends(get_current_user),
):
    """Wiki statistics: page counts, entity counts, wikilink counts."""
    engine = _get_wiki_engine(request)

    from xagent.core.wiki.models import PageLevel

    all_pages = await engine.store.list_pages(namespace=namespace)
    entity_pages = [p for p in all_pages if p.level == PageLevel.ENTITY]
    concept_pages = [p for p in all_pages if p.level == PageLevel.CONCEPT]
    summary_pages = [p for p in all_pages if p.level == PageLevel.SUMMARY]

    all_entities: set[str] = set()
    total_wikilinks = 0
    last_compiled = None
    for p in all_pages:
        all_entities.update(p.entities)
        total_wikilinks += len(p.wikilinks)
        if last_compiled is None or p.compiled_at > last_compiled:
            last_compiled = p.compiled_at

    return WikiStatsResponse(
        namespace=namespace,
        total_pages=len(all_pages),
        entity_pages=len(entity_pages),
        concept_pages=len(concept_pages),
        summary_pages=len(summary_pages),
        total_entities=len(all_entities),
        total_wikilinks=total_wikilinks,
        last_compiled_at=last_compiled.isoformat() if last_compiled else None,
    )


@wiki_router.get("/index/{namespace}")
async def get_index(
    namespace: str,
    request: Request = None,
    _user: User = Depends(get_current_user),
):
    """Get the wiki/index.md content."""
    engine = _get_wiki_engine(request)
    index_path = engine.vault.wiki_dir / namespace / "index.md"

    if not index_path.exists():
        raise HTTPException(status_code=404, detail="index.md not found")

    return {"namespace": namespace, "content": index_path.read_text(encoding="utf-8")}
