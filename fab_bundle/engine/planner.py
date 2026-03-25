"""
Deployment planner — computes the diff between desired state (bundle)
and current state (workspace) to produce a deployment plan.

This is the 'fab bundle plan' engine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from rich.console import Console
from rich.table import Table

from fab_bundle.engine.resolver import ResourceNode, get_deployment_order
from fab_bundle.models.bundle import BundleDefinition


class PlanAction(str, Enum):
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    NO_CHANGE = "no_change"
    REPLACE = "replace"  # delete + create (for immutable changes)


@dataclass
class PlanItem:
    """A single item in the deployment plan."""
    resource_key: str
    resource_type: str
    action: PlanAction
    reason: str = ""
    details: dict[str, Any] = field(default_factory=dict)
    depends_on: list[str] = field(default_factory=list)

    @property
    def symbol(self) -> str:
        return {
            PlanAction.CREATE: "+",
            PlanAction.UPDATE: "~",
            PlanAction.DELETE: "-",
            PlanAction.NO_CHANGE: "=",
            PlanAction.REPLACE: "!",
        }[self.action]

    @property
    def color(self) -> str:
        return {
            PlanAction.CREATE: "green",
            PlanAction.UPDATE: "yellow",
            PlanAction.DELETE: "red",
            PlanAction.NO_CHANGE: "dim",
            PlanAction.REPLACE: "magenta",
        }[self.action]


@dataclass
class DeploymentPlan:
    """Complete deployment plan."""
    bundle_name: str
    target_name: str
    workspace_name: str | None
    items: list[PlanItem] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        return any(item.action != PlanAction.NO_CHANGE for item in self.items)

    @property
    def creates(self) -> list[PlanItem]:
        return [i for i in self.items if i.action == PlanAction.CREATE]

    @property
    def updates(self) -> list[PlanItem]:
        return [i for i in self.items if i.action == PlanAction.UPDATE]

    @property
    def deletes(self) -> list[PlanItem]:
        return [i for i in self.items if i.action == PlanAction.DELETE]

    @property
    def replaces(self) -> list[PlanItem]:
        return [i for i in self.items if i.action == PlanAction.REPLACE]

    @property
    def summary(self) -> str:
        parts = []
        if self.creates:
            parts.append(f"{len(self.creates)} to create")
        if self.updates:
            parts.append(f"{len(self.updates)} to update")
        if self.deletes:
            parts.append(f"{len(self.deletes)} to delete")
        if self.replaces:
            parts.append(f"{len(self.replaces)} to replace")
        no_change = len([i for i in self.items if i.action == PlanAction.NO_CHANGE])
        if no_change:
            parts.append(f"{no_change} unchanged")
        return ", ".join(parts) if parts else "No resources defined"

    def display(self, console: Console | None = None) -> None:
        """Pretty-print the plan to the console."""
        console = console or Console()

        console.print()
        console.print(f"[bold]Deployment Plan: {self.bundle_name}[/bold]")
        console.print(f"  Target:    {self.target_name}")
        if self.workspace_name:
            console.print(f"  Workspace: {self.workspace_name}")
        console.print()

        if self.errors:
            for error in self.errors:
                console.print(f"  [red]ERROR:[/red] {error}")
            console.print()
            return

        if self.warnings:
            for warning in self.warnings:
                console.print(f"  [yellow]WARNING:[/yellow] {warning}")
            console.print()

        if not self.has_changes:
            console.print("  [dim]No changes detected. Infrastructure is up to date.[/dim]")
            return

        table = Table(show_header=True, header_style="bold", box=None, pad_edge=False)
        table.add_column("", width=3)
        table.add_column("Resource", min_width=30)
        table.add_column("Type", min_width=18)
        table.add_column("Action", min_width=12)
        table.add_column("Details", min_width=30)

        for item in self.items:
            if item.action == PlanAction.NO_CHANGE:
                continue
            table.add_row(
                f"[{item.color}]{item.symbol}[/{item.color}]",
                f"[{item.color}]{item.resource_key}[/{item.color}]",
                item.resource_type,
                f"[{item.color}]{item.action.value}[/{item.color}]",
                item.reason,
            )

        console.print(table)
        console.print()
        console.print(f"  [bold]Summary:[/bold] {self.summary}")
        console.print()


def create_plan(
    bundle: BundleDefinition,
    target_name: str | None = None,
    workspace_items: dict[str, dict[str, Any]] | None = None,
    auto_delete: bool = False,
) -> DeploymentPlan:
    """
    Create a deployment plan by comparing bundle definition to workspace state.

    Args:
        bundle: The parsed bundle definition.
        target_name: Target to plan for (uses default if None).
        workspace_items: Current items in the workspace (from API). 
                         Dict of item_name -> {type, id, last_modified, ...}
                         If None, treats everything as CREATE.
        auto_delete: If True, items in workspace not in bundle are marked for deletion.

    Returns:
        DeploymentPlan with ordered items.
    """
    workspace = bundle.get_effective_workspace(target_name)
    workspace_items = workspace_items or {}

    plan = DeploymentPlan(
        bundle_name=bundle.bundle.name,
        target_name=target_name or "(default)",
        workspace_name=workspace.name,
    )

    # Get deployment-ordered resources
    try:
        ordered_nodes = get_deployment_order(bundle)
    except Exception as e:
        plan.errors.append(str(e))
        return plan

    # Map Fabric item type names to our resource type names
    fabric_type_map = {
        "lakehouses": "Lakehouse",
        "notebooks": "Notebook",
        "pipelines": "DataPipeline",
        "warehouses": "Warehouse",
        "semantic_models": "SemanticModel",
        "reports": "Report",
        "data_agents": "DataAgent",
        "environments": "Environment",
        "eventhouses": "Eventhouse",
        "eventstreams": "Eventstream",
        "ml_models": "MLModel",
        "ml_experiments": "MLExperiment",
    }

    # Track which workspace items are accounted for
    accounted_items: set[str] = set()

    for node in ordered_nodes:
        fabric_type = fabric_type_map.get(node.resource_type, node.resource_type)

        # Check if item exists in workspace
        existing = workspace_items.get(node.key)

        if existing:
            accounted_items.add(node.key)
            # Item exists — mark as update or no_change
            plan.items.append(PlanItem(
                resource_key=node.key,
                resource_type=fabric_type,
                action=PlanAction.UPDATE,
                reason="Definition updated",
                depends_on=list(node.depends_on),
            ))
        else:
            # Item doesn't exist — create
            plan.items.append(PlanItem(
                resource_key=node.key,
                resource_type=fabric_type,
                action=PlanAction.CREATE,
                reason="New resource",
                depends_on=list(node.depends_on),
            ))

    # Check for items in workspace not in bundle
    if auto_delete:
        for item_name, item_info in workspace_items.items():
            if item_name not in accounted_items:
                plan.items.append(PlanItem(
                    resource_key=item_name,
                    resource_type=item_info.get("type", "Unknown"),
                    action=PlanAction.DELETE,
                    reason="Not in bundle definition",
                ))
    else:
        unmanaged = set(workspace_items.keys()) - accounted_items
        if unmanaged:
            plan.warnings.append(
                f"{len(unmanaged)} workspace item(s) not managed by this bundle: "
                + ", ".join(sorted(unmanaged)[:5])
                + ("..." if len(unmanaged) > 5 else "")
            )

    return plan
