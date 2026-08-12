# Xagent Agent System

Xagent is a powerful and flexible framework for building and running AI-powered agents with support for various execution patterns, tools, memory management, and observability.

## Engineering Collaboration Protocol

Treat yourself as an engineering collaborator for this repository, not as a passive assistant.

- Deliver complete, reviewable units of work. A useful delivery explains what changed, why it changed, what was verified, and what trade-offs remain.
- Default to doing the next necessary step when it is part of the task. Do not stop to ask whether to continue when the path is reversible and can be judged from the codebase.
- Ask the user only when continuing would likely produce work opposite to the user's intent. Do not ask about reversible implementation details, ordinary style choices, or obvious follow-up steps.
- Prioritize correctness over conversational comfort. The order of authority is:
  1. The task completion standard: code compiles, tests pass, types check, and the feature works.
  2. Existing project style and architecture, learned from reading the code.
  3. The user's explicit, unambiguous instruction.
- Report results at the end with engineering substance. Process chatter is not a substitute for verification.

## Windows, WSL, and Shell Safety

This repository is often operated from Windows while also using WSL. Be careful with multi-layer command parsing.

- Prefer simple, single-purpose commands. For file reading, search, git inspection, and script checks, WSL commands are often less error-prone than complex PowerShell pipelines.
- Use `rg` first for code search. If WSL lacks `rg`, avoid unbounded full-repo `grep -R`; restrict searches to relevant directories.
- Do not pass secrets containing `$`, quotes, or shell metacharacters through `wsl.exe env NAME=value ...` from PowerShell. PowerShell or the outer shell may expand or truncate values before WSL receives them.
- Do not echo full passwords, tokens, API keys, kubeconfigs, or other sensitive values in command output.
- When sensitive values must be set for a WSL command, assign them inside the WSL shell and escape literal `$` as needed, for example:

```powershell
wsl.exe -- bash -lc 'PASSWORD=p\$\$word command-that-reads-password-from-env'
```

- Avoid complex nested one-liners that mix PowerShell, `wsl.exe bash -lc`, SSH, Python `-c`, heredocs, regular expressions, pipes, and shell variables. If a command needs loops, dictionaries, JSON, multi-line Python, or fragile quoting, write a small script in the repository or use explicit separate commands.
- Do not rely on unescaped `$var` / `${var}` inside a PowerShell string intended for WSL. The outer layer may expand it before Bash sees it.
- WSL does not by itself solve PowerShell pre-parsing. The command string is
  parsed by PowerShell before `wsl.exe` receives it, so Bash fragments such as
  `$c:$base/path` can fail in PowerShell with `变量引用无效` before they ever
  reach WSL. When a WSL command needs Bash variables next to a colon, use
  `${c}:${base}/path` and protect the whole Bash program from PowerShell
  expansion, or avoid the loop and run explicit `docker cp` / shell commands
  one by one. For fragile Docker hot-patch loops, prefer explicit commands over
  clever nested `for` loops.
- Avoid passing complex regex such as `grep -E "a|b"` through multiple shells. Prefer a script, a pattern file, or simpler sequential filters.
- For remote SSH or `kubectl` work, avoid packing many remote operations into one nested command string with `;`, `&&`, pipes, or heavy quoting. Prefer one SSH command per clear operation, or upload and run a script.
- If WSL-exposed Docker Desktop or `kubectl` commands fail with local `Input/output error`, first try `wsl.exe --shutdown` and rerun before treating it as a Kubernetes API problem.
- Use PowerShell directly only when the task requires Windows-specific tooling or the user explicitly asks for it.
- Docker Desktop may be accessible from WSL even when the Windows-side Docker
  client fails with permission errors such as `Access is denied` on
  `//./pipe/docker_engine` or cannot read `~/.docker/config.json`. In this
  repo, prefer checking service state from WSL before concluding Docker is down
  or asking to start Compose, for example:

