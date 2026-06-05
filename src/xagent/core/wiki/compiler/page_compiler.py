"""Page compilers — entity pages and concept pages."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from xagent.core.wiki.compiler.wikilinker import Wikilinker
from xagent.core.wiki.ingestion.chunker import WikiChunker
from xagent.core.wiki.models import (
    Chunk,
    PageLevel,
    PageStatus,
    WikiPage,
)
from xagent.core.wiki.protocols import LLMFunc


def _slugify(name: str) -> str:
    """Convert a name to a URL-safe slug."""
    return name.strip().replace(" ", "_").lower()


class EntityPageCompiler:
    """Compile an entity page — synthesise all information about one entity."""

    level = PageLevel.ENTITY

    _CREATE_PROMPT = """\
你是一个知识编译器。请综合以下关于"{entity}"的信息，生成一个结构化 Wiki 页面。

要求:
1. 综合所有信息，生成结构化的知识（不是原始数据拼接）
2. 使用 [[wikilink]] 引用相关概念和实体
3. 包含关键事实、洞察和可操作建议
4. 在末尾 Related 部分列出关联页面

源信息:
{text}"""

    _UPDATE_PROMPT = """\
你是一个知识编译器。以下是关于"{entity}"的已有 Wiki 页面和新增信息。
请将新信息综合进已有页面，保持结构一致，增量更新。

已有页面 (revision {revision}):
---
{existing_content}
---

新增信息:
---
{new_text}
---

要求:
1. 合并新信息到已有结构中
2. 更新或新增 [[wikilink]] 引用
3. 返回更新后的完整页面内容"""

    def __init__(self, llm: LLMFunc, namespace: str = "default",
                 model_name: str = "llm"):
        self.llm = llm
        self.namespace = namespace
        self.model_name = model_name

    async def compile(
        self,
        entity_name: str,
        chunks: list[Chunk],
        existing_page: Optional[WikiPage] = None,
        namespace: Optional[str] = None,
    ) -> WikiPage:
        combined = "\n---\n".join(c.content for c in chunks)
        ns = namespace or self.namespace

        if existing_page:
            prompt = self._UPDATE_PROMPT.format(
                entity=entity_name,
                revision=existing_page.revision,
                existing_content=existing_page.content,
                new_text=combined,
            )
        else:
            prompt = self._CREATE_PROMPT.format(entity=entity_name, text=combined)

        content = await self.llm(prompt, system="你是知识编译器。", temperature=0.3)
        wikilinks = Wikilinker.extract(content)

        return WikiPage(
            page_id=_slugify(entity_name),
            title=entity_name,
            level=PageLevel.ENTITY,
            status=PageStatus.PUBLISHED,
            content=content,
            entities=[entity_name],
            wikilinks=wikilinks,
            sources=list({c.doc_id for c in chunks}),
            compiled_at=datetime.now(timezone.utc),
            compiled_by=self.model_name,
            revision=(existing_page.revision + 1) if existing_page else 1,
            token_count=WikiChunker._estimate_tokens(content),
            namespace=ns,
        )


class ConceptPageCompiler:
    """Compile a concept page — cross-entity synthesis (the core differentiator)."""

    level = PageLevel.CONCEPT

    _PROMPT = """\
你是一个知识编译器。请综合以下关于"{concept}"的多个实体信息，
生成一个概念级 Wiki 页面。

要求:
1. 发现跨实体的模式和趋势
2. 提取可操作的洞察
3. 使用 [[wikilink]] 引用源实体页面
4. 在 Related 部分列出关联的概念

实体信息:
{all_context}"""

    def __init__(self, llm: LLMFunc, namespace: str = "default",
                 model_name: str = "llm"):
        self.llm = llm
        self.namespace = namespace
        self.model_name = model_name

    async def compile(
        self,
        concept: str,
        entity_pages: list[WikiPage],
        existing_page: Optional[WikiPage] = None,
        namespace: Optional[str] = None,
    ) -> WikiPage:
        ns = namespace or self.namespace
        all_context = "\n\n".join(
            f"=== {p.title} (Level {p.level}) ===\n{p.content}"
            for p in entity_pages
        )
        prompt = self._PROMPT.format(concept=concept, all_context=all_context)
        content = await self.llm(prompt, system="你是知识编译器。", temperature=0.3)
        wikilinks = Wikilinker.extract(content)

        return WikiPage(
            page_id=f"concept_{_slugify(concept)}",
            title=f"概念: {concept}",
            level=PageLevel.CONCEPT,
            status=PageStatus.PUBLISHED,
            content=content,
            entities=[p.title for p in entity_pages],
            wikilinks=wikilinks,
            sources=[p.page_id for p in entity_pages],
            compiled_at=datetime.now(timezone.utc),
            compiled_by=self.model_name,
            revision=1,
            token_count=WikiChunker._estimate_tokens(content),
            namespace=ns,
        )
