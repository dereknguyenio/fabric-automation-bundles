# fabric.yml reference

The `fabric.yml` file is the single declarative definition for a Microsoft Fabric project. It defines every resource, environment target, security role, connection, and policy for your project in one file (or split across multiple files using `include`).

This topic provides a complete reference for every top-level key, field, type, default value, and validation rule in the `fabric.yml` schema.

---

## File structure overview

```yaml
bundle:          # Required. Project metadata.
workspace:       # Default workspace configuration.
variables:       # Variable definitions with optional defaults.
resources:       # All Fabric resource definitions (45 types).
security:        # Workspace and OneLake role assignments.
connections:     # Data source connection definitions.
policies:        # Validation and governance rules.
notifications:   # Deployment notification hooks.
state:           # Remote state backend configuration.
targets:         # Environment-specific overrides (dev, staging, prod).
include:         # Additional YAML files to merge into the bundle.
extends:         # Parent bundle to inherit from.
```

> **Note**
>
> Only the `bundle` key (with its `name` field) is required. All other top-level keys are optional.

---

## JSON Schema validation

A JSON Schema file is provided at the repository root for editor autocompletion and validation:

```yaml
# yaml-language-server: $schema=../../fabric.schema.json
bundle:
  name: my-project
```

---

## bundle

Project metadata and identity. This is the only required top-level key.

### Fields

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `name` | String | **Yes** | | Unique identifier for the bundle. Used in state files, deployment history, and destroy confirmations. |
| `version` | String | No | `"0.1.0"` | Semantic version string. Recorded in deployment state and history. |
| `description` | String | No | | Human-readable description of the project. |
| `depends_on` | List of strings | No | `[]` | Paths to other `fabric.yml` files that this bundle depends on. Used for cross-bundle dependency resolution. |

### Example

```yaml
bundle:
  name: sales-analytics
  version: "2.1.0"
  description: "End-to-end sales analytics pipeline with medallion architecture"
  depends_on:
    - ../shared-infrastructure/fabric.yml
    - ../data-platform/fabric.yml
```

> **Important**
>
> The `name` field is used as a confirmation prompt during `fab-bundle destroy`. Choose a descriptive, unique name. Changing the name after initial deployment creates a new state track.

---

## workspace

Default workspace configuration. Targets can override these values.

