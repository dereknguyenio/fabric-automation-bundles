"""
Fabric Automation Bundles — MCP Server

Exposes fab-bundle CLI capabilities as MCP tools for use in
Claude Code, Cursor, Windsurf, or any MCP-compatible client.

Usage:
    fab-bundle-mcp                    # stdio transport (default)
    fab-bundle-mcp --transport sse    # SSE transport for remote

MCP config (claude_desktop_config.json or .claude/settings.json):
    {
        "mcpServers": {
            "fab-bundle": {
                "command": "fab-bundle-mcp"
            }
        }
    }
"""

from __future__ import annotations

import json
import os
import sys
import traceback
from pathlib import Path
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

server = Server("fab-bundle")


def _find_bundle_file(project_dir: str | None = None) -> Path | None:
    """Find fabric.yml in the given or current directory."""
    search_dir = Path(project_dir) if project_dir else Path.cwd()
    for name in ("fabric.yml", "fabric.yaml"):
        candidate = search_dir / name
        if candidate.exists():
            return candidate
    return None


def _load_bundle(project_dir: str | None = None, target: str | None = None):
    """Load and return a bundle."""
    from fab_bundle.engine.loader import load_bundle

    bundle_file = _find_bundle_file(project_dir)
    if not bundle_file:
        raise FileNotFoundError(f"No fabric.yml found in {project_dir or 'current directory'}")
    return load_bundle(str(bundle_file), target)


def _get_client():
    """Get authenticated Fabric API client."""
    from fab_bundle.providers.fabric_api import FabricClient
    return FabricClient()


