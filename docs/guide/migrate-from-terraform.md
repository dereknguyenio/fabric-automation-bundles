# Migrate from Terraform

If you're using the [Terraform Fabric Provider](https://registry.terraform.io/providers/microsoft/fabric/latest/docs), here's how to migrate to fab-bundle.

## Why Migrate?

| | Terraform | fab-bundle |
|---|-----------|-----------|
| Language | HCL | YAML |
| State | Remote (S3, Blob, etc.) | Local or OneLake |
| Learning curve | High (HCL, providers, modules) | Low (single YAML file) |
| Drift detection | `terraform plan` | `fab-bundle drift` |
| Rollback | Manual state manipulation | `fab-bundle rollback` |
| Fabric-specific | Generic provider | Purpose-built for Fabric |
| MCP support | No | Yes (12 tools) |
| Item types | ~15 | 45 |

## Step-by-step Migration

### 1. Import existing state

```bash
fab-bundle import --from-terraform terraform.tfstate --target dev
```

This reads your Terraform state and creates a fab-bundle state file.

### 2. Generate fabric.yml

```bash
fab-bundle generate --workspace "your-workspace-name"
```

Or manually map your Terraform resources:

| Terraform | fabric.yml |
|-----------|------------|
| `microsoft_fabric_workspace` | `targets.dev.workspace` |
| `microsoft_fabric_lakehouse` | `resources.lakehouses` |
| `microsoft_fabric_notebook` | `resources.notebooks` |
| `microsoft_fabric_warehouse` | `resources.warehouses` |
| `microsoft_fabric_spark_environment` | `resources.environments` |
| `microsoft_fabric_data_pipeline` | `resources.pipelines` |

### 3. Validate

```bash
fab-bundle validate
fab-bundle plan -t dev
```

### 4. Deploy

```bash
fab-bundle deploy -t dev
```

### 5. Remove Terraform

Once fab-bundle is managing your resources, remove the Terraform config. Keep the Terraform state file as a backup until you're confident.
