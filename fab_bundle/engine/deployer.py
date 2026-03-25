"""
Deployer — executes a deployment plan against a Fabric workspace.

Handles the orchestrated creation, update, and deletion of resources
in dependency order with progress reporting.
"""

from __future__ import annotations

import base64
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from fab_bundle.engine.planner import DeploymentPlan, PlanAction, PlanItem
from fab_bundle.models.bundle import BundleDefinition
from fab_bundle.providers.fabric_api import FabricApiError, FabricClient, ITEM_TYPE_MAP, LIST_ONLY_TYPES, DEFINITION_REQUIRED_TYPES, NO_DEFINITION_TYPES
from fab_bundle.engine.state import StateManager, compute_definition_hash


@dataclass
class DeployResult:
    """Result of a deployment."""
    success: bool
    items_created: int = 0
    items_updated: int = 0
    items_deleted: int = 0
    items_skipped: int = 0
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

    def _build_generic_definition(self, path: str, part_name: str) -> dict[str, Any] | None:
        """Build a generic item definition from a single file."""
        content = self._read_file_as_base64(path)
        if not content:
            return None
        return {
            "parts": [
                {
                    "path": part_name,
                    "payload": content,
                    "payloadType": "InlineBase64",
                }
            ],
        }

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
            kernel_map = {
                "python": "synapse_pyspark",
                "sql": "sparksql",
                "scala": "spark_scala",
                "r": "sparkr",
            }
            language = lang_map.get(file_ext, "python")
            kernel = kernel_map.get(language, "synapse_pyspark")

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
                    "kernel_info": {"name": kernel},
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

    def _build_spark_job_definition(self, resource_key: str) -> dict[str, Any] | None:
        """Build Fabric item definition for a Spark Job Definition."""
        sjd = self.bundle.resources.spark_job_definitions.get(resource_key)
        if not sjd or not sjd.path:
            return None

        file_ext = Path(sjd.path).suffix.lower()

        if file_ext == ".jar":
            content_b64 = self._read_file_as_base64(sjd.path)
            return {
                "parts": [
                    {
                        "path": "SparkJobDefinitionV1.json",
                        "payload": base64.b64encode(json.dumps({
                            "executableFile": None,
                            "defaultLakehouseArtifactId": "",
                            "mainClass": "",
                            "additionalLakehouseIds": [],
                            "retryPolicy": None,
                            "commandLineArguments": " ".join(sjd.args) if sjd.args else "",
                            "additionalLibraryUris": [],
                            "language": "Java",
                            "environmentArtifactId": None,
                        }).encode()).decode(),
                        "payloadType": "InlineBase64",
                    },
                    {
                        "path": Path(sjd.path).name,
                        "payload": content_b64,
                        "payloadType": "InlineBase64",
                    },
                ],
            }
        else:
            # .py files — single part with SparkJobDefinitionV1.json only
            # The executable file is referenced by URI after upload, not embedded
            return {
                "parts": [
                    {
                        "path": "SparkJobDefinitionV1.json",
                        "payload": base64.b64encode(json.dumps({
                            "executableFile": None,
                            "defaultLakehouseArtifactId": "",
                            "mainClass": "",
                            "additionalLakehouseIds": [],
                            "retryPolicy": None,
                            "commandLineArguments": " ".join(sjd.args) if sjd.args else "",
                            "additionalLibraryUris": [],
                            "language": "Python",
                            "environmentArtifactId": None,
                        }).encode()).decode(),
                        "payloadType": "InlineBase64",
                    },
                ],
            }

    def _build_pipeline_definition(self, resource_key: str, workspace_id: str | None = None) -> dict[str, Any] | None:
        """Build Fabric item definition for a pipeline."""
        pipeline = self.bundle.resources.pipelines.get(resource_key)
        if not pipeline:
            return None

        if pipeline.path:
            # User-provided pipeline JSON
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

        if not pipeline.activities:
            return None

        # Resolve notebook/pipeline names to workspace item IDs
        items_map = {}
        if workspace_id:
            try:
                items_map = self.client.get_workspace_items_map(workspace_id)
            except Exception:
                pass

        # Generate pipeline JSON from YAML activities
        activities = []
        for activity in pipeline.activities:
            act_def: dict[str, Any] = {
                "name": activity.name or activity.notebook or activity.pipeline or "unnamed",
                "type": "TridentNotebook" if activity.notebook else "ExecutePipeline",
            }

            if activity.notebook:
                # Resolve notebook name to item ID
                nb_info = items_map.get(activity.notebook, {})
                nb_id = nb_info.get("id", "")
                if not nb_id:
                    self.console.print(f"    [yellow]Warning:[/yellow] Notebook '{activity.notebook}' not found in workspace — pipeline may fail")

                act_def["typeProperties"] = {
                    "notebookId": nb_id,
                }
                if workspace_id:
                    act_def["typeProperties"]["workspaceId"] = workspace_id
                if activity.parameters:
                    act_def["typeProperties"]["parameters"] = {
                        k: {"value": v, "type": "string"} for k, v in activity.parameters.items()
                    }
            elif activity.pipeline:
                pipe_info = items_map.get(activity.pipeline, {})
                pipe_id = pipe_info.get("id", "")
                act_def["typeProperties"] = {
                    "pipelineId": pipe_id,
                }
                if workspace_id:
                    act_def["typeProperties"]["workspaceId"] = workspace_id

            if activity.depends_on:
                act_def["dependsOn"] = [
                    {"activity": dep, "dependencyConditions": ["Succeeded"]}
                    for dep in activity.depends_on
                ]

            activities.append(act_def)

        pipeline_json = {
            "properties": {
                "activities": activities,
            },
        }

        content_b64 = base64.b64encode(
            json.dumps(pipeline_json).encode("utf-8")
        ).decode("utf-8")

        return {
            "parts": [
                {
                    "path": "pipeline-content.json",
                    "payload": content_b64,
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

    def _detect_report_schema_version(self, workspace_id: str) -> dict[str, str] | None:
        """Try to detect the correct PBIR schema versions from an existing report in the workspace."""
        try:
            items = self.client.list_items(workspace_id, item_type="Report")
            for item in items:
                try:
                    defn = self.client.get_item_definition(workspace_id, item["id"])
                    parts = defn.get("definition", {}).get("parts", [])
                    for part in parts:
                        if part.get("path") == "definition/version.json":
                            import base64
                            content = base64.b64decode(part["payload"]).decode("utf-8")
                            return json.loads(content)
                except Exception:
                    continue
        except Exception:
            pass
        return None

    def _get_item_definition(self, resource_key: str, resource_type: str) -> dict[str, Any] | None:
        """Get the item definition for a resource based on its type."""
        if resource_type == "DataPipeline":
            return self._build_pipeline_definition(resource_key, workspace_id=getattr(self, '_current_workspace_id', None))

        builders = {
            "Notebook": self._build_notebook_definition,
            "SemanticModel": self._build_semantic_model_definition,
            "Report": self._build_report_definition,
        }
        builder = builders.get(resource_type)
        if builder:
            return builder(resource_key)

        # Type-specific definition part paths used by the Fabric API
        DEFINITION_PART_MAP = {
            "Dataflow": ("dataflows", "dataflow.json"),
            "GraphQLApi": ("graphql_apis", "schema.graphql"),
            "CopyJob": ("copy_jobs", "copyjob.json"),
            "ApacheAirflowJob": ("airflow_jobs", "dag.py"),
            "Reflex": ("reflex", "reflex.json"),
            "UserDataFunction": ("user_data_functions", "function.json"),
            "Eventstream": ("eventstreams", "eventstream.json"),
            "KQLDashboard": ("kql_dashboards", "definition.json"),
            "KQLQueryset": ("kql_querysets", "definition.json"),
            "Ontology": ("ontologies", "definition.json"),
            "Graph": ("graphs", "definition.json"),
            "DataBuildToolJob": ("dbt_jobs", "dbt-project.json"),
            "AnomalyDetector": ("anomaly_detectors", "definition.json"),
            "DigitalTwinBuilder": ("digital_twin_builders", "definition.json"),
            "DigitalTwinBuilderFlow": ("digital_twin_builder_flows", "definition.json"),
            "EventSchemaSet": ("event_schema_sets", "definition.json"),
            "GraphQuerySet": ("graph_query_sets", "definition.json"),
            "Map": ("map_items", "definition.json"),
            "GraphModel": ("graph_models", "definition.json"),
            "HLSCohort": ("hls_cohorts", "definition.json"),
        }

        if resource_type == "SparkJobDefinition":
            sjd = self.bundle.resources.spark_job_definitions.get(resource_key)
            if sjd and sjd.path:
                return self._build_spark_job_definition(resource_key)
            return None

        if resource_type in DEFINITION_PART_MAP:
            field_name, part_name = DEFINITION_PART_MAP[resource_type]
            resource_dict = getattr(self.bundle.resources, field_name, {})
            resource = resource_dict.get(resource_key)
            if resource and hasattr(resource, "path") and resource.path:
                return self._build_generic_definition(resource.path, part_name)
            return None

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

                # Resolve secrets in connection details
                if conn_config.connection_string_var:
                    import os
                    conn_str = os.environ.get(conn_config.connection_string_var)
                    if conn_str:
                        connection_details["connectionString"] = conn_str

                # Resolve any ${secret.*} or ${keyvault.*} references
                try:
                    from fab_bundle.engine.secrets import SecretsResolver
                    resolver = SecretsResolver()
                    connection_details = resolver.resolve_dict(connection_details)
                except Exception:
                    pass  # Secrets resolution is best-effort

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

    def _deploy_onelake_roles(self, workspace_id: str) -> None:
        """Deploy OneLake data access roles for security config."""
        if not self.bundle.security.roles:
            return

        # Collect roles that have onelake_roles defined
        for role in self.bundle.security.roles:
            if not role.onelake_roles:
                continue

            principal_value = role.entra_group or role.entra_user or role.service_principal
            if not principal_value:
                continue

            principal_type = "Group"
            if role.entra_user:
                principal_type = "User"
            elif role.service_principal:
                principal_type = "ServicePrincipal"

            principal_id = self._resolve_principal_id(principal_value, principal_type)

            for binding in role.onelake_roles:
                # Build data access role for each lakehouse
                # Must look up by type=Lakehouse (not SQLEndpoint which shares the same name)
                all_items = self.client.list_items(workspace_id)
                for lh_key in self.bundle.resources.lakehouses:
                    try:
                        lh_id = None
                        for ws_item in all_items:
                            if ws_item.get("displayName") == lh_key and ws_item.get("type") == "Lakehouse":
                                lh_id = ws_item["id"]
                                break
                        if not lh_id:
                            continue

                        # Build permission paths
                        paths = []
                        for table in binding.tables:
                            paths.append("*" if table == "*" else f"/Tables/{table}")
                        for folder in binding.folders:
                            paths.append("*" if folder == "*" else f"/Files/{folder}")
                        if not paths:
                            paths = ["*"]

                        permissions = [p.value.capitalize() for p in binding.permissions]
                        if not permissions:
                            permissions = ["Read"]

                        # Role name: alphanumeric only (no underscores, hyphens, spaces)
                        import re
                        safe_name = re.sub(r'[^a-zA-Z0-9]', '', f"{role.name}{lh_key}")

                        # Build members with required fields
                        entra_members = []
                        if principal_id:
                            entra_members.append({
                                "objectId": principal_id,
                                "objectType": principal_type,
                            })

                        role_def = {
                            "name": safe_name,
                            "decisionRules": [{
                                "effect": "Permit",
                                "permission": [
                                    {"attributeName": "Path", "attributeValueIncludedIn": paths},
                                    {"attributeName": "Action", "attributeValueIncludedIn": permissions},
                                ],
                            }],
                            "members": {
                                "fabricItemMembers": [{
                                    "itemAccess": ["ReadAll"],
                                    "sourcePath": f"{workspace_id}/{lh_id}",
                                }],
                                "microsoftEntraMembers": entra_members,
                            },
                        }

                        if self.dry_run:
                            self.console.print(f"  [dim]Would set OneLake role: {role.name} on {lh_key}[/dim]")
                        else:
                            self.client.update_lakehouse_data_access_roles(
                                workspace_id, lh_id, [role_def],
                            )
                            self.console.print(f"    OneLake role: {safe_name} on {lh_key}")
                    except Exception as e:
                        self.console.print(f"    [yellow]Warning:[/yellow] OneLake role failed on {lh_key}: {e}")

    def _publish_environments(self, workspace_id: str) -> None:
        """Publish Spark environments to install libraries."""
        if not self.bundle.resources.environments:
            return

        for key, env in self.bundle.resources.environments.items():
            if not env.libraries:
                continue

            try:
                items = self.client.get_workspace_items_map(workspace_id)
                env_info = items.get(key)
                if not env_info:
                    continue

                if self.dry_run:
                    self.console.print(f"  [dim]Would publish environment: {key} ({len(env.libraries)} libraries)[/dim]")
                    continue

                self.console.print(f"  Publishing environment: {key}...")
                try:
                    self.client.update_environment_libraries(workspace_id, env_info["id"], env.libraries)
                    self.client.publish_environment(workspace_id, env_info["id"])
                    self.console.print(f"    Published: {key} ({', '.join(env.libraries)})")
                except Exception as e:
                    self.console.print(f"    [yellow]Warning:[/yellow] Environment publish failed for {key}: {e}")
            except Exception as e:
                self.console.print(f"    [yellow]Warning:[/yellow] Environment {key}: {e}")

    def _deploy_schedules(self, workspace_id: str) -> None:
        """Deploy pipeline schedules via the Job Scheduler API."""
        for key, pipeline in self.bundle.resources.pipelines.items():
            if not pipeline.schedule:
                continue

            try:
                items = self.client.get_workspace_items_map(workspace_id)
                pipeline_info = items.get(key)
                if not pipeline_info:
                    continue

                schedule = pipeline.schedule
                schedule_config = {
                    "enabled": schedule.enabled,
                    "configuration": {
                        "type": "Cron",
                        "cronExpression": schedule.cron or "0 6 * * *",
                        "startDateTime": schedule.start_time or "2024-01-01T00:00:00Z",
                        "timeZone": schedule.timezone,
                    },
                }

                if self.dry_run:
                    self.console.print(f"  [dim]Would set schedule for {key}: {schedule.cron}[/dim]")
                else:
                    try:
                        self.client.create_item_schedule(workspace_id, pipeline_info["id"], schedule_config)
                        self.console.print(f"    Schedule: {key} → {schedule.cron} ({schedule.timezone})")
                    except Exception:
                        # Try update if create fails (schedule already exists)
                        self.client.update_item_schedule(workspace_id, pipeline_info["id"], schedule_config)
                        self.console.print(f"    Schedule updated: {key} → {schedule.cron}")
            except Exception as e:
                self.console.print(f"    [yellow]Warning:[/yellow] Schedule for {key} failed: {e}")

    def _refresh_semantic_models(self, workspace_id: str) -> None:
        """Trigger refresh for semantic models with auto_refresh enabled."""
        for key, model in self.bundle.resources.semantic_models.items():
            if not model.auto_refresh:
                continue
            try:
                items = self.client.get_workspace_items_map(workspace_id)
                item_info = items.get(key)
                if not item_info:
                    continue
                if self.dry_run:
                    self.console.print(f"  [dim]Would refresh semantic model: {key}[/dim]")
                else:
                    self.console.print(f"  Refreshing semantic model: {key}...")
                    self.client.refresh_semantic_model(workspace_id, item_info["id"])
                    self.console.print(f"    Refresh complete: {key}")
            except Exception as e:
                self.console.print(f"    [yellow]Warning:[/yellow] Refresh failed for {key}: {e}")

    def _deploy_shortcuts(self, workspace_id: str) -> None:
        """Deploy OneLake shortcuts for lakehouses."""
        for lh_key, lakehouse in self.bundle.resources.lakehouses.items():
            if not lakehouse.shortcuts:
                continue

            items = self.client.get_workspace_items_map(workspace_id)
            lh_info = items.get(lh_key)
            if not lh_info:
                continue

            existing_shortcuts = []
            try:
                existing_shortcuts = self.client.list_shortcuts(workspace_id, lh_info["id"])
            except Exception:
                pass
            existing_names = {s.get("name") for s in existing_shortcuts}

            for shortcut in lakehouse.shortcuts:
                name = shortcut.name
                if name in existing_names:
                    continue

                try:
                    # Parse target — supports ADLS, S3, OneLake, GCS
                    target_str = shortcut.target or ""
                    target_config: dict[str, Any] = {}

                    if target_str.startswith("adls://") or target_str.startswith("abfss://"):
                        parts = target_str.replace("adls://", "").replace("abfss://", "").split("/", 2)
                        target_config = {
                            "adlsGen2": {
                                "location": f"https://{parts[0]}.dfs.core.windows.net",
                                "subpath": f"/{'/'.join(parts[1:])}" if len(parts) > 1 else "/",
                            }
                        }
                        if shortcut.connection_id:
                            target_config["adlsGen2"]["connectionId"] = shortcut.connection_id
                    elif target_str.startswith("s3://"):
                        parts = target_str.replace("s3://", "").split("/", 1)
                        target_config = {
                            "amazonS3": {
                                "location": f"https://{parts[0]}.s3.amazonaws.com",
                                "subpath": f"/{parts[1]}" if len(parts) > 1 else "/",
                            }
                        }
                    elif target_str.startswith("onelake://"):
                        parts = target_str.replace("onelake://", "").split("/", 2)
                        target_config = {
                            "oneLake": {
                                "workspaceId": parts[0] if len(parts) > 0 else "",
                                "itemId": parts[1] if len(parts) > 1 else "",
                                "path": f"/{parts[2]}" if len(parts) > 2 else "/",
                            }
                        }
                    else:
                        # Treat as generic path
                        target_config = {"adlsGen2": {"location": target_str, "subpath": "/"}}

                    shortcut_path = shortcut.path or "Tables"

                    # Build transform config if specified
                    transform_config = None
                    if shortcut.transformation:
                        t = shortcut.transformation
                        if t.type == "file" and t.source_format == "csv":
                            transform_config = {
                                "type": "csvToDelta",
                                "properties": {
                                    "delimiter": ",",
                                    "useFirstRowAsHeader": True,
                                    "skipFilesWithErrors": True,
                                },
                                "includeSubfolders": False,
                            }
                        # Note: JSON, Parquet, Excel, AI transformations are portal-only as of March 2026

                    if self.dry_run:
                        self.console.print(f"  [dim]Would create shortcut: {name} in {lh_key}[/dim]")
                        if transform_config:
                            self.console.print(f"  [dim]  with transform: {transform_config['type']}[/dim]")
                    else:
                        self.client.create_shortcut(
                            workspace_id, lh_info["id"], name, shortcut_path, target_config,
                            transform=transform_config,
                        )
                        xform_label = f" (transform: {transform_config['type']})" if transform_config else ""
                        self.console.print(f"    Shortcut: {name} → {target_str}{xform_label}")
                except Exception as e:
                    self.console.print(f"    [yellow]Warning:[/yellow] Shortcut {name} on {lh_key}: {e}")

    def _run_post_deploy_validation(self, workspace_id: str, target_name: str | None) -> list[str]:
        """Run post-deploy validation checks. Returns list of failures."""
        target = self.bundle.resolve_target(target_name)
        if not target.post_deploy:
            return []

        self.console.print("  Running post-deploy validation...")
        failures = []

        for check in target.post_deploy:
            if check.run:
                try:
                    items = self.client.get_workspace_items_map(workspace_id)
                    item_info = items.get(check.run)
                    if item_info:
                        job_type = "RunNotebook" if item_info.get("type") == "Notebook" else "Pipeline"
                        self.client.run_item_job(workspace_id, item_info["id"], job_type)
                        self.console.print(f"    [green]✓[/green] {check.run}: triggered")
                    else:
                        failures.append(f"{check.run}: not found in workspace")
                except Exception as e:
                    failures.append(f"{check.run}: {e}")

            elif check.sql:
                self.console.print(f"    [dim]SQL validation not yet wired to endpoint[/dim]")

        return failures

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
    ) -> bool | None:
        """Deploy a single item. Returns True on success, False on failure, None if skipped."""
        resource_type_name = self.bundle.resources.get_resource_type(item.resource_key)
        fabric_type = item.resource_type

        # Skip list-only types that cannot be created/updated/deleted via API
        if fabric_type in LIST_ONLY_TYPES:
            self.console.print(f"  [dim]-[/dim] {item.resource_key}: {fabric_type} is list-only (cannot be managed via API)")
            return None

        if item.action == PlanAction.CREATE:
            definition = self._get_item_definition(item.resource_key, item.resource_type)
            description = self._get_description(item.resource_key, resource_type_name) if resource_type_name else None

            # Don't send definition for types that don't support it
            if fabric_type in NO_DEFINITION_TYPES:
                definition = None

            # Warn if definition required but missing
            if fabric_type in DEFINITION_REQUIRED_TYPES and not definition:
                self.console.print(f"  [yellow]Warning:[/yellow] {item.resource_key}: {fabric_type} requires a definition — skipping")
                return None

            if self.dry_run:
                self.console.print(f"  [green]+[/green] Would create {item.resource_type}: {item.resource_key}")
                return True

            # Build creation payload for type-specific options (e.g. schema-enabled lakehouses)
            creation_payload = None
            if item.resource_type == "Lakehouse" and resource_type_name:
                lh = self.bundle.resources.lakehouses.get(item.resource_key)
                if lh and lh.enable_schemas:
                    creation_payload = {"enableSchemas": True}

            # KQL databases require parent eventhouse ID — may need retry if eventhouse still provisioning
            if item.resource_type == "KQLDatabase" and resource_type_name:
                kdb = self.bundle.resources.kql_databases.get(item.resource_key)
                if kdb and kdb.parent_eventhouse:
                    # Look up parent eventhouse by name AND type
                    # Fabric auto-creates a KQLDatabase with same name as the Eventhouse,
                    # so we must filter by type to get the actual Eventhouse item
                    parent_id = None
                    for _wait in range(12):
                        all_items = self.client.list_items(workspace_id)
                        for ws_item in all_items:
                            if ws_item.get("displayName") == kdb.parent_eventhouse and ws_item.get("type") == "Eventhouse":
                                parent_id = ws_item["id"]
                                break
                        if parent_id:
                            break
                        self.console.print(f"  [dim]Waiting for eventhouse '{kdb.parent_eventhouse}' to provision...[/dim]")
                        time.sleep(5)
                    if parent_id:
                        creation_payload = {"parentEventhouseItemId": parent_id}
                    else:
                        self.console.print(f"  [yellow]Warning:[/yellow] Parent eventhouse '{kdb.parent_eventhouse}' not found for KQL database '{item.resource_key}'")
                        return False

            # Digital Twin Builder Flows need parent to be provisioned first
            if item.resource_type == "DigitalTwinBuilderFlow" and resource_type_name:
                dtbf = self.bundle.resources.digital_twin_builder_flows.get(item.resource_key)
                if dtbf and dtbf.twin_builder:
                    # Wait for parent to provision (up to 60s)
                    for _wait in range(12):
                        all_items = self.client.list_items(workspace_id)
                        found = any(
                            i.get("displayName") == dtbf.twin_builder and i.get("type") == "DigitalTwinBuilder"
                            for i in all_items
                        )
                        if found:
                            break
                        self.console.print(f"  [dim]Waiting for twin builder '{dtbf.twin_builder}'...[/dim]")
                        time.sleep(5)

            # For reports: try to auto-detect schema version from existing reports
            if item.resource_type == "Report" and definition:
                detected_version = self._detect_report_schema_version(workspace_id)
                if detected_version:
                    # Inject the detected version.json into the definition parts
                    import base64 as b64
                    version_payload = b64.b64encode(
                        json.dumps(detected_version).encode()
                    ).decode()
                    parts = definition.get("parts", [])
                    # Replace or add version.json
                    parts = [p for p in parts if p.get("path") != "definition/version.json"]
                    parts.append({
                        "path": "definition/version.json",
                        "payload": version_payload,
                        "payloadType": "InlineBase64",
                    })
                    definition["parts"] = parts

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

            # Don't update definition for types that don't support it
            if fabric_type in NO_DEFINITION_TYPES:
                definition = None

            # Skip if definition unchanged (incremental deploy)
            if definition and self.state_manager and not getattr(self, '_force_deploy', False):
                from fab_bundle.engine.state import compute_definition_hash
                new_hash = compute_definition_hash(definition)
                state = self.state_manager.load()
                stored = state.resources.get(item.resource_key)
                if stored and stored.definition_hash and stored.definition_hash == new_hash:
                    self.console.print(f"  [dim]=[/dim] {item.resource_key}: unchanged, skipping")
                    return True

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

    def execute(self, plan: DeploymentPlan, target_name: str | None = None, force: bool = False) -> DeployResult:
        """
        Execute a deployment plan.

        Args:
            plan: The deployment plan to execute.
            target_name: Target environment name.

        Returns:
            DeployResult with outcomes.
        """
        result = DeployResult(success=True)
        self._force_deploy = force

        # Acquire deployment lock
        if self.state_manager and not self.dry_run:
            lock_info = self.state_manager.get_lock_info()
            if lock_info and not getattr(self, '_force_deploy', False):
                self.console.print(f"[red]Deployment locked[/red] by {lock_info.get('deployer', 'unknown')} at {lock_info.get('timestamp', '?')}")
                self.console.print("  Use --force to override.")
                result.success = False
                result.errors.append("Deployment locked")
                return result
            self.state_manager.acquire_lock()

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
            self._current_workspace_id = workspace_id
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
                    if success is None:
                        # Item was skipped (list-only, missing definition, etc.)
                        result.items_skipped += 1
                    elif success:
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
            self._publish_environments(workspace_id)
            self._deploy_security(workspace_id)
            self._deploy_onelake_roles(workspace_id)
            self._deploy_git_integration(workspace_id)
            self._deploy_connections()
            self._deploy_shortcuts(workspace_id)
            self._deploy_schedules(workspace_id)
            self._execute_sql_scripts(workspace_id)
            self._refresh_semantic_models(workspace_id)

            validation_failures = self._run_post_deploy_validation(workspace_id, target_name)
            if validation_failures:
                self.console.print("[yellow]Post-deploy validation warnings:[/yellow]")
                for f in validation_failures:
                    self.console.print(f"  [yellow]![/yellow] {f}")

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
            f"Deleted: {result.items_deleted}  Skipped: {result.items_skipped}  Failed: {result.items_failed}"
        )

        # Release lock (always, even on error)
        try:
            if self.state_manager and not self.dry_run:
                self.state_manager.release_lock()
        except Exception:
            pass

        return result