```bash
wsl bash -lc 'cd /mnt/d/github/xagent && docker compose ps'
wsl bash -lc 'cd /mnt/d/github/xagent && docker logs xagent_nginx --tail 80'
```

- Do not conclude that port 80 is not listening solely from a failed
  non-elevated Windows-side check. Cross-check through WSL Docker/Compose and
  direct HTTP probes.
- When `http://localhost` times out in Windows PowerShell but
  `http://127.0.0.1` works, suspect a localhost resolution path difference,
  especially IPv6 `::1` versus IPv4 `127.0.0.1`. Prefer resolving this class of
  issue through WSL instead of Windows-side workarounds: run the localhost
  diagnostics, login checks, Docker checks, and Agent 31 loop regression commands
  from WSL. Keep generated URLs as `http://localhost`.

## Features

- **Agent Patterns**: ReAct, DAG plan-execute
- **Nested Agents**: Hierarchical agent execution with parent-child relationships
- **Tool System**: Built-in tools with auto-discovery mechanism
- **Memory Management**: LanceDB-based vector storage with semantic search
- **Observability**: Langfuse integration for tracing and monitoring
- **Real-time Communication**: WebSocket support for agent execution monitoring

## Architecture Overview

### Entry Points

Xagent has one main entrypoint:

**Web Interface (`src/xagent/web/`):**
- FastAPI-based web application with WebSocket support
- Real-time agent execution monitoring
- File upload and management
- DAG visualization
- API endpoints for agent operations

## Architecture Overview

### Core Components (`src/xagent/core/`)

**Agent System (`src/xagent/core/agent/`):**
- `service.py` - `AgentService` facade used by web/chat/preview/builder entry points.
- `agent.py` - Core `Agent` definition for the only supported execution runtime.
- `execution_adapter.py` - Adapts `AgentService` calls into `AgentRunner` executions.
- `runner.py` - Execution engine with pause/resume/interruption and checkpoint loading.
- `runtime.py` - Cross-cutting pattern services: LLM calls, tool calls, tracing, checkpoints, outbound messages, and context compaction.
- `context/` - Message and execution context management.
- `pattern/` - Execution patterns: `single_call`, ReAct, DAG plan-execute, and auto routing.
- `checkpoint.py` - Trace-backed checkpoint persistence for resumable executions.

There is no v1/v2 runtime switch. Do not add new code under `agent_v2` or `agent_runtime`; both concepts have been collapsed into `core.agent`.

Execution mode mapping:
- `flash` -> `single_call`
- `balanced` -> ReAct
- `think` -> DAG plan-execute
- `auto` -> auto pattern selection between final-answer, ReAct, and DAG

Agent tasks built in the agent builder should default to memory disabled unless a future product change adds an explicit switch. Knowledge base/RAG grounding is separate from memory.

**Graph System:**
- `graph.py` - Graph workflow execution engine with validation
- `node.py` - Node types (Start, End, Agent, Tool, etc.)
- `node_factory.py` - Node creation factory

**Tools System:**
- `adapters/` - Tool adapters for different frameworks
- `core/` - Core tool implementations (calculator, file operations, web search, etc.)
- Tool auto-discovery using `get_{tool_name}_tool()` naming convention

**Model Integration:**
- `llm/` - LLM provider implementations (OpenAI, Zhipu)
- Support for embedding models and reranking models

**Memory Management:**
- `storage/` - Storage manager and database operations
- `workspace.py` - Task workspace management with isolated working directories

**Observability:**
- Langfuse integration for tracing and monitoring
- Execution history and message tracking

### Configuration System

**IMPORTANT**: All path-related and configuration settings SHALL try their best to use the unified configuration module at `src/xagent/config.py`.

**Core Principles:**
1. **Single source of truth** - All configuration goes through `config.py`
2. **No hardcoded paths** - Never use string literals like `"uploads"` or `"./data"`
3. **Environment variable support** - All paths must be configurable via `XAGENT_*` env vars
4. **No circular dependencies** - `config.py` has no dependencies on other core submodules

