# MCP Server

Use fab-bundle as an MCP (Model Context Protocol) server in Claude Code, Cursor, Windsurf, or any MCP-compatible client. This lets you manage Fabric workspaces conversationally.

## Install

```bash
pip install fabric-automation-bundles[mcp]
```

## Configure

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

### Cursor / Windsurf

Add to your MCP configuration file (check your IDE's MCP docs for the exact path):

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
> Uses `fab_status` to show all deployed resources with their types and IDs.

**"Deploy my project to dev"**
> Uses `fab_validate` to check the bundle, then `fab_plan` to show changes, then `fab_deploy` to execute.

**"Something changed in prod that I didn't deploy"**
> Uses `fab_drift` to compare deployed state against the bundle definition.

**"Run the ETL pipeline"**
> Uses `fab_run` with the pipeline name and target environment.

**"Set up a new Fabric project"**
> Uses `fab_list_capacities` to find available capacity, then `fab_list_templates` to show options.

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
