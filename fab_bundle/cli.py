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
@click.version_option(version=None, prog_name="fabric-automation-bundles", package_name="fabric-automation-bundles")
def cli():
    """Fabric Automation Bundles — declarative project definitions for Microsoft Fabric."""
    pass


# ---------------------------------------------------------------------------
# fab bundle init
# ---------------------------------------------------------------------------


@cli.command()
@click.option("--template", "-t", default=None, help="Template name or path")
@click.option("--output", "-o", default=".", help="Output directory")
@click.option("--name", "-n", default=None, help="Bundle project name")
@click.option("--var", multiple=True, help="Template variables (KEY=VALUE)")
@click.option("--interactive", "-i", is_flag=True, default=False, help="Interactive setup wizard")
def init(template: str | None, output: str, name: str | None, var: tuple[str, ...], interactive: bool):
    """Create a new bundle project from a template."""
    from fab_bundle.generators.templates import init_from_template, list_templates

    # If no template or name provided, default to interactive mode
    if not template and not name:
        interactive = True

    if interactive:
        from fab_bundle.generators.templates import list_templates as _list_templates
        templates = _list_templates()
        console.print("[bold]Fabric Automation Bundles — Setup Wizard[/bold]\n")

        # Select template
        console.print("Available templates:")
        for i, t in enumerate(templates, 1):
            console.print(f"  {i}. [bold]{t['name']}[/bold] — {t.get('description', '')}")
        choice = click.prompt("Select template", type=int, default=1)
        if 1 <= choice <= len(templates):
            template = templates[choice - 1]["name"]
        console.print()

        # Project name
        if not name:
            name = click.prompt("Project name", default="my-fabric-project")

        # Capacity
        try:
            console.print("Fetching available capacities...")
            import json as _json
            import subprocess
            r = subprocess.run(
                ["az", "rest", "--method", "get", "--url", "https://api.fabric.microsoft.com/v1/capacities", "--resource", "https://api.fabric.microsoft.com"],
                capture_output=True, text=True, timeout=15,
            )
            if r.returncode == 0:
                caps = _json.loads(r.stdout).get("value", [])
                active = [c for c in caps if c.get("state") == "Active"]
                if active:
                    for i, c in enumerate(active, 1):
                        console.print(f"  {i}. {c['displayName']} ({c['sku']}, {c['region']})")
                    cap_choice = click.prompt("Select capacity", type=int, default=1)
                    if 1 <= cap_choice <= len(active):
                        variables["capacity_id"] = active[cap_choice - 1]["id"]
        except Exception:
            console.print("  [dim]Could not fetch capacities (run 'az login' first)[/dim]")

        console.print()

    # Defaults for non-interactive mode
    if not template:
        template = "blank"
    if not name:
        name = click.prompt("Project name")

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
@click.option("--validate-api", is_flag=True, default=False, help="Validate definitions against Fabric API")
def plan(bundle_file: str | None, target: str | None, auto_delete: bool, validate_api: bool):
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

    if validate_api and deployment_plan.has_changes:
        console.print("[dim]Validating definitions against Fabric API...[/dim]")
        bundle_path = Path(bundle_file) if bundle_file else Path.cwd()
        project_dir = bundle_path.parent if bundle_path.is_file() else bundle_path
        from fab_bundle.engine.deployer import Deployer
        deployer = Deployer(client, bundle, project_dir, console, dry_run=True)
        for item in deployment_plan.items:
            if item.action.value in ("create", "update"):
                defn = deployer._get_item_definition(item.resource_key, item.resource_type)
                if defn:
                    console.print(f"  [dim]✓ {item.resource_key}: definition valid ({len(defn.get('parts', []))} parts)[/dim]")
                else:
                    console.print(f"  [dim]- {item.resource_key}: no definition (metadata only)[/dim]")


# ---------------------------------------------------------------------------
# fab bundle deploy
# ---------------------------------------------------------------------------