**Import Style:**
- **Source code** (`src/xagent/`): Use relative imports
  ```python
  from ..config import get_uploads_dir, get_storage_root
  ```
- **Test files** (`tests/`): Use absolute imports
  ```python
  from xagent.config import get_uploads_dir, get_storage_root
  ```

**Configuration Pattern:**
```python
def get_<config_name>() -> ReturnType:
    """Get <config> with environment variable override.

    Priority:
        1. <ENV_VAR> environment variable
        2. Computed default

    Returns:
        Description of return value
    """
    env_value = os.getenv(ENV_VAR)
    if env_value:
        return <process_env_value>(env_value)

    # Default computation
    return <compute_default>()
```

**Adding New Configuration:**
1. Add function to `src/xagent/config.py`
2. Add env var constant: `<ENV_VAR> = "XAGENT_<NAME>"`
3. Follow env var → default priority pattern
4. Update `example.env` with documentation
5. Add tests to `tests/core/test_config.py`

### Available Tools

Xagent has two categories of tools:

**Basic Tools** (`src/xagent/core/tools/core/`):
- `calculator` - Mathematical expression evaluation
- `file_tool` - File operations (read, write, list, edit, delete)
- `workspace_file_tool` - Workspace file operations
- `python_executor` - Dynamic Python code execution
- `browser_use` - Browser automation
- `excel` - Excel file operations
- `document_parser` - Document parsing (PDF, DOCX, etc.)
- `image_tool` - Image processing

**Web & Search Tools** (`src/xagent/core/tools/core/`):
- `web_search` - Generic web search
- `image_web_search` - Image search functionality
- `zhipu_web_search` - Zhipu search integration
- `web_crawler` - Web crawling and content extraction

**RAG Tools** (`src/xagent/core/tools/core/RAG_tools/`):
- Document parsing and chunking
- Vector storage and retrieval (LanceDB)
- Knowledge base management
- Semantic search capabilities

**MCP Server Tools** (`src/xagent/core/tools/core/mcp/`):
- Model Context Protocol (MCP) server integration
- Standardized tool access via MCP protocol

**Skill Documentation Access Tools** (`src/xagent/core/tools/adapters/vibe/skill_tools.py`):
- `read_skill_doc` - Read documentation from skill directories (SKILL.md, examples, etc.)
- `list_skill_docs` - List documentation files in skill directories (returns names and sizes)
- `fetch_skill_file` - Copy resource files from skill directories to workspace

### Custom Tools

Create custom tools by adding Python files following the naming convention:

```python
from langchain_core.tools import BaseTool, tool

def get_my_tool(_info: Optional[dict[str, str]] = None) -> BaseTool:
    """My custom tool description"""
    return tool(my_tool_function)
```

**Requirements:**
- Function name pattern: `get_{tool_name}_tool()`
- File location: `src/xagent/core/tools/core/`
- Return type: `BaseTool` instance from langchain_core
- No manual registration needed - auto-discovery on load

## Environment Configuration

Create a `.env` file based on `example.env` with required API keys:
```bash
OPENAI_API_KEY="your-openai-key"
DEEPSEEK_API_KEY="your-deepseek-key"
GOOGLE_API_KEY="your-google-api-key"
GOOGLE_CSE_ID="your-google-cse-id"
LANGFUSE_PUBLIC_KEY="your-langfuse-public-key"
LANGFUSE_SECRET_KEY="your-langfuse-secret-key"
```

### Local Development Conventions

**Commit and PR titles:**
- Use a short conventional prefix: `feat:`, `fix:`, `enh:`, `ref:`, or `chore:`.
- Prefer the same prefix in PR titles so split PRs are easy to scan.
- Keep branch names meaningful and task-oriented, for example `fix/remove-agent-v1` or `feat/agent-builder-preview`. Avoid generic agent/tool prefixes that do not describe the work.