### Fields

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `name` | String | No | | Workspace display name. If the workspace does not exist, `deploy` creates it. |
| `workspace_id` | String | No | | GUID of an existing workspace to deploy into. If set, `name` is used for display only. |
| `capacity_id` | String | No | | Fabric capacity GUID. Required when creating a new workspace. Must be a valid GUID format (`xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`) or a variable reference (`${var.capacity_id}`). |
| `capacity` | String | No | | **Deprecated.** Use `capacity_id` instead. |
| `description` | String | No | | Workspace description. |
| `git_integration` | Object | No | | Git integration settings for the workspace. See [git_integration](#git_integration). |

### Example

```yaml
workspace:
  name: sales-analytics-dev
  capacity_id: "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
  description: "Development workspace for the sales analytics team"
  git_integration:
    provider: github
    organization: my-org
    repository: sales-analytics
    branch: main
    directory: /
```

> **Warning**
>
> If you provide both `workspace_id` and `name`, the `workspace_id` takes precedence. The tool deploys to the workspace identified by the GUID, regardless of the `name` value.

### git_integration

Git integration settings that connect the workspace to a source control repository.

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `provider` | String | No | `"azuredevops"` | Git provider: `azuredevops` or `github`. |
| `organization` | String | No | | GitHub organization or Azure DevOps organization name. |
| `project` | String | No | | Azure DevOps project name. Not used for GitHub. |
| `repository` | String | No | | Repository name. |
| `branch` | String | No | `"main"` | Branch to sync with. |
| `directory` | String | No | `"/"` | Root directory in the repository for Fabric items. |

### Example

```yaml
workspace:
  git_integration:
    provider: azuredevops
    organization: contoso
    project: data-platform
    repository: fabric-items
    branch: main
    directory: /workspace
```

---

## variables

Variable definitions with optional descriptions and default values. Variables can be referenced anywhere in the bundle using `${var.variable_name}` syntax.

### Field formats

Variables support two definition formats:

**Short form** (string value as default):

```yaml
variables:
  environment: "development"
  region: "eastus2"
```

**Long form** (with description and optional default):

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `description` | String | No | | Human-readable description of the variable. |
| `default` | String | No | | Default value. If no default is set and no target override provides a value, `--strict` validation fails. |

```yaml
variables:
  source_connection:
    description: "Connection string for the source database"
    default: "Server=dev-server;Database=sales"
  capacity_id:
    description: "Fabric capacity GUID"
  environment:
    description: "Deployment environment name"
    default: "dev"
```

### Variable resolution order

Variables are resolved in the following order (highest priority first):

1. Target-specific `variables` overrides.
2. Variable `default` value from the top-level `variables` section.
3. Environment variables (for `${env.VAR_NAME}` syntax).
4. Azure Key Vault secrets (for `${secret.SECRET_NAME}` syntax, requires the `keyvault` extra).

### Examples

**Referencing variables in the bundle:**

```yaml
variables:
  lakehouse_name:
    description: "Name of the primary lakehouse"
    default: "bronze_lake"

resources:
  lakehouses:
    ${var.lakehouse_name}:
      description: "Primary ingestion lakehouse"
```

**Using secrets:**

```yaml
notifications:
  on_success:
    - type: slack
      webhook: "${secret.SLACK_WEBHOOK_URL}"
      message: "Deployed ${bundle.name} v${bundle.version}"
```

> **Important**
>
> Variables using `${secret.*}` syntax require the `keyvault` extra (`pip install fabric-automation-bundles[keyvault]`) and a configured Azure Key Vault.

---

## resources

All Fabric resource definitions organized by type. Each resource type is a dictionary where keys are the resource display names and values define the resource configuration.

### Supported resource types (45 types)

The following table lists every supported resource type. Click a type name for details in the [resource type reference](../reference/resource-types.md).

| Category | Resource type key | Description |
|---|---|---|
| **Data Engineering** | `lakehouses` | Fabric Lakehouse with optional shortcuts and Delta table definitions. |
| | `notebooks` | Spark notebooks (.py, .ipynb). |
| | `environments` | Spark runtime environments with library dependencies. |
| | `spark_job_definitions` | Spark Job Definition resources (.py, .jar). |
| | `pipelines` | Data Pipelines with activities and schedules. |
| | `dataflows` | Dataflow Gen2 definitions. |
| | `copy_jobs` | Copy Job resources. |
| | `airflow_jobs` | Apache Airflow Job (DAG) resources. |
| | `dbt_jobs` | dbt job resources. |
| **Data Warehousing** | `warehouses` | Fabric Warehouse with SQL scripts. |
| | `sql_databases` | SQL Database resources. |
| **Real-Time Intelligence** | `eventhouses` | Eventhouse (KQL database cluster) resources. |
| | `eventstreams` | Eventstream resources. |
| | `kql_databases` | KQL Database resources. |
| | `kql_dashboards` | KQL Dashboard resources. |
| | `kql_querysets` | KQL Queryset resources. |
| | `event_schema_sets` | Event Schema Set resources. |
| **Business Intelligence** | `semantic_models` | Semantic models (Power BI datasets). |
| | `reports` | Power BI reports (.pbir). |
| | `dashboards` | Power BI Dashboard resources. |
| | `paginated_reports` | Paginated reports (.rdl). |
| | `datamarts` | Datamart resources. |
| **AI & Machine Learning** | `data_agents` | Data Agent (AI/NL2SQL) resources. |
| | `ml_models` | ML Model resources. |
| | `ml_experiments` | ML Experiment resources. |
| | `operations_agents` | Operations Agent resources. |
| | `anomaly_detectors` | Anomaly Detector resources. |
| **Data Integration** | `mirrored_databases` | Mirrored Database resources. |
| | `mirrored_warehouses` | Mirrored Warehouse resources. |
| | `snowflake_databases` | Snowflake Database resources. |
| | `cosmosdb_databases` | Cosmos DB Database resources. |
| | `mirrored_databricks_catalogs` | Mirrored Azure Databricks Catalog resources. |
| | `mounted_data_factories` | Mounted Azure Data Factory resources. |
| **Functions & APIs** | `graphql_apis` | GraphQL API resources. |
| | `user_data_functions` | User Data Function resources. |
| **Governance & Management** | `variable_libraries` | Variable Library resources. |
| | `reflex` | Reflex (Data Activator) resources. |
| **Knowledge & Graphs** | `ontologies` | Fabric Ontology (knowledge graph) resources. |
| | `graphs` | Fabric Graph resources. |
| | `graph_query_sets` | Graph Query Set resources. |
| | `graph_models` | Graph Model resources. |
| | `map_items` | Map resources. |
| **IoT & Digital Twin** | `digital_twin_builders` | Digital Twin Builder resources. |
| | `digital_twin_builder_flows` | Digital Twin Builder Flow resources. |
| **Healthcare** | `hls_cohorts` | HLS Cohort (Healthcare) resources. |

### Core resource types in detail

The following sections document the most commonly used resource types.

---

### lakehouses

Fabric Lakehouse resources with optional OneLake shortcuts and Delta table definitions.

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `description` | String | No | | Lakehouse description. |
| `enable_schemas` | Boolean | No | `true` | Enable the lakehouse schemas feature. |
| `sql_endpoint_enabled` | Boolean | No | `true` | Enable the SQL analytics endpoint. |
| `schemas` | List of strings | No | `[]` | Paths to JSON schema files. |
| `shortcuts` | List of [ShortcutConfig](#shortcutconfig) | No | `[]` | OneLake shortcut definitions. |
| `tables` | Map of string to [TableSchema](#tableschema) | No | `{}` | Delta table definitions with schema and partitioning. |

#### ShortcutConfig

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `name` | String | **Yes** | | Shortcut display name. |
| `target` | String | **Yes** | | Target path. Supports `adls://`, `s3://`, `onelake://` protocols. |
| `path` | String | No | `"Tables"` | Shortcut location in lakehouse: `Tables` or `Files`. |
| `connection_id` | String | No | | Connection ID for authenticated shortcuts. |
| `transformation` | Object | No | | Auto-transform files to Delta tables. |

#### TableSchema

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `schema_path` | String | No | | Path to a JSON schema file. |
| `partition_by` | List of strings | No | `[]` | Partition columns. |
| `description` | String | No | | Table description. |

#### Example

```yaml
resources:
  lakehouses:
    bronze_lakehouse:
      description: "Raw data ingestion lakehouse"
      enable_schemas: true
      shortcuts:
        - name: external_sales
          target: "adls://storageaccount.dfs.core.windows.net/container/sales"
          path: Tables
          connection_id: "${var.adls_connection_id}"
          transformation:
            type: file
            source_format: parquet
            destination_table: raw_sales
            sync: true
      tables:
        orders:
          partition_by: [order_date]
          description: "Customer orders"

    gold_lakehouse:
      description: "Curated analytics lakehouse"
```

> **Note**
>
> Lakehouse names support only letters, numbers, and underscores. Hyphens and spaces are not allowed by the Fabric API.

---

### notebooks

Spark notebooks deployed from local `.py` or `.ipynb` files.

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `path` | String | **Yes** | | Local path to the notebook file (`.py` or `.ipynb`), relative to the `fabric.yml` location. |
| `description` | String | No | | Notebook description. |
| `environment` | String | No | | Reference to an `environments` resource key. |
| `default_lakehouse` | String | No | | Reference to a `lakehouses` resource key. Attached as the default lakehouse. |
| `external_lakehouse` | String | No | | Cross-workspace lakehouse reference using `workspace://ws-name/item` syntax. |
| `spark_properties` | Map of string to string | No | `{}` | Spark configuration overrides. |
| `parameters` | Map of string to any | No | `{}` | Default parameters for notebook execution (used by `fab-bundle run`). |
| `folder` | String | No | | Workspace folder path (for example, `ETL/Bronze`). |

#### Example

```yaml
resources:
  notebooks:
    ingest_notebook:
      path: notebooks/ingest.py
      description: "Ingest raw data from external sources"
      environment: spark_env
      default_lakehouse: bronze_lakehouse
      parameters:
        source_path: "/mnt/data/raw"
        batch_size: "1000"
      folder: "ETL/Bronze"

    transform_notebook:
      path: notebooks/transform.ipynb
      description: "Transform bronze to gold"
      environment: spark_env
      default_lakehouse: gold_lakehouse
      spark_properties:
        spark.sql.shuffle.partitions: "200"
      folder: "ETL/Gold"
```

> **Important**
>
> The `environment` and `default_lakehouse` fields must reference resource keys defined in the same bundle. Cross-references are validated at load time. Invalid references cause a validation error.

---

### pipelines

Data Pipelines with optional inline activities and schedules.

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `path` | String | No | | Local path to a pipeline JSON definition file. If provided, the JSON is uploaded as the pipeline definition. |
| `description` | String | No | | Pipeline description. |
| `schedule` | [PipelineSchedule](#pipelineschedule) | No | | Schedule configuration. |
| `activities` | List of [PipelineActivity](#pipelineactivity) | No | `[]` | Inline activity definitions. Used when `path` is not provided. |
| `folder` | String | No | | Workspace folder path. |

#### PipelineSchedule

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `frequency` | Enum | No | `"daily"` | Schedule frequency: `once`, `hourly`, `daily`, `weekly`, `monthly`, `cron`. |
| `cron` | String | No | | Cron expression. Required when `frequency` is `cron`. |
| `timezone` | String | No | `"UTC"` | Timezone for the schedule (for example, `America/New_York`). |
| `start_time` | String | No | | ISO 8601 start time. |
| `enabled` | Boolean | No | `true` | Whether the schedule is active. |

#### PipelineActivity

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `name` | String | No | | Activity display name. |
| `notebook` | String | No | | Reference to a `notebooks` resource key. |
| `pipeline` | String | No | | Reference to another `pipelines` resource key (for chained pipelines). |
| `depends_on` | List of strings | No | `[]` | Activity dependencies (names of other activities in this pipeline). |
| `parameters` | Map of string to any | No | `{}` | Parameters to pass to the notebook or pipeline. |

#### Example

```yaml
resources:
  pipelines:
    daily_pipeline:
      description: "Daily ETL orchestration pipeline"
      schedule:
        frequency: cron
        cron: "0 6 * * *"
        timezone: "America/New_York"
        enabled: true
      activities:
        - name: ingest
          notebook: ingest_notebook
          parameters:
            mode: "incremental"
        - name: transform
          notebook: transform_notebook
          depends_on: [ingest]
        - name: refresh_model
          pipeline: refresh_pipeline
          depends_on: [transform]

    manual_pipeline:
      path: pipelines/manual_pipeline.json
      description: "Ad-hoc data loading pipeline"
```

---

### environments

Spark runtime environments with Python library dependencies and Spark configuration.

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `runtime` | String | No | `"1.3"` | Spark runtime version (`1.2` or `1.3`). |
| `libraries` | List of strings | No | `[]` | PyPI package specifications (for example, `pandas>=2.0`, `great-expectations`). |
| `conda_dependencies` | List of strings | No | `[]` | Conda package specifications. |
| `spark_properties` | Map of string to string | No | `{}` | Spark configuration properties. |
| `description` | String | No | | Environment description. |

#### Example

```yaml
resources:
  environments:
    spark_env:
      description: "Standard Spark environment for ETL"
      runtime: "1.3"
      libraries:
        - great-expectations>=0.18.0
        - delta-spark>=3.0
        - azure-storage-blob
      spark_properties:
        spark.sql.shuffle.partitions: "200"
        spark.databricks.delta.autoCompact.enabled: "true"
```

---

### warehouses

Fabric Warehouse resources with optional SQL scripts executed on deployment.

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `description` | String | No | | Warehouse description. |
| `sql_scripts` | List of strings | No | `[]` | Paths to SQL scripts to execute on deploy. Scripts run in order. |
| `folder` | String | No | | Workspace folder path. |

#### Example

```yaml
resources:
  warehouses:
    analytics_warehouse:
      description: "Central analytics warehouse"
      sql_scripts:
        - sql/create_schemas.sql
        - sql/create_views.sql
        - sql/seed_reference_data.sql
```

> **Note**
>
> Warehouse names support only letters, numbers, and underscores.

---

### semantic_models

Semantic models (Power BI datasets) deployed from local TMDL or BIM definition directories.

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `path` | String | **Yes** | | Path to the semantic model definition directory (TMDL format). |
| `description` | String | No | | Model description. |
| `default_lakehouse` | String | No | | Lakehouse resource key for data source binding. |
| `auto_refresh` | Boolean | No | `false` | Automatically refresh the model after deployment. |
| `refresh_timeout` | Integer | No | `600` | Refresh timeout in seconds. |
| `after_deploy` | List of strings | No | `[]` | Actions to run after deployment (for example, `"refresh"`). |
| `depends_on_run` | List of strings | No | `[]` | Only refresh if these resources ran successfully. |
| `folder` | String | No | | Workspace folder path. |

#### Example

```yaml
resources:
  semantic_models:
    sales_model:
      path: semantic_models/sales_model/
      description: "Sales analytics semantic model"
      default_lakehouse: gold_lakehouse
      auto_refresh: true
      refresh_timeout: 900
      folder: "BI/Models"
```

---

### reports

Power BI reports deployed from local `.pbir` or report definition files.

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `path` | String | **Yes** | | Path to the `.pbir` or report definition file/directory. |
| `description` | String | No | | Report description. |
| `semantic_model` | String | No | | Reference to a `semantic_models` resource key in the same bundle. |
| `external_semantic_model` | String | No | | Cross-workspace model reference using `workspace://ws-name/model-name` syntax. |
| `folder` | String | No | | Workspace folder path. |

#### Example

```yaml
resources:
  reports:
    sales_report:
      path: reports/sales_report/
      description: "Executive sales dashboard"
      semantic_model: sales_model
      folder: "BI/Reports"

    cross_workspace_report:
      path: reports/cross_ws_report/
      external_semantic_model: "workspace://shared-models/enterprise_model"
```

---

### data_agents

Data Agent (AI/NL2SQL) resources with grounding configuration.

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `description` | String | No | | Agent description. |
| `sources` | List of strings | No | `[]` | Resource keys for lakehouses, warehouses, or semantic models to ground the agent on. |
| `instructions` | String | No | | Path to an instructions markdown file. |
| `few_shot_examples` | String | No | | Path to a few-shot examples YAML file. |
| `tables_in_scope` | List of strings | No | `[]` | Specific tables the agent can query. |

#### Example

```yaml
resources:
  data_agents:
    sales_agent:
      description: "Natural language query agent for sales data"
      sources:
        - gold_lakehouse
        - analytics_warehouse
      instructions: agents/sales_instructions.md
      few_shot_examples: agents/sales_examples.yml
      tables_in_scope:
        - orders
        - customers
        - products
```

---

### eventhouses

Eventhouse (KQL database cluster) resources.

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `description` | String | No | | Eventhouse description. |
| `kql_scripts` | List of strings | No | `[]` | Paths to KQL scripts to execute on deploy. |
| `retention_days` | Integer | No | | Data retention period in days. |
| `cache_days` | Integer | No | | Hot cache period in days. |

#### Example

```yaml
resources:
  eventhouses:
    telemetry_eventhouse:
      description: "Real-time telemetry event store"
      kql_scripts:
        - kql/create_tables.kql
        - kql/create_functions.kql
      retention_days: 365
      cache_days: 30
```

---

### eventstreams

Eventstream resources for real-time data ingestion.

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `description` | String | No | | Eventstream description. |
| `path` | String | No | | Path to an eventstream definition JSON file. |
| `sources` | List of objects | No | `[]` | Eventstream source configurations. |
| `destinations` | List of objects | No | `[]` | Eventstream destination configurations. |

#### Example

```yaml
resources:
  eventstreams:
    iot_stream:
      description: "IoT device telemetry stream"
      path: eventstreams/iot_stream.json
```

---

## security

Workspace and OneLake role assignments.

### Fields

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `roles` | List of [SecurityRole](#securityrole) | No | `[]` | Role definitions. |

### SecurityRole

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `name` | String | **Yes** | | Role display name. |
| `entra_group` | String | No | | Entra ID (Azure AD) group name or object ID. |
| `entra_user` | String | No | | Entra ID user UPN (for example, `user@contoso.com`). |
| `service_principal` | String | No | | Service principal name or application ID. |
| `workspace_role` | Enum | No | `"viewer"` | Workspace role: `admin`, `member`, `contributor`, `viewer`. |
| `onelake_roles` | List of [OneLakeRoleBinding](#onelakerole) | No | `[]` | Fine-grained OneLake data access roles. |

> **Note**
>
> Specify exactly one of `entra_group`, `entra_user`, or `service_principal` per role.

### OneLakeRoleBinding

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `tables` | List of strings | No | `[]` | Table names to grant access to. |
| `folders` | List of strings | No | `[]` | Folder paths to grant access to. |
| `permissions` | List of enum | No | `[]` | Permissions: `read`, `write`, `readwrite`. |

### Example

```yaml
security:
  roles:
    - name: data-engineers
      entra_group: "sg-data-engineers"
      workspace_role: contributor
      onelake_roles:
        - tables: [orders, customers]
          folders: ["/Files/raw"]
          permissions: [readwrite]

    - name: analysts
      entra_group: "sg-data-analysts"
      workspace_role: viewer
      onelake_roles:
        - tables: [orders, customers, products]
          permissions: [read]

    - name: ci-cd-deployer
      service_principal: "sp-fabric-deploy"
      workspace_role: admin

    - name: report-viewer
      entra_user: "manager@contoso.com"
      workspace_role: viewer
```

---

## connections

Data source connection definitions.

### Fields

Each connection is a named entry in the `connections` map.

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `type` | Enum | **Yes** | | Connection type: `adls_gen2`, `sql_server`, `azure_sql`, `cosmos_db`, `kusto`, `http`, `custom`. |
| `endpoint` | String | No | | Connection endpoint URL or server address. |
| `database` | String | No | | Database name (for database-type connections). |
| `auth_method` | String | No | | Authentication method (for example, `service_principal`, `managed_identity`, `key`). |
| `connection_string_var` | String | No | | Environment variable name containing the connection string. |
| `properties` | Map of string to string | No | `{}` | Additional connection properties. |

### Example

```yaml
connections:
  source_adls:
    type: adls_gen2
    endpoint: "https://mystorage.dfs.core.windows.net"
    auth_method: managed_identity

  source_sql:
    type: azure_sql
    endpoint: "myserver.database.windows.net"
    database: "salesdb"
    auth_method: service_principal

  external_api:
    type: http
    endpoint: "https://api.example.com/v2"
    properties:
      api_version: "2024-01-01"
      timeout: "30"

  source_cosmos:
    type: cosmos_db
    endpoint: "https://myaccount.documents.azure.com:443/"
    database: "telemetry"
    auth_method: key
    connection_string_var: "COSMOS_CONNECTION_STRING"
```

> **Warning**
>
> Never put secrets (connection strings, API keys, passwords) directly in `fabric.yml`. Use `${secret.KEY_NAME}` for Key Vault references, `${env.VAR_NAME}` for environment variables, or the `connection_string_var` field.

---

## policies

Validation and governance rules enforced during `fab-bundle validate` and `fab-bundle deploy`.

### Fields

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `rules` | List of [PolicyRule](#policyrule) | No | `[]` | Custom policy rules. |
| `require_description` | Boolean | No | `false` | Require a `description` field on every resource. |
| `naming_convention` | String | No | | Naming convention to enforce: `snake_case`, `camelCase`, etc. |
| `max_notebook_size_kb` | Integer | No | | Maximum allowed notebook file size in kilobytes. |
| `blocked_libraries` | List of strings | No | `[]` | PyPI packages that are not allowed in environment definitions. |

### PolicyRule

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `name` | String | **Yes** | | Rule display name. |
| `check` | String | **Yes** | | Policy check type (for example, `require_description`, `naming_convention`, `max_resources`). |
| `value` | Any | No | | Check-specific value. |
| `severity` | String | No | `"error"` | Severity level: `error` (blocks deploy) or `warning` (informational). |

### Example

```yaml
policies:
  require_description: true
  naming_convention: snake_case
  max_notebook_size_kb: 500
  blocked_libraries:
    - tensorflow   # Use ml_models instead
    - boto3        # Use Fabric-native connections
  rules:
    - name: max-resources
      check: max_resources
      value: 50
      severity: warning
    - name: require-env
      check: require_environment
      severity: error
```

> **Note**
>
> Policy violations with severity `error` cause `fab-bundle validate --strict` and `fab-bundle deploy` to fail. Violations with severity `warning` are reported but do not block deployment.

---

## notifications

Webhook notifications sent after deployment events.

### Fields

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `on_success` | List of [NotificationConfig](#notificationconfig) | No | `[]` | Notifications to send after a successful deployment. |
| `on_failure` | List of [NotificationConfig](#notificationconfig) | No | `[]` | Notifications to send after a failed deployment. |

### NotificationConfig

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `type` | String | **Yes** | | Notification type: `slack`, `teams`. |
| `webhook` | String | **Yes** | | Webhook URL. Use `${secret.WEBHOOK}` for secrets. |
| `message` | String | No | `"Deployed {bundle.name} v{bundle.version} to {target}"` | Message template. Supports `{bundle.name}`, `{bundle.version}`, `{target}` placeholders. |

### Example

```yaml
notifications:
  on_success:
    - type: slack
      webhook: "${secret.SLACK_DEPLOY_WEBHOOK}"
      message: "Deployed {bundle.name} v{bundle.version} to {target}"
    - type: teams
      webhook: "${secret.TEAMS_WEBHOOK}"

  on_failure:
    - type: slack
      webhook: "${secret.SLACK_ALERTS_WEBHOOK}"
      message: "FAILED: {bundle.name} v{bundle.version} deployment to {target}"
```

---

## state

Remote state backend configuration. By default, deployment state is stored locally in a `.fab-bundle/` directory.

### Fields

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `backend` | String | No | `"local"` | State backend type: `local`, `azureblob`, `adls`. |
| `config` | Map of string to string | No | `{}` | Backend-specific configuration. |

### Backend: local (default)

State is stored in `.fab-bundle/state/<target>.json` in the project directory.

```yaml
state:
  backend: local
```

### Backend: azureblob

State is stored in Azure Blob Storage. Requires the `remote-state` extra.

```yaml
state:
  backend: azureblob
  config:
    storage_account: "mystorageaccount"
    container: "fab-bundle-state"
    key: "sales-analytics.tfstate"
```

### Backend: adls

State is stored in Azure Data Lake Storage Gen2. Requires the `remote-state` extra.

```yaml
state:
  backend: adls
  config:
    storage_account: "mydatalake"
    filesystem: "state"
    path: "fab-bundle/sales-analytics"
```

> **Important**
>
> Remote state backends require the `remote-state` extra: `pip install fabric-automation-bundles[remote-state]`.

> **Tip**
>
> Use a remote state backend when multiple team members or CI/CD pipelines deploy the same bundle to prevent state conflicts.

---

## targets

Environment-specific overrides. Each target defines a deployment context with its own workspace, variables, security, run identity, post-deploy checks, and deployment strategy.

### Fields

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `default` | Boolean | No | `false` | Whether this is the default target when `-t` is not specified. Only one target should be set as default. |
| `workspace` | [WorkspaceConfig](#workspace) | No | | Workspace overrides for this target. Merges with the top-level `workspace`. |
| `variables` | Map of string to string | No | `{}` | Variable values for this target. Overrides the top-level `variables` defaults. |
| `run_as` | [RunAsConfig](#runasconfig) | No | | Identity to use for deployment. |
| `security` | [SecurityConfig](#security) | No | | Target-specific security role overrides. |
| `resources` | [ResourceOverrides](#resourceoverrides) | No | | Per-resource property overrides for this target. |
| `post_deploy` | List of [ValidationCheck](#validationcheck) | No | `[]` | Post-deployment validation checks. |
| `deployment_strategy` | [DeploymentStrategy](#deploymentstrategy) | No | | Deployment strategy (all-at-once or canary). |

### RunAsConfig

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `service_principal` | String | No | | Service principal name or app ID to deploy as. |
| `user_name` | String | No | | User UPN to deploy as. |

### ValidationCheck

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `run` | String | No | | Resource name to execute as a validation. |
| `sql` | String | No | | SQL query to execute as a validation. |
| `expect` | String | No | | Expected result (for example, `success`, `> 0`). |
| `timeout` | Integer | No | `300` | Timeout in seconds. |

### DeploymentStrategy

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `type` | String | No | `"all-at-once"` | Strategy type: `all-at-once` or `canary`. |
| `canary_resources` | List of strings | No | `[]` | Resource keys to deploy first in a canary deployment. |
| `validation` | [ValidationCheck](#validationcheck) | No | | Validation to run after canary resources are deployed, before proceeding with the rest. |

### ResourceOverrides

Per-target property overrides for specific resources. Each resource type key maps resource names to a dictionary of field overrides.

| Field | Type | Description |
|---|---|---|
| `lakehouses` | Map | Per-lakehouse overrides. |
| `notebooks` | Map | Per-notebook overrides. |
| `pipelines` | Map | Per-pipeline overrides. |
| `warehouses` | Map | Per-warehouse overrides. |
| `semantic_models` | Map | Per-semantic-model overrides. |
| `reports` | Map | Per-report overrides. |
| `data_agents` | Map | Per-data-agent overrides. |
| `environments` | Map | Per-environment overrides. |
| `eventhouses` | Map | Per-eventhouse overrides. |
| `eventstreams` | Map | Per-eventstream overrides. |

### Example

```yaml
targets:
  dev:
    default: true
    workspace:
      name: sales-analytics-dev
      capacity_id: "aaaabbbb-cccc-dddd-eeee-ffffffffffff"
    variables:
      source_connection: "Server=dev-sql;Database=sales"
      environment: "development"
    post_deploy:
      - run: smoke_test_notebook
        expect: success
        timeout: 300

  staging:
    workspace:
      name: sales-analytics-staging
      capacity_id: "11112222-3333-4444-5555-666677778888"
    variables:
      source_connection: "Server=staging-sql;Database=sales"
      environment: "staging"
    run_as:
      service_principal: sp-fabric-staging
    post_deploy:
      - run: integration_test_notebook
        expect: success
        timeout: 600
      - sql: "SELECT COUNT(*) FROM gold_lakehouse.orders WHERE load_date = CURRENT_DATE()"
        expect: "> 0"
        timeout: 60

  prod:
    workspace:
      name: sales-analytics-prod
      capacity_id: "99998888-7777-6666-5555-444433332222"
    variables:
      source_connection: "${secret.PROD_SQL_CONNECTION}"
      environment: "production"
    run_as:
      service_principal: sp-fabric-prod
    security:
      roles:
        - name: prod-admins
          entra_group: "sg-prod-admins"
          workspace_role: admin
    deployment_strategy:
      type: canary
      canary_resources:
        - ingest_notebook
      validation:
        run: smoke_test_notebook
        expect: success
        timeout: 300
    resources:
      notebooks:
        ingest_notebook:
          spark_properties:
            spark.sql.shuffle.partitions: "400"
```

> **Tip**
>
> Use the `deployment_strategy` with `type: canary` for production targets. This deploys a subset of resources first, runs validation, and only proceeds with the full deployment if validation passes.

---

## include

Merge additional YAML files into the bundle definition. Use `include` to split large bundles across multiple files.

### Fields

| Type | Description |
|---|---|
| List of strings | File paths or glob patterns relative to the `fabric.yml` location. |

### Example

**Main fabric.yml:**

```yaml
bundle:
  name: sales-analytics
  version: "1.0.0"

include:
  - resources/lakehouses.yml
  - resources/notebooks.yml
  - resources/pipelines.yml
  - security/*.yml
```

**resources/lakehouses.yml:**

```yaml
resources:
  lakehouses:
    bronze_lakehouse:
      description: "Raw ingestion lakehouse"
    gold_lakehouse:
      description: "Curated analytics lakehouse"
```

**resources/notebooks.yml:**

```yaml
resources:
  notebooks:
    ingest_notebook:
      path: notebooks/ingest.py
      default_lakehouse: bronze_lakehouse
```

> **Note**
>
> Included files are deep-merged into the main bundle. If the same resource key appears in multiple files, the last included file wins.

---

## extends

Inherit from a parent bundle definition. The child bundle inherits all settings from the parent and can override any field.

### Fields

| Type | Description |
|---|---|
| String | Path to the parent `fabric.yml` file, relative to the child bundle location. |

### Example

**Parent bundle (shared/fabric.yml):**

```yaml
bundle:
  name: shared-platform
  version: "1.0.0"

workspace:
  capacity_id: "aaaabbbb-cccc-dddd-eeee-ffffffffffff"

resources:
  environments:
    standard_env:
      runtime: "1.3"
      libraries:
        - great-expectations>=0.18.0
        - delta-spark>=3.0
```

**Child bundle (sales/fabric.yml):**

```yaml
extends: ../shared/fabric.yml

bundle:
  name: sales-analytics
  version: "1.0.0"

resources:
  notebooks:
    ingest_notebook:
      path: notebooks/ingest.py
      environment: standard_env   # Inherited from parent
```

> **Note**
>
> The child bundle's `bundle.name` overrides the parent's name. All other fields are deep-merged, with child values taking precedence.

---

## Complete example

The following `fabric.yml` demonstrates most features:

```yaml
bundle:
  name: sales-analytics
  version: "2.0.0"
  description: "End-to-end sales analytics with medallion architecture"

workspace:
  capacity_id: "${var.capacity_id}"
  description: "Sales analytics workspace"

variables:
  capacity_id:
    description: "Fabric capacity GUID"
  source_connection:
    description: "Source database connection string"
    default: "Server=localhost;Database=sales"
  environment:
    description: "Deployment environment"
    default: "dev"

resources:
  environments:
    spark_env:
      runtime: "1.3"
      libraries:
        - great-expectations>=0.18.0
        - delta-spark>=3.0

  lakehouses:
    bronze_lakehouse:
      description: "Raw data ingestion"
      shortcuts:
        - name: external_data
          target: "adls://storage.dfs.core.windows.net/raw"
    gold_lakehouse:
      description: "Curated analytics data"

  notebooks:
    ingest_notebook:
      path: notebooks/ingest.py
      environment: spark_env
      default_lakehouse: bronze_lakehouse
    transform_notebook:
      path: notebooks/transform.py
      environment: spark_env
      default_lakehouse: gold_lakehouse

  pipelines:
    daily_pipeline:
      schedule:
        frequency: daily
        timezone: "America/New_York"
      activities:
        - name: ingest
          notebook: ingest_notebook
        - name: transform
          notebook: transform_notebook
          depends_on: [ingest]

  semantic_models:
    sales_model:
      path: models/sales/
      default_lakehouse: gold_lakehouse
      auto_refresh: true

  reports:
    sales_dashboard:
      path: reports/sales_dashboard/
      semantic_model: sales_model

  data_agents:
    sales_agent:
      sources: [gold_lakehouse]
      instructions: agents/instructions.md

security:
  roles:
    - name: engineers
      entra_group: "sg-data-engineers"
      workspace_role: contributor
    - name: analysts
      entra_group: "sg-analysts"
      workspace_role: viewer

connections:
  source_sql:
    type: azure_sql
    endpoint: "myserver.database.windows.net"
    database: "salesdb"

policies:
  require_description: true
  naming_convention: snake_case
  max_notebook_size_kb: 500

notifications:
  on_success:
    - type: slack
      webhook: "${secret.SLACK_WEBHOOK}"
  on_failure:
    - type: slack
      webhook: "${secret.SLACK_ALERTS_WEBHOOK}"
      message: "FAILED: {bundle.name} to {target}"

state:
  backend: azureblob
  config:
    storage_account: "statestore"
    container: "fab-bundle"
    key: "sales-analytics"

targets:
  dev:
    default: true
    workspace:
      name: sales-analytics-dev
    variables:
      capacity_id: "dev-capacity-guid-here"
      source_connection: "Server=dev-sql;Database=sales"
    post_deploy:
      - run: ingest_notebook
        expect: success
        timeout: 300

  prod:
    workspace:
      name: sales-analytics-prod
    variables:
      capacity_id: "prod-capacity-guid-here"
      source_connection: "${secret.PROD_CONNECTION_STRING}"
    run_as:
      service_principal: sp-fabric-prod
    deployment_strategy:
      type: canary
      canary_resources: [ingest_notebook]
      validation:
        run: ingest_notebook
        expect: success
```

---

## See also

- [CLI command reference](../cli/commands.md) -- Full reference for all `fab-bundle` commands.
- [Installation](../getting-started/installation.md) -- Install and configure Fabric Automation Bundles.
