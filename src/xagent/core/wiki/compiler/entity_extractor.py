"""LLM-driven entity and relation extraction — no graph DB middleware."""

from __future__ import annotations

import json
import re
from typing import Optional

from xagent.core.wiki.models import Chunk, ExtractedEntity, ExtractedRelation
from xagent.core.wiki.protocols import LLMFunc

_ENTITY_EXTRACT_PROMPT = """\
从以下文本中提取关键实体和关系。

要求:
1. 提取所有重要实体（人名、组织、概念、技术、事件等）
2. 提取实体间的关系
3. 返回严格 JSON 格式

返回格式:
{{
  "entities": [
    {{"name": "实体名", "type": "person|concept|organization|event|technology",
     "context": "该实体在文中的上下文"}}
  ],
  "relations": [
    {{"source": "源实体", "target": "目标实体",
     "type": "关系类型", "context": "关系上下文"}}
  ]
}}

文本:
{text}"""

_ENTITY_EXTRACT_SYSTEM = "你是一个精准的实体和关系提取器。只返回 JSON，不要多余解释。"


class LLMEntityExtractor:
    """Extract entities and relations from text chunks using an LLM."""

    def __init__(self, llm: LLMFunc):
        self.llm = llm

    async def extract(
        self, chunks: list[Chunk]
    ) -> tuple[list[ExtractedEntity], list[ExtractedRelation]]:
        """Run extraction over the first ≤10 chunks."""
        combined = "\n---\n".join(c.content for c in chunks[:10])
        response = await self.llm(
            _ENTITY_EXTRACT_PROMPT.format(text=combined),
            system=_ENTITY_EXTRACT_SYSTEM,
            temperature=0.1,
        )
        return self.parse_response(response)

    # ---- helpers (public for testability) ----

    @staticmethod
    def parse_response(response: str) -> tuple[list[ExtractedEntity], list[ExtractedRelation]]:
        """Parse LLM JSON response with fault tolerance."""
        data = _extract_json(response)
        if data is None:
            return [], []

        entities = [
            ExtractedEntity(
                name=e["name"],
                entity_type=e.get("type", "unknown"),
                context=e.get("context", ""),
                confidence=0.8,
            )
            for e in data.get("entities", [])
            if "name" in e and e["name"].strip()
        ]
        relations = [
            ExtractedRelation(
                source=r["source"],
                target=r["target"],
                relation_type=r.get("type", "related_to"),
                context=r.get("context", ""),
            )
            for r in data.get("relations", [])
            if "source" in r and "target" in r
        ]
        return entities, relations


def _extract_json(text: str) -> Optional[dict]:
    """Best-effort JSON extraction from LLM output."""
    # Try fenced code block first
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    raw = match.group(1) if match else text.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    # Fallback: find outermost { … }
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    return None
