# Claude Code Instructions for Fabric Projects

This project uses **Fabric Automation Bundles** (`fab-bundle`) to manage Microsoft Fabric resources.

## MCP Server

If configured, you have access to these tools via the `fab-bundle-mcp` MCP server:

- `fab_validate` — Validate the fabric.yml bundle
- `fab_plan` — Preview what would change (dry-run)
- `fab_deploy` — Deploy resources to a target workspace
- `fab_destroy` — Tear down resources
- `fab_status` — Show deployed resource health
- `fab_drift` — Detect out-of-band changes
- `fab_run` — Run a notebook or pipeline
- `fab_history` — Show deployment history
- `fab_doctor` — Diagnose configuration issues
- `fab_list_templates` — Available project templates
- `fab_list_workspaces` — List Fabric workspaces
- `fab_list_capacities` — List available capacities

## Key Files

- `fabric.yml` — Declarative project definition (lakehouses, notebooks, pipelines, security, targets)
- `notebooks/` — PySpark notebooks deployed to Fabric
- `sql/` — SQL scripts executed on warehouses
- `agent/` — Data Agent instructions and few-shot examples

## Common Tasks

- **Deploy to dev:** Use `fab_deploy` with `target: "dev"` or run `fab-bundle deploy --target dev`
- **Check what's deployed:** Use `fab_status` with `target: "dev"`
- **Preview changes:** Use `fab_plan` with `target: "dev"`
- **Run a notebook:** Use `fab_run` with `resource_name: "notebook_name"` and `target: "dev"`

## fabric.yml Structure

```yaml
bundle:
  name: project-name
  version: "1.0.0"

resources:
  lakehouses: {}    # Data storage
  notebooks: {}     # PySpark ETL code
  pipelines: {}     # Orchestration
  environments: {}  # Spark runtime + libraries
  warehouses: {}    # SQL analytics
  data_agents: {}   # Natural language interface

security:
  roles: []         # Workspace + OneLake access

targets:
  dev: {}           # Dev workspace config
  test: {}          # Test workspace config
  prod: {}          # Prod workspace config
```

## Prerequisites

- `az login` for authentication
- Fabric capacity must be active
- `pip install fabric-automation-bundles[mcp]` for MCP tools
