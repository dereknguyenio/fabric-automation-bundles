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
    capacity_id: str | None = Field(None, description="Fabric capacity GUID (from admin portal)")
    capacity: str | None = Field(None, description="Deprecated: use capacity_id instead")
    description: str | None = None
    git_integration: GitIntegrationConfig | None = None

    @property
    def effective_capacity_id(self) -> str | None:
        """Return capacity_id, falling back to capacity for backwards compat."""
        return self.capacity_id or self.capacity


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

class ShortcutTransformation(BaseModel):
    """Shortcut transformation — auto-converts files to Delta tables."""
    type: str = Field("file", description="Transformation type: file, ai")
    source_format: str | None = Field(None, description="Source format: csv, parquet, json, excel")
    destination_table: str | None = Field(None, description="Target Delta table name")
    sync: bool = Field(True, description="Keep in sync with source (always-on)")
    # AI-powered transformation options
    ai_skill: str | None = Field(None, description="AI skill: summarize, translate, classify")
    ai_model: str | None = Field(None, description="AI model to use for transformation")
    ai_prompt: str | None = Field(None, description="Custom prompt for AI transformation")
    # File transformation options
    flatten: bool = Field(False, description="Deep flatten nested JSON/Parquet")
    compression: str | None = Field(None, description="Source compression: gzip, snappy, zstd")


class ShortcutConfig(BaseModel):
    """OneLake shortcut definition."""
    name: str
    target: str = Field(..., description="Target path (adls://, s3://, onelake://)")
    path: str = Field("Tables", description="Shortcut location in lakehouse (Tables or Files)")
    connection_id: str | None = Field(None, description="Connection ID for authenticated shortcuts")
    transformation: ShortcutTransformation | None = Field(None, description="Auto-transform files to Delta tables")


class TableSchema(BaseModel):
    """Delta table schema definition."""
    schema_path: str | None = Field(None, description="Path to JSON schema file")
    partition_by: list[str] = Field(default_factory=list)
    description: str | None = None


class LakehouseResource(BaseModel):
    """Lakehouse resource definition."""
    description: str | None = None
    schemas: list[str] = Field(default_factory=list, description="Paths to JSON schema files")
    shortcuts: list[ShortcutConfig] = Field(default_factory=list)
    enable_schemas: bool = Field(True, description="Enable lakehouse schemas feature")
    sql_endpoint_enabled: bool = True
    tables: dict[str, TableSchema] = Field(default_factory=dict, description="Delta table definitions")


class NotebookResource(BaseModel):
    """Notebook resource definition."""
    path: str = Field(..., description="Local path to notebook file (.py, .ipynb)")
    description: str | None = None
    environment: str | None = Field(None, description="Reference to an environment resource key")
    default_lakehouse: str | None = Field(None, description="Reference to a lakehouse resource key")
    external_lakehouse: str | None = Field(None, description="Cross-workspace lakehouse ref (workspace://ws-name/item)")
    spark_properties: dict[str, str] = Field(default_factory=dict)
    parameters: dict[str, Any] = Field(default_factory=dict, description="Default parameters for notebook execution")
    folder: str | None = Field(None, description="Workspace folder path (e.g., 'ETL/Bronze')")


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
    folder: str | None = Field(None, description="Workspace folder path (e.g., 'ETL/Bronze')")


class WarehouseResource(BaseModel):
    """Fabric Warehouse resource definition."""
    description: str | None = None
    sql_scripts: list[str] = Field(default_factory=list, description="Paths to SQL scripts to execute on deploy")
    folder: str | None = Field(None, description="Workspace folder path (e.g., 'ETL/Bronze')")


class SemanticModelResource(BaseModel):
    """Semantic model (Power BI dataset) resource definition."""
    path: str = Field(..., description="Path to semantic model definition directory")
    description: str | None = None
    default_lakehouse: str | None = None
    auto_refresh: bool = Field(False, description="Auto-refresh after deploy")
    refresh_timeout: int = Field(600, description="Refresh timeout in seconds")
    after_deploy: list[str] = Field(default_factory=list, description="Actions to run after deploy (e.g., 'refresh')")
    depends_on_run: list[str] = Field(default_factory=list, description="Only refresh if these resources ran successfully")
    folder: str | None = Field(None, description="Workspace folder path (e.g., 'ETL/Bronze')")


