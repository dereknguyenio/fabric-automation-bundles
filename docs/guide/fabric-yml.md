# fabric.yml Reference

The `fabric.yml` file is the single declarative definition for your Fabric project.

## Structure

```yaml
bundle:          # Project metadata
workspace:       # Default workspace config
variables:       # Variable definitions with defaults
resources:       # All Fabric resources
security:        # Role assignments
connections:     # Data source connections
policies:        # Validation rules
notifications:   # Deploy alerts
targets:         # Environment configs (dev/staging/prod)
include:         # Additional YAML files to merge
extends:         # Parent bundle to inherit from
```

## bundle

```yaml
bundle:
  name: my-project          # Required: unique identifier
  version: "1.0.0"          # Semver version
  description: "My project" # Optional description
  depends_on:               # Cross-bundle dependencies
    - ../shared/fabric.yml
```

## workspace

```yaml
workspace:
  capacity_id: "guid"       # Fabric capacity GUID
  name: my-workspace        # Display name (overridden by targets)
  description: "..."
  git_integration:           # Git sync config
    provider: github
    organization: my-org
    repository: my-repo
    branch: main
    directory: /
```

## targets

```yaml
targets:
  dev:
    default: true
    workspace:
      name: project-dev
      capacity_id: "dev-capacity-guid"
    variables:
      source_connection: "dev-conn-string"
    post_deploy:
      - run: smoke_test_notebook
        expect: success
        timeout: 300

  prod:
    workspace:
      name: project-prod
    run_as:
      service_principal: sp-fabric-prod
    deployment_strategy:
      type: canary
      canary_resources: [ingest_notebook]
```
