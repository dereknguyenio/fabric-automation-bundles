# Targets and Variables

Targets and variables are how fab-bundle manages environment-specific configuration. Targets represent deployment environments (dev, staging, prod), and variables hold the values that differ between them.

## What targets are

A target is a named deployment environment. Each target maps to a specific Fabric workspace and can override variables, authentication, post-deployment checks, and deployment strategy. When you run `fab-bundle deploy -t prod`, fab-bundle reads the `prod` target configuration and deploys to the workspace defined there.

```yaml
targets:
  dev:
    default: true
    workspace:
      name: contoso-analytics-dev
      capacity_id: "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

  staging:
    workspace:
      name: contoso-analytics-staging
      capacity_id: "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

  prod:
    workspace:
      name: contoso-analytics-prod
      capacity_id: "ffffffff-gggg-hhhh-iiii-jjjjjjjjjjjj"
```

Each target can override any property from the top-level `workspace` block. Target-level settings take precedence over top-level defaults.

## Default target

Exactly one target should have `default: true`. This is the target used when you omit the `-t` flag:

```bash
# Uses the default target (dev in the example above)
fab-bundle deploy

# Explicitly specify a target
fab-bundle deploy -t prod
```

If no default is set and no `-t` flag is provided, fab-bundle will prompt you to select a target.

## Variable definitions

Variables are declared at the top level with an optional description, type, and default value. They define what configuration knobs exist in the bundle.

```yaml
variables:
  db_host:
    description: "SQL Server hostname"
    type: string
    default: "localhost"

  db_port:
    description: "SQL Server port"
    type: number
    default: 1433

  enable_logging:
    description: "Enable verbose logging in notebooks"
    type: boolean
    default: false

  allowed_regions:
    description: "Regions allowed for data residency"
    type: list
    default: ["eastus", "westus2"]
```

### Supported types

| Type | Description | Example Default |
|------|-------------|-----------------|
| `string` | Text value | `"localhost"` |
| `number` | Integer or float | `1433` |
| `boolean` | True or false | `false` |
| `list` | Array of values | `["eastus", "westus2"]` |

If `type` is omitted, fab-bundle infers the type from the `default` value. If neither is provided, the variable is treated as a required string with no default.

## Variable substitution syntax

Use `${...}` syntax to reference variables anywhere a string value is expected in `fabric.yml`.

### `${var.name}` -- Bundle variables

References a variable defined in the `variables` section. The value comes from the variable's default or from a target-level override.

```yaml
connections:
  my_db:
    type: sql_server
    endpoint: "${var.db_host}:${var.db_port}"
```

### `${env.NAME}` -- Environment variables

Reads a value from the operating system environment at deploy time. Useful for values that vary per machine or CI runner but are not secrets.

```yaml
bundle:
  name: analytics
  version: "${env.BUILD_VERSION}"
```

### `${secret.NAME}` -- Secret references

Reads a secret from the environment. Functionally identical to `${env.NAME}` but signals intent: fab-bundle redacts these values in plan output and logs. See [Secrets Management](secrets.md) for details.

```yaml
connections:
  my_db:
    properties:
      password: "${secret.DB_PASSWORD}"
```

### `${bundle.name}` and `${bundle.version}` -- Bundle metadata

References the bundle's own metadata. Useful for generating resource names that include the project name or version.

```yaml
resources:
  lakehouses:
    data_lake:
      display_name: "${bundle.name}-lake"
      description: "Data lake for ${bundle.name} v${bundle.version}"
```

### Combining substitutions

Substitution expressions can be combined within a single string:

```yaml
connections:
  my_db:
    endpoint: "${var.db_host}:${var.db_port}"
    properties:
      database: "${bundle.name}_${var.environment_suffix}"
```

## Per-target variable overrides

Each target can override any variable. Target-level values take precedence over the default.

```yaml
variables:
  db_host:
    description: "SQL Server hostname"
    default: "localhost"
  environment_suffix:
    description: "Suffix for environment-specific resource names"
    default: "dev"

targets:
  dev:
    default: true
    workspace:
      name: contoso-analytics-dev
    variables:
      db_host: "dev-sql.database.windows.net"
      environment_suffix: "dev"

  staging:
    workspace:
      name: contoso-analytics-staging
    variables:
      db_host: "staging-sql.database.windows.net"
      environment_suffix: "staging"

  prod:
    workspace:
      name: contoso-analytics-prod
    variables:
      db_host: "prod-sql.database.windows.net"
      environment_suffix: "prod"
```

When deploying to `prod`, `${var.db_host}` resolves to `prod-sql.database.windows.net`.

