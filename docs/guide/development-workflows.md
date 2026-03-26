# Development Workflows

There are three ways to develop with fab-bundle. Choose the one that fits your team.

## Pattern 1: Write Local

Best for: New projects, small teams, developers comfortable with code editors.

You write notebooks and fabric.yml locally, test via `fab-bundle deploy`, and iterate.

```
┌─────────────────────────────────────────────────┐
│ Local Machine                                   │
│                                                 │
│  1. fab-bundle init --template medallion        │
│  2. Edit notebooks in VS Code / your editor     │
│  3. fab-bundle validate                         │
│  4. fab-bundle deploy -t dev                    │
│  5. Open Fabric portal → run notebook → verify  │
│  6. Fix issues locally → redeploy               │
│  7. git commit + push → CI/CD to test/prod      │
└─────────────────────────────────────────────────┘
```

### How it works

```bash
# Create project
fab-bundle init --template medallion --name my-project
cd my-project

# Edit fabric.yml — set your capacity_id and workspace names
# Edit notebooks in ./notebooks/ with your editor

# Deploy to dev to test
fab-bundle deploy -t dev

# Open Fabric portal — your notebooks are there
# Run them, check the output, verify data in lakehouses

# Something broken? Fix locally, redeploy
fab-bundle deploy -t dev

# Working? Commit and push
git add -A && git commit -m "feat: add ETL pipeline"
git push  # CI/CD deploys to test → prod
```

### Limitations

- Notebooks are uploaded as-is — no Spark intellisense while editing locally
- You can't run notebooks locally (they need Fabric Spark)
- Testing means deploying to dev and running in the portal
- Best for simple notebooks; complex Spark code benefits from portal development

### When to use

- Greenfield projects (no existing workspace)
- Teams that prefer code-first development
- CI/CD-heavy workflows where everything is in git

---

## Pattern 2: Develop in Portal, Export to Git

Best for: Most teams. Developers use the full Fabric portal experience, then capture state for CI/CD.

```
┌─────────────────────────────────────────────────┐
│ Fabric Portal (dev workspace)                   │
│                                                 │
│  1. Create/edit notebooks in the portal         │
│  2. Run notebooks, test with real data          │
│  3. Build pipelines, configure schedules        │
│  4. Everything working? Export:                 │
│                                                 │
│     fab-bundle generate --workspace "my-dev"    │
│                                                 │
│  5. Commit fabric.yml + notebooks to git        │
│  6. CI/CD deploys to test → prod                │
│  7. Future changes: edit in portal → re-export  │
└─────────────────────────────────────────────────┘
```

### How it works

```bash
# Step 1: Develop in the Fabric portal
# - Create lakehouses, notebooks, pipelines manually
# - Run notebooks, test with real data
# - Iterate until everything works

# Step 2: Export the workspace to fabric.yml
fab-bundle generate --workspace "my-dev-workspace"
# Creates:
#   fabric.yml          — all resources declared
#   notebooks/*.py      — exported notebook content
#   pipelines/*.json    — pipeline definitions

# Step 3: Add targets for test/prod
# Edit fabric.yml to add:
#   targets:
#     dev:
#       workspace:
#         name: my-dev-workspace
#         capacity_id: "..."
#     test:
#       workspace:
#         name: my-test-workspace
#         capacity_id: "..."
#     prod:
#       workspace:
#         name: my-prod-workspace
#         capacity_id: "..."

# Step 4: Commit to git
git init && git add -A
git commit -m "feat: initial export from dev workspace"
git push

# Step 5: CI/CD deploys test and prod automatically

# Step 6: Future changes
# Edit in portal → re-export → commit → CI/CD deploys
fab-bundle generate --workspace "my-dev-workspace"
git add -A && git commit -m "feat: updated ETL logic"
git push
```

### Limitations

- `fab-bundle generate` exports the current state — manual diff review needed
- Portal edits aren't automatically captured in git (you must re-export)
- Risk of forgetting to export after portal changes

### When to use

- Teams with existing Fabric workspaces
- Developers who prefer the portal's notebook experience
- Projects where you need real Spark + real data during development

---

## Pattern 3: Git Sync + fab-bundle

Best for: Enterprise teams. Fabric's built-in git sync handles notebook content, fab-bundle handles infrastructure and CI/CD deployment.