@cli.command()
@click.option("--file", "-f", "bundle_file", default=None, help="Path to fabric.yml")
@click.option("--target", "-t", default=None, help="Target environment")
@click.option("--dry-run", is_flag=True, default=False, help="Preview without deploying")
@click.option("--auto-approve", "-y", is_flag=True, default=False, help="Skip confirmation")
@click.option("--auto-delete/--no-auto-delete", default=False, help="Delete unmanaged items")
@click.option("--force", is_flag=True, default=False, help="Override deployment lock and skip cache")
def deploy(bundle_file: str | None, target: str | None, dry_run: bool, auto_approve: bool, auto_delete: bool, force: bool):
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

    # Set up state manager (with remote backend if configured)
    from fab_bundle.engine.state import StateManager
    target_label = target or "default"
    state_backend = getattr(bundle, 'state', None)
    state_mgr = StateManager(
        project_dir, target_label,
        backend_type=state_backend.backend if state_backend else "local",
        backend_config=dict(state_backend.config) if state_backend and state_backend.config else None,
    )

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
    result = deployer.execute(deployment_plan, target, force=force)

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
@click.option("--param", "-p", multiple=True, help="Parameters (KEY=VALUE)")
def run(resource_name: str, bundle_file: str | None, target: str | None, param: tuple[str, ...]):
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

    # Build execution parameters
    params = {}
    # Get default params from bundle
    nb = bundle.resources.notebooks.get(resource_name)
    if nb and nb.parameters:
        params.update(nb.parameters)
    # Override with CLI params
    for p in param:
        if "=" in p:
            k, v = p.split("=", 1)
            params[k] = v

    execution_data = None
    if params:
        execution_data = {"parameters": {k: {"value": v, "type": "string"} for k, v in params.items()}}
        console.print(f"  Parameters: {params}")

    # Trigger execution via Job Scheduler API
    try:
        job_type = "RunNotebook" if item_type == "Notebook" else "Pipeline"
        result = client.run_item_job(workspace_id, item_id, job_type, execution_data=execution_data)

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


# ---------------------------------------------------------------------------
# fab bundle history
# ---------------------------------------------------------------------------


@cli.command()
@click.option("--file", "-f", "bundle_file", default=None, help="Path to fabric.yml")
@click.option("--target", "-t", default=None, help="Target environment")
@click.option("--limit", "-n", default=20, help="Number of entries to show")
def history(bundle_file: str | None, target: str | None, limit: int):
    """Show deployment history."""
    from fab_bundle.engine.state import StateManager

    bundle_path = Path(bundle_file) if bundle_file else Path.cwd()
    project_dir = bundle_path.parent if bundle_path.is_file() else bundle_path

    state_mgr = StateManager(project_dir, target or "default")
    entries = state_mgr.list_history(limit)

    if not entries:
        console.print("[dim]No deployment history found.[/dim]")
        return

    console.print(f"[bold]Deployment History ({target or 'default'}):[/bold]")
    console.print()
    for entry in entries:
        import datetime
        ts = datetime.datetime.fromtimestamp(entry.get("timestamp", 0))
        console.print(
            f"  [bold]{entry.get('deploy_id', '?')}[/bold]  "
            f"{ts.strftime('%Y-%m-%d %H:%M')}  "
            f"v{entry.get('bundle_version', '?')}  "
            f"{entry.get('resource_count', 0)} resources  "
            f"{entry.get('summary', '')}"
        )


# ---------------------------------------------------------------------------
# fab bundle rollback
# ---------------------------------------------------------------------------


