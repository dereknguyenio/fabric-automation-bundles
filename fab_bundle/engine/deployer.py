"""
Deployer — executes a deployment plan against a Fabric workspace.

Handles the orchestrated creation, update, and deletion of resources
in dependency order with progress reporting.
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from fab_bundle.engine.planner import DeploymentPlan, PlanAction, PlanItem
from fab_bundle.models.bundle import BundleDefinition
from fab_bundle.providers.fabric_api import FabricApiError, FabricClient, ITEM_TYPE_MAP
from fab_bundle.engine.state import StateManager, compute_definition_hash


@dataclass
class DeployResult:
    """Result of a deployment."""
    success: bool
    items_created: int = 0
    items_updated: int = 0
    items_deleted: int = 0
    items_failed: int = 0
    errors: list[str] = field(default_factory=list)
    item_ids: dict[str, str] = field(default_factory=dict)  # resource_key -> item_id
    rollback_log: list[str] = field(default_factory=list)


class Deployer:
    """
    Executes deployment plans against Fabric workspaces.

    Usage:
        deployer = Deployer(client, bundle, project_dir)
        result = deployer.execute(plan)
    """

    def __init__(
        self,
        client: FabricClient,
        bundle: BundleDefinition,
        project_dir: Path,
        console: Console | None = None,
        dry_run: bool = False,
        parallel: bool = False,
    ):
        self.client = client
        self.bundle = bundle
        self.project_dir = project_dir
        self.console = console or Console()
        self.dry_run = dry_run
        self.state_manager: StateManager | None = None
        self._rollback_stack: list[dict[str, Any]] = []
        self.parallel = parallel

    def _resolve_path(self, relative_path: str) -> Path:
        """Resolve a relative path against the project directory."""
        return self.project_dir / relative_path

    def _read_file_as_base64(self, path: str) -> str:
        """Read a file and return its content as base64."""
        full_path = self._resolve_path(path)
        if not full_path.exists():
            raise FileNotFoundError(f"File not found: {full_path}")
        return base64.b64encode(full_path.read_bytes()).decode("utf-8")

    def _read_file_text(self, path: str) -> str:
        """Read a file and return its text content."""
        full_path = self._resolve_path(path)
        if not full_path.exists():
            raise FileNotFoundError(f"File not found: {full_path}")
        return full_path.read_text(encoding="utf-8")

    def _build_notebook_definition(self, resource_key: str) -> dict[str, Any] | None:
        """Build Fabric item definition for a notebook.

        For .ipynb files: uses ipynb format directly.
        For .py/.sql/.scala/.r files: wraps in ipynb JSON structure since
        fabricGitSource requires special Fabric metadata annotations.
        """
        nb = self.bundle.resources.notebooks.get(resource_key)
        if not nb:
            return None

        file_ext = Path(nb.path).suffix.lower()
        raw_content = self._read_file_text(nb.path)

        if file_ext == ".ipynb":
            # Already ipynb — use as-is
            content_b64 = self._read_file_as_base64(nb.path)
            return {
                "format": "ipynb",
                "parts": [
                    {
                        "path": "artifact.content.ipynb",
                        "payload": content_b64,
                        "payloadType": "InlineBase64",
                    }
                ],
            }
        else:
            # Wrap .py/.sql/.scala/.r in ipynb JSON structure
            lang_map = {".py": "python", ".sql": "sql", ".scala": "scala", ".r": "r"}
            language = lang_map.get(file_ext, "python")

            ipynb = {
                "nbformat": 4,
                "nbformat_minor": 5,
                "cells": [
                    {
                        "cell_type": "code",
                        "source": [raw_content],
                        "execution_count": None,
                        "outputs": [],
                        "metadata": {},
                    }
                ],
                "metadata": {
                    "language_info": {"name": language},
                },
            }

            ipynb_b64 = base64.b64encode(
                json.dumps(ipynb).encode("utf-8")
            ).decode("utf-8")

            return {
                "format": "ipynb",
                "parts": [
                    {
                        "path": "artifact.content.ipynb",
                        "payload": ipynb_b64,
                        "payloadType": "InlineBase64",
                    }
                ],
            }

    def _build_pipeline_definition(self, resource_key: str) -> dict[str, Any] | None:
        """Build Fabric item definition for a pipeline."""
        pipeline = self.bundle.resources.pipelines.get(resource_key)
        if not pipeline or not pipeline.path:
            return None

        content = self._read_file_as_base64(pipeline.path)
        return {
            "parts": [
                {
                    "path": "pipeline-content.json",
                    "payload": content,
                    "payloadType": "InlineBase64",
                }
            ],
        }

    def _build_semantic_model_definition(self, resource_key: str) -> dict[str, Any] | None:
        """Build Fabric item definition for a semantic model."""
        sm = self.bundle.resources.semantic_models.get(resource_key)
        if not sm:
            return None

        model_dir = self._resolve_path(sm.path)
        if not model_dir.is_dir():
            return None

        parts = []
        for file_path in sorted(model_dir.rglob("*")):
            if file_path.is_file():
                relative = file_path.relative_to(model_dir)
                content = base64.b64encode(file_path.read_bytes()).decode("utf-8")
                parts.append({
                    "path": str(relative),
                    "payload": content,
                    "payloadType": "InlineBase64",
                })

        return {"parts": parts} if parts else None

    def _build_report_definition(self, resource_key: str) -> dict[str, Any] | None:
        """Build Fabric item definition for a report."""
        report = self.bundle.resources.reports.get(resource_key)
        if not report:
            return None

        report_path = self._resolve_path(report.path)
        if report_path.is_dir():
            parts = []
            for file_path in sorted(report_path.rglob("*")):
                if file_path.is_file():
                    relative = file_path.relative_to(report_path)
                    content = base64.b64encode(file_path.read_bytes()).decode("utf-8")
                    parts.append({
                        "path": str(relative),
                        "payload": content,
                        "payloadType": "InlineBase64",
                    })
            return {"parts": parts} if parts else None
        else:
            content = self._read_file_as_base64(report.path)
            return {
                "parts": [
                    {
                        "path": report_path.name,
                        "payload": content,
                        "payloadType": "InlineBase64",
                    }
                ],
            }

    def _get_item_definition(self, resource_key: str, resource_type: str) -> dict[str, Any] | None:
        """Get the item definition for a resource based on its type."""
        builders = {
            "Notebook": self._build_notebook_definition,
            "DataPipeline": self._build_pipeline_definition,
            "SemanticModel": self._build_semantic_model_definition,
            "Report": self._build_report_definition,
        }
        builder = builders.get(resource_type)
        if builder:
            return builder(resource_key)
        return None

    def _get_description(self, resource_key: str, resource_type_name: str) -> str | None:
        """Get the description for a resource from the bundle."""
        resource_dict = getattr(self.bundle.resources, resource_type_name, {})
        if isinstance(resource_dict, dict):
            resource = resource_dict.get(resource_key)
            if resource and hasattr(resource, "description"):
                return resource.description
        return None

    def _resolve_principal_id(self, value: str, principal_type: str) -> str | None:
        """Resolve a principal display name to a GUID using Microsoft Graph."""
        from fab_bundle.providers.graph_api import is_guid
        if is_guid(value):
            return value
        try:
            from fab_bundle.providers.graph_api import GraphClient
            if not hasattr(self, '_graph_client'):
                self._graph_client = GraphClient()
            resolved = self._graph_client.resolve_principal(value, principal_type)
            if resolved:
                self.console.print(f"    Resolved '{value}' → {resolved}")
            return resolved
        except Exception:
            return None

    def _deploy_security(self, workspace_id: str) -> None:
        """Deploy security role assignments to the workspace."""
        if not self.bundle.security.roles:
            return

        self.console.print("  Applying security roles...")
        for role in self.bundle.security.roles:
            principal_value = role.entra_group or role.entra_user or role.service_principal
            if not principal_value:
                continue

            principal_type = "Group"
            if role.entra_user:
                principal_type = "User"
            elif role.service_principal:
                principal_type = "ServicePrincipal"

            # Resolve display name to GUID if needed
            principal_id = self._resolve_principal_id(principal_value, principal_type)
            if not principal_id:
                self.console.print(f"    [yellow]Warning:[/yellow] Could not resolve '{principal_value}' to a GUID. Skipping.")
                continue

            # Map workspace role names to Fabric API role names
            role_map = {
                "admin": "Admin",
                "member": "Member",
                "contributor": "Contributor",
                "viewer": "Viewer",
            }
            fabric_role = role_map.get(role.workspace_role.value, "Viewer")

            if self.dry_run:
                self.console.print(f"    [dim]Would assign {fabric_role} to {principal_id}[/dim]")
            else:
                try:
                    self.client.add_workspace_role_assignment(
                        workspace_id, principal_id, principal_type, fabric_role,
                    )
                    self.console.print(f"    Assigned {fabric_role} to {principal_id}")
                except Exception as e:
                    self.console.print(f"    [yellow]Warning:[/yellow] Could not assign role: {e}")

    def _deploy_git_integration(self, workspace_id: str) -> None:
        """Configure git integration for the workspace."""
        ws_config = self.bundle.workspace
        if not ws_config.git_integration:
            return

        git = ws_config.git_integration
        if self.dry_run:
            self.console.print(f"  [dim]Would connect workspace to git: {git.repository}[/dim]")
            return

        self.console.print(f"  Connecting workspace to git: {git.repository}")
        try:
            self.client.connect_workspace_to_git(
                workspace_id=workspace_id,
                provider=git.provider,
                organization=git.organization or "",
                project=git.project,
                repository=git.repository or "",
                branch=git.branch,
                directory=git.directory,
            )
            self.client.initialize_git_connection(workspace_id)
            self.console.print("  Git integration configured.")
        except Exception as e:
            self.console.print(f"  [yellow]Warning:[/yellow] Git integration failed: {e}")

    def _deploy_connections(self) -> dict[str, str]:
        """Deploy connections defined in the bundle. Returns name -> connection_id map."""
        if not self.bundle.connections:
            return {}

        connection_ids: dict[str, str] = {}
        self.console.print("  Deploying connections...")

        for name, conn_config in self.bundle.connections.items():
            if self.dry_run:
                self.console.print(f"    [dim]Would create connection: {name}[/dim]")
                continue

            try:
                connection_details = {"type": conn_config.type.value}
                if conn_config.endpoint:
                    connection_details["endpoint"] = conn_config.endpoint
                if conn_config.database:
                    connection_details["database"] = conn_config.database
                connection_details.update(conn_config.properties)

                result = self.client.create_connection(
                    display_name=name,
                    connection_type=conn_config.type.value,
                    connection_details=connection_details,
                )
                conn_id = result.get("id", "")
                connection_ids[name] = conn_id
                self.console.print(f"    Created connection: {name}")
            except Exception as e:
                self.console.print(f"    [yellow]Warning:[/yellow] Connection '{name}' failed: {e}")

        return connection_ids

    def _execute_sql_scripts(self, workspace_id: str) -> None:
        """Execute SQL scripts for warehouse resources."""
        for key, warehouse in self.bundle.resources.warehouses.items():
            if not warehouse.sql_scripts:
                continue

            # Find the warehouse item ID
            try:
                items = self.client.get_workspace_items_map(workspace_id)
                warehouse_info = items.get(key)
                if not warehouse_info:
                    self.console.print(f"  [yellow]Warning:[/yellow] Warehouse '{key}' not found, skipping SQL scripts")
                    continue
                warehouse_id = warehouse_info["id"]
            except Exception:
                continue

            for script_path in warehouse.sql_scripts:
                if self.dry_run:
                    self.console.print(f"  [dim]Would execute SQL: {script_path}[/dim]")
                    continue

                try:
                    sql = self._read_file_text(script_path)
                    self.console.print(f"  Executing SQL: {script_path}")
                    self.client.execute_sql(workspace_id, warehouse_id, sql)
                except Exception as e:
                    self.console.print(f"  [yellow]Warning:[/yellow] SQL script '{script_path}' failed: {e}")

    def _deploy_shortcuts(self, workspace_id: str) -> None:
        """Deploy OneLake shortcuts for lakehouses."""
        for key, lakehouse in self.bundle.resources.lakehouses.items():
            if not lakehouse.shortcuts:
                continue

            # Find the lakehouse item ID
            try:
                items = self.client.get_workspace_items_map(workspace_id)
                lh_info = items.get(key)
                if not lh_info:
                    continue
                lh_id = lh_info["id"]
            except Exception:
                continue

            for shortcut in lakehouse.shortcuts:
                if self.dry_run:
                    self.console.print(f"  [dim]Would create shortcut: {shortcut.name} in {key}[/dim]")
                    continue

                try:
                    # Parse target URI to determine shortcut type
                    target_config = {"type": "ExternalTarget"}
                    if shortcut.target.startswith("adls://"):
                        parts = shortcut.target.replace("adls://", "").split("/", 2)
                        target_config = {
                            "adlsGen2": {
                                "location": f"https://{parts[0]}.dfs.core.windows.net",
                                "subpath": f"/{'/'.join(parts[1:])}" if len(parts) > 1 else "/",
                            }
                        }

                    path = shortcut.subfolder or "/Tables"
                    self.client.create_shortcut(workspace_id, lh_id, shortcut.name, path, target_config)
                    self.console.print(f"    Created shortcut: {shortcut.name} in {key}")
                except Exception as e:
                    self.console.print(f"    [yellow]Warning:[/yellow] Shortcut '{shortcut.name}' failed: {e}")

    def _rollback(self, workspace_id: str, result: DeployResult) -> None:
        """Attempt to rollback created items on failure."""
        if not self._rollback_stack:
            return

        self.console.print()
        self.console.print("[yellow]Rolling back created items...[/yellow]")

        for entry in reversed(self._rollback_stack):
            item_id = entry.get("item_id")
            key = entry.get("resource_key", "unknown")
            if item_id:
                try:
                    self.client.delete_item(workspace_id, item_id)
                    result.rollback_log.append(f"Rolled back: {key}")
                    self.console.print(f"  [yellow]-[/yellow] Rolled back: {key}")
                except Exception as e:
                    result.rollback_log.append(f"Rollback failed for {key}: {e}")
                    self.console.print(f"  [red]Rollback failed:[/red] {key}: {e}")

    def _ensure_workspace(self, target_name: str | None = None) -> str:
        """Ensure the target workspace exists and return its ID."""
        ws_config = self.bundle.get_effective_workspace(target_name)

        if ws_config.workspace_id:
            return ws_config.workspace_id

        if not ws_config.name:
            raise ValueError("No workspace name or ID specified for target")

        existing = self.client.find_workspace(ws_config.name)
        if existing:
            return existing["id"]

        # Create workspace
        if self.dry_run:
            self.console.print(f"  [dim]Would create workspace: {ws_config.name}[/dim]")
            return "dry-run-workspace-id"

        self.console.print(f"  Creating workspace: {ws_config.name}")
        result = self.client.create_workspace(
            name=ws_config.name,
            description=ws_config.description,
        )
        workspace_id = result["id"]

        # Assign capacity if specified
        cap_id = ws_config.effective_capacity_id
        if cap_id:
            self.client.assign_capacity(workspace_id, cap_id)

        return workspace_id

    def _deploy_item(
        self,
        workspace_id: str,
        item: PlanItem,
        existing_items: dict[str, dict[str, Any]],
    ) -> bool:
        """Deploy a single item. Returns True on success."""
        resource_type_name = self.bundle.resources.get_resource_type(item.resource_key)

        if item.action == PlanAction.CREATE:
            definition = self._get_item_definition(item.resource_key, item.resource_type)
            description = self._get_description(item.resource_key, resource_type_name) if resource_type_name else None

            if self.dry_run:
                self.console.print(f"  [green]+[/green] Would create {item.resource_type}: {item.resource_key}")
                return True

            # Build creation payload for type-specific options (e.g. schema-enabled lakehouses)
            creation_payload = None
            if item.resource_type == "Lakehouse" and resource_type_name:
                lh = self.bundle.resources.lakehouses.get(item.resource_key)
                if lh and lh.enable_schemas:
                    creation_payload = {"enableSchemas": True}

            result = self.client.create_item(
                workspace_id=workspace_id,
                display_name=item.resource_key,
                item_type=item.resource_type,
                definition=definition,
                description=description,
                creation_payload=creation_payload,
            )

            # Handle LRO (202 Accepted) — poll for completion then look up item
            if result and "operation_url" in result:
                try:
                    self.client._wait_for_operation(result["operation_url"])
                    # LRO completed — look up the created item by name
                    items_map = self.client.get_workspace_items_map(workspace_id)
                    item_id = items_map.get(item.resource_key, {}).get("id")
                except Exception:
                    item_id = None
            else:
                item_id = result.get("id")
            if item_id:
                self._rollback_stack.append({
                    "resource_key": item.resource_key,
                    "item_id": item_id,
                    "action": "created",
                })
            return bool(item_id)

        elif item.action == PlanAction.UPDATE:
            existing = existing_items.get(item.resource_key, {})
            item_id = existing.get("id")
            if not item_id:
                self.console.print(f"  [yellow]![/yellow] Cannot update {item.resource_key}: item ID not found")
                return False

            definition = self._get_item_definition(item.resource_key, item.resource_type)

            if self.dry_run:
                self.console.print(f"  [yellow]~[/yellow] Would update {item.resource_type}: {item.resource_key}")
                return True

            if definition:
                self.client.update_item_definition(workspace_id, item_id, definition)

            description = self._get_description(item.resource_key, resource_type_name) if resource_type_name else None
            if description:
                self.client.update_item(workspace_id, item_id, description=description)

            return True

        elif item.action == PlanAction.DELETE:
            existing = existing_items.get(item.resource_key, {})
            item_id = existing.get("id")
            if not item_id:
                return True  # Already gone

            if self.dry_run:
                self.console.print(f"  [red]-[/red] Would delete {item.resource_type}: {item.resource_key}")
                return True

            self.client.delete_item(workspace_id, item_id)
            return True

        return True  # NO_CHANGE

    def execute(self, plan: DeploymentPlan, target_name: str | None = None) -> DeployResult:
        """
        Execute a deployment plan.

        Args:
            plan: The deployment plan to execute.
            target_name: Target environment name.

        Returns:
            DeployResult with outcomes.
        """
        result = DeployResult(success=True)

        if not plan.has_changes:
            self.console.print("[dim]No changes to deploy.[/dim]")
            return result

        if plan.errors:
            result.success = False
            result.errors = plan.errors
            return result

        # Ensure workspace exists
        try:
            workspace_id = self._ensure_workspace(target_name)
        except Exception as e:
            result.success = False
            result.errors.append(f"Failed to ensure workspace: {e}")
            return result

        # Get current workspace items for update operations
        existing_items: dict[str, dict[str, Any]] = {}
        if not self.dry_run:
            try:
                existing_items = self.client.get_workspace_items_map(workspace_id)
            except Exception:
                pass  # Will treat as fresh workspace

        # Execute plan items in order
        action_items = [i for i in plan.items if i.action != PlanAction.NO_CHANGE]

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=self.console,
            disable=self.dry_run,
        ) as progress:
            task = progress.add_task("Deploying...", total=len(action_items))

            for item in action_items:
                progress.update(task, description=f"{item.symbol} {item.resource_key}")

                try:
                    success = self._deploy_item(workspace_id, item, existing_items)
                    if success:
                        if item.action == PlanAction.CREATE:
                            result.items_created += 1
                        elif item.action == PlanAction.UPDATE:
                            result.items_updated += 1
                        elif item.action == PlanAction.DELETE:
                            result.items_deleted += 1
                    else:
                        result.items_failed += 1
                        result.errors.append(f"Failed to {item.action.value} {item.resource_key}")
                except FabricApiError as e:
                    result.items_failed += 1
                    result.errors.append(f"{item.resource_key}: {e}")
                    self.console.print(f"  [red]ERROR[/red] {item.resource_key}: {e}")
                except FileNotFoundError as e:
                    result.items_failed += 1
                    result.errors.append(f"{item.resource_key}: {e}")
                    self.console.print(f"  [red]ERROR[/red] {item.resource_key}: {e}")
                except Exception as e:
                    result.items_failed += 1
                    result.errors.append(f"{item.resource_key}: Unexpected error: {e}")
                    self.console.print(f"  [red]ERROR[/red] {item.resource_key}: {e}")

                progress.advance(task)

        # Rollback on failure if items were created
        if result.items_failed > 0 and self._rollback_stack:
            self._rollback(workspace_id, result)

        result.success = result.items_failed == 0

        # Deploy security, git, connections, SQL scripts (only on success)
        if result.success and not self.dry_run:
            self._deploy_security(workspace_id)
            self._deploy_git_integration(workspace_id)
            self._deploy_connections()
            self._deploy_shortcuts(workspace_id)
            self._execute_sql_scripts(workspace_id)

        # Save state
        if result.success and not self.dry_run and self.state_manager:
            deployed_items: dict[str, dict[str, Any]] = {}
            try:
                current_items = self.client.get_workspace_items_map(workspace_id)
                for item in plan.items:
                    if item.action in (PlanAction.CREATE, PlanAction.UPDATE):
                        live = current_items.get(item.resource_key, {})
                        definition = self._get_item_definition(item.resource_key, item.resource_type)
                        deployed_items[item.resource_key] = {
                            "id": live.get("id", ""),
                            "type": item.resource_type,
                            "definition_hash": compute_definition_hash(definition),
                        }
            except Exception:
                pass

            if deployed_items:
                ws_config = self.bundle.get_effective_workspace(target_name)
                self.state_manager.record_deployment(
                    bundle_name=self.bundle.bundle.name,
                    bundle_version=self.bundle.bundle.version,
                    workspace_id=workspace_id,
                    workspace_name=ws_config.name or "",
                    deployed_items=deployed_items,
                )

        # Summary
        self.console.print()
        if result.success:
            self.console.print("[bold green]Deployment complete.[/bold green]")
        else:
            self.console.print("[bold red]Deployment completed with errors.[/bold red]")
            if result.rollback_log:
                self.console.print("[yellow]Rollback actions:[/yellow]")
                for entry in result.rollback_log:
                    self.console.print(f"  {entry}")

        self.console.print(
            f"  Created: {result.items_created}  Updated: {result.items_updated}  "
            f"Deleted: {result.items_deleted}  Failed: {result.items_failed}"
        )

        return result
