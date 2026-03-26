# ${{project_name}}

Medallion lakehouse architecture (bronze/silver/gold) managed by [Fabric Automation Bundles](https://github.com/dereknguyenio/fabric-automation-bundles).

## Project Structure

```
${{project_name}}/
├── fabric.yml                          # Bundle definition
├── notebooks/
│   ├── ingest_to_bronze.py             # Source → bronze ingestion
│   ├── bronze_to_silver.py             # Bronze → silver cleaning
│   └── silver_to_gold.py              # Silver → gold aggregation
├── sql/
│   └── create_gold_views.sql           # Warehouse SQL views
├── agent/
│   ├── instructions.md                 # Data Agent instructions
│   └── examples.yaml                   # Few-shot examples
├── tests/
│   └── test_validate.py                # Validation tests
└── README.md
```

## Getting Started

```bash
# Update fabric.yml with your capacity_id, then:
fab-bundle validate
fab-bundle plan -t dev
fab-bundle deploy -t dev
```

## Architecture

```
Source Systems → [ingest_to_bronze] → Bronze Lakehouse
                                          ↓
                                   [bronze_to_silver] → Silver Lakehouse
                                                            ↓
                                                     [silver_to_gold] → Gold Lakehouse
                                                                            ↓
                                                                     Warehouse (SQL views)
                                                                            ↓
                                                                     Data Agent (NL queries)
```
