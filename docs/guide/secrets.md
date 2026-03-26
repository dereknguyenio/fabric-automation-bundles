# Secrets Management

Secrets such as database passwords, API keys, and connection strings should never appear in plain text in `fabric.yml` or be committed to source control. fab-bundle supports two mechanisms for injecting secrets at deploy time: environment variable references and Azure Key Vault integration.

## Environment variable secrets

Use the `${secret.NAME}` syntax to reference an environment variable. At deploy time, fab-bundle reads the value from the environment and substitutes it into the configuration.

```yaml
connections:
  my_database:
    type: sql_server
    endpoint: "${secret.DB_HOST}"
    properties:
      username: "${secret.DB_USERNAME}"
      password: "${secret.DB_PASSWORD}"

  my_api:
    type: rest_api
    endpoint: "https://api.example.com"
    properties:
      api_key: "${secret.API_KEY}"
```

Before deploying, set the environment variables:

```bash
export DB_HOST="myserver.database.windows.net"
export DB_USERNAME="svc_fabric"
export DB_PASSWORD="correct-horse-battery-staple"
export API_KEY="sk-abc123..."

fab-bundle deploy --target prod -y
```

If a referenced secret is missing from the environment, fab-bundle will fail with a clear error before making any API calls:

```
Error: Secret 'DB_PASSWORD' is not set.
  Set the environment variable DB_PASSWORD or use a KeyVault reference.
```

## Azure Key Vault integration

For teams that manage secrets centrally in Azure Key Vault, use the `${keyvault.VAULT_NAME.SECRET_NAME}` syntax. fab-bundle retrieves the secret value from Key Vault at deploy time using `DefaultAzureCredential`.

```yaml
connections:
  my_database:
    type: sql_server
    endpoint: "${keyvault.contoso-kv.db-host}"
    properties:
      username: "${keyvault.contoso-kv.db-username}"
      password: "${keyvault.contoso-kv.db-password}"

  my_api:
    type: rest_api
    endpoint: "https://api.example.com"
    properties:
      api_key: "${keyvault.contoso-kv.api-key}"
```

### Prerequisites

1. Install the Key Vault extra:

    ```bash
    pip install fabric-automation-bundles[keyvault]
    ```

2. Grant the deploying identity (your user account or the CI/CD service principal) the **Key Vault Secrets User** role on the Key Vault, or assign a Key Vault access policy with **Get** permission on secrets.

3. The Key Vault must be network-accessible from the machine running `fab-bundle`. If the vault uses private endpoints, ensure the CI/CD runner can reach it.

### Versioned secrets

To reference a specific version of a Key Vault secret, append the version ID:

```yaml
password: "${keyvault.contoso-kv.db-password.a1b2c3d4e5f6}"
```

If no version is specified, the current (latest) version is used.

## How secrets are resolved at deploy time

Secret resolution happens during the plan and deploy phases, after the YAML is parsed but before any API calls are made.

1. fab-bundle scans all string values in the resolved configuration for `${secret.*}` and `${keyvault.*}` patterns.
2. For `${secret.NAME}`, it reads the environment variable `NAME`. If the variable is not set, deployment fails.
3. For `${keyvault.VAULT.SECRET}`, it calls the Azure Key Vault API to retrieve the secret value. If the vault or secret does not exist, or if the identity lacks permission, deployment fails.
4. The resolved values are used in the Fabric API calls but are never written to the state file, logs, or plan output. fab-bundle redacts secret values in all output.

## Secrets in CI/CD

### GitHub Actions

Store secrets in your repository settings (**Settings > Secrets and variables > Actions**) or at the environment level. Reference them as environment variables in your workflow:

```yaml
- name: Deploy to production
  run: fab-bundle deploy --target prod -y
  env:
    AZURE_TENANT_ID: ${{ secrets.AZURE_TENANT_ID }}
    AZURE_CLIENT_ID: ${{ secrets.AZURE_CLIENT_ID }}
    AZURE_CLIENT_SECRET: ${{ secrets.AZURE_CLIENT_SECRET }}
    DB_HOST: ${{ secrets.DB_HOST }}
    DB_USERNAME: ${{ secrets.DB_USERNAME }}
    DB_PASSWORD: ${{ secrets.DB_PASSWORD }}
    API_KEY: ${{ secrets.API_KEY }}
```

GitHub Actions automatically masks secret values in logs. Combined with fab-bundle's own redaction, secrets will not appear in workflow output.

If you use Key Vault references instead of environment variable secrets, you only need the three Azure authentication secrets. fab-bundle will retrieve everything else from Key Vault.

### Azure DevOps

Store secrets in a variable group (**Pipelines > Library**). Link the variable group to your pipeline and mark sensitive values as secret:

```yaml
variables:
  - group: fabric-credentials
  - group: fabric-secrets  # Contains DB_HOST, DB_PASSWORD, etc.

steps:
  - script: fab-bundle deploy --target prod -y
    displayName: 'Deploy to production'
    env:
      AZURE_TENANT_ID: $(AZURE_TENANT_ID)
      AZURE_CLIENT_ID: $(AZURE_CLIENT_ID)
      AZURE_CLIENT_SECRET: $(AZURE_CLIENT_SECRET)
      DB_HOST: $(DB_HOST)
      DB_PASSWORD: $(DB_PASSWORD)
```

Azure DevOps variable groups can be linked directly to an Azure Key Vault, which provides automatic secret rotation without updating pipeline variables.

## Best practices

**Never commit secrets to source control.** Even if you remove them later, they remain in git history.

**Use `.gitignore` to prevent accidental commits.** The `fab-bundle init` command creates a `.gitignore` that includes common patterns:

```gitignore
# fab-bundle state (contains workspace IDs, item IDs)
.fab-bundle/

# Environment files with secrets
.env
.env.*

# Azure credentials
*.pem
*.key
```

**Prefer Key Vault over environment variables for production.** Key Vault provides audit logging, access policies, automatic rotation, and centralized management. Environment variables are simpler for development but harder to audit and rotate.

**Use separate secrets per environment.** Do not share database credentials between dev and prod. Use per-target variables that reference different secrets:

```yaml
targets:
  dev:
    variables:
      db_password: "${secret.DEV_DB_PASSWORD}"
  prod:
    variables:
      db_password: "${secret.PROD_DB_PASSWORD}"
```

**Rotate secrets regularly.** Set calendar reminders for service principal client secret expiry. Key Vault secrets can be configured with expiry dates and rotation policies.

## Full YAML example

```yaml
bundle:
  name: contoso-analytics

variables:
  db_host:
    description: "SQL Server hostname"
  db_password:
    description: "SQL Server password"

connections:
  warehouse_db:
    type: sql_server
    endpoint: "${var.db_host}"
    properties:
      username: "${keyvault.contoso-kv.db-username}"
      password: "${var.db_password}"

  external_api:
    type: rest_api
    endpoint: "https://api.partner.com/v2"
    properties:
      api_key: "${keyvault.contoso-kv.partner-api-key}"

targets:
  dev:
    default: true
    workspace:
      name: contoso-analytics-dev
    variables:
      db_host: "dev-sql.database.windows.net"
      db_password: "${secret.DEV_DB_PASSWORD}"

  prod:
    workspace:
      name: contoso-analytics-prod
    variables:
      db_host: "prod-sql.database.windows.net"
      db_password: "${keyvault.contoso-kv.prod-db-password}"
```

In this example, dev uses an environment variable for the database password (simple for local development), while prod retrieves it from Key Vault (auditable, centrally managed).
