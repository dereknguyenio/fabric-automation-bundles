# Service Principal Setup

A service principal (SP) is required for CI/CD deployments. It authenticates fab-bundle to the Fabric API without user interaction.

## 1. Create the App Registration

```bash
az ad app create --display-name "fab-bundle-cicd"
```

Note the `appId` from the output — this is your `AZURE_CLIENT_ID`.

## 2. Create a Client Secret

```bash
az ad app credential reset --id <appId> --append
```

Copy the `password` — this is your `AZURE_CLIENT_SECRET`. You cannot retrieve it later.

## 3. Create the Service Principal

```bash
az ad sp create --id <appId>
```

## 4. Get Your Tenant ID

```bash
az account show --query tenantId -o tsv
```

This is your `AZURE_TENANT_ID`.

## 5. Grant Fabric Workspace Access

The service principal needs **Contributor** or **Admin** role on each workspace it deploys to.

### Option A: Grant via Fabric Portal

1. Open the workspace in app.fabric.microsoft.com
2. Settings → Manage access
3. Add the service principal by name or app ID
4. Set role to **Contributor** (or **Admin** for security role management)

### Option B: Grant via fab-bundle

Add the SP to your fabric.yml security roles:

```yaml
security:
  roles:
    - name: cicd_deployer
      service_principal: "<appId>"
      workspace_role: admin
```

Then deploy once with your personal account to grant the SP access.

### Option C: Grant via API

```bash
# Get the SP object ID
SP_OBJECT_ID=$(az ad sp show --id <appId> --query id -o tsv)

# Grant workspace access (requires existing workspace)
az rest --method post \
  --url "https://api.fabric.microsoft.com/v1/workspaces/<workspaceId>/roleAssignments" \
  --resource "https://api.fabric.microsoft.com" \
  --body "{\"principal\": {\"id\": \"$SP_OBJECT_ID\", \"type\": \"ServicePrincipal\"}, \"role\": \"Admin\"}"
```

## 6. Configure CI/CD

### GitHub Actions

Go to repo Settings → Secrets and variables → Actions:

| Secret | Value |
|--------|-------|
| `AZURE_TENANT_ID` | Tenant GUID |
| `AZURE_CLIENT_ID` | App ID |
| `AZURE_CLIENT_SECRET` | Client secret |

### Azure DevOps

Go to Pipelines → Library → create a variable group:

| Variable | Value | Secret? |
|----------|-------|---------|
| `AZURE_TENANT_ID` | Tenant GUID | No |
| `AZURE_CLIENT_ID` | App ID | No |
| `AZURE_CLIENT_SECRET` | Client secret | Yes |

## 7. Test Locally

```bash
export AZURE_TENANT_ID="..."
export AZURE_CLIENT_ID="..."
export AZURE_CLIENT_SECRET="..."
fab-bundle deploy --target dev
```

## Minimum Permissions

The service principal needs:

| Permission | Why |
|-----------|-----|
| Fabric workspace Contributor/Admin | Create, update, delete items |
| Fabric API access | Authenticate to `api.fabric.microsoft.com` |
| Microsoft Graph (optional) | Resolve Entra group display names to GUIDs |

## Secret Rotation

Client secrets expire. Set a reminder to rotate before expiry:

```bash
# Create new secret
az ad app credential reset --id <appId> --append --end-date "2027-01-01"

# Update CI/CD secrets with the new value
# Delete the old secret from Azure Portal
```

## Managed Identity (Alternative)

For Azure-hosted runners, you can use managed identity instead of client secrets:

1. Enable managed identity on your Azure VM / App Service / AKS
2. Grant the managed identity workspace access (same as SP)
3. `DefaultAzureCredential` will automatically use the managed identity — no env vars needed

This is the most secure option for production CI/CD.
