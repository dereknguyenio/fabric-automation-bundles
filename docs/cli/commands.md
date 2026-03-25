# CLI Commands

## Core Commands

| Command | Description |
|---------|-------------|
| `fab-bundle init` | Create a new project from a template |
| `fab-bundle validate` | Validate the bundle definition |
| `fab-bundle plan` | Preview changes (dry-run) |
| `fab-bundle deploy` | Deploy to a target workspace |
| `fab-bundle destroy` | Tear down bundle resources |

## Resource Commands

| Command | Description |
|---------|-------------|
| `fab-bundle run <resource>` | Run a notebook or pipeline |
| `fab-bundle export` | Export definitions from workspace |
| `fab-bundle generate` | Generate fabric.yml from workspace |
| `fab-bundle bind` | Bind existing item to bundle |
| `fab-bundle import` | Import from Terraform or workspace |

## Operational Commands

| Command | Description |
|---------|-------------|
| `fab-bundle status` | Show deployed resource health |
| `fab-bundle drift` | Detect drift from deployed state |
| `fab-bundle diff` | Definition-level diff (local vs deployed) |
| `fab-bundle history` | Show deployment history |
| `fab-bundle rollback` | Rollback to previous deployment |
| `fab-bundle promote` | Promote between targets |
| `fab-bundle watch` | Auto-deploy on file changes |
| `fab-bundle doctor` | Diagnose configuration issues |
| `fab-bundle graph` | Visualize dependency graph |

## Common Flags

| Flag | Description |
|------|-------------|
| `-f, --file` | Path to fabric.yml |
| `-t, --target` | Target environment |
| `-y, --auto-approve` | Skip confirmation |
| `--dry-run` | Preview without changes |
| `--force` | Override locks and skip cache |
