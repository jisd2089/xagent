"""Tests for WikiEngine — end-to-end pipeline with mocked LLM."""

import json
from pathlib import Path

import pytest

from xagent.core.wiki.config import WikiConfig
from xagent.core.wiki.engine import WikiEngine
from xagent.core.wiki.models import PageLevel


class TestEngineFromConfig:
    def test_creates_engine(self, tmp_path):
        config = WikiConfig(wiki_dir=tmp_path / "wiki", namespace="test")
        engine = WikiEngine.from_config(config, mock_llm_func)
        assert engine.store is not None
        assert engine.compiler is not None
        assert engine.searcher is not None


class TestIngestAndCompile:
    async def test_basic_pipeline(self, tmp_path):
        """End-to-end: text → chunks → entities → wiki page."""
        config = WikiConfig(
            wiki_dir=tmp_path / "wiki",
            namespace="test",
        )
        llm = MockLLMForEngine()
        engine = WikiEngine.from_config(config, llm)

        result = await engine.ingest_and_compile(
            "张伟是一名 Python 学习者，对数据分析感兴趣。",
            source_type="text",
            namespace="test",
        )

        assert result.compile_duration_ms >= 0
        # Should have created or discovered at least one page
        total_pages = len(result.pages_created) + len(result.pages_updated)
        assert total_pages >= 1

    async def test_compiled_page_is_searchable(self, tmp_path):
        """After compilation, the page should be findable via search."""
        config = WikiConfig(wiki_dir=tmp_path / "wiki", namespace="test")
        llm = MockLLMForEngine()
        engine = WikiEngine.from_config(config, llm)

        await engine.ingest_and_compile(
            "张伟学习 Python 数据分析。",
            source_type="text",
            namespace="test",
        )

        results = await engine.search("张伟", namespace="test")
        assert len(results) >= 1

    async def test_md_files_created(self, tmp_path):
        """Compiled pages should produce .md files on disk."""
        config = WikiConfig(wiki_dir=tmp_path / "wiki", namespace="test")
        llm = MockLLMForEngine()
        engine = WikiEngine.from_config(config, llm)

        await engine.ingest_and_compile(
            "李明是前端开发者，擅长 React。",
            source_type="text",
            namespace="test",
        )

        # Check that .md files were created
        md_files = list((tmp_path / "wiki").rglob("*.md"))
        assert len(md_files) >= 1

    async def test_obsidian_defaults_created(self, tmp_path):
        """Engine should create .obsidian/ defaults."""
        config = WikiConfig(wiki_dir=tmp_path / "wiki", namespace="test")
        llm = MockLLMForEngine()
        engine = WikiEngine.from_config(config, llm)

        await engine.ingest_and_compile(
            "测试内容。", source_type="text", namespace="test"
        )

        obs_dir = tmp_path / "wiki" / "test" / ".obsidian"
        assert obs_dir.is_dir()
        assert (obs_dir / "graph.json").exists()

    async def test_index_md_created(self, tmp_path):
        """Engine should create index.md."""
        config = WikiConfig(wiki_dir=tmp_path / "wiki", namespace="test")
        llm = MockLLMForEngine()
        engine = WikiEngine.from_config(config, llm)

        await engine.ingest_and_compile(
            "王五学习机器学习。", source_type="text", namespace="test"
        )

        index_path = tmp_path / "wiki" / "test" / "index.md"
        assert index_path.exists()

    async def test_log_md_created(self, tmp_path):
        """Engine should append to log.md."""
        config = WikiConfig(wiki_dir=tmp_path / "wiki", namespace="test")
        llm = MockLLMForEngine()
        engine = WikiEngine.from_config(config, llm)

        await engine.ingest_and_compile(
            "赵六学SQL。", source_type="text", namespace="test"
        )

        log_path = tmp_path / "wiki" / "test" / "log.md"
        assert log_path.exists()
        content = log_path.read_text(encoding="utf-8")
        assert "COMPILE" in content


class TestSearch:
    async def test_search_returns_results(self, tmp_path):
        config = WikiConfig(wiki_dir=tmp_path / "wiki", namespace="test")
        llm = MockLLMForEngine()
        engine = WikiEngine.from_config(config, llm)

        await engine.ingest_and_compile(
            "张伟学Python。", source_type="text", namespace="test"
        )

        results = await engine.search("Python", namespace="test", max_results=5)
        assert isinstance(results, list)

    async def test_search_empty_namespace(self, tmp_path):
        config = WikiConfig(wiki_dir=tmp_path / "wiki", namespace="test")
        llm = MockLLMForEngine()
        engine = WikiEngine.from_config(config, llm)

        results = await engine.search("anything", namespace="empty_ns")
        assert results == []


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _entity_json() -> str:
    return json.dumps({
        "entities": [
            {"name": "张伟", "type": "person", "context": "学员"},
            {"name": "Python", "type": "technology", "context": "编程语言"},
        ],
        "relations": [
            {"source": "张伟", "target": "Python", "type": "learns"},
        ],
    }, ensure_ascii=False)


def _page_content(entity: str) -> str:
    return (
        f"# {entity}\n\n"
        f"关于 {entity} 的综合知识页面。\n\n"
        f"## 关键事实\n- {entity} 是重要的知识实体\n\n"
        f"## Related\n- [[相关概念]]\n"
    )


class MockLLMForEngine:
    """A mock LLM that returns appropriate responses for each compiler stage."""

    def __init__(self):
        self.call_count = 0

    async def __call__(self, prompt, *, system="", temperature=0.3):
        self.call_count += 1
        # Entity extraction stage
        if "提取" in prompt and "实体" in prompt:
            return _entity_json()
        # Page compilation stage
        if "综合" in prompt or "编译" in prompt:
            # Extract entity name from prompt
            for marker in ['关于"', '关于"']:
                if marker in prompt:
                    rest = prompt[prompt.index(marker) + len(marker):]
                    name = rest.split('"')[0] if '"' in rest else "Entity"
                    return _page_content(name)
            return _page_content("知识实体")
        return _page_content("默认实体")


async def mock_llm_func(prompt, *, system="", temperature=0.3):
    """Simple async function that satisfies the LLMFunc protocol."""
    return _entity_json()
