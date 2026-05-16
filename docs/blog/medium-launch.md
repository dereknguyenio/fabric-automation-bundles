# Stop Clicking Through Microsoft Fabric. Start Shipping It.

### Introducing **Fabric Automation Bundles** — one `fabric.yml`, one CLI, your entire Microsoft Fabric project as code.

---

If you build on Microsoft Fabric, you already know the feeling.

You spent the morning designing a beautiful medallion lakehouse in dev. Bronze, silver, gold. Notebooks wired up. A pipeline orchestrating the whole thing. A semantic model on top. A Data Agent answering business questions in natural language. It works. It’s elegant. You’re proud of it.

Then someone says the words that ruin your week:

> *“Great. Now do it again in staging. And prod. And keep them in sync.”*

You open the Fabric portal in three tabs. You start clicking. Capacity IDs. Workspace permissions. Connection strings. Lakehouse IDs that change between environments. Notebooks that need to be re-pointed at the new lakehouse. Pipelines that reference notebook IDs that don’t exist yet. Semantic models that need the gold lakehouse to exist *first*. A Data Agent that needs the semantic model to exist *first*. Security roles. Service principal access. The cron schedule that was “0 6 * * *” in dev but should be “0 2 * * *” in prod.

By the time you’re done, you’ve made eleven mistakes, fixed nine of them, and the other two won’t surface until the 6 AM run on Tuesday.

**There has to be a better way.**

