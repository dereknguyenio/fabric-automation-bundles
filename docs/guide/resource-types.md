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
| Mirrored Warehouse | `mirrored_warehouses` | MirroredWarehouse | Metadata |
| Mirrored Databricks Catalog | `mirrored_databricks_catalogs` | MirroredAzureDatabricksCatalog | Connection-based |
| Cosmos DB Database | `cosmosdb_databases` | CosmosDBDatabase | Connection-based |
| Datamart | `datamarts` | Datamart | Definition file |

### Power BI
| Resource | Type Key | API Type | Definitions |
|----------|----------|----------|-------------|
| Semantic Model | `semantic_models` | SemanticModel | TMDL or TMSL |
| Report | `reports` | Report | PBIR format |
| Paginated Report | `paginated_reports` | PaginatedReport | .rdl file |
| Dashboard | `dashboards` | Dashboard | Metadata |
| Dataflow | `dataflows` | Dataflow | JSON definition |

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

## Lakehouse

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
```

## Notebook

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

## Pipeline

```yaml
pipelines:
  daily_refresh:
    description: "Daily ETL"
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
```

## Environment

```yaml
environments:
  spark_env:
    runtime: "1.3"
    libraries:
      - semantic-link-labs
      - delta-spark
    spark_properties:
      spark.sql.shuffle.partitions: "200"
```