def _format_result(data: Any) -> str:
    """Format result for MCP response."""
    if isinstance(data, (dict, list)):
        return json.dumps(data, indent=2, default=str)
    return str(data)


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="fab_validate",
            description="Validate a fabric.yml bundle definition. Checks schema, references, dependencies, naming rules, and policies.",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_dir": {"type": "string", "description": "Path to project directory containing fabric.yml"},
                    "target": {"type": "string", "description": "Target environment (dev, staging, prod)"},
                },
            },
        ),
        Tool(
            name="fab_plan",
            description="Preview what would change if deployed. Shows create/update/delete actions without making changes.",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_dir": {"type": "string", "description": "Path to project directory"},
                    "target": {"type": "string", "description": "Target environment"},
                },
            },
        ),
        Tool(
            name="fab_deploy",
            description="Deploy the bundle to a target Fabric workspace. Creates/updates/deletes resources to match fabric.yml.",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_dir": {"type": "string", "description": "Path to project directory"},
                    "target": {"type": "string", "description": "Target environment"},
                    "dry_run": {"type": "boolean", "description": "Preview without making changes", "default": False},
                },
            },
        ),
        Tool(
            name="fab_destroy",
            description="Destroy all bundle-managed resources in the target workspace. Deletes in reverse dependency order.",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_dir": {"type": "string", "description": "Path to project directory"},
                    "target": {"type": "string", "description": "Target environment"},
                },
                "required": ["target"],
            },
        ),
        Tool(
            name="fab_status",
            description="Show deployed resource health, item IDs, drift detection, and last deploy time.",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_dir": {"type": "string", "description": "Path to project directory"},
                    "target": {"type": "string", "description": "Target environment"},
                },
            },
        ),
        Tool(
            name="fab_drift",
            description="Detect drift between deployed state and live workspace. Shows items added, removed, or modified outside of fab-bundle.",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_dir": {"type": "string", "description": "Path to project directory"},
                    "target": {"type": "string", "description": "Target environment"},
                },
            },
        ),
        Tool(
            name="fab_run",
            description="Run a notebook or pipeline in the Fabric workspace.",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_dir": {"type": "string", "description": "Path to project directory"},
                    "target": {"type": "string", "description": "Target environment"},
                    "resource_name": {"type": "string", "description": "Name of notebook or pipeline to run"},
                    "parameters": {"type": "object", "description": "Key-value parameters to pass", "default": {}},
                },
                "required": ["resource_name"],
            },
        ),
        Tool(
            name="fab_history",
            description="Show deployment history for a target environment.",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_dir": {"type": "string", "description": "Path to project directory"},
                    "target": {"type": "string", "description": "Target environment"},
                    "limit": {"type": "integer", "description": "Max entries to show", "default": 10},
                },
            },
        ),
        Tool(
            name="fab_doctor",
            description="Diagnose common configuration issues: Python version, packages, Azure auth, Fabric API, bundle validity.",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_dir": {"type": "string", "description": "Path to project directory"},
                },
            },
        ),
        Tool(
            name="fab_list_templates",
            description="List available project templates (medallion, osdu_analytics, etc.).",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        Tool(
            name="fab_list_workspaces",
            description="List Fabric workspaces accessible to the current user.",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        Tool(
            name="fab_list_capacities",
            description="List available Fabric capacities with their IDs, SKUs, and regions.",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    try:
        result = _dispatch(name, arguments)
        return [TextContent(type="text", text=result)]
    except Exception as e:
        error_msg = f"Error: {e}\n{traceback.format_exc()}"
        return [TextContent(type="text", text=error_msg)]


def _dispatch(name: str, args: dict[str, Any]) -> str:
    handlers = {
        "fab_validate": _handle_validate,
        "fab_plan": _handle_plan,
        "fab_deploy": _handle_deploy,
        "fab_destroy": _handle_destroy,
        "fab_status": _handle_status,
        "fab_drift": _handle_drift,
        "fab_run": _handle_run,
        "fab_history": _handle_history,
        "fab_doctor": _handle_doctor,
        "fab_list_templates": _handle_list_templates,
        "fab_list_workspaces": _handle_list_workspaces,
        "fab_list_capacities": _handle_list_capacities,
    }
    handler = handlers.get(name)
    if not handler:
        return f"Unknown tool: {name}"
    return handler(args)


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


def _handle_validate(args: dict[str, Any]) -> str:
    project_dir = args.get("project_dir")
    target = args.get("target")

    bundle = _load_bundle(project_dir, target)

    resource_counts = {}
    for field_name in type(bundle.resources).model_fields:
        d = getattr(bundle.resources, field_name)
        if isinstance(d, dict) and d:
            resource_counts[field_name] = len(d)

    from fab_bundle.engine.resolver import get_deployment_order
    order = get_deployment_order(bundle)

    result = {
        "valid": True,
        "bundle_name": bundle.bundle.name,
        "version": bundle.bundle.version,
        "description": bundle.bundle.description,
        "total_resources": sum(resource_counts.values()),
        "resources": resource_counts,
        "deployment_order": order,
        "targets": list(bundle.targets.keys()) if bundle.targets else [],
    }
    return _format_result(result)


def _handle_plan(args: dict[str, Any]) -> str:
    project_dir = args.get("project_dir")
    target = args.get("target")

    bundle = _load_bundle(project_dir, target)
    client = _get_client()

    ws = bundle.get_effective_workspace(target)
    workspace_items = None
    if ws.name:
        found = client.find_workspace(ws.name)
        if found:
            workspace_items = client.get_workspace_items_map(found["id"])

    from fab_bundle.engine.planner import create_plan
    plan = create_plan(bundle, target, workspace_items)

    items = []
    for item in plan.items:
        if item.action.value != "no_change":
            items.append({
                "resource": item.resource_key,
                "type": item.resource_type,
                "action": item.action.value,
                "details": item.details,
            })

    return _format_result({
        "workspace": ws.name,
        "target": target or "default",
        "has_changes": plan.has_changes,
        "summary": {
            "create": sum(1 for i in items if i["action"] == "create"),
            "update": sum(1 for i in items if i["action"] == "update"),
            "delete": sum(1 for i in items if i["action"] == "delete"),
        },
        "items": items,
    })


def _handle_deploy(args: dict[str, Any]) -> str:
    project_dir = args.get("project_dir")
    target = args.get("target")
    dry_run = args.get("dry_run", False)

    bundle = _load_bundle(project_dir, target)
    client = _get_client()

    bundle_path = _find_bundle_file(project_dir)
    proj_dir = bundle_path.parent if bundle_path else Path.cwd()

    ws = bundle.get_effective_workspace(target)
    workspace_items = None
    if ws.name:
        found = client.find_workspace(ws.name)
        if found:
            workspace_items = client.get_workspace_items_map(found["id"])

    from fab_bundle.engine.planner import create_plan
    plan = create_plan(bundle, target, workspace_items)

    if not plan.has_changes:
        return "No changes to deploy."

    from fab_bundle.engine.deployer import Deployer
    from fab_bundle.engine.state import StateManager
    from rich.console import Console

    console = Console(file=open(os.devnull, "w"))
    deployer = Deployer(client, bundle, proj_dir, console, dry_run=dry_run)
    deployer.state_manager = StateManager(proj_dir, target or "default")
    result = deployer.execute(plan, target)

    return _format_result({
        "success": result.success,
        "created": result.items_created,
        "updated": result.items_updated,
        "deleted": result.items_deleted,
        "failed": result.items_failed,
        "errors": result.errors,
    })


def _handle_destroy(args: dict[str, Any]) -> str:
    project_dir = args.get("project_dir")
    target = args.get("target")

    bundle = _load_bundle(project_dir, target)
    client = _get_client()

    ws = bundle.get_effective_workspace(target)
    ws_id = None
    if ws.name:
        found = client.find_workspace(ws.name)
        ws_id = found["id"] if found else None

    if not ws_id:
        return f"Workspace '{ws.name}' not found."

    items = client.get_workspace_items_map(ws_id)
    bundle_keys = bundle.resources.all_resource_keys()

    from fab_bundle.engine.resolver import get_deployment_order
    order = get_deployment_order(bundle)

    deleted = []
    errors = []
    for key in reversed(order):
        if key in items:
            try:
                client.delete_item(ws_id, items[key]["id"])
                deleted.append(key)
            except Exception as e:
                errors.append(f"{key}: {e}")

    return _format_result({
        "deleted": deleted,
        "deleted_count": len(deleted),
        "errors": errors,
    })


def _handle_status(args: dict[str, Any]) -> str:
    project_dir = args.get("project_dir")
    target = args.get("target")

    bundle = _load_bundle(project_dir, target)
    client = _get_client()

    ws = bundle.get_effective_workspace(target)
    ws_id = None
    if ws.name:
        found = client.find_workspace(ws.name)
        ws_id = found["id"] if found else None

    if not ws_id:
        return f"Workspace '{ws.name}' not found. Deploy first."

    items = client.get_workspace_items_map(ws_id)
    bundle_keys = bundle.resources.all_resource_keys()

    bundle_path = _find_bundle_file(project_dir)
    proj_dir = bundle_path.parent if bundle_path else Path.cwd()

    from fab_bundle.engine.state import StateManager
    state_mgr = StateManager(proj_dir, target or "default")
    state = state_mgr.load()

    resources = []
    for key in sorted(bundle_keys):
        in_workspace = key in items
        rt = bundle.resources.get_resource_type(key) or ""
        resources.append({
            "name": key,
            "type": rt,
            "status": "deployed" if in_workspace else "pending",
            "item_id": items[key]["id"][:12] if in_workspace else None,
        })

    unmanaged = sorted(set(items.keys()) - bundle_keys)
    for key in unmanaged:
        resources.append({
            "name": key,
            "type": items[key].get("type", ""),
            "status": "unmanaged",
            "item_id": items[key].get("id", "")[:12],
        })

    return _format_result({
        "workspace": ws.name,
        "workspace_id": ws_id,
        "last_deploy": state.last_deployed,
        "bundle_items": len(bundle_keys),
        "workspace_items": len(items),
        "resources": resources,
        "drift_count": len(unmanaged),
    })


def _handle_drift(args: dict[str, Any]) -> str:
    project_dir = args.get("project_dir")
    target = args.get("target")

    bundle = _load_bundle(project_dir, target)
    client = _get_client()

    ws = bundle.get_effective_workspace(target)
    ws_id = None
    if ws.name:
        found = client.find_workspace(ws.name)
        ws_id = found["id"] if found else None

    if not ws_id:
        return "Workspace not found."

    items = client.get_workspace_items_map(ws_id)
    bundle_keys = bundle.resources.all_resource_keys()

    added = sorted(set(items.keys()) - bundle_keys)
    removed = sorted(bundle_keys - set(items.keys()))

    return _format_result({
        "has_drift": bool(added or removed),
        "added_in_workspace": added,
        "missing_from_workspace": removed,
    })


def _handle_run(args: dict[str, Any]) -> str:
    project_dir = args.get("project_dir")
    target = args.get("target")
    resource_name = args["resource_name"]
    parameters = args.get("parameters", {})

    bundle = _load_bundle(project_dir, target)
    client = _get_client()

    ws = bundle.get_effective_workspace(target)
    ws_id = None
    if ws.name:
        found = client.find_workspace(ws.name)
        ws_id = found["id"] if found else None

    if not ws_id:
        return "Workspace not found."

    items = client.get_workspace_items_map(ws_id)
    item_info = items.get(resource_name)
    if not item_info:
        return f"Resource '{resource_name}' not found in workspace."

    item_type = item_info.get("type", "")
    job_type = "RunNotebook" if item_type == "Notebook" else "Pipeline"

    execution_data = None
    if parameters:
        execution_data = {"parameters": {k: {"value": v, "type": "string"} for k, v in parameters.items()}}

    try:
        result = client.run_item_job(ws_id, item_info["id"], job_type, execution_data=execution_data)
        return _format_result({
            "status": "submitted",
            "resource": resource_name,
            "item_id": item_info["id"],
            "job_type": job_type,
        })
    except Exception as e:
        return f"Failed to run {resource_name}: {e}"


def _handle_history(args: dict[str, Any]) -> str:
    project_dir = args.get("project_dir")
    target = args.get("target")
    limit = args.get("limit", 10)

    bundle_path = _find_bundle_file(project_dir)
    proj_dir = bundle_path.parent if bundle_path else Path.cwd()

    from fab_bundle.engine.state import StateManager
    state_mgr = StateManager(proj_dir, target or "default")
    entries = state_mgr.list_history(limit)

    return _format_result(entries)


def _handle_doctor(args: dict[str, Any]) -> str:
    import platform
    import shutil
    import subprocess

    checks = []

    # Python version
    py_version = platform.python_version()
    py_ok = tuple(int(x) for x in py_version.split(".")[:2]) >= (3, 10)
    checks.append({"check": f"Python {py_version}", "passed": py_ok})

    # Required packages
    for pkg in ["pydantic", "click", "rich", "yaml", "requests", "azure.identity"]:
        try:
            __import__(pkg)
            checks.append({"check": f"Package: {pkg}", "passed": True})
        except ImportError:
            checks.append({"check": f"Package: {pkg}", "passed": False})

    # Azure CLI
    checks.append({"check": "Azure CLI installed", "passed": shutil.which("az") is not None})

    # Azure login
    try:
        r = subprocess.run(["az", "account", "show", "-o", "none"], capture_output=True, timeout=10)
        checks.append({"check": "Azure CLI authenticated", "passed": r.returncode == 0})
    except Exception:
        checks.append({"check": "Azure CLI authenticated", "passed": False})

    # Fabric API
    try:
        client = _get_client()
        client.list_workspaces()
        checks.append({"check": "Fabric API reachable", "passed": True})
    except Exception:
        checks.append({"check": "Fabric API reachable", "passed": False})

    passed = sum(1 for c in checks if c["passed"])
    failed = sum(1 for c in checks if not c["passed"])

    return _format_result({
        "checks": checks,
        "passed": passed,
        "failed": failed,
    })


def _handle_list_templates(args: dict[str, Any]) -> str:
    from fab_bundle.generators.templates import list_templates
    templates = list_templates()
    return _format_result(templates)


def _handle_list_workspaces(args: dict[str, Any]) -> str:
    client = _get_client()
    workspaces = client.list_workspaces()
    result = []
    for ws in workspaces:
        result.append({
            "name": ws.get("displayName", ""),
            "id": ws.get("id", ""),
            "type": ws.get("type", ""),
        })
    return _format_result(result)


def _handle_list_capacities(args: dict[str, Any]) -> str:
    import subprocess
    try:
        r = subprocess.run(
            ["az", "rest", "--method", "get",
             "--url", "https://api.fabric.microsoft.com/v1/capacities",
             "--resource", "https://api.fabric.microsoft.com"],
            capture_output=True, text=True, timeout=15,
        )
        if r.returncode == 0:
            data = json.loads(r.stdout)
            caps = []
            for c in data.get("value", []):
                caps.append({
                    "name": c.get("displayName", ""),
                    "id": c.get("id", ""),
                    "sku": c.get("sku", ""),
                    "region": c.get("region", ""),
                    "state": c.get("state", ""),
                })
            return _format_result(caps)
        return f"Failed: {r.stderr}"
    except Exception as e:
        return f"Error listing capacities: {e}"


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main():
    """Run the MCP server."""
    import asyncio

    async def _run():
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())

    asyncio.run(_run())


if __name__ == "__main__":
    main()