**Agent 31 loop regression:**
- For the interview psychologist loop regression work, use `http://localhost` as the base URL. Do not default generated scripts, docs, or reports to a port-qualified localhost URL for this flow unless the user explicitly asks for that port.
- Run Agent 31 HTTP regression from WSL when debugging local Docker/localhost issues. The known-good flow is: login to `http://localhost` as admin, rotate or obtain the Agent 31 runtime API key, call `/v1/chat/tasks`, then poll `/v1/chat/tasks/{task_id}`.
- Agent 31 is configured for DAG `think` mode and a single smoke case can take 7-10 minutes. Use a per-case timeout around 900 seconds for real HTTP regression; shorter 120-240 second timeouts can falsely report a timeout while the task is still running.
- If a completed Agent 31 task already exists, prefer rejudging it with `scripts/loop_data_factory/run_agent31_regression.py --reuse-task-id <id> --limit 1` instead of creating another expensive run.
- A failure like `Tool call arguments must be valid JSON.` during `dag_plan_generation_failed` is a model/DAG planning output-format failure, not a localhost, Docker, login, or runtime API key failure. Treat it as a planning retry/repair problem.
- The planner repair path belongs inside `LLMPlanGenerator.generate_plan`: when `generate_execution_plan` has invalid JSON or invalid plan arguments, feed the error back as a user retry message and call the planning tool again. This keeps the failure local to planning instead of surfacing as a failed task.

**Local data locations:**
- The default storage root is `~/.xagent`, configured by `XAGENT_STORAGE_ROOT`.
- The default SQLite database is `~/.xagent/xagent.db`, unless `DATABASE_URL` is set.
- The default KB/RAG LanceDB path is `~/.xagent/data/lancedb`, unless `LANCEDB_PATH`/`LANCEDB_DIR` is set by the specific code path.
- User memory and knowledge base storage are different concepts. Agent/user memory uses `DynamicMemoryStoreManager`; when a LanceDB memory store is active it defaults to `~/.xagent/memory_store` after checking the legacy project `memory_store/` directory. KB/RAG collections use the RAG storage layer and the LanceDB path above.
- Uploaded files default to `src/xagent/web/uploads`, unless `XAGENT_UPLOADS_DIR` is set. External upload roots must go through `XAGENT_EXTERNAL_UPLOAD_DIRS`.
- Do not hardcode these paths in source or tests. Use `src/xagent/config.py` helpers or explicitly override env vars in tests.

### Optional Dependencies for Presentation Generation

If you plan to use the presentation generator feature (JavaScript-based PowerPoint creation via `execute_javascript_code` tool), you need to install Node.js and pptxgenjs:

```bash
# Ensure Node.js 20+ is installed
node --version

# Install pptxgenjs globally for presentation generation
npm install -g pptxgenjs@4.0.1

# Verify installation
npm root -g  # Should show path to global node_modules
ls $(npm root -g)/pptxgenjs  # Should show the package directory
```

**Note:** Without this installation, the `javascript_executor` tool will fail with "Cannot find module 'pptxgenjs'" when generating presentations. The pptxgenjs package is automatically installed in Docker/CI environments.

## Development Commands

### Installation and Setup
```bash
# Install the package with core dependencies only (SQLite, basic PDF support)
pip install -e .

# Install development dependencies (requires pip >= 25.1 or uv)
pip install -e . --group dev

# Install optional extras for additional features
pip install -e ".[document-processing]" # Document processing libraries
pip install -e ".[ai-document]"         # AI-related document processing (docling)
pip install -e ".[postgresql]"          # PostgreSQL database driver
pip install -e ".[browser]"             # Browser automation (playwright)
pip install -e ".[chromadb]"            # ChromaDB vector database
pip install -e ".[milvus]"              # Milvus vector database
pip install -e ".[all]"                 # Install all optional extras

# For development with all features:
pip install -e ".[all]" --group dev

# For older pip versions, use uv instead:
# uv sync --group dev --extra all
```

