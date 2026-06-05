"""Wiki Agent tools — wiki_search and wiki_compile for xAgent tasks.

These tools are registered via @register_tool and become available to the
Agent during task execution. The Agent can use them to:
1. wiki_search — search the compiled Wiki knowledge base
2. wiki_compile — compile new raw data into Wiki pages
"""

import logging
from typing import TYPE_CHECKING, Any, Dict, List, Mapping, Optional, Type

from pydantic import BaseModel, Field

from .base import AbstractBaseTool, ToolCategory
from .factory import register_tool

if TYPE_CHECKING:
    from .config import BaseToolConfig

logger = logging.getLogger(__name__)


# Pydantic models for arguments
class WikiSearchArgs(BaseModel):
    """Arguments for wiki_search tool."""
    query: str = Field(description="Search query — describe what knowledge you need")
    namespace: str = Field(default="default", description="Wiki namespace (default: 'default')")
    max_results: int = Field(default=5, description="Maximum number of results (default: 5)")


class WikiCompileArgs(BaseModel):
    """Arguments for wiki_compile tool."""
    content: str = Field(description="Raw text content to compile into Wiki knowledge")
    namespace: str = Field(default="default", description="Wiki namespace (default: 'default')")
    source_type: str = Field(default="text", description="Source type: text, url, file (default: text)")


# Pydantic models for return types
class WikiSearchResult(BaseModel):
    """Result from wiki_search tool."""
    result: str = Field(description="Formatted search results")


class WikiCompileResult(BaseModel):
    """Result from wiki_compile tool."""
    result: str = Field(description="Compilation summary")


class WikiSearchTool(AbstractBaseTool):
    """wiki_search — search compiled Wiki knowledge."""

    def __init__(self, wiki_engine):
        self._engine = wiki_engine

    @property
    def name(self) -> str:
        return "wiki_search"

    @property
    def description(self) -> str:
        return (
            "Search the compiled Wiki knowledge base for structured knowledge pages. "
            "Wiki pages are LLM-synthesised from raw data into persistent, structured "
            "knowledge. Use this to find entity profiles, concept analyses, and "
            "cross-source insights. Returns pages with titles, content excerpts, "
            "relevance scores, and [[wikilinks]] to related pages.\n\n"
            "Use this tool when the user asks to search, query, or retrieve "
            "information from previously compiled knowledge data. "
            "搜索已编译的Wiki知识库，查找实体档案、概念分析和跨源综合洞察。"
        )

    @property
    def category(self) -> ToolCategory:
        return ToolCategory.KNOWLEDGE

    def args_type(self) -> Type[BaseModel]:
        return WikiSearchArgs

    def return_type(self) -> Type[BaseModel]:
        return WikiSearchResult

    def run_json_sync(self, args: Mapping[str, Any]) -> Any:
        import asyncio
        return asyncio.run(self.run_json_async(args))

    async def run_json_async(self, args: Mapping[str, Any]) -> Any:
        query = args.get("query", "")
        namespace = args.get("namespace", "default")
        max_results = args.get("max_results", 5)

        if not query:
            return WikiSearchResult(result="Error: query is required")

        results = await self._engine.search(
            query, namespace=namespace, max_results=max_results,
        )

        if not results:
            return WikiSearchResult(result=f"No Wiki pages found for query: '{query}'")

        output_parts = [f"Found {len(results)} Wiki page(s):\n"]
        for i, r in enumerate(results, 1):
            output_parts.append(
                f"## {i}. {r.page.title} (Level {r.page.level}, rev {r.page.revision})\n"
                f"**Score**: {r.score:.3f}\n"
                f"**Entities**: {', '.join(r.page.entities)}\n"
                f"**Wikilinks**: {', '.join(r.page.wikilinks[:5])}\n\n"
                f"{r.page.content[:500]}\n"
            )
        return WikiSearchResult(result="\n".join(output_parts))


