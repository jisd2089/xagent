"""PPTX Tool Adapter for xagent

Adapts pptx_tool.py to be used as an xagent tool via vibe adapter system.
"""

import logging
from typing import TYPE_CHECKING, Any, Dict

from ...core.pptx_tool import (
    clean_pptx,
    generate_pptx,
    pack_pptx,
    read_pptx,
    unpack_pptx,
)
from .base import ToolCategory
from .config import BaseToolConfig
from .factory import ToolFactory, register_tool
from .function import FunctionTool

logger = logging.getLogger(__name__)


class PPTXTool(FunctionTool):
    """PPTXTool with ToolCategory.PPT category."""

    category = ToolCategory.PPT


if TYPE_CHECKING:
    from ....workspace import TaskWorkspace
else:
    TaskWorkspace = Any  # type: ignore[assignment]


class PPTXGenerationTool:
    """
    PPTX tool wrapper that handles workspace integration.

    Similar to ImageGenerationTool, this wraps the pptx functions
    and ensures workspace is properly integrated.
    """

    def __init__(self, workspace: "TaskWorkspace | None" = None):
        """
        Initialize PPTX tool with workspace support.

        Args:
            workspace: Workspace for file management (optional but recommended)
        """
        self._workspace = workspace
        logger.debug(f"PPTX tool initialized with workspace: {workspace is not None}")

    async def read_pptx(self, pptx_path: str, extract_text: bool = False) -> Dict:
        """Read PPTX file and extract information."""
        return read_pptx(pptx_path, extract_text, self._workspace)

    async def unpack_pptx(self, pptx_path: str, output_dir: str) -> Dict:
        """Unpack PPTX file to directory."""
        return unpack_pptx(pptx_path, output_dir, self._workspace)

    async def pack_pptx(
        self, input_dir: str, output_path: str, validate: bool = True
    ) -> Dict:
        """Pack directory into PPTX file."""
        return pack_pptx(input_dir, output_path, validate, self._workspace)

    async def clean_pptx(self, unpacked_dir: str) -> Dict:
        """Clean orphaned files from unpacked PPTX directory."""
        return clean_pptx(unpacked_dir, self._workspace)

    async def generate_pptx(
        self,
        output_path: str,
        title: str = "Presentation",
        theme: str = "aurora",
        theme_config: dict | None = None,
        slide_contents: list | str | None = None,
    ) -> Dict:
        """Generate a new PPTX presentation from slide definitions.

        Args:
            output_path: Output .pptx file name (saved to workspace output directory)
            title: Presentation title
            theme: Preset theme name - 'aurora' (light), 'vortex' (dark), or 'mono' (minimal)
            theme_config: Custom theme config dict to override preset
            slide_contents: List of slide dicts, each with 'type' and content fields.
                Supported slide types: title, content, two_column, section_divider,
                quote, thank_you, metrics, timeline, comparison, statement,
                image_highlight, flow.
                Example: [{'type': 'title', 'title': 'My Title', 'subtitle': 'Sub'},
                          {'type': 'content', 'title': 'Topic', 'bullets': ['A', 'B']}]
        """
        return generate_pptx(
            output_path=output_path,
            title=title,
            theme=theme,
            theme_config=theme_config,
            slide_contents=slide_contents,
            workspace=self._workspace,
        )

    def get_tools(self) -> list:
        """Get all tool instances."""
        return [
            PPTXTool(
                self.read_pptx,
                name="read_pptx",
                description="""Read PPTX file and extract information.

Use this tool to:
- Get slide count and slide information from a .pptx file
- Extract all text content from a presentation
- Read slide titles and structure
- Analyze existing presentations as reference

Args:
    pptx_path: Path to .pptx file to read
    extract_text: If True, extracts all text content; if False, returns slide structure

Returns:
    Dictionary with slide information or extracted text
""",
                tags=["pptx", "presentation", "file"],
            ),
            PPTXTool(
                self.unpack_pptx,
                name="unpack_pptx",
                description="""Unpack PPTX file to directory for advanced editing.

Extracts PPTX ZIP archive and pretty-prints XML files for manual editing.
Use when you need to:
- Manually edit PPTX XML structure
- Inspect PPTX internal files and structure
- Modify slide layouts directly
- Learn from existing presentation templates
- Before using pack_pptx to repackage

Args:
    pptx_path: Path to .pptx file to unpack
    output_dir: Directory path to extract files to

Returns:
    Dictionary with success status, output directory, and file count
""",
                tags=["pptx", "presentation", "unpack", "editing"],
            ),
            PPTXTool(
                self.pack_pptx,
                name="pack_pptx",
                description="""Pack directory into PPTX file.

Packages an unpacked PPTX directory back into a valid .pptx file.
Use after unpacking and editing with unpack_pptx.

Args:
    input_dir: Directory containing unpacked PPTX files
    output_path: Output .pptx file path
    validate: Whether to validate structure (default: True)

Returns:
    Dictionary with success status and output file path
""",
                tags=["pptx", "presentation", "pack", "editing"],
            ),
            PPTXTool(
                self.clean_pptx,
                name="clean_pptx",
                description="""Clean orphaned files from unpacked PPTX directory.

Removes slides that are not in presentation.xml slide list,
unreferenced media files, and orphaned relationship files.

Use this when:
- PPTX has unused/orphaned slides
- Media directory has unreferenced images
- After manually deleting slides
- Before packaging with pack_pptx

Args:
    unpacked_dir: Path to unpacked PPTX directory

Returns:
    Dictionary with success status and count of removed files
""",
                tags=["pptx", "presentation", "clean", "editing"],
            ),
            PPTXTool(
                self.generate_pptx,
                name="generate_pptx",
                description="""Generate a new PowerPoint presentation (.pptx) from slide definitions.

Use this tool as the PRIMARY method for creating presentations - it handles file registration
and workspace integration automatically. Use execute_javascript_code only for complex
customizations not supported by this tool.

Args:
    output_path: Output .pptx file name (e.g., 'my_deck.pptx') - saved to workspace output
    title: Presentation title
    theme: Preset theme - 'aurora' (light, default), 'vortex' (dark), or 'mono' (minimal)
    theme_config: Optional custom theme config dict for full control over colors/fonts/layout
    slide_contents: List of slide definition dicts. Each slide has a 'type' field and
        type-specific content fields. Supported types and their fields:

        - title: {title, subtitle}
        - content: {title, bullets: [str, ...]}
        - two_column: {title, left: [str, ...], right: [str, ...]}
        - section_divider: {section_title}
        - quote: {text}
        - thank_you: {message}
        - metrics: {title, items: [{label, value}, ...]}
        - timeline: {title, milestones: [{title, description}, ...]}
        - comparison: {title, left_title, right_title, left_items: [...], right_items: [...]}
        - statement: {text}
        - image_highlight: {title, caption, image_path}
        - flow: {title, steps: [str, ...]}

Returns:
    Dictionary with success status, output file path, and file_id for download
""",
                tags=["pptx", "presentation", "generate", "create"],
            ),
        ]


@register_tool(categories={"ppt"})
async def create_pptx_tool(config: "BaseToolConfig") -> list:
    """
    Create PPTX tools with workspace support.

    Registered via @register_tool decorator for auto-discovery.

    Args:
        config: Tool configuration with workspace settings

    Returns:
        List of tool instances
    """
    workspace = ToolFactory._create_workspace(config.get_workspace_config())
    tool_instance = PPTXGenerationTool(workspace)
    return tool_instance.get_tools()
