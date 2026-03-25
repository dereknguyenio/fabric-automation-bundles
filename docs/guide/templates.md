# Templates

## Built-in Templates

### medallion
Bronze/Silver/Gold lakehouse architecture with ETL notebooks, pipelines, and data agents.

### osdu_analytics
OSDU on Fabric for Oil, Gas & Energy with well/wellbore/production analytics.

## Custom Templates

Create a directory with `template.yml` and `fabric.yml`:

```yaml
# template.yml
name: my-template
description: "My custom template"
variables:
  project_name:
    description: "Project name"
    default: "my-project"
```

## Remote Templates

```bash
fab-bundle init --template https://example.com/template.tar.gz
fab-bundle init --template github:org/repo
```