class ReportResource(BaseModel):
    """Power BI report resource definition."""
    path: str = Field(..., description="Path to .pbir or report definition")
    description: str | None = None
    semantic_model: str | None = Field(None, description="Reference to a semantic_model resource key")
    external_semantic_model: str | None = Field(None, description="Cross-workspace model ref (workspace://ws-name/item)")
    folder: str | None = Field(None, description="Workspace folder path (e.g., 'ETL/Bronze')")


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
    path: str | None = Field(None, description="Path to model definition or MLflow model URI")
    description: str | None = None
    framework: str | None = None


class MLExperimentResource(BaseModel):
    """ML Experiment resource definition."""
    description: str | None = None
    path: str | None = None


class KQLDatabaseResource(BaseModel):
    """KQL Database resource definition."""
    description: str | None = None
    parent_eventhouse: str | None = Field(None, description="Parent eventhouse resource key")
    kql_scripts: list[str] = Field(default_factory=list, description="Paths to KQL scripts to execute")


class KQLDashboardResource(BaseModel):
    """KQL Dashboard resource definition."""
    description: str | None = None
    path: str | None = Field(None, description="Path to dashboard definition")
    data_source: str | None = Field(None, description="KQL database or eventhouse resource key")


class KQLQuerysetResource(BaseModel):
    """KQL Queryset resource definition."""
    description: str | None = None
    path: str | None = Field(None, description="Path to queryset definition")
    data_source: str | None = Field(None, description="KQL database resource key")


class DataflowResource(BaseModel):
    """Dataflow Gen2 resource definition."""
    description: str | None = None
    path: str | None = Field(None, description="Path to dataflow definition JSON")


class GraphQLApiResource(BaseModel):
    """GraphQL API resource definition."""
    description: str | None = None
    path: str | None = Field(None, description="Path to GraphQL schema file")
    data_source: str | None = Field(None, description="Lakehouse or warehouse resource key")


class SparkJobDefinitionResource(BaseModel):
    """Spark Job Definition resource definition."""
    description: str | None = None
    path: str | None = Field(None, description="Path to Spark job main file (.py, .jar)")
    environment: str | None = Field(None, description="Environment resource key")
    default_lakehouse: str | None = None
    args: list[str] = Field(default_factory=list, description="Command-line arguments")
    conf: dict[str, str] = Field(default_factory=dict, description="Spark configuration overrides")


class SQLDatabaseResource(BaseModel):
    """SQL Database resource definition."""
    description: str | None = None
    sql_scripts: list[str] = Field(default_factory=list, description="Paths to SQL scripts")


class MirroredDatabaseResource(BaseModel):
    """Mirrored Database resource definition."""
    description: str | None = None
    source_type: str | None = Field(None, description="Source database type (e.g., Azure SQL, Cosmos DB)")
    connection: str | None = Field(None, description="Connection resource key")


class CopyJobResource(BaseModel):
    """Copy Job resource definition."""
    description: str | None = None
    path: str | None = Field(None, description="Path to copy job definition JSON")


class ApacheAirflowJobResource(BaseModel):
    """Apache Airflow Job resource definition."""
    description: str | None = None
    path: str | None = Field(None, description="Path to DAG definition file")


class ReflexResource(BaseModel):
    """Reflex (Data Activator) resource definition."""
    description: str | None = None
    path: str | None = Field(None, description="Path to Reflex definition")


class MountedDataFactoryResource(BaseModel):
    """Mounted Data Factory resource definition."""
    description: str | None = None
    data_factory_id: str | None = Field(None, description="Azure Data Factory resource ID")


class UserDataFunctionResource(BaseModel):
    """User Data Function resource definition."""
    description: str | None = None
    path: str | None = Field(None, description="Path to function definition")
    runtime: str | None = Field(None, description="Function runtime (e.g., python, dotnet)")