## `run_as` -- Service principal per target

Each target can specify a different service principal for deployment. This is useful when dev and prod workspaces are in different tenants or when you want to enforce least-privilege access.

```yaml
targets:
  dev:
    default: true
    workspace:
      name: contoso-analytics-dev
    run_as:
      service_principal: sp-fabric-dev

  prod:
    workspace:
      name: contoso-analytics-prod
    run_as:
      service_principal: sp-fabric-prod
```

The `service_principal` value is the display name of a service principal in Entra ID. fab-bundle resolves it to a GUID via the Microsoft Graph API. When `run_as` is set, fab-bundle authenticates as that service principal for the deployment. The corresponding credentials (`AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`) must be available in the environment.

If `run_as` is omitted, fab-bundle uses whatever identity is available through `DefaultAzureCredential` (your logged-in account, a managed identity, or the environment variables).

## `post_deploy` -- Validation checks

Run automated checks after a deployment succeeds. This is useful for smoke tests that verify the deployment actually works.

```yaml
targets:
  dev:
    workspace:
      name: contoso-analytics-dev
    post_deploy:
      - run: smoke_test_notebook
        expect: success
        timeout: 300

      - run: data_quality_checks
        expect: success
        timeout: 600
```

| Field | Description |
|-------|-------------|
| `run` | The resource key of a notebook or pipeline to execute |
| `expect` | Expected outcome: `success` or `completed` |
| `timeout` | Maximum wait time in seconds before the check is marked as failed |

If any `post_deploy` check fails, fab-bundle reports the failure but does not roll back the deployment. Use `fab-bundle rollback` to revert if needed.

## `deployment_strategy` -- Canary deployments

For production targets, you can deploy a subset of resources first (canary) before deploying everything. If the canary resources fail, the full deployment is halted.

```yaml
targets:
  prod:
    workspace:
      name: contoso-analytics-prod
    deployment_strategy:
      type: canary
      canary_resources:
        - ingest_to_bronze
        - bronze_to_silver
      validation:
        - run: smoke_test_notebook
          expect: success
          timeout: 300
```

The canary deployment flow:

1. Deploy only the resources listed in `canary_resources`.
2. Run the `validation` checks.
3. If validation passes, deploy all remaining resources.
4. If validation fails, stop. The canary resources are rolled back.

## Full YAML example

```yaml
bundle:
  name: contoso-analytics
  version: "2.1.0"

variables:
  db_host:
    description: "SQL Server hostname"
    type: string
    default: "localhost"
  db_port:
    description: "SQL Server port"
    type: number
    default: 1433
  enable_logging:
    description: "Enable verbose notebook logging"
    type: boolean
    default: false
  environment_suffix:
    description: "Environment name for resource naming"
    type: string

workspace:
  capacity_id: "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

resources:
  lakehouses:
    bronze:
      display_name: "${bundle.name}_bronze_${var.environment_suffix}"
      description: "Raw data landing zone"
    silver:
      display_name: "${bundle.name}_silver_${var.environment_suffix}"
      description: "Cleansed and conformed data"

  notebooks:
    ingest_to_bronze:
      display_name: "ingest_to_bronze"
      description: "Ingest raw data into the bronze lakehouse"
      path: notebooks/ingest_to_bronze.py
      default_lakehouse: bronze

connections:
  warehouse_db:
    type: sql_server
    endpoint: "${var.db_host}:${var.db_port}"
    properties:
      password: "${secret.DB_PASSWORD}"

targets:
  dev:
    default: true
    workspace:
      name: contoso-analytics-dev
    variables:
      db_host: "dev-sql.database.windows.net"
      environment_suffix: "dev"
      enable_logging: true
    post_deploy:
      - run: smoke_test_notebook
        expect: success
        timeout: 300

  staging:
    workspace:
      name: contoso-analytics-staging
    variables:
      db_host: "staging-sql.database.windows.net"
      environment_suffix: "staging"

  prod:
    workspace:
      name: contoso-analytics-prod
      capacity_id: "ffffffff-gggg-hhhh-iiii-jjjjjjjjjjjj"
    variables:
      db_host: "prod-sql.database.windows.net"
      environment_suffix: "prod"
      enable_logging: false
    run_as:
      service_principal: sp-fabric-prod
    deployment_strategy:
      type: canary
      canary_resources: [ingest_to_bronze]
      validation:
        - run: smoke_test_notebook
          expect: success
          timeout: 300
    post_deploy:
      - run: data_quality_checks
        expect: success
        timeout: 600
```