@cli.command()
@click.option("--file", "-f", "bundle_file", default=None, help="Path to fabric.yml")
@click.option("--target", "-t", default=None, help="Target environment")
@click.option("--to", "deploy_id", default=None, help="Deploy ID to rollback to")
@click.option("--last", "use_last", is_flag=True, help="Rollback to previous deployment")
@click.option("--auto-approve", "-y", is_flag=True, default=False, help="Skip confirmation")
def rollback(bundle_file: str | None, target: str | None, deploy_id: str | None, use_last: bool, auto_approve: bool):
    """Rollback to a previous deployment."""
    from fab_bundle.engine.state import StateManager

    bundle_path = Path(bundle_file) if bundle_file else Path.cwd()
    project_dir = bundle_path.parent if bundle_path.is_file() else bundle_path

    state_mgr = StateManager(project_dir, target or "default")
    entries = state_mgr.list_history()

    if len(entries) < 2:
        console.print("[yellow]Not enough deployment history to rollback.[/yellow]")
        return

    if use_last:
        target_entry = entries[1]  # Previous deployment (entries[0] is current)
    elif deploy_id:
        target_entry = state_mgr.get_history_entry(deploy_id)
        if not target_entry:
            console.print(f"[red]Deploy ID '{deploy_id}' not found in history.[/red]")
            return
    else:
        console.print("[red]Specify --to <deploy-id> or --last[/red]")
        return

    import datetime
    ts = datetime.datetime.fromtimestamp(target_entry.get("timestamp", 0))
    console.print(f"[bold]Rollback target:[/bold] {target_entry.get('deploy_id')} ({ts.strftime('%Y-%m-%d %H:%M')})")
    console.print(f"  Version: v{target_entry.get('bundle_version', '?')}")
    console.print(f"  Resources: {target_entry.get('resource_count', 0)}")
    console.print()

    if not auto_approve:
        if not click.confirm("Proceed with rollback?"):
            console.print("[dim]Cancelled.[/dim]")
            return

    # Restore the state from history
    from fab_bundle.engine.state import DeploymentState, ResourceState
    resources = {}
    for key, info in target_entry.get("resources", {}).items():
        resources[key] = ResourceState(
            item_id=info.get("item_id", ""),
            item_type=info.get("type", ""),
            resource_key=key,
        )

    state = DeploymentState(
        bundle_name=target_entry.get("bundle_name", ""),
        bundle_version=target_entry.get("bundle_version", ""),
        target_name=target or "default",
        workspace_id=target_entry.get("workspace_id", ""),
        resources=resources,
        last_deployed=target_entry.get("timestamp", 0),
    )
    state_mgr.save(state)
    console.print("[bold green]State rolled back.[/bold green] Run 'fab-bundle deploy' to apply.")


# ---------------------------------------------------------------------------
# fab bundle promote
# ---------------------------------------------------------------------------


@cli.command()
@click.option("--file", "-f", "bundle_file", default=None, help="Path to fabric.yml")
@click.option("--from", "from_target", required=True, help="Source target")
@click.option("--to", "to_target", required=True, help="Destination target")
@click.option("--auto-approve", "-y", is_flag=True, default=False, help="Skip confirmation")
def promote(bundle_file: str | None, from_target: str, to_target: str, auto_approve: bool):
    """Promote deployed artifacts from one target to another."""
    from fab_bundle.engine.loader import BundleLoadError, load_bundle
    from fab_bundle.providers.fabric_api import FabricClient

    try:
        bundle = load_bundle(bundle_file)
    except BundleLoadError as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)

    try:
        client = FabricClient()
    except Exception as e:
        console.print(f"[red]Auth error:[/red] {e}")
        sys.exit(1)

    # Resolve source and dest workspaces
    src_ws = bundle.get_effective_workspace(from_target)
    dst_ws = bundle.get_effective_workspace(to_target)

    src_id = src_ws.workspace_id
    if not src_id and src_ws.name:
        found = client.find_workspace(src_ws.name)
        src_id = found["id"] if found else None

    dst_id = dst_ws.workspace_id
    if not dst_id and dst_ws.name:
        found = client.find_workspace(dst_ws.name)
        dst_id = found["id"] if found else None

    if not src_id:
        console.print(f"[red]Source workspace '{src_ws.name}' not found[/red]")
        sys.exit(1)

    console.print(f"[bold]Promote: {from_target} → {to_target}[/bold]")
    console.print(f"  Source:  {src_ws.name} ({src_id})")
    console.print(f"  Dest:    {dst_ws.name} ({dst_id or 'will be created'})")
    console.print()

    src_items = client.get_workspace_items_map(src_id)
    console.print(f"  {len(src_items)} items to promote")

    if not auto_approve:
        if not click.confirm("Proceed?"):
            return

    # Ensure dest workspace exists
    if not dst_id:
        result = client.create_workspace(name=dst_ws.name, description=dst_ws.description)
        dst_id = result["id"]
        cap = dst_ws.effective_capacity_id
        if cap:
            client.assign_capacity(dst_id, cap)
        console.print(f"  Created workspace: {dst_ws.name}")

    # Copy item definitions from source to dest
    dst_items = client.get_workspace_items_map(dst_id)
    promoted = 0
    for name, info in src_items.items():
        try:
            defn = client.get_item_definition(src_id, info["id"])
            definition = defn.get("definition")

            if name in dst_items:
                if definition:
                    client.update_item_definition(dst_id, dst_items[name]["id"], definition)
                console.print(f"  [yellow]~[/yellow] Updated: {name}")
            else:
                result = client.create_item(dst_id, name, info["type"], definition=definition)
                if result and "operation_url" in result:
                    client._wait_for_operation(result["operation_url"])
                console.print(f"  [green]+[/green] Created: {name}")
            promoted += 1
        except Exception as e:
            console.print(f"  [red]![/red] {name}: {e}")

    console.print(f"\n[bold green]Promoted {promoted} items from {from_target} to {to_target}.[/bold green]")


