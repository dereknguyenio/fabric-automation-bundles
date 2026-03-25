# Security & Permissions

## Workspace Roles

```yaml
security:
  roles:
    - name: engineers
      entra_group: sg-data-engineering  # or use GUID
      workspace_role: contributor
    - name: analysts
      entra_user: analyst@company.com
      workspace_role: viewer
      onelake_roles:
        - tables: ["*"]
          permissions: [read]
```

## Entra ID Resolution

Display names are automatically resolved to GUIDs via Microsoft Graph API. You can also use GUIDs directly.

## OneLake Data Access Roles

Fine-grained table/folder-level permissions:

```yaml
onelake_roles:
  - tables: ["dim_customer", "fact_sales"]
    permissions: [read]
  - folders: ["raw/*"]
    permissions: [read, write]
```