**Optional Extras:**
| Extra | Description |
|-------|-------------|
| `document-processing` | document processing libraries (pdfplumber, unstructured, pymupdf, etc.) |
| `ai-document` | AI-related document processing (docling) |
| `postgresql` | PostgreSQL driver (uses psycopg2-binary; for production consider psycopg2) |
| `browser` | Browser automation (playwright) |
| `chromadb` | ChromaDB vector database (alternative to LanceDB) |
| `milvus` | Milvus vector database (alternative to LanceDB) |
| `all` | All optional extras combined |

**Note**: Pre-commit hooks are installed via `--group dev`, not as an optional extra.

### Running Tests
```bash
# Run all tests
pytest

# Run tests with coverage
pytest --cov=src/xagent --cov-report=html

# Run specific test categories
pytest -m integration  # Integration tests
pytest -m slow         # Slow tests

# Run specific test files
pytest tests/core/agent/test_agent.py
pytest tests/web_integration/test_comprehensive.py
```

### Local Verification Fallbacks

Some Windows/WSL workstations do not have the full Python test environment
available in every shell. In the current local setup, WSL has `python3` but may
not have `pytest`, while Windows-side `python` may be unavailable.

- Do not treat missing `pytest` or missing Windows `python` as a product
  failure. Report it as an environment limitation.
- For stdlib-only scripts and generators, verify behavior directly with WSL
  `python3` from the repository root, for example:

```bash
wsl bash -lc 'cd /mnt/d/github/xagent && python3 scripts/path/to/script.py --help'
```

- Still add or update pytest test files when the change warrants tests. The
  tests should be runnable in the normal development environment even if the
  current workstation can only run direct CLI smoke checks.
- In final delivery notes, distinguish direct CLI verification from skipped
  pytest execution, and include the exact reason when pytest could not run.

### Code Quality and Linting
```bash
# Format code with ruff
ruff format .

# Lint code with ruff
ruff check .

# Type checking with mypy
mypy src/xagent

# Run pre-commit hooks
pre-commit run --all-files
```

### Running the Application

Xagent has separate frontend and backend components:

**Backend (Web API):**
```bash
python -m xagent.web.__main__
# For Agent 31 loop regression, route through http://localhost.
```

**Frontend (Web UI):**
```bash
cd frontend
npm run dev    # Development mode with hot-reload
npm run build  # Production build
npm run start  # Production mode
# Use the localhost URL printed by the frontend dev server.
```

**Development Mode:**
Run both backend and frontend in separate terminals for full-stack development.

### Docker Release Image Bumps

When bumping Docker release image tags, update all fixed Xagent images together:
- All fixed Xagent service images present in `docker-compose.yml`
- `docker/docker-compose.sandbox.boxlite.yml` `SANDBOX_IMAGE`
- `docker/docker-compose.sandbox.docker.yml` `SANDBOX_IMAGE`

Validate both the base compose file and sandbox overlays:
```bash
docker compose config --quiet
docker compose -f docker-compose.yml -f docker/docker-compose.sandbox.boxlite.yml config --quiet
docker compose -f docker-compose.yml -f docker/docker-compose.sandbox.docker.yml config --quiet
```

## Skills Configuration

Skills directories can be extended using the `XAGENT_EXTERNAL_SKILLS_LIBRARY_DIRS` environment variable:
- External directories are **appended** to default built-in and user directories
- Comma-separated list of paths
- Supports local directories, home directory expansion, and environment variables
- Non-existent paths are skipped with warnings
- Default directories are always loaded

Load order: built-in → user → external (later skills override earlier ones with the same name)

Examples:
```bash
# Single directory (appended to defaults)
XAGENT_EXTERNAL_SKILLS_LIBRARY_DIRS="/path/to/custom/skills"

# Multiple directories
XAGENT_EXTERNAL_SKILLS_LIBRARY_DIRS="/path/to/skills1,/path/to/skills2,~/skills"

# With path expansion
XAGENT_EXTERNAL_SKILLS_LIBRARY_DIRS="~/skills,$HOME/custom_skills,./local_skills"
```

See `src/xagent/skills/README.md` for details.
Run both backend and frontend in separate terminals for full-stack development.
