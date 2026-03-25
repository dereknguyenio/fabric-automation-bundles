"""
Fabric Automation Bundles CLI — 'fab-bundle' commands.

Declarative project definitions for Microsoft Fabric:
  fab-bundle init       — Create a new project from a template
  fab-bundle validate   — Validate the bundle definition
  fab-bundle plan       — Preview what would change (dry-run)
  fab-bundle deploy     — Deploy to a target workspace
  fab-bundle destroy    — Tear down a target workspace
  fab-bundle generate   — Generate fabric.yml from an existing workspace
  fab-bundle run        — Run a specific resource (pipeline/notebook)
  fab-bundle list       — List available templates
  fab-bundle bind       — Bind an existing workspace item to bundle management

Future: integrate as 'fab bundle' subcommand in the Fabric CLI.
"""

from __future__ import annotations

import sys
from pathlib import Path

import click
from rich.console import Console

console = Console()


@click.group("bundle")
@click.version_option(version="0.3.0", prog_name="fabric-automation-bundles")
def cli():
    """Fabric Automation Bundles — declarative project definitions for Microsoft Fabric."""
    pass


# ---------------------------------------------------------------------------
# fab bundle init
# ---------------------------------------------------------------------------


@cli.command()
@click.option("--template", "-t", default="medallion", help="Template name or path")
@click.option("--output", "-o", default=".", help="Output directory")
@click.option("--name", "-n", prompt="Project name", help="Bundle project name")
@click.option("--var", multiple=True, help="Template variables (KEY=VALUE)")
def init(template: str, output: str, name: str, var: tuple[str, ...]):
    """Create a new bundle project from a template."""
    from fab_bundle.generators.templates import init_from_template, list_templates

    variables = {"project_name": name}
    for v in var:
        if "=" in v:
            key, value = v.split("=", 1)
            variables[key] = value

    try:
        output_dir = Path(output) / name if output == "." else Path(output)
        init_from_template(template, output_dir, variables, console)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


# ---------------------------------------------------------------------------
# fab bundle validate
# ---------------------------------------------------------------------------


@cli.command()
@click.option("--file", "-f", "bundle_file", default=None, help="Path to fabric.yml")
@click.option("--target", "-t", default=None, help="Target to validate against")
def validate(bundle_file: str | None, target: str | None):
    """Validate the bundle definition."""
    from fab_bundle.engine.loader import BundleLoadError, load_bundle
    from fab_bundle.engine.resolver import DependencyResolutionError, get_deployment_order

    try:
        bundle = load_bundle(bundle_file, target)
    except BundleLoadError as e:
        console.print(f"[red]Validation failed:[/red] {e}")
        if e.errors:
            for err in e.errors:
                console.print(f"  {err}")
        sys.exit(1)

    # Validate dependency graph
    try:
        order = get_deployment_order(bundle)
    except DependencyResolutionError as e:
        console.print(f"[red]Dependency error:[/red] {e}")
        sys.exit(1)

    # Count resources
    total = len(order)
    types_summary = {}
    for node in order:
        types_summary[node.resource_type] = types_summary.get(node.resource_type, 0) + 1

    console.print("[bold green]Bundle is valid.[/bold green]")
    console.print()
    console.print(f"  Bundle:    {bundle.bundle.name} v{bundle.bundle.version}")
    if bundle.bundle.description:
        console.print(f"  Desc:      {bundle.bundle.description}")
    console.print(f"  Resources: {total}")
    for rtype, count in sorted(types_summary.items()):
        console.print(f"    {rtype}: {count}")
    console.print(f"  Targets:   {', '.join(bundle.targets.keys()) or '(none)'}")

    if target:
        ws = bundle.get_effective_workspace(target)
        console.print(f"  Workspace: {ws.name or ws.workspace_id or '(not set)'}")
        variables = bundle.resolve_variables(target)
        if variables:
            console.print(f"  Variables: {len(variables)}")

    console.print()
    console.print("  Deployment order:")
    for i, node in enumerate(order, 1):
        deps = f" (depends: {', '.join(node.depends_on)})" if node.depends_on else ""
        console.print(f"    {i}. [{node.resource_type}] {node.key}{deps}")


