"""Shared test fixtures for Wiki Engine tests."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Optional

import pytest

from xagent.core.wiki.models import (
    Chunk,
    PageLevel,
    PageStatus,
    WikiPage,
    content_hash,
)
from xagent.core.wiki.store.memory_store import InMemoryWikiStore


# ---------------------------------------------------------------------------
# Async event loop
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def event_loop():
    """Use a single event loop for the whole test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# ---------------------------------------------------------------------------
# Mock LLM
# ---------------------------------------------------------------------------


class MockLLM:
    """Configurable mock that satisfies the LLMFunc protocol."""

    def __init__(self, responses: Optional[dict[str, str]] = None):
        self._responses = responses or {}
        self._default = "mock response"
        self.call_count = 0
        self.last_prompt = ""
        self.last_system = ""

    def set_response(self, keyword: str, response: str) -> None:
        self._responses[keyword] = response

    def set_default(self, response: str) -> None:
        self._default = response

    async def __call__(
        self, prompt: str, *, system: str = "", temperature: float = 0.3
    ) -> str:
        self.call_count += 1
        self.last_prompt = prompt
        self.last_system = system

        for keyword, response in self._responses.items():
            if keyword in prompt:
                return response
        return self._default


@pytest.fixture
def mock_llm():
    return MockLLM()


# ---------------------------------------------------------------------------
# Pre-built data
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_chunks() -> list[Chunk]:
    """A few sample chunks for compiler tests."""
    return [
        Chunk(
            chunk_id=content_hash("chunk1"),
            doc_id="doc1",
            content="张伟是一名 Python 学习者，对数据分析方向感兴趣。目前在互联网公司做运营。",
            token_count=25,
            position=0,
        ),
        Chunk(
            chunk_id=content_hash("chunk2"),
            doc_id="doc1",
            content="张伟的 Python 基础测评成绩 85 分，pandas 数据处理熟练，SQL 基础薄弱。",
            token_count=22,
            position=1,
        ),
    ]


@pytest.fixture
def sample_page() -> WikiPage:
    """A sample compiled Wiki page."""
    return WikiPage(
        page_id="zhang_wei",
        title="张伟",
        level=PageLevel.ENTITY,
        status=PageStatus.PUBLISHED,
        content="张伟是一名 Python 学习者，数据分析方向。\n\n## 技能\n- Python: 85分\n- SQL: 学习中",
        entities=["张伟", "Python", "数据分析"],
        wikilinks=["SQL基础", "Python进阶"],
        sources=["doc1"],
        revision=1,
        token_count=30,
        namespace="test_ns",
    )


@pytest.fixture
def memory_store() -> InMemoryWikiStore:
    return InMemoryWikiStore()


@pytest.fixture
def tmp_wiki_dir(tmp_path: Path) -> Path:
    """A temporary wiki directory."""
    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir()
    return wiki_dir
