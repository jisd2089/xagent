#!/usr/bin/env python3
"""
sync_aihub_tools.py — Sync 53AIHub Mock Gateway Agent capabilities to xAgent Custom API tools

Usage:
  python scripts/sync_aihub_tools.py [--dry-run] [--skip-existing]

Environment variables:
  AIHUB_BASE_URL         53AIHub base URL (default: http://localhost:3000/)
  AIHUB_TOKEN            Mock Gateway service token
  XAGENT_BASE_URL        xAgent base URL (default: http://localhost:80)
  XAGENT_USERNAME        xAgent admin username
  XAGENT_PASSWORD        xAgent admin password
  XAGENT_TOKEN           xAgent JWT token (alternative to username/password)

Process:
  1. Fetch tool definitions from 53AIHub GET /api/mock/sync/xagent-tools
  2. For each tool, register it in xAgent via POST /api/custom-apis
  3. If a tool with the same name already exists, update via PUT (or skip with --skip-existing)
  4. Report sync results
"""

import argparse
import json
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_AIHUB_URL = "http://localhost:3000/"
DEFAULT_XAGENT_URL = "http://localhost:80"


def get_env_or_default(key: str, default: str) -> str:
    val = os.environ.get(key, "").strip()
    return val if val else default


def get_env_required(key: str) -> str:
    val = os.environ.get(key, "").strip()
    if not val:
        print(f"[ERROR] Required environment variable '{key}' is not set.")
        sys.exit(1)
    return val


# ---------------------------------------------------------------------------
# xAgent authentication
# ---------------------------------------------------------------------------


def xagent_login(base_url: str, username: str, password: str) -> str:
    """Get a JWT access token from xAgent."""
    resp = requests.post(
        f"{base_url}/api/auth/login",
        json={"username": username, "password": password},
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    token = data.get("access_token") or data.get("data", {}).get("access_token")
    if not token:
        print(f"[ERROR] Login succeeded but no access_token in response: {json.dumps(data, indent=2)}")
        sys.exit(1)
    print(f"[INFO] Logged into xAgent as '{username}'")
    return token


# ---------------------------------------------------------------------------
# Fetch tools from 53AIHub
# ---------------------------------------------------------------------------


def fetch_aihub_tools(base_url: str, token: str) -> Dict[str, Any]:
    """Fetch mock agent tool definitions from 53AIHub."""
    url = f"{base_url}api/mock/sync/xagent-tools"
    headers = {"Authorization": f"Bearer {token}"}
    print(f"[INFO] Fetching tools from {url} ...")
    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    body = resp.json()
    # 53AIHub response format: { "success": true, "data": { "tools": [...], "total_tools": N } }
    data = body.get("data", body)
    tools = data.get("tools", [])
    print(f"[INFO] Fetched {len(tools)} tool definitions from 53AIHub")
    return data


# ---------------------------------------------------------------------------
# Register / update tools in xAgent
# ---------------------------------------------------------------------------


def list_existing_tools(base_url: str, token: str) -> Dict[str, Dict]:
    """List all existing custom API tools in xAgent, keyed by name."""
    url = f"{base_url}/api/custom-apis"
    resp = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=15)
    resp.raise_for_status()
    items = resp.json()
    # Response could be a list or {data: [...]}
    if isinstance(items, dict):
        items = items.get("data", [])
    return {item["name"]: item for item in items if isinstance(item, dict)}


def create_tool(base_url: str, token: str, tool_def: Dict[str, Any]) -> Dict:
    """Register a new custom API tool in xAgent."""
    url = f"{base_url}/api/custom-apis"
    payload = build_xagent_payload(tool_def)
    resp = requests.post(
        url, json=payload, headers={"Authorization": f"Bearer {token}"}, timeout=15
    )
    resp.raise_for_status()
    return resp.json()


def update_tool(base_url: str, token: str, api_id: int, tool_def: Dict[str, Any]) -> Dict:
    """Update an existing custom API tool in xAgent (PUT)."""
    url = f"{base_url}/api/custom-apis/{api_id}"
    payload = build_xagent_payload(tool_def)
    resp = requests.put(
        url, json=payload, headers={"Authorization": f"Bearer {token}"}, timeout=15
    )
    resp.raise_for_status()
    return resp.json()


