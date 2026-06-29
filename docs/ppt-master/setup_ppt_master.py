#!/usr/bin/env python3
"""
ppt-master → xAgent Skill 集成部署脚本

将 ppt-master 技能（AI 驱动的多格式 SVG 内容生成系统）部署到 xAgent 技能目录，
自动适配 xAgent SKILL.md 格式并替换路径变量。

用法:
    # 部署到 xAgent 容器的技能目录
    python setup_ppt_master.py \
        --source D:/Workspace/ppt-master/skills/ppt-master \
        --target /root/.xagent/skills/ppt-master

    # 仅生成 SKILL.md 不复制文件（需要 --copy-only-skill 配合）
    python setup_ppt_master.py \
        --source D:/Workspace/ppt-master/skills/ppt-master \
        --target /root/.xagent/skills/ppt-master \
        --generate-skill-only

    # 安装 Python 依赖
    python setup_ppt_master.py --target /root/.xagent/skills/ppt-master --install-deps

    # 完整部署（复制 + 生成 SKILL.md + 安装依赖）
    python setup_ppt_master.py \
        --source D:/Workspace/ppt-master/skills/ppt-master \
        --target /root/.xagent/skills/ppt-master \
        --install-deps

    # 预览模式（不实际写入文件）
    python setup_ppt_master.py \
        --source D:/Workspace/ppt-master/skills/ppt-master \
        --target /root/.xagent/skills/ppt-master \
        --dry-run
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# ============================================================================
# Constants
# ============================================================================

# Essential subdirectories that must be copied
REQUIRED_SUBDIRS = [
    "scripts",
    "templates",
    "references",
    "workflows",
]

# Files to skip (not needed at runtime)
SKIP_PATTERNS = [
    "__pycache__",
    "*.pyc",
    "*.pyo",
    ".git",
    ".gitignore",
    ".DS_Store",
    "Thumbs.db",
]

# xAgent skill tags derived from ppt-master capabilities
SKILL_TAGS = [
    "ppt",
    "presentation",
    "svg",
    "design",
    "generation",
]


def should_skip(name: str) -> bool:
    """Check if a file/directory should be skipped during copy."""
    import fnmatch

    for pattern in SKIP_PATTERNS:
        if fnmatch.fnmatch(name, pattern):
            return True
    return False


# ============================================================================
# SKILL.md Generation
# ============================================================================


def generate_xagent_skill_md(
    source_dir: Path, target_path: str
) -> str:
    """Generate xAgent-compatible SKILL.md from ppt-master source.

    Reads the original SKILL.md, adapts the frontmatter for xAgent format,
    and replaces ${SKILL_DIR} variables with the actual target path.
    """
    source_skill = source_dir / "SKILL.md"
    if not source_skill.exists():
        print(f"ERROR: Source SKILL.md not found at {source_skill}")
        sys.exit(1)

    original = source_skill.read_text(encoding="utf-8")

    # --- Extract original name and description from frontmatter ---
    orig_name = "ppt-master"
    orig_desc = ""
    fm_match = re.match(r"^---\s*\n(.*?)\n---", original, re.DOTALL)
    if fm_match:
        fm_text = fm_match.group(1)
        name_m = re.search(r"name:\s*(.+)", fm_text)
        if name_m:
            orig_name = name_m.group(1).strip()
        desc_m = re.search(r"description:\s*>?\s*(.+)", fm_text)
        if desc_m:
            orig_desc = " ".join(
                line.strip() for line in desc_m.group(1).splitlines()
            )

    # --- Build body: remove original frontmatter, keep everything else ---
    body = original
    if fm_match:
        body = original[fm_match.end():].strip()

    # --- Replace ${SKILL_DIR} with actual target path ---
    body = body.replace("${SKILL_DIR}", target_path)

    # --- Simplify GitHub callouts to plain markdown ---
    # > [!CAUTION] → bold text
    body = re.sub(
        r'>\s*\[!CAUTION\]\s*\n>\s*##\s*(.+)',
        r'**\1**',
        body,
    )
    # > [!IMPORTANT] → bold text
    body = re.sub(
        r'>\s*\[!IMPORTANT\]\s*\n>\s*##\s*(.+)',
        r'**\1**',
        body,
    )
    # Remove remaining callout markers and > prefixes
    body = re.sub(r'>\s*\[!NOTE\]\s*', '', body)
    # De-nest callout block quotes: remove leading > from lines after a cleaned callout
    body_lines = body.splitlines()
    cleaned_lines: List[str] = []
    in_callout = False
    for line in body_lines:
        if line.startswith("> **") or line.startswith("> ⚠️") or line.startswith("> ❌"):
            in_callout = True
            cleaned_lines.append(line[2:])  # strip "> "
        elif in_callout and line.startswith("> "):
            cleaned_lines.append(line[2:])
        elif in_callout and line.startswith(">"):
            cleaned_lines.append(line[1:])
        elif in_callout and not line.startswith(">"):
            in_callout = False
            cleaned_lines.append(line)
        else:
            cleaned_lines.append(line)
    body = "\n".join(cleaned_lines)

    # --- Build xAgent frontmatter ---
    when_to_use = (
        "当用户要求创建PPT、生成演示文稿、制作幻灯片、做PPT、"
        "制作PPT，或提到ppt-master、presentation、slide deck等相关需求时使用此技能。"
        "支持从 PDF/DOCX/URL/Markdown/纯文本 等多种来源生成高质量SVG页面并导出PPTX。"
        "核心流程：源文件转换 → 项目初始化 → 策略设计 → 图片获取 → "
        "SVG页面生成 → 质量检查 → 后处理 → PPTX导出。"
    )

    description = (
        f"AI驱动的多格式SVG内容生成系统。将源文档（PDF/DOCX/URL/Markdown）"
        f"转换为高质量SVG页面并通过多角色协作导出PPTX。"
    )

    fm_lines = [
        "---",
        f"name: {orig_name}",
        f"description: {description}",
        f"when_to_use: {when_to_use}",
        "tags:",
    ]
    for tag in SKILL_TAGS:
        fm_lines.append(f"  - {tag}")
    fm_lines.append("---")

    # --- Add xAgent usage note ---
    xagent_note = f"""