# ---------------------------------------------------------------------------
# fab bundle plan
# ---------------------------------------------------------------------------


@cli.command()
@click.option("--file", "-f", "bundle_file", default=None, help="Path to fabric.yml")
@click.option("--target", "-t", default=None, help="Target environment")
@click.option("--auto-delete/--no-auto-delete", default=False, help="Plan deletion of unmanaged items")
def plan(bundle_file: str | None, target: str | None, auto_delete: bool):
    """Preview what changes would be made (dry-run)."""
    from fab_bundle.engine.loader import BundleLoadError, load_bundle
    from fab_bundle.engine.planner import create_plan

    try:
        bundle = load_bundle(bundle_file, target)
    except BundleLoadError as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)

    ws_config = bundle.get_effective_workspace(target)

    # Try to get current workspace state
    workspace_items = None
    if ws_config.workspace_id or ws_config.name:
        try:
            from fab_bundle.providers.fabric_api import FabricClient
            client = FabricClient()
            if ws_config.workspace_id:
                workspace_items = client.get_workspace_items_map(ws_config.workspace_id)
            elif ws_config.name:
                ws = client.find_workspace(ws_config.name)
                if ws:
                    workspace_items = client.get_workspace_items_map(ws["id"])
        except Exception as e:
            console.print(f"[yellow]Warning:[/yellow] Could not connect to workspace: {e}")
            console.print("  Planning against empty workspace (all items will be CREATE)")
            console.print()

    deployment_plan = create_plan(bundle, target, workspace_items, auto_delete)
    deployment_plan.display(console)


# ---------------------------------------------------------------------------
# fab bundle deploy
# ---------------------------------------------------------------------------


@cli.command()
@click.option("--file", "-f", "bundle_file", default=None, help="Path to fabric.yml")
@click.option("--target", "-t", default=None, help="Target environment")
@click.option("--dry-run", is_flag=True, default=False, help="Preview without deploying")
@click.option("--auto-approve", "-y", is_flag=True, default=False, help="Skip confirmation")
@click.option("--auto-delete/--no-auto-delete", default=False, help="Delete unmanaged items")
def deploy(bundle_file: str | None, target: str | None, dry_run: bool, auto_approve: bool, auto_delete: bool):
    """Deploy the bundle to a target workspace."""
    from fab_bundle.engine.deployer import Deployer
    from fab_bundle.engine.loader import BundleLoadError, load_bundle
    from fab_bundle.engine.planner import create_plan
    from fab_bundle.providers.fabric_api import FabricClient

    try:
        bundle = load_bundle(bundle_file, target)
    except BundleLoadError as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)

    bundle_path = Path(bundle_file) if bundle_file else Path.cwd()
    project_dir = bundle_path.parent if bundle_path.is_file() else bundle_path

    # Set up state manager
    from fab_bundle.engine.state import StateManager
    target_label = target or "default"
    state_mgr = StateManager(project_dir, target_label)

    # Connect to Fabric
    try:
        client = FabricClient()
    except Exception as e:
        console.print(f"[red]Authentication error:[/red] {e}")
        console.print("  Run 'az login' or set service principal environment variables.")
        sys.exit(1)

    # Get workspace state
    ws_config = bundle.get_effective_workspace(target)
    workspace_items = None
    try:
        if ws_config.workspace_id:
            workspace_items = client.get_workspace_items_map(ws_config.workspace_id)
        elif ws_config.name:
            ws = client.find_workspace(ws_config.name)
            if ws:
                workspace_items = client.get_workspace_items_map(ws["id"])
    except Exception:
        pass

    # Create plan
    deployment_plan = create_plan(bundle, target, workspace_items, auto_delete)
    deployment_plan.display(console)

    if not deployment_plan.has_changes:
        return

    # Confirm
    if not dry_run and not auto_approve:
        if not click.confirm("Do you want to apply these changes?"):
            console.print("[dim]Cancelled.[/dim]")
            return

    # Deploy
    deployer = Deployer(client, bundle, project_dir, console, dry_run=dry_run)
    deployer.state_manager = state_mgr
    result = deployer.execute(deployment_plan, target)

    if not result.success:
        sys.exit(1)


