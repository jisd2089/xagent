"""Shared fixtures for Wiki Engine end-to-end tests.

All E2E tests use a stateful mock LLM that returns context-aware responses
for entity extraction and page compilation stages.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Optional

import pytest

from xagent.core.wiki.config import WikiConfig
from xagent.core.wiki.engine import WikiEngine


# ---------------------------------------------------------------------------
# Async event loop (session-scoped)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def event_loop():
    """Single event loop for the entire test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# ---------------------------------------------------------------------------
# E2E Mock LLM
# ---------------------------------------------------------------------------


class E2EMockLLM:
    """Stateful mock LLM for end-to-end Wiki Engine tests.

    Returns context-aware responses based on prompt content:
    - Entity extraction prompts → JSON with entities detected from input text
    - Page compilation prompts  → Markdown with wikilinks
    - Concept compilation      → Cross-entity synthesis with patterns
    """

    KNOWN_ENTITIES: dict[str, dict[str, Any]] = {
        "张伟": {"type": "person", "keywords": ["张伟"]},
        "李明": {"type": "person", "keywords": ["李明"]},
        "王芳": {"type": "person", "keywords": ["王芳"]},
        "赵六": {"type": "person", "keywords": ["赵六"]},
        "陈七": {"type": "person", "keywords": ["陈七"]},
        "王五": {"type": "person", "keywords": ["王五"]},
        "Python": {"type": "technology", "keywords": ["Python", "python"]},
        "SQL": {"type": "technology", "keywords": ["SQL"]},
        "数据分析": {"type": "concept", "keywords": ["数据分析"]},
        "前端开发": {"type": "concept", "keywords": ["前端开发", "前端"]},
        "UI设计": {"type": "concept", "keywords": ["UI设计"]},
        "React": {"type": "technology", "keywords": ["React"]},
        "pandas": {"type": "technology", "keywords": ["pandas"]},
        "Java": {"type": "technology", "keywords": ["Java"]},
        "机器学习": {"type": "concept", "keywords": ["机器学习"]},
    }

    def __init__(self) -> None:
        self.compiled_entities: set[str] = set()
        self.compiled_concepts: set[str] = set()
        self.call_count = 0
        self.last_prompt = ""

    async def __call__(
        self, prompt: str, *, system: str = "", temperature: float = 0.3
    ) -> str:
        self.call_count += 1
        self.last_prompt = prompt

        # Entity extraction stage
        if "提取" in prompt and "实体" in prompt:
            return self._handle_entity_extraction(prompt)

        # Concept page compilation
        if "概念" in prompt and "综合" in prompt:
            return self._handle_concept_compile(prompt)

        # Entity page compilation (create or update)
        return self._handle_page_compile(prompt)

    # ---- Entity extraction ----

    def _detect_entities(self, text: str) -> list[str]:
        """Scan text for known entity names."""
        found: list[str] = []
        for name, info in self.KNOWN_ENTITIES.items():
            for kw in info["keywords"]:
                if kw in text:
                    if name not in found:
                        found.append(name)
                    break
        return found

    def _handle_entity_extraction(self, prompt: str) -> str:
        entities = self._detect_entities(prompt)
        if not entities:
            entities = ["未知实体"]

        # Include the full prompt text as context so concept grouping
        # can find co-occurring entity names across entities
        entity_list = [
            {
                "name": name,
                "type": self.KNOWN_ENTITIES.get(name, {}).get("type", "unknown"),
                "context": prompt[:500],  # Include source text for concept detection
            }
            for name in entities
        ]

        # Build relations from co-occurring entities
        relations = []
        for i in range(len(entities)):
            for j in range(i + 1, min(i + 3, len(entities))):
                relations.append({
                    "source": entities[i],
                    "target": entities[j],
                    "type": "related_to",
                    "context": f"{entities[i]} 与 {entities[j]} 在同一上下文中出现",
                })

        return json.dumps(
            {"entities": entity_list, "relations": relations},
            ensure_ascii=False,
        )

    # ---- Concept page compilation ----

    def _handle_concept_compile(self, prompt: str) -> str:
        concept = ""
        for marker in ['关于"', '关于"']:
            if marker in prompt:
                rest = prompt[prompt.index(marker) + len(marker) :]
                concept = rest.split('"')[0] if '"' in rest else ""
                break

        self.compiled_concepts.add(concept)

        # Detect entities from prompt text
        detected = self._detect_entities(prompt)

        # Also parse entity names from "=== name (Level N) ===" markers
        import re
        marker_names = re.findall(r'===\s*(.+?)\s*\(Level', prompt)
        for name in marker_names:
            name = name.strip()
            if name and name not in detected:
                detected.append(name)

        entity_refs = []
        for name in detected:
            entity_refs.append(f"[[{name}]]")
            self.compiled_entities.add(name)

        wikilinks_str = "\n".join(entity_refs) if entity_refs else ""

        return (
            f"# 概念: {concept}\n\n"
            f"## 跨实体综合分析\n\n"
            f"通过对多个实体的信息综合分析，发现以下模式和趋势：\n\n"
            f"### 群体特征与共性\n"
            f"- 整体呈现出多元化的学习需求\n"
            f"- 技术方向选择与个人背景密切相关\n\n"
            f"### 关键趋势\n"
            f"- 实战型课程更受欢迎\n"
            f"- 跨领域技能需求增长明显\n\n"
            f"## Related\n"
            f"{wikilinks_str}\n"
        )

    # ---- Entity page compilation ----

    def _handle_page_compile(self, prompt: str) -> str:
        entities = self._detect_entities(prompt)
        entity_name = entities[0] if entities else "知识实体"
        self.compiled_entities.add(entity_name)

        # Build relevant wikilinks from co-occurring entities/concepts
        wikilinks: list[str] = []
        for name in entities:
            if name != entity_name:
                wikilinks.append(name)

        # Add concept wikilinks based on keywords in prompt
        prompt_lower = prompt.lower()
        if "数据分析" in prompt:
            wikilinks.append("数据分析")
        if "sql" in prompt_lower:
            wikilinks.append("SQL")
        if "python" in prompt_lower:
            wikilinks.append("Python")
        if "前端" in prompt:
            wikilinks.append("前端开发")
        if "react" in prompt_lower:
            wikilinks.append("React")
        if "pandas" in prompt_lower:
            wikilinks.append("pandas")
        if "机器学习" in prompt:
            wikilinks.append("机器学习")

        # Deduplicate preserving order
        seen: set[str] = set()
        unique_wikilinks: list[str] = []
        for wl in wikilinks:
            if wl not in seen:
                seen.add(wl)
                unique_wikilinks.append(wl)

        wikilinks_section = "\n".join(f"- [[{wl}]]" for wl in unique_wikilinks)

        return (
            f"# {entity_name}\n\n"
            f"## 概述\n"
            f"{entity_name} 是一个重要的知识实体，经过 LLM 综合的知识页面。\n\n"
            f"## 关键事实\n"
            f"- 从多源数据综合生成的结构化知识\n"
            f"- 包含具体的数据和分析\n\n"
            f"## 洞察与建议\n"
            f"- 基于综合分析的可操作建议\n\n"
            f"## Related\n"
            f"{wikilinks_section}\n"
        )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

