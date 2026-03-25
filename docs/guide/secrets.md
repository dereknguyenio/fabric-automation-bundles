# Secrets Management

## Environment Variable Secrets

```yaml
connections:
  my_db:
    type: sql_server
    endpoint: "${secret.DB_HOST}"
    properties:
      password: "${secret.DB_PASSWORD}"
```

Set the env vars before deploying:
```bash
export DB_HOST=myserver.database.windows.net
export DB_PASSWORD=secret123
fab-bundle deploy -t prod
```

## Azure KeyVault

```yaml
connections:
  my_db:
    properties:
      password: "${keyvault.my-vault.db-password}"
```

Install KeyVault support: `pip install fabric-automation-bundles[keyvault]`
