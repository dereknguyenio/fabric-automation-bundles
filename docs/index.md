# Fabric Automation Bundles

**Declarative project definitions for Microsoft Fabric.**

Define your entire Fabric project in a single `fabric.yml` — lakehouses, notebooks, pipelines, semantic models, Data Agents, security roles, and environment targets — then validate, plan, and deploy with a single command.

```bash
pip install fabric-automation-bundles
fab-bundle init --template medallion --name my-project
fab-bundle deploy -t dev
```

## Why?

Microsoft Fabric has no single declarative project definition. The Fabric CLI can export/import items, `fabric-cicd` can deploy across workspaces, and Terraform can provision infrastructure — but none of them describe:

- What resources your project needs
- How those resources depend on each other
- How configuration varies across environments
- What security roles and permissions are required
- How to deploy everything in the correct order

**Fabric Automation Bundles fills that gap.**

## Features

- **12 resource types** — Lakehouses, Notebooks, Pipelines, Warehouses, Semantic Models, Reports, Environments, Data Agents, Eventhouses, Eventstreams, ML Models, ML Experiments
- **Dependency resolution** — automatic topological sort for deployment ordering
- **Multi-environment** — dev, staging, prod targets with variable overrides
- **State management** — tracks deployed resources, detects drift
- **Rollback support** — deployment history with point-in-time rollback
- **Security** — Entra ID group/user/SP role assignments with Graph API resolution
- **Secrets** — Environment variables and Azure KeyVault integration
- **CI/CD ready** — GitHub Actions and Azure DevOps templates included
- **Policy enforcement** — configurable pre-deploy validation rules
