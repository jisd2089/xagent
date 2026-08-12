"""Import loop design/research docs into a KB collection and bind Agent 31."""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import secrets
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.loop_data_factory.export_agent_snapshot import (
    export_agent_snapshot,
    fetch_agent,
    login,
    request_json,
)


DEFAULT_COLLECTION = "interview_psychologist_loop_kb"
DEFAULT_SOURCE_FILES = [
    "deep_research_data_inventory.md",
    "recruitment_compliance_guardrails.md",
    "structured_interview_bei_bars_library.md",
    "software_industrial_ai_competency_library.md",
    "loop_calibration_seed_dataset.md",
    "local_seed_case_anonymized.md",
    "three_loops_auto_data_generation_spec.md",
    "interview_psychologist_agent_three_loops_design.md",
    "interview_psychologist_agent_three_loops_requirements.md",
    "three_loops_implementation_design.md",
    "agent31_deep_research_test_prompts.md",
]


def import_and_bind_loop_kb(
    *,
    api_base: str,
    agent_id: int,
    username: str,
    password: str,
    docs_dir: Path,
    output_dir: Path,
    collection: str = DEFAULT_COLLECTION,
    source_files: list[str] | None = None,
    embedding_model_id: str = "text-embedding-v4",
    chunk_strategy: str = "markdown",
    bind_even_if_upload_fails: bool = False,
    force_upload: bool = False,
    import_manifest_path: Path | None = None,
) -> dict[str, Any]:
    token = login(api_base=api_base, username=username, password=password)
    selected_files = resolve_source_files(docs_dir, source_files or DEFAULT_SOURCE_FILES)
    manifest_path = import_manifest_path or output_dir / "agent31_kb_import_manifest.json"
    import_manifest = load_import_manifest(manifest_path)

    before_collections = list_collection_names(api_base=api_base, token=token)
    upload_results = []
    for path in selected_files:
        fingerprint = build_file_fingerprint(path)
        manifest_key = build_manifest_key(collection=collection, docs_dir=docs_dir, path=path)
        if not force_upload and is_manifest_entry_current(
            import_manifest.get(manifest_key),
            fingerprint=fingerprint,
            embedding_model_id=embedding_model_id,
            chunk_strategy=chunk_strategy,
        ):
            upload_results.append(
                {
                    "status": "skipped",
                    "file": str(path),
                    "reason": "same sha256 already imported into collection",
                    "sha256": fingerprint["sha256"],
                }
            )
            continue

        result = upload_kb_document(
            api_base=api_base,
            token=token,
            collection=collection,
            path=path,
            embedding_model_id=embedding_model_id,
            chunk_strategy=chunk_strategy,
        )
        if result["status"] == "success":
            import_manifest[manifest_key] = {
                **fingerprint,
                "collection": collection,
                "source": manifest_key.split(":", 1)[1],
                "embedding_model_id": embedding_model_id,
                "chunk_strategy": chunk_strategy,
                "imported_at": datetime.now(timezone.utc).isoformat(),
            }
            result["sha256"] = fingerprint["sha256"]
        upload_results.append(result)

    save_import_manifest(manifest_path, import_manifest)
    after_collections = list_collection_names(api_base=api_base, token=token)
    upload_failures = [item for item in upload_results if item["status"] == "error"]
    skipped_uploads = [item for item in upload_results if item["status"] == "skipped"]
    collection_visible = collection in after_collections

    bind_result: dict[str, Any] = {
        "status": "skipped",
        "reason": "collection upload had failures or collection is not visible",
    }
    if collection_visible and (bind_even_if_upload_fails or not upload_failures):
        bind_result = bind_agent_to_collection(
            api_base=api_base,
            token=token,
            agent_id=agent_id,
            collection=collection,
        )

    generated_at = datetime.now(timezone.utc).isoformat()
    report = {
        "generated_at": generated_at,
        "api_base": api_base.rstrip("/"),
        "agent_id": agent_id,
        "collection": collection,
        "docs_dir": str(docs_dir),
        "import_manifest_path": str(manifest_path),
        "force_upload": force_upload,
        "source_files": [str(path) for path in selected_files],
        "collections_before": before_collections,
        "collections_after": after_collections,
        "collection_visible": collection_visible,
        "upload": {
            "total": len(upload_results),
            "succeeded": len([item for item in upload_results if item["status"] == "success"]),
            "skipped": len(skipped_uploads),
            "failed": len(upload_failures),
            "results": upload_results,
        },
        "bind_result": bind_result,
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "agent31_kb_binding_report.json"
    md_path = output_dir / "agent31_kb_binding_report.md"
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    md_path.write_text(render_binding_report_markdown(report), encoding="utf-8")

    if bind_result.get("status") == "success":
        snapshot_paths = export_agent_snapshot(
            api_base=api_base,
            agent_id=agent_id,
            username=username,
            password=password,
            output_dir=output_dir,
        )
        report["snapshot_paths"] = snapshot_paths
        json_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        md_path.write_text(render_binding_report_markdown(report), encoding="utf-8")

    return {"report_path": str(json_path), "markdown_path": str(md_path), **report}


def resolve_source_files(docs_dir: Path, filenames: list[str]) -> list[Path]:
    paths = [docs_dir / filename for filename in filenames]
    missing = [str(path) for path in paths if not path.exists()]
    if missing:
        raise FileNotFoundError("Missing KB source file(s): " + ", ".join(missing))
    return paths


def load_import_manifest(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def save_import_manifest(path: Path, manifest: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(dict(sorted(manifest.items())), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def build_file_fingerprint(path: Path) -> dict[str, Any]:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    stat = path.stat()
    return {
        "sha256": digest.hexdigest(),
        "size_bytes": stat.st_size,
    }


def build_manifest_key(*, collection: str, docs_dir: Path, path: Path) -> str:
    try:
        source = path.relative_to(docs_dir).as_posix()
    except ValueError:
        source = path.name
    return f"{collection}:{source}"


def is_manifest_entry_current(
    entry: Any,
    *,
    fingerprint: dict[str, Any],
    embedding_model_id: str,
    chunk_strategy: str,
) -> bool:
    return (
        isinstance(entry, dict)
        and entry.get("sha256") == fingerprint["sha256"]
        and entry.get("size_bytes") == fingerprint["size_bytes"]
        and entry.get("embedding_model_id") == embedding_model_id
        and entry.get("chunk_strategy") == chunk_strategy
    )


def list_collection_names(*, api_base: str, token: str) -> list[str]:
    data = request_json("GET", f"{api_base.rstrip('/')}/api/kb/collections", token, None)
    collections = data.get("collections")
    if not isinstance(collections, list):
        return []
    names = []
    for item in collections:
        if isinstance(item, dict) and isinstance(item.get("name"), str):
            names.append(item["name"])
    return sorted(set(names))


def upload_kb_document(
    *,
    api_base: str,
    token: str,
    collection: str,
    path: Path,
    embedding_model_id: str,
    chunk_strategy: str,
) -> dict[str, Any]:
    fields = {
        "collection": collection,
        "embedding_model_id": embedding_model_id,
        "chunk_strategy": chunk_strategy,
    }
    try:
        response = request_multipart_json(
            f"{api_base.rstrip('/')}/api/kb/ingest",
            token,
            fields,
            file_field="file",
            file_path=path,
        )
        return {
            "status": "success",
            "file": str(path),
            "response": response,
        }
    except Exception as exc:
        return {
            "status": "error",
            "file": str(path),
            "error": str(exc),
        }


def bind_agent_to_collection(
    *,
    api_base: str,
    token: str,
    agent_id: int,
    collection: str,
) -> dict[str, Any]:
    agent = fetch_agent(api_base=api_base, agent_id=agent_id, token=token)
    tool_categories = merge_unique(agent.get("tool_categories") or [], ["knowledge"])
    knowledge_bases = merge_unique(agent.get("knowledge_bases") or [], [collection])
    updated = request_json(
        "PUT",
        f"{api_base.rstrip('/')}/api/agents/{agent_id}",
        token,
        {
            "knowledge_bases": knowledge_bases,
            "tool_categories": tool_categories,
        },
    )
    return {
        "status": "success",
        "knowledge_bases": updated.get("knowledge_bases") or [],
        "tool_categories": updated.get("tool_categories") or [],
    }


def merge_unique(existing: list[Any], additions: list[str]) -> list[str]:
    merged: list[str] = []
    for item in [*existing, *additions]:
        if isinstance(item, str) and item and item not in merged:
            merged.append(item)
    return merged


def request_multipart_json(
    url: str,
    bearer_token: str,
    fields: dict[str, str],
    *,
    file_field: str,
    file_path: Path,
) -> dict[str, Any]:
    boundary = "----xagent-loop-boundary-" + secrets.token_hex(12)
    body = build_multipart_body(
        fields=fields,
        file_field=file_field,
        file_path=file_path,
        boundary=boundary,
    )
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {bearer_token}",
        "Content-Type": f"multipart/form-data; boundary={boundary}",
    }
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            data = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"POST {url} failed: HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"POST {url} failed: {exc.reason}") from exc
    loaded = json.loads(data)
    if not isinstance(loaded, dict):
        raise RuntimeError(f"POST {url} returned non-object JSON")
    return loaded


def build_multipart_body(
    *,
    fields: dict[str, str],
    file_field: str,
    file_path: Path,
    boundary: str,
) -> bytes:
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.extend(
            [
                f"--{boundary}\r\n".encode("utf-8"),
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(
                    "utf-8"
                ),
                str(value).encode("utf-8"),
                b"\r\n",
            ]
        )

    content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    chunks.extend(
        [
            f"--{boundary}\r\n".encode("utf-8"),
            (
                f'Content-Disposition: form-data; name="{file_field}"; '
                f'filename="{file_path.name}"\r\n'
            ).encode("utf-8"),
            f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"),
            file_path.read_bytes(),
            b"\r\n",
            f"--{boundary}--\r\n".encode("utf-8"),
        ]
    )
    return b"".join(chunks)


def render_binding_report_markdown(report: dict[str, Any]) -> str:
    upload = report["upload"]
    bind = report["bind_result"]
    lines = [
        "# Agent 31 知识库导入与绑定报告",
        "",
        f"- 生成时间：`{report['generated_at']}`",
        f"- API Base：`{report['api_base']}`",
        f"- Collection：`{report['collection']}`",
        f"- Collection 可见：`{report['collection_visible']}`",
        f"- Import Manifest：`{report['import_manifest_path']}`",
        f"- 强制上传：`{report['force_upload']}`",
        f"- 上传结果：`{upload['succeeded']}` 上传，`{upload['skipped']}` 跳过，`{upload['failed']}` 失败，总计 `{upload['total']}`",
        f"- 绑定状态：`{bind.get('status')}`",
        "",
        "## 上传明细",
        "",
        "| 文件 | 状态 | 说明 |",
        "| --- | --- | --- |",
    ]
    for item in upload["results"]:
        detail = item.get("error") or item.get("reason") or item.get("response", {}).get("message") or ""
        lines.append(
            f"| `{Path(item['file']).name}` | `{item['status']}` | {markdown_cell(detail)} |"
        )
    lines.extend(
        [
            "",
            "## Agent 绑定结果",
            "",
            "```json",
            json.dumps(bind, ensure_ascii=False, indent=2),
            "```",
            "",
        ]
    )
    if report.get("snapshot_paths"):
        lines.extend(
            [
                "## 后续快照",
                "",
                f"- JSON：`{report['snapshot_paths']['json_path']}`",
                f"- Markdown：`{report['snapshot_paths']['markdown_path']}`",
                "",
            ]
        )
    return "\n".join(lines)


def markdown_cell(value: Any) -> str:
    text = "" if value is None else str(value)
    return text.replace("|", "\\|").replace("\n", "<br>")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-base", default="http://localhost")
    parser.add_argument("--agent-id", type=int, default=31)
    parser.add_argument("--login-username", required=True)
    parser.add_argument("--login-password", required=True)
    parser.add_argument("--docs-dir", type=Path, default=Path("docs/loop"))
    parser.add_argument("--output-dir", type=Path, default=Path("docs/loop"))
    parser.add_argument("--collection", default=DEFAULT_COLLECTION)
    parser.add_argument("--embedding-model-id", default="text-embedding-v4")
    parser.add_argument("--chunk-strategy", default="markdown")
    parser.add_argument(
        "--source-file",
        action="append",
        dest="source_files",
        help="Markdown filename under --docs-dir. Repeat to override the default file set.",
    )
    parser.add_argument(
        "--bind-even-if-upload-fails",
        action="store_true",
        help="Bind the collection if it is visible even when one or more uploads fail.",
    )
    parser.add_argument(
        "--force-upload",
        action="store_true",
        help="Upload files even when the local import manifest says the same sha256 was already imported.",
    )
    parser.add_argument(
        "--import-manifest",
        type=Path,
        default=None,
        help="Path to the local KB import manifest. Defaults to agent31_kb_import_manifest.json under --output-dir.",
    )
    args = parser.parse_args()
    report = import_and_bind_loop_kb(
        api_base=args.api_base,
        agent_id=args.agent_id,
        username=args.login_username,
        password=args.login_password,
        docs_dir=args.docs_dir,
        output_dir=args.output_dir,
        collection=args.collection,
        source_files=args.source_files,
        embedding_model_id=args.embedding_model_id,
        chunk_strategy=args.chunk_strategy,
        bind_even_if_upload_fails=args.bind_even_if_upload_fails,
        force_upload=args.force_upload,
        import_manifest_path=args.import_manifest,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
