# Policy Enforcement

Policies are pre-deploy validation rules that catch problems before they reach a workspace. They are defined in the `policies` section of `fabric.yml` and are evaluated every time you run `fab-bundle validate` or `fab-bundle deploy`. If any policy is violated, the command exits with a non-zero status and prints the violations, preventing a bad deployment from going through.

## Defining policies

Add a `policies` block to your `fabric.yml`:

```yaml
policies:
  require_description: true
  naming_convention: snake_case
  max_notebook_size_kb: 500
  blocked_libraries:
    - "pandas<2.0"
    - "numpy<1.24"
```

Policies apply to all resources in the bundle. They are checked during validation, before any API calls are made.

## Built-in policy options

### `require_description`

Requires every resource to have a non-empty `description` field. This enforces documentation discipline across the project.

```yaml
policies:
  require_description: true
```

**Violation example:**

```
POLICY VIOLATION: require_description
  Resource 'ingest_to_bronze' (Notebook) is missing a description.
  Resource 'silver' (Lakehouse) is missing a description.
```

### `naming_convention`

Enforces a naming pattern for all resource keys. Supported values:

| Value | Pattern | Example |
|-------|---------|---------|
| `snake_case` | lowercase with underscores | `ingest_to_bronze` |
| `kebab-case` | lowercase with hyphens | `ingest-to-bronze` |
| `camelCase` | camelCase | `ingestToBronze` |
| `PascalCase` | PascalCase | `IngestToBronze` |

```yaml
policies:
  naming_convention: snake_case
```

**Violation example:**

```
POLICY VIOLATION: naming_convention (expected: snake_case)
  Resource 'IngestToBronze' does not match snake_case.
  Resource 'my-lakehouse' does not match snake_case.
```

You can also provide a custom regex pattern:

```yaml
policies:
  naming_convention:
    pattern: "^[a-z][a-z0-9_]{2,48}$"
    message: "Names must be lowercase, start with a letter, and be 3-49 characters."
```

### `max_notebook_size_kb`

Sets a maximum file size for notebook definitions in kilobytes. This prevents accidentally committing notebooks with large embedded outputs or data.

```yaml
policies:
  max_notebook_size_kb: 500
```

**Violation example:**

```
POLICY VIOLATION: max_notebook_size_kb (limit: 500 KB)
  Notebook 'exploration' is 2,340 KB. Strip outputs before committing.
```

### `blocked_libraries`

Prevents deployments that depend on specific library versions. Useful for blocking known-vulnerable or deprecated packages. Each entry is a pip-style version specifier.

```yaml
policies:
  blocked_libraries:
    - "pandas<2.0"
    - "numpy<1.24"
    - "requests==2.28.0"
```

This policy inspects `environment` resources that declare library dependencies. If any declared library matches a blocked specifier, validation fails.

**Violation example:**

```
POLICY VIOLATION: blocked_libraries
  Environment 'spark_env' declares 'pandas==1.5.3', which matches blocked specifier 'pandas<2.0'.
```

## Custom policy rules

For project-specific requirements that go beyond the built-in options, define custom rules:

```yaml
policies:
  custom:
    - name: no_hardcoded_connections
      description: "Connection strings must use variables or secrets, not hardcoded values."
      pattern: ".*\\.database\\.windows\\.net"
      scope: connections
      action: deny

    - name: require_lakehouse_prefix
      description: "All lakehouses must start with the project name."
      check: |
        for key, res in resources.items():
          if res.type == 'Lakehouse' and not key.startswith(bundle.name):
            fail(f"Lakehouse '{key}' must start with '{bundle.name}'")
```

Custom rules support two modes:

- **`pattern` + `scope`**: A regex is tested against values in the specified scope. If it matches, the `action` (`deny` or `warn`) is triggered.
- **`check`**: An inline Python expression evaluated against the bundle context. Call `fail(message)` to report a violation.

## Running policy checks

### During validation

```bash
fab-bundle validate
```

Validation always runs policies. If any policy is violated, the command exits with code `1` and prints all violations.

### Strict mode

The `--strict` flag promotes warnings to errors. Policies that normally produce warnings (such as custom rules with `action: warn`) will cause validation to fail:

```bash
fab-bundle validate --strict
```

This is recommended for CI/CD pipelines where you want zero tolerance for policy issues.

### During deployment

`fab-bundle deploy` runs validation automatically before making any API calls. If validation fails, deployment is aborted. You do not need to run `validate` separately before `deploy`.

## Full example output

```
$ fab-bundle validate --strict

Validating bundle: contoso-analytics (v1.0.0)

  Checking schema...                     OK
  Checking resource references...        OK
  Checking dependency cycles...          OK
  Checking policies...                   FAILED

  POLICY VIOLATIONS (3):

    1. require_description
       Resource 'staging' (Lakehouse) is missing a description.

    2. naming_convention (expected: snake_case)
       Resource 'MyNotebook' does not match snake_case.

    3. blocked_libraries
       Environment 'spark_env' declares 'pandas==1.5.3',
       which matches blocked specifier 'pandas<2.0'.

Validation failed: 3 policy violations.
```

## CI/CD integration

Use policy validation as a gate in your deployment pipeline. The non-zero exit code on failure will cause the CI job to fail, preventing the merge or deployment.

### GitHub Actions

```yaml
- name: Validate bundle
  run: fab-bundle validate --strict
```

### Azure DevOps

```yaml
- script: fab-bundle validate --strict
  displayName: 'Validate bundle (strict)'
```

### Pull request workflow

A typical pattern is to run `fab-bundle validate --strict` on every pull request so that policy violations are caught before code is merged:

```yaml
name: PR Validation

on:
  pull_request:
    paths:
      - 'fabric.yml'
      - 'notebooks/**'
      - 'sql/**'

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - run: pip install fabric-automation-bundles

      - name: Validate with strict policies
        run: fab-bundle validate --strict
```

No secrets are required for validation because it does not contact the Fabric API. It only parses and checks the local bundle definition.

## Recommended policy configuration

A solid starting point for most teams:

```yaml
policies:
  require_description: true
  naming_convention: snake_case
  max_notebook_size_kb: 500
  blocked_libraries:
    - "pandas<2.0"
```

Add custom rules as your project grows and you identify patterns that should be enforced organization-wide.