class VariableLibraryResource(BaseModel):
    """Variable Library resource definition."""
    description: str | None = None
    variables: dict[str, str] = Field(default_factory=dict, description="Library variables")


class OntologyResource(BaseModel):
    """Fabric Ontology (knowledge graph) resource definition."""
    description: str | None = None
    path: str | None = Field(None, description="Path to ontology definition")
    data_sources: list[str] = Field(default_factory=list, description="Lakehouse/warehouse resource keys")


class GraphResource(BaseModel):
    """Fabric Graph resource definition."""
    description: str | None = None
    path: str | None = Field(None, description="Path to graph definition")
    data_source: str | None = Field(None, description="Lakehouse or SQL database resource key")


class DataBuildToolJobResource(BaseModel):
    """dbt job resource definition."""
    description: str | None = None
    path: str | None = Field(None, description="Path to dbt project or job definition")
    environment: str | None = Field(None, description="Environment resource key")


class DatamartResource(BaseModel):
    """Datamart resource definition."""
    description: str | None = None
    path: str | None = Field(None, description="Path to datamart definition")


class PaginatedReportResource(BaseModel):
    """Paginated Report (RDL) resource definition."""
    description: str | None = None
    path: str | None = Field(None, description="Path to .rdl report definition")
    data_source: str | None = Field(None, description="Data source resource key")


class DashboardResource(BaseModel):
    """Power BI Dashboard resource definition."""
    description: str | None = None


class MirroredWarehouseResource(BaseModel):
    """Mirrored Warehouse resource definition."""
    description: str | None = None
    source_type: str | None = None


class SnowflakeDatabaseResource(BaseModel):
    """Snowflake Database resource definition."""
    description: str | None = None
    connection: str | None = Field(None, description="Connection resource key")


class CosmosDBDatabaseResource(BaseModel):
    """Cosmos DB Database resource definition."""
    description: str | None = None
    connection: str | None = Field(None, description="Connection resource key")


class MirroredDatabricksCatalogResource(BaseModel):
    """Mirrored Azure Databricks Catalog resource definition."""
    description: str | None = None
    connection: str | None = Field(None, description="Connection resource key")


class OperationsAgentResource(BaseModel):
    """Operations Agent resource definition."""
    description: str | None = None
    sources: list[str] = Field(default_factory=list, description="Data source resource keys")
    instructions: str | None = Field(None, description="Path to instructions file")


class AnomalyDetectorResource(BaseModel):
    """Anomaly Detector resource definition."""
    description: str | None = None
    data_source: str | None = Field(None, description="Data source resource key")
    path: str | None = Field(None, description="Path to detector configuration")


class DigitalTwinBuilderResource(BaseModel):
    """Digital Twin Builder resource definition."""
    description: str | None = None
    path: str | None = Field(None, description="Path to twin definition")


class DigitalTwinBuilderFlowResource(BaseModel):
    """Digital Twin Builder Flow resource definition."""
    description: str | None = None
    path: str | None = Field(None, description="Path to flow definition")
    twin_builder: str | None = Field(None, description="Digital twin builder resource key")


class EventSchemaSetResource(BaseModel):
    """Event Schema Set resource definition."""
    description: str | None = None
    path: str | None = Field(None, description="Path to schema set definition")


class GraphQuerySetResource(BaseModel):
    """Graph Query Set resource definition."""
    description: str | None = None
    path: str | None = Field(None, description="Path to query set definition")
    data_source: str | None = Field(None, description="Graph or KQL database resource key")


class MapResource(BaseModel):
    """Map resource definition."""
    description: str | None = None
    path: str | None = Field(None, description="Path to map definition")


class GraphModelResource(BaseModel):
    """Graph Model resource definition."""
    description: str | None = None
    path: str | None = Field(None, description="Path to graph model definition")
    data_source: str | None = Field(None, description="Data source resource key")


class HLSCohortResource(BaseModel):
    """HLS Cohort (Healthcare) resource definition."""
    description: str | None = None
    path: str | None = Field(None, description="Path to cohort definition")


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


