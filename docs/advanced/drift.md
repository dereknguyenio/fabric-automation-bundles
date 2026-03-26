# Drift Detection

Drift occurs when the live state of a Fabric workspace diverges from what is defined in your `fabric.yml`. This can happen when someone edits a resource through the Fabric portal, when an external tool modifies an item via the REST API, or when a teammate deploys a change that is not reflected in the bundle definition. Left unchecked, drift erodes the reliability of infrastructure-as-code: what you see in source control no longer matches what is running in production.

`fab-bundle drift` compares the bundle's recorded state against the actual workspace and reports every discrepancy.

## How drift detection works

Every time `fab-bundle deploy` runs, it writes a state file (`.fab-bundle/state-{target}.json`) that records every deployed resource along with a SHA-256 hash of its definition. When you run `fab-bundle drift`, the tool:

1. **Reads the local state file** to get the list of resources fab-bundle previously deployed, including their item IDs and definition hashes.
2. **Queries the Fabric workspace** via the REST API to retrieve the current list of items and their definitions.
3. **Compares the two** and classifies each difference into one of three categories.

No changes are made to the workspace or the state file during a drift check. It is a read-only operation.

## Types of drift

### Added

Items that exist in the workspace but are not tracked in the bundle state. These were created outside of fab-bundle, for example by a user in the Fabric portal or by another deployment tool.

### Removed

Items that are recorded in the bundle state but no longer exist in the workspace. Someone deleted the item manually, or another process removed it.

### Modified

Items that exist in both the state and the workspace, but whose definition has changed. The definition hash in the state file no longer matches the hash of the live item's definition. This typically means someone edited the resource in the portal (for example, modifying a notebook's code or changing a pipeline's activities).

## Using `fab-bundle drift`

### Basic usage

```bash
# Check drift against the default target
fab-bundle drift

# Check drift against a specific target
fab-bundle drift --target prod
```

### Example output

```
$ fab-bundle drift --target dev

Drift Report for target: dev
Workspace: contoso-analytics-dev (c2410443-5bce-4cce-8065-b453dd6b2f1d)
Compared against state from: 2026-03-25T14:32:10Z

  Added (2):
    + Notebook: ad_hoc_analysis (not tracked by bundle)
    + Report: executive_dashboard (not tracked by bundle)

  Removed (1):
    - Lakehouse: staging_lakehouse (expected but missing from workspace)

  Modified (1):
    ~ Notebook: ingest_to_bronze (definition changed)
        Local hash:  a3f8c2d1e5b7...
        Remote hash: 7b2e4f9a1c3d...

Summary: 4 resources drifted (2 added, 1 removed, 1 modified)
```

### Machine-readable output

Use `--format json` to produce output suitable for scripts and CI/CD:

```bash
fab-bundle drift --target dev --format json
```

```json
{
  "target": "dev",
  "workspace_id": "c2410443-5bce-4cce-8065-b453dd6b2f1d",
  "state_timestamp": "2026-03-25T14:32:10Z",
  "added": [
    {"name": "ad_hoc_analysis", "type": "Notebook"},
    {"name": "executive_dashboard", "type": "Report"}
  ],
  "removed": [
    {"name": "staging_lakehouse", "type": "Lakehouse"}
  ],
  "modified": [
    {"name": "ingest_to_bronze", "type": "Notebook"}
  ],
  "drift_count": 4
}
```

### Exit codes

| Exit Code | Meaning |
|-----------|---------|
| `0` | No drift detected |
| `1` | Drift detected |
| `2` | Error (authentication failure, state file not found, etc.) |

The non-zero exit code on drift makes it straightforward to use in CI/CD pipelines where you want a job to fail when drift is present.

## Automated drift checks in CI/CD

Scheduled drift checks catch configuration drift before it causes problems. A common pattern is to run a drift check on a cron schedule and notify the team when drift is found.

### GitHub Actions example

```yaml
name: Drift Check

on:
  schedule:
    - cron: '0 8 * * 1-5'  # Weekdays at 8:00 AM UTC
  workflow_dispatch:         # Allow manual trigger

jobs:
  drift:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        target: [dev, staging, prod]
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Install fab-bundle
        run: pip install fabric-automation-bundles

      - name: Check for drift
        id: drift
        run: |
          fab-bundle drift -t ${{ matrix.target }} --format json > drift-report.json
        env:
          AZURE_TENANT_ID: ${{ secrets.AZURE_TENANT_ID }}
          AZURE_CLIENT_ID: ${{ secrets.AZURE_CLIENT_ID }}
          AZURE_CLIENT_SECRET: ${{ secrets.AZURE_CLIENT_SECRET }}
        continue-on-error: true

      - name: Upload drift report
        if: steps.drift.outcome == 'failure'
        uses: actions/upload-artifact@v4
        with:
          name: drift-report-${{ matrix.target }}
          path: drift-report.json

      - name: Notify on drift
        if: steps.drift.outcome == 'failure'
        run: |
          echo "::warning::Drift detected in ${{ matrix.target }} environment. Review drift-report artifact."
```

## Resolving drift

Once drift is detected, you have two options depending on which version of the truth you want to keep.

### Option 1: Overwrite the workspace (bundle wins)

If the bundle definition is correct and the workspace should match it, redeploy:

```bash
fab-bundle deploy --target dev -y
```

This pushes the bundle definitions to the workspace, overwriting any manual changes. Added items that are not in the bundle are left untouched (fab-bundle only manages resources it tracks).

### Option 2: Update the bundle to match the workspace

If the changes made in the workspace are intentional and should be preserved, update your `fabric.yml` to reflect the new state:

```bash
# Export the current workspace definitions to local files
fab-bundle export --target dev

# Review the exported changes, update fabric.yml as needed, then redeploy
fab-bundle deploy --target dev -y
```

For items that were added outside the bundle and should now be managed, use `fab-bundle bind`:

```bash
fab-bundle bind --item-id <item-guid> --resource-key new_notebook --target dev
```

For items that were deleted from the workspace and should also be removed from the bundle, delete the resource entry from `fabric.yml` and redeploy.

## Integration with the state file

Drift detection depends entirely on the state file. If no state file exists for a target (because you have never deployed to it), `fab-bundle drift` will return an error:

```
Error: No state file found for target 'prod'.
  Run 'fab-bundle deploy --target prod' or 'fab-bundle import --target prod' first.
```

When using a remote state backend (OneLake, Azure Blob, or ADLS), the drift command reads the remote state file so that any CI runner can check for drift without needing a local copy. See [State Management](state.md) for backend configuration.

The drift command never writes to the state file. Only `deploy`, `import`, `bind`, and `rollback` modify state.
