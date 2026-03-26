# Azure DevOps

## Pipeline Setup

Create `azure-pipelines.yml` in your repo root:

```yaml
trigger:
  branches:
    include:
      - main
  paths:
    include:
      - fabric.yml
      - notebooks/*
      - sql/*
      - agent/*

pool:
  vmImage: 'ubuntu-latest'

variables:
  pythonVersion: '3.12'

stages:
  # ──────────────────────────────────────────
  # Validate (runs on every PR and push)
  # ──────────────────────────────────────────
  - stage: Validate
    displayName: 'Validate Bundle'
    jobs:
      - job: Validate
        steps:
          - task: UsePythonVersion@0
            inputs:
              versionSpec: '$(pythonVersion)'

          - script: pip install fabric-automation-bundles
            displayName: 'Install fab-bundle'

          - script: fab-bundle validate
            displayName: 'Validate fabric.yml'

          - script: fab-bundle plan -t dev
            displayName: 'Plan dev deployment'
            env:
              AZURE_TENANT_ID: $(AZURE_TENANT_ID)
              AZURE_CLIENT_ID: $(AZURE_CLIENT_ID)
              AZURE_CLIENT_SECRET: $(AZURE_CLIENT_SECRET)

  # ──────────────────────────────────────────
  # Deploy to Dev (auto on merge to main)
  # ──────────────────────────────────────────
  - stage: DeployDev
    displayName: 'Deploy to Dev'
    dependsOn: Validate
    condition: and(succeeded(), eq(variables['Build.SourceBranch'], 'refs/heads/main'))
    jobs:
      - deployment: DeployDev
        environment: 'dev'
        strategy:
          runOnce:
            deploy:
              steps:
                - checkout: self

                - task: UsePythonVersion@0
                  inputs:
                    versionSpec: '$(pythonVersion)'

                - script: pip install fabric-automation-bundles
                  displayName: 'Install fab-bundle'

                - script: fab-bundle deploy -t dev -y
                  displayName: 'Deploy to dev'
                  env:
                    AZURE_TENANT_ID: $(AZURE_TENANT_ID)
                    AZURE_CLIENT_ID: $(AZURE_CLIENT_ID)
                    AZURE_CLIENT_SECRET: $(AZURE_CLIENT_SECRET)

                - script: fab-bundle status -t dev
                  displayName: 'Check status'
                  env:
                    AZURE_TENANT_ID: $(AZURE_TENANT_ID)
                    AZURE_CLIENT_ID: $(AZURE_CLIENT_ID)
                    AZURE_CLIENT_SECRET: $(AZURE_CLIENT_SECRET)

  # ──────────────────────────────────────────
  # Deploy to Test (with quality gate)
  # ──────────────────────────────────────────
  - stage: DeployTest
    displayName: 'Deploy to Test'
    dependsOn: DeployDev
    jobs:
      - deployment: DeployTest
        environment: 'test'
        strategy:
          runOnce:
            deploy:
              steps:
                - checkout: self

                - task: UsePythonVersion@0
                  inputs:
                    versionSpec: '$(pythonVersion)'

                - script: pip install fabric-automation-bundles
                  displayName: 'Install fab-bundle'

                - script: fab-bundle deploy -t test -y
                  displayName: 'Deploy to test'
                  env:
                    AZURE_TENANT_ID: $(AZURE_TENANT_ID)
                    AZURE_CLIENT_ID: $(AZURE_CLIENT_ID)
                    AZURE_CLIENT_SECRET: $(AZURE_CLIENT_SECRET)

  # ──────────────────────────────────────────
  # Deploy to Prod (manual approval)
  # ──────────────────────────────────────────
  - stage: DeployProd
    displayName: 'Deploy to Production'
    dependsOn: DeployTest
    jobs:
      - deployment: DeployProd
        environment: 'production'  # Configure approval in ADO Environments
        strategy:
          runOnce:
            deploy:
              steps:
                - checkout: self

                - task: UsePythonVersion@0
                  inputs:
                    versionSpec: '$(pythonVersion)'

                - script: pip install fabric-automation-bundles
                  displayName: 'Install fab-bundle'

                - script: fab-bundle deploy -t prod -y
                  displayName: 'Deploy to production'
                  env:
                    AZURE_TENANT_ID: $(AZURE_TENANT_ID)
                    AZURE_CLIENT_ID: $(AZURE_CLIENT_ID)
                    AZURE_CLIENT_SECRET: $(AZURE_CLIENT_SECRET)

                - script: fab-bundle status -t prod
                  displayName: 'Verify deployment'
                  env:
                    AZURE_TENANT_ID: $(AZURE_TENANT_ID)
                    AZURE_CLIENT_ID: $(AZURE_CLIENT_ID)
                    AZURE_CLIENT_SECRET: $(AZURE_CLIENT_SECRET)
```

## Setup

### 1. Create a Variable Group

Go to Pipelines → Library → create a variable group named `fabric-credentials`:

| Variable | Value | Secret? |
|----------|-------|---------|
| `AZURE_TENANT_ID` | Your Entra tenant GUID | No |
| `AZURE_CLIENT_ID` | Service principal app ID | No |
| `AZURE_CLIENT_SECRET` | Service principal secret | Yes |

### 2. Create Environments

Go to Pipelines → Environments → create:

- **dev** — no approvals
- **test** — no approvals
- **production** — add required approvers

### 3. Create the Pipeline

Go to Pipelines → New Pipeline → select your repo → choose "Existing Azure Pipelines YAML file" → select `azure-pipelines.yml`.
