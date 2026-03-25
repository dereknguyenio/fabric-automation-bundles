# Targets & Variables

## Targets
Define environment-specific configuration:

```yaml
targets:
  dev:
    default: true
    workspace:
      name: project-dev
    variables:
      db_host: dev-server.database.windows.net

  prod:
    workspace:
      name: project-prod
    variables:
      db_host: prod-server.database.windows.net
```

## Variables

```yaml
variables:
  db_host:
    description: "Database server hostname"
    default: "localhost"
```

Use with `${var.db_host}` in any string value.

## Environment Variables

Access environment variables with `${env.MY_VAR}`.

## Bundle Variables

Access bundle metadata with `${bundle.name}` and `${bundle.version}`.
