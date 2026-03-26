# ${{project_name}}

OSDU on Fabric for Oil, Gas & Energy managed by [Fabric Automation Bundles](https://github.com/dereknguyenio/fabric-automation-bundles).

## Project Structure

```
${{project_name}}/
├── fabric.yml                          # Bundle definition
├── notebooks/
│   ├── ingest_osdu_entities.py         # OSDU Search API ingestion
│   ├── flatten_wells.py                # Well entity flattening
│   ├── flatten_wellbores.py            # Wellbore entity flattening
│   └── process_production.py           # Production data processing
├── sql/
│   ├── create_well_views.sql           # Well master views
│   └── create_production_views.sql     # Production trend views
├── agent/
│   ├── instructions.md                 # Petroleum engineering context
│   └── examples.yaml                   # Industry-specific examples
├── tests/
│   └── test_validate.py                # Validation tests
└── README.md
```

## Getting Started

```bash
# Update fabric.yml with your capacity_id and ADME endpoint, then:
fab-bundle validate
fab-bundle plan -t dev
fab-bundle deploy -t dev
```
