# Resource Types

## Supported Types

### Data Engineering
| Resource | Type Key | API Type | Definitions |
|----------|----------|----------|-------------|
| Lakehouse | `lakehouses` | Lakehouse | Shortcuts, tables, schemas |
| Notebook | `notebooks` | Notebook | .py, .ipynb, .sql, .scala, .r |
| Environment | `environments` | SparkEnvironment | Runtime, libraries, Spark config |
| Spark Job Definition | `spark_job_definitions` | SparkJobDefinition | .py, .jar |
| GraphQL API | `graphql_apis` | GraphQLApi | Schema file |
| Snowflake Database | `snowflake_databases` | SnowflakeDatabase | Connection-based |

### Data Factory
| Resource | Type Key | API Type | Definitions |
|----------|----------|----------|-------------|
| Data Pipeline | `pipelines` | DataPipeline | YAML activities or JSON |
| Copy Job | `copy_jobs` | CopyJob | JSON definition |
| Mounted Data Factory | `mounted_data_factories` | MountedDataFactory | Metadata |
| Apache Airflow Job | `airflow_jobs` | ApacheAirflowJob | DAG file |
| dbt Job | `dbt_jobs` | DataBuildToolJob | dbt project |

### Data Warehouse
| Resource | Type Key | API Type | Definitions |
|----------|----------|----------|-------------|
| Warehouse | `warehouses` | Warehouse | SQL scripts |
| SQL Database | `sql_databases` | SQLDatabase | SQL scripts |
| Mirrored Database | `mirrored_databases` | MirroredDatabase | Connection-based |
| Mirrored Warehouse | `mirrored_warehouses` | MirroredWarehouse | List-only — cannot be created via API |
| Mirrored Databricks Catalog | `mirrored_databricks_catalogs` | MirroredAzureDatabricksCatalog | Connection-based |
| Cosmos DB Database | `cosmosdb_databases` | CosmosDBDatabase | Connection-based |
| Datamart | `datamarts` | Datamart | List-only — cannot be created via API |

### Power BI
| Resource | Type Key | API Type | Definitions |
|----------|----------|----------|-------------|
| Semantic Model | `semantic_models` | SemanticModel | TMDL or TMSL |
| Report | `reports` | Report | PBIR format |
| Paginated Report | `paginated_reports` | PaginatedReport | List-only — cannot be created via API |
| Dashboard | `dashboards` | Dashboard | List-only — cannot be created via API |
| Dataflow | `dataflows` | Dataflow | Not supported by Fabric API |

### Data Science
| Resource | Type Key | API Type | Definitions |
|----------|----------|----------|-------------|
| ML Model | `ml_models` | MLModel | MLflow model |
| ML Experiment | `ml_experiments` | MLExperiment | Metadata |

### Real-Time Intelligence
| Resource | Type Key | API Type | Definitions |
|----------|----------|----------|-------------|
| Eventhouse | `eventhouses` | Eventhouse | KQL scripts |
| Eventstream | `eventstreams` | Eventstream | JSON definition |
| KQL Database | `kql_databases` | KQLDatabase | KQL scripts |
| KQL Dashboard | `kql_dashboards` | KQLDashboard | Definition file |
| KQL Queryset | `kql_querysets` | KQLQueryset | Definition file |
| Reflex (Data Activator) | `reflex` | Reflex | JSON definition |
| Digital Twin Builder | `digital_twin_builders` | DigitalTwinBuilder | Definition file |
| Digital Twin Builder Flow | `digital_twin_builder_flows` | DigitalTwinBuilderFlow | Definition file |
| Event Schema Set | `event_schema_sets` | EventSchemaSet | Definition file |
| Graph Query Set | `graph_query_sets` | GraphQuerySet | Definition file |

### AI & Knowledge
| Resource | Type Key | API Type | Definitions |
|----------|----------|----------|-------------|
| Data Agent | `data_agents` | DataAgent | Instructions + examples |
| Operations Agent | `operations_agents` | OperationsAgent | Instructions |
| Anomaly Detector | `anomaly_detectors` | AnomalyDetector | Configuration |
| Ontology | `ontologies` | Ontology | Definition file |