```
┌─────────────────────────────────────────────────┐
│ Fabric Portal (dev workspace with git sync)     │
│                                                 │
│  1. Enable git sync on dev workspace            │
│     (Settings → Git integration → Connect)      │
│  2. Fabric auto-commits notebook changes to git │
│  3. fab-bundle manages everything else:         │
│     - Lakehouses, warehouses, environments      │
│     - Pipelines, schedules, security roles      │
│     - Deployment to test/prod                   │
│                                                 │
│  fabric.yml = infrastructure                    │
│  git sync = notebook content                    │
│  fab-bundle deploy = promotion to test/prod     │
└─────────────────────────────────────────────────┘
```

### How it works

```bash
# Step 1: Set up dev workspace with git sync
# In Fabric portal:
#   Workspace settings → Git integration → Connect to Azure DevOps or GitHub
#   Select repo, branch, folder
#   Fabric syncs notebook content automatically

# Step 2: Create fabric.yml for infrastructure
# You can write it manually or generate from the workspace:
fab-bundle generate --workspace "my-dev-workspace"

# Step 3: Edit fabric.yml to REMOVE notebook paths
# Since git sync handles notebook content, fab-bundle only manages infrastructure:
#
#   notebooks:
#     ingest_to_bronze:
#       # path: ./notebooks/ingest.py  ← REMOVE this, git sync handles it
#       description: "Ingest raw data"
#       environment: spark_env
#       default_lakehouse: bronze
#
# Or keep the paths — fab-bundle will update the definition on deploy,
# which is useful if you want CI/CD to override what git sync committed.

# Step 4: Commit fabric.yml
git add fabric.yml && git commit -m "feat: add infrastructure definition"
git push

# Step 5: Developer workflow
# - Edit notebooks in Fabric portal (auto-synced to git)
# - Edit fabric.yml for infrastructure changes (lakehouses, pipelines, security)
# - Both flow through CI/CD:
#   PR → validate → plan → merge → deploy to test → deploy to prod

# Step 6: CI/CD deploys infrastructure to test/prod
# Notebooks are already synced via git
# fab-bundle creates lakehouses, pipelines, security, environments
fab-bundle deploy -t prod -y
```

### What git sync handles vs what fab-bundle handles

| Component | Git Sync | fab-bundle |
|-----------|----------|------------|
| Notebook content (.py, .ipynb) | ✅ Auto-synced | ✅ Can also deploy |
| Lakehouse creation | ❌ | ✅ |
| Pipeline creation + schedules | ❌ | ✅ |
| Environment + libraries | ❌ | ✅ |
| Warehouse + SQL views | ❌ | ✅ |
| Security roles | ❌ | ✅ |
| OneLake data access roles | ❌ | ✅ |
| Data agents | ❌ | ✅ |
| Multi-environment promotion | ❌ | ✅ |
| Drift detection | ❌ | ✅ |

### Limitations

- Git sync is workspace-level — you can't sync individual items
- Git sync only works with Azure DevOps or GitHub
- Conflict resolution between git sync and fab-bundle deploy needs care
- If both git sync and fab-bundle update the same notebook, last write wins

### When to use

- Enterprise teams with established git workflows
- Projects where notebook development happens in the portal
- Teams that need infrastructure-as-code but don't want to manage notebook files manually
- When you need security roles, schedules, and environments deployed consistently

---

## Pattern 4: VS Code + Fabric Extension + fab-bundle

Best for: Developers who want the full VS Code experience (Claude Code, GitHub Copilot, extensions) while running notebooks on real Fabric Spark compute.

