# ${{project_name}}

A Microsoft Fabric project managed by [Fabric Automation Bundles](https://github.com/dereknguyenio/fabric-automation-bundles).

## Project Structure

```
${{project_name}}/
├── fabric.yml              # Bundle definition — all resources, targets, security
├── src/                    # Notebooks and source code
│   └── sample_notebook.py  # Sample PySpark notebook
├── resources/              # Pipeline configs, SQL scripts, agent instructions
├── tests/                  # Validation tests
│   └── test_validate.py    # Checks fabric.yml is valid
└── README.md               # This file
```

## Getting Started

### Prerequisites

- Python 3.10+
- Azure CLI (`az login`)
- A Microsoft Fabric capacity

### Setup

```bash
# Install fab-bundle
pip install fabric-automation-bundles

# Find your capacity GUID
az rest --method get \
  --url "https://api.fabric.microsoft.com/v1/capacities" \
  --resource "https://api.fabric.microsoft.com"

# Update fabric.yml with your capacity_id
```

### Deploy

```bash
fab-bundle validate          # Check for errors
fab-bundle plan -t dev       # Preview changes
fab-bundle deploy -t dev     # Deploy to dev workspace
```

### Develop

Edit notebooks in `src/`, then redeploy:

```bash
fab-bundle deploy -t dev
```

Or use the [Fabric VS Code Extension](https://learn.microsoft.com/en-us/fabric/data-engineering/setup-vs-code-extension) to edit and run notebooks on remote Spark compute.

### CI/CD

See the [CI/CD guide](https://dereknguyenio.github.io/fabric-automation-bundles/cicd/overview/) for GitHub Actions and Azure DevOps templates.

## Commands

| Command | Description |
|---------|-------------|
| `fab-bundle validate` | Validate fabric.yml |
| `fab-bundle plan -t dev` | Preview changes |
| `fab-bundle deploy -t dev` | Deploy to dev |
| `fab-bundle destroy -t dev` | Tear down dev |
| `fab-bundle status -t dev` | Show deployed resources |
| `fab-bundle drift -t dev` | Detect portal changes |
| `fab-bundle run <notebook>` | Run a notebook |
