# Security and Permissions

The `security` section of `fabric.yml` manages workspace role assignments, OneLake data access roles, and row-level and column-level security. fab-bundle resolves Entra ID display names to GUIDs at deploy time, so you can write human-readable YAML instead of opaque identifiers.

## Workspace roles

Fabric workspaces have four built-in roles:

| Role | Capabilities |
|------|-------------|
| **Admin** | Full control. Manage access, delete the workspace, configure settings. |
| **Member** | Create, edit, and delete all items. Share items. Cannot manage workspace settings. |
| **Contributor** | Create, edit, and delete items they own. Cannot share items or manage access. |
| **Viewer** | View items and run reports. Cannot edit or create items. |

Assign roles to Entra ID groups, individual users, or service principals:

```yaml
security:
  roles:
    - name: data_engineers
      entra_group: sg-data-engineering
      workspace_role: contributor

    - name: analysts
      entra_group: sg-analytics-team
      workspace_role: viewer

    - name: project_lead
      entra_user: jane.doe@contoso.com
      workspace_role: admin

    - name: cicd_deployer
      service_principal: fab-bundle-cicd
      workspace_role: admin
```

Each role entry requires exactly one principal (`entra_group`, `entra_user`, or `service_principal`) and one `workspace_role`.

## Entra ID group resolution

You can reference Entra ID groups and service principals by their display name or by their GUID. When you use a display name, fab-bundle calls the Microsoft Graph API at deploy time to resolve it to the object's GUID.

```yaml
# Display name (resolved via Graph API)
entra_group: sg-data-engineering

# GUID (used directly, no Graph API call)
entra_group: "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
```

Display name resolution requires the deploying identity (your user account or the CI/CD service principal) to have `GroupMember.Read.All` or `Group.Read.All` permission in Microsoft Graph. If the permission is missing, fab-bundle will report an error suggesting you use GUIDs instead.

Using GUIDs is faster (no API call) and avoids ambiguity when multiple groups share similar names.

## OneLake data access roles

OneLake data access roles provide fine-grained, table-level and folder-level access control within a lakehouse. They operate below the workspace role level: a user can have Viewer access to the workspace but read access to only specific tables.

```yaml
security:
  roles:
    - name: sales_analysts
      entra_group: sg-sales-team
      workspace_role: viewer
      onelake_roles:
        - tables: ["fact_sales", "dim_customer", "dim_product"]
          permissions: [read]

    - name: data_engineers
      entra_group: sg-data-engineering
      workspace_role: contributor
      onelake_roles:
        - tables: ["*"]
          permissions: [read, write]
        - folders: ["raw/*"]
          permissions: [read, write]

    - name: finance
      entra_group: sg-finance
      workspace_role: viewer
      onelake_roles:
        - tables: ["fact_revenue", "dim_cost_center"]
          permissions: [read]
        - folders: ["reports/finance/*"]
          permissions: [read]
```

### Supported permissions

| Permission | Description |
|-----------|-------------|
| `read` | Read data from the specified tables or folders |
| `write` | Write data to the specified tables or folders |

### Wildcard patterns

- `["*"]` -- All tables or all folders in the lakehouse.
- `["raw/*"]` -- All items under the `raw/` folder path.
- `["dim_*"]` -- All tables whose names start with `dim_`.

!!! warning "Portal prerequisite"
    OneLake data access roles must be enabled per-lakehouse in the Fabric portal before fab-bundle can manage them. Go to the lakehouse settings in the portal and enable **OneLake data access roles (Preview)**. Without this, the API calls will fail with a 403 error.

## Row-level security

Row-level security (RLS) restricts which rows a user can see in a semantic model. Define RLS roles with DAX filter expressions:

