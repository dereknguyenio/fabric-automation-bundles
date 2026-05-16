# The declarative model

Fabric Automation Bundles is **declarative**. You describe the *desired state* of your Microsoft Fabric project in `fabric.yml`, and the CLI is responsible for figuring out what to create, update, or delete to make the live workspace match.

This page explains what that means in practice, how the desired-state / reconcile loop works, and how it differs from the imperative scripts that most Fabric automation starts as.

---

## Imperative vs. declarative

| | **Imperative** (scripts) | **Declarative** (`fabric.yml`) |
|---|---|---|
| You write | The *steps* to take | The *end state* you want |
| Order | You sequence every call | Resolved from a dependency graph |
| Re-runs | May fail or duplicate | Converge on the same state (idempotent) |
| Drift | Invisible until something breaks | Detected by comparing desired vs. actual |
| Deletes | Easy to forget | Computed from the diff |
| Review | Diff is a code diff of logic | Diff is a state diff of resources |

A typical imperative Fabric script reads like: *create the bronze lakehouse, then create the silver lakehouse, then upload notebook A, then update its default lakehouse to silver, then create the pipeline, then set its parameters…* Every step is your responsibility, and every step is a place where the script and the real workspace can disagree.

A declarative bundle reads like: *these are my lakehouses, these are my notebooks (each attached to one of those lakehouses), this is the pipeline that runs them.* The tool figures out the order and the operations.

---

## The desired-state / reconcile loop

Every `fab-bundle` command that touches a workspace follows the same four-phase loop:

1. **Parse** — `fabric.yml` (plus any `include:` files) is loaded, variables for the chosen `--target` are substituted, and the result is validated against the JSON schema. This produces the **desired state**.
2. **Resolve** — resources are sorted into a dependency graph (e.g. environments before notebooks, lakehouses before semantic models, semantic models before reports / Data Agents).
3. **Plan** — the desired state is compared against the **actual state** of the workspace (read live from the Fabric REST API, augmented by the local state file). The output is a diff: *create*, *update*, *replace*, *delete*, or *no-op* per resource.
4. **Apply** — the diff is executed in dependency order. Unchanged resources are skipped via content hashing. State is updated so the next run starts from a known baseline.

```text
fabric.yml ──► parse ──► resolve ──► plan ──► apply ──► state
   (desired)              (graph)    (diff)   (REST)    (actual)
                                       ▲                  │
                                       └──── drift ◄──────┘
```

The same loop is invoked by every workflow command:

- `validate` stops after **parse** — schema + reference checks only.
- `plan` stops after **plan** — shows the diff without touching the workspace.
- `deploy` runs all four phases.
- `drift` runs **parse → plan** and reports any actual-vs-desired differences.
- `destroy` inverts the diff — everything in state, nothing in desired, delete in reverse dependency order.

---

## What "desired state" actually contains

The desired state is the **fully-resolved** bundle for one target. That means:

- `${var.*}` and `${env.*}` substitutions are applied.
- `targets.<name>.variables` overrides are merged on top of top-level `variables`.
- `include:` files are merged.
- `extends:` parents are merged.
- Defaults from the schema are filled in.

What it does **not** contain:

- Anything that exists in the workspace but isn't in the bundle (those become candidates for *delete* — only if the resource type is managed by the bundle and the resource is recorded in state).
- Implementation details like REST endpoints or item IDs (those are looked up at plan time).

This separation is why a bundle is portable across workspaces and capacities — the YAML is the *what*, the provider is the *how*.

---

## Idempotency and content hashing

Running `fab-bundle deploy` twice in a row against an unchanged bundle is a no-op. This is enforced two ways:

- **Resource-level diffing** — each resource's desired definition is compared to its recorded state. Equal definitions produce a *no-op*.
- **Content hashing** — file-backed resources (notebooks, pipeline definitions, semantic model TMDL, report definitions) hash their payload. If the hash matches what was last deployed, the upload is skipped even if metadata changed elsewhere.

This is what makes CI/CD pipelines safe to run on every merge: a deploy that finds nothing to do exits cleanly in seconds.

---

## Drift detection

Because the tool always knows the desired state and can always read the actual state, **drift is just a plan with no apply**. `fab-bundle drift --target prod` answers: *what has changed in the live workspace since the last deploy?*

This catches:

- Manual edits in the Fabric portal.
- Out-of-band changes by other tools.
- Resources deleted in the portal that the bundle still expects.
- Configuration that was changed and not committed.

See [Drift Detection](../advanced/drift.md) for the full workflow and CI integration patterns.

---

## How this compares to other tools

- **Terraform** — same desired-state / plan / apply model, same dependency graph, same state file. Bundles apply that model to Fabric items (notebooks, pipelines, semantic models, Data Agents, …) that Terraform providers don't cover. See [Migrate from Terraform](migrate-from-terraform.md).
- **Databricks Asset Bundles** — also declarative YAML with targets and variables, focused on Databricks. Bundles applies the same idea to Microsoft Fabric.
- **`fabric-cicd`** — imperative deployment helper. Promotes items between workspaces but doesn't describe a project, resolve dependencies, or detect drift. See [Migrate from fabric-cicd](migrate-from-fabric-cicd.md).
- **Fabric CLI (`fab`)** — imperative item-level operations (`export`, `import`, `create`). A great primitive layer; not a project model.

---

## When *not* to use the declarative model

Declarative tools are the wrong fit for a few cases — be honest about them:

- **One-off exploration.** If you're prototyping a single notebook in the portal, a bundle is overkill. Use [`fab-bundle generate`](../cli/commands.md) later to capture it.
- **Highly dynamic resources.** If the *set* of resources is computed at runtime (e.g. one lakehouse per tenant, discovered from a database), a thin imperative wrapper that emits YAML and then calls `fab-bundle deploy` is usually cleaner than trying to express the loop in YAML.
- **Operations on data, not definitions.** Running a notebook, refreshing a semantic model, or kicking off a pipeline is imperative by nature. Bundles defines the resources; orchestration tools (Fabric pipelines, Airflow, ADF) run them.

---

## Next steps

- [`fabric.yml` reference](fabric-yml.md) — every top-level key in the desired-state schema.
- [Development Workflows](development-workflows.md) — `validate` → `plan` → `deploy` in practice.
- [Targets & Variables](targets-variables.md) — how the desired state varies across dev / staging / prod.
- [Drift Detection](../advanced/drift.md) — comparing desired vs. actual on a schedule.