# ---------------------------------------------------------------------------
# fab bundle destroy
# ---------------------------------------------------------------------------


@cli.command()
@click.option("--file", "-f", "bundle_file", default=None, help="Path to fabric.yml")
@click.option("--target", "-t", default=None, help="Target environment")
@click.option("--auto-approve", "-y", is_flag=True, default=False, help="Skip confirmation")
@click.option("--delete-workspace", is_flag=True, default=False, help="Also delete the workspace itself")
def destroy(bundle_file: str | None, target: str | None, auto_approve: bool, delete_workspace: bool):
    """Destroy all bundle-managed resources in the target workspace."""
    from fab_bundle.engine.loader import BundleLoadError, load_bundle
    from fab_bundle.engine.resolver import get_deployment_order
    from fab_bundle.providers.fabric_api import FabricClient

    try:
        bundle = load_bundle(bundle_file, target)
    except BundleLoadError as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)

    ws = bundle.get_effective_workspace(target)
    console.print(f"[bold red]WARNING:[/bold red] This will delete all bundle-managed resources in:")
    console.print(f"  Workspace: {ws.name or ws.workspace_id}")
    console.print(f"  Target:    {target or '(default)'}")
    console.print()

    # Show what would be destroyed (reverse deployment order)
    order = get_deployment_order(bundle)
    reversed_order = list(reversed(order))
    console.print("  Resources to destroy (reverse dependency order):")
    for i, node in enumerate(reversed_order, 1):
        console.print(f"    {i}. [red]-[/red] [{node.resource_type}] {node.key}")
    console.print()

    if not auto_approve:
        confirm_text = click.prompt(
            f"Type the bundle name '{bundle.bundle.name}' to confirm destruction",
            type=str,
        )
        if confirm_text != bundle.bundle.name:
            console.print("[dim]Cancelled — name did not match.[/dim]")
            return

    # Connect and destroy
    try:
        client = FabricClient()
    except Exception as e:
        console.print(f"[red]Authentication error:[/red] {e}")
        sys.exit(1)

    # Resolve workspace ID
    workspace_id = ws.workspace_id
    if not workspace_id and ws.name:
        found = client.find_workspace(ws.name)
        if found:
            workspace_id = found["id"]

    if not workspace_id:
        console.print(f"[yellow]Workspace not found — nothing to destroy.[/yellow]")
        return

    # Get current items
    existing = client.get_workspace_items_map(workspace_id)

    destroyed = 0
    failed = 0
    for node in reversed_order:
        if node.key in existing:
            item_id = existing[node.key].get("id")
            if item_id:
                try:
                    client.delete_item(workspace_id, item_id)
                    console.print(f"  [red]-[/red] Deleted: {node.key}")
                    destroyed += 1
                except Exception as e:
                    console.print(f"  [red]ERROR[/red] {node.key}: {e}")
                    failed += 1
        else:
            console.print(f"  [dim]=[/dim] Not found: {node.key}")

    console.print()
    if failed:
        console.print(f"[bold red]Destroy completed with errors.[/bold red] Deleted: {destroyed}, Failed: {failed}")
    else:
        console.print(f"[bold green]Destroy complete.[/bold green] Deleted: {destroyed} resources.")

    # Optionally delete the workspace
    if delete_workspace and failed == 0:
        if not auto_approve:
            if not click.confirm(f"Also delete workspace '{ws.name}'?"):
                return
        try:
            client.delete_workspace(workspace_id)
            console.print(f"  [red]Workspace deleted: {ws.name}[/red]")
        except Exception as e:
            console.print(f"  [red]Failed to delete workspace:[/red] {e}")

    # Clean up state
    from fab_bundle.engine.state import StateManager
    state_mgr = StateManager(
        Path(bundle_file).parent if bundle_file else Path.cwd(),
        target or "default",
    )
    state = state_mgr.load()
    for node in reversed_order:
        if node.key in existing:
            state_mgr.remove_resource(node.key)