def build_xagent_payload(tool_def: Dict[str, Any]) -> Dict[str, Any]:
    """Convert 53AIHub tool definition to xAgent Custom API payload."""
    # Extract relevant fields
    name = tool_def.get("name", "")
    description = tool_def.get("description", "")
    url = tool_def.get("url", "")
    method = tool_def.get("method", "POST")
    headers = tool_def.get("headers", {})
    env_vars = tool_def.get("env", {})

    # Clean up: remove $ prefix from env values for registration (xAgent will use the key name)
    # The env dict maps env var names to their values
    cleaned_env = {}
    for k, v in env_vars.items():
        if isinstance(v, str) and v.startswith("$"):
            # Keep the actual value; xAgent uses the key name for $SECRET substitution
            cleaned_env[k] = v
        else:
            cleaned_env[k] = v

    return {
        "name": name,
        "description": description,
        "url": url,
        "method": method.upper(),
        "headers": headers,
        "env": cleaned_env,
        "is_active": True,
    }


# ---------------------------------------------------------------------------
# Sync logic
# ---------------------------------------------------------------------------


def sync_tools(
    aihub_url: str,
    aihub_token: str,
    xagent_url: str,
    xagent_token: str,
    *,
    dry_run: bool = False,
    skip_existing: bool = False,
) -> Tuple[int, int, int]:
    """
    Sync tools and return (created, updated, skipped) counts.
    """
    data = fetch_aihub_tools(aihub_url, aihub_token)
    tools: List[Dict] = data.get("tools", [])
    if not tools:
        print("[INFO] No tools to sync.")
        return 0, 0, 0

    existing = list_existing_tools(xagent_url, xagent_token)
    print(f"[INFO] xAgent already has {len(existing)} custom API tools registered")

    created = 0
    updated = 0
    skipped = 0
    errors = 0

    for tool in tools:
        name = tool.get("name", "unknown")
        try:
            if name in existing:
                if skip_existing:
                    print(f"  [SKIP] '{name}' — already exists (--skip-existing)")
                    skipped += 1
                    continue
                if dry_run:
                    print(f"  [UPDATE] '{name}' (dry-run)")
                    updated += 1
                    continue
                api_id = existing[name]["id"]
                update_tool(xagent_url, xagent_token, api_id, tool)
                print(f"  [UPDATE] '{name}' (id={api_id})")
                updated += 1
            else:
                if dry_run:
                    print(f"  [CREATE] '{name}' (dry-run)")
                    created += 1
                    continue
                create_tool(xagent_url, xagent_token, tool)
                print(f"  [CREATE] '{name}'")
                created += 1
        except requests.exceptions.HTTPError as e:
            detail = ""
            try:
                detail = e.response.text[:200]
            except Exception:
                pass
            print(f"  [ERROR] '{name}': {e} {detail}")
            errors += 1

    print(f"\n[DONE] Created={created}, Updated={updated}, Skipped={skipped}, Errors={errors}")
    return created, updated, skipped


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Sync 53AIHub Mock Gateway tools to xAgent Custom API tools"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be done without making changes",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip tools that already exist in xAgent instead of updating them",
    )
    args = parser.parse_args()

    aihub_url = get_env_or_default("AIHUB_BASE_URL", DEFAULT_AIHUB_URL).rstrip("/") + "/"
    aihub_token = get_env_required("AIHUB_TOKEN")
    xagent_url = get_env_or_default("XAGENT_BASE_URL", DEFAULT_XAGENT_URL).rstrip("/") + "/"

    # Auth: prefer token, fall back to username/password
    xagent_token = os.environ.get("XAGENT_TOKEN", "").strip()
    if not xagent_token:
        xagent_username = get_env_required("XAGENT_USERNAME")
        xagent_password = get_env_required("XAGENT_PASSWORD")
        xagent_token = xagent_login(xagent_url, xagent_username, xagent_password)

    print(f"[INFO] AI Hub URL: {aihub_url}")
    print(f"[INFO] xAgent URL: {xagent_url}")
    print(f"[INFO] Dry run: {args.dry_run}")
    print()

    sync_tools(
        aihub_url=aihub_url,
        aihub_token=aihub_token,
        xagent_url=xagent_url,
        xagent_token=xagent_token,
        dry_run=args.dry_run,
        skip_existing=args.skip_existing,
    )


if __name__ == "__main__":
    main()
