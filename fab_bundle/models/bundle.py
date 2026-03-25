"""
Pydantic models for Fabric Asset Bundle definitions.

These models define the schema for fabric.yml — the single declarative
project definition file for Microsoft Fabric projects.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class WorkspaceRole(str, Enum):
    ADMIN = "admin"
    MEMBER = "member"
    CONTRIBUTOR = "contributor"
    VIEWER = "viewer"


class OneLakePermission(str, Enum):
    READ = "read"
    WRITE = "write"
    READWRITE = "readwrite"


class ConnectionType(str, Enum):
    ADLS_GEN2 = "adls_gen2"
    SQL_SERVER = "sql_server"
    AZURE_SQL = "azure_sql"
    COSMOS_DB = "cosmos_db"
    KUSTO = "kusto"
    HTTP = "http"
    CUSTOM = "custom"


class ScheduleFrequency(str, Enum):
    ONCE = "once"
    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    CRON = "cron"


class SparkRuntimeVersion(str, Enum):
    V1_2 = "1.2"
    V1_3 = "1.3"


class DeployAction(str, Enum):
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    NO_CHANGE = "no_change"


# ---------------------------------------------------------------------------
# Sub-models: Workspace & Capacity
# ---------------------------------------------------------------------------

class CapacityConfig(BaseModel):
    """Fabric capacity configuration."""
    sku: str | None = Field(None, description="Capacity SKU (e.g., F2, F4, F16, F64)")
    capacity_id: str | None = Field(None, description="Explicit capacity ID")

    @model_validator(mode="after")
    def validate_capacity(self) -> "CapacityConfig":
        if not self.sku and not self.capacity_id:
            raise ValueError("Either 'sku' or 'capacity_id' must be provided")
        return self


class WorkspaceConfig(BaseModel):
    """Workspace-level configuration."""
    name: str | None = Field(None, description="Workspace display name")
    workspace_id: str | None = Field(None, description="Existing workspace ID to bind to")
    capacity: str | None = Field(None, description="Capacity SKU or ID")
    description: str | None = None
    git_integration: GitIntegrationConfig | None = None


class GitIntegrationConfig(BaseModel):
    """Git integration settings for the workspace."""
    provider: str = Field("azuredevops", description="Git provider: azuredevops or github")
    organization: str | None = None
    project: str | None = None
    repository: str | None = None
    branch: str = "main"
    directory: str = "/"


# ---------------------------------------------------------------------------
# Sub-models: Resources
# ---------------------------------------------------------------------------

class ShortcutConfig(BaseModel):
    """OneLake shortcut definition."""
    name: str
    target: str = Field(..., description="Target path (e.g., adls://account/container/path)")
    subfolder: str | None = None


class LakehouseResource(BaseModel):
    """Lakehouse resource definition."""
    description: str | None = None
    schemas: list[str] = Field(default_factory=list, description="Paths to JSON schema files")
    shortcuts: list[ShortcutConfig] = Field(default_factory=list)
    enable_schemas: bool = Field(True, description="Enable lakehouse schemas feature")
    sql_endpoint_enabled: bool = True


class NotebookResource(BaseModel):
    """Notebook resource definition."""
    path: str = Field(..., description="Local path to notebook file (.py, .ipynb)")
    description: str | None = None
    environment: str | None = Field(None, description="Reference to an environment resource key")
    default_lakehouse: str | None = Field(None, description="Reference to a lakehouse resource key")
    spark_properties: dict[str, str] = Field(default_factory=dict)


class PipelineSchedule(BaseModel):
    """Pipeline schedule configuration."""
    frequency: ScheduleFrequency = ScheduleFrequency.DAILY
    cron: str | None = Field(None, description="Cron expression (when frequency=cron)")
    timezone: str = "UTC"
    start_time: str | None = None
    enabled: bool = True


class PipelineActivity(BaseModel):
    """A single activity within a pipeline."""
    name: str | None = None
    notebook: str | None = Field(None, description="Reference to a notebook resource key")
    pipeline: str | None = Field(None, description="Reference to another pipeline resource key")
    depends_on: list[str] = Field(default_factory=list, description="Activity dependencies")
    parameters: dict[str, Any] = Field(default_factory=dict)


class PipelineResource(BaseModel):
    """Pipeline / Data Pipeline resource definition."""
    path: str | None = Field(None, description="Local path to pipeline JSON definition")
    description: str | None = None
    schedule: PipelineSchedule | None = None
    activities: list[PipelineActivity] = Field(default_factory=list)


class WarehouseResource(BaseModel):
    """Fabric Warehouse resource definition."""
    description: str | None = None
    sql_scripts: list[str] = Field(default_factory=list, description="Paths to SQL scripts to execute on deploy")


class SemanticModelResource(BaseModel):
    """Semantic model (Power BI dataset) resource definition."""
    path: str = Field(..., description="Path to semantic model definition directory")
    description: str | None = None
    default_lakehouse: str | None = None


class ReportResource(BaseModel):
    """Power BI report resource definition."""
    path: str = Field(..., description="Path to .pbir or report definition")
    description: str | None = None
    semantic_model: str | None = Field(None, description="Reference to a semantic_model resource key")


class DataAgentInstructions(BaseModel):
    """Data Agent grounding and configuration."""
    sources: list[str] = Field(default_factory=list, description="Resource keys for lakehouses/warehouses/semantic models")
    instructions: str | None = Field(None, description="Path to instructions markdown file")
    few_shot_examples: str | None = Field(None, description="Path to few-shot examples YAML")
    tables_in_scope: list[str] = Field(default_factory=list)
    description: str | None = None


class EnvironmentResource(BaseModel):
    """Fabric Environment resource definition."""
    runtime: str = Field("1.3", description="Spark runtime version")
    libraries: list[str] = Field(default_factory=list, description="PyPI packages to install")
    conda_dependencies: list[str] = Field(default_factory=list)
    spark_properties: dict[str, str] = Field(default_factory=dict)
    description: str | None = None


class EventhouseResource(BaseModel):
    """Eventhouse (KQL database) resource definition."""
    description: str | None = None
    kql_scripts: list[str] = Field(default_factory=list, description="Paths to KQL scripts")
    retention_days: int | None = None
    cache_days: int | None = None


class EventstreamResource(BaseModel):
    """Eventstream resource definition."""
    description: str | None = None
    path: str | None = Field(None, description="Path to eventstream definition JSON")
    sources: list[dict[str, Any]] = Field(default_factory=list)
    destinations: list[dict[str, Any]] = Field(default_factory=list)


class MLModelResource(BaseModel):
    """ML Model resource definition."""
    path: str = Field(..., description="Path to model definition or MLflow model URI")
    description: str | None = None
    framework: str | None = None


class MLExperimentResource(BaseModel):
    """ML Experiment resource definition."""
    description: str | None = None
    path: str | None = None


# ---------------------------------------------------------------------------
# Sub-models: Security
# ---------------------------------------------------------------------------

class OneLakeRoleBinding(BaseModel):
    """OneLake security role binding."""
    tables: list[str] = Field(default_factory=list)
    folders: list[str] = Field(default_factory=list)
    permissions: list[OneLakePermission] = Field(default_factory=list)


class SecurityRole(BaseModel):
    """Security role definition."""
    name: str
    entra_group: str | None = Field(None, description="Entra ID group name or object ID")
    entra_user: str | None = Field(None, description="Entra ID user UPN")
    service_principal: str | None = Field(None, description="Service principal name or app ID")
    workspace_role: WorkspaceRole = WorkspaceRole.VIEWER
    onelake_roles: list[OneLakeRoleBinding] = Field(default_factory=list)


class SecurityConfig(BaseModel):
    """Security configuration."""
    roles: list[SecurityRole] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Sub-models: Connections
# ---------------------------------------------------------------------------

class ConnectionConfig(BaseModel):
    """Connection / data source configuration."""
    type: ConnectionType
    endpoint: str | None = None
    database: str | None = None
    auth_method: str | None = Field(None, description="Authentication method")
    connection_string_var: str | None = Field(None, description="Environment variable containing connection string")
    properties: dict[str, str] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Sub-models: Variables & Targets
# ---------------------------------------------------------------------------

class VariableDefinition(BaseModel):
    """Variable with optional default value."""
    description: str | None = None
    default: str | None = None


class RunAsConfig(BaseModel):
    """Run-as identity for a target."""
    service_principal: str | None = None
    user_name: str | None = None


class TargetConfig(BaseModel):
    """Environment target (dev, staging, prod)."""
    default: bool = False
    workspace: WorkspaceConfig | None = None
    variables: dict[str, str] = Field(default_factory=dict)
    run_as: RunAsConfig | None = None
    security: SecurityConfig | None = None
    resources: ResourceOverrides | None = None


class ResourceOverrides(BaseModel):
    """Per-target resource overrides."""
    lakehouses: dict[str, dict[str, Any]] = Field(default_factory=dict)
    notebooks: dict[str, dict[str, Any]] = Field(default_factory=dict)
    pipelines: dict[str, dict[str, Any]] = Field(default_factory=dict)
    warehouses: dict[str, dict[str, Any]] = Field(default_factory=dict)
    semantic_models: dict[str, dict[str, Any]] = Field(default_factory=dict)
    reports: dict[str, dict[str, Any]] = Field(default_factory=dict)
    data_agents: dict[str, dict[str, Any]] = Field(default_factory=dict)
    environments: dict[str, dict[str, Any]] = Field(default_factory=dict)
    eventhouses: dict[str, dict[str, Any]] = Field(default_factory=dict)
    eventstreams: dict[str, dict[str, Any]] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Resources container
# ---------------------------------------------------------------------------

class ResourcesConfig(BaseModel):
    """All resource definitions in the bundle."""
    lakehouses: dict[str, LakehouseResource] = Field(default_factory=dict)
    notebooks: dict[str, NotebookResource] = Field(default_factory=dict)
    pipelines: dict[str, PipelineResource] = Field(default_factory=dict)
    warehouses: dict[str, WarehouseResource] = Field(default_factory=dict)
    semantic_models: dict[str, SemanticModelResource] = Field(default_factory=dict)
    reports: dict[str, ReportResource] = Field(default_factory=dict)
    data_agents: dict[str, DataAgentInstructions] = Field(default_factory=dict)
    environments: dict[str, EnvironmentResource] = Field(default_factory=dict)
    eventhouses: dict[str, EventhouseResource] = Field(default_factory=dict)
    eventstreams: dict[str, EventstreamResource] = Field(default_factory=dict)
    ml_models: dict[str, MLModelResource] = Field(default_factory=dict)
    ml_experiments: dict[str, MLExperimentResource] = Field(default_factory=dict)

    def all_resource_keys(self) -> set[str]:
        """Return all resource keys across all types."""
        keys: set[str] = set()
        for field_name in type(self).model_fields:
            resource_dict = getattr(self, field_name)
            if isinstance(resource_dict, dict):
                keys.update(resource_dict.keys())
        return keys

    def get_resource_type(self, key: str) -> str | None:
        """Return the resource type name for a given key."""
        for field_name in type(self).model_fields:
            resource_dict = getattr(self, field_name)
            if isinstance(resource_dict, dict) and key in resource_dict:
                return field_name
        return None


# ---------------------------------------------------------------------------
# Include support
# ---------------------------------------------------------------------------

class IncludeConfig(BaseModel):
    """Include additional YAML files into the bundle definition."""
    paths: list[str] = Field(default_factory=list, description="Glob patterns or paths to include")


# ---------------------------------------------------------------------------
# Root model: BundleDefinition
# ---------------------------------------------------------------------------

class BundleMetadata(BaseModel):
    """Top-level bundle metadata."""
    name: str = Field(..., description="Bundle name (used as identifier)")
    version: str = Field("0.1.0", description="Bundle version")
    description: str | None = None


class BundleDefinition(BaseModel):
    """
    Root model for a fabric.yml bundle definition.

    This is the single declarative project definition for a Microsoft Fabric
    project — analogous to databricks.yml for Databricks Asset Bundles.
    """

    bundle: BundleMetadata
    workspace: WorkspaceConfig = Field(default_factory=WorkspaceConfig)
    include: list[str] = Field(default_factory=list, description="Additional YAML files to merge")
    variables: dict[str, VariableDefinition | str] = Field(default_factory=dict)
    resources: ResourcesConfig = Field(default_factory=ResourcesConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    connections: dict[str, ConnectionConfig] = Field(default_factory=dict)
    targets: dict[str, TargetConfig] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_references(self) -> "BundleDefinition":
        """Validate that cross-resource references are valid."""
        all_keys = self.resources.all_resource_keys()
        errors: list[str] = []

        # Validate notebook -> environment references
        for key, nb in self.resources.notebooks.items():
            if nb.environment and nb.environment not in self.resources.environments:
                errors.append(f"Notebook '{key}' references unknown environment '{nb.environment}'")
            if nb.default_lakehouse and nb.default_lakehouse not in self.resources.lakehouses:
                errors.append(f"Notebook '{key}' references unknown lakehouse '{nb.default_lakehouse}'")

        # Validate report -> semantic_model references
        for key, report in self.resources.reports.items():
            if report.semantic_model and report.semantic_model not in self.resources.semantic_models:
                errors.append(f"Report '{key}' references unknown semantic model '{report.semantic_model}'")

        # Validate data_agent -> source references
        for key, agent in self.resources.data_agents.items():
            for src in agent.sources:
                if src not in all_keys:
                    errors.append(f"Data Agent '{key}' references unknown source '{src}'")

        # Validate pipeline activity -> notebook/pipeline references
        for key, pipeline in self.resources.pipelines.items():
            for activity in pipeline.activities:
                if activity.notebook and activity.notebook not in self.resources.notebooks:
                    errors.append(
                        f"Pipeline '{key}' activity references unknown notebook '{activity.notebook}'"
                    )
                if activity.pipeline and activity.pipeline not in self.resources.pipelines:
                    errors.append(
                        f"Pipeline '{key}' activity references unknown pipeline '{activity.pipeline}'"
                    )

        if errors:
            raise ValueError("Bundle validation errors:\n  " + "\n  ".join(errors))

        return self

    def resolve_target(self, target_name: str | None = None) -> TargetConfig:
        """Resolve the target config, falling back to default."""
        if target_name:
            if target_name not in self.targets:
                raise ValueError(f"Unknown target '{target_name}'. Available: {list(self.targets.keys())}")
            return self.targets[target_name]

        # Find default target
        for name, target in self.targets.items():
            if target.default:
                return target

        # No default, return empty config
        return TargetConfig()

    def get_effective_workspace(self, target_name: str | None = None) -> WorkspaceConfig:
        """Get the effective workspace config for a target (merged with base)."""
        target = self.resolve_target(target_name)
        base = self.workspace

        if target.workspace:
            return WorkspaceConfig(
                name=target.workspace.name or base.name,
                workspace_id=target.workspace.workspace_id or base.workspace_id,
                capacity=target.workspace.capacity or base.capacity,
                description=target.workspace.description or base.description,
                git_integration=target.workspace.git_integration or base.git_integration,
            )
        return base

    def resolve_variables(self, target_name: str | None = None) -> dict[str, str]:
        """Resolve variables with target overrides applied."""
        resolved: dict[str, str] = {}

        # Start with base variable defaults
        for key, val in self.variables.items():
            if isinstance(val, str):
                resolved[key] = val
            elif isinstance(val, VariableDefinition) and val.default:
                resolved[key] = val.default

        # Apply target overrides
        target = self.resolve_target(target_name)
        resolved.update(target.variables)

        return resolved