> **xAgent 部署说明**：本技能来自 [ppt-master](https://github.com/hugohe3/ppt-master) 项目。
> 技能目录已部署到 `{target_path}`，所有脚本和模板均可通过绝对路径访问。
> Python 脚本位于 `{target_path}/scripts/` 目录下。
> 初次使用前请确保已安装依赖：`pip install -r {target_path}/requirements.txt`
"""

    return "\n".join(fm_lines) + "\n" + xagent_note + "\n" + body


# ============================================================================
# File Operations
# ============================================================================


def copy_skill_files(
    source_dir: Path, target_dir: Path, dry_run: bool = False
) -> Tuple[int, int]:
    """Copy ppt-master skill directory tree to target.

    Returns (files_copied, dirs_created).
    """
    if not source_dir.exists():
        print(f"ERROR: Source directory not found: {source_dir}")
        sys.exit(1)

    files_copied = 0
    dirs_created = 0

    for root, dirs, files in os.walk(source_dir):
        # Filter out skipped directories in-place
        dirs[:] = [d for d in dirs if not should_skip(d)]

        rel_path = Path(root).relative_to(source_dir)
        target_root = target_dir / rel_path

        if not dry_run:
            target_root.mkdir(parents=True, exist_ok=True)
        dirs_created += 1

        for filename in files:
            if should_skip(filename):
                continue

            src_file = Path(root) / filename
            dst_file = target_root / filename

            if not dry_run:
                shutil.copy2(src_file, dst_file)

            files_copied += 1

    return files_copied, dirs_created


def install_dependencies(target_dir: Path) -> bool:
    """Install Python dependencies from requirements.txt."""
    req_file = target_dir / "requirements.txt"
    if not req_file.exists():
        print(f"WARNING: requirements.txt not found at {req_file}")
        return False

    print(f"Installing dependencies from {req_file}...")
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", str(req_file)],
            check=True,
        )
        print("Dependencies installed successfully.")
        return True
    except subprocess.CalledProcessError as e:
        print(f"ERROR: Dependency installation failed: {e}")
        return False


def verify_deployment(target_dir: Path) -> Dict[str, bool]:
    """Verify that all essential skill components are in place."""
    checks: Dict[str, bool] = {}

    # Check SKILL.md
    checks["SKILL.md"] = (target_dir / "SKILL.md").exists()

    # Check essential subdirectories
    for subdir in REQUIRED_SUBDIRS:
        d = target_dir / subdir
        checks[f"Directory: {subdir}"] = d.exists() and d.is_dir()

    # Check key scripts
    key_scripts = [
        "scripts/project_manager.py",
        "scripts/finalize_svg.py",
        "scripts/svg_to_pptx.py",
        "scripts/svg_quality_checker.py",
    ]
    for script in key_scripts:
        checks[f"Script: {script}"] = (target_dir / script).exists()

    # Check key references
    key_refs = [
        "references/strategist.md",
        "references/executor-base.md",
        "references/shared-standards.md",
    ]
    for ref in key_refs:
        checks[f"Reference: {ref}"] = (target_dir / ref).exists()

    return checks


# ============================================================================
# Main
# ============================================================================


def main():
    parser = argparse.ArgumentParser(
        description="将 ppt-master 技能部署到 xAgent 技能目录",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python setup_ppt_master.py --source ../ppt-master/skills/ppt-master --target ~/.xagent/skills/ppt-master
  python setup_ppt_master.py --source ../ppt-master/skills/ppt-master --target ./skills/ppt-master --install-deps
  python setup_ppt_master.py --target ~/.xagent/skills/ppt-master --generate-skill-only
        """,
    )
    parser.add_argument(
        "--source",
        help="ppt-master 技能源目录路径（如 D:/Workspace/ppt-master/skills/ppt-master）",
    )
    parser.add_argument(
        "--target",
        required=True,
        help="xAgent 技能部署目标目录路径",
    )
    parser.add_argument(
        "--install-deps",
        action="store_true",
        help="在目标目录中安装 Python 依赖（pip install -r requirements.txt）",
    )
    parser.add_argument(
        "--generate-skill-only",
        action="store_true",
        help="仅生成 SKILL.md，不复制其他文件（目标目录必须已存在）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="预览模式，不实际写入文件",
    )

    args = parser.parse_args()

    target_dir = Path(os.path.expanduser(args.target))

    # Validate: --generate-skill-only requires --source
    if args.generate_skill_only and not args.source:
        print("ERROR: --generate-skill-only 需要 --source 参数")
        sys.exit(1)

    # Validate: file copy requires --source
    if not args.generate_skill_only and not args.source:
        print("ERROR: 完整部署需要 --source 参数（或使用 --generate-skill-only）")
        sys.exit(1)

    # Validate: --install-deps requires target to exist
    if args.install_deps and not target_dir.exists() and not args.dry_run:
        print(f"ERROR: 目标目录不存在，无法安装依赖: {target_dir}")
        print("请先执行完整部署，再使用 --install-deps")
        sys.exit(1)

    print("=" * 60)
    print("ppt-master → xAgent Skill 部署")
    print("=" * 60)

    # --- Step 1: Copy skill files ---
    if not args.generate_skill_only and args.source:
        source_dir = Path(args.source)
        print(f"\n[1/3] 复制技能文件...")
        print(f"  源目录: {source_dir}")
        print(f"  目标目录: {target_dir}")

        files, dirs = copy_skill_files(source_dir, target_dir, args.dry_run)
        print(f"  已{'[预览]' if args.dry_run else ''}复制 {files} 个文件, "
              f"创建 {dirs} 个目录")

    # --- Step 2: Generate xAgent SKILL.md ---
    if args.source:
        source_dir = Path(args.source)
        print(f"\n[2/3] 生成 xAgent 兼容 SKILL.md...")

        target_path_for_skill = str(target_dir).replace("\\", "/")
        skill_content = generate_xagent_skill_md(source_dir, target_path_for_skill)

        skill_file = target_dir / "SKILL.md"
        if not args.dry_run:
            # Backup original if it exists
            if skill_file.exists():
                backup_file = target_dir / "SKILL.md.bak"
                shutil.copy2(skill_file, backup_file)
                print(f"  已备份原 SKILL.md → SKILL.md.bak")

            skill_file.write_text(skill_content, encoding="utf-8")

        print(f"  已{'[预览]' if args.dry_run else ''}写入 {skill_file}")
        print(f"  文件大小: {len(skill_content):,} 字符")

        # Check ${SKILL_DIR} replacements
        remaining = skill_content.count("${SKILL_DIR}")
        if remaining > 0:
            print(f"  WARNING: 仍有 {remaining} 处 ${{SKILL_DIR}} 未替换")
        else:
            print(f"  ${{SKILL_DIR}} 替换: 全部完成")
    else:
        print(f"\n[2/3] 跳过 SKILL.md 生成（未提供 --source）")

    # --- Step 3: Install dependencies ---
    if args.install_deps:
        print(f"\n[3/3] 安装 Python 依赖...")
        if not args.dry_run:
            install_dependencies(target_dir)
        else:
            print(f"  [预览] pip install -r {target_dir / 'requirements.txt'}")
    else:
        print(f"\n[3/3] 跳过依赖安装（使用 --install-deps 启用）")

    # --- Verification ---
    if not args.dry_run and not args.generate_skill_only:
        print(f"\n验证部署结果...")
        checks = verify_deployment(target_dir)
        all_ok = True
        for name, ok in checks.items():
            status = "OK" if ok else "MISSING"
            if not ok:
                all_ok = False
            print(f"  [{status}] {name}")

        if all_ok:
            print(f"\n部署成功!")
        else:
            print(f"\n部署完成，但有缺失项，请检查。")

        # Print post-install instructions
        print(f"""
{'=' * 60}
后续步骤:
{'=' * 60}

1. 在 xAgent 中重新加载技能:
   curl -X POST {{BASE_URL}}/api/skills/reload \\
     -H "Authorization: Bearer <YOUR_TOKEN>"

2. 验证技能已加载:
   curl {{BASE_URL}}/api/skills/ppt-master \\
     -H "Authorization: Bearer <YOUR_TOKEN>"

3. 创建 Agent 时在 Skills 字段中填入:
   ppt-master

4. （可选）安装 Python 依赖:
   pip install -r {target_dir / 'requirements.txt'}
""")
    elif args.generate_skill_only and not args.dry_run:
        print(f"\nSKILL.md 已生成到 {target_dir / 'SKILL.md'}")
        print("请将其与 ppt-master 的 scripts/templates/references/workflows 目录放置在同一个技能目录下。")


if __name__ == "__main__":
    main()