class ValidationCheck(BaseModel):
    """Post-deploy validation check."""
    run: str | None = Field(None, description="Resource name to run")
    sql: str | None = Field(None, description="SQL query to execute")
    expect: str | None = Field(None, description="Expected result (e.g., 'success', '> 0')")
    timeout: int = Field(300, description="Timeout in seconds")


class DeploymentStrategy(BaseModel):
    """Deployment strategy configuration."""
    type: str = Field("all-at-once", description="Deployment strategy: all-at-once, canary")
    canary_resources: list[str] = Field(default_factory=list, description="Resources to deploy first in canary")
    validation: ValidationCheck | None = None


class TargetConfig(BaseModel):
    """Environment target (dev, staging, prod)."""
    default: bool = False
    workspace: WorkspaceConfig | None = None
    variables: dict[str, str] = Field(default_factory=dict)
    run_as: RunAsConfig | None = None
    security: SecurityConfig | None = None
    resources: ResourceOverrides | None = None
    post_deploy: list[ValidationCheck] = Field(default_factory=list, description="Post-deploy validation checks")
    deployment_strategy: DeploymentStrategy | None = None


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
    kql_databases: dict[str, KQLDatabaseResource] = Field(default_factory=dict)
    kql_dashboards: dict[str, KQLDashboardResource] = Field(default_factory=dict)
    kql_querysets: dict[str, KQLQuerysetResource] = Field(default_factory=dict)
    dataflows: dict[str, DataflowResource] = Field(default_factory=dict)
    graphql_apis: dict[str, GraphQLApiResource] = Field(default_factory=dict)
    spark_job_definitions: dict[str, SparkJobDefinitionResource] = Field(default_factory=dict)
    sql_databases: dict[str, SQLDatabaseResource] = Field(default_factory=dict)
    mirrored_databases: dict[str, MirroredDatabaseResource] = Field(default_factory=dict)
    copy_jobs: dict[str, CopyJobResource] = Field(default_factory=dict)
    airflow_jobs: dict[str, ApacheAirflowJobResource] = Field(default_factory=dict)
    reflex: dict[str, ReflexResource] = Field(default_factory=dict)
    mounted_data_factories: dict[str, MountedDataFactoryResource] = Field(default_factory=dict)
    user_data_functions: dict[str, UserDataFunctionResource] = Field(default_factory=dict)
    variable_libraries: dict[str, VariableLibraryResource] = Field(default_factory=dict)
    ontologies: dict[str, OntologyResource] = Field(default_factory=dict)
    graphs: dict[str, GraphResource] = Field(default_factory=dict)
    dbt_jobs: dict[str, DataBuildToolJobResource] = Field(default_factory=dict)
    # Note: These types are list-only in the Fabric API — they can be listed
    # but not created/updated/deleted programmatically
    datamarts: dict[str, DatamartResource] = Field(default_factory=dict)
    paginated_reports: dict[str, PaginatedReportResource] = Field(default_factory=dict)
    dashboards: dict[str, DashboardResource] = Field(default_factory=dict)
    mirrored_warehouses: dict[str, MirroredWarehouseResource] = Field(default_factory=dict)
    snowflake_databases: dict[str, SnowflakeDatabaseResource] = Field(default_factory=dict)
    cosmosdb_databases: dict[str, CosmosDBDatabaseResource] = Field(default_factory=dict)
    mirrored_databricks_catalogs: dict[str, MirroredDatabricksCatalogResource] = Field(default_factory=dict)
    operations_agents: dict[str, OperationsAgentResource] = Field(default_factory=dict)
    anomaly_detectors: dict[str, AnomalyDetectorResource] = Field(default_factory=dict)
    digital_twin_builders: dict[str, DigitalTwinBuilderResource] = Field(default_factory=dict)
    digital_twin_builder_flows: dict[str, DigitalTwinBuilderFlowResource] = Field(default_factory=dict)
    event_schema_sets: dict[str, EventSchemaSetResource] = Field(default_factory=dict)
    graph_query_sets: dict[str, GraphQuerySetResource] = Field(default_factory=dict)
    map_items: dict[str, MapResource] = Field(default_factory=dict)
    graph_models: dict[str, GraphModelResource] = Field(default_factory=dict)
    hls_cohorts: dict[str, HLSCohortResource] = Field(default_factory=dict)

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

    def validate_resource_names(self) -> list[str]:
        """Validate resource names follow Fabric naming rules per item type. Returns list of warnings."""
        warnings: list[str] = []
        # Lakehouses, warehouses: no hyphens, no spaces, no special chars except underscore
        strict_name_types = {"lakehouses", "warehouses", "eventhouses", "sql_databases", "kql_databases"}
        # All types: max 256 chars, no leading/trailing spaces
        import re
        strict_pattern = re.compile(r'^[a-zA-Z0-9_]+$')
        general_pattern = re.compile(r'^[a-zA-Z0-9_ -]+$')

        for field_name in type(self).model_fields:
            resource_dict = getattr(self, field_name)
            if not isinstance(resource_dict, dict):
                continue
            for key in resource_dict:
                if len(key) > 256:
                    warnings.append(f"'{key}' exceeds 256 character limit")
                if key != key.strip():
                    warnings.append(f"'{key}' has leading/trailing whitespace")
                if field_name in strict_name_types:
                    if not strict_pattern.match(key):
                        warnings.append(
                            f"'{key}' ({field_name}): only letters, numbers, and underscores allowed. "
                            f"Hyphens and spaces are not supported."
                        )
                else:
                    if not general_pattern.match(key):
                        warnings.append(f"'{key}' ({field_name}): contains invalid characters")
        return warnings


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
    depends_on: list[str] = Field(default_factory=list, description="Paths to dependent bundle files")


