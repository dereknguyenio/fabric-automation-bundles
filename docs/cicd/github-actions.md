# GitHub Actions

Copy `cicd/github-actions.yml` to `.github/workflows/fabric-bundle.yml`.

## Required Secrets

- `AZURE_TENANT_ID`
- `AZURE_CLIENT_ID`
- `AZURE_CLIENT_SECRET`

## Example

```yaml
- name: Deploy to Fabric
  run: |
    pip install fabric-automation-bundles
    fab-bundle deploy -t prod -y
  env:
    AZURE_TENANT_ID: ${{ secrets.AZURE_TENANT_ID }}
    AZURE_CLIENT_ID: ${{ secrets.AZURE_CLIENT_ID }}
    AZURE_CLIENT_SECRET: ${{ secrets.AZURE_CLIENT_SECRET }}
```