class WikiCompileTool(AbstractBaseTool):
    """wiki_compile — compile raw data into Wiki knowledge pages."""

    def __init__(self, wiki_engine):
        self._engine = wiki_engine

    @property
    def name(self) -> str:
        return "wiki_compile"

    @property
    def description(self) -> str:
        return (
            "Compile raw text data into structured Wiki knowledge pages. "
            "The compiler extracts entities, synthesises entity pages, and "
            "auto-creates concept pages when enough related entities exist. "
            "Compiled knowledge persists and can be searched later via wiki_search.\n\n"
            "Use this tool when the user provides raw data (text, records, notes) "
            "and wants to compile/ingest it into the knowledge base. "
            "将原始文本数据编译为结构化Wiki知识页面，自动提取实体并生成知识页面。"
        )

    @property
    def category(self) -> ToolCategory:
        return ToolCategory.KNOWLEDGE

    def args_type(self) -> Type[BaseModel]:
        return WikiCompileArgs

    def return_type(self) -> Type[BaseModel]:
        return WikiCompileResult

    def run_json_sync(self, args: Mapping[str, Any]) -> Any:
        import asyncio
        return asyncio.run(self.run_json_async(args))

    async def run_json_async(self, args: Mapping[str, Any]) -> Any:
        content = args.get("content", "")
        namespace = args.get("namespace", "default")
        source_type = args.get("source_type", "text")

        if not content:
            return WikiCompileResult(result="Error: content is required")

        try:
            result = await self._engine.ingest_and_compile(
                source=content,
                source_type=source_type,
                namespace=namespace,
            )
        except Exception as e:
            return WikiCompileResult(result=f"Compilation failed: {e}")

        parts = ["Compilation complete:\n"]
        if result.pages_created:
            parts.append(
                f"- **Created** {len(result.pages_created)} page(s): "
                f"{', '.join(p.title for p in result.pages_created)}"
            )
        if result.pages_updated:
            parts.append(
                f"- **Updated** {len(result.pages_updated)} page(s): "
                f"{', '.join(p.title for p in result.pages_updated)}"
            )
        parts.append(f"- **Entities discovered**: {len(result.entities_discovered)}")
        parts.append(f"- **Wikilinks added**: {len(result.wikilinks_added)}")
        parts.append(f"- **Duration**: {result.compile_duration_ms}ms")

        return WikiCompileResult(result="\n".join(parts))


@register_tool
async def create_wiki_tools(config: "BaseToolConfig") -> List[Any]:
    """Create Wiki search and compile tools using the real LLM from config."""
    tools: List[Any] = []

    try:
        import os
        from pathlib import Path

        from ....wiki.config import WikiConfig
        from ....wiki.engine import WikiEngine

        # Get the real LLM from the task's tool configuration
        real_llm = config.get_llm()
        if real_llm is None:
            logger.warning("Wiki tools skipped: no LLM available in tool config")
            return tools

        # Bridge the BaseLLM.chat(messages) interface to the Wiki compiler's
        # expected callable: (prompt, *, system="", temperature=0.3) -> str
        async def _wiki_llm(prompt: str, *, system: str = "", temperature: float = 0.3) -> str:
            messages = []
            if system:
                messages.append({"role": "system", "content": system})
            messages.append({"role": "user", "content": prompt})
            result = await real_llm.chat(messages, temperature=temperature)
            if isinstance(result, dict):
                # Tool-call response — extract text content if present
                return result.get("content", str(result))
            return str(result)

        wiki_dir = Path(os.getenv("WIKI_DIR", "/root/.xagent/wiki"))
        wiki_config = WikiConfig(wiki_dir=wiki_dir, namespace="default")
        wiki_config.ensure_dirs()

        engine = WikiEngine.from_config(wiki_config, _wiki_llm)
        tools.append(WikiSearchTool(engine))
        tools.append(WikiCompileTool(engine))
        logger.info("Wiki tools (wiki_search, wiki_compile) created with real LLM")
    except Exception as e:
        logger.warning(f"Failed to create wiki tools: {e}")

    return tools
