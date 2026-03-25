# Installation

## Requirements

- Python 3.10+
- Azure CLI (`az`) for authentication
- A Microsoft Fabric capacity

## Install from PyPI

```bash
pip install fabric-automation-bundles
```

## Optional: KeyVault support

```bash
pip install fabric-automation-bundles[keyvault]
```

## Verify installation

```bash
fab-bundle --version
fab-bundle doctor
```

## Authentication

Fabric Automation Bundles uses `azure-identity` for authentication:

```bash
# Interactive (development)
az login
fab-bundle deploy -t dev

# Service Principal (CI/CD)
export AZURE_TENANT_ID=...
export AZURE_CLIENT_ID=...
export AZURE_CLIENT_SECRET=...
fab-bundle deploy -t prod -y
```