# ---------------------------------------------------------------------------
# fab bundle generate
# ---------------------------------------------------------------------------


@cli.command()
@click.option("--workspace", "-w", required=True, help="Workspace name or ID to scan")
@click.option("--output", "-o", default=".", help="Output directory")
def generate(workspace: str, output: str):
    """Generate a fabric.yml from an existing workspace."""
    from fab_bundle.generators.reverse import generate_bundle_from_workspace
    from fab_bundle.providers.fabric_api import FabricClient

    try:
        client = FabricClient()
    except Exception as e:
        console.print(f"[red]Authentication error:[/red] {e}")
        sys.exit(1)

    output_dir = Path(output)

    try:
        # Determine if it's a GUID or a name
        is_guid = len(workspace) == 36 and workspace.count("-") == 4
        generate_bundle_from_workspace(
            client=client,
            workspace_id=workspace if is_guid else None,
            workspace_name=workspace if not is_guid else None,
            output_dir=output_dir,
            console=console,
        )
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


# ---------------------------------------------------------------------------
# fab bundle run
# ---------------------------------------------------------------------------


@cli.command()
@click.argument("resource_name")
@click.option("--file", "-f", "bundle_file", default=None, help="Path to fabric.yml")
@click.option("--target", "-t", default=None, help="Target environment")
def run(resource_name: str, bundle_file: str | None, target: str | None):
    """Run a specific resource (pipeline or notebook)."""
    from fab_bundle.engine.loader import BundleLoadError, load_bundle
    from fab_bundle.providers.fabric_api import FabricClient

    try:
        bundle = load_bundle(bundle_file, target)
    except BundleLoadError as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)

    resource_type = bundle.resources.get_resource_type(resource_name)
    if not resource_type:
        console.print(f"[red]Error:[/red] Resource '{resource_name}' not found in bundle")
        sys.exit(1)

    if resource_type not in ("notebooks", "pipelines"):
        console.print(f"[red]Error:[/red] Cannot run resource type '{resource_type}'. Only notebooks and pipelines are runnable.")
        sys.exit(1)

    # Connect to Fabric
    try:
        client = FabricClient()
    except Exception as e:
        console.print(f"[red]Authentication error:[/red] {e}")
        sys.exit(1)

    # Resolve workspace
    ws = bundle.get_effective_workspace(target)
    workspace_id = ws.workspace_id
    if not workspace_id and ws.name:
        found = client.find_workspace(ws.name)
        if found:
            workspace_id = found["id"]

    if not workspace_id:
        console.print(f"[red]Error:[/red] Workspace '{ws.name}' not found")
        sys.exit(1)

    # Find the item
    existing = client.get_workspace_items_map(workspace_id)
    if resource_name not in existing:
        console.print(f"[red]Error:[/red] '{resource_name}' not found in workspace. Deploy first with 'fab bundle deploy'.")
        sys.exit(1)

    item_id = existing[resource_name]["id"]
    item_type = existing[resource_name]["type"]

    console.print(f"Running [{resource_type[:-1]}]: [bold]{resource_name}[/bold]")
    console.print(f"  Workspace: {ws.name} ({workspace_id})")
    console.print(f"  Item ID:   {item_id}")
    console.print()

    # Trigger execution via Job Scheduler API
    try:
        job_type = "RunNotebook" if item_type == "Notebook" else "Pipeline"
        result = client.run_item_job(workspace_id, item_id, job_type)

        if result and "operation_url" in result:
            console.print("[dim]Job submitted. Waiting for completion...[/dim]")
            try:
                final = client._wait_for_operation(result["operation_url"], timeout=600)
                console.print("[bold green]Run complete.[/bold green]")
            except Exception as e:
                console.print(f"[yellow]Job submitted but could not track completion:[/yellow] {e}")
                console.print("  Check the Fabric portal for run status.")
        else:
            console.print("[bold green]Run triggered successfully.[/bold green]")

    except Exception as e:
        console.print(f"[red]Error triggering run:[/red] {e}")
        sys.exit(1)


