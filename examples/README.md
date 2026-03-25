# Examples

Working examples you can copy and deploy to your Fabric tenant.

## Quick Start

1. Copy any example folder to your working directory
2. Update `capacity_id` in `fabric.yml` with your Fabric capacity GUID
3. Run:
   ```bash
   fab-bundle validate
   fab-bundle plan -t dev
   fab-bundle deploy -t dev
   ```

## Examples

| # | Example | Description | Complexity |
|---|---------|-------------|------------|
| 01 | [Minimal](01-minimal/) | One lakehouse, one notebook | Beginner |
| 02 | [Medallion Lakehouse](02-medallion-lakehouse/) | Bronze/Silver/Gold ETL with scheduling | Intermediate |
| 03 | [Real-Time Intelligence](03-real-time-intelligence/) | Eventhouse + Eventstream + KQL | Intermediate |
| 04 | [Data Science](04-data-science/) | ML experiments, training pipelines, Spark jobs | Intermediate |
| 05 | [Multi-Environment](05-multi-environment/) | Policies, secrets, canary deploy, notifications | Advanced |
| 06 | [Shortcuts & Connections](06-shortcuts-and-connections/) | ADLS, S3, cross-workspace shortcuts | Intermediate |
| 07 | [Shortcut Transformations](07-shortcut-transformations/) | CSV/JSON/Excel → Delta, AI summarize/translate/classify | Intermediate |

## Finding Your Capacity GUID

```bash
az rest --method get \
  --url "https://api.fabric.microsoft.com/v1/capacities" \
  --resource "https://api.fabric.microsoft.com"
```

## Need Help?

- [Documentation](https://dereknguyenio.github.io/fabric-automation-bundles/)
- [GitHub Issues](https://github.com/dereknguyenio/fabric-automation-bundles/issues)
- `fab-bundle doctor` to diagnose common issues
