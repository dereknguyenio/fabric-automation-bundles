# Installation

This topic describes how to install, configure, and verify Fabric Automation Bundles on your local machine or CI/CD environment.

---

## Prerequisites

Before you install Fabric Automation Bundles, make sure your environment meets the following requirements.

### System requirements

| Requirement | Minimum version | Notes |
|---|---|---|
| **Python** | 3.10 | Python 3.10, 3.11, 3.12, and 3.13 are supported. |
| **Azure CLI** | 2.50+ | Required for interactive authentication. Install from [https://aka.ms/installazurecli](https://aka.ms/installazurecli). |
| **pip** | 21.0+ | Ships with Python. Upgrade with `pip install --upgrade pip`. |
| **Operating system** | Windows 10+, macOS 12+, Linux (glibc 2.17+) | Any OS that runs CPython 3.10+. |

### Microsoft Fabric requirements

| Requirement | Details |
|---|---|
| **Fabric capacity** | An active Fabric capacity (F2 or higher). You need the capacity GUID from the Fabric admin portal. |
| **Workspace permissions** | Admin or Contributor role on the target workspace, or permissions to create new workspaces. |
| **Entra ID (Azure AD) access** | The authenticated identity must have Fabric API permissions. |

> **Important**
>
> Fabric Automation Bundles calls the Microsoft Fabric REST API. If your organization uses Conditional Access policies or tenant restrictions, confirm that API access is allowed for your identity before proceeding.

---

## Step 1: Install the package

### Basic installation

Install the core package from PyPI:

```bash
pip install fabric-automation-bundles
```

This installs the CLI (`fab-bundle`) and all core dependencies: `click`, `pydantic`, `pyyaml`, `rich`, `azure-identity`, `requests`, `jinja2`, and `jsonschema`.

### Installation with extras

Fabric Automation Bundles provides optional extras for specific use cases. Install them by specifying the extra name in brackets.

| Extra | Command | Use case |
|---|---|---|
| `keyvault` | `pip install fabric-automation-bundles[keyvault]` | Resolve `${secret.KEY_NAME}` variables from Azure Key Vault. Installs `azure-keyvault-secrets`. |
| `mcp` | `pip install fabric-automation-bundles[mcp]` | Enable the MCP (Model Context Protocol) server for AI-assisted bundle authoring. Installs `mcp>=1.0.0`. |
| `remote-state` | `pip install fabric-automation-bundles[remote-state]` | Store deployment state in Azure Blob Storage or ADLS Gen2 instead of local files. Installs `azure-storage-blob` and `azure-storage-file-datalake`. |
| `dev` | `pip install fabric-automation-bundles[dev]` | Development dependencies for contributing. Installs `pytest`, `pytest-cov`, `ruff`, `mypy`, and `black`. |

To install multiple extras at once:

```bash
pip install "fabric-automation-bundles[keyvault,remote-state]"
```

To install all extras:

```bash
pip install "fabric-automation-bundles[keyvault,mcp,remote-state,dev]"
```

### Install from source

To install from the GitHub repository (for example, to use an unreleased feature):

```bash
pip install git+https://github.com/dereknguyenio/fabric-automation-bundles.git
```

---

## Step 2: Verify the installation

### Check the version

```bash
fab-bundle --version
```

**Example output:**

```
fabric-automation-bundles, version 1.0.0b2
```

### Run the diagnostic check

The `doctor` command validates your environment, dependencies, authentication, and Fabric API connectivity in a single step:

```bash
fab-bundle doctor
```

**Example output (healthy environment):**

```
fab-bundle doctor

  ✓ Python 3.12.4 (>=3.10 required)
  ✓ Package: pydantic
  ✓ Package: click
  ✓ Package: rich
  ✓ Package: yaml
  ✓ Package: requests
  ✓ Package: azure.identity
  ✓ Azure CLI installed
  ✓ Azure CLI authenticated
  ✓ Fabric API reachable
  ✓ fabric.yml found
  ✓ Bundle validates

  11 passed, 0 failed
```

**Example output (problems detected):**

```
fab-bundle doctor

  ✓ Python 3.12.4 (>=3.10 required)
  ✓ Package: pydantic
  ✓ Package: click
  ✓ Package: rich
  ✓ Package: yaml
  ✓ Package: requests
  ✓ Package: azure.identity
  ✓ Azure CLI installed
  ✗ Azure CLI authenticated
  ✗ Fabric API reachable
  ✗ fabric.yml found

  7 passed, 3 failed
```

> **Note**
>
> The `doctor` command does not require a `fabric.yml` file. If one is not found, it skips the bundle validation check and reports it as a failure. All other checks still run.

---

## Step 3: Set up authentication

Fabric Automation Bundles uses the `azure-identity` library and supports two authentication methods: interactive login for development and service principal for CI/CD.

### Interactive login (development)

Use the Azure CLI to sign in interactively. This is the recommended method for local development.

```bash
az login
```

After signing in, verify that your token works:

```bash
fab-bundle doctor
```

Then run commands against your development environment:

```bash
fab-bundle plan -t dev
fab-bundle deploy -t dev
```

> **Note**
>
> If you have access to multiple Azure tenants, specify the tenant explicitly:
> ```bash
> az login --tenant your-tenant-id
> ```

### Service principal (CI/CD)

For automated pipelines, use a service principal with the following environment variables:

```bash
export AZURE_TENANT_ID="your-tenant-id"
export AZURE_CLIENT_ID="your-client-id"
export AZURE_CLIENT_SECRET="your-client-secret"
```

Then run commands non-interactively using the `--auto-approve` flag:

```bash
fab-bundle deploy -t prod --auto-approve
```

**Setting up a service principal:**

1. Register an application in Entra ID (Azure AD).
2. Create a client secret or configure certificate-based auth.
3. Grant the service principal the **Contributor** role on the target Fabric workspace.
4. If creating workspaces, grant the service principal permission to create workspaces in the Fabric tenant.

> **Warning**
>
> Never commit service principal credentials to source control. Use your CI/CD platform's secret management (for example, GitHub Actions secrets, Azure DevOps variable groups, or Azure Key Vault) to inject these values at runtime.

### Azure DevOps pipeline example

```yaml
# azure-pipelines.yml
trigger:
  branches:
    include: [main]

pool:
  vmImage: 'ubuntu-latest'

steps:
  - task: UsePythonVersion@0
    inputs:
      versionSpec: '3.12'

  - script: pip install fabric-automation-bundles
    displayName: 'Install fab-bundle'

  - script: fab-bundle deploy -t prod --auto-approve
    displayName: 'Deploy to production'
    env:
      AZURE_TENANT_ID: $(AZURE_TENANT_ID)
      AZURE_CLIENT_ID: $(AZURE_CLIENT_ID)
      AZURE_CLIENT_SECRET: $(AZURE_CLIENT_SECRET)
```

### GitHub Actions example

```yaml
# .github/workflows/deploy.yml
name: Deploy Fabric Bundle
on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - run: pip install fabric-automation-bundles

      - run: fab-bundle deploy -t prod --auto-approve
        env:
          AZURE_TENANT_ID: ${{ secrets.AZURE_TENANT_ID }}
          AZURE_CLIENT_ID: ${{ secrets.AZURE_CLIENT_ID }}
          AZURE_CLIENT_SECRET: ${{ secrets.AZURE_CLIENT_SECRET }}
```

---

## Upgrading

### Check for updates

```bash
fab-bundle check-update
```

**Example output (update available):**

```
  Update available: 1.0.0b1 → 1.0.0b2
  Run: pip install --upgrade fabric-automation-bundles
```

**Example output (up to date):**

```
  You're on the latest version: 1.0.0b2
```

### Upgrade to the latest version

```bash
pip install --upgrade fabric-automation-bundles
```

To upgrade extras as well:

```bash
pip install --upgrade "fabric-automation-bundles[keyvault,remote-state]"
```

### Pin a specific version

For reproducible CI/CD pipelines, pin the version in your `requirements.txt`:

```
fabric-automation-bundles==1.0.0b2
```

Or in `pyproject.toml`:

```toml
[project]
dependencies = [
    "fabric-automation-bundles==1.0.0b2",
]
```

---

## Troubleshooting installation issues

### `fab-bundle: command not found`

**Cause:** The Python scripts directory is not in your system `PATH`.

**Solution (macOS/Linux):**

```bash
# Find where pip installed the script
python -m site --user-base
# Typical output: /Users/yourname/.local

# Add to PATH in your shell profile (~/.zshrc, ~/.bashrc)
export PATH="$HOME/.local/bin:$PATH"

# Reload your shell
source ~/.zshrc
```

**Solution (Windows):**

```powershell
# Find the Scripts directory
python -m site --user-base
# Typical output: C:\Users\yourname\AppData\Roaming\Python\Python312

# Add to PATH via System Properties > Environment Variables
# Add: C:\Users\yourname\AppData\Roaming\Python\Python312\Scripts
```

> **Tip**
>
> If you installed Python via the Microsoft Store on Windows, the scripts directory may be under `%LOCALAPPDATA%\Packages\PythonSoftwareFoundation.Python.3.12_*\LocalCache\local-packages\Python312\Scripts`.

### Permission denied during install

**Cause:** You are installing to the system Python without elevated privileges.

**Solution:** Use a virtual environment (recommended) or install with `--user`:

```bash
# Option 1: Virtual environment (recommended)
python -m venv .venv
source .venv/bin/activate   # macOS/Linux
# .venv\Scripts\activate    # Windows
pip install fabric-automation-bundles

# Option 2: User install
pip install --user fabric-automation-bundles
```

> **Warning**
>
> Avoid using `sudo pip install` on Linux/macOS. This modifies system packages and can break your operating system's Python installation.

### Virtual environment best practices

Always use a virtual environment for project isolation:

```bash
# Create a virtual environment in your project directory
cd my-fabric-project
python -m venv .venv

# Activate it
source .venv/bin/activate        # macOS/Linux
# .venv\Scripts\activate         # Windows
# .venv\Scripts\Activate.ps1     # PowerShell

# Install fab-bundle
pip install fabric-automation-bundles

# Verify
fab-bundle --version
```

Add `.venv/` to your `.gitignore`:

```
# .gitignore
.venv/
.fab-bundle/
```

### Dependency conflicts

**Cause:** Another package in your environment requires an incompatible version of a shared dependency (for example, `pydantic` or `azure-identity`).

**Solution:**

```bash
# Check for conflicts
pip check

# If conflicts exist, create a fresh virtual environment
python -m venv .venv-fresh
source .venv-fresh/bin/activate
pip install fabric-automation-bundles
```

### `ModuleNotFoundError: No module named 'azure.keyvault'`

**Cause:** You are using `${secret.*}` variable references in your `fabric.yml` but did not install the `keyvault` extra.

**Solution:**

```bash
pip install "fabric-automation-bundles[keyvault]"
```

### `ModuleNotFoundError: No module named 'azure.storage'`

**Cause:** You configured a remote state backend (`azureblob` or `adls`) but did not install the `remote-state` extra.

**Solution:**

```bash
pip install "fabric-automation-bundles[remote-state]"
```

### `az login` errors

**Cause:** The Azure CLI is not installed or not authenticated.

**Solution:**

```bash
# Check if Azure CLI is installed
az --version

# If not installed, see https://aka.ms/installazurecli

# Sign in
az login

# Verify the active account
az account show --query '{name:name, tenantId:tenantId}' -o table
```

### Proxy or firewall issues

If you are behind a corporate proxy, configure pip and the Azure CLI:

```bash
# pip
export HTTPS_PROXY=http://proxy.example.com:8080
pip install fabric-automation-bundles

# Azure CLI
export HTTPS_PROXY=http://proxy.example.com:8080
az login
```

If your firewall blocks PyPI, use a private package index:

```bash
pip install fabric-automation-bundles --index-url https://your-private-index/simple/
```

---

## Next steps

- [Quick start tutorial](../getting-started/quickstart.md) -- Create and deploy your first bundle.
- [CLI commands reference](../cli/commands.md) -- Full reference for all `fab-bundle` commands.
- [fabric.yml reference](../guide/fabric-yml.md) -- Complete schema reference for bundle definitions.