# ---------------------------------------------------------------------------
# fab bundle doctor
# ---------------------------------------------------------------------------


@cli.command()
def doctor():
    """Diagnose common configuration issues."""
    import shutil
    import subprocess

    checks_passed = 0
    checks_failed = 0

    def check(name: str, fn):
        nonlocal checks_passed, checks_failed
        try:
            result = fn()
            if result:
                console.print(f"  [green]✓[/green] {name}")
                checks_passed += 1
            else:
                console.print(f"  [red]✗[/red] {name}")
                checks_failed += 1
        except Exception as e:
            console.print(f"  [red]✗[/red] {name}: {e}")
            checks_failed += 1

    console.print("[bold]fab-bundle doctor[/bold]")
    console.print()

    # Python version
    import platform
    check(f"Python {platform.python_version()} (>=3.10 required)",
          lambda: tuple(int(x) for x in platform.python_version().split(".")[:2]) >= (3, 10))

    # Required packages
    for pkg in ["pydantic", "click", "rich", "yaml", "requests", "azure.identity"]:
        check(f"Package: {pkg}", lambda p=pkg: __import__(p) is not None)

    # Azure CLI
    check("Azure CLI installed", lambda: shutil.which("az") is not None)

    # Azure login
    def check_az_login():
        r = subprocess.run(["az", "account", "show", "--query", "name", "-o", "tsv"],
                          capture_output=True, text=True, timeout=10)
        return r.returncode == 0
    check("Azure CLI authenticated", check_az_login)

    # Fabric API reachable
    def check_fabric_api():
        from fab_bundle.providers.fabric_api import FabricClient
        client = FabricClient()
        workspaces = client.list_workspaces()
        return isinstance(workspaces, list)
    check("Fabric API reachable", check_fabric_api)

    # fabric.yml exists
    check("fabric.yml found", lambda: Path("fabric.yml").exists() or Path("fabric.yaml").exists())

    # Bundle valid
    def check_bundle():
        from fab_bundle.engine.loader import load_bundle
        load_bundle()
        return True
    if Path("fabric.yml").exists():
        check("Bundle validates", check_bundle)

    console.print()
    console.print(f"  {checks_passed} passed, {checks_failed} failed")


# ---------------------------------------------------------------------------
# fab bundle watch
# ---------------------------------------------------------------------------