```yaml
security:
  row_level_security:
    - semantic_model: sales_model
      roles:
        - name: region_us
          description: "See only US sales data"
          filter: "'dim_geography'[country] = \"US\""
          members:
            - entra_group: sg-sales-us

        - name: region_eu
          description: "See only EU sales data"
          filter: "'dim_geography'[region] = \"EU\""
          members:
            - entra_group: sg-sales-eu

        - name: all_regions
          description: "See all data (no filter)"
          filter: "TRUE()"
          members:
            - entra_group: sg-sales-leadership
```

Each RLS role defines a DAX `filter` expression applied to the specified table. The `members` list determines which Entra groups or users are assigned to that role.

## Column-level security

Column-level security (CLS) restricts which columns a user can see. It is defined per semantic model and applies to specific tables:

```yaml
security:
  column_level_security:
    - semantic_model: hr_model
      restrictions:
        - table: dim_employee
          denied_columns: [salary, ssn, performance_rating]
          applies_to:
            - entra_group: sg-hr-viewers

        - table: dim_employee
          denied_columns: [ssn]
          applies_to:
            - entra_group: sg-hr-managers
```

Users in the `applies_to` list will see the table but the specified columns will be hidden. Users not in any restriction list see all columns.

## Service principal permissions

The service principal used for CI/CD deployments needs specific permissions depending on what the bundle manages:

| Capability | Required Permission |
|-----------|-------------------|
| Create, update, delete items | Workspace **Contributor** or **Admin** role |
| Manage workspace role assignments | Workspace **Admin** role |
| Manage OneLake data access roles | Workspace **Admin** role |
| Resolve Entra display names to GUIDs | Microsoft Graph `Group.Read.All` (application permission) |
| Manage RLS/CLS | Workspace **Admin** role + semantic model ownership |

If the service principal only needs to deploy items without managing security, **Contributor** is sufficient. If the bundle includes a `security` section, **Admin** is required.

## Security in CI/CD

In a CI/CD pipeline, the service principal authenticates via environment variables (`AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`) and must have the workspace roles listed above.

A common bootstrap pattern:

1. A workspace admin manually grants the service principal **Admin** access to each target workspace (dev, staging, prod) through the Fabric portal.
2. The service principal is also declared in the bundle's `security` section so that its access is codified and will be re-applied on every deploy:

```yaml
security:
  roles:
    - name: cicd_deployer
      service_principal: fab-bundle-cicd
      workspace_role: admin
```

3. From this point on, all security changes (adding new groups, modifying OneLake roles) go through the bundle and are deployed by the service principal.

See [Service Principal Setup](service-principal.md) for full instructions on creating the service principal, granting permissions, and configuring CI/CD secrets.

## Full YAML example

```yaml
security:
  roles:
    # Workspace-level roles
    - name: data_engineers
      entra_group: sg-data-engineering
      workspace_role: contributor
      onelake_roles:
        - tables: ["*"]
          permissions: [read, write]

    - name: analysts
      entra_group: sg-analytics-team
      workspace_role: viewer
      onelake_roles:
        - tables: ["fact_sales", "dim_customer", "dim_product"]
          permissions: [read]

    - name: external_vendor
      entra_group: "b2c3d4e5-f6a7-8901-bcde-f12345678901"  # GUID for external group
      workspace_role: viewer
      onelake_roles:
        - tables: ["fact_sales_summary"]
          permissions: [read]

    - name: cicd_deployer
      service_principal: fab-bundle-cicd
      workspace_role: admin

  # Row-level security
  row_level_security:
    - semantic_model: sales_model
      roles:
        - name: region_us
          filter: "'dim_geography'[country] = \"US\""
          members:
            - entra_group: sg-sales-us
        - name: region_eu
          filter: "'dim_geography'[region] = \"EU\""
          members:
            - entra_group: sg-sales-eu

  # Column-level security
  column_level_security:
    - semantic_model: hr_model
      restrictions:
        - table: dim_employee
          denied_columns: [salary, ssn]
          applies_to:
            - entra_group: sg-hr-viewers
```
