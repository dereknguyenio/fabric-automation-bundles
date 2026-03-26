# MCP Server

Use fab-bundle as an MCP (Model Context Protocol) server in GitHub Copilot, Claude Code, or any MCP-compatible client. This lets you manage Fabric workspaces conversationally.

## Install

```bash
pip install fabric-automation-bundles[mcp]
```

## Configure

### GitHub Copilot

Add to your project's `.vscode/mcp.json`:

```json
{
  "servers": {
    "fab-bundle": {
      "command": "fab-bundle-mcp"
    }
  }
}
```

Or add to your VS Code user settings (`settings.json`) under `"mcp.servers"` to use across all projects.

### Claude Code

Add to your project's `.claude/settings.json`:

```json
{
  "mcpServers": {
    "fab-bundle": {
      "command": "fab-bundle-mcp"
    }
  }
}
```

Or add globally to `~/.claude/settings.json` to use across all projects.

### Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "fab-bundle": {
      "command": "fab-bundle-mcp"
    }
  }
}
```

## Prerequisites

Before using the MCP server, make sure:

1. **Azure CLI authenticated:** `az login`
2. **fabric.yml exists** in your project directory
3. **Fabric capacity** is active and accessible

Run `fab-bundle doctor` to verify everything is configured correctly.

## Available Tools

| Tool | Description | Example prompt |
|------|-------------|----------------|
| `fab_validate` | Validate fabric.yml | "Validate my Fabric bundle" |
| `fab_plan` | Preview deployment changes | "What would change if I deploy to dev?" |
| `fab_deploy` | Deploy to a target | "Deploy to dev" |
| `fab_destroy` | Tear down resources | "Destroy the test environment" |
| `fab_status` | Show deployed resources | "What's deployed in prod?" |
| `fab_drift` | Detect out-of-band changes | "Check for drift in staging" |
| `fab_run` | Run a notebook or pipeline | "Run the ingest_to_bronze notebook in dev" |
| `fab_history` | Show deployment history | "Show me recent deployments" |
| `fab_doctor` | Diagnose issues | "Check if my Fabric setup is working" |
| `fab_list_templates` | List templates | "What templates are available?" |
| `fab_list_workspaces` | List workspaces | "Show me all Fabric workspaces" |
| `fab_list_capacities` | List capacities | "What Fabric capacities do I have?" |

## Example Conversations

**"What's in my Fabric workspace?"**
> The AI calls `fab_status` and responds:
>
> *"Your dev workspace has 12 items deployed: 3 lakehouses (bronze, silver, gold), 3 notebooks (ingest_to_bronze, transform_to_silver, aggregate_to_gold), 2 pipelines (daily_etl, weekly_refresh), 1 Spark environment, 1 warehouse, 1 SQL analytics endpoint, and 1 data agent. Last deployment was 3 hours ago. No drift detected."*

**"Deploy my project to dev"**
> The AI first calls `fab_validate` to check your bundle, then `fab_plan` to preview changes:
>
> *"Your fabric.yml is valid. Here's what will happen: 3 lakehouses will be created, 3 notebooks uploaded, and 2 pipelines configured with schedules. Total: 8 new resources. No existing resources will be modified. Should I proceed with the deployment?"*
>
> After you confirm, it calls `fab_deploy` and reports:
>
> *"Deployed 8 resources to sales-analytics-dev in 45 seconds. All items created successfully. You can open the workspace at https://app.fabric.microsoft.com/..."*

**"Something changed in prod that I didn't deploy"**
> The AI calls `fab_drift` and responds:
>
> *"I found drift in 2 items. A notebook 'manual_fix' was added directly in the portal (not in your fabric.yml). And the 'daily_etl' pipeline schedule was changed from 6:00 AM to 8:00 AM. Would you like me to update your fabric.yml to match, or redeploy to revert the changes?"*

**"Run the ETL pipeline"**
> The AI calls `fab_run` and responds:
>
> *"I've submitted the 'daily_etl' pipeline in the dev workspace. Job ID: a3f8c... You can monitor progress in the Fabric portal under Monitoring Hub. I'll check back -- want me to poll the status?"*

**"Set up a new Fabric project"**
> The AI calls `fab_list_capacities` and `fab_list_templates`, then responds:
>
> *"You have 2 capacities available: 'Team-Dev' (F8, West US 2) and 'Prod' (F16, East US). I found 4 templates: medallion (bronze/silver/gold lakehouse), starter (single lakehouse + notebook), warehouse (SQL-first with views), and custom (empty scaffold). Which template and capacity would you like to use?"*

## Setting up both MCP servers

For the best experience, use **fab-bundle-mcp** alongside **[Microsoft's Fabric MCP server](https://github.com/microsoft/mcp)**. fab-bundle-mcp lets the AI act on your workspace (deploy, plan, status), while Microsoft's Fabric MCP gives the AI deep knowledge of Fabric APIs and best practices.

### GitHub Copilot (`.vscode/mcp.json`)

```json
{
  "servers": {
    "fab-bundle": {
      "command": "fab-bundle-mcp"
    },
    "fabric": {
      "command": "npx",
      "args": ["-y", "@anthropic-ai/mcp-server-fetch", "https://github.com/microsoft/mcp"]
    }
  }
}
```

> Check Microsoft's [Fabric MCP repo](https://github.com/microsoft/mcp) for the latest install command -- the `args` above are illustrative.

### Claude Code (`.claude/settings.json`)

```json
{
  "mcpServers": {
    "fab-bundle": {
      "command": "fab-bundle-mcp"
    },
    "fabric": {
      "command": "npx",
      "args": ["-y", "@anthropic-ai/mcp-server-fetch", "https://github.com/microsoft/mcp"]
    }
  }
}
```

### Claude Desktop (`claude_desktop_config.json`)

```json
{
  "mcpServers": {
    "fab-bundle": {
      "command": "fab-bundle-mcp"
    },
    "fabric": {
      "command": "npx",
      "args": ["-y", "@anthropic-ai/mcp-server-fetch", "https://github.com/microsoft/mcp"]
    }
  }
}
```

### What each server provides

| MCP Server | Purpose | Example |
|------------|---------|---------|
| **fab-bundle-mcp** | Manage your Fabric project: deploy, plan, status, run, drift, destroy | "Deploy to dev", "Check for drift" |
| **Microsoft Fabric MCP** | Fabric API docs, best practices, item schemas | "How do I configure a pipeline trigger?", "What Spark versions does Fabric support?" |

Together, the AI can both *understand* Fabric and *act* on your workspace.

## Troubleshooting

**"fab-bundle-mcp: command not found"**
- Make sure you installed with `pip install fabric-automation-bundles[mcp]`
- Check that the pip scripts directory is in your PATH

**"Authentication error"**
- Run `az login` in your terminal first
- Or set `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET` environment variables

**Tools not showing up**
- Restart your IDE after adding the MCP configuration
- Check the MCP server logs for errors