# ---------------------------------------------------------------------------
# fab bundle list (templates)
# ---------------------------------------------------------------------------


@cli.command("list")
def list_cmd():
    """List available bundle templates."""
    from fab_bundle.generators.templates import list_templates

    templates = list_templates()
    if not templates:
        console.print("[dim]No templates found.[/dim]")
        console.print("  Templates should be placed in the fab_bundle/templates/ directory.")
        return

    console.print("[bold]Available templates:[/bold]")
    console.print()
    for tmpl in templates:
        name = tmpl.get("name", "unknown")
        desc = tmpl.get("description", "")
        console.print(f"  [bold]{name}[/bold]")
        if desc:
            console.print(f"    {desc}")
    console.print()
    console.print("Usage: fab bundle init --template <name> --name <project-name>")


# ---------------------------------------------------------------------------
# fab bundle bind
# ---------------------------------------------------------------------------


@cli.command()
@click.argument("resource_name")
@click.option("--workspace", "-w", required=True, help="Workspace name or ID")
@click.option("--file", "-f", "bundle_file", default=None, help="Path to fabric.yml")
def bind(resource_name: str, workspace: str, bundle_file: str | None):
    """Bind an existing workspace resource to bundle management."""
    from fab_bundle.engine.loader import BundleLoadError, load_bundle
    from fab_bundle.providers.fabric_api import FabricClient

    try:
        bundle = load_bundle(bundle_file)
    except BundleLoadError as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)

    # Check resource exists in bundle
    resource_type = bundle.resources.get_resource_type(resource_name)
    if not resource_type:
        console.print(f"[red]Error:[/red] Resource '{resource_name}' not found in fabric.yml")
        console.print("  Add the resource definition to fabric.yml first, then bind it.")
        sys.exit(1)

    # Connect to Fabric
    try:
        client = FabricClient()
    except Exception as e:
        console.print(f"[red]Authentication error:[/red] {e}")
        sys.exit(1)

    # Resolve workspace
    is_guid = len(workspace) == 36 and workspace.count("-") == 4
    if is_guid:
        workspace_id = workspace
    else:
        ws = client.find_workspace(workspace)
        if not ws:
            console.print(f"[red]Error:[/red] Workspace '{workspace}' not found")
            sys.exit(1)
        workspace_id = ws["id"]

    # Find the item in the workspace
    existing = client.get_workspace_items_map(workspace_id)
    if resource_name not in existing:
        console.print(f"[red]Error:[/red] '{resource_name}' not found in workspace")
        console.print(f"  Available items: {', '.join(sorted(existing.keys())[:10])}")
        sys.exit(1)

    item_info = existing[resource_name]
    console.print(f"[bold green]Bound:[/bold green] {resource_name}")
    console.print(f"  Type:      {item_info.get('type')}")
    console.print(f"  Item ID:   {item_info.get('id')}")
    console.print(f"  Workspace: {workspace}")
    console.print()
    console.print("  This resource will be managed by the bundle on the next deploy.")
    console.print("  Changes to fabric.yml will be applied to the existing item.")


# ---------------------------------------------------------------------------
# fab bundle drift
# ---------------------------------------------------------------------------


