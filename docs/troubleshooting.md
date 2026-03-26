# Troubleshooting

Common errors and how to fix them.

## Authentication

### "DefaultAzureCredential failed to retrieve a token"

**Cause:** Not authenticated with Azure.

**Fix:**
```bash
# Interactive login
az login

# Or set service principal env vars
export AZURE_TENANT_ID="your-tenant-guid"
export AZURE_CLIENT_ID="your-client-guid"
export AZURE_CLIENT_SECRET="your-secret"
```

### "Invalid client secret provided"

**Cause:** The `AZURE_CLIENT_SECRET` value is wrong — you may have copied the Secret ID instead of the Secret Value.

**Fix:** Go to Azure Portal → App registrations → your app → Certificates & secrets → create a new secret → copy the **Value** (not the ID).

### "AADSTS7000215: Invalid client secret"

**Cause:** Same as above, or the secret has expired.

**Fix:** Create a new client secret and update your GitHub secrets / environment variables.

## Capacity

### "capacity_id is not a valid GUID"

**Cause:** The `capacity_id` in fabric.yml is not in the correct format.

**Fix:** Find your capacity GUID:
```bash
az rest --method get \
  --url "https://api.fabric.microsoft.com/v1/capacities" \
  --resource "https://api.fabric.microsoft.com"
```

Copy the `id` field (format: `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`).

### "Capacity not found" or deploy creates workspace but items fail

**Cause:** The capacity is paused/inactive, or you don't have access.

**Fix:** Check the Fabric Admin Portal → Capacities → ensure your capacity shows "Active".

## Item Creation

### "DisplayName is Invalid for ArtifactType"

**Cause:** Lakehouses, warehouses, and some other types cannot have hyphens or spaces in their names.

**Fix:** Use underscores instead of hyphens:
```yaml
# Wrong
lakehouses:
  bronze-lakehouse:  # ← hyphens not allowed

# Right
lakehouses:
  bronze_lakehouse:  # ← underscores only
```

### "ItemDisplayNameNotAvailableYet"

**Cause:** You recently deleted an item with the same name. Fabric reserves the name for a few minutes.

**Fix:** Wait 2-5 minutes and retry. fab-bundle automatically retries retriable errors, but if the wait exceeds the retry window, run deploy again.

### "NotebookId cannot be null"

**Cause:** Pipeline activities reference notebooks by ID, but the notebook wasn't found in the workspace.

**Fix:** Ensure notebooks are deployed before pipelines. fab-bundle handles this automatically via dependency ordering, but if you're creating a pipeline that references notebooks from a different bundle, deploy the notebooks first.

### "Artifact definition parts count should be 1"

**Cause:** Spark Job Definitions only accept a single definition part.

**Fix:** This was a bug in earlier versions. Update to the latest version: `pip install --upgrade fabric-automation-bundles`

### "InvalidDefinitionFormat"

**Cause:** The notebook definition format is not recognized by the Fabric API.

**Fix:** Ensure your notebook files are valid `.py` or `.ipynb` files. fab-bundle wraps `.py` files in ipynb format automatically.

### "MissingDefinition"

**Cause:** Semantic Models and Reports require definition files (TMDL/PBIR) that don't exist locally.

**Fix:**

- **Semantic Models:** Export TMDL files from Power BI Desktop or the Fabric portal, place in the `path` directory
- **Reports:** Export PBIR files from Power BI Desktop, place in the `path` directory
- Or remove these from fabric.yml and create them in the portal

### "The feature is not available"

**Cause:** The item type requires a capacity feature that's not enabled (e.g., dbt, EventSchemaSet).

**Fix:** Contact your Fabric admin to enable the feature, or remove the item from fabric.yml.

## OneLake Security

### "UniversalSecurityFeatureDisabledForArtifactType"

**Cause:** OneLake data access roles require the security feature to be enabled per-lakehouse.

**Fix:**

1. Open the lakehouse in the Fabric portal
2. Click **Manage OneLake security (preview)** in the ribbon
3. Enable the feature
4. Run `fab-bundle deploy` again

Note: This is a per-item setting, not a tenant admin setting.

## Environment

### "There is a publish operation in progress"

**Cause:** A previous environment publish is still running. Environment publishes can take 5-10 minutes.

**Fix:** Wait for the current publish to complete. Check status in the Fabric portal under the environment's details. fab-bundle publishes are fire-and-forget — the deploy itself succeeds.

## Variables

### "Unresolved variables: ${var.missing}"

**Cause:** A variable referenced in fabric.yml has no value defined.

**Fix:** Either:

- Add a default value: `variables: { missing: { default: "value" } }`
- Set it in the target: `targets: { dev: { variables: { missing: "value" } } }`
- Set the environment variable if using `${env.MISSING}`
- Set the secret if using `${secret.MISSING}`

In deploy mode, unresolved variables cause a hard failure. In validate mode, use `--strict` to catch them.

## Deployment

### "Deployment locked by user@host"

**Cause:** A previous deployment didn't release its lock (e.g., crashed mid-deploy).

**Fix:**
```bash
fab-bundle deploy --target dev --force  # Override the lock
```

Or manually delete the lock file:
```bash
rm .fab-bundle/lock-dev.json
```

### Partial deployment / rollback

**Cause:** Some items failed during creation, triggering a rollback of already-created items.

**Fix:** Check the error messages for the failed items. Fix the issues (naming, definitions, permissions) and run deploy again. Successfully created items from previous runs will show as "update" instead of "create".

## CI/CD

### GitHub Actions: "Process completed with exit code 1"

**Cause:** Check the step that failed in the Actions log. Common causes:

- Authentication: secrets not configured or expired
- Capacity: not active or wrong GUID
- Naming: hyphens in resource names

**Fix:** Check the full log output. Run `fab-bundle doctor` locally to diagnose.

### "fab-bundle: command not found" in CI

**Cause:** fab-bundle not installed in the CI environment.

**Fix:** Add `pip install fabric-automation-bundles` before running fab-bundle commands.

## Getting Help

- Run `fab-bundle doctor` to diagnose common issues
- Check [GitHub Issues](https://github.com/dereknguyenio/fabric-automation-bundles/issues) for known bugs
- File a new issue with the full error message and your fabric.yml (redact secrets)
