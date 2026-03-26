# Migrate from fabric-cicd

If you're using [fabric-cicd](https://github.com/microsoft/fabric-cicd), here's how to migrate to fab-bundle.

## Comparison

| | fabric-cicd | fab-bundle |
|---|------------|-----------|
| Approach | Git sync-based deployment | Declarative YAML + API |
| Config | Python code | fabric.yml |
| Item support | Git-synced items only | 45 item types |
| Creates workspaces | No | Yes |
| Creates lakehouses | No | Yes |
| Creates environments | No | Yes |
| Security roles | No | Yes |
| Drift detection | No | Yes |
| Rollback | No | Yes |
| MCP server | No | Yes |
| State tracking | No | Yes |

## When to Migrate

Migrate if you need:
- Infrastructure creation (workspaces, lakehouses, environments)
- Security role automation
- Drift detection
- Full item type coverage beyond git-synced items
- Declarative YAML instead of Python code

Stay with fabric-cicd if:
- You only need to promote git-synced content between workspaces
- Your infrastructure is already created and managed manually

## Migration Steps

### 1. Export your workspace

```bash
fab-bundle generate --workspace "your-dev-workspace"
```

### 2. Review the generated fabric.yml

The generated file captures all items in your workspace. Edit it to:
- Add targets for staging/prod
- Add security roles
- Add variable overrides per target
- Remove items you don't want managed

### 3. Set up CI/CD

Replace your fabric-cicd pipeline with fab-bundle:

**Before (fabric-cicd):**
```python
from fabric_cicd import FabricWorkspace
ws = FabricWorkspace(workspace_id="...", repository_directory=".")
ws.publish_all_items()
```

**After (fab-bundle):**
```bash
fab-bundle deploy -t prod -y
```

### 4. Test

```bash
fab-bundle validate
fab-bundle plan -t staging
fab-bundle deploy -t staging
```