@cli.command()
@click.option("--file", "-f", "bundle_file", default=None, help="Path to fabric.yml")
@click.option("--target", "-t", default=None, help="Target environment")
def drift(bundle_file: str | None, target: str | None):
    """Detect drift between deployed state and live workspace."""
    from fab_bundle.engine.loader import BundleLoadError, load_bundle
    from fab_bundle.engine.state import StateManager
    from fab_bundle.providers.fabric_api import FabricClient

    try:
        bundle = load_bundle(bundle_file, target)
    except BundleLoadError as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)

    bundle_path = Path(bundle_file) if bundle_file else Path.cwd()
    project_dir = bundle_path.parent if bundle_path.is_file() else bundle_path

    state_mgr = StateManager(project_dir, target or "default")
    state = state_mgr.load()

    if not state.workspace_id:
        console.print("[yellow]No deployment state found.[/yellow] Run 'fab-bundle deploy' first.")
        return

    try:
        client = FabricClient()
    except Exception as e:
        console.print(f"[red]Authentication error:[/red] {e}")
        sys.exit(1)

    try:
        live_items = client.get_workspace_items_map(state.workspace_id)
    except Exception as e:
        console.print(f"[red]Error fetching workspace:[/red] {e}")
        sys.exit(1)

    drift_report = state_mgr.detect_drift(live_items)

    if not drift_report:
        console.print("[bold green]No drift detected.[/bold green] Workspace matches deployed state.")
        return

    console.print(f"[bold yellow]Drift detected:[/bold yellow] {len(drift_report)} item(s)")
    console.print()
    for key, drift_type in sorted(drift_report.items()):
        color = {"added": "green", "removed": "red", "modified": "yellow"}.get(drift_type, "white")
        symbol = {"added": "+", "removed": "-", "modified": "~"}.get(drift_type, "?")
        console.print(f"  [{color}]{symbol}[/{color}] {key}: {drift_type}")

    console.print()
    console.print("  Run 'fab-bundle deploy' to reconcile, or 'fab-bundle plan' to preview changes.")


# ---------------------------------------------------------------------------
# fab bundle export
# ---------------------------------------------------------------------------


@cli.command()
@click.option("--file", "-f", "bundle_file", default=None, help="Path to fabric.yml")
@click.option("--target", "-t", default=None, help="Target environment")
@click.option("--resource", "-r", "resource_name", default=None, help="Export a specific resource (default: all)")
@click.option("--output", "-o", default=".", help="Output directory")
def export(bundle_file: str | None, target: str | None, resource_name: str | None, output: str):
    """Export item definitions from deployed workspace to local files."""
    import base64
    from fab_bundle.engine.loader import BundleLoadError, load_bundle
    from fab_bundle.providers.fabric_api import FabricClient

    try:
        bundle = load_bundle(bundle_file, target)
    except BundleLoadError as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)

    try:
        client = FabricClient()
    except Exception as e:
        console.print(f"[red]Authentication error:[/red] {e}")
        sys.exit(1)

    # Resolve workspace
    ws = bundle.get_effective_workspace(target)
    workspace_id = ws.workspace_id
    if not workspace_id and ws.name:
        found = client.find_workspace(ws.name)
        if found:
            workspace_id = found["id"]

    if not workspace_id:
        console.print(f"[red]Error:[/red] Workspace not found")
        sys.exit(1)

    existing = client.get_workspace_items_map(workspace_id)
    output_dir = Path(output)
    exported = 0

    items_to_export = {}
    if resource_name:
        if resource_name not in existing:
            console.print(f"[red]Error:[/red] '{resource_name}' not found in workspace")
            sys.exit(1)
        items_to_export[resource_name] = existing[resource_name]
    else:
        items_to_export = existing

    console.print(f"Exporting from workspace: {ws.name or workspace_id}")
    console.print()

    for name, info in sorted(items_to_export.items()):
        item_id = info.get("id")
        item_type = info.get("type", "Unknown")
        if not item_id:
            continue

        try:
            definition = client.get_item_definition(workspace_id, item_id)
            parts = definition.get("definition", {}).get("parts", [])
            if not parts:
                console.print(f"  [dim]=[/dim] {name} ({item_type}): no exportable definition")
                continue

            item_dir = output_dir / name
            item_dir.mkdir(parents=True, exist_ok=True)

            for part in parts:
                part_path = part.get("path", "")
                payload = part.get("payload", "")
                payload_type = part.get("payloadType", "")

                if payload and payload_type == "InlineBase64":
                    file_path = item_dir / part_path
                    file_path.parent.mkdir(parents=True, exist_ok=True)
                    file_path.write_bytes(base64.b64decode(payload))

            console.print(f"  [green]+[/green] {name} ({item_type}): {len(parts)} files → {item_dir}")
            exported += 1
        except Exception as e:
            console.print(f"  [yellow]![/yellow] {name} ({item_type}): {e}")

    console.print()
    console.print(f"Exported {exported} item(s) to {output_dir.resolve()}")


if __name__ == "__main__":
    cli()
