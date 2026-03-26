# Environment Variables

## Authentication

| Variable | Required | Description |
|----------|----------|-------------|
| `AZURE_TENANT_ID` | For SP auth | Azure AD tenant GUID |
| `AZURE_CLIENT_ID` | For SP auth | Service principal app ID |
| `AZURE_CLIENT_SECRET` | For SP auth | Service principal client secret |

When these are set, `DefaultAzureCredential` uses `EnvironmentCredential` automatically. Otherwise falls back to `az login` session.

## fabric.yml Variables

Reference in fabric.yml with `${env.VARIABLE_NAME}`:

```yaml
resources:
  notebooks:
    etl:
      path: ./notebooks/etl.py
      parameters:
        db_host: "${env.DB_HOST}"
```

## Secret Variables

Reference with `${secret.NAME}`:

```yaml
targets:
  prod:
    variables:
      db_password: "${secret.DB_PASSWORD}"
```

Secrets are resolved from environment variables at deploy time. The `secret.` prefix is a convention — it reads from the same environment.

## KeyVault Variables

Reference with `${keyvault.VAULT_NAME.SECRET_NAME}`:

```yaml
connections:
  my_db:
    properties:
      password: "${keyvault.my-vault.db-password}"
```

Requires: `pip install fabric-automation-bundles[keyvault]`

## Bundle Variables

Built-in variables available in fabric.yml:

| Variable | Value |
|----------|-------|
| `${bundle.name}` | Bundle name from `bundle.name` |
| `${bundle.version}` | Bundle version from `bundle.version` |

## State Backend Config

For remote state (in fabric.yml):

```yaml
state:
  backend: onelake  # or: azureblob, adls, local
  config:
    workspace_id: "guid"      # OneLake
    lakehouse_id: "guid"      # OneLake
    account_name: "storage"   # azureblob / adls
    container_name: "state"   # azureblob
    filesystem: "state"       # adls
    account_key: "..."        # azureblob (optional, uses DefaultAzureCredential)
```