### Other
| Resource | Type Key | API Type | Definitions |
|----------|----------|----------|-------------|
| Variable Library | `variable_libraries` | VariableLibrary | Key-value pairs |
| User Data Function | `user_data_functions` | UserDataFunction | Function definition |
| Graph | `graphs` | Graph | Definition file |
| Graph Model | `graph_models` | GraphModel | Definition file |
| Map | `map_items` | Map | Definition file |
| HLS Cohort | `hls_cohorts` | HLSCohort | Definition file |

### OneLake Shortcuts

Shortcuts are not a separate item type — they are sub-resources of Lakehouses:

```yaml
lakehouses:
  bronze_lakehouse:
    shortcuts:
      - name: external_data
        target: "adls://storageaccount/container/path"
        path: Tables
        connection_id: "optional-connection-guid"
      - name: s3_data
        target: "s3://bucket-name/prefix"
      - name: cross_workspace
        target: "onelake://workspace-id/item-id/Tables/my_table"
```

Supported shortcut targets:

- `adls://` — Azure Data Lake Storage Gen2
- `s3://` — Amazon S3
- `onelake://` — Cross-workspace OneLake reference

### Shortcut Transformations

Auto-convert source files to managed Delta tables — always in sync, no pipelines required.

**File transformations** convert CSV, Parquet, JSON, or Excel files into Delta tables:

```yaml
lakehouses:
  bronze_lakehouse:
    shortcuts:
      - name: csv_sales_data
        target: "adls://datalake/sales/*.csv"
        path: Files
        transformation:
          type: file
          source_format: csv
          destination_table: raw_sales
          sync: true
          flatten: false

      - name: nested_json_events
        target: "adls://datalake/events/*.json"
        path: Files
        transformation:
          type: file
          source_format: json
          destination_table: raw_events
          flatten: true
          compression: gzip

      - name: excel_reports
        target: "adls://datalake/finance/*.xlsx"
        path: Files
        transformation:
          type: file
          source_format: excel
          destination_table: finance_reports
```

**AI-powered transformations** apply summarization, translation, or classification:

```yaml
lakehouses:
  documents_lakehouse:
    shortcuts:
      - name: support_tickets
        target: "adls://datalake/tickets/*.json"
        path: Files
        transformation:
          type: ai
          ai_skill: summarize
          destination_table: ticket_summaries

      - name: multilingual_docs
        target: "adls://datalake/docs/*.json"
        path: Files
        transformation:
          type: ai
          ai_skill: translate
          ai_prompt: "Translate to English"
          destination_table: docs_english

      - name: email_classification
        target: "adls://datalake/emails/*.json"
        path: Files
        transformation:
          type: ai
          ai_skill: classify
          ai_prompt: "Classify as: complaint, inquiry, feedback, spam"
          destination_table: classified_emails
```

---

## YAML Reference — All Resource Types

### Data Engineering

#### Lakehouse

```yaml
lakehouses:
  bronze_lakehouse:
    description: "Raw data landing zone"
    enable_schemas: true
    tables:
      raw_orders:
        schema_path: ./schemas/orders.json
        partition_by: [order_date]
    shortcuts:
      - name: external_data
        target: "adls://account/container/path"
        path: Tables
        connection_id: "optional-guid"
        transformation:
          type: file
          source_format: csv
          destination_table: raw_external
```

#### Notebook

```yaml
notebooks:
  etl_pipeline:
    path: ./notebooks/etl.py
    description: "ETL pipeline"
    environment: spark_env
    default_lakehouse: bronze_lakehouse
    parameters:
      batch_size: 1000
      source_table: orders
    folder: ETL/Bronze
```

#### Environment

```yaml
environments:
  spark_env:
    runtime: "1.3"
    libraries:
      - semantic-link-labs
      - delta-spark
    conda_dependencies:
      - numpy=1.24
    spark_properties:
      spark.sql.shuffle.partitions: "200"
```

#### Spark Job Definition

```yaml
spark_job_definitions:
  distributed_training:
    path: ./spark_jobs/train.py
    description: "Distributed model training"
    environment: spark_env
    default_lakehouse: feature_store
    args: ["--epochs", "10", "--batch-size", "256"]
    conf:
      spark.executor.memory: "8g"
      spark.executor.cores: "4"
```

#### GraphQL API

