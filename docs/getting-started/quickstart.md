# Quick Start

## Create a new project

```bash
fab-bundle init --template medallion --name my-analytics
cd my-analytics
```

This creates a project with:
- 3 lakehouses (bronze, silver, gold)
- 3 ETL notebooks
- 1 data pipeline with scheduling
- 1 Spark environment
- 1 data agent
- Dev/staging/prod targets

## Configure your capacity

Find your Fabric capacity GUID:

```bash
az rest --method get \
  --url "https://api.fabric.microsoft.com/v1/capacities" \
  --resource "https://api.fabric.microsoft.com"
```

Update `fabric.yml` with your capacity ID:

```yaml
workspace:
  capacity_id: "your-capacity-guid-here"
```

## Validate

```bash
fab-bundle validate
```

## Plan (dry-run)

```bash
fab-bundle plan -t dev
```

## Deploy

```bash
fab-bundle deploy -t dev
```

## Check status

```bash
fab-bundle status -t dev
fab-bundle drift -t dev
```