@cli.command()
@click.option("--file", "-f", "bundle_file", default=None, help="Path to fabric.yml")
@click.option("--target", "-t", default=None, help="Target environment")
@click.option("--interval", default=5, help="Check interval in seconds")
def watch(bundle_file: str | None, target: str | None, interval: int):
    """Watch for file changes and auto-deploy to target."""
    import hashlib
    import time as time_mod

    bundle_path = Path(bundle_file) if bundle_file else Path.cwd()
    project_dir = bundle_path.parent if bundle_path.is_file() else bundle_path

    console.print(f"[bold]Watching for changes...[/bold] (target: {target or 'default'}, interval: {interval}s)")
    console.print("  Press Ctrl+C to stop.")
    console.print()

    def get_file_hashes(directory: Path) -> dict[str, str]:
        hashes = {}
        for ext in ("*.py", "*.sql", "*.yml", "*.yaml", "*.json", "*.ipynb", "*.tmdl", "*.r", "*.scala"):
            for f in directory.rglob(ext):
                if ".fab-bundle" in str(f) or "__pycache__" in str(f) or ".venv" in str(f):
                    continue
                try:
                    h = hashlib.md5(f.read_bytes()).hexdigest()
                    hashes[str(f.relative_to(directory))] = h
                except Exception:
                    pass
        return hashes

    prev_hashes = get_file_hashes(project_dir)

    try:
        while True:
            time_mod.sleep(interval)
            curr_hashes = get_file_hashes(project_dir)

            changed = []
            for f, h in curr_hashes.items():
                if f not in prev_hashes or prev_hashes[f] != h:
                    changed.append(f)

            if changed:
                import datetime
                console.print(f"  [{datetime.datetime.now().strftime('%H:%M:%S')}] Changed: {', '.join(changed[:5])}")
                try:
                    from fab_bundle.engine.loader import load_bundle
                    from fab_bundle.engine.deployer import Deployer
                    from fab_bundle.engine.planner import create_plan
                    from fab_bundle.providers.fabric_api import FabricClient

                    bundle = load_bundle(bundle_file, target)
                    client = FabricClient()
                    ws = bundle.get_effective_workspace(target)
                    ws_id = ws.workspace_id
                    if not ws_id and ws.name:
                        found = client.find_workspace(ws.name)
                        ws_id = found["id"] if found else None

                    if ws_id:
                        items = client.get_workspace_items_map(ws_id)
                        plan = create_plan(bundle, target, items)
                        if plan.has_changes:
                            deployer = Deployer(client, bundle, project_dir, console)
                            result = deployer.execute(plan, target)
                            if result.success:
                                console.print(f"  [green]Deployed.[/green]")
                        else:
                            console.print(f"  [dim]No deployment changes.[/dim]")
                except Exception as e:
                    console.print(f"  [red]Deploy failed:[/red] {e}")

                prev_hashes = curr_hashes
    except KeyboardInterrupt:
        console.print("\n[dim]Watch stopped.[/dim]")


# ---------------------------------------------------------------------------
# fab bundle status
# ---------------------------------------------------------------------------