```yaml
graphql_apis:
  product_api:
    description: "GraphQL API over product data"
    path: ./graphql/schema.graphql
    data_source: gold_lakehouse
```

#### Snowflake Database

```yaml
snowflake_databases:
  snowflake_mirror:
    description: "Mirrored Snowflake data"
    connection: snowflake_conn
```

### Data Factory

#### Data Pipeline

```yaml
pipelines:
  daily_refresh:
    description: "Daily ETL pipeline"
    schedule:
      cron: "0 6 * * *"
      timezone: America/Chicago
      enabled: true
    activities:
      - name: ingest
        notebook: ingest_notebook
      - name: transform
        notebook: transform_notebook
        depends_on: [ingest]
      - name: load
        notebook: load_notebook
        depends_on: [transform]
```

#### Copy Job

```yaml
copy_jobs:
  copy_sales_data:
    description: "Copy sales data from Azure SQL"
    path: ./copy_jobs/sales_copy.json
```

#### Mounted Data Factory

```yaml
mounted_data_factories:
  legacy_adf:
    description: "Mounted Azure Data Factory for legacy pipelines"
    data_factory_id: "/subscriptions/.../resourceGroups/.../providers/Microsoft.DataFactory/factories/my-adf"
```

#### Apache Airflow Job

```yaml
airflow_jobs:
  airflow_etl:
    description: "Airflow DAG for complex orchestration"
    path: ./dags/etl_dag.py
```

#### dbt Job

```yaml
dbt_jobs:
  dbt_transform:
    description: "dbt transformation project"
    path: ./dbt_project/
    environment: spark_env
```

### Data Warehouse

#### Warehouse

```yaml
warehouses:
  analytics_warehouse:
    description: "SQL analytics warehouse"
    sql_scripts:
      - ./sql/create_views.sql
      - ./sql/create_procedures.sql
```

#### SQL Database

```yaml
sql_databases:
  operational_db:
    description: "Operational SQL database"
    sql_scripts:
      - ./sql/schema.sql
      - ./sql/seed_data.sql
```

#### Mirrored Database

```yaml
mirrored_databases:
  azure_sql_mirror:
    description: "Mirrored Azure SQL database"
    source_type: "Azure SQL"
    connection: azure_sql_conn
```

#### Mirrored Warehouse

```yaml
mirrored_warehouses:
  synapse_mirror:
    description: "Mirrored Synapse warehouse"
    source_type: "Synapse"
```

#### Mirrored Databricks Catalog

```yaml
mirrored_databricks_catalogs:
  databricks_catalog:
    description: "Mirrored Databricks Unity Catalog"
    connection: databricks_conn
```

#### Cosmos DB Database

```yaml
cosmosdb_databases:
  cosmos_mirror:
    description: "Mirrored Cosmos DB data"
    connection: cosmos_conn
```

#### Datamart

```yaml
datamarts:
  sales_datamart:
    description: "Self-service sales datamart"
    path: ./datamarts/sales_definition.json
```

### Power BI

#### Semantic Model

```yaml
semantic_models:
  analytics_model:
    path: ./semantic_model/
    description: "Semantic model over gold lakehouse"
    default_lakehouse: gold_lakehouse
    auto_refresh: true
    refresh_timeout: 600
    folder: Models
```

#### Report

```yaml
reports:
  executive_dashboard:
    path: ./reports/dashboard/
    description: "Executive dashboard (PBIR format)"
    semantic_model: analytics_model
    folder: Reports
```

#### Paginated Report

```yaml
paginated_reports:
  monthly_invoice:
    description: "Monthly invoice report (RDL)"
    path: ./reports/invoice.rdl
    data_source: analytics_warehouse
```

#### Dashboard

```yaml
dashboards:
  overview_dashboard:
    description: "High-level KPI dashboard"
```

#### Dataflow

```yaml
dataflows:
  customer_transform:
    description: "Dataflow Gen2 for customer data"
    path: ./dataflows/customer_transform.json
```

### Data Science

#### ML Model

```yaml
ml_models:
  churn_model:
    path: ./models/churn_model/
    description: "Customer churn prediction model"
    framework: xgboost
```

#### ML Experiment

```yaml
ml_experiments:
  churn_experiment:
    description: "Churn prediction experiment tracking"
```

