# Resource Types

## Supported Types

| Resource | Type Key | Create | Update | Destroy |
|----------|----------|--------|--------|---------|
| Lakehouse | `lakehouses` | ✅ | ✅ | ✅ |
| Notebook | `notebooks` | ✅ | ✅ | ✅ |
| Data Pipeline | `pipelines` | ✅ | ✅ | ✅ |
| Warehouse | `warehouses` | ✅ | ✅ | ✅ |
| Semantic Model | `semantic_models` | ✅ | ✅ | ✅ |
| Report | `reports` | ✅ | ✅ | ✅ |
| Environment | `environments` | ✅ | ✅ | ✅ |
| Data Agent | `data_agents` | ✅ | ✅ | ✅ |
| Eventhouse | `eventhouses` | ✅ | ✅ | ✅ |
| Eventstream | `eventstreams` | ✅ | ✅ | ✅ |
| ML Model | `ml_models` | ✅ | ✅ | ✅ |
| ML Experiment | `ml_experiments` | ✅ | ✅ | ✅ |

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