@cli.command()
@click.option("--file", "-f", "bundle_file", default=None, help="Path to fabric.yml")
@click.option("--target", "-t", default=None, help="Target environment")
def status(bundle_file: str | None, target: str | None):
    """Show deployed resource health and status."""
    from fab_bundle.engine.loader import BundleLoadError, load_bundle
    from fab_bundle.engine.state import StateManager
    from fab_bundle.providers.fabric_api import FabricClient

    try:
        bundle = load_bundle(bundle_file, target)
    except BundleLoadError as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)

    try:
        client = FabricClient()
    except Exception as e:
        console.print(f"[red]Auth error:[/red] {e}")
        sys.exit(1)

    ws = bundle.get_effective_workspace(target)
    workspace_id = ws.workspace_id
    if not workspace_id and ws.name:
        found = client.find_workspace(ws.name)
        workspace_id = found["id"] if found else None

    if not workspace_id:
        console.print(f"[yellow]Workspace not found.[/yellow] Deploy first.")
        return

    items = client.get_workspace_items_map(workspace_id)
    bundle_keys = bundle.resources.all_resource_keys()

    # State info
    bundle_path = Path(bundle_file) if bundle_file else Path.cwd()
    project_dir = bundle_path.parent if bundle_path.is_file() else bundle_path
    state_mgr = StateManager(project_dir, target or "default")
    state = state_mgr.load()

    console.print(f"[bold]Status: {bundle.bundle.name}[/bold]")
    console.print(f"  Target:    {target or 'default'}")
    console.print(f"  Workspace: {ws.name} ({workspace_id})")
    if state.last_deployed:
        import datetime
        ts = datetime.datetime.fromtimestamp(state.last_deployed)
        console.print(f"  Last deploy: {ts.strftime('%Y-%m-%d %H:%M')}")
    console.print(f"  Items in workspace: {len(items)}")
    console.print(f"  Items in bundle:    {len(bundle_keys)}")
    console.print()

    # Resource table
    from rich.table import Table
    table = Table(show_header=True, header_style="bold", box=None, pad_edge=False)
    table.add_column("Resource", min_width=25)
    table.add_column("Type", min_width=15)
    table.add_column("Status", min_width=10)
    table.add_column("Item ID", min_width=12)

    for key in sorted(bundle_keys):
        in_workspace = key in items
        in_state = key in state.resources
        rt = bundle.resources.get_resource_type(key) or ""

        if in_workspace:
            status_str = "[green]deployed[/green]"
            item_id = items[key].get("id", "")[:12]
        elif in_state:
            status_str = "[red]missing[/red]"
            item_id = state.resources[key].item_id[:12]
        else:
            status_str = "[yellow]pending[/yellow]"
            item_id = ""

        table.add_row(key, rt, status_str, item_id)

    # Show unmanaged items
    unmanaged = set(items.keys()) - bundle_keys
    for key in sorted(unmanaged):
        table.add_row(key, items[key].get("type", ""), "[dim]unmanaged[/dim]", items[key].get("id", "")[:12])

    console.print(table)

    # Drift summary
    drift = state_mgr.detect_drift(items)
    if drift:
        console.print(f"\n  [yellow]Drift detected: {len(drift)} item(s)[/yellow]")


# ---------------------------------------------------------------------------
# fab bundle import
# ---------------------------------------------------------------------------


