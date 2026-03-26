# Quick Start

## Create a new project

```bash
fab-bundle init --template medallion --name my-analytics
cd my-analytics
```

This creates a project with:
- 3 lakehouses (bronze, silver, gold)
- 3 ETL notebooks
- 1 data pipeline with scheduling
- 1 Spark environment
- 1 data agent
- Dev/staging/prod targets

## Configure your capacity

Find your Fabric capacity GUID:

```bash
az rest --method get \
  --url "https://api.fabric.microsoft.com/v1/capacities" \
  --resource "https://api.fabric.microsoft.com"
```

Update `fabric.yml` with your capacity ID:

```yaml
workspace:
  capacity_id: "your-capacity-guid-here"
```

## Validate

```bash
fab-bundle validate
```

## Plan (dry-run)

```bash
fab-bundle plan -t dev
```

## Deploy

```bash
fab-bundle deploy -t dev
```

## Check status

```bash
fab-bundle status -t dev
fab-bundle drift -t dev
```

---

## Quick Start with Claude Code (MCP)

If you use Claude Code, Cursor, or Windsurf, you can manage Fabric conversationally instead of typing CLI commands.

### 1. Install with MCP support

```bash
pip install fabric-automation-bundles[mcp]
```

### 2. Authenticate

```bash
az login
```

### 3. Add the MCP server

**Claude Code** — add to `.claude/settings.json` in your project root (or `~/.claude/settings.json` for global):

```json
{
  "mcpServers": {
    "fab-bundle": {
      "command": "fab-bundle-mcp"
    }
  }
}
```

**Claude Desktop** — add to `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS):

```json
{
  "mcpServers": {
    "fab-bundle": {
      "command": "fab-bundle-mcp"
    }
  }
}
```

**Cursor / Windsurf** — add to your IDE's MCP config file (check your IDE's MCP docs for the exact path).

### 4. Add CLAUDE.md to your project (optional but recommended)

Copy `examples/CLAUDE.md` from the fab-bundle repo to your project root. This gives Claude Code context about your project structure and available tools.

### 5. Start talking

```
You: "Create a new Fabric project for sales analytics"
You: "What capacities do I have?"
You: "Deploy to dev"
You: "Run the ingest notebook"
You: "Check for drift in prod"
You: "Show me what's deployed"
```

Claude Code will use the 12 MCP tools (`fab_validate`, `fab_plan`, `fab_deploy`, `fab_status`, `fab_drift`, `fab_run`, etc.) to execute your requests against the live Fabric API.

### 6. Combine with Fabric VS Code Extension

For the best experience, also install the [Fabric Data Engineering VS Code Extension](https://marketplace.visualstudio.com/items?itemName=ms-fabric.fabricdataengineering). This lets you:

- Edit notebooks in VS Code with Claude Code helping
- Run cells on remote Fabric Spark compute
- Use fab-bundle MCP for infrastructure management
- All without leaving VS Code

See [Development Workflows](../guide/development-workflows.md) for detailed patterns.