class NotificationConfig(BaseModel):
    """Notification configuration."""
    type: str = Field(..., description="Notification type: slack, teams")
    webhook: str = Field(..., description="Webhook URL (use ${secret.WEBHOOK} for secrets)")
    message: str = Field("Deployed {bundle.name} v{bundle.version} to {target}", description="Message template")


class NotificationsConfig(BaseModel):
    """Notifications configuration."""
    on_success: list[NotificationConfig] = Field(default_factory=list)
    on_failure: list[NotificationConfig] = Field(default_factory=list)


class PolicyRule(BaseModel):
    """A single policy rule for validation."""
    name: str
    check: str = Field(..., description="Policy check type: require_description, naming_convention, max_resources, etc.")
    value: Any = None
    severity: str = Field("error", description="error or warning")


class PolicyConfig(BaseModel):
    """Policy enforcement configuration."""
    rules: list[PolicyRule] = Field(default_factory=list)
    require_description: bool = False
    naming_convention: str | None = Field(None, description="snake_case, camelCase, etc.")
    max_notebook_size_kb: int | None = None
    blocked_libraries: list[str] = Field(default_factory=list)


class BundleDefinition(BaseModel):
    """
    Root model for a fabric.yml bundle definition.

    This is the single declarative project definition for a Microsoft Fabric
    project — analogous to databricks.yml for Databricks Asset Bundles.
    """

    bundle: BundleMetadata
    workspace: WorkspaceConfig = Field(default_factory=WorkspaceConfig)
    include: list[str] = Field(default_factory=list, description="Additional YAML files to merge")
    extends: str | None = Field(None, description="Path to parent bundle to inherit from")
    variables: dict[str, VariableDefinition | str] = Field(default_factory=dict)
    resources: ResourcesConfig = Field(default_factory=ResourcesConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    connections: dict[str, ConnectionConfig] = Field(default_factory=dict)
    policies: PolicyConfig = Field(default_factory=PolicyConfig)
    notifications: NotificationsConfig = Field(default_factory=NotificationsConfig)
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

        # Validate resource names
        name_warnings = self.resources.validate_resource_names()
        if name_warnings:
            raise ValueError("Resource naming errors:\n  " + "\n  ".join(name_warnings))

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
                capacity_id=target.workspace.capacity_id or base.capacity_id,
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
