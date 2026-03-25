"""
Reverse generator — generates a fabric.yml bundle definition from an
existing Fabric workspace.

This is 'fab bundle generate' — the on-ramp for existing projects.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml
from rich.console import Console

from fab_bundle.providers.fabric_api import FabricClient, ITEM_TYPE_MAP


# Reverse map: Fabric item type -> our resource type key
REVERSE_TYPE_MAP = {v: k for k, v in ITEM_TYPE_MAP.items()}

# Additional Fabric types we recognize
REVERSE_TYPE_MAP.update({
    "Lakehouse": "lakehouses",
    "Notebook": "notebooks",
    "DataPipeline": "pipelines",
    "Warehouse": "warehouses",
    "SemanticModel": "semantic_models",
    "Report": "reports",
    "SparkEnvironment": "environments",
    "Eventhouse": "eventhouses",
    "Eventstream": "eventstreams",
    "MLModel": "ml_models",
    "MLExperiment": "ml_experiments",
    "KQLDatabase": "eventhouses",
})


def _sanitize_key(name: str) -> str:
    """Convert a display name to a valid YAML key."""
    return name.lower().replace(" ", "-").replace("_", "-")


def generate_bundle_from_workspace(
    client: FabricClient,
    workspace_name: str | None = None,
    workspace_id: str | None = None,
    output_dir: Path | None = None,
    console: Console | None = None,
) -> dict[str, Any]:
    """
    Generate a fabric.yml from an existing workspace.

    Args:
        client: Authenticated Fabric API client.
        workspace_name: Name of the workspace to scan.
        workspace_id: ID of the workspace (takes precedence over name).
        output_dir: Directory to write fabric.yml and exported definitions.
        console: Rich console for output.

    Returns:
        Dict representation of the generated fabric.yml.
    """
    console = console or Console()
    output_dir = output_dir or Path.cwd()

    # Resolve workspace
    if workspace_id:
        ws = client.get_workspace(workspace_id)
    elif workspace_name:
        ws = client.find_workspace(workspace_name)
        if not ws:
            raise ValueError(f"Workspace '{workspace_name}' not found")
    else:
        raise ValueError("Either workspace_name or workspace_id must be provided")

    ws_id = ws["id"]
    ws_name = ws.get("displayName", workspace_name or "unknown")

    console.print(f"Scanning workspace: [bold]{ws_name}[/bold] ({ws_id})")

    # List all items
    items = client.list_items(ws_id)
    console.print(f"  Found {len(items)} items")

    # Build bundle structure
    bundle_data: dict[str, Any] = {
        "bundle": {
            "name": _sanitize_key(ws_name),
            "version": "0.1.0",
            "description": f"Generated from workspace: {ws_name}",
        },
        "workspace": {
            "name": ws_name,
        },
        "resources": {},
        "targets": {
            "dev": {
                "default": True,
                "workspace": {"name": f"{ws_name}-dev"},
            },
            "staging": {
                "workspace": {"name": f"{ws_name}-staging"},
            },
            "prod": {
                "workspace": {"name": ws_name},
            },
        },
    }

    # Group items by type
    items_by_type: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        item_type = item.get("type", "Unknown")
        resource_type = REVERSE_TYPE_MAP.get(item_type)
        if resource_type:
            items_by_type.setdefault(resource_type, []).append(item)
        else:
            console.print(f"  [dim]Skipping unsupported item type: {item_type} ({item.get('displayName')})[/dim]")

    # Process each resource type
    for resource_type, type_items in sorted(items_by_type.items()):
        console.print(f"  Processing {resource_type}: {len(type_items)} items")
        resources: dict[str, Any] = {}

        for item in type_items:
            display_name = item.get("displayName", "unknown")
            key = _sanitize_key(display_name)
            item_id = item.get("id")

            resource_def: dict[str, Any] = {}

            if item.get("description"):
                resource_def["description"] = item["description"]

            # Type-specific handling
            if resource_type == "notebooks":
                # Export notebook definition
                export_path = f"notebooks/{display_name}.py"
                resource_def["path"] = f"./{export_path}"

                try:
                    defn = client.get_item_definition(ws_id, item_id)
                    if defn and "definition" in defn:
                        _export_definition(defn["definition"], output_dir / "notebooks", display_name)
                        console.print(f"    Exported: {display_name}")
                except Exception as e:
                    console.print(f"    [yellow]Could not export {display_name}: {e}[/yellow]")
                    resource_def["path"] = f"./notebooks/{display_name}.py  # TODO: export manually"

            elif resource_type == "pipelines":
                export_path = f"pipelines/{display_name}.json"
                resource_def["path"] = f"./{export_path}"

                try:
                    defn = client.get_item_definition(ws_id, item_id)
                    if defn and "definition" in defn:
                        _export_definition(defn["definition"], output_dir / "pipelines", display_name)
                except Exception as e:
                    console.print(f"    [yellow]Could not export {display_name}: {e}[/yellow]")

            elif resource_type == "semantic_models":
                resource_def["path"] = f"./semantic_models/{display_name}/"

            elif resource_type == "reports":
                resource_def["path"] = f"./reports/{display_name}/"

            elif resource_type == "lakehouses":
                pass  # No path needed

            elif resource_type == "warehouses":
                resource_def["sql_scripts"] = []

            elif resource_type == "environments":
                resource_def["runtime"] = "1.3"
                resource_def["libraries"] = []

            resources[key] = resource_def

        if resources:
            bundle_data["resources"][resource_type] = resources

    # Write fabric.yml
    output_file = output_dir / "fabric.yml"
    with open(output_file, "w") as f:
        yaml.dump(bundle_data, f, default_flow_style=False, sort_keys=False, width=120)

    console.print()
    console.print(f"[bold green]Generated:[/bold green] {output_file}")
    console.print()
    console.print("Next steps:")
    console.print("  1. Review and edit fabric.yml")
    console.print("  2. Export item definitions: fab bundle export")
    console.print("  3. Validate: fab bundle validate")
    console.print("  4. Deploy to a target: fab bundle deploy -t dev")

    return bundle_data


def _export_definition(definition: dict[str, Any], output_dir: Path, name: str) -> None:
    """Export an item definition's parts to disk."""
    import base64

    output_dir.mkdir(parents=True, exist_ok=True)

    parts = definition.get("parts", [])
    for part in parts:
        path = part.get("path", "")
        payload = part.get("payload", "")
        payload_type = part.get("payloadType", "")

        if payload_type == "InlineBase64":
            content = base64.b64decode(payload)
            out_path = output_dir / path
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(content)