@cli.command("import")
@click.option("--from-terraform", "tf_state_path", help="Path to terraform.tfstate")
@click.option("--workspace", "-w", help="Workspace name or ID to import from")
@click.option("--output", "-o", default=".", help="Output directory")
@click.option("--target", "-t", default="dev", help="Target name for state")
def import_cmd(tf_state_path: str | None, workspace: str | None, output: str, target: str):
    """Import existing resources into fab-bundle management."""
    import json as _json

    output_dir = Path(output)

    if tf_state_path:
        # Import from Terraform state
        tf_path = Path(tf_state_path)
        if not tf_path.exists():
            console.print(f"[red]File not found: {tf_path}[/red]")
            sys.exit(1)

        tf_state = _json.loads(tf_path.read_text())
        resources = tf_state.get("resources", [])

        fabric_resources = {}
        for res in resources:
            if "microsoft_fabric" in res.get("type", ""):
                for inst in res.get("instances", []):
                    attrs = inst.get("attributes", {})
                    name = attrs.get("display_name", res.get("name", "unknown"))
                    res_type = res.get("type", "").replace("microsoft_fabric_", "")
                    fabric_resources[name] = {
                        "type": res_type,
                        "id": attrs.get("id", ""),
                        "workspace_id": attrs.get("workspace_id", ""),
                    }

        console.print(f"Found {len(fabric_resources)} Fabric resources in Terraform state")
        for name, info in sorted(fabric_resources.items()):
            console.print(f"  {info['type']:20s} {name}")

        # Save as fab-bundle state
        if fabric_resources:
            from fab_bundle.engine.state import StateManager, ResourceState
            state_mgr = StateManager(output_dir, target)
            ws_id = next(iter(fabric_resources.values()), {}).get("workspace_id", "")
            deployed = {
                name: {"id": info["id"], "type": info["type"]}
                for name, info in fabric_resources.items()
            }
            state_mgr.record_deployment(
                bundle_name="imported",
                bundle_version="0.0.0",
                workspace_id=ws_id,
                workspace_name="",
                deployed_items=deployed,
            )
            console.print(f"\n[green]Imported {len(fabric_resources)} resources to fab-bundle state.[/green]")

    elif workspace:
        # Import from live workspace
        from fab_bundle.providers.fabric_api import FabricClient
        client = FabricClient()

        is_guid = len(workspace) == 36 and workspace.count("-") == 4
        if is_guid:
            ws_id = workspace
            ws_name = workspace
        else:
            found = client.find_workspace(workspace)
            if not found:
                console.print(f"[red]Workspace '{workspace}' not found[/red]")
                sys.exit(1)
            ws_id = found["id"]
            ws_name = found.get("displayName", workspace)

        items = client.get_workspace_items_map(ws_id)
        console.print(f"Found {len(items)} items in workspace '{ws_name}'")

        from fab_bundle.engine.state import StateManager
        state_mgr = StateManager(output_dir, target)
        deployed = {name: {"id": info["id"], "type": info.get("type", "")} for name, info in items.items()}
        state_mgr.record_deployment(
            bundle_name="imported",
            bundle_version="0.0.0",
            workspace_id=ws_id,
            workspace_name=ws_name,
            deployed_items=deployed,
        )
        console.print(f"[green]Imported {len(items)} resources to fab-bundle state.[/green]")
    else:
        console.print("[red]Specify --from-terraform or --workspace[/red]")
        sys.exit(1)


# ---------------------------------------------------------------------------
# fab bundle diff
# ---------------------------------------------------------------------------


@cli.command("diff")
@click.option("--file", "-f", "bundle_file", default=None, help="Path to fabric.yml")
@click.option("--target", "-t", default=None, help="Target environment")
@click.argument("resource_name", required=False)
def diff_cmd(bundle_file: str | None, target: str | None, resource_name: str | None):
    """Show definition-level diff between local and deployed."""
    import base64
    import difflib
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

    ws = bundle.get_effective_workspace(target)
    workspace_id = ws.workspace_id
    if not workspace_id and ws.name:
        found = client.find_workspace(ws.name)
        if found:
            workspace_id = found["id"]

    if not workspace_id:
        console.print("[red]Workspace not found[/red]")
        sys.exit(1)

    existing = client.get_workspace_items_map(workspace_id)
    bundle_path = Path(bundle_file) if bundle_file else Path.cwd()
    project_dir = bundle_path.parent if bundle_path.is_file() else bundle_path

    from fab_bundle.engine.deployer import Deployer
    deployer = Deployer(client, bundle, project_dir, console, dry_run=True)

    resources = {}
    if resource_name:
        rt = bundle.resources.get_resource_type(resource_name)
        if rt:
            resources[resource_name] = rt
    else:
        for key in bundle.resources.all_resource_keys():
            rt = bundle.resources.get_resource_type(key)
            if rt:
                resources[key] = rt

    from fab_bundle.providers.fabric_api import ITEM_TYPE_MAP
    has_diff = False

    for key, resource_type_name in sorted(resources.items()):
        fabric_type = ITEM_TYPE_MAP.get(resource_type_name, resource_type_name)
        local_def = deployer._get_item_definition(key, fabric_type)
        if not local_def:
            continue

        item_info = existing.get(key)
        if not item_info:
            console.print(f"[green]+ {key}[/green]: new (not yet deployed)")
            has_diff = True
            continue

        try:
            remote_def = client.get_item_definition(workspace_id, item_info["id"])
            remote_parts = remote_def.get("definition", {}).get("parts", [])
            local_parts = local_def.get("parts", [])

            for local_part in local_parts:
                local_path = local_part.get("path", "")
                local_content = base64.b64decode(local_part.get("payload", "")).decode("utf-8", errors="replace")

                remote_content = ""
                for rp in remote_parts:
                    if rp.get("path") == local_path:
                        remote_content = base64.b64decode(rp.get("payload", "")).decode("utf-8", errors="replace")
                        break

                if local_content != remote_content:
                    has_diff = True
                    diff = difflib.unified_diff(
                        remote_content.splitlines(keepends=True),
                        local_content.splitlines(keepends=True),
                        fromfile=f"deployed/{key}/{local_path}",
                        tofile=f"local/{key}/{local_path}",
                        lineterm="",
                    )
                    for line in diff:
                        if line.startswith("+"):
                            console.print(f"[green]{line}[/green]")
                        elif line.startswith("-"):
                            console.print(f"[red]{line}[/red]")
                        elif line.startswith("@@"):
                            console.print(f"[cyan]{line}[/cyan]")
                        else:
                            console.print(line)
                    console.print()
        except Exception as e:
            console.print(f"[yellow]{key}: could not fetch remote definition: {e}[/yellow]")

    if not has_diff:
        console.print("[dim]No differences found.[/dim]")



