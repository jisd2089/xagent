#!/usr/bin/env python3
"""
Convert agency-agents-zh agent definitions to xAgent SKILL.md format.

Usage:
    python convert_agents_to_skills.py \\
        --source D:/Workspace/agency-agents-zh \\
        --target D:/github/xagent/docs/agency-agents-zh/skills

    python convert_agents_to_skills.py \\
        --source D:/Workspace/agency-agents-zh \\
        --target ./skills \\
        --dry-run

    python convert_agents_to_skills.py \\
        --source D:/Workspace/agency-agents-zh \\
        --target ./skills \\
        --departments engineering,marketing
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import yaml
except ImportError:
    print("Error: PyYAML is required. Install it with: pip install pyyaml")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Directories inside agency-agents-zh that are NOT agent department dirs
NON_DEPARTMENT_DIRS = {
    "assets", "examples", "scripts", "strategy", "integrations",
    ".git", ".github", "node_modules",
}

# Files to skip within department directories
SKIP_FILES = {
    "README.md", "CATALOG.md", "AGENT-LIST.md", "UPSTREAM.md",
    "CONTRIBUTING.md", "LICENSE",
}

# Chinese section header patterns → normalized section key
# The regex matches both "## 你的XXX" and "## XXX" variants
SECTION_PATTERNS: List[Tuple[str, str]] = [
    (r"##\s+(?:你的\s*)?身份与记忆", "identity_memory"),
    (r"##\s+(?:你的\s*)?核心使命", "core_mission"),
    (r"##\s+(?:你必须(?:遵循|遵守)的\s*)?关键规则", "key_rules"),
    (r"##\s+(?:你的\s*)?(?:技术|架构)交付物", "technical_deliverables"),
    (r"##\s+(?:你的\s*)?工作流程", "workflow"),
    (r"##\s+(?:你的\s*)?交付物模板", "deliverable_template"),
    (r"##\s+(?:你的\s*)?沟通风格", "communication_style"),
    (r"##\s+学习与记忆", "learning_memory"),
    (r"##\s+(?:你的\s*)?成功指标", "success_metrics"),
    (r"##\s+(?:高级|进阶)能力", "advanced_capabilities"),
]

# Chinese keyword → tags mapping for auto-tagging
CHINESE_TAG_KEYWORDS: Dict[str, List[str]] = {
    "frontend": ["React", "Vue", "Angular", "Svelte", "HTML", "CSS",
                 "组件化", "响应式", "浏览器", "小程序", "WXML", "WXSS"],
    "backend": ["API", "REST", "GraphQL", "gRPC", "消息队列", "Redis",
                "Nginx", "服务端", "微服务", "后端"],
    "mobile": ["iOS", "Android", "Flutter", "React Native", "移动端",
               "跨平台", "Swift", "Kotlin"],
    "ai-ml": ["机器学习", "深度学习", "LLM", "大模型", "模型训练",
              "神经网络", "NLP", "计算机视觉", "RAG", "Agent"],
    "devops": ["CI/CD", "DevOps", "Docker", "Kubernetes", "K8s",
               "Terraform", "持续集成", "持续部署"],
    "security": ["安全审计", "漏洞", "渗透测试", "OWASP", "威胁建模",
                 "SIEM", "MITRE", "SQL注入", "加密", "Auth", "鉴权"],
    "data": ["ETL", "ELT", "Spark", "Flink", "dbt", "数仓", "数据湖",
             "数据管道", "OLAP", "数据中台"],
    "database": ["MySQL", "PostgreSQL", "MongoDB", "索引优化", "查询优化",
                 "Schema", "分库分表", "数据库"],
    "content": ["文案", "内容创作", "写作", "编辑", "排版", "SEO", "关键词策略"],
    "social-media": ["小红书", "抖音", "TikTok", "微信", "微博", "B站",
                     "Bilibili", "快手", "知乎", "LinkedIn", "Instagram", "Reddit"],
    "game": ["Unity", "Unreal", "Godot", "Blender", "Roblox", "Shader",
             "物理引擎", "游戏引擎", "渲染管线"],
    "blockchain": ["区块链", "智能合约", "Solidity", "EVM", "DeFi", "Web3",
                   "NFT", "代币"],
    "embedded": ["嵌入式", "固件", "RTOS", "ARM", "STM32", "ESP32", "FPGA",
                 "Verilog", "单片机", "IoT"],
    "design": ["Figma", "Photoshop", "品牌设计"],
    "testing": ["测试", "QA", "自动化测试", "单测", "集成测试", "质量保证"],
    "sales": ["销售", "获客", "转化率", "CRM", "Salesforce", "客户关系"],
    "support": ["客服", "工单", "售后", "服务台"],
    "legal": ["法律", "合规", "合同", "法规", "GDPR", "个人信息保护法"],
    "hr": ["招聘", "人事", "绩效", "HR", "培训", "入职", "薪酬"],
    "finance": ["财务", "税务", "会计", "审计", "报表", "预算"],
    "mcp": ["MCP", "Model Context Protocol"],
    "voice": ["语音识别", "ASR", "TTS", "Whisper", "语音转录"],
    "email": ["邮件", "Email", "IMAP", "SMTP"],
}


# Department directory → output subdirectory name mapping
DEPARTMENT_OUTPUT_MAP = {
    "academic": "academic",
    "design": "design",
    "engineering": "engineering",
    "finance": "finance",
    "game-development": "game-development",
    "hr": "hr",
    "legal": "legal",
    "marketing": "marketing",
    "paid-media": "paid-media",
    "product": "product",
    "project-management": "project-management",
    "sales": "sales",
    "spatial-computing": "spatial-computing",
    "specialized": "specialized",
    "supply-chain": "supply-chain",
    "support": "support",
    "testing": "testing",
}


# ---------------------------------------------------------------------------
# Parsing utilities
# ---------------------------------------------------------------------------

def parse_frontmatter(content: str) -> Dict[str, Any]:
    """Extract YAML frontmatter from a markdown file."""
    stripped = content.lstrip()
    if not stripped.startswith("---"):
        return {}

    lines = stripped.splitlines()
    if len(lines) < 2:
        return {}

    end_idx = None
    for i, line in enumerate(lines[1:], start=1):
        if line.strip().startswith("---"):
            end_idx = i
            break

    if end_idx is None:
        return {}

    fm_text = "\n".join(lines[1:end_idx])
    try:
        result = yaml.safe_load(fm_text)
        return result if isinstance(result, dict) else {}
    except yaml.YAMLError:
        return {}


def get_body_without_frontmatter(content: str) -> str:
    """Return the markdown body without YAML frontmatter."""
    stripped = content.lstrip()
    if not stripped.startswith("---"):
        return stripped

    lines = stripped.splitlines()
    end_idx = None
    for i, line in enumerate(lines[1:], start=1):
        if line.strip().startswith("---"):
            end_idx = i
            break

    if end_idx is None:
        return stripped

    return "\n".join(lines[end_idx + 1:]).strip()


def _strip_code_blocks(text: str) -> tuple:
    """Replace fenced code block content while preserving character positions.

    Returns (clean_body, code_block_ranges) where code_block_ranges is a
    list of (start_line, end_line) tuples (0-indexed) marking code blocks.
    """
    result: List[str] = []
    in_block = False
    fence_char = ""
    code_ranges: List[Tuple[int, int]] = []
    block_start = 0
    line_num = 0

    for line in text.splitlines():
        stripped = line.strip()
        if not in_block:
            if stripped.startswith("```") or stripped.startswith("~~~"):
                in_block = True
                fence_char = stripped[:3]
                block_start = line_num
                result.append(line)  # keep the opening fence
            else:
                result.append(line)
        else:
            if stripped.startswith(fence_char):
                in_block = False
                code_ranges.append((block_start, line_num))
                result.append(line)  # keep the closing fence
            else:
                # Preserve character count to maintain positions
                result.append(" " * len(line))
        line_num += 1

    return "\n".join(result), code_ranges


def _is_in_code_block(line_num: int, code_ranges: List[Tuple[int, int]]) -> bool:
    """Check if a given line number falls inside any code block range."""
    for start, end in code_ranges:
        if start < line_num < end:
            return True
    return False


def parse_sections(body: str) -> Dict[str, str]:
    """Parse a markdown body into named sections based on Chinese headers."""
    sections: Dict[str, str] = {}

    # Strip code blocks to identify their line ranges
    clean_body, code_ranges = _strip_code_blocks(body)

    # Find all H2 headers
    header_pattern = re.compile(r"^##\s+(.+)$", re.MULTILINE)
    matches = list(header_pattern.finditer(body))

    # Build line number → position map for the original body
    body_lines = body.splitlines()
    line_starts: List[int] = []
    pos = 0
    for line in body_lines:
        line_starts.append(pos)
        pos += len(line) + 1  # +1 for the newline

    def get_line_number(char_pos: int) -> int:
        """Convert character position to 0-indexed line number."""
        for i in range(len(line_starts) - 1, -1, -1):
            if line_starts[i] <= char_pos:
                return i
        return 0

    for i, match in enumerate(matches):
        header_text = match.group(1).strip()

        # Skip headers inside code blocks
        line_no = get_line_number(match.start())
        if _is_in_code_block(line_no, code_ranges):
            continue

        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        section_body = body[start:end].strip()

        # Match against known section patterns
        full_header = f"## {header_text}"
        for pattern, key in SECTION_PATTERNS:
            if re.match(pattern, full_header):
                sections[key] = section_body
                break

    return sections


def extract_h1_title(body: str) -> Optional[str]:
    """Extract the H1 title from the body."""
    m = re.match(r"^#\s+(.+?)(?:\s*Agent\s*(?:人格|角色))?\s*$", body, re.MULTILINE)
    if m:
        return m.group(1).strip()
    # Try simpler pattern
    m = re.match(r"^#\s+(.+)", body, re.MULTILINE)
    if m:
        return m.group(1).strip()
    return None


def strip_footer(body: str) -> str:
    """Remove the horizontal-rule footer (e.g., '**指令参考**：...') from the body."""
    # Find the last `---` separator and remove everything after it
    # Only if it's near the end (last 10% of content)
    lines = body.splitlines()
    for i in range(len(lines) - 1, len(lines) - min(20, len(lines)), -1):
        if lines[i].strip() == "---":
            return "\n".join(lines[:i]).strip()
    return body



# ---------------------------------------------------------------------------
# Tag generation
# ---------------------------------------------------------------------------

def generate_tags(department: str, frontmatter: dict, agent: dict) -> List[str]:
    """Generate tags from department name and focused content analysis.

    Uses a stricter 3-match threshold with compound keywords to reduce
    false positives from common Chinese characters appearing in unexpected
    contexts (e.g. '设计' in '教学设计' shouldn't trigger the 'design' tag).
    """
    tags: List[str] = []

    dept_tag = department.lower().replace(" ", "-")
    tags.append(dept_tag)

    sections = agent.get("sections", {})
    focused_text = " ".join([
        frontmatter.get("description", ""),
        sections.get("core_mission", ""),
        sections.get("key_rules", ""),
    ]).lower()

    for tag, keywords in CHINESE_TAG_KEYWORDS.items():
        if tag == dept_tag:
            continue
        match_count = sum(1 for kw in keywords if kw.lower() in focused_text)
        if match_count >= 3:  # Stricter: 3+ keyword hits required
            tags.append(tag)

    return tags[:5]


# ---------------------------------------------------------------------------
# Content assembly
# ---------------------------------------------------------------------------

def generate_when_to_use(agent: dict) -> str:
    """Synthesize a concise 'when_to_use' from the agent's description and key rules."""
    fm = agent.get("frontmatter", {})
    desc = fm.get("description", "")

    # Use the description as the base, crafting a natural sentence
    if desc:
        return f"当任务涉及{desc.rstrip('。')}时使用此技能。"

    name = fm.get("name", agent.get("name", "相关领域"))
    return f"当任务涉及{name}相关工作时使用此技能。"


def build_description_section(agent: dict) -> str:
    """Build the ## Description section.

    Preserves the identity bullets and the full core_mission content
    including sub-headings, up to a generous character limit.
    """
    sections = agent.get("sections", {})

    parts: List[str] = []

    # Identity / memory — keep the short role bullets
    identity = sections.get("identity_memory", "")
    if identity:
        bullets = _extract_bullets(identity)
        if bullets:
            parts.append("**角色定位**")
            parts.extend(f"- {b}" for b in bullets[:4])
            parts.append("")

    # Core mission — preserve full structure with sub-headings
    mission = sections.get("core_mission", "")
    if mission:
        parts.append("**核心能力**")
        parts.append("")
        # Keep sub-headings and their content up to a generous limit
        parts.append(mission.strip())

    return "\n".join(parts)


def _extract_bullets(text: str) -> List[str]:
    """Extract bullet point content, stripping bold markers."""
    bullets: List[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        # Match "- content" or "- **content**" or "* content"
        m = re.match(r"[-*]\s+(.+?)$", stripped)
        if m:
            # Strip bold markers
            content = re.sub(r"\*{1,2}([^*]+?)\*{1,2}", r"\1", m.group(1))
            content = content.strip()
            if content:
                bullets.append(content)
    return bullets


def build_when_to_use_section(agent: dict) -> str:
    """Build the ## When to Use section from key_rules.

    Preserves H3 sub-headings (### lines) alongside bullet points
    to retain the structural organization of the original rules.
    """
    sections = agent.get("sections", {})

    rules = sections.get("key_rules", "")
    if not rules:
        return ""

    lines: List[str] = []
    for line in rules.splitlines():
        stripped = line.strip()
        if not stripped:
            if lines and lines[-1] != "":
                lines.append("")
            continue

        # Keep H3 sub-headings as bold text
        if stripped.startswith("### "):
            heading = stripped[4:].strip()
            if lines and lines[-1] != "":
                lines.append("")
            lines.append(f"**{heading}**")
            continue

        # Keep bullet points
        m = re.match(r"[-*]\s+(.+?)$", stripped)
        if m:
            content = re.sub(r"\*{1,2}", "", m.group(1)).strip()
            lines.append(f"- {content}")

    return "\n".join(lines)


def build_execution_flow_section(agent: dict) -> str:
    """Build the ## Execution Flow section from workflow.

    Preserves H3 sub-headings (### lines) alongside bullet points
    to retain the full workflow detail, same approach as build_when_to_use_section.
    """
    sections = agent.get("sections", {})

    workflow = sections.get("workflow", "")
    if not workflow:
        return ""

    lines: List[str] = []
    for line in workflow.splitlines():
        stripped = line.strip()
        if not stripped:
            if lines and lines[-1] != "":
                lines.append("")
            continue

        # Keep H3 sub-headings as bold text
        if stripped.startswith("### "):
            heading = stripped[4:].strip()
            if lines and lines[-1] != "":
                lines.append("")
            lines.append(f"**{heading}**")
            continue

        # Keep bullet points
        m = re.match(r"[-*]\s+(.+?)$", stripped)
        if m:
            content = re.sub(r"\*{1,2}", "", m.group(1)).strip()
            lines.append(f"- {content}")
            continue

        # Keep any other non-empty content
        lines.append(stripped)

    return "\n".join(lines)


def build_skill_content(agent: dict, source_path: str) -> str:
    """Assemble the complete SKILL.md content."""
    fm = agent.get("frontmatter", {})
    sections = agent.get("sections", {})

    # --- Frontmatter ---
    name = fm.get("name", agent.get("name", "Unknown"))
    description = fm.get("description", "")
    when_to_use = generate_when_to_use(agent)
    tags = agent.get("tags", [])

    fm_lines = [
        "---",
        f"name: {name}",
        f"description: {description}",
        f"when_to_use: {when_to_use}",
    ]
    if tags:
        fm_lines.append("tags:")
        for t in tags:
            fm_lines.append(f"  - {t}")
    fm_lines.append("---")

    # --- Body sections ---
    body_parts: List[str] = []

    # H1 title
    title = extract_h1_title(agent.get("body", "")) or name
    body_parts.append(f"# {title}")
    body_parts.append("")

    # Description
    desc = build_description_section(agent)
    if desc:
        body_parts.append("## Description")
        body_parts.append("")
        body_parts.append(desc)
        body_parts.append("")

    # When to Use
    when = build_when_to_use_section(agent)
    if when:
        body_parts.append("## When to Use")
        body_parts.append("")
        body_parts.append(when)
        body_parts.append("")

    # Execution Flow
    flow = build_execution_flow_section(agent)
    if flow:
        body_parts.append("## Execution Flow")
        body_parts.append("")
        body_parts.append(flow)
        body_parts.append("")

    # Reference Deliverables
    deliverables = sections.get("technical_deliverables", "")
    if deliverables:
        body_parts.append("## Reference Deliverables")
        body_parts.append("")
        body_parts.append(deliverables.strip())
        body_parts.append("")

    # Communication Style
    comm = sections.get("communication_style", "")
    if comm:
        body_parts.append("## Communication Style")
        body_parts.append("")
        body_parts.append(comm.strip())
        body_parts.append("")

    # Success Metrics
    metrics = sections.get("success_metrics", "")
    if metrics:
        body_parts.append("## Success Metrics")
        body_parts.append("")
        body_parts.append(metrics.strip())
        body_parts.append("")

    # Advanced Capabilities
    advanced = sections.get("advanced_capabilities", "")
    if advanced:
        body_parts.append("## Advanced Capabilities")
        body_parts.append("")
        body_parts.append(advanced.strip())
        body_parts.append("")

    # Footer: source reference
    body_parts.append("---")
    body_parts.append(f"*Source: agency-agents-zh → {source_path}*")

    body = "\n".join(body_parts)

    return "\n".join(fm_lines) + "\n\n" + body


# ---------------------------------------------------------------------------
# Skill directory naming
# ---------------------------------------------------------------------------

def slugify_name(filename: str, department: str) -> str:
    """Generate a skill directory name from the source filename.

    Examples:
        engineering-frontend-developer → frontend-developer
        unity-architect               → unity-architect
        specialized-mcp-builder        → mcp-builder
    """
    stem = filename.replace(".md", "")

    # Try stripping department prefix
    for prefix in [f"{department}-", f"{department.replace('-', '_')}-"]:
        if stem.startswith(prefix):
            stem = stem[len(prefix):]
            break

    # Fallback: strip common department-like prefixes even if not exact match
    # This handles cases like "engineering-xxx" where department is "engineering"
    common_prefixes = [
        "engineering-", "marketing-", "specialized-", "academic-",
        "design-", "finance-", "game-development-", "hr-", "legal-",
        "paid-media-", "product-", "project-management-", "sales-",
        "spatial-computing-", "supply-chain-", "support-", "testing-",
    ]
    for prefix in common_prefixes:
        if stem.startswith(prefix):
            stem = stem[len(prefix):]
            break

    return stem


# ---------------------------------------------------------------------------
# Main conversion logic
# ---------------------------------------------------------------------------

def is_agent_file(filepath: Path) -> bool:
    """Check if a .md file is an agent definition (not a README, etc.)."""
    if filepath.suffix.lower() != ".md":
        return False
    if filepath.name in SKIP_FILES:
        return False
    # Quick check: agent files have YAML frontmatter
    try:
        text = filepath.read_text(encoding="utf-8").lstrip()
        return text.startswith("---")
    except Exception:
        return False


def parse_agent_file(filepath: Path) -> Optional[dict]:
    """Parse a single agency-agents-zh agent markdown file.

    Returns a dict with keys: frontmatter, body, sections, name, tags
    """
    try:
        raw = filepath.read_text(encoding="utf-8")
    except Exception as e:
        print(f"  [WARN] Cannot read {filepath}: {e}")
        return None

    fm = parse_frontmatter(raw)
    body = get_body_without_frontmatter(raw)
    body = strip_footer(body)
    sections = parse_sections(body)

    agent_name = fm.get("name", filepath.stem)

    return {
        "frontmatter": fm,
        "body": body,
        "sections": sections,
        "name": agent_name,
    }


def convert_one(
    filepath: Path,
    department: str,
    target_root: Path,
    dry_run: bool = False,
    verbose: bool = False,
) -> Optional[dict]:
    """Convert a single agent file to a skill directory.

    Returns conversion info dict, or None on failure.
    """
    agent = parse_agent_file(filepath)
    if agent is None:
        return None

    # Generate tags
    agent["tags"] = generate_tags(department, agent["frontmatter"], agent)

    # Determine output directory name
    skill_dirname = slugify_name(filepath.name, department)
    dept_output = DEPARTMENT_OUTPUT_MAP.get(department, department)
    skill_dir = target_root / dept_output / skill_dirname

    # Determine source relative path for reference
    try:
        source_rel = filepath.relative_to(filepath.parents[2])
    except (ValueError, IndexError):
        source_rel = filepath

    # Build SKILL.md content
    skill_content = build_skill_content(agent, str(source_rel))

    if verbose:
        name = agent["frontmatter"].get("name", skill_dirname)
        tags_str = ", ".join(agent["tags"])
        print(f"  {name} → {skill_dir}/SKILL.md  [{tags_str}]")

    if not dry_run:
        skill_dir.mkdir(parents=True, exist_ok=True)
        skill_md = skill_dir / "SKILL.md"
        skill_md.write_text(skill_content, encoding="utf-8")

    return {
        "source": str(filepath),
        "target_dir": str(skill_dir),
        "skill_name": skill_dirname,
        "display_name": agent["frontmatter"].get("name", skill_dirname),
        "department": department,
        "tags": agent["tags"],
    }


def scan_agent_files(source_root: Path, departments: Optional[List[str]] = None) -> List[Tuple[Path, str]]:
    """Scan source_root for all agent .md files.

    Returns list of (filepath, department_name) tuples.
    """
    results: List[Tuple[Path, str]] = []

    for child in sorted(source_root.iterdir()):
        if not child.is_dir():
            continue
        if child.name in NON_DEPARTMENT_DIRS:
            continue

        dept = child.name

        if departments and dept not in departments:
            continue

        # Collect .md files in this directory and subdirectories
        md_files: List[Path] = []
        for item in sorted(child.rglob("*.md")):
            if item.is_file() and is_agent_file(item):
                md_files.append(item)

        for f in md_files:
            results.append((f, dept))

    return results


def run(
    source: str,
    target: str,
    departments: Optional[List[str]] = None,
    dry_run: bool = False,
    verbose: bool = False,
) -> Dict[str, Any]:
    """Main conversion runner."""
    source_root = Path(source)
    target_root = Path(target)

    if not source_root.exists():
        print(f"Error: Source directory not found: {source_root}")
        sys.exit(1)

    print(f"Source: {source_root}")
    print(f"Target: {target_root}")
    if dry_run:
        print("Mode:  DRY RUN (no files written)")
    print()

    # Scan
    files = scan_agent_files(source_root, departments)
    print(f"Found {len(files)} agent files to convert")
    if verbose and departments:
        print(f"Departments filter: {departments}")
    print()

    # Convert
    converted: List[dict] = []
    skipped: List[str] = []
    failed: List[str] = []

    for filepath, dept in files:
        try:
            info = convert_one(filepath, dept, target_root, dry_run=dry_run, verbose=verbose)
            if info:
                converted.append(info)
            else:
                skipped.append(str(filepath))
        except Exception as e:
            failed.append(str(filepath))
            print(f"  [ERROR] {filepath}: {e}")

    # Statistics
    print()
    print("=" * 60)
    print("CONVERSION SUMMARY")
    print("=" * 60)
    print(f"  Converted: {len(converted)}")
    print(f"  Skipped:   {len(skipped)}")
    print(f"  Failed:    {len(failed)}")

    # Per-department breakdown
    dept_counts: Dict[str, int] = {}
    for c in converted:
        d = c["department"]
        dept_counts[d] = dept_counts.get(d, 0) + 1

    print()
    print("By department:")
    for dept, count in sorted(dept_counts.items()):
        print(f"  {dept:25s} {count:3d} skills")

    # Write mapping file
    if not dry_run and converted:
        mapping_path = target_root / "mapping.json"
        mapping_data = {
            "source": str(source_root),
            "total_converted": len(converted),
            "skills": converted,
        }
        mapping_path.write_text(
            json.dumps(mapping_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"\nMapping written to: {mapping_path}")

    if failed:
        print(f"\nFailed files:")
        for f in failed:
            print(f"  - {f}")

    return {"converted": len(converted), "skipped": len(skipped), "failed": len(failed)}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Convert agency-agents-zh agent files to xAgent SKILL.md format",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python convert_agents_to_skills.py --source ../agency-agents-zh --target ./skills
  python convert_agents_to_skills.py --source ../agency-agents-zh --target ./skills --dry-run
  python convert_agents_to_skills.py --source ../agency-agents-zh --target ./skills --departments engineering,marketing
        """,
    )
    parser.add_argument(
        "--source", required=True,
        help="Path to agency-agents-zh root directory"
    )
    parser.add_argument(
        "--target", required=True,
        help="Output directory for converted skills"
    )
    parser.add_argument(
        "--departments",
        help="Comma-separated department names to convert (default: all)"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print conversion plan without writing files"
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Print per-file conversion details"
    )

    args = parser.parse_args()

    departments = None
    if args.departments:
        departments = [d.strip() for d in args.departments.split(",") if d.strip()]

    run(
        source=args.source,
        target=args.target,
        departments=departments,
        dry_run=args.dry_run,
        verbose=args.verbose,
    )


if __name__ == "__main__":
    main()