E2E_NAMESPACE = "test_e2e"


@pytest.fixture
def namespace() -> str:
    """Standard E2E test namespace."""
    return E2E_NAMESPACE


@pytest.fixture
def wiki_config(tmp_path: Path, namespace: str) -> WikiConfig:
    """WikiConfig for E2E tests."""
    return WikiConfig(
        wiki_dir=tmp_path / "wiki",
        namespace=namespace,
    )


@pytest.fixture
def mock_llm() -> E2EMockLLM:
    """Fresh E2E mock LLM instance."""
    return E2EMockLLM()


@pytest.fixture
def wiki_engine(wiki_config: WikiConfig, mock_llm: E2EMockLLM) -> WikiEngine:
    """Fully wired WikiEngine for E2E tests."""
    return WikiEngine.from_config(wiki_config, mock_llm)


@pytest.fixture
def student_zhang_wei_records() -> list[dict]:
    """7 simulated records for student 张伟 (across 4 data sources)."""
    return [
        {
            "source": "crm",
            "type": "conversation",
            "content": "张伟来电咨询编程课程，表示对 Python 数据分析方向感兴趣。"
            "目前在互联网公司做运营，想转行做数据分析。预算 5000-8000 元。"
            "偏好周末班。",
        },
        {
            "source": "academic",
            "type": "assessment",
            "content": "Python 基础测评: 张伟得分 85/100。变量/循环/函数掌握扎实，"
            "pandas 数据处理熟练。SQL 基础薄弱。",
        },
        {
            "source": "academic",
            "type": "teacher_feedback",
            "content": "张伟自学能力强，课堂表现积极。建议往数据分析或机器学习方向深入。"
            "可以先补 SQL 基础，再学 pandas 高级应用。",
        },
        {
            "source": "academic",
            "type": "course_record",
            "content": "张伟 2025 Q4 完成「算法入门」课程，成绩 A-。"
            "2026 Q1 正在学习「SQL 基础」课程，进度 60%。",
        },
        {
            "source": "crm",
            "type": "cohort_analysis",
            "content": "同背景学员（互联网运营转数据分析）3 人: "
            "学员A 选了「进阶数据分析课」，6 个月后成功转型。"
            "学员B 选了「Python 项目实战课」，3 个月后在原公司转岗。"
            "学员C 选了「机器学习入门」，反馈难度偏高。",
        },
        {
            "source": "career",
            "type": "job_market",
            "content": "2026 Q1 数据分析师岗位: 平均薪资 15-25K（上海），"
            "要求 Python+SQL+pandas，面试高频考点: SQL JOIN/窗口函数/"
            "pandas groupby/数据可视化。",
        },
        {
            "source": "content",
            "type": "article_performance",
            "content": "「Python 数据分析学习路线 2026」文章: 阅读量 12K，"
            "转化率 8.5%（同类均值 3.2%）。爆款因子: "
            "实操项目清单 + 薪资数据 + 学习时间表。",
        },
    ]


@pytest.fixture
def multi_student_data() -> list[str]:
    """Data for multiple students — triggers concept page compilation."""
    return [
        "张伟，Python 基础 85 分，对数据分析感兴趣，偏好周末班。"
        "互联网运营转行，预算 5000-8000 元。",
        "李明，Java 基础扎实，对前端开发感兴趣。"
        "计算机专业毕业，想做全栈开发。学习 React。",
        "王芳，零基础，对 UI设计 感兴趣。"
        "市场营销背景，想做产品设计师。",
        "赵六，Python 数据分析方向，3 年运营经验。"
        "想学数据可视化，目标薪资 15K+。学习 pandas。",
    ]


@pytest.fixture
def cross_entity_data() -> list[str]:
    """Data for cross-entity wikilink testing."""
    return [
        "张伟，Python 85 分，学数据分析。正在补 SQL 基础。学习 pandas。",
        "李明，Java 基础好，学前端开发。学习 React。",
        "数据分析岗位要求: Python + SQL + pandas，薪资 15-25K。",
        "前端开发岗位要求: React + Java，薪资 12-20K。",
    ]