### Real-Time Intelligence

#### Eventhouse

```yaml
eventhouses:
  telemetry_eventhouse:
    description: "IoT telemetry eventhouse"
    kql_scripts:
      - ./kql/create_tables.kql
      - ./kql/create_functions.kql
    retention_days: 365
    cache_days: 31
```

#### Eventstream

```yaml
eventstreams:
  device_events:
    description: "Real-time device event stream"
    path: ./eventstreams/device_config.json
    sources:
      - type: event_hub
        name: iot-hub-events
    destinations:
      - type: eventhouse
        name: telemetry_eventhouse
```

#### KQL Database

```yaml
kql_databases:
  telemetry_db:
    description: "KQL database for device telemetry"
    parent_eventhouse: telemetry_eventhouse
    kql_scripts:
      - ./kql/create_tables.kql
```

#### KQL Dashboard

```yaml
kql_dashboards:
  ops_dashboard:
    description: "Real-time operations dashboard"
    path: ./dashboards/ops_dashboard.json
    data_source: telemetry_db
```

#### KQL Queryset

```yaml
kql_querysets:
  telemetry_queries:
    description: "Pre-built KQL queries for analysis"
    path: ./kql/querysets/
    data_source: telemetry_db
```

#### Reflex (Data Activator)

```yaml
reflex:
  anomaly_alerts:
    description: "Trigger alerts on anomalous readings"
    path: ./reflex/anomaly_rules.json
```

#### Digital Twin Builder

```yaml
digital_twin_builders:
  factory_twin:
    description: "Digital twin of factory floor"
    path: ./twins/factory_definition.json
```

#### Digital Twin Builder Flow

```yaml
digital_twin_builder_flows:
  factory_flow:
    description: "Data flow for factory twin"
    path: ./twins/factory_flow.json
    twin_builder: factory_twin
```

#### Event Schema Set

```yaml
event_schema_sets:
  device_schemas:
    description: "Schema definitions for IoT events"
    path: ./schemas/device_events.json
```

#### Graph Query Set

```yaml
graph_query_sets:
  network_queries:
    description: "Graph queries for network analysis"
    path: ./graph/queries/
    data_source: telemetry_db
```

### AI & Knowledge

#### Data Agent

```yaml
data_agents:
  analytics_agent:
    description: "Natural language interface to your data"
    sources:
      - gold_lakehouse
      - analytics_warehouse
    instructions: ./agent/instructions.md
    few_shot_examples: ./agent/examples.yaml
    tables_in_scope:
      - daily_order_summary
      - customer_360
```

#### Operations Agent

```yaml
operations_agents:
  ops_agent:
    description: "Operations monitoring agent"
    sources:
      - telemetry_eventhouse
    instructions: ./agent/ops_instructions.md
```

#### Anomaly Detector

```yaml
anomaly_detectors:
  revenue_detector:
    description: "Detect revenue anomalies"
    data_source: gold_lakehouse
    path: ./detectors/revenue_config.json
```

#### Ontology

```yaml
ontologies:
  business_ontology:
    description: "Business domain knowledge graph"
    path: ./ontology/definition.json
    data_sources:
      - gold_lakehouse
      - analytics_warehouse
```

### Other

#### Variable Library

```yaml
variable_libraries:
  shared_config:
    description: "Shared configuration variables"
    variables:
      environment: production
      region: us-east
      log_level: info
      max_retries: "3"
```

#### User Data Function

```yaml
user_data_functions:
  custom_transform:
    description: "Custom data transformation function"
    path: ./functions/transform.py
    runtime: python
```

#### Graph

```yaml
graphs:
  knowledge_graph:
    description: "Product knowledge graph"
    path: ./graph/definition.json
    data_source: gold_lakehouse
```

#### Graph Model

```yaml
graph_models:
  supply_chain_model:
    description: "Supply chain graph model"
    path: ./graph/supply_chain.json
    data_source: analytics_warehouse
```

#### Map

```yaml
map_items:
  geo_mapping:
    description: "Geographic data mapping"
    path: ./maps/geo_config.json
```

#### HLS Cohort

```yaml
hls_cohorts:
  patient_cohort:
    description: "Patient cohort for clinical analytics"
    path: ./cohorts/patient_definition.json
```
