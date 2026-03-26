# GitHub Actions

This page provides complete, copy-ready workflow files for deploying Fabric Automation Bundles with GitHub Actions.

For a working reference repository, see [github.com/dereknguyenio/fabric-fab-cicd-example](https://github.com/dereknguyenio/fabric-fab-cicd-example).

## Setting up secrets

Go to your repository on GitHub: **Settings > Secrets and variables > Actions**. Add the following repository secrets:

| Secret | Description |
|--------|-------------|
| `AZURE_TENANT_ID` | Your Entra ID (Azure AD) tenant GUID |
| `AZURE_CLIENT_ID` | The service principal's application (client) ID |
| `AZURE_CLIENT_SECRET` | The service principal's client secret |

These secrets are referenced as `${{ secrets.AZURE_TENANT_ID }}`, etc., in the workflow files below.

See [Service Principal Setup](../guide/service-principal.md) for instructions on creating the service principal and granting it workspace access.

## Setting up environments with approval gates

Go to **Settings > Environments** in your repository. Create the following environments:

| Environment | Configuration |
|-------------|---------------|
| `dev` | No protection rules. Deployments run automatically on merge. |
| `staging` | Optional: add required reviewers if you want a gate before staging. |
| `production` | Required reviewers. Add one or more team members who must approve before production deploys run. Optionally add a wait timer (e.g., 5 minutes) to allow time to cancel. |

You can also scope environment secrets. If dev and prod use different service principals, add the `AZURE_CLIENT_ID` and `AZURE_CLIENT_SECRET` secrets at the environment level instead of the repository level.

## CI workflow: PR validation

This workflow runs on every pull request that touches the bundle definition. It validates the schema and policies, then runs a plan to show what would change.

Create `.github/workflows/fabric-ci.yml`:

```yaml
name: Fabric CI

on:
  pull_request:
    paths:
      - 'fabric.yml'
      - 'notebooks/**'
      - 'sql/**'
      - 'agent/**'
      - 'pipelines/**'

jobs:
  validate:
    name: Validate Bundle
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Install fab-bundle
        run: pip install fabric-automation-bundles

      - name: Validate
        run: fab-bundle validate --strict

  plan:
    name: Plan (${{ matrix.target }})
    runs-on: ubuntu-latest
    needs: validate
    strategy:
      matrix:
        target: [dev]
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Install fab-bundle
        run: pip install fabric-automation-bundles

      - name: Plan deployment
        run: fab-bundle plan -t ${{ matrix.target }}
        env:
          AZURE_TENANT_ID: ${{ secrets.AZURE_TENANT_ID }}
          AZURE_CLIENT_ID: ${{ secrets.AZURE_CLIENT_ID }}
          AZURE_CLIENT_SECRET: ${{ secrets.AZURE_CLIENT_SECRET }}
```

## CD workflow: deploy on merge

This workflow runs when changes are merged to `main`. It deploys sequentially through dev, staging, and production, with an approval gate before production.

Create `.github/workflows/fabric-cd.yml`:

```yaml
name: Fabric CD

on:
  push:
    branches: [main]
    paths:
      - 'fabric.yml'
      - 'notebooks/**'
      - 'sql/**'
      - 'agent/**'
      - 'pipelines/**'

jobs:
  # ── Deploy to Dev (automatic) ─────────────────────
  deploy-dev:
    name: Deploy to Dev
    runs-on: ubuntu-latest
    environment: dev
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Install fab-bundle
        run: pip install fabric-automation-bundles

      - name: Deploy
        run: fab-bundle deploy --target dev -y
        env:
          AZURE_TENANT_ID: ${{ secrets.AZURE_TENANT_ID }}
          AZURE_CLIENT_ID: ${{ secrets.AZURE_CLIENT_ID }}
          AZURE_CLIENT_SECRET: ${{ secrets.AZURE_CLIENT_SECRET }}

      - name: Verify deployment
        run: fab-bundle status --target dev
        env:
          AZURE_TENANT_ID: ${{ secrets.AZURE_TENANT_ID }}
          AZURE_CLIENT_ID: ${{ secrets.AZURE_CLIENT_ID }}
          AZURE_CLIENT_SECRET: ${{ secrets.AZURE_CLIENT_SECRET }}

  # ── Deploy to Staging (automatic after dev) ────────
  deploy-staging:
    name: Deploy to Staging
    runs-on: ubuntu-latest
    needs: deploy-dev
    environment: staging
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Install fab-bundle
        run: pip install fabric-automation-bundles

      - name: Deploy
        run: fab-bundle deploy --target staging -y
        env:
          AZURE_TENANT_ID: ${{ secrets.AZURE_TENANT_ID }}
          AZURE_CLIENT_ID: ${{ secrets.AZURE_CLIENT_ID }}
          AZURE_CLIENT_SECRET: ${{ secrets.AZURE_CLIENT_SECRET }}

      - name: Verify deployment
        run: fab-bundle status --target staging
        env:
          AZURE_TENANT_ID: ${{ secrets.AZURE_TENANT_ID }}
          AZURE_CLIENT_ID: ${{ secrets.AZURE_CLIENT_ID }}
          AZURE_CLIENT_SECRET: ${{ secrets.AZURE_CLIENT_SECRET }}

  # ── Deploy to Production (requires approval) ──────
  deploy-prod:
    name: Deploy to Production
    runs-on: ubuntu-latest
    needs: deploy-staging
    environment: production
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Install fab-bundle
        run: pip install fabric-automation-bundles

      - name: Deploy
        run: fab-bundle deploy --target prod -y
        env:
          AZURE_TENANT_ID: ${{ secrets.AZURE_TENANT_ID }}
          AZURE_CLIENT_ID: ${{ secrets.AZURE_CLIENT_ID }}
          AZURE_CLIENT_SECRET: ${{ secrets.AZURE_CLIENT_SECRET }}

      - name: Verify deployment
        run: fab-bundle status --target prod
        env:
          AZURE_TENANT_ID: ${{ secrets.AZURE_TENANT_ID }}
          AZURE_CLIENT_ID: ${{ secrets.AZURE_CLIENT_ID }}
          AZURE_CLIENT_SECRET: ${{ secrets.AZURE_CLIENT_SECRET }}
```

## Drift check workflow (scheduled)

This workflow runs on a schedule to detect changes made outside of the bundle pipeline. It reports drift as a workflow annotation and uploads the report as an artifact.

Create `.github/workflows/fabric-drift.yml`:

```yaml
name: Drift Check

on:
  schedule:
    - cron: '0 8 * * 1-5'  # Weekdays at 8:00 AM UTC
  workflow_dispatch:

jobs:
  drift:
    name: Check Drift (${{ matrix.target }})
    runs-on: ubuntu-latest
    strategy:
      matrix:
        target: [dev, staging, prod]
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Install fab-bundle
        run: pip install fabric-automation-bundles

      - name: Check for drift
        id: drift
        run: fab-bundle drift -t ${{ matrix.target }} --format json > drift-report.json
        env:
          AZURE_TENANT_ID: ${{ secrets.AZURE_TENANT_ID }}
          AZURE_CLIENT_ID: ${{ secrets.AZURE_CLIENT_ID }}
          AZURE_CLIENT_SECRET: ${{ secrets.AZURE_CLIENT_SECRET }}
        continue-on-error: true

      - name: Upload drift report
        if: steps.drift.outcome == 'failure'
        uses: actions/upload-artifact@v4
        with:
          name: drift-report-${{ matrix.target }}
          path: drift-report.json

      - name: Annotate on drift
        if: steps.drift.outcome == 'failure'
        run: echo "::warning::Drift detected in '${{ matrix.target }}' environment. See drift-report artifact for details."

      - name: Fail on drift
        if: steps.drift.outcome == 'failure'
        run: exit 1
```

## Destroy workflow (manual dispatch)

This workflow tears down all bundle resources in a target workspace. It requires manual dispatch and confirmation to prevent accidental deletion.

Create `.github/workflows/fabric-destroy.yml`:

```yaml
name: Destroy Environment

on:
  workflow_dispatch:
    inputs:
      target:
        description: 'Target environment to destroy'
        required: true
        type: choice
        options:
          - dev
          - staging
      confirm:
        description: 'Type the target name to confirm destruction'
        required: true
        type: string

jobs:
  destroy:
    name: Destroy ${{ github.event.inputs.target }}
    runs-on: ubuntu-latest
    environment: ${{ github.event.inputs.target }}
    steps:
      - name: Verify confirmation
        run: |
          if [ "${{ github.event.inputs.confirm }}" != "${{ github.event.inputs.target }}" ]; then
            echo "::error::Confirmation does not match target. Expected '${{ github.event.inputs.target }}', got '${{ github.event.inputs.confirm }}'."
            exit 1
          fi

      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Install fab-bundle
        run: pip install fabric-automation-bundles

      - name: Destroy resources
        run: fab-bundle destroy -t ${{ github.event.inputs.target }} -y
        env:
          AZURE_TENANT_ID: ${{ secrets.AZURE_TENANT_ID }}
          AZURE_CLIENT_ID: ${{ secrets.AZURE_CLIENT_ID }}
          AZURE_CLIENT_SECRET: ${{ secrets.AZURE_CLIENT_SECRET }}
```

!!! warning "Production protection"
    The `prod` option is intentionally excluded from the destroy workflow's target choices. If you need to destroy production resources, do so through a separate process with additional safeguards.

## Example of a working pipeline run

A successful CD run looks like this in the GitHub Actions UI:

```
Fabric CD                                    ✓ completed in 4m 32s
├── Deploy to Dev                            ✓ 1m 12s
│   ├── Checkout                             ✓ 2s
│   ├── Setup Python 3.12                    ✓ 8s
│   ├── Install fab-bundle                   ✓ 15s
│   ├── Deploy                               ✓ 42s
│   │   Deploying to target: dev
│   │   Workspace: contoso-analytics-dev
│   │     ✓ Lakehouse: bronze (unchanged)
│   │     ✓ Lakehouse: silver (unchanged)
│   │     ✓ Notebook: ingest_to_bronze (updated)
│   │     ✓ Pipeline: daily_ingest (unchanged)
│   │   Deployed 4 resources (1 updated, 3 unchanged)
│   └── Verify deployment                    ✓ 5s
├── Deploy to Staging                        ✓ 1m 08s
│   └── ...
└── Deploy to Production                     ⏳ waiting for approval
    └── dereknguyenio approved               ✓ 2m 12s
```

## Reference repository

A complete working example with all four workflows, a multi-target `fabric.yml`, and sample notebooks is available at:

[github.com/dereknguyenio/fabric-fab-cicd-example](https://github.com/dereknguyenio/fabric-fab-cicd-example)
