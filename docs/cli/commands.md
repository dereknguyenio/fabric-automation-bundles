# CLI command reference

This topic provides a complete reference for all `fab-bundle` CLI commands, including syntax, options, usage examples, and example output.

---

## Global options

The following options are available on all commands unless otherwise noted.

| Option | Description |
|---|---|
| `--version` | Print the installed version and exit. |
| `--help` | Show help text for any command. |

```bash
fab-bundle --version
fab-bundle --help
fab-bundle deploy --help
```

---

## Command summary

| Category | Command | Description |
|---|---|---|
| **Project setup** | [init](#init) | Create a new bundle project from a template. |
| | [list](#list) | List available bundle templates. |
| | [doctor](#doctor) | Diagnose configuration issues. |
| | [check-update](#check-update) | Check if a newer version is available. |
| **Validation** | [validate](#validate) | Validate the bundle definition. |
| | [graph](#graph) | Visualize the dependency graph. |
| **Planning and deployment** | [plan](#plan) | Preview what changes would be made. |
| | [deploy](#deploy) | Deploy the bundle to a target workspace. |
| | [destroy](#destroy) | Tear down all bundle-managed resources. |
| | [promote](#promote) | Promote artifacts from one target to another. |
| **Operations** | [status](#status) | Show deployed resource health. |
| | [drift](#drift) | Detect drift between state and live workspace. |
| | [diff](#diff) | Show definition-level diff (local vs. deployed). |
| | [history](#history) | Show deployment history. |
| | [rollback](#rollback) | Roll back to a previous deployment. |
| | [watch](#watch) | Auto-deploy on file changes. |
| **Resource management** | [run](#run) | Run a notebook or pipeline. |
| | [export](#export) | Export definitions from a deployed workspace. |
| | [generate](#generate) | Generate fabric.yml from an existing workspace. |
| | [bind](#bind) | Bind an existing workspace item to bundle management. |
| | [import](#import) | Import resources from Terraform state or a workspace. |

---

## init

Create a new bundle project from a template.

### Syntax

```
fab-bundle init [OPTIONS]
```

### Options

| Option | Short | Type | Default | Description |
|---|---|---|---|---|
| `--template` | `-t` | String | `blank` | Template name or path. Use `fab-bundle list` to see available templates. |
| `--name` | `-n` | String | *(prompted)* | Bundle project name. Used as the directory name and `bundle.name` value. |
| `--output` | `-o` | String | `.` | Output directory. If `.`, creates a subdirectory named after the project. |
| `--var` | | String (multiple) | | Template variables as `KEY=VALUE` pairs. Can be specified multiple times. |
| `--interactive` | `-i` | Flag | `false` | Launch the interactive setup wizard. Automatically enabled if no `--template` or `--name` is provided. |

### Examples

**Create a project using the interactive wizard:**

```bash
fab-bundle init
```

**Example output:**

```
Fabric Automation Bundles — Setup Wizard

Available templates:
  1. blank — Empty project with minimal structure
  2. medallion — Bronze/Silver/Gold lakehouse pattern

Select template: 2

Project name: sales-analytics

Fetching available capacities...
  1. MyCapacity (F4, West US 2)
Select capacity: 1

✓ Created project: sales-analytics/
  fabric.yml
  notebooks/
  README.md
```

**Create a project non-interactively:**

```bash
fab-bundle init --template medallion --name sales-analytics --var capacity_id=abc-def-123
```

**Create a project in a specific directory:**

```bash
fab-bundle init --template blank --name my-project --output /path/to/projects
```

> **Note**
>
> When using interactive mode, the wizard attempts to fetch available Fabric capacities using `az rest`. If Azure CLI is not authenticated, this step is skipped and you can set the capacity ID manually in `fabric.yml` afterward.

---

## validate

Validate the bundle definition file for syntax errors, schema violations, unresolved variables, and dependency cycles.

### Syntax

```
fab-bundle validate [OPTIONS]
```

### Options

| Option | Short | Type | Default | Description |
|---|---|---|---|---|
| `--file` | `-f` | String | Auto-detected | Path to `fabric.yml`. If omitted, searches the current directory. |
| `--target` | `-t` | String | *(none)* | Target environment to validate against. Applies target-specific variable overrides and workspace config. |
| `--strict` | | Flag | `false` | Fail on unresolved variables and warnings in addition to errors. |

### Examples

**Validate the bundle in the current directory:**

```bash
fab-bundle validate
```

**Example output:**

```
Bundle is valid.

  Bundle:    sales-analytics v1.0.0
  Desc:      Sales analytics pipeline
  Resources: 6
    environments: 1
    lakehouses: 2
    notebooks: 2
    pipelines: 1
  Targets:   dev, staging, prod

  Deployment order:
    1. [environments] spark_env
    2. [lakehouses] bronze_lakehouse
    3. [lakehouses] gold_lakehouse
    4. [notebooks] ingest_notebook (depends: bronze_lakehouse, spark_env)
    5. [notebooks] transform_notebook (depends: bronze_lakehouse, gold_lakehouse, spark_env)
    6. [pipelines] daily_pipeline (depends: ingest_notebook, transform_notebook)
```

**Validate against a specific target:**

```bash
fab-bundle validate -t prod
```

**Example output (with target):**

```
Bundle is valid.

  Bundle:    sales-analytics v1.0.0
  Resources: 6
    ...
  Targets:   dev, staging, prod
  Workspace: sales-analytics-prod
  Variables: 3

  Deployment order:
    ...
```

**Strict validation:**

```bash
fab-bundle validate --strict
```

**Example output (failure):**

```
Validation failed: Unresolved variable: ${source_connection}
  Variable 'source_connection' has no default value and no target override
```

> **Tip**
>
> Run `fab-bundle validate --strict -t <target>` in your CI pipeline to catch configuration errors before deployment.

---

## plan

Preview what changes would be made to the target workspace without actually deploying. Compares the local bundle definition to the current workspace state.

### Syntax

```
fab-bundle plan [OPTIONS]
```

### Options

| Option | Short | Type | Default | Description |
|---|---|---|---|---|
| `--file` | `-f` | String | Auto-detected | Path to `fabric.yml`. |
| `--target` | `-t` | String | *(default target)* | Target environment. |
| `--auto-delete / --no-auto-delete` | | Flag | `false` | Include deletion of workspace items not in the bundle definition. |
| `--validate-api` | | Flag | `false` | After planning, validate each item definition against the Fabric API. |

### Examples

**Preview changes for the default target:**

```bash
fab-bundle plan
```

**Example output:**

```
Plan: sales-analytics → sales-analytics-dev

  + [Lakehouse]      bronze_lakehouse          CREATE
  + [Lakehouse]      gold_lakehouse            CREATE
  + [Environment]    spark_env                 CREATE
  + [Notebook]       ingest_notebook           CREATE
  + [Notebook]       transform_notebook        CREATE
  + [DataPipeline]   daily_pipeline            CREATE

  Summary: 6 to create, 0 to update, 0 to delete, 0 unchanged
```

**Plan with auto-delete to remove unmanaged items:**

```bash
fab-bundle plan -t prod --auto-delete
```

**Example output:**

```
Plan: sales-analytics → sales-analytics-prod

  = [Lakehouse]      bronze_lakehouse          NO CHANGE
  ~ [Notebook]       ingest_notebook           UPDATE
  - [Notebook]       old_notebook              DELETE (unmanaged)

  Summary: 0 to create, 1 to update, 1 to delete, 1 unchanged
```

**Plan with API validation:**

```bash
fab-bundle plan --validate-api
```

**Example output:**

```
Plan: sales-analytics → sales-analytics-dev
  ...

Validating definitions against Fabric API...
  ✓ ingest_notebook: definition valid (2 parts)
  ✓ transform_notebook: definition valid (2 parts)
  - daily_pipeline: no definition (metadata only)
```

> **Note**
>
> If the workspace does not exist or is not reachable, the plan assumes an empty workspace and marks all items as CREATE.

---

## deploy

Deploy the bundle to a target workspace. Creates, updates, or deletes items as needed to match the bundle definition.

### Syntax

```
fab-bundle deploy [OPTIONS]
```

### Options

| Option | Short | Type | Default | Description |
|---|---|---|---|---|
| `--file` | `-f` | String | Auto-detected | Path to `fabric.yml`. |
| `--target` | `-t` | String | *(default target)* | Target environment. |
| `--dry-run` | | Flag | `false` | Preview the plan without applying changes. Equivalent to `plan`. |
| `--auto-approve` | `-y` | Flag | `false` | Skip the interactive confirmation prompt. Required for CI/CD. |
| `--auto-delete / --no-auto-delete` | | Flag | `false` | Delete workspace items that are not defined in the bundle. |
| `--force` | | Flag | `false` | Override deployment locks and skip the definition cache. |

### Examples

**Deploy to the default target (interactive):**

```bash
fab-bundle deploy
```

**Example output:**

```
Plan: sales-analytics → sales-analytics-dev

  + [Lakehouse]      bronze_lakehouse          CREATE
  + [Environment]    spark_env                 CREATE
  + [Notebook]       ingest_notebook           CREATE

  Summary: 3 to create, 0 to update, 0 to delete

Do you want to apply these changes? [y/N]: y

  ✓ Created: bronze_lakehouse (Lakehouse)
  ✓ Created: spark_env (Environment)
  ✓ Created: ingest_notebook (Notebook)

Deploy complete. 3 items deployed in 12.4s.
```

**Deploy to production with auto-approve (CI/CD):**

```bash
fab-bundle deploy -t prod -y
```

**Dry run:**

```bash
fab-bundle deploy -t staging --dry-run
```

**Force deploy (skip lock and cache):**

```bash
fab-bundle deploy -t dev --force --auto-approve
```

> **Warning**
>
> The `--auto-delete` flag permanently deletes workspace items that are not defined in your bundle. Use `fab-bundle plan --auto-delete` first to review which items would be removed.

> **Important**
>
> The `--force` flag overrides deployment locks. Use it only when a previous deployment was interrupted or left in an inconsistent state.

---

## destroy

Delete all bundle-managed resources from the target workspace. Optionally delete the workspace itself.

### Syntax

```
fab-bundle destroy [OPTIONS]
```

### Options

| Option | Short | Type | Default | Description |
|---|---|---|---|---|
| `--file` | `-f` | String | Auto-detected | Path to `fabric.yml`. |
| `--target` | `-t` | String | *(default target)* | Target environment. |
| `--auto-approve` | `-y` | Flag | `false` | Skip the confirmation prompt. When not set, you must type the bundle name to confirm. |
| `--delete-workspace` | | Flag | `false` | Also delete the workspace after all items are removed. |

### Examples

**Destroy resources in the dev environment:**

```bash
fab-bundle destroy -t dev
```

**Example output:**

```
WARNING: This will delete all bundle-managed resources in:
  Workspace: sales-analytics-dev
  Target:    dev

  Resources to destroy (reverse dependency order):
    1. - [pipelines] daily_pipeline
    2. - [notebooks] transform_notebook
    3. - [notebooks] ingest_notebook
    4. - [environments] spark_env
    5. - [lakehouses] gold_lakehouse
    6. - [lakehouses] bronze_lakehouse

Type the bundle name 'sales-analytics' to confirm destruction: sales-analytics

  - Deleted: daily_pipeline
  - Deleted: transform_notebook
  - Deleted: ingest_notebook
  - Deleted: spark_env
  - Deleted: gold_lakehouse
  - Deleted: bronze_lakehouse

Destroy complete. Deleted: 6 resources.
```

**Destroy with auto-approve and delete workspace (CI/CD cleanup):**

```bash
fab-bundle destroy -t dev -y --delete-workspace
```

> **Warning**
>
> This operation is irreversible. Destroyed resources cannot be recovered. The `--delete-workspace` flag deletes the entire Fabric workspace, including any items not managed by the bundle.

> **Note**
>
> Resources are destroyed in reverse dependency order (dependents first, then their dependencies) to avoid API errors from dangling references.

---

## run

Execute a specific notebook or pipeline in the target workspace.

### Syntax

```
fab-bundle run RESOURCE_NAME [OPTIONS]
```

### Arguments

| Argument | Required | Description |
|---|---|---|
| `RESOURCE_NAME` | Yes | The resource key of the notebook or pipeline to run, as defined in `fabric.yml`. |

### Options

| Option | Short | Type | Default | Description |
|---|---|---|---|---|
| `--file` | `-f` | String | Auto-detected | Path to `fabric.yml`. |
| `--target` | `-t` | String | *(default target)* | Target environment. |
| `--param` | `-p` | String (multiple) | | Execution parameters as `KEY=VALUE` pairs. Overrides default parameters from the bundle definition. |

### Examples

**Run a notebook:**

```bash
fab-bundle run ingest_notebook -t dev
```

**Example output:**

```
Running [notebook]: ingest_notebook
  Workspace: sales-analytics-dev (abc123-...)
  Item ID:   def456-...

Job submitted. Waiting for completion...
Run complete.
```

**Run a notebook with parameters:**

```bash
fab-bundle run ingest_notebook -t dev -p start_date=2025-01-01 -p end_date=2025-12-31
```

**Example output:**

```
Running [notebook]: ingest_notebook
  Workspace: sales-analytics-dev (abc123-...)
  Item ID:   def456-...

  Parameters: {'start_date': '2025-01-01', 'end_date': '2025-12-31'}
Job submitted. Waiting for completion...
Run complete.
```

**Run a pipeline:**

```bash
fab-bundle run daily_pipeline -t prod
```

> **Note**
>
> Only `notebooks` and `pipelines` resource types are runnable. Attempting to run other resource types (such as lakehouses or semantic models) produces an error.

> **Important**
>
> The resource must already be deployed to the workspace. If it has not been deployed, run `fab-bundle deploy` first.

---

## status

Show the deployed resource health and status for a target, including which items are deployed, missing, pending, or unmanaged.

### Syntax

```
fab-bundle status [OPTIONS]
```

### Options

| Option | Short | Type | Default | Description |
|---|---|---|---|---|
| `--file` | `-f` | String | Auto-detected | Path to `fabric.yml`. |
| `--target` | `-t` | String | *(default target)* | Target environment. |

### Examples

```bash
fab-bundle status -t dev
```

**Example output:**

```
Status: sales-analytics
  Target:    dev
  Workspace: sales-analytics-dev (abc123-def456-...)
  Last deploy: 2025-03-15 14:30
  Items in workspace: 8
  Items in bundle:    6

Resource                   Type             Status       Item ID
bronze_lakehouse           lakehouses       deployed     abc123def456
gold_lakehouse             lakehouses       deployed     def789abc012
spark_env                  environments     deployed     ghi345jkl678
ingest_notebook            notebooks        deployed     mno901pqr234
transform_notebook         notebooks        deployed     stu567vwx890
daily_pipeline             pipelines        deployed     yza123bcd456
legacy_report              reports          unmanaged    efg789hij012
test_notebook              notebooks        unmanaged    klm345nop678

  Drift detected: 1 item(s)
```

> **Note**
>
> **Status meanings:**
> - **deployed** -- The item exists in the workspace and matches the state file.
> - **missing** -- The item was previously deployed but is no longer in the workspace (deleted outside of fab-bundle).
> - **pending** -- The item is defined in the bundle but has not been deployed yet.
> - **unmanaged** -- The item exists in the workspace but is not defined in the bundle.

---

## drift

Detect drift between the last deployed state and the live workspace. Reports items that were added, removed, or modified outside of `fab-bundle`.

### Syntax

```
fab-bundle drift [OPTIONS]
```

### Options

| Option | Short | Type | Default | Description |
|---|---|---|---|---|
| `--file` | `-f` | String | Auto-detected | Path to `fabric.yml`. |
| `--target` | `-t` | String | *(default target)* | Target environment. |

### Examples

```bash
fab-bundle drift -t dev
```

**Example output (drift detected):**

```
Drift detected: 2 item(s)

  + new_notebook: added
  ~ ingest_notebook: modified

  Run 'fab-bundle deploy' to reconcile, or 'fab-bundle plan' to preview changes.
```

**Example output (no drift):**

```
No drift detected. Workspace matches deployed state.
```

> **Note**
>
> Drift detection requires a prior deployment. If no deployment state exists, the command prompts you to run `fab-bundle deploy` first.

---

## diff

Show a definition-level diff between local files and the deployed definitions in the workspace. Uses unified diff format.

### Syntax

```
fab-bundle diff [OPTIONS] [RESOURCE_NAME]
```

### Arguments

| Argument | Required | Description |
|---|---|---|
| `RESOURCE_NAME` | No | Specific resource to diff. If omitted, diffs all resources. |

### Options

| Option | Short | Type | Default | Description |
|---|---|---|---|---|
| `--file` | `-f` | String | Auto-detected | Path to `fabric.yml`. |
| `--target` | `-t` | String | *(default target)* | Target environment. |

### Examples

**Diff all resources:**

```bash
fab-bundle diff -t dev
```

**Example output:**

```
--- deployed/ingest_notebook/notebook-content.py
+++ local/ingest_notebook/notebook-content.py
@@ -10,6 +10,8 @@
 df = spark.read.format("csv").load(source_path)
+# Added data quality check
+df = df.filter(df["amount"] > 0)
 df.write.format("delta").save(target_path)
```

**Diff a single resource:**

```bash
fab-bundle diff -t dev ingest_notebook
```

**Example output (no differences):**

```
No differences found.
```

> **Note**
>
> Resources that have no exportable definition (for example, lakehouses created as metadata-only) are skipped.

---

## history

Show the deployment history for a target environment.

### Syntax

```
fab-bundle history [OPTIONS]
```

### Options

| Option | Short | Type | Default | Description |
|---|---|---|---|---|
| `--file` | `-f` | String | Auto-detected | Path to `fabric.yml`. |
| `--target` | `-t` | String | *(default target)* | Target environment. |
| `--limit` | `-n` | Integer | `20` | Maximum number of history entries to display. |

### Examples

```bash
fab-bundle history -t prod
```

**Example output:**

```
Deployment History (prod):

  deploy-abc123  2025-03-15 14:30  v1.2.0  6 resources  Update ingest_notebook
  deploy-def456  2025-03-10 09:15  v1.1.0  6 resources  Add transform_notebook
  deploy-ghi789  2025-03-01 11:00  v1.0.0  4 resources  Initial deployment
```

**Show only the last 5 entries:**

```bash
fab-bundle history -t prod -n 5
```

**Example output (no history):**

```
No deployment history found.
```

---

## rollback

Roll back to a previous deployment by restoring the state file to a prior version.

### Syntax

```
fab-bundle rollback [OPTIONS]
```

### Options

| Option | Short | Type | Default | Description |
|---|---|---|---|---|
| `--file` | `-f` | String | Auto-detected | Path to `fabric.yml`. |
| `--target` | `-t` | String | *(default target)* | Target environment. |
| `--to` | | String | | Deploy ID to roll back to. Use `fab-bundle history` to find deploy IDs. |
| `--last` | | Flag | `false` | Roll back to the immediately previous deployment. |
| `--auto-approve` | `-y` | Flag | `false` | Skip the confirmation prompt. |

### Examples

**Roll back to the previous deployment:**

```bash
fab-bundle rollback -t prod --last
```

**Example output:**

```
Rollback target: deploy-def456 (2025-03-10 09:15)
  Version: v1.1.0
  Resources: 6

Proceed with rollback? [y/N]: y
State rolled back. Run 'fab-bundle deploy' to apply.
```

**Roll back to a specific deployment:**

```bash
fab-bundle rollback -t prod --to deploy-ghi789 -y
```

> **Important**
>
> The `rollback` command restores the *state file* only. It does not modify the workspace. After rolling back, run `fab-bundle deploy` to apply the rolled-back state to the workspace.

> **Note**
>
> At least two deployment history entries are required for rollback. If only one entry exists, the command reports that there is not enough history.

---

## promote

Promote deployed artifacts from one target workspace to another by copying item definitions.

### Syntax

```
fab-bundle promote [OPTIONS]
```

### Options

| Option | Short | Type | Default | Description |
|---|---|---|---|---|
| `--file` | `-f` | String | Auto-detected | Path to `fabric.yml`. |
| `--from` | | String | **Required** | Source target name (for example, `staging`). |
| `--to` | | String | **Required** | Destination target name (for example, `prod`). |
| `--auto-approve` | `-y` | Flag | `false` | Skip the confirmation prompt. |

### Examples

**Promote from staging to production:**

```bash
fab-bundle promote --from staging --to prod
```

**Example output:**

```
Promote: staging → prod
  Source:  sales-analytics-staging (abc123-...)
  Dest:    sales-analytics-prod (def456-...)

  6 items to promote
Proceed? [y/N]: y

  + Created: bronze_lakehouse
  + Created: gold_lakehouse
  ~ Updated: ingest_notebook
  ~ Updated: transform_notebook
  + Created: daily_pipeline
  + Created: spark_env

Promoted 6 items from staging to prod.
```

> **Note**
>
> If the destination workspace does not exist, `promote` creates it automatically and assigns the capacity configured in the target.

> **Important**
>
> Promote copies item *definitions* from the source workspace. It does not copy data. Lakehouse tables, warehouse data, and other runtime state are not transferred.

---

## export

Export item definitions from a deployed workspace to local files.

### Syntax

```
fab-bundle export [OPTIONS]
```

### Options

| Option | Short | Type | Default | Description |
|---|---|---|---|---|
| `--file` | `-f` | String | Auto-detected | Path to `fabric.yml`. |
| `--target` | `-t` | String | *(default target)* | Target environment. |
| `--output` | `-o` | String | `.` | Output directory for exported files. |
| `--resource` | `-r` | String | *(all)* | Export a specific resource by name. If omitted, exports all items. |

### Examples

**Export all items from the dev workspace:**

```bash
fab-bundle export -t dev -o ./exported
```

**Example output:**

```
Exporting from workspace: sales-analytics-dev

  + ingest_notebook (Notebook): 2 files → exported/ingest_notebook
  + transform_notebook (Notebook): 2 files → exported/transform_notebook
  + daily_pipeline (DataPipeline): 1 files → exported/daily_pipeline
  = bronze_lakehouse (Lakehouse): no exportable definition
  = gold_lakehouse (Lakehouse): no exportable definition

Exported 3 item(s) to /Users/you/project/exported
```

**Export a single resource:**

```bash
fab-bundle export -t dev -r ingest_notebook -o ./exported
```

---

## generate

Generate a `fabric.yml` bundle definition by scanning an existing Fabric workspace.

### Syntax

```
fab-bundle generate [OPTIONS]
```

### Options

| Option | Short | Type | Default | Description |
|---|---|---|---|---|
| `--workspace` | `-w` | String | **Required** | Workspace name or GUID to scan. |
| `--output` | `-o` | String | `.` | Output directory for the generated `fabric.yml` and item definitions. |

### Examples

**Generate from a workspace name:**

```bash
fab-bundle generate -w "My Existing Workspace" -o ./generated
```

**Generate from a workspace GUID:**

```bash
fab-bundle generate -w "abc12345-def6-7890-abcd-ef1234567890" -o ./generated
```

**Example output:**

```
Scanning workspace: My Existing Workspace (abc12345-...)
  Found 8 items

  + Lakehouse: bronze_lake
  + Lakehouse: gold_lake
  + Notebook:  etl_step1
  + Notebook:  etl_step2
  + Pipeline:  nightly_run

Generated:
  ./generated/fabric.yml
  ./generated/notebooks/etl_step1/notebook-content.py
  ./generated/notebooks/etl_step2/notebook-content.py
```

> **Tip**
>
> Use `generate` to bootstrap a bundle definition for an existing workspace, then customize the generated `fabric.yml` to add variables, targets, security roles, and policies.

---

## bind

Bind an existing workspace item to bundle management. The item must already be defined in `fabric.yml`.

### Syntax

```
fab-bundle bind RESOURCE_NAME [OPTIONS]
```

### Arguments

| Argument | Required | Description |
|---|---|---|
| `RESOURCE_NAME` | Yes | The resource key as defined in `fabric.yml`. |

### Options

| Option | Short | Type | Default | Description |
|---|---|---|---|---|
| `--workspace` | `-w` | String | **Required** | Workspace name or GUID containing the item. |
| `--file` | `-f` | String | Auto-detected | Path to `fabric.yml`. |

### Examples

```bash
fab-bundle bind ingest_notebook -w "sales-analytics-dev"
```

**Example output:**

```
Bound: ingest_notebook
  Type:      Notebook
  Item ID:   abc123-def456-...
  Workspace: sales-analytics-dev
  Recorded to state. Visible in 'fab-bundle status'.

  This resource will be managed by the bundle on the next deploy.
  Changes to fabric.yml will be applied to the existing item.
```

> **Important**
>
> The resource must be defined in `fabric.yml` before you can bind it. Add the resource definition first, then run `bind` to associate it with the existing workspace item.

---

## import

Import existing resources into fab-bundle management from a Terraform state file or a live Fabric workspace.

### Syntax

```
fab-bundle import [OPTIONS]
```

### Options

| Option | Short | Type | Default | Description |
|---|---|---|---|---|
| `--from-terraform` | | String | | Path to a `terraform.tfstate` file. Extracts `microsoft_fabric_*` resources. |
| `--workspace` | `-w` | String | | Workspace name or GUID to import from. |
| `--output` | `-o` | String | `.` | Output directory for state files. |
| `--target` | `-t` | String | `dev` | Target name to assign to the imported state. |

> **Note**
>
> You must specify exactly one of `--from-terraform` or `--workspace`.

### Examples

**Import from Terraform state:**

```bash
fab-bundle import --from-terraform ./terraform.tfstate -t prod
```

**Example output:**

```
Found 4 Fabric resources in Terraform state
  lakehouse            bronze_lakehouse
  lakehouse            gold_lakehouse
  notebook             ingest_notebook
  datapipeline         daily_pipeline

Imported 4 resources to fab-bundle state.
```

**Import from a live workspace:**

```bash
fab-bundle import -w "My Workspace" -t dev
```

**Example output:**

```
Found 6 items in workspace 'My Workspace'
Imported 6 resources to fab-bundle state.
```

> **Tip**
>
> After importing, create or update your `fabric.yml` to define the resources, then run `fab-bundle deploy` to bring them under full bundle management.

---

## list

List available bundle templates that can be used with `fab-bundle init`.

### Syntax

```
fab-bundle list
```

### Examples

```bash
fab-bundle list
```

**Example output:**

```
Available templates:

  blank
    Empty project with minimal structure

  medallion
    Bronze/Silver/Gold lakehouse pattern with ingestion notebooks

Usage: fab bundle init --template <name> --name <project-name>
```

---

## doctor

Run diagnostic checks to validate your environment, dependencies, authentication, API connectivity, and bundle configuration.

### Syntax

```
fab-bundle doctor
```

### Examples

```bash
fab-bundle doctor
```

**Example output:**

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

### Checks performed

| Check | What it validates |
|---|---|
| Python version | Python >= 3.10 is installed. |
| Required packages | `pydantic`, `click`, `rich`, `yaml`, `requests`, `azure.identity` are importable. |
| Azure CLI installed | The `az` binary is found in PATH. |
| Azure CLI authenticated | `az account show` succeeds (a valid session exists). |
| Fabric API reachable | The Fabric REST API responds to a workspace list request. |
| `fabric.yml` found | A `fabric.yml` or `fabric.yaml` file exists in the current directory. |
| Bundle validates | The bundle definition parses and validates without errors. |

---

## graph

Visualize the bundle dependency graph in Mermaid, DOT (Graphviz), or plain text format.

### Syntax

```
fab-bundle graph [OPTIONS]
```

### Options

| Option | Short | Type | Default | Description |
|---|---|---|---|---|
| `--file` | `-f` | String | Auto-detected | Path to `fabric.yml`. |
| `--target` | `-t` | String | *(default target)* | Target environment. |
| `--format` | | Choice: `mermaid`, `dot`, `text` | `mermaid` | Output format. |
| `--output` | `-o` | String | *(stdout)* | Output file path. If omitted, prints to stdout. |

### Examples

**Generate a Mermaid diagram:**

```bash
fab-bundle graph
```

**Example output:**

```
graph TD
    spark_env["spark_env\n(environments)"]
    style spark_env fill:#457b9d,color:#fff
    bronze_lakehouse["bronze_lakehouse\n(lakehouses)"]
    style bronze_lakehouse fill:#2d6a4f,color:#fff
    ingest_notebook["ingest_notebook\n(notebooks)"]
    style ingest_notebook fill:#264653,color:#fff
    spark_env --> ingest_notebook
    bronze_lakehouse --> ingest_notebook
```

**Generate a DOT file for Graphviz:**

```bash
fab-bundle graph --format dot -o graph.dot
```

**Generate plain text:**

```bash
fab-bundle graph --format text
```

**Example output:**

```
  [environments] spark_env
  [lakehouses] bronze_lakehouse
  [notebooks] ingest_notebook ← spark_env, bronze_lakehouse
  [pipelines] daily_pipeline ← ingest_notebook
```

> **Tip**
>
> Paste Mermaid output into [mermaid.live](https://mermaid.live) or any Mermaid-compatible renderer (GitHub, GitLab, Notion, Confluence) to visualize the graph.

---

## watch

Watch the project directory for file changes and automatically deploy to the target workspace.

### Syntax

```
fab-bundle watch [OPTIONS]
```

### Options

| Option | Short | Type | Default | Description |
|---|---|---|---|---|
| `--file` | `-f` | String | Auto-detected | Path to `fabric.yml`. |
| `--target` | `-t` | String | *(default target)* | Target environment. |
| `--interval` | | Integer | `5` | File check interval in seconds. |

### Examples

**Watch and auto-deploy to dev:**

```bash
fab-bundle watch -t dev
```

**Example output:**

```
Watching for changes... (target: dev, interval: 5s)
  Press Ctrl+C to stop.

  [14:30:15] Changed: notebooks/ingest_notebook.py
  Deployed.

  [14:32:08] Changed: fabric.yml, notebooks/transform_notebook.py
  Deployed.
```

**Watch with a faster interval:**

```bash
fab-bundle watch -t dev --interval 2
```

### Watched file types

The watch command monitors files with the following extensions: `.py`, `.sql`, `.yml`, `.yaml`, `.json`, `.ipynb`, `.tmdl`, `.r`, `.scala`.

Directories named `.fab-bundle`, `__pycache__`, and `.venv` are excluded.

> **Warning**
>
> The `watch` command deploys changes automatically without a confirmation prompt. Use it only in development environments.

---

## check-update

Check if a newer version of Fabric Automation Bundles is available on PyPI.

### Syntax

```
fab-bundle check-update
```

### Examples

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

---

## Exit codes

All `fab-bundle` commands use the following exit codes:

| Code | Meaning |
|---|---|
| `0` | Success. |
| `1` | Error. The command failed due to a validation error, API error, authentication error, or runtime exception. |

---

## Environment variables

The following environment variables affect `fab-bundle` behavior:

| Variable | Description |
|---|---|
| `AZURE_TENANT_ID` | Azure AD tenant ID for service principal authentication. |
| `AZURE_CLIENT_ID` | Application (client) ID for service principal authentication. |
| `AZURE_CLIENT_SECRET` | Client secret for service principal authentication. |
| `HTTPS_PROXY` | HTTP proxy URL for outbound connections. |
| `FAB_BUNDLE_FILE` | Default path to `fabric.yml` (overrides auto-detection). |

---

## See also

- [Installation](../getting-started/installation.md) -- Install and configure Fabric Automation Bundles.
- [fabric.yml reference](../guide/fabric-yml.md) -- Complete schema reference for bundle definitions.