There is. We built it. It’s open source. It’s called **[Fabric Automation Bundles](https://github.com/dereknguyenio/fabric-automation-bundles)**, and it turns the chaos above into this:

```bash
fab-bundle deploy --target prod
```

That’s it. That’s the post. Thanks for reading.

…okay, let me actually show you why this matters.

---

## The Gap Nobody Talks About

Microsoft Fabric is incredible. It unifies lakehouses, warehouses, notebooks, pipelines, Power BI, real-time intelligence, and AI agents into one platform. The vision is unmatched.

But the **project model** — the thing that says *“here is my application, here are its pieces, here is how to deploy it”* — doesn’t exist. Each tool in the ecosystem solves part of the problem:

- **The Fabric CLI** can export and import individual items. Great for one-offs. Not a project definition.
- **`fabric-cicd`** can deploy items across workspaces. Great for promotion. Doesn’t describe what your project *is*.
- **Terraform** can provision capacities and workspaces. Great for infrastructure. Doesn’t know about notebooks, pipelines, or semantic models.
- **The Fabric portal** is a beautiful click-ops experience. Great for exploration. A nightmare for repeatability.

What none of them do — and what every real-world Fabric project desperately needs — is a single, declarative answer to:

- What resources does this project need?
- How do they depend on each other?
- How does configuration vary across dev, staging, and prod?
- What security roles and permissions are required?
- How do I deploy everything, in the right order, every time?

If you’ve done serious work in Databricks, you know the answer over there is **Databricks Asset Bundles** — a YAML file, a CLI, a deployment model. Snowflake users have **schemachange** and **Snowpark Project Files**. Even Power BI alone has **Tabular Editor** and **pbi-tools**.

Fabric had nothing.

**Now it does.**

---

## Meet `fabric.yml`

Fabric Automation Bundles is built around one idea: **your entire Fabric project should fit in a single, version-controlled file** — and that file should be the source of truth.

It's a **declarative** model, in the same lineage as Terraform and Databricks Asset Bundles. You describe the *desired state* of your workspace — these lakehouses, these notebooks pointed at those lakehouses, this pipeline that runs them on this schedule — and the CLI works out the rest:

- The **order** to create things in, from the dependency graph (lakehouses → notebooks → pipelines → semantic models → reports → Data Agents).
- The **diff** between what you've described and what's actually live in the workspace, so `deploy` only does the work that's needed.
- The **drift** when somebody clicks something in the portal that doesn't match the file.

That's it. Re-running the same `deploy` against an unchanged bundle is a no-op. Re-running it against a changed bundle does the minimum required to converge. Re-running it against a workspace someone hand-edited tells you exactly what they touched.

Here's a real bundle. Read it like English. It is English:

```yaml
bundle:
  name: my-analytics
  version: "1.0.0"

resources:
  environments:
    spark-env:
      runtime: "1.3"
      libraries: [semantic-link-labs]

  lakehouses:
    bronze:
      description: "Raw data landing zone"
    gold:
      description: "Business-ready datasets"

  notebooks:
    etl-pipeline:
      path: ./notebooks/etl.py
      environment: spark-env
      default_lakehouse: bronze

  pipelines:
    daily-refresh:
      schedule:
        cron: "0 6 * * *"
        timezone: America/Chicago
      activities:
        - notebook: etl-pipeline

  semantic_models:
    analytics-model:
      path: ./semantic_model/
      default_lakehouse: gold

  data_agents:
    my-agent:
      sources: [gold]
      instructions: ./agent/instructions.md

security:
  roles:
    - name: engineers
      entra_group: sg-data-eng
      workspace_role: contributor
    - name: analysts
      entra_group: sg-analysts
      workspace_role: viewer

targets:
  dev:
    default: true
    workspace:
      name: my-analytics-dev
      capacity_id: "your-dev-capacity-guid"

  prod:
    workspace:
      name: my-analytics-prod
    run_as:
      service_principal: sp-fabric-prod
```

That file *is* your project. Your lakehouses, notebooks, pipelines, semantic models, AI agents, security roles, and per-environment configuration — all of it. Commit it to git. Diff it. PR it. Roll it back.

---

## Four Commands. That’s the Whole Workflow.

```bash
fab-bundle init --template medallion --name my-project
fab-bundle validate
fab-bundle plan --target dev
fab-bundle deploy --target dev
```

If you’ve used Terraform, this will feel like coming home. If you’ve used Databricks Asset Bundles, you’ll be productive in five minutes. If you’ve never touched IaC before, you’ll wonder why everyone makes it sound complicated.

### `validate` — fail fast, before you touch the cloud
Schema-checks the bundle, resolves every reference, and walks the dependency graph. If your pipeline references a notebook that doesn’t exist, you find out in 200ms — not 20 minutes into a deployment.

### `plan` — see exactly what will change
```
Deployment Plan: my-analytics
  Target:    dev
  Workspace: my-analytics-dev

  +  bronze-lakehouse      Lakehouse      create    New resource
  +  silver-lakehouse      Lakehouse      create    New resource
  +  gold-lakehouse        Lakehouse      create    New resource
  +  spark-env             Environment    create    New resource
  +  etl-bronze            Notebook       create    New resource
  +  etl-silver            Notebook       create    New resource
  +  daily-refresh         DataPipeline   create    New resource
  ~  analytics-model       SemanticModel  update    Definition updated

  Summary: 7 to create, 1 to update
```

No surprises. No “oh, I didn’t mean to delete that.” Plan first, deploy second. Always.

### `deploy` — everything, in the right order, every time
Topological sort under the hood. Environments before lakehouses. Lakehouses before notebooks. Notebooks before pipelines. Semantic models before reports. You stop thinking about order — because the tool already did.

### `drift` — catch the click-ops sneak attacks
Someone “just made a quick change in the portal”? `fab-bundle drift` tells you, in seconds, what no longer matches the bundle. Your `fabric.yml` is the truth. Drift makes sure reality agrees.

---

## What You Actually Get

Let’s be specific about why this is worth your time.

### 🧱 45 item types, across every Fabric workload
Lakehouses, Warehouses, Notebooks, Data Pipelines, Spark Job Definitions, Semantic Models, Reports, Eventhouses, KQL Databases, Eventstreams, Reflexes, ML Models, ML Experiments, Data Agents, Operations Agents, Anomaly Detectors, Ontologies, Variable Libraries, GraphQL APIs, User Data Functions, OneLake Shortcuts… **30 of them are verified end-to-end against the live Fabric API today.** The rest are wired in and progressing through verification.

### 🌍 Multi-environment, the way it should be
One bundle, many targets. Variables resolve per-target. Capacity IDs swap automatically. Schedules differ between dev and prod. Service principals run prod, your `az login` runs dev. No copy-pasted YAML, no environment-specific forks.

### 🔁 Real CI/CD, end-to-end, today
Not a slide. A working pipeline. We ship two starter repos:

- **GitHub Actions** → [`fabric-fab-cicd-example`](https://github.com/dereknguyenio/fabric-fab-cicd-example) — click *Use this template*, add five secrets, push. Done.
- **Azure DevOps** → [`fabric-fab-cicd-ado-example`](https://github.com/dereknguyenio/fabric-fab-cicd-ado-example) — same idea, same five-minute setup.

Validate on PR. Plan on PR. Auto-deploy to staging on merge. Manual approval gate before prod. The patterns your platform team already expects from every other production system — finally available for Fabric.

### 🤖 Built for the AI-native workflow (MCP)
Plug Fabric Automation Bundles directly into **GitHub Copilot** or **Claude Code** via the Model Context Protocol:

```bash
pip install fabric-automation-bundles[mcp]
```

Then talk to your Fabric workspace like a person:

> *“Deploy to dev.”*
> *“Check for drift in prod.”*
> *“Run the daily ETL pipeline and tell me when it finishes.”*
> *“What changed in this bundle since last Friday?”*

Twelve MCP tools — `validate`, `plan`, `deploy`, `destroy`, `status`, `drift`, `run`, `history`, `doctor`, `list-templates`, `list-workspaces`, `list-capacities` — all callable by your AI assistant, with bundled instruction files for both Copilot and Claude so the model actually understands your project conventions.

This is what “AI for data engineering” should feel like: not a chatbot guessing at clicks, but an agent driving a real, deterministic, production-grade tool.

### 🪄 Reverse-generate from an existing workspace
Already have a workspace with thirty items in it that you cannot rebuild from scratch? One command:

```bash
fab-bundle generate --workspace "My Existing Workspace"
```

It walks your workspace, pulls every item, and writes a `fabric.yml` you can clean up and check into git. The fastest possible on-ramp from “organic chaos” to “version-controlled.”

### 📐 Templates that aren’t just hello-world
- **`medallion`** — full bronze/silver/gold lakehouse, ETL notebooks, scheduled pipeline, semantic model, dashboard, Data Agent with few-shot examples, security roles, dev/staging/prod targets.
- **`osdu_analytics`** — a real industry template for Oil, Gas & Energy. ADME (Azure Data Manager for Energy) integration, OSDU Search API ingestion, Well/Wellbore/Production entity flattening, SQL views for BI (well master, production trends, field rollups), and a Data Agent loaded with petroleum engineering context (GOR, water cut, decline analysis).

You can write your own templates by dropping a directory into `fab_bundle/templates/`. The template engine is Jinja2, so anything you can express in YAML, you can parameterize.

### 🔐 Authentication that just works
`azure-identity` under the hood. `az login` for local dev. Service principal env vars for CI/CD. KeyVault for secrets. The same auth story your security team already approved.

### ✨ A delightful authoring experience
Add four lines to `.vscode/settings.json` and you get full autocomplete and validation for `fabric.yml` from the bundled JSON Schema. Typos caught as you type. Resource references autocompleted. Field documentation on hover. Authoring a bundle should feel like a well-tooled programming language, not a YAML guessing game.

---

## How It Actually Works (For the Curious)

Under the hood, Fabric Automation Bundles is a clean, well-tested Python package:

```
fab_bundle/
├── cli.py              # Click CLI
├── models/             # 30+ Pydantic models — the schema is the spec
├── engine/
│   ├── loader.py       # YAML parser with includes + variable substitution
│   ├── resolver.py     # Topological dependency sort
│   ├── planner.py      # Diff engine (desired vs actual)
│   ├── deployer.py     # Executes plans via Fabric REST API
│   ├── state.py        # State tracking + drift detection
│   └── secrets.py      # env vars + Azure KeyVault
├── providers/
│   └── fabric_api.py   # Fabric REST client (workspace, items, git, jobs)
├── generators/         # Reverse-generate + Jinja2 templates
└── templates/          # Built-in starter projects
```

The flow is the one Terraform taught us all to love:

1. **Parse** the bundle (`loader`) — including any `include:` files and `${var.name}` substitutions.
2. **Resolve** the dependency graph (`resolver`) — environments → lakehouses → notebooks → pipelines → semantic models → reports → agents.
3. **Plan** the diff (`planner`) — desired state from `fabric.yml` vs actual state from the live workspace.
4. **Deploy** (`deployer`) — apply create/update/delete operations through the Fabric REST API, with hash-based incremental skipping so unchanged resources aren’t redeployed.
5. **Track** (`state`) — record what was deployed so we can detect drift and roll back.

Every layer is independently testable. Every layer is independently replaceable. This is software engineering applied to Fabric — not a script that grew teeth.

---

## Where This Is Headed

Today, Fabric Automation Bundles ships the standalone CLI `fab-bundle`. The long-term goal is integration as a `fab bundle` subcommand in the [official Microsoft Fabric CLI](https://github.com/microsoft/fabric-cli), so the same workflow lives natively in the platform tools you already use. Until then, both syntaxes work — pick whichever fits your install.

The roadmap is public, the tests run on every PR, and the CI/CD examples are battle-tested. The core (`validate`, `plan`, `deploy`, `destroy`, `drift`, `status`, `history`, `doctor`) is **stable**. Remote state, the MCP server, OneLake data access roles, environment library publishing — **beta**. Watch mode, canary deploys, Slack/Teams notifications, policy enforcement — **experimental, ready to harden with real-world feedback**.

That feedback is where you come in.

---

## Get Started in 60 Seconds

```bash
pip install fabric-automation-bundles
fab-bundle init --template medallion --name my-first-bundle
cd my-first-bundle
fab-bundle validate
fab-bundle plan --target dev
fab-bundle deploy --target dev
```

That’s a fully working medallion architecture, deployed to your Fabric workspace, before your coffee gets cold.

Want CI/CD next? Click **Use this template** on the [GitHub Actions starter](https://github.com/dereknguyenio/fabric-fab-cicd-example) (or the [Azure DevOps starter](https://github.com/dereknguyenio/fabric-fab-cicd-ado-example)), add your five secrets, push to `main`, and watch your Fabric environments deploy themselves.

Want to plug it into your AI assistant? Add the MCP server to your Copilot or Claude config and start typing `“deploy to dev.”`

---

## A Call to the Fabric Community

Microsoft Fabric is going to be the data platform of the next decade. But platforms are made by their tooling, not just their features. Databricks won the engineer’s heart in part because Databricks Asset Bundles made deployments boring, repeatable, and version-controlled. Snowflake won the data engineer’s heart in part because schemachange and dbt made schema and modeling boring, repeatable, and version-controlled.

Fabric deserves the same. Fabric Automation Bundles is our open-source contribution toward making that happen — but it gets dramatically better with you in it.

If this resonates:

- ⭐ **Star the repo** → [github.com/dereknguyenio/fabric-automation-bundles](https://github.com/dereknguyenio/fabric-automation-bundles)
- 📖 **Read the docs** → [dereknguyenio.github.io/fabric-automation-bundles](https://dereknguyenio.github.io/fabric-automation-bundles/)
- 🐛 **Open an issue** with the resource you wish was first-class.
- 🛠️ **Open a PR** — `pip install -e ".[dev]" && pytest` and you’re a contributor.
- 💬 **Tell a teammate.** This works infinitely better when your whole org speaks `fabric.yml`.

The portal is great for exploring. Code is great for shipping.

**Stop clicking. Start shipping.**

```bash
pip install fabric-automation-bundles
```

---

*Fabric Automation Bundles is MIT-licensed and maintained in the open at [github.com/dereknguyenio/fabric-automation-bundles](https://github.com/dereknguyenio/fabric-automation-bundles). It is an independent open-source project and is not an official Microsoft product.*

*If this saved you a Tuesday morning, consider clapping 👏 and following along — there’s a lot more coming.*