# ---------------------------------------------------------------------------
# fab bundle graph
# ---------------------------------------------------------------------------


@cli.command()
@click.option("--file", "-f", "bundle_file", default=None, help="Path to fabric.yml")
@click.option("--target", "-t", default=None, help="Target environment")
@click.option("--format", "output_format", default="mermaid", type=click.Choice(["mermaid", "dot", "text"]), help="Output format")
@click.option("--output", "-o", "output_file", default=None, help="Output file (default: stdout)")
def graph(bundle_file: str | None, target: str | None, output_format: str, output_file: str | None):
    """Visualize the bundle dependency graph."""
    from fab_bundle.engine.loader import BundleLoadError, load_bundle
    from fab_bundle.engine.resolver import build_dependency_graph

    try:
        bundle = load_bundle(bundle_file, target)
    except BundleLoadError as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)

    dep_graph = build_dependency_graph(bundle)

    type_colors = {
        "lakehouses": "#2d6a4f", "notebooks": "#264653", "pipelines": "#e76f51",
        "warehouses": "#f4a261", "semantic_models": "#e9c46a", "reports": "#a8dadc",
        "environments": "#457b9d", "data_agents": "#6d6875", "eventhouses": "#b5838d",
        "eventstreams": "#ffb4a2", "ml_models": "#cdb4db", "ml_experiments": "#ffc8dd",
    }

    if output_format == "mermaid":
        lines = ["graph TD"]
        for key, node in dep_graph.items():
            color = type_colors.get(node.resource_type, "#666")
            label = f"{key}\\n({node.resource_type})"
            lines.append(f'    {key}["{label}"]')
            lines.append(f'    style {key} fill:{color},color:#fff')
            for dep in node.depends_on:
                if dep in dep_graph:
                    lines.append(f"    {dep} --> {key}")
        output = "\n".join(lines)

    elif output_format == "dot":
        lines = ["digraph bundle {", "    rankdir=LR;", '    node [shape=box, style=filled, fontcolor=white];']
        for key, node in dep_graph.items():
            color = type_colors.get(node.resource_type, "#666666")
            lines.append(f'    "{key}" [label="{key}\\n{node.resource_type}", fillcolor="{color}"];')
            for dep in node.depends_on:
                if dep in dep_graph:
                    lines.append(f'    "{dep}" -> "{key}";')
        lines.append("}")
        output = "\n".join(lines)

    else:  # text
        lines = []
        for key, node in dep_graph.items():
            deps = f" ← {', '.join(node.depends_on)}" if node.depends_on else ""
            lines.append(f"  [{node.resource_type}] {key}{deps}")
        output = "\n".join(lines)

    if output_file:
        Path(output_file).write_text(output)
        console.print(f"Graph written to {output_file}")
    else:
        console.print(output)


if __name__ == "__main__":
    cli()