The [Fabric Data Engineering VS Code Extension](https://learn.microsoft.com/en-us/fabric/data-engineering/setup-vs-code-extension) lets you author notebooks in VS Code and execute them on remote Fabric Spark — no portal needed.

```
┌─────────────────────────────────────────────────┐
│ VS Code                                         │
│                                                 │
│  Fabric Extension  ← connects to workspace      │
│  Claude Code / Copilot  ← AI assistance         │
│  fab-bundle  ← infrastructure + deployment      │
│                                                 │
│  1. Install Fabric VS Code Extension            │
│  2. Connect to your dev workspace               │
│  3. Create/edit notebooks in VS Code            │
│  4. Run cells on Fabric Spark (remote compute)  │
│  5. fab-bundle deploy -t dev  (infra changes)   │
│  6. git commit + push → CI/CD to test/prod      │
└─────────────────────────────────────────────────┘
```

### Setup

```bash
# 1. Install the Fabric VS Code extension
#    VS Code → Extensions → search "Fabric Data Engineering" → Install
#    Or: code --install-extension ms-fabric.fabricdataengineering

# 2. Sign in to Fabric
#    Click the Fabric icon in VS Code sidebar → Sign in

# 3. Select your workspace
#    Browse workspaces → select your dev workspace

# 4. Open or create notebooks
#    Notebooks appear in the explorer → edit with full VS Code features
#    Select kernel "Microsoft Fabric Runtime" to run on remote Spark

# 5. Use AI assistance
#    Claude Code: ask it to write Spark code, fix errors, optimize queries
#    Copilot: inline completions while writing PySpark
#    Fabric AI Agent: context-aware notebook assistance (March 2026)

# 6. fab-bundle manages infrastructure
fab-bundle init --name my-project
# Edit fabric.yml for lakehouses, pipelines, security
fab-bundle deploy -t dev

# 7. Commit everything
git add -A && git commit -m "feat: new ETL pipeline"
git push  # CI/CD deploys to test → prod
```

### What each tool handles

| Tool | Responsibility |
|------|----------------|
| **Fabric VS Code Extension** | Notebook editing + remote Spark execution |
| **Claude Code / Copilot** | AI-assisted code writing + debugging |
| **fab-bundle** | Infrastructure (lakehouses, pipelines, security, environments) |
| **fab-bundle deploy** | Promotion to test/prod |
| **Git** | Version control + CI/CD trigger |

### The AI-assisted development loop

```bash
# In VS Code with Claude Code + Fabric Extension:

# 1. "Create a notebook that reads from bronze and deduplicates by order_id"
#    → Claude Code writes the PySpark code

# 2. Run it on Fabric Spark (Ctrl+Enter on cell)
#    → Executes on remote compute, real data

# 3. "This is slow, optimize the join"
#    → Claude Code rewrites with broadcast join

# 4. Run again → verify it's faster

# 5. "Now deploy the infrastructure"
#    → Claude Code calls fab_deploy via MCP
#    → Or you run: fab-bundle deploy -t dev

# 6. Commit and push → CI/CD handles test/prod
```

### Limitations

- Fabric VS Code Extension requires sign-in (can't work fully offline)
- Remote Spark execution has startup latency (~30s for first cell)
- Some Fabric features (pipeline designer, semantic model editor) are portal-only
- The extension is GA but some features (AI agent) are still preview

### When to use

- Teams that live in VS Code
- Developers using Claude Code or GitHub Copilot for AI assistance
- When you want real Spark execution without leaving your editor
- Best of both worlds: local editing + remote compute + AI + CI/CD

---

## Comparison

| | Write Local | Portal + Export | Git Sync + fab-bundle | VS Code + Fabric Extension |
|---|---|---|---|---|
| **Notebook editing** | VS Code (no Spark) | Fabric portal | Fabric portal | VS Code (with Spark) |
| **Testing** | Deploy first, then portal | Run in portal | Run in portal | Run from VS Code |
| **AI assistance** | Claude Code / Copilot | Fabric Copilot | Fabric Copilot | Claude Code + Copilot + Fabric AI Agent |
| **Git integration** | Manual commit | Manual export | Auto-sync | Manual commit |
| **Infrastructure** | fabric.yml | fabric.yml (generated) | fabric.yml | fabric.yml |
| **Best for** | Simple projects | Existing workspaces | Enterprise | AI-first development |
| **Complexity** | Low | Medium | Medium-High | Medium |

## Recommended Starting Point

1. **New project?** → Pattern 1 (Write Local). Run `fab-bundle init` and start coding.
2. **Existing workspace?** → Pattern 2 (Portal + Export). Run `fab-bundle generate` to capture what you have.
3. **Enterprise with git sync?** → Pattern 3. Use git sync for notebooks, fab-bundle for everything else.
4. **Want AI + real Spark in VS Code?** → Pattern 4. Install the Fabric VS Code Extension + Claude Code/Copilot + fab-bundle MCP server.
